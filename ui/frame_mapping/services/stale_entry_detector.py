"""Async stale entry detection service for frame mapping projects.

This service moves the expensive stale entry detection off the UI thread,
preventing UI freezes when loading projects with many game frames.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from core.mesen_integration.click_extractor import MesenCaptureParser
from core.repositories.capture_result_repository import CaptureResultRepository
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

    # Signal: (stale_frame_ids, request_id)
    detection_complete = Signal(list, int)

    def __init__(self, request: StaleDetectionRequest) -> None:
        super().__init__()
        self._request = request
        self._stop_requested = False
        # Fallback parser when no repository provided
        self._parser = MesenCaptureParser() if request.capture_repository is None else None

    def request_stop(self) -> None:
        """Request the worker to stop processing."""
        self._stop_requested = True

    def run(self) -> None:
        """Run stale detection for all game frames."""
        stale_ids: list[str] = []

        for game_frame in self._request.game_frames:
            if self._stop_requested:
                break

            # Skip frames without selected_entry_ids (ROM-only workflow)
            if not game_frame.selected_entry_ids:
                continue

            # Skip frames without capture path
            if not game_frame.capture_path:
                continue

            # Check if capture file exists
            if not game_frame.capture_path.exists():
                logger.warning(
                    "Capture file not found for frame '%s': %s",
                    game_frame.id,
                    game_frame.capture_path,
                )
                stale_ids.append(game_frame.id)
                continue

            # Load the capture file and check if entry IDs are still valid
            try:
                # Use shared repository if available, otherwise parse directly
                if self._request.capture_repository is not None:
                    capture_result = self._request.capture_repository.get_or_parse(game_frame.capture_path)
                else:
                    assert self._parser is not None
                    capture_result = self._parser.parse_file(game_frame.capture_path)

                # Get the IDs of all entries in the current capture
                current_entry_ids = {entry.id for entry in capture_result.entries}

                # Check if all selected_entry_ids are present
                selected_ids_set = set(game_frame.selected_entry_ids)
                is_stale = not selected_ids_set.issubset(current_entry_ids)

                if is_stale:
                    stale_ids.append(game_frame.id)
                    logger.debug(
                        "Game frame '%s' has stale entries: %s not in current capture IDs %s",
                        game_frame.id,
                        selected_ids_set - current_entry_ids,
                        current_entry_ids,
                    )

            except Exception as e:
                logger.warning(
                    "Failed to parse capture file for frame '%s': %s",
                    game_frame.id,
                    e,
                )
                stale_ids.append(game_frame.id)

        if not self._stop_requested:
            self.detection_complete.emit(stale_ids, self._request.request_id)


class AsyncStaleEntryDetector(QObject):
    """Async service for detecting stale entries in game frames.

    Runs detection in a background thread to avoid UI freezes during project load.

    Signals:
        stale_entries_detected: Emitted with list of stale frame IDs when detection completes.
        detection_finished: Emitted when detection completes (even if no stale entries).
    """

    # Signal: list of stale frame IDs
    stale_entries_detected = Signal(list)

    # Signal: emitted when detection completes
    detection_finished = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        capture_repository: CaptureResultRepository | None = None,
    ) -> None:
        super().__init__(parent)
        self._worker: _StaleEntryWorker | None = None
        self._thread: QThread | None = None
        self._destroyed = False
        self._current_request_id = 0
        self._capture_repository = capture_repository

        if parent is not None:
            parent.destroyed.connect(self._on_parent_destroyed)

    @Slot()
    def _on_parent_destroyed(self) -> None:
        """Handle parent destruction - cancel any running work."""
        self._destroyed = True
        self.cancel()

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
            self.stale_entries_detected.emit([])
            self.detection_finished.emit()
            return

        # Create worker and thread
        request = StaleDetectionRequest(
            game_frames=frames_to_check,
            request_id=self._current_request_id,
            capture_repository=self._capture_repository,
        )
        self._worker = _StaleEntryWorker(request)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._thread.started.connect(self._worker.run)
        self._worker.detection_complete.connect(self._on_detection_complete)

        # Start detection
        self._thread.start()

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
        self.detection_finished.emit()

    def cancel(self) -> None:
        """Cancel any in-progress detection."""
        worker = getattr(self, "_worker", None)
        if worker:
            worker.request_stop()
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        """Clean up thread resources without blocking UI.

        Uses a short initial wait (100ms) followed by a deferred cleanup
        to avoid blocking the UI thread for up to 5 seconds.
        """
        worker = getattr(self, "_worker", None)
        thread = getattr(self, "_thread", None)
        destroyed = getattr(self, "_destroyed", True)

        # Block signals first to prevent emission during cleanup
        if worker is not None:
            worker.blockSignals(True)
            try:
                worker.detection_complete.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected or never connected

        if thread is not None:
            if thread.isRunning():
                thread.quit()
                if not thread.wait(100):  # Short initial wait
                    # Schedule delayed cleanup instead of blocking UI
                    QTimer.singleShot(500, lambda: self._finish_cleanup(thread, worker, destroyed))
                    self._thread = None
                    self._worker = None
                    return

        self._do_cleanup(thread, worker, destroyed)

    def _finish_cleanup(self, thread: QThread, worker: QObject | None, destroyed: bool) -> None:
        """Complete cleanup after delayed wait."""
        if thread.isRunning():
            thread.terminate()
            thread.wait(100)
        self._do_cleanup(thread, worker, destroyed)

    def _do_cleanup(self, thread: QThread | None, worker: QObject | None, destroyed: bool) -> None:
        """Perform actual cleanup of thread and worker objects."""
        if thread is not None:
            if not destroyed:
                thread.deleteLater()
        if worker is not None:
            if not destroyed:
                worker.deleteLater()
        self._thread = None
        self._worker = None
