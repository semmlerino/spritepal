"""
Advanced Qt threading and signal/slot integration tests.

This module focuses on the thread-safety aspects of signal/slot connections,
testing complex scenarios involving:
- Cross-thread signal delivery
- QueuedConnection vs DirectConnection behavior
- Signal parameter marshalling across threads
- Thread affinity and object ownership
- Deadlock prevention patterns
"""
from __future__ import annotations

import os
import time
from typing import Any

import pytest

# Skip entire module in offscreen mode - QThread + waitSignal causes segfaults
_offscreen_mode = os.environ.get('QT_QPA_PLATFORM') == 'offscreen'
pytestmark = pytest.mark.skipif(
    _offscreen_mode,
    reason="QThread + waitSignal/wait causes segfaults in offscreen mode"
)
from PySide6.QtCore import (
    QEventLoop,
    QMutex,
    QMutexLocker,
    QObject,
    Qt,
    QThread,
    QTimer,
    QWaitCondition,
    Signal,
    Slot,
)
from PySide6.QtWidgets import QApplication

from utils.logging_config import get_logger

logger = get_logger(__name__)

class ThreadSafeCounter(QObject):
    """Thread-safe counter using Qt's synchronization primitives."""

    value_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self._value = 0
        self._mutex = QMutex()

    @Slot()
    def increment(self):
        """Thread-safe increment."""
        with QMutexLocker(self._mutex):
            self._value += 1
            new_value = self._value
        # Emit outside lock to prevent deadlock
        self.value_changed.emit(new_value)

    @Slot(result=int)
    def get_value(self) -> int:
        """Thread-safe read."""
        with QMutexLocker(self._mutex):
            return self._value

class WorkerWithSignals(QObject):
    """Worker that emits signals from worker thread."""

    started = Signal()
    progress = Signal(int)
    result_ready = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.is_cancelled = False
        self._mutex = QMutex()

    @Slot()
    def process(self):
        """Main processing method - runs in worker thread."""
        try:
            self.started.emit()

            for i in range(10):
                # Check cancellation
                with QMutexLocker(self._mutex):
                    if self.is_cancelled:
                        break

                # Simulate work
                QThread.msleep(10)

                # Emit progress
                self.progress.emit((i + 1) * 10)

            # Emit result
            if not self.is_cancelled:
                self.result_ready.emit("Processing complete")

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    @Slot()
    def cancel(self):
        """Cancel processing - thread-safe."""
        with QMutexLocker(self._mutex):
            self.is_cancelled = True

class SignalCollector(QObject):
    """Collects signals with thread information."""

    def __init__(self):
        super().__init__()
        self.signals: list[tuple] = []
        self._mutex = QMutex()
        self.main_thread = QThread.currentThread()

    @Slot()
    def collect_simple(self):
        """Collect simple signal."""
        self._collect("simple", None)

    @Slot(int)
    def collect_int(self, value: int):
        """Collect int parameter."""
        self._collect("int", value)

    @Slot(str)
    def collect_str(self, value: str):
        """Collect string parameter."""
        self._collect("str", value)

    @Slot(int, str)
    def collect_multi(self, num: int, text: str):
        """Collect multiple parameters."""
        self._collect("multi", (num, text))

    def _collect(self, signal_type: str, value: Any):
        """Thread-safe signal collection."""
        thread = QThread.currentThread()
        is_main = (thread == self.main_thread)
        timestamp = time.time()

        with QMutexLocker(self._mutex):
            self.signals.append((signal_type, value, is_main, timestamp))

    def get_signals(self) -> list[tuple]:
        """Get collected signals thread-safely."""
        with QMutexLocker(self._mutex):
            return self.signals.copy()

    def clear(self):
        """Clear collected signals."""
        with QMutexLocker(self._mutex):
            self.signals.clear()

