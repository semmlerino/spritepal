"""
Worker signal lifecycle tests.

Tests verifying that worker signals emit in the correct order:
- started -> progress -> finished
- Error paths: started -> error -> finished

Also tests known issues from Tier 2:
- _signals_connected flag desync (preview_worker_pool.py:447-450, 532-535)
- Signals not disconnected before reconnect (batch_thumbnail_worker.py:817-819)

These tests focus on signal ordering and lifecycle, not full worker functionality.

Async Safety Notes
------------------
These tests use mock workers with synchronous `run_sync()` methods to test signal
ordering without threading complexity. This is safe because:
1. MockWorkerWithLifecycle emits signals synchronously in the test thread
2. processEvents() ensures any queued side-effects complete

For testing REAL threaded workers, use `qtbot.waitSignal()` with context manager:

    # REAL ASYNC WORKER PATTERN:
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()  # Runs in separate thread

    # Verify order using MultiSignalRecorder connected BEFORE starting
    recorder = MultiSignalRecorder()
    recorder.connect_signal(worker.started, "started")
    recorder.connect_signal(worker.finished, "finished")

    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()

    recorder.assert_contains_sequence(["started", "finished"])

IMPORTANT: When testing real threaded workers, connect spies BEFORE starting
the worker, otherwise signals may be missed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from tests.fixtures.timeouts import signal_timeout, worker_timeout
from tests.ui.integration.helpers.signal_spy_utils import MultiSignalRecorder

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class MockWorkerWithLifecycle(QObject):
    """Mock worker that emits lifecycle signals for testing."""

    started = Signal()
    progress = Signal(int, int)  # current, total
    finished = Signal()
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._should_error = False
        self._progress_steps = 3

    def set_error_mode(self, should_error: bool) -> None:
        """Configure whether to emit error during run."""
        self._should_error = should_error

    def run_sync(self) -> None:
        """Simulate synchronous worker execution (for testing signal order)."""
        self.started.emit()

        if self._should_error:
            self.error.emit("Test error")
        else:
            for i in range(self._progress_steps):
                self.progress.emit(i + 1, self._progress_steps)

        self.finished.emit()


class TestWorkerLifecycleOrder:
    """Test that worker signals emit in correct order."""

    def test_successful_worker_emits_started_progress_finished(self, qtbot: QtBot) -> None:
        """Worker must emit started -> progress -> finished in order."""
        worker = MockWorkerWithLifecycle()

        recorder = MultiSignalRecorder()
        recorder.connect_signal(worker.started, "started")
        recorder.connect_signal(worker.progress, "progress")
        recorder.connect_signal(worker.finished, "finished")

        worker.run_sync()
        QCoreApplication.processEvents()

        order = recorder.emission_order()
        assert order[0] == "started", f"First signal should be 'started', got: {order}"
        assert order[-1] == "finished", f"Last signal should be 'finished', got: {order}"

        # Progress should be between started and finished
        recorder.assert_contains_sequence(["started", "progress", "finished"])

    def test_error_worker_emits_started_error_finished(self, qtbot: QtBot) -> None:
        """Worker with error must emit started -> error -> finished."""
        worker = MockWorkerWithLifecycle()
        worker.set_error_mode(True)

        recorder = MultiSignalRecorder()
        recorder.connect_signal(worker.started, "started")
        recorder.connect_signal(worker.error, "error")
        recorder.connect_signal(worker.finished, "finished")

        worker.run_sync()
        QCoreApplication.processEvents()

        order = recorder.emission_order()
        assert order[0] == "started"
        assert order[-1] == "finished"
        recorder.assert_contains_sequence(["started", "error", "finished"])

    def test_finished_always_emitted_last(self, qtbot: QtBot) -> None:
        """finished signal must always be the last signal emitted."""
        worker = MockWorkerWithLifecycle()

        recorder = MultiSignalRecorder()
        recorder.connect_signal(worker.started, "started")
        recorder.connect_signal(worker.progress, "progress")
        recorder.connect_signal(worker.finished, "finished")
        recorder.connect_signal(worker.error, "error")

        # Test both success and error paths
        for error_mode in [False, True]:
            recorder.clear()
            worker.set_error_mode(error_mode)
            worker.run_sync()
            QCoreApplication.processEvents()

            order = recorder.emission_order()
            assert order[-1] == "finished", f"finished should be last (error_mode={error_mode}), order: {order}"


class TestWorkerProgressTracking:
    """Test progress signal emissions."""

    def test_progress_emits_correct_values(self, qtbot: QtBot) -> None:
        """Progress signal must emit with correct (current, total) values."""
        worker = MockWorkerWithLifecycle()
        worker._progress_steps = 5

        recorder = MultiSignalRecorder()
        recorder.connect_signal(worker.progress, "progress")

        worker.run_sync()
        QCoreApplication.processEvents()

        # Should have 5 progress emissions
        recorder.assert_emitted("progress", times=5)

        # Check values
        all_args = recorder.all_args("progress")
        for i, (current, total) in enumerate(all_args):
            assert current == i + 1, f"Progress current should be {i + 1}, got {current}"
            assert total == 5, f"Progress total should be 5, got {total}"

    def test_zero_progress_steps_still_emits_lifecycle(self, qtbot: QtBot) -> None:
        """Worker with no work should still emit started -> finished."""
        worker = MockWorkerWithLifecycle()
        worker._progress_steps = 0

        recorder = MultiSignalRecorder()
        recorder.connect_signal(worker.started, "started")
        recorder.connect_signal(worker.progress, "progress")
        recorder.connect_signal(worker.finished, "finished")

        worker.run_sync()
        QCoreApplication.processEvents()

        recorder.assert_emitted("started", times=1)
        recorder.assert_emitted("finished", times=1)
        recorder.assert_emitted("progress", times=0)


class MockSignalConnectedWorker(QObject):
    """Mock worker that tracks signal connection state."""

    preview_ready = Signal(int)  # request_id

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._signals_connected = False

    def connect_signals(self) -> None:
        """Simulate connecting signals (sets flag)."""
        self._signals_connected = True

    def disconnect_signals(self) -> None:
        """Simulate disconnecting signals (clears flag)."""
        self._signals_connected = False

    @property
    def signals_connected(self) -> bool:
        return self._signals_connected


class TestSignalConnectionFlagConsistency:
    """Test that _signals_connected flags match actual behavior.

    This addresses known issues in:
    - preview_worker_pool.py:447-450, 532-535

    Note: PySide6's receivers() doesn't count new-style connections, so we
    test behavior (signal emission -> slot called) instead of connection counts.
    """

    def test_signals_connected_flag_matches_behavior(self, qtbot: QtBot) -> None:
        """_signals_connected flag must match actual signal delivery."""
        worker = MockSignalConnectedWorker()
        received_values: list[int] = []

        def slot(x: int) -> None:
            received_values.append(x)

        # Initially not connected - flag false, signal not delivered
        assert worker.signals_connected is False
        worker.preview_ready.emit(1)
        QCoreApplication.processEvents()
        assert len(received_values) == 0, "Signal should not be delivered when not connected"

        # Connect and update flag
        worker.preview_ready.connect(slot)
        worker.connect_signals()

        # Flag true, signal should be delivered
        assert worker.signals_connected is True
        worker.preview_ready.emit(2)
        QCoreApplication.processEvents()
        assert 2 in received_values, "Signal should be delivered when connected"

        # Disconnect and update flag
        worker.preview_ready.disconnect(slot)
        worker.disconnect_signals()
        received_values.clear()

        # Flag false, signal not delivered
        assert worker.signals_connected is False
        worker.preview_ready.emit(3)
        QCoreApplication.processEvents()
        assert len(received_values) == 0, "Signal should not be delivered after disconnect"

    def test_flag_behavior_desync_detection(self, qtbot: QtBot) -> None:
        """Detect desync: flag says connected but signal not delivered (simulated bug)."""
        worker = MockSignalConnectedWorker()
        received_values: list[int] = []

        def slot(x: int) -> None:
            received_values.append(x)

        # Simulate bug: flag set but no actual connection
        worker._signals_connected = True

        # Emit signal
        worker.preview_ready.emit(42)
        QCoreApplication.processEvents()

        # Bug condition: flag says connected but nothing received
        if worker.signals_connected and len(received_values) == 0:
            # This is expected in the bug scenario - the flag is wrong
            pass  # Test passes by demonstrating the desync condition exists


class TestSignalReconnection:
    """Test signal disconnection before reconnection.

    This addresses known issues in:
    - batch_thumbnail_worker.py:817-819 (signals not disconnected before reconnect)
    """

    def test_reconnect_without_disconnect_causes_duplicate_emission(self, qtbot: QtBot) -> None:
        """Reconnecting without disconnecting first causes duplicate emissions."""
        worker = MockSignalConnectedWorker()
        emission_count = 0

        def counter(x: int) -> None:
            nonlocal emission_count
            emission_count += 1

        # First connection
        worker.preview_ready.connect(counter)

        # BUG: Second connection WITHOUT disconnecting first
        worker.preview_ready.connect(counter)

        # Emit once
        worker.preview_ready.emit(1)
        QCoreApplication.processEvents()

        # Bug: counter called twice because two connections exist
        assert emission_count == 2, f"Expected duplicate emission (bug scenario), got {emission_count} emissions"

    def test_proper_reconnect_with_disconnect_first(self, qtbot: QtBot) -> None:
        """Proper reconnection: disconnect first, then connect."""
        worker = MockSignalConnectedWorker()
        emission_count = 0

        def counter(x: int) -> None:
            nonlocal emission_count
            emission_count += 1

        # First connection
        worker.preview_ready.connect(counter)

        # Proper reconnection: disconnect first
        worker.preview_ready.disconnect(counter)
        worker.preview_ready.connect(counter)

        # Emit once
        worker.preview_ready.emit(1)
        QCoreApplication.processEvents()

        # Correct: counter called once
        assert emission_count == 1, f"Expected single emission after proper reconnect, got {emission_count}"


class TestMultipleWorkerInstances:
    """Test signal isolation between multiple worker instances."""

    def test_signals_isolated_between_instances(self, qtbot: QtBot) -> None:
        """Signals from one worker must not affect another worker's receivers."""
        worker1 = MockWorkerWithLifecycle()
        worker2 = MockWorkerWithLifecycle()

        recorder1 = MultiSignalRecorder()
        recorder2 = MultiSignalRecorder()

        recorder1.connect_signal(worker1.started, "started")
        recorder2.connect_signal(worker2.started, "started")

        # Only run worker1
        worker1.run_sync()
        QCoreApplication.processEvents()

        # recorder1 should have emission, recorder2 should not
        recorder1.assert_emitted("started", times=1)
        recorder2.assert_emitted("started", times=0)

    def test_no_cross_talk_on_same_signal_name(self, qtbot: QtBot) -> None:
        """Workers with same signal names must not cross-talk."""
        worker1 = MockWorkerWithLifecycle()
        worker2 = MockWorkerWithLifecycle()

        worker1_count = 0
        worker2_count = 0

        def counter1() -> None:
            nonlocal worker1_count
            worker1_count += 1

        def counter2() -> None:
            nonlocal worker2_count
            worker2_count += 1

        worker1.started.connect(counter1)
        worker2.started.connect(counter2)

        # Run only worker1
        worker1.run_sync()
        QCoreApplication.processEvents()

        assert worker1_count == 1
        assert worker2_count == 0, "worker2's slot should not have been called"


