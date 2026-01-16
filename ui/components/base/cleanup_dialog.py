"""
Base dialog class with automatic worker cleanup.

This class extends DialogBase to provide automatic cleanup of worker threads
when the dialog is closed, preventing resource leaks and test pollution.

IMPORTANT: Subclasses should use register_worker() for all workers to ensure
proper cleanup on dialog close.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import QThread

from ui.components.base.dialog_base import DialogBase
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QWidget

    from core.workers.base import BaseWorker

logger = get_logger(__name__)

# Default timeout for waiting on worker threads (5 seconds)
DEFAULT_WORKER_TIMEOUT_MS = 5000


class CleanupDialog(DialogBase):
    """
    Base class for dialogs that manage worker threads.

    Provides automatic cleanup of registered workers when the dialog closes,
    with configurable timeouts to prevent hangs.

    Usage:
        class MyDialog(CleanupDialog):
            def __init__(self, parent: QWidget | None = None) -> None:
                # Declare instance variables BEFORE super()
                self._my_worker: MyWorker | None = None
                self._my_thread: QThread | None = None

                super().__init__(parent, title="My Dialog")

            def _setup_ui(self) -> None:
                # Create worker and thread
                self._my_worker = MyWorker()
                self._my_thread = QThread()

                # Register for automatic cleanup
                self.register_worker(self._my_worker, self._my_thread)

                # Move to thread and start
                self._my_worker.moveToThread(self._my_thread)
                self._my_thread.start()
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        worker_timeout_ms: int = DEFAULT_WORKER_TIMEOUT_MS,
        **kwargs: object,
    ) -> None:
        """
        Initialize the cleanup dialog.

        Args:
            parent: Parent widget (optional)
            worker_timeout_ms: Timeout in ms for waiting on worker cleanup (default: 5000)
            **kwargs: Additional arguments passed to DialogBase
        """
        # Track registered workers and threads
        self._registered_workers: list[tuple[BaseWorker, QThread | None]] = []
        self._worker_timeout_ms = worker_timeout_ms

        # Call parent init
        super().__init__(parent, **kwargs)  # pyright: ignore[reportArgumentType] - kwargs compatibility

    def register_worker(
        self,
        worker: BaseWorker,
        thread: QThread | None = None,
    ) -> None:
        """
        Register a worker for automatic cleanup on dialog close.

        Args:
            worker: The worker to register
            thread: Optional thread the worker runs on (for proper shutdown)
        """
        self._registered_workers.append((worker, thread))
        logger.debug(f"Registered worker {worker.__class__.__name__} for cleanup")

    def unregister_worker(self, worker: BaseWorker) -> bool:
        """
        Unregister a worker from automatic cleanup.

        Args:
            worker: The worker to unregister

        Returns:
            True if worker was found and unregistered, False otherwise
        """
        for i, (w, _) in enumerate(self._registered_workers):
            if w is worker:
                self._registered_workers.pop(i)
                logger.debug(f"Unregistered worker {worker.__class__.__name__}")
                return True
        return False

    def _cleanup_workers(self) -> None:
        """
        Clean up all registered workers with timeout protection.

        This method cancels all workers and waits for their threads to finish,
        with a configurable timeout to prevent hangs.
        """
        if not self._registered_workers:
            return

        logger.debug(f"Cleaning up {len(self._registered_workers)} registered workers")

        for worker, thread in self._registered_workers:
            worker_name = worker.__class__.__name__

            try:
                # Cancel the worker first
                worker.cancel()
                logger.debug(f"Cancelled worker {worker_name}")

                # If there's a thread, wait for it to finish
                if thread is not None and thread.isRunning():
                    thread.quit()

                    # Wait with timeout
                    if not thread.wait(self._worker_timeout_ms):
                        logger.warning(
                            f"Worker {worker_name} thread did not stop within "
                            f"{self._worker_timeout_ms}ms timeout - "
                            "thread will be orphaned to avoid dangerous terminate()"
                        )
                        # Note: We intentionally do NOT call thread.terminate() as it can
                        # cause crashes and undefined behavior. The thread will be orphaned
                        # and cleaned up when the process exits.
                    else:
                        logger.debug(f"Worker {worker_name} thread stopped cleanly")

            except RuntimeError as e:
                # Worker or thread may have been deleted
                logger.debug(f"Error cleaning up {worker_name}: {e}")
            except Exception as e:
                # Log but don't re-raise - we want to clean up other workers
                logger.warning(f"Unexpected error cleaning up {worker_name}: {e}")

        # Clear the list
        self._registered_workers.clear()
        logger.debug("Worker cleanup complete")

    @override
    def closeEvent(self, event: QCloseEvent | None) -> None:
        """
        Handle dialog close event with automatic worker cleanup.

        Args:
            event: The close event
        """
        # Clean up workers before closing
        self._cleanup_workers()

        # Call parent closeEvent
        if event:
            super().closeEvent(event)
