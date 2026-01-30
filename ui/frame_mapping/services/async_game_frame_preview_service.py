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
from typing import TYPE_CHECKING

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import MesenCaptureParser
from core.repositories.capture_result_repository import CaptureResultRepository
from core.services.image_utils import pil_to_qimage
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
    capture_repository: CaptureResultRepository | None


class _GameFramePreviewWorker(QObject):
    """Worker that generates game frame previews in a background thread."""

    # Signal: (request_id, frame_id, qimage)
    preview_ready = Signal(int, str, QImage)
    # Signal: (request_id) - emitted when batch is complete
    batch_finished = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._state_mutex = QMutex()
        self._target_request_id = 0
        self._stop_requested = False
        self._parser = MesenCaptureParser()

    def set_target_request_id(self, req_id: int) -> None:
        """Update target request ID and request stop of current work."""
        with QMutexLocker(self._state_mutex):
            self._target_request_id = req_id
            self._stop_requested = True

    def _should_cancel(self, request_id: int) -> bool:
        """Check if this request should be cancelled."""
        with QMutexLocker(self._state_mutex):
            return request_id != self._target_request_id

    def _clear_stop_flag(self) -> None:
        """Clear stop flag at start of valid request processing."""
        with QMutexLocker(self._state_mutex):
            self._stop_requested = False

    @Slot(BatchPreviewRequest)
    def process_batch(self, batch: BatchPreviewRequest) -> None:
        """Process batch of preview requests."""
        request_id = batch.request_id

        # Fast rejection if already stale
        if self._should_cancel(request_id):
            return

        self._clear_stop_flag()

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
        capture_repository: CaptureResultRepository | None,
    ) -> QImage | None:
        """Generate preview for a single game frame."""
        if not req.capture_path.exists():
            return None

        try:
            # Parse capture file (use shared repository if available)
            if capture_repository is not None:
                capture_result = capture_repository.get_or_parse(req.capture_path)
            else:
                capture_result = self._parser.parse_file(req.capture_path)

            if not capture_result.has_entries:
                return None

            # Apply entry filtering
            from core.mesen_integration.entry_filtering import (
                create_filtered_capture,
                filter_capture_entries,
            )

            filtering = filter_capture_entries(
                capture_result,
                selected_entry_ids=req.selected_entry_ids,
                rom_offsets=req.rom_offsets,
                allow_all_entries_fallback=False,
                context_label=req.frame_id,
            )

            if filtering.has_entries:
                capture_result = create_filtered_capture(capture_result, filtering.entries)

            # Render preview
            renderer = CaptureRenderer(capture_result)
            preview_img = renderer.render_selection()

            # Convert to QImage (thread-safe)
            return pil_to_qimage(preview_img, with_alpha=True)

        except Exception as e:
            logger.warning("Error generating preview for %s: %s", req.frame_id, e)
            return None


class AsyncGameFramePreviewService(QObject):
    """Service for async batch game frame preview generation.

    Generates previews for multiple game frames in a background thread,
    emitting results incrementally for responsive UI updates.

    Signals:
        preview_ready: (frame_id, pixmap) - emitted for each completed preview
        batch_finished: () - emitted when batch is complete
    """

    preview_ready = Signal(str, QPixmap)  # frame_id, pixmap
    batch_finished = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        capture_repository: CaptureResultRepository | None = None,
    ) -> None:
        super().__init__(parent)
        self._capture_repository = capture_repository
        self._current_request_id = 0
        self._worker: _GameFramePreviewWorker | None = None
        self._thread: QThread | None = None
        self._destroyed = False

        if parent is not None:
            parent.destroyed.connect(self._on_parent_destroyed)

    @Slot()
    def _on_parent_destroyed(self) -> None:
        """Handle parent destruction."""
        self._destroyed = True
        # Use getattr to handle case where __init__ hasn't completed
        if getattr(self, "_worker", None) is not None or getattr(self, "_thread", None) is not None:
            self.cancel()

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
            self.batch_finished.emit()
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
            self.batch_finished.emit()
            return

        # Create worker and thread
        self._worker = _GameFramePreviewWorker()
        self._thread = QThread()
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

        # Start processing
        self._thread.start()

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
        self.batch_finished.emit()

    def cancel(self) -> None:
        """Cancel any in-progress batch."""
        if self._worker is not None:
            self._worker.set_target_request_id(self._current_request_id + 1)
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        """Clean up thread resources without blocking UI."""
        worker = self._worker
        thread = self._thread

        if worker is not None:
            worker.blockSignals(True)
            try:
                worker.preview_ready.disconnect()
                worker.batch_finished.disconnect()
            except (RuntimeError, TypeError):
                pass

        if thread is not None:
            if thread.isRunning():
                thread.quit()
                if not thread.wait(100):
                    # Schedule delayed cleanup
                    from PySide6.QtCore import QTimer

                    QTimer.singleShot(500, lambda: self._finish_cleanup(thread, worker))
                    self._thread = None
                    self._worker = None
                    return

        self._do_cleanup(thread, worker)

    def _finish_cleanup(self, thread: QThread, worker: QObject | None) -> None:
        """Complete cleanup after delayed wait."""
        if thread.isRunning():
            thread.terminate()
            thread.wait(100)
        self._do_cleanup(thread, worker)

    def _do_cleanup(self, thread: QThread | None, worker: QObject | None) -> None:
        """Perform actual cleanup."""
        if thread is not None and not self._destroyed:
            thread.deleteLater()
        if worker is not None and not self._destroyed:
            worker.deleteLater()
        self._thread = None
        self._worker = None