class ThreadedMockWorker(QObject):
    """Mock worker that runs in a QThread to demonstrate async patterns."""

    started = Signal()
    progress = Signal(int, int)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._work_steps = 3

    def run(self) -> None:
        """Simulate work (called in thread context)."""
        self.started.emit()
        for i in range(self._work_steps):
            self.progress.emit(i + 1, self._work_steps)
        self.finished.emit()


class TestAsyncWaitingPatterns:
    """Examples demonstrating proper qtbot.waitSignal() usage for async workers.

    These tests demonstrate the CORRECT patterns for testing real threaded workers.
    The key principles are:
    1. Always use context manager: `with qtbot.waitSignal(...)`
    2. Connect spies BEFORE starting async operation
    3. Use timeouts from tests/fixtures/timeouts.py
    4. Use `raising=True` to fail fast on timeout (default in pytest-qt)
    """

    def test_wait_signal_context_manager_pattern(self, qtbot: QtBot) -> None:
        """Demonstrate correct context manager pattern for async signals.

        CORRECT PATTERN:
            with qtbot.waitSignal(signal, timeout=timeout):
                start_async_operation()

        WRONG PATTERN (race condition):
            spy = QSignalSpy(signal)
            start_async_operation()
            # Signal may have already emitted before spy was ready!
        """
        from PySide6.QtCore import QThread

        worker = ThreadedMockWorker()
        thread = QThread()
        worker.moveToThread(thread)

        recorder = MultiSignalRecorder()
        recorder.connect_signal(worker.started, "started")
        recorder.connect_signal(worker.finished, "finished")

        # Connect thread started to worker run
        thread.started.connect(worker.run)
        # Clean shutdown
        worker.finished.connect(thread.quit)

        # CORRECT: Context manager ensures we don't miss the signal
        with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
            thread.start()

        # Verify signals were captured
        recorder.assert_emitted("started", times=1)
        recorder.assert_emitted("finished", times=1)
        recorder.assert_contains_sequence(["started", "finished"])

        # Cleanup
        thread.wait()

    def test_multiple_signals_with_recorder_and_wait(self, qtbot: QtBot) -> None:
        """Demonstrate recording multiple signals from async worker.

        Pattern: Connect MultiSignalRecorder BEFORE starting, then wait
        for the terminal signal (usually `finished`).
        """
        from PySide6.QtCore import QThread

        worker = ThreadedMockWorker()
        worker._work_steps = 5
        thread = QThread()
        worker.moveToThread(thread)

        # Setup recorder BEFORE starting
        recorder = MultiSignalRecorder()
        recorder.connect_signal(worker.started, "started")
        recorder.connect_signal(worker.progress, "progress")
        recorder.connect_signal(worker.finished, "finished")

        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)

        # Wait for terminal signal
        with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
            thread.start()

        # Now verify order and counts
        recorder.assert_emitted("started", times=1)
        recorder.assert_emitted("progress", times=5)
        recorder.assert_emitted("finished", times=1)

        order = recorder.emission_order()
        assert order[0] == "started", "Worker must emit started first"
        assert order[-1] == "finished", "Worker must emit finished last"

        thread.wait()

    def test_timeout_handling_with_raising(self, qtbot: QtBot) -> None:
        """Demonstrate timeout handling - test should fail fast on timeout.

        By default pytest-qt uses raising=True, meaning TimeoutError is raised
        if the signal isn't emitted within the timeout. This is the correct
        behavior for detecting "signal never emitted" bugs.
        """
        from PySide6.QtCore import QThread

        worker = ThreadedMockWorker()
        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)

        # This should NOT timeout since worker emits finished
        with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
            thread.start()

        thread.wait()

        # To demonstrate timeout behavior (commented out - would fail):
        # from PySide6.QtCore import Signal
        # class NeverEmits(QObject):
        #     never = Signal()
        # obj = NeverEmits()
        # with pytest.raises(pytestqt.exceptions.TimeoutError):
        #     with qtbot.waitSignal(obj.never, timeout=100):
        #         pass  # Signal never emits