@pytest.mark.gui
class TestCrossThreadSignals:
    """Test cross-thread signal delivery."""

    def test_queued_connection_cross_thread(self, qtbot):
        """Test QueuedConnection delivers signals across threads correctly."""
        collector = SignalCollector()
        worker = WorkerWithSignals()
        thread = QThread()

        # Move worker to thread
        worker.moveToThread(thread)

        # Connect with QueuedConnection (automatic for cross-thread)
        worker.progress.connect(collector.collect_int)
        worker.result_ready.connect(collector.collect_str)

        # Start processing
        thread.started.connect(worker.process)

        with qtbot.waitSignal(worker.finished, timeout=5000):
            thread.start()

        # Clean up thread
        thread.quit()
        thread.wait()

        # Verify signals were collected
        signals = collector.get_signals()

        # Should have progress signals and result
        progress_signals = [s for s in signals if s[0] == "int"]
        result_signals = [s for s in signals if s[0] == "str"]

        assert len(progress_signals) > 0
        assert len(result_signals) == 1

        # All should be received in main thread (QueuedConnection)
        for sig in signals:
            assert sig[2] == True  # is_main_thread

    def test_direct_connection_same_thread(self, qtbot):
        """Test DirectConnection executes slot immediately in same thread."""
        collector = SignalCollector()
        worker = WorkerWithSignals()
        thread = QThread()

        # Move both to same worker thread
        worker.moveToThread(thread)
        collector.moveToThread(thread)

        # Connect with DirectConnection
        worker.progress.connect(
            collector.collect_int,
            Qt.ConnectionType.DirectConnection
        )

        # Start processing
        thread.started.connect(worker.process)

        with qtbot.waitSignal(worker.finished, timeout=5000):
            thread.start()

        thread.quit()
        thread.wait()

        # Verify signals were collected in worker thread
        signals = collector.get_signals()
        progress_signals = [s for s in signals if s[0] == "int"]

        # All should be received in worker thread (DirectConnection)
        for sig in progress_signals:
            assert sig[2] == False  # not main_thread

    def test_blocking_queued_connection(self, qtbot):
        """Test BlockingQueuedConnection blocks until slot completes."""

        class SlowReceiver(QObject):
            processing_started = Signal()
            processing_finished = Signal()

            @Slot(int)
            def slow_process(self, value: int):
                """Slow processing slot."""
                self.processing_started.emit()
                QThread.msleep(100)  # Simulate slow processing
                self.processing_finished.emit()

        receiver = SlowReceiver()
        worker = WorkerWithSignals()
        thread = QThread()

        worker.moveToThread(thread)

        # Connect with BlockingQueuedConnection
        worker.progress.connect(
            receiver.slow_process,
            Qt.ConnectionType.BlockingQueuedConnection
        )

        # Measure blocking time
        start_time = None
        end_time = None

        def on_started():
            nonlocal start_time
            start_time = time.time()

        def on_finished():
            nonlocal end_time
            end_time = time.time()

        receiver.processing_started.connect(on_started)
        receiver.processing_finished.connect(on_finished)

        # Emit signal from worker thread
        def emit_in_thread():
            worker.progress.emit(42)

        thread.started.connect(emit_in_thread)
        thread.start()

        # Wait for completion
        qtbot.waitUntil(lambda: start_time is not None and end_time is not None, timeout=1000)
        thread.quit()
        thread.wait()

        # Verify blocking occurred
        assert start_time is not None
        assert end_time is not None
        assert (end_time - start_time) >= 0.1  # At least 100ms

@pytest.mark.gui
class TestSignalParameterMarshalling:
    """Test parameter marshalling across threads."""

    def test_primitive_types_marshalling(self, qtbot):
        """Test marshalling of primitive types across threads."""

        class TypeEmitter(QObject):
            int_signal = Signal(int)
            float_signal = Signal(float)
            str_signal = Signal(str)
            bool_signal = Signal(bool)
            bytes_signal = Signal(bytes)

        emitter = TypeEmitter()
        SignalCollector()
        thread = QThread()

        emitter.moveToThread(thread)

        # Connect all signals
        received = {}

        @Slot(int)
        def receive_int(v): received['int'] = v

        @Slot(float)
        def receive_float(v): received['float'] = v

        @Slot(str)
        def receive_str(v): received['str'] = v

        @Slot(bool)
        def receive_bool(v): received['bool'] = v

        @Slot(bytes)
        def receive_bytes(v): received['bytes'] = v

        emitter.int_signal.connect(receive_int)
        emitter.float_signal.connect(receive_float)
        emitter.str_signal.connect(receive_str)
        emitter.bool_signal.connect(receive_bool)
        emitter.bytes_signal.connect(receive_bytes)

        # Emit from worker thread
        def emit_all():
            emitter.int_signal.emit(42)
            emitter.float_signal.emit(3.14)
            emitter.str_signal.emit("hello")
            emitter.bool_signal.emit(True)
            emitter.bytes_signal.emit(b"data")

        thread.started.connect(emit_all)
        thread.start()

        # Wait for signals
        qtbot.waitUntil(lambda: len(received) == 5, timeout=1000)
        thread.quit()
        thread.wait()

        # Verify all types marshalled correctly
        assert received['int'] == 42
        assert received['float'] == 3.14
        assert received['str'] == "hello"
        assert received['bool'] == True
        assert received['bytes'] == b"data"

    def test_complex_object_marshalling(self, qtbot):
        """Test marshalling of complex objects across threads."""

        class ComplexEmitter(QObject):
            list_signal = Signal(list)
            dict_signal = Signal(dict)
            tuple_signal = Signal(tuple)

        emitter = ComplexEmitter()
        thread = QThread()
        emitter.moveToThread(thread)

        received = {}

        @Slot(list)
        def receive_list(v): received['list'] = v

        @Slot(dict)
        def receive_dict(v): received['dict'] = v

        @Slot(tuple)
        def receive_tuple(v): received['tuple'] = v

        emitter.list_signal.connect(receive_list)
        emitter.dict_signal.connect(receive_dict)
        emitter.tuple_signal.connect(receive_tuple)

        # Test data
        test_list = [1, 2, 3, "four", 5.0]
        test_dict = {"key": "value", "number": 42}
        test_tuple = (1, "two", 3.0)

        def emit_complex():
            emitter.list_signal.emit(test_list)
            emitter.dict_signal.emit(test_dict)
            emitter.tuple_signal.emit(test_tuple)

        thread.started.connect(emit_complex)
        thread.start()

        qtbot.waitUntil(lambda: len(received) == 3, timeout=1000)
        thread.quit()
        thread.wait()

        # Verify complex types marshalled correctly
        assert received['list'] == test_list
        assert received['dict'] == test_dict
        assert received['tuple'] == test_tuple

