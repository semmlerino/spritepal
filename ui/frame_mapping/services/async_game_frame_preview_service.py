"""Async game frame preview generation service.

Offloads game frame preview generation to a background thread to avoid
blocking the UI during project load or palette changes. Generates previews
for multiple frames in a batch, emitting results incrementally.

Key design:
- Worker runs preview generation in background thread
- Request ID pattern cancels stale batches when new request arrives
- QImage created in worker (thread-safe), QPixmap conversion on main thread
- Emits preview_ready for each completed preview (incremental UI updates)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

if TYPE_CHECKING:
    from typing import override
else:

    def override(f):
        return f


from core.repositories.capture_result_repository import CaptureResultRepository
from ui.common import WorkerManager
from ui.frame_mapping.services.async_service_base import AsyncServiceBase
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

logger = get_logger(__name__)


@dataclass
class GameFramePreviewRequest:
    """Request for game frame preview generation."""

    frame_id: str
    capture_path: Path
    selected_entry_ids: list[int]
    rom_offsets: list[int] = field(default_factory=list)


@dataclass
class BatchPreviewRequest:
    """Batch request for multiple game frame previews."""

    request_id: int
    requests: list[GameFramePreviewRequest]
    capture_repository: CaptureResultRepository


class _GameFramePreviewWorker(QObject):
    """Worker that generates game frame previews in a background thread."""

    preview_ready = Signal(int, str, QImage)
    """Emitted when a single preview is generated in worker thread.

    Internal signal used to communicate from worker thread to service.
    The service converts QImage to QPixmap and relays as public preview_ready signal.

    Args:
        request_id: Internal request ID for tracking (used to cancel stale requests)
        frame_id: ID of the game frame
        qimage: QImage of the rendered preview (thread-safe)

    Emitted by:
        - process_batch() → for each successfully generated preview

    Triggers:
        - AsyncGameFramePreviewService._on_preview_ready()
    """

    batch_finished = Signal(int)
    """Emitted when all previews in a batch are generated.

    Internal signal used to signal batch completion from worker thread.
    The service relays this as the public batch_finished signal.

    Args:
        request_id: Internal request ID for tracking (used to cancel stale requests)

    Emitted by:
        - process_batch() → after all previews are generated or batch is cancelled

    Triggers:
        - AsyncGameFramePreviewService._on_batch_finished()
    """

    def __init__(self) -> None:
        super().__init__()
        self._state_mutex = QMutex()
        self._target_request_id = 0

    def set_target_request_id(self, req_id: int) -> None:
        """Update target request ID and request stop of current work."""
        with QMutexLocker(self._state_mutex):
            self._target_request_id = req_id

    def init_target_request_id(self, req_id: int) -> None:
        """Initialize target request ID for new work (does not set stop flag)."""
        with QMutexLocker(self._state_mutex):
            self._target_request_id = req_id

    def _should_cancel(self, request_id: int) -> bool:
        """Check if this request should be cancelled."""
        with QMutexLocker(self._state_mutex):
            return request_id != self._target_request_id

    @Slot(BatchPreviewRequest)
    def process_batch(self, batch: BatchPreviewRequest) -> None:
        """Process batch of preview requests."""
        request_id = batch.request_id

        # Fast rejection if already stale
        if self._should_cancel(request_id):
            return

        for req in batch.requests:
            # Check for cancellation between frames
            if self._should_cancel(request_id):
                return

            try:
                qimage = self._generate_preview(req, batch.capture_repository)
                if qimage is not None and not qimage.isNull():
                    self.preview_ready.emit(request_id, req.frame_id, qimage)
            except Exception as e:
                logger.warning("Failed to generate preview for frame %s: %s", req.frame_id, e)

        # Emit batch finished (only if not cancelled)
        if not self._should_cancel(request_id):
            self.batch_finished.emit(request_id)

    def _generate_preview(
        self,
        req: GameFramePreviewRequest,
        capture_repository: CaptureResultRepository,
    ) -> QImage | None:
        """Generate preview for a single game frame.

        Uses shared PreviewRenderer to ensure consistent rendering with
        the synchronous PreviewService path.
        """
        from ui.frame_mapping.services.preview_renderer import PreviewRenderer

        # Parse and filter capture using shared utility
        capture_result, _, _ = PreviewRenderer.parse_and_filter_capture(
            capture_path=req.capture_path,
            selected_entry_ids=req.selected_entry_ids,
            rom_offsets=req.rom_offsets,
            frame_id=req.frame_id,
            capture_repository=capture_repository,
        )

        if capture_result is None:
            return None

        # Render preview using shared renderer
        return PreviewRenderer.render_preview_qimage(capture_result)


class AsyncGameFramePreviewService(AsyncServiceBase):
    """Service for async batch game frame preview generation.

    Generates previews for multiple game frames in a background thread,
    emitting results incrementally for responsive UI updates.

    Signals:
        preview_ready: (frame_id, pixmap) - emitted for each completed preview
    """

    preview_ready = Signal(str, QPixmap)
    """Emitted when a game frame preview is ready for display.

    Part of batch async preview generation. Emitted incrementally for each
    completed preview.

    Args:
        frame_id: ID of the game frame
        pixmap: QPixmap of the rendered preview (safe for main thread use)

    Emitted by:
        - _on_preview_ready() → after converting worker's QImage to QPixmap

    Triggers:
        - FrameMappingController.game_frame_preview_ready
        - WorkbenchCanvas → updates frame display
        - CapturesLibraryPane → updates thumbnail
    """

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        capture_repository: CaptureResultRepository,
    ) -> None:
        super().__init__(parent)
        self._capture_repository = capture_repository
        self._current_request_id = 0

    @override
    def _get_final_wait_timeout(self) -> int:
        """Use 1000ms final wait instead of default 3000ms."""
        return 1000

    @override
    def _cleanup_current_work(self) -> None:
        """Cancel in-progress batch."""
        worker = cast(_GameFramePreviewWorker | None, getattr(self, "_worker", None))
        if worker is not None:
            worker.set_target_request_id(self._current_request_id + 1)

    @override
    def _disconnect_worker_signals(self) -> None:
        """Disconnect worker-specific signals."""
        worker = cast(_GameFramePreviewWorker | None, getattr(self, "_worker", None))
        if worker is not None:
            try:
                worker.preview_ready.disconnect()
                worker.batch_finished.disconnect()
            except (RuntimeError, TypeError):
                pass

    def request_previews(
        self,
        frame_ids: list[str],
        project: FrameMappingProject,
    ) -> None:
        """Request async preview generation for specified frames.

        Args:
            frame_ids: List of game frame IDs to generate previews for
            project: Current project (for game frame lookup)
        """
        # Increment request ID to cancel in-flight work
        self._current_request_id += 1
        request_id = self._current_request_id

        # Cancel any existing work
        self.cancel()

        if not frame_ids:
            return

        # Build requests from frame IDs
        requests: list[GameFramePreviewRequest] = []
        for frame_id in frame_ids:
            game_frame = project.get_game_frame_by_id(frame_id)
            if game_frame is None or game_frame.capture_path is None:
                continue

            requests.append(
                GameFramePreviewRequest(
                    frame_id=frame_id,
                    capture_path=game_frame.capture_path,
                    selected_entry_ids=list(game_frame.selected_entry_ids),
                    rom_offsets=list(game_frame.rom_offsets),
                )
            )

        if not requests:
            return
        # Create worker and thread
        self._worker = _GameFramePreviewWorker()
        # Initialize target request ID BEFORE moving to thread (fixes race condition)
        self._worker.init_target_request_id(request_id)
        self._thread = QThread()
        self._thread.setObjectName(f"AsyncGameFramePreviewService-{request_id}")
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._thread.started.connect(
            lambda: self._worker.process_batch(  # type: ignore[union-attr]
                BatchPreviewRequest(
                    request_id=request_id,
                    requests=requests,
                    capture_repository=self._capture_repository,
                )
            )
        )
        self._worker.preview_ready.connect(self._on_preview_ready)
        self._worker.batch_finished.connect(self._on_batch_finished)

        # Start processing via WorkerManager for lifecycle tracking
        WorkerManager.start_worker(self._thread)

    @Slot(int, str, QImage)
    def _on_preview_ready(self, request_id: int, frame_id: str, qimage: QImage) -> None:
        """Handle preview completion from worker."""
        if self._destroyed:
            return
        if request_id != self._current_request_id:
            return

        # Convert to QPixmap on main thread
        pixmap = QPixmap.fromImage(qimage)
        if not pixmap.isNull():
            self.preview_ready.emit(frame_id, pixmap)

    @Slot(int)
    def _on_batch_finished(self, request_id: int) -> None:
        """Handle batch completion from worker."""
        if self._destroyed:
            return
        if request_id != self._current_request_id:
            return

        self._cleanup_thread()

    def cancel(self) -> None:
        """Cancel any in-progress batch."""
        self._cleanup_current_work()
        self._cleanup_thread()
