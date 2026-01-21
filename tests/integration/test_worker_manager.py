"""
Real component tests for WorkerManager utility class.

This refactored version demonstrates:
- Testing with real QThread workers
- Proper signal/slot testing
- Real timing behavior validation
- No mocking of Qt components
"""

import time
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QThread, Signal
from PySide6.QtTest import QSignalSpy

from tests.fixtures.timeouts import SHORT, signal_timeout
from ui.common import WorkerManager
from ui.common.timing_constants import (
    # Test characteristics: Real GUI components requiring display, Thread safety concerns
    SLEEP_MEDIUM,
    TEST_TIMEOUT_MEDIUM,
    WORKER_TIMEOUT_LONG,
    WORKER_TIMEOUT_SHORT,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.gui,
    pytest.mark.slow,
    pytest.mark.headless,
]


class RealTestWorker(QThread):
    """Real test worker that performs actual work."""

    # Signals following SpritePal conventions
    progress = Signal(int, str)
    finished_work = Signal()
    error = Signal(str, Exception)

    def __init__(self):
        super().__init__()
        self.should_run = True
        self.work_done = False
        self._work_cycles = 0
        self._interrupted = False

    @property
    def is_interrupted(self) -> bool:
        """Check if worker was interrupted during execution."""
        return self._interrupted

    def run(self):
        """Perform real work with interruption checking."""
        try:
            # Simulate work with interruption checking (as per CLAUDE.md)
            for i in range(5):
                if self.isInterruptionRequested() or not self.should_run:
                    self._interrupted = True
                    return

                # Do some work
                self.msleep(int(SLEEP_MEDIUM * 200))  # 10ms chunks
                self._work_cycles += 1

                # Emit progress
                progress_percent = (i + 1) * 20
                self.progress.emit(progress_percent, f"Processing step {i + 1}")

            # Work completed successfully
            self.work_done = True
            self.finished_work.emit()

        except Exception as e:
            self.error.emit(str(e), e)

    def stop(self):
        """Stop the worker gracefully."""
        self.should_run = False
        self.requestInterruption()
        self.quit()


class SlowStoppingWorker(QThread):
    """Worker that takes time to stop, for testing timeouts."""

    finished_work = Signal()

    def __init__(self, stop_delay_ms=100):
        super().__init__()
        self._should_stop = False
        self._stop_delay_ms = stop_delay_ms
        self._stop_requested_time = None

    def run(self):
        """Run until told to stop, with delay."""
        while not self._should_stop:
            if self.isInterruptionRequested():
                # Simulate slow cleanup
                self.msleep(self._stop_delay_ms)
                self._should_stop = True
                break
            self.msleep(10)

        self.finished_work.emit()

    def quit(self):
        """Override quit to add delay."""
        self._stop_requested_time = time.time()
        self.requestInterruption()
        super().quit()


