"""
Worker thread adapter for testing QObject-based workers.

Provides a clean way to run any QObject worker in a QThread for integration tests,
with proper lifecycle management, signal forwarding, and cleanup.

Usage:
    worker = MyWorker(params)
    adapter = WorkerThreadAdapter(worker)

    # Optional: Access forwarded signals
    adapter.signals.finished.connect(my_handler)

    with qtbot.waitSignal(adapter.signals.finished, timeout=5000):
        adapter.start()

    # Cleanup is automatic in __del__, or call explicitly
    adapter.cleanup()

For tests with pytest-qt:
    def test_my_worker(qtbot):
        worker = MyWorker()
        adapter = WorkerThreadAdapter(worker)

        with qtbot.waitSignal(worker.finished, timeout=5000):
            adapter.start()

        assert worker.result is not None
        adapter.cleanup()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal

if TYPE_CHECKING:
    from collections.abc import Callable


class SignalProxy(QObject):
    """Proxy for forwarding worker signals.

    This allows accessing common signals through a unified interface
    without knowing the specific worker type.
    """

    # Common worker signals - connect to worker's signals as needed
    finished = Signal()
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)


class WorkerThreadAdapter:
    """
    Adapter to run any QObject-based worker in a QThread for testing.

    This reduces boilerplate in integration tests that need to run workers
    in their own threads with proper lifecycle management.

    The adapter:
    - Creates a QThread and moves the worker to it
    - Connects thread.started → worker.run (if worker has run method)
    - Connects worker.finished → thread.quit (if worker has finished signal)
    - Provides start(), stop(), wait(), isRunning() methods
    - Handles cleanup with proper thread termination

    Attributes:
        worker: The wrapped worker object
        thread: The QThread running the worker
        signals: SignalProxy for common signals (optional usage)
    """

    def __init__(
        self,
        worker: QObject,
        *,
        run_method: str = "run",
        finished_signal: str = "finished",
        stop_method: str | None = "stop",
    ) -> None:
        """
        Initialize the adapter with a worker.

        Args:
            worker: QObject-based worker to wrap
            run_method: Name of the method to call when thread starts (default: "run")
            finished_signal: Name of the signal emitted when work is done (default: "finished")
            stop_method: Name of the method to call to stop the worker (default: "stop", None to skip)
        """
        self.worker = worker
        self.thread = QThread()
        self.signals = SignalProxy()
        self._stop_method = stop_method
        self._cleaned_up = False

        # Move worker to thread
        self.worker.moveToThread(self.thread)

        # Connect thread started → worker run
        if hasattr(self.worker, run_method):
            run_callable: Callable[[], None] = getattr(self.worker, run_method)
            self.thread.started.connect(run_callable)

        # Connect worker finished → thread quit
        if hasattr(self.worker, finished_signal):
            finished_sig = getattr(self.worker, finished_signal)
            finished_sig.connect(self.thread.quit)
            # Also forward to our signal proxy
            finished_sig.connect(self.signals.finished.emit)

        # Forward common signals if they exist
        if hasattr(self.worker, "error"):
            self.worker.error.connect(self.signals.error.emit)
        if hasattr(self.worker, "progress"):
            self.worker.progress.connect(self.signals.progress.emit)

    def start(self) -> None:
        """Start the worker thread."""
        self.thread.start()

    def stop(self) -> None:
        """Request the worker to stop."""
        if self._stop_method and hasattr(self.worker, self._stop_method):
            stop_callable: Callable[[], None] = getattr(self.worker, self._stop_method)
            stop_callable()

    def wait(self, timeout_ms: int = 5000) -> bool:
        """
        Wait for the thread to finish.

        Args:
            timeout_ms: Maximum time to wait in milliseconds

        Returns:
            True if thread finished, False if timeout occurred
        """
        return self.thread.wait(timeout_ms)

    def is_running(self) -> bool:
        """Check if the thread is currently running."""
        return self.thread.isRunning()

    # Alias for Qt-style naming
    isRunning = is_running

    def cleanup(self, timeout_ms: int = 3000) -> None:
        """
        Clean up the worker and thread.

        This method:
        1. Requests the worker to stop (if stop_method is set)
        2. Waits for the thread to finish
        3. Terminates the thread if it doesn't stop gracefully
        4. Calls worker.cleanup() if it exists

        Args:
            timeout_ms: Maximum time to wait for graceful shutdown
        """
        if self._cleaned_up:
            return

        self._cleaned_up = True

        # Stop the thread first and wait for it to finish
        if self.thread.isRunning():
            self.stop()
            if not self.thread.wait(timeout_ms):
                # Thread didn't stop gracefully, force terminate
                self.thread.terminate()
                self.thread.wait(1000)

        # Now safe to clean up worker resources
        if hasattr(self.worker, "cleanup"):
            cleanup_callable: Callable[[], None] = self.worker.cleanup
            cleanup_callable()

    def __del__(self) -> None:
        """Ensure cleanup on destruction."""
        self.cleanup()


def run_worker_to_completion(
    worker: QObject,
    timeout_ms: int = 5000,
    *,
    run_method: str = "run",
    finished_signal: str = "finished",
) -> bool:
    """
    Convenience function to run a worker to completion and return.

    This is useful for simple tests that just need to run a worker
    and wait for it to finish.

    Args:
        worker: QObject-based worker to run
        timeout_ms: Maximum time to wait for completion
        run_method: Name of the run method (default: "run")
        finished_signal: Name of the finished signal (default: "finished")

    Returns:
        True if worker finished within timeout, False otherwise
    """
    adapter = WorkerThreadAdapter(
        worker,
        run_method=run_method,
        finished_signal=finished_signal,
    )

    try:
        adapter.start()
        return adapter.wait(timeout_ms)
    finally:
        adapter.cleanup()