@pytest.mark.gui
class TestThreadAffinity:
    """Test Qt object thread affinity rules."""

    def test_parent_child_thread_affinity(self, qtbot):
        """Test parent and child must be in same thread."""
        parent = QObject()
        child = QObject(parent)

        # Both should be in main thread
        main_thread = QThread.currentThread()
        assert parent.thread() == main_thread
        assert child.thread() == main_thread

        # Cannot move parent with children to another thread
        thread = QThread()
        with pytest.raises(Exception):
            parent.moveToThread(thread)

    def test_object_creation_after_move(self, qtbot):
        """Test creating QObjects after moveToThread."""

        class Worker(QObject):
            object_created = Signal(bool)

            def __init__(self):
                super().__init__()
                self.timer = None

            @Slot()
            def create_objects(self):
                """Create QObjects in worker thread."""
                # This timer will have correct thread affinity
                self.timer = QTimer()
                self.timer.setInterval(100)

                # Check thread affinity
                worker_thread = QThread.currentThread()
                timer_thread = self.timer.thread()

                self.object_created.emit(worker_thread == timer_thread)

        worker = Worker()
        thread = QThread()

        # Move worker BEFORE creating child objects
        worker.moveToThread(thread)

        # Connect and verify
        result = []
        worker.object_created.connect(lambda v: result.append(v))

        thread.started.connect(worker.create_objects)
        thread.start()

        qtbot.waitUntil(lambda: len(result) > 0, timeout=1000)
        thread.quit()
        thread.wait()

        # Timer should have same thread as worker
        assert result[0] == True

@pytest.mark.gui
class TestSignalSynchronization:
    """Test synchronization patterns with signals."""

    def test_wait_condition_pattern(self, qtbot):
        """Test QWaitCondition with counter pattern for synchronization."""

        class SynchronizedWorker(QObject):
            work_done = Signal(int)

            def __init__(self):
                super().__init__()
                self.mutex = QMutex()
                self.wait_condition = QWaitCondition()
                self.active_count = 0
                self.should_wait = True

            @Slot()
            def do_work(self):
                """Worker that waits for condition."""
                self.mutex.lock()

                while self.should_wait:
                    self.wait_condition.wait(self.mutex)

                self.active_count += 1
                work_id = self.active_count
                self.mutex.unlock()

                # Do actual work
                QThread.msleep(50)

                # Signal completion
                self.work_done.emit(work_id)

                # Decrement counter
                self.mutex.lock()
                self.active_count -= 1
                self.mutex.unlock()

            @Slot()
            def wake_workers(self):
                """Wake up waiting workers."""
                self.mutex.lock()
                self.should_wait = False
                self.mutex.unlock()
                self.wait_condition.wakeAll()

        worker = SynchronizedWorker()
        thread = QThread()
        worker.moveToThread(thread)

        # Track completions
        completions = []
        worker.work_done.connect(lambda v: completions.append(v))

        # Start worker (will wait)
        thread.started.connect(worker.do_work)
        thread.start()

        # Let it start waiting (brief pause for thread startup)
        QApplication.processEvents()
        QThread.msleep(50)

        # Wake it up
        worker.wake_workers()

        # Wait for completion
        qtbot.waitUntil(lambda: len(completions) > 0, timeout=1000)

        thread.quit()
        thread.wait()

        # Should have completed
        assert len(completions) == 1

    def test_event_loop_synchronization(self, qtbot):
        """Test using QEventLoop for synchronization."""

        class AsyncWorker(QObject):
            result_ready = Signal(str)

            @Slot()
            def async_operation(self):
                """Simulate async operation."""
                QTimer.singleShot(100, lambda: self.result_ready.emit("Done"))

        worker = AsyncWorker()

        # Synchronous wrapper using event loop
        def wait_for_result() -> str:
            loop = QEventLoop()
            result = []

            def on_result(value):
                result.append(value)
                loop.quit()

            worker.result_ready.connect(on_result)
            worker.async_operation()

            # Wait synchronously
            loop.exec()

            return result[0] if result else None

        # Test synchronous wait
        result = wait_for_result()
        assert result == "Done"