class TestWorkerManagerReal:
    """Test WorkerManager with real Qt workers."""

    @pytest.fixture
    def real_worker(self):
        """Create a real test worker."""
        worker = RealTestWorker()
        yield worker
        # Ensure cleanup
        if worker.isRunning():
            worker.stop()
            worker.wait(1000)

    def test_cleanup_none_worker_real(self):
        """Test cleanup handles None worker gracefully."""
        # Should not raise any exception - test passes if no exception raised
        WorkerManager.cleanup_worker(None)

    def test_cleanup_stopped_worker_real(self):
        """Test cleanup of already stopped real worker."""
        worker = RealTestWorker()
        # Worker is not running, cleanup should handle gracefully
        WorkerManager.cleanup_worker(worker)
        assert not worker.isRunning()

    def test_cleanup_running_worker_real(self, qtbot):
        """Test cleanup of running real worker with graceful shutdown."""
        worker = RealTestWorker()

        # Start real worker
        worker.start()
        qtbot.waitUntil(worker.isRunning, timeout=TEST_TIMEOUT_MEDIUM)
        assert worker.isRunning()

        # Track work cycles before cleanup

        # Clean up should stop it gracefully
        WorkerManager.cleanup_worker(worker, timeout=WORKER_TIMEOUT_SHORT)

        # Worker should be stopped
        assert not worker.isRunning()
        # Worker should have been interrupted
        assert worker.is_interrupted or not worker.should_run

    def test_cleanup_with_timeout_real(self, qtbot):
        """Test cleanup respects timeout with real slow worker."""
        # Create worker that takes 100ms to stop
        worker = SlowStoppingWorker(stop_delay_ms=100)

        # Start worker
        worker.start()
        qtbot.waitUntil(worker.isRunning, timeout=TEST_TIMEOUT_MEDIUM)

        # Cleanup with sufficient timeout should succeed
        WorkerManager.cleanup_worker(worker, timeout=500)

        # Worker should eventually stop
        assert not worker.isRunning()

    def test_start_worker_real(self, qtbot):
        """Test starting a real worker."""
        worker = RealTestWorker()

        # Set up signal spy
        progress_spy = QSignalSpy(worker.progress)

        # Start worker
        WorkerManager.start_worker(worker)

        # Worker should be running
        qtbot.waitUntil(worker.isRunning, timeout=TEST_TIMEOUT_MEDIUM)
        assert worker.isRunning()

        # Wait for some progress
        qtbot.waitUntil(lambda: progress_spy.count() > 0, timeout=signal_timeout())

        # Verify progress signals were emitted
        assert progress_spy.count() > 0
        first_progress = progress_spy.at(0)
        assert isinstance(first_progress[0], int)  # percent
        assert isinstance(first_progress[1], str)  # message

        # Cleanup
        worker.stop()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=TEST_TIMEOUT_MEDIUM)

    def test_start_with_cleanup_real(self, qtbot):
        """Test starting a worker with cleanup of existing real worker."""
        old_worker = RealTestWorker()
        old_worker.start()
        qtbot.waitUntil(old_worker.isRunning, timeout=signal_timeout())

        new_worker = RealTestWorker()

        # Start new worker, should cleanup old one
        WorkerManager.start_worker(new_worker, cleanup_existing=old_worker)

        # Old worker should be stopped
        qtbot.waitUntil(lambda: not old_worker.isRunning(), timeout=WORKER_TIMEOUT_LONG)
        assert not old_worker.isRunning()

        # New worker should be running
        assert new_worker.isRunning()

        # Cleanup
        new_worker.stop()
        qtbot.waitUntil(lambda: not new_worker.isRunning(), timeout=signal_timeout())

    def test_worker_interruption_handling_real(self, qtbot):
        """Test that workers properly handle interruption requests."""
        worker = RealTestWorker()

        # Start worker
        worker.start()
        qtbot.waitUntil(worker.isRunning, timeout=TEST_TIMEOUT_MEDIUM)

        # Request interruption
        worker.requestInterruption()

        # Worker should detect interruption and stop
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=signal_timeout())

        # Verify worker detected interruption
        assert worker._interrupted
        assert not worker.work_done  # Should not complete work

    def test_worker_error_handling_real(self, qtbot):
        """Test real error signal emission."""

        class ErrorWorker(QThread):
            error = Signal(str, Exception)

            def run(self):
                try:
                    raise ValueError("Test error")
                except Exception as e:
                    self.error.emit(str(e), e)

        worker = ErrorWorker()
        error_spy = QSignalSpy(worker.error)

        # Start worker
        worker.start()

        # Wait for error signal
        qtbot.waitUntil(lambda: error_spy.count() > 0, timeout=signal_timeout())

        # Verify error was emitted
        assert error_spy.count() == 1
        error_msg, error_exc = error_spy.at(0)
        assert "Test error" in error_msg
        assert isinstance(error_exc, ValueError)

        # Cleanup
        worker.quit()
        worker.wait(1000)

    def test_multiple_worker_management_real(self, qtbot):
        """Test managing multiple real workers."""
        workers = [RealTestWorker() for _ in range(3)]

        # Start all workers
        for worker in workers:
            WorkerManager.start_worker(worker)

        # All should be running
        for worker in workers:
            assert worker.isRunning()

        # Clean up all workers
        for worker in workers:
            WorkerManager.cleanup_worker(worker, timeout=WORKER_TIMEOUT_SHORT)

        # All should be stopped
        for worker in workers:
            assert not worker.isRunning()

    def test_worker_completion_real(self, qtbot):
        """Test worker natural completion without interruption."""

        class QuickWorker(QThread):
            finished_work = Signal()

            def run(self):
                self.msleep(50)  # Quick work
                self.finished_work.emit()

        worker = QuickWorker()
        finished_spy = QSignalSpy(worker.finished_work)

        # Start worker
        worker.start()

        # Wait for natural completion
        qtbot.waitUntil(lambda: finished_spy.count() > 0, timeout=signal_timeout())

        # Worker should complete and stop naturally
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=signal_timeout())

        assert finished_spy.count() == 1
        assert not worker.isRunning()

    def test_worker_priority_handling_real(self, qtbot):
        """Test worker thread priority management."""
        import sys

        worker = RealTestWorker()

        # Start worker first - Qt6 requires thread to be running before setPriority
        worker.start()
        qtbot.waitUntil(worker.isRunning, timeout=TEST_TIMEOUT_MEDIUM)

        # Set high priority (only works on running thread in Qt6)
        worker.setPriority(QThread.Priority.HighPriority)

        # Verify priority is set (give Qt a moment to apply it)
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        # Note: Linux often ignores thread priority for non-root processes,
        # so we accept either HighPriority (if supported) or InheritPriority (fallback)
        if sys.platform == "linux":
            # On Linux, priority may not be settable - accept the call didn't crash
            assert worker.priority() in (
                QThread.Priority.HighPriority,
                QThread.Priority.InheritPriority,
            )
        else:
            assert worker.priority() == QThread.Priority.HighPriority

        # Cleanup
        worker.stop()
        worker.wait(1000)

    def test_worker_state_consistency_real(self, qtbot):
        """Test worker state remains consistent through lifecycle."""
        worker = RealTestWorker()

        # Initial state
        assert not worker.isRunning()
        assert not worker.work_done
        assert worker._work_cycles == 0

        # Start and let it run briefly
        worker.start()
        qtbot.waitUntil(worker.isRunning, timeout=TEST_TIMEOUT_MEDIUM)
        qtbot.waitUntil(
            lambda: worker._work_cycles > 0, timeout=signal_timeout(SHORT)
        )  # Wait for worker to do some work

        # Interrupt
        worker.stop()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=signal_timeout())

        # State should be consistent
        assert not worker.isRunning()
        assert worker._work_cycles >= 0  # Some work may have been done
        assert worker._interrupted or not worker.should_run


