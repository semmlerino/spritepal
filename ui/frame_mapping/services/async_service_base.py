"""Base class for async services with thread management.

Provides common thread cleanup logic with graceful shutdown and orphaned
thread handling to prevent Qt corruption.
"""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import QObject, QThread, QTimer, Slot

from utils.logging_config import get_logger

logger = get_logger(__name__)


class AsyncServiceBase(QObject):
    """Base class for async services with thread management.

    Provides common thread cleanup logic with graceful shutdown
    and orphaned thread handling to prevent Qt corruption.

    Subclasses must:
    - Call super().__init__(parent) in their __init__
    - Implement _disconnect_worker_signals() to disconnect service-specific signals
    - Optionally implement _cleanup_current_work() to cancel pending work
    - Set _worker and _thread when creating workers

    Attributes:
        _destroyed: Flag indicating parent has been destroyed
        _thread: Current worker thread (or None)
        _worker: Current worker object (or None)
    """

    # Class-level sets to prevent GC of threads that didn't stop in time
    _orphaned_threads: ClassVar[set[QThread]] = set()
    _pending_cleanup_threads: ClassVar[set[QThread]] = set()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._destroyed = False
        self._thread: QThread | None = None
        self._worker: QObject | None = None

        if parent is not None:
            parent.destroyed.connect(self._on_parent_destroyed)

    @Slot()
    def _on_parent_destroyed(self) -> None:
        """Handle parent destruction. Override for service-specific cleanup."""
        self._destroyed = True
        self._cleanup_current_work()
        self._cleanup_thread()

    def _cleanup_current_work(self) -> None:
        """Hook for subclass to cancel pending work. Called before thread cleanup.

        Override this to:
        - Clear pending queues
        - Cancel in-progress requests
        - Signal workers to stop

        Default implementation does nothing.
        """
        pass

    def _disconnect_worker_signals(self) -> None:
        """Hook for subclass to disconnect worker-specific signals.

        Override this to disconnect signals specific to your worker.
        Called before thread cleanup to prevent signal emission during teardown.

        Example:
            if self._worker is not None:
                try:
                    self._worker.result_ready.disconnect()
                    self._worker.progress.disconnect()
                except (RuntimeError, TypeError):
                    pass
        """
        pass

    def _get_final_wait_timeout(self) -> int:
        """Get timeout for final cleanup wait in milliseconds.

        Override to customize. Default is 3000ms (3 seconds).
        """
        return 3000

    def _cleanup_thread(self) -> None:
        """Clean up thread resources without blocking UI.

        Uses a short initial wait (100ms) followed by deferred cleanup
        to avoid blocking the UI thread. Thread lifecycle:
        1. Initial quit + 100ms wait
        2. If still running: schedule retry after 500ms
        3. Retry quit + final wait (default 3000ms)
        4. If still running: orphan thread to prevent Qt corruption
        """
        worker = getattr(self, "_worker", None)
        thread = getattr(self, "_thread", None)

        if worker is not None:
            worker.blockSignals(True)
            self._disconnect_worker_signals()

        if thread is not None:
            if thread.isRunning():
                thread.quit()
                if not thread.wait(100):
                    AsyncServiceBase._pending_cleanup_threads.add(thread)
                    QTimer.singleShot(500, lambda: self._finish_cleanup(thread, worker))
                    self._thread = None
                    self._worker = None
                    return
            elif not thread.isFinished():
                # Thread not fully started yet - defer cleanup to avoid premature deletion
                AsyncServiceBase._pending_cleanup_threads.add(thread)
                QTimer.singleShot(200, lambda: self._finish_cleanup(thread, worker))
                self._thread = None
                self._worker = None
                return

        self._do_cleanup(thread, worker)

    def _finish_cleanup(self, thread: QThread, worker: QObject | None) -> None:
        """Complete cleanup after delayed wait."""
        AsyncServiceBase._pending_cleanup_threads.discard(thread)
        if thread.isRunning():
            logger.warning(f"Thread {thread.__class__.__name__} still running after initial wait")
            thread.quit()
            if not thread.wait(self._get_final_wait_timeout()):
                # Keep reference in class-level set to prevent GC while running
                AsyncServiceBase._pending_cleanup_threads.discard(thread)
                AsyncServiceBase._orphaned_threads.add(thread)
                logger.critical(
                    f"Thread {thread.__class__.__name__} won't stop - keeping alive to avoid Qt corruption "
                    f"(orphaned count: {len(AsyncServiceBase._orphaned_threads)})"
                )
                thread.finished.connect(lambda t=thread: AsyncServiceBase._orphaned_threads.discard(t))
                return
        elif not thread.isFinished():
            # Thread hasn't finished yet (startup race) - retry shortly
            AsyncServiceBase._pending_cleanup_threads.add(thread)
            QTimer.singleShot(200, lambda: self._finish_cleanup(thread, worker))
            return
        self._do_cleanup(thread, worker)

    def _do_cleanup(self, thread: QThread | None, worker: QObject | None) -> None:
        """Perform actual cleanup."""
        destroyed = getattr(self, "_destroyed", False)
        if thread is not None and not destroyed:
            thread.deleteLater()
        if worker is not None and not destroyed:
            worker.deleteLater()
        self._thread = None
        self._worker = None
