"""Async stale entry detection service for frame mapping projects.

This service moves the expensive stale entry detection off the UI thread,
preventing UI freezes when loading projects with many game frames.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, QThread, Signal, Slot

if TYPE_CHECKING:
    from typing import override
else:

    def override(f):
        return f


from core.mesen_integration.click_extractor import CaptureResult
from core.repositories.capture_result_repository import CaptureResultRepository
from core.services.stale_entry_logic import detect_stale_frame_ids
from ui.common import WorkerManager
from ui.frame_mapping.services.async_service_base import AsyncServiceBase
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import GameFrame

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StaleDetectionRequest:
    """Request for stale entry detection.

    Attributes:
        game_frames: List of game frames to check.
        request_id: Unique ID for this request batch.
        capture_repository: Shared repository for caching parsed capture files.
    """

    game_frames: list[GameFrame]
    request_id: int
    capture_repository: CaptureResultRepository | None


class _StaleEntryWorker(QObject):
    """Background worker that performs stale entry detection.

    Runs in a separate thread to avoid blocking the UI.
    """

    detection_complete = Signal(list, int)
    """Emitted when stale entry detection completes.

    Internal signal used to communicate from worker thread to service.
    The service relays this as the public stale_entries_detected signal.

    Args:
        stale_frame_ids: List of game frame IDs that have stale OAM entry references
        request_id: Internal request ID for tracking (used to cancel stale batches)

    Emitted by:
        - run() → after detection completes

    Triggers:
        - AsyncStaleEntryDetector._on_detection_complete()
    """

    def __init__(self, request: StaleDetectionRequest) -> None:
        super().__init__()
        self._request = request
        self._stop_requested = False

    def request_stop(self) -> None:
        """Request the worker to stop processing."""
        self._stop_requested = True

    def run(self) -> None:
        """Run stale detection for all game frames."""

        def get_capture(path: Path) -> CaptureResult:
            """Get capture result from repository."""
            assert self._request.capture_repository is not None
            return self._request.capture_repository.get_or_parse(path)

        stale_ids = detect_stale_frame_ids(
            self._request.game_frames,
            get_capture,
            stop_check=lambda: self._stop_requested,
        )

        if not self._stop_requested:
            self.detection_complete.emit(stale_ids, self._request.request_id)


class AsyncStaleEntryDetector(AsyncServiceBase):
    """Async service for detecting stale entries in game frames.

    Runs detection in a background thread to avoid UI freezes during project load.

    Signals:
        stale_entries_detected: Emitted with list of stale frame IDs when detection completes.
    """

    stale_entries_detected = Signal(list)
    """Emitted when stale OAM entry IDs are detected in game frames.

    Signals completion of stale entry detection with a list of affected frame IDs.
    Only emitted if stale entries are found (not emitted for clean batches).

    Args:
        stale_frame_ids: List of game frame IDs with stale OAM entry references

    Emitted by:
        - _on_detection_complete() → when stale_ids is non-empty

    Triggers:
        - FrameMappingController.stale_entries_on_load
        - Workspace → shows batch warning dialog
    """

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        capture_repository: CaptureResultRepository | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_request_id = 0
        self._capture_repository = capture_repository

    @override
    def _get_final_wait_timeout(self) -> int:
        """Use 1000ms final wait instead of default 3000ms."""
        return 1000

    @override
    def _cleanup_current_work(self) -> None:
        """Request worker to stop processing."""
        worker = cast(_StaleEntryWorker | None, getattr(self, "_worker", None))
        if worker:
            worker.request_stop()

    @override
    def _disconnect_worker_signals(self) -> None:
        """Disconnect worker-specific signals."""
        worker = cast(_StaleEntryWorker | None, getattr(self, "_worker", None))
        if worker is not None:
            try:
                worker.detection_complete.disconnect()
            except (RuntimeError, TypeError):
                pass

    def detect_stale_entries(self, game_frames: list[GameFrame]) -> None:
        """Start async stale entry detection.

        Args:
            game_frames: List of game frames to check for stale entries.
        """
        # Increment request ID to invalidate any in-progress work
        self._current_request_id += 1

        # Cancel any existing work
        self.cancel()

        # Filter to only frames that need checking (have selected_entry_ids and capture_path)
        frames_to_check = [gf for gf in game_frames if gf.selected_entry_ids and gf.capture_path is not None]

        if not frames_to_check:
            return

        # Create worker and thread
        request = StaleDetectionRequest(
            game_frames=frames_to_check,
            request_id=self._current_request_id,
            capture_repository=self._capture_repository,
        )
        self._worker = _StaleEntryWorker(request)
        self._thread = QThread()
        self._thread.setObjectName(f"AsyncStaleEntryDetector-{self._current_request_id}")
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._thread.started.connect(self._worker.run)
        self._worker.detection_complete.connect(self._on_detection_complete)

        # Start detection via WorkerManager for lifecycle tracking
        WorkerManager.start_worker(self._thread)

    @Slot(list, int)
    def _on_detection_complete(self, stale_ids: list[str], request_id: int) -> None:
        """Handle detection completion from worker.

        Args:
            stale_ids: List of frame IDs with stale entries.
            request_id: The request batch ID (stale if != _current_request_id).
        """
        if self._destroyed:
            return
        # Filter stale results from cancelled batches
        if request_id != self._current_request_id:
            return

        self._cleanup_thread()

        if stale_ids:
            self.stale_entries_detected.emit(stale_ids)

    def cancel(self) -> None:
        """Cancel any in-progress detection."""
        self._cleanup_current_work()
        self._cleanup_thread()
