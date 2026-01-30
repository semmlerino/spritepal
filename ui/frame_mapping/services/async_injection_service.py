"""Async injection service for frame mapping.

Offloads ROM injection to a background thread to avoid blocking the UI.
Uses a serial queue to ensure only one injection runs at a time (ROM safety).

Key design:
- Worker runs InjectionOrchestrator.execute() in background thread
- Serial queue ensures safe ROM access (one at a time)
- Progress signals emitted for UI feedback
- Request ID pattern cancels stale operations
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, QTimer, Signal, Slot

from core.services.injection_debug_context import InjectionDebugContext
from core.services.injection_orchestrator import InjectionOrchestrator
from core.services.injection_results import InjectionRequest, InjectionResult
from core.services.injection_snapshot import InjectionSnapshot
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

logger = get_logger(__name__)


@dataclass
class AsyncInjectionRequest:
    """Request for async injection.

    Contains immutable snapshot of project data captured at queue time.
    The worker uses the snapshot instead of the mutable project to avoid
    race conditions when the user modifies settings during injection.
    """

    request_id: int
    ai_frame_id: str
    injection_request: InjectionRequest
    snapshot: InjectionSnapshot
    debug: bool = False


class _InjectionWorker(QObject):
    """Worker that performs injection in a background thread."""

    # Signal: (request_id, ai_frame_id, result)
    injection_finished = Signal(int, str, object)  # result is InjectionResult
    # Signal: (request_id, ai_frame_id, message)
    progress = Signal(int, str, str)

    def __init__(self) -> None:
        super().__init__()
        self._state_mutex = QMutex()
        self._stop_requested = False
        self._orchestrator = InjectionOrchestrator()

    def request_stop(self) -> None:
        """Request stop of current work."""
        with QMutexLocker(self._state_mutex):
            self._stop_requested = True

    def _is_stop_requested(self) -> bool:
        """Check if stop was requested."""
        with QMutexLocker(self._state_mutex):
            return self._stop_requested

    def _clear_stop_flag(self) -> None:
        """Clear stop flag at start of processing."""
        with QMutexLocker(self._state_mutex):
            self._stop_requested = False

    @Slot(AsyncInjectionRequest)
    def process_request(self, request: AsyncInjectionRequest) -> None:
        """Process injection request."""
        self._clear_stop_flag()

        if self._is_stop_requested():
            return

        request_id = request.request_id
        ai_frame_id = request.ai_frame_id

        # Progress callback
        def emit_progress(msg: str) -> None:
            if not self._is_stop_requested():
                self.progress.emit(request_id, ai_frame_id, msg)

        try:
            # Execute injection using snapshot (thread-safe, no mutable project access)
            with InjectionDebugContext.from_env() as debug_ctx:
                if request.debug and not debug_ctx.enabled:
                    debug_ctx = InjectionDebugContext(enabled=True)
                    debug_ctx.__enter__()
                    try:
                        result = self._orchestrator.execute_from_snapshot(
                            request=request.injection_request,
                            snapshot=request.snapshot,
                            debug_context=debug_ctx,
                            on_progress=emit_progress,
                        )
                    finally:
                        debug_ctx.__exit__(None, None, None)
                else:
                    result = self._orchestrator.execute_from_snapshot(
                        request=request.injection_request,
                        snapshot=request.snapshot,
                        debug_context=debug_ctx,
                        on_progress=emit_progress,
                    )

            if not self._is_stop_requested():
                self.injection_finished.emit(request_id, ai_frame_id, result)

        except Exception as e:
            logger.exception("Injection worker error for %s: %s", ai_frame_id, e)
            # Emit a failure result
            result = InjectionResult(
                success=False,
                messages=(),
                error=str(e),
            )
            if not self._is_stop_requested():
                self.injection_finished.emit(request_id, ai_frame_id, result)


class AsyncInjectionService(QObject):
    """Service for async injection operations.

    Runs injections in a background thread with a serial queue to ensure
    safe ROM access.

    Signals:
        injection_started: (ai_frame_id) - emitted when injection begins
        injection_progress: (ai_frame_id, message) - emitted for progress updates
        injection_finished: (ai_frame_id, success, message) - emitted when complete
    """

    injection_started = Signal(str)  # ai_frame_id
    injection_progress = Signal(str, str)  # ai_frame_id, message
    injection_finished = Signal(str, bool, str, object)  # ai_frame_id, success, message, result

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_request_id = 0
        self._worker: _InjectionWorker | None = None
        self._thread: QThread | None = None
        self._destroyed = False
        self._pending_queue: list[AsyncInjectionRequest] = []
        self._is_processing = False

        if parent is not None:
            parent.destroyed.connect(self._on_parent_destroyed)

    @Slot()
    def _on_parent_destroyed(self) -> None:
        """Handle parent destruction."""
        self._destroyed = True
        # Use getattr to handle case where __init__ hasn't completed
        if getattr(self, "_pending_queue", None) is not None:
            self.cancel_all()

    def queue_injection(
        self,
        ai_frame_id: str,
        injection_request: InjectionRequest,
        project: FrameMappingProject,
        debug: bool = False,
    ) -> None:
        """Queue an injection for background processing.

        Injections are processed serially (one at a time) for ROM safety.
        Project state is snapshotted at queue time to avoid race conditions
        when the user modifies settings during injection.

        Args:
            ai_frame_id: ID of the AI frame to inject
            injection_request: The injection request parameters
            project: Current project (used to create immutable snapshot)
            debug: Enable debug mode
        """
        # Create immutable snapshot of project state NOW (on UI thread)
        # This prevents race conditions if user modifies alignment/palette during injection
        snapshot = InjectionSnapshot.from_project(project, ai_frame_id)
        if snapshot is None:
            logger.warning(
                "Cannot create injection snapshot for %s - missing mapping/frame",
                ai_frame_id,
            )
            # Emit failure immediately (signal expects: ai_frame_id, success, message, result)
            result = InjectionResult(
                success=False,
                messages=(),
                error=f"Missing mapping or frame data for {ai_frame_id}",
            )
            self.injection_finished.emit(
                ai_frame_id, False, result.error or "Snapshot creation failed", result
            )
            return

        self._current_request_id += 1

        request = AsyncInjectionRequest(
            request_id=self._current_request_id,
            ai_frame_id=ai_frame_id,
            injection_request=injection_request,
            snapshot=snapshot,
            debug=debug,
        )

        self._pending_queue.append(request)
        self.injection_started.emit(ai_frame_id)

        # Start processing if not already running
        if not self._is_processing:
            self._process_next()

    def _process_next(self) -> None:
        """Process the next queued injection."""
        if self._destroyed or not self._pending_queue:
            self._is_processing = False
            return

        self._is_processing = True
        request = self._pending_queue.pop(0)

        # Create worker and thread
        self._worker = _InjectionWorker()
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._thread.started.connect(
            lambda: self._worker.process_request(request)  # type: ignore[union-attr]
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.injection_finished.connect(self._on_injection_finished)

        # Start processing
        self._thread.start()

    @Slot(int, str, str)
    def _on_progress(self, request_id: int, ai_frame_id: str, message: str) -> None:
        """Handle progress from worker."""
        if self._destroyed:
            return
        self.injection_progress.emit(ai_frame_id, message)

    @Slot(int, str, object)
    def _on_injection_finished(self, request_id: int, ai_frame_id: str, result: object) -> None:
        """Handle injection completion from worker."""
        if self._destroyed:
            return

        # Clean up current worker
        self._cleanup_thread()

        # Emit result
        if isinstance(result, InjectionResult):
            message = "\n".join(result.messages) if result.messages else ""
            if not result.success and result.error:
                message = result.error
            self.injection_finished.emit(ai_frame_id, result.success, message, result)
        else:
            self.injection_finished.emit(ai_frame_id, False, "Unknown error", None)

        # Process next in queue
        if self._pending_queue:
            # Use timer to avoid deep recursion
            QTimer.singleShot(0, self._process_next)
        else:
            self._is_processing = False

    def cancel_all(self) -> None:
        """Cancel all pending and current injections."""
        self._pending_queue.clear()
        if self._worker is not None:
            self._worker.request_stop()
        self._cleanup_thread()
        self._is_processing = False

    def _cleanup_thread(self) -> None:
        """Clean up thread resources without blocking UI."""
        worker = self._worker
        thread = self._thread

        if worker is not None:
            worker.blockSignals(True)
            try:
                worker.progress.disconnect()
                worker.injection_finished.disconnect()
            except (RuntimeError, TypeError):
                pass

        if thread is not None:
            if thread.isRunning():
                thread.quit()
                if not thread.wait(100):
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

    @property
    def is_busy(self) -> bool:
        """Check if an injection is currently in progress."""
        return self._is_processing

    @property
    def pending_count(self) -> int:
        """Get the number of pending injections in queue."""
        return len(self._pending_queue)