@pytest.mark.usefixtures("isolated_managers")
@pytest.mark.skip_thread_cleanup(reason="Uses isolated_managers which owns worker threads")
class TestWorkerCancellationStability:
    """Test WorkerManager safe cancellation mechanisms.

    Migrated from test_phase1_stability_fixes.py - validates Phase 1 stability fixes
    for worker cancellation patterns.

    Note: Static analysis tests (test_no_terminate_calls_in_codebase,
    test_worker_manager_safe_patterns) have been moved to scripts/lint_safety.py.
    """

    def test_worker_manager_timeout_handling(self):
        """Test WorkerManager timeout handling logic."""
        from unittest.mock import call

        # Test the static methods directly without requiring Qt

        # Create a mock worker that simulates different behaviors
        mock_worker = Mock()
        mock_worker.__class__.__name__ = "TestWorker"
        mock_worker.isRunning.return_value = True
        mock_worker.wait.return_value = True  # Simulates successful shutdown
        mock_worker.isFinished.return_value = True  # Worker has finished
        mock_worker.deleteLater.return_value = None

        # Test cleanup with responsive worker
        WorkerManager.cleanup_worker(mock_worker, timeout=1000)

        # Verify expected calls were made
        mock_worker.requestInterruption.assert_called_once()
        mock_worker.quit.assert_called_once()
        # Implementation calls wait(timeout) for shutdown, then wait(50) for extra cleanup
        # when isFinished() returns True (two-stage wait for complete thread cleanup)
        assert mock_worker.wait.call_count == 2
        mock_worker.wait.assert_has_calls([call(1000), call(50)])
        mock_worker.deleteLater.assert_called_once()

    def test_worker_manager_unresponsive_handling(self):
        """Test WorkerManager handles unresponsive workers without terminate."""

        # Create mock unresponsive worker
        mock_worker = Mock()
        mock_worker.__class__.__name__ = "UnresponsiveWorker"
        mock_worker.isRunning.return_value = True
        mock_worker.wait.return_value = False  # Simulates timeout
        mock_worker.deleteLater.return_value = None

        # Test cleanup with unresponsive worker
        WorkerManager.cleanup_worker(mock_worker, timeout=100)

        # Verify safe handling - no terminate() should be called
        assert not hasattr(mock_worker, "terminate") or not mock_worker.terminate.called
        mock_worker.deleteLater.assert_called_once()