@pytest.mark.gui
class TestDeadlockPrevention:
    """Test patterns that prevent deadlocks."""

    def test_signal_emission_outside_lock(self, qtbot):
        """Test emitting signals outside mutex locks to prevent deadlock."""

        class SafeEmitter(QObject):
            value_changed = Signal(int)

            def __init__(self):
                super().__init__()
                self._value = 0
                self._mutex = QMutex()

            @Slot()
            def update_value(self):
                """Update value and emit signal safely."""
                # Lock, modify, unlock
                self._mutex.lock()
                self._value += 1
                new_value = self._value
                self._mutex.unlock()

                # Emit OUTSIDE the lock
                self.value_changed.emit(new_value)

            @Slot(result=int)
            def get_value(self) -> int:
                """Get value safely."""
                with QMutexLocker(self._mutex):
                    return self._value

        emitter = SafeEmitter()

        # Connect slot that also needs the mutex
        @Slot(int)
        def on_value_changed(value):
            # This could try to acquire mutex
            current = emitter.get_value()
            assert current >= value

        emitter.value_changed.connect(on_value_changed)

        # Update multiple times - should not deadlock
        for _ in range(10):
            emitter.update_value()

        # Process pending signals
        QApplication.processEvents()
        assert emitter.get_value() == 10

    def test_unique_connection_prevents_duplicates(self, qtbot):
        """Test UniqueConnection flag prevents duplicate connections."""

        class Emitter(QObject):
            signal = Signal(int)

        emitter = Emitter()
        counter = ThreadSafeCounter()

        # Connect multiple times with UniqueConnection
        for _ in range(5):
            emitter.signal.connect(
                counter.increment,
                Qt.ConnectionType.UniqueConnection
            )

        # Emit once
        emitter.signal.emit(1)
        qtbot.waitUntil(lambda: counter.get_value() > 0, timeout=500)

        # Should only increment once despite multiple connection attempts
        assert counter.get_value() == 1

@pytest.mark.gui
class TestHighConcurrency:
    """Test high concurrency scenarios."""

    def test_multiple_threads_single_receiver(self, qtbot):
        """Test multiple worker threads signaling to single receiver."""

        class MultiWorker(QObject):
            result = Signal(int, int)  # thread_id, value

            def __init__(self, worker_id):
                super().__init__()
                self.worker_id = worker_id

            @Slot()
            def process(self):
                """Process in worker thread."""
                for i in range(5):
                    QThread.msleep(10)
                    self.result.emit(self.worker_id, i)

        # Create multiple workers
        num_workers = 5
        workers = []
        threads = []
        results = []

        @Slot(int, int)
        def collect_result(worker_id, value):
            results.append((worker_id, value))

        for i in range(num_workers):
            worker = MultiWorker(i)
            thread = QThread()

            worker.moveToThread(thread)
            worker.result.connect(collect_result)
            thread.started.connect(worker.process)

            workers.append(worker)
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        qtbot.waitUntil(lambda: len(results) == num_workers * 5, timeout=2000)

        # Clean up threads
        for thread in threads:
            thread.quit()
            thread.wait()

        # Verify all results received
        assert len(results) == num_workers * 5

        # Check each worker contributed
        for i in range(num_workers):
            worker_results = [v for wid, v in results if wid == i]
            assert len(worker_results) == 5

    def test_signal_storm_handling(self, qtbot):
        """Test handling rapid signal emissions (signal storm)."""

        class SignalStorm(QObject):
            signal = Signal(int)

        storm = SignalStorm()
        received = []

        @Slot(int)
        def receive(value):
            received.append(value)

        storm.signal.connect(receive)

        # Emit many signals rapidly
        num_signals = 1000
        for i in range(num_signals):
            storm.signal.emit(i)

        # Process all events
        qtbot.waitUntil(lambda: len(received) == num_signals, timeout=2000)
        QApplication.processEvents()

        # All should be received in order
        assert len(received) == num_signals
        assert received == list(range(num_signals))

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
