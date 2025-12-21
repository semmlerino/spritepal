"""
Test suite for Qt threading patterns and concurrency validation.

This suite specifically tests:
1. QThread patterns (moveToThread vs subclassing)
2. Signal/slot connections across threads
3. Thread affinity and object ownership
4. Event loop management
5. Synchronization and thread safety

SKIPPED: QThread signal synchronization tests hang in Qt offscreen mode.
These tests require a real display.
"""
from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtCore import (
    # Serial execution required: QApplication management, Thread safety concerns
    QEventLoop,
    QMutex,
    QMutexLocker,
    QObject,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import QApplication

from core.workers.base import BaseWorker, handle_worker_errors
from ui.common import WorkerManager

pytestmark = [
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Thread tests may intentionally leave threads running"),
    pytest.mark.headless,
    pytest.mark.slow,
]
class ThreadInfoCapture:
    """Helper to capture thread information during signal delivery"""

    def __init__(self):
        self.captures = []
        self.lock = threading.Lock()

    def capture(self, label: str):
        """Capture current thread info"""
        with self.lock:
            thread = threading.current_thread()
            qt_thread = QThread.currentThread()
            self.captures.append({
                'label': label,
                'thread_id': thread.ident,
                'thread_name': thread.name,
                'is_main': thread == threading.main_thread(),
                'qt_thread': qt_thread,
                'qt_thread_id': id(qt_thread) if qt_thread else None
            })

    def get_capture(self, label: str):
        """Get capture by label"""
        with self.lock:
            for capture in self.captures:
                if capture['label'] == label:
                    return capture
        return None

    def reset(self):
        """Reset captures"""
        with self.lock:
            self.captures.clear()

class TestQThreadPatterns:
    """Test different QThread implementation patterns"""

    @pytest.fixture
    def app(self):
        """Ensure QApplication exists"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    @pytest.fixture
    def thread_capture(self):
        """Create thread capture helper"""
        return ThreadInfoCapture()

    def test_movetothread_pattern(self, app, thread_capture):
        """Test the recommended moveToThread pattern"""

        class Worker(QObject):
            started = Signal()
            progress = Signal(int)
            finished = Signal()

            def __init__(self):
                super().__init__()
                self.should_stop = False

            def process(self):
                thread_capture.capture('worker_start')
                self.started.emit()

                for i in range(5):
                    if self.should_stop:
                        break
                    thread_capture.capture(f'worker_progress_{i}')
                    self.progress.emit(i)
                    time.sleep(0.01)  # sleep-ok: thread interleaving

                thread_capture.capture('worker_finish')
                self.finished.emit()

            def stop(self):
                self.should_stop = True

        # Create worker and thread
        worker = Worker()
        thread = QThread()

        # Capture main thread info
        thread_capture.capture('main_thread')

        # Move worker to thread
        worker.moveToThread(thread)

        # Connect signals
        thread.started.connect(worker.process)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Capture signal reception
        signal_received = []
        finished_received = False

        def on_finished():
            nonlocal finished_received
            finished_received = True

        worker.progress.connect(lambda x: signal_received.append(x))
        worker.finished.connect(on_finished)

        # Start thread
        thread.start()

        # Wait for completion with event processing
        start_time = time.time()
        while not finished_received and time.time() - start_time < 2.0:
            app.processEvents()
            time.sleep(0.01)  # sleep-ok: thread interleaving

        # Ensure thread finishes
        thread.quit()
        assert thread.wait(1000)

        # Verify thread execution
        main_capture = thread_capture.get_capture('main_thread')
        worker_start = thread_capture.get_capture('worker_start')

        # Worker should run in different thread
        assert worker_start['thread_id'] != main_capture['thread_id']
        assert not worker_start['is_main']

        # All worker operations should be in same thread
        for i in range(5):
            progress = thread_capture.get_capture(f'worker_progress_{i}')
            if progress:
                assert progress['thread_id'] == worker_start['thread_id']

        # Signals should be received
        assert len(signal_received) == 5

    def test_subclassing_pattern(self, app, thread_capture):
        """Test the QThread subclassing pattern"""

        class WorkerThread(QThread):
            progress = Signal(int)

            def run(self):
                thread_capture.capture('subclass_run')

                for i in range(5):
                    thread_capture.capture(f'subclass_progress_{i}')
                    self.progress.emit(i)
                    time.sleep(0.01)  # sleep-ok: thread interleaving

        # Create and start thread
        thread = WorkerThread()

        # Capture signals
        signal_received = []
        thread.progress.connect(lambda x: signal_received.append(x))

        # Start thread
        thread.start()
        thread.wait(1000)

        # Process queued signals from worker thread
        QApplication.processEvents()

        # Verify execution in separate thread
        run_capture = thread_capture.get_capture('subclass_run')
        assert run_capture is not None
        assert not run_capture['is_main']

        # Verify signals received
        assert len(signal_received) == 5

    def test_thread_affinity(self, app):
        """Test Qt object thread affinity rules"""

        class Worker(QObject):
            def __init__(self):
                super().__init__()
                # Record creation thread
                self.creation_thread = QThread.currentThread()

                # This timer will have wrong thread affinity if created here
                # self.timer = QTimer()  # DON'T DO THIS

                self.timer = None

            def setup_in_thread(self):
                # Create QTimer in the correct thread
                self.timer = QTimer()
                self.timer.setInterval(100)

                # Verify timer has correct thread affinity
                assert self.timer.thread() == QThread.currentThread()
                assert self.timer.thread() == self.thread()

        # Create worker in main thread
        worker = Worker()
        main_thread = QThread.currentThread()

        # Worker initially has main thread affinity
        assert worker.thread() == main_thread

        # Create new thread and move worker
        thread = QThread()
        worker.moveToThread(thread)

        # Worker now has new thread affinity
        assert worker.thread() == thread
        assert worker.thread() != main_thread

        # Connect setup to thread start
        thread.started.connect(worker.setup_in_thread)

        # Start thread
        thread.start()
        thread.quit()
        thread.wait(1000)

        # Cleanup
        worker.deleteLater()
        thread.deleteLater()

class TestSignalSlotAcrossThreads:
    """Test signal/slot mechanism across threads"""

    @pytest.fixture
    def app(self):
        """Ensure QApplication exists"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_connection_types(self, app):
        """Test different Qt connection types"""

        class Emitter(QObject):
            signal = Signal(str)

        class Receiver(QObject):
            def __init__(self):
                super().__init__()
                self.received = []
                self.receive_threads = []

            def on_signal(self, msg):
                self.received.append(msg)
                self.receive_threads.append(QThread.currentThread())

        # Create objects
        emitter = Emitter()
        receiver = Receiver()

        # Test 1: Auto connection (should be direct in same thread)
        emitter.signal.connect(receiver.on_signal)
        emitter.signal.emit("auto_same_thread")

        assert len(receiver.received) == 1
        assert receiver.receive_threads[0] == QThread.currentThread()

        # Test 2: Queued connection across threads
        receiver.received.clear()
        receiver.receive_threads.clear()

        # Move emitter to different thread
        thread = QThread()
        emitter.moveToThread(thread)
        thread.start()

        # Emit from worker thread
        def emit_from_thread():
            emitter.signal.emit("queued_cross_thread")

        QTimer.singleShot(0, emit_from_thread)

        # Process events to receive signal
        loop = QEventLoop()
        QTimer.singleShot(100, loop.quit)
        loop.exec()

        # Signal should be received in main thread
        assert len(receiver.received) == 1
        assert receiver.receive_threads[0] == QThread.currentThread()

        # Cleanup
        thread.quit()
        thread.wait()

    def test_signal_parameter_safety(self, app):
        """Test thread-safe parameter passing in signals"""

        class DataHolder:
            def __init__(self):
                self.data = []
                self.mutex = QMutex()

            def add_data(self, value):
                with QMutexLocker(self.mutex):
                    self.data.append(value)

            def get_data(self):
                with QMutexLocker(self.mutex):
                    return self.data.copy()

        class Worker(QObject):
            data_ready = Signal(list)

            def __init__(self, data_holder):
                super().__init__()
                self.data_holder = data_holder

            def process(self):
                # Modify shared data
                for i in range(10):
                    self.data_holder.add_data(f"worker_{i}")

                # Emit copy of data
                self.data_ready.emit(self.data_holder.get_data())

        # Create shared data
        data_holder = DataHolder()

        # Create worker
        worker = Worker(data_holder)
        thread = QThread()
        worker.moveToThread(thread)

        # Capture emitted data
        received_data = []
        worker.data_ready.connect(lambda x: received_data.append(x))

        # Connect and start
        thread.started.connect(worker.process)
        thread.start()

        # Wait for completion
        thread.quit()
        thread.wait(1000)

        # Verify data integrity
        assert len(received_data) == 1
        assert len(received_data[0]) == 10
        assert all(f"worker_{i}" in received_data[0] for i in range(10))

class TestEventLoopManagement:
    """Test event loop management in worker threads"""

    @pytest.fixture
    def app(self):
        """Ensure QApplication exists"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_worker_thread_event_loop(self, app):
        """Test event loop in worker thread"""

        class Worker(QObject):
            work_done = Signal(str)

            def __init__(self):
                super().__init__()
                self.timer = None
                self.count = 0

            def start_work(self):
                # Create timer in worker thread
                self.timer = QTimer()
                self.timer.timeout.connect(self.do_work)
                self.timer.start(50)  # 50ms intervals

            def do_work(self):
                self.count += 1
                self.work_done.emit(f"Work {self.count}")

                if self.count >= 5:
                    self.timer.stop()
                    QThread.currentThread().quit()

        # Create worker and thread
        worker = Worker()
        thread = QThread()
        worker.moveToThread(thread)

        # Capture work done
        work_results = []
        worker.work_done.connect(work_results.append)

        # Connect signals
        thread.started.connect(worker.start_work)

        # Start thread (will run event loop)
        thread.start()

        # Wait for completion
        assert thread.wait(2000)

        # Verify work was done
        assert len(work_results) == 5
        assert work_results[-1] == "Work 5"

    def test_blocking_operations_with_event_loop(self, app):
        """Test handling blocking operations with event loop"""

        class Worker(QObject):
            result_ready = Signal(str)

            def process_with_event_loop(self):
                # Create local event loop for synchronous-style code
                loop = QEventLoop()
                result = None

                def on_timer_timeout():
                    nonlocal result
                    result = "Timer completed"
                    loop.quit()

                # Setup timer
                timer = QTimer()
                timer.timeout.connect(on_timer_timeout)
                timer.setSingleShot(True)
                timer.start(100)

                # Block until timer completes
                loop.exec()

                # Emit result
                self.result_ready.emit(result)
                QThread.currentThread().quit()

        # Create and setup worker
        worker = Worker()
        thread = QThread()
        worker.moveToThread(thread)

        # Capture result
        results = []
        worker.result_ready.connect(results.append)

        # Run in thread
        thread.started.connect(worker.process_with_event_loop)

        thread.start()
        assert thread.wait(1000)

        # Verify result
        assert len(results) == 1
        assert results[0] == "Timer completed"

class TestSynchronizationPatterns:
    """Test Qt synchronization patterns"""

    @pytest.fixture
    def app(self):
        """Ensure QApplication exists"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_mutex_protection(self, app):
        """Test QMutex for thread-safe data access"""

        class SharedCounter(QObject):
            count_changed = Signal(int)

            def __init__(self):
                super().__init__()
                self._count = 0
                self._mutex = QMutex()

            def increment(self):
                with QMutexLocker(self._mutex):
                    self._count += 1
                    current = self._count
                # Emit outside lock to prevent deadlock
                self.count_changed.emit(current)

            def get_count(self):
                with QMutexLocker(self._mutex):
                    return self._count

        # Create shared counter
        counter = SharedCounter()

        # Create multiple worker threads
        class IncrementWorker(QThread):
            def __init__(self, counter, iterations):
                super().__init__()
                self.counter = counter
                self.iterations = iterations

            def run(self):
                for _ in range(self.iterations):
                    self.counter.increment()

        # Start multiple workers
        workers = []
        increments_per_worker = 100
        num_workers = 5

        for _ in range(num_workers):
            worker = IncrementWorker(counter, increments_per_worker)
            workers.append(worker)
            worker.start()

        # Wait for all workers
        for worker in workers:
            worker.wait(2000)

        # Verify count is correct (no race conditions)
        expected_count = num_workers * increments_per_worker
        assert counter.get_count() == expected_count

    @pytest.mark.parallel_unsafe
    def test_signal_based_synchronization(self, app):
        """Test using signals for thread synchronization.

        Marked parallel_unsafe because Qt threading state can conflict
        between parallel test workers sharing the same QApplication.
        """

        class Coordinator(QObject):
            start_work = Signal(int)
            work_done = Signal(int, str)
            all_done = Signal()

            def __init__(self, num_workers):
                super().__init__()
                self.num_workers = num_workers
                self.completed = 0
                self.results = {}

            def on_work_done(self, worker_id, result):
                self.results[worker_id] = result
                self.completed += 1

                if self.completed == self.num_workers:
                    self.all_done.emit()

        class Worker(QObject):
            def __init__(self, worker_id, coordinator):
                super().__init__()
                self.worker_id = worker_id
                self.coordinator = coordinator

                # Connect to coordinator
                coordinator.start_work.connect(self.do_work)

            def do_work(self, data):
                # Simulate work
                time.sleep(0.01)  # sleep-ok: thread interleaving
                result = f"Worker {self.worker_id} processed {data}"

                # Report completion
                self.coordinator.work_done.emit(self.worker_id, result)

        # Create coordinator
        num_workers = 3
        coordinator = Coordinator(num_workers)

        # Connect work_done signal to handler
        coordinator.work_done.connect(coordinator.on_work_done)

        # Create workers in separate threads
        workers = []
        threads = []

        for i in range(num_workers):
            worker = Worker(i, coordinator)
            thread = QThread()

            worker.moveToThread(thread)
            thread.start()

            workers.append(worker)
            threads.append(thread)

        # Setup completion handling
        loop = QEventLoop()
        coordinator.all_done.connect(loop.quit)

        # Start work
        coordinator.start_work.emit(42)

        # Wait for completion
        loop.exec()

        # Verify all workers completed
        assert len(coordinator.results) == num_workers
        for i in range(num_workers):
            assert i in coordinator.results
            assert f"Worker {i} processed 42" == coordinator.results[i]

        # Cleanup threads
        for thread in threads:
            thread.quit()
            thread.wait()

class TestWorkerLifecycle:
    """Test worker lifecycle management"""

    @pytest.fixture
    def app(self):
        """Ensure QApplication exists"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_worker_cleanup_pattern(self, app):
        """Test proper worker cleanup pattern using WorkerManager"""

        class TestWorker(BaseWorker):
            progress = Signal(int)
            finished = Signal()

            @handle_worker_errors()  # Note: decorator factory needs parentheses
            def run(self):
                for i in range(50):  # Longer running to ensure still running when cleanup called
                    if self.is_cancelled:
                        break
                    self.progress.emit(i)
                    time.sleep(0.02)  # sleep-ok: thread interleaving
                self.finished.emit()

        # Create worker
        worker = TestWorker()

        # Track cancellation via the cancel method
        cancel_called = False
        original_cancel = worker.cancel

        def track_cancel():
            nonlocal cancel_called
            cancel_called = True
            original_cancel()

        worker.cancel = track_cancel

        # Use WorkerManager for proper lifecycle
        worker.start()

        # Wait a short bit then cleanup via WorkerManager (worker should still be running)
        time.sleep(0.05)  # sleep-ok: thread interleaving
        WorkerManager.cleanup_worker(worker, timeout=1000)

        # Verify cancel was called (WorkerManager calls cancel if available)
        assert cancel_called
        assert worker.is_cancelled

    def test_worker_error_handling(self, app):
        """Test worker error handling with decorator"""

        class ErrorWorker(BaseWorker):
            # BaseWorker already has 'error' signal, no need to redefine

            @handle_worker_errors()  # Note: decorator factory needs parentheses
            def run(self):
                # This will be caught by decorator
                raise ValueError("Test error")

        # Create worker
        worker = ErrorWorker()

        # Capture error using BaseWorker's error signal
        errors = []
        worker.error.connect(lambda msg, exc: errors.append((msg, exc)))

        # Run worker
        worker.start()
        worker.wait(1000)

        # Process queued signals from worker thread
        QApplication.processEvents()

        # Verify error was emitted
        assert len(errors) == 1
        assert "Test error" in errors[0][0]
        assert isinstance(errors[0][1], ValueError)

class TestRealWorldScenarios:
    """Test real-world threading scenarios"""

    @pytest.fixture
    def app(self):
        """Ensure QApplication exists"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_gui_update_from_worker(self, app):
        """Test safe GUI updates from worker thread"""

        class GUIUpdater(QObject):
            update_gui = Signal(str)

            def __init__(self):
                super().__init__()
                self.gui_updates = []
                self.update_threads = []

                # Connect signal to slot
                self.update_gui.connect(self._on_update_gui)

            def _on_update_gui(self, text):
                # This should always run in main thread
                self.gui_updates.append(text)
                self.update_threads.append(QThread.currentThread())

        class Worker(QThread):
            def __init__(self, updater):
                super().__init__()
                self.updater = updater

            def run(self):
                # Emit updates from worker thread
                for i in range(3):
                    self.updater.update_gui.emit(f"Update {i}")
                    time.sleep(0.01)  # sleep-ok: thread interleaving

        # Create updater and worker
        updater = GUIUpdater()
        worker = Worker(updater)

        # Get main thread reference
        main_thread = QThread.currentThread()

        # Run worker
        worker.start()
        worker.wait(1000)

        # Process events
        app.processEvents()

        # Verify all updates received in main thread
        assert len(updater.gui_updates) == 3
        for thread in updater.update_threads:
            assert thread == main_thread

    def test_concurrent_operations(self, app):
        """Test concurrent operations with proper synchronization"""

        class DataProcessor(QObject):
            processing_done = Signal(int, list)

            def __init__(self):
                super().__init__()
                self.mutex = QMutex()
                self.processed_data = {}

            def process_chunk(self, chunk_id, data):
                # Simulate processing
                result = [x * 2 for x in data]
                time.sleep(0.01)  # sleep-ok: thread interleaving

                # Store result thread-safely
                with QMutexLocker(self.mutex):
                    self.processed_data[chunk_id] = result

                # Emit completion
                self.processing_done.emit(chunk_id, result)

        # Create processor
        processor = DataProcessor()

        class ChunkWorker(QThread):
            def __init__(self, chunk_id: int, data: list[int]):
                super().__init__()
                self.chunk_id = chunk_id
                self.data = data

            def run(self):
                processor.process_chunk(self.chunk_id, self.data)

        # Create multiple worker threads
        threads = []
        chunks = {
            0: [1, 2, 3],
            1: [4, 5, 6],
            2: [7, 8, 9]
        }

        for chunk_id, data in chunks.items():
            # Process chunk when thread starts
            worker = ChunkWorker(chunk_id, data)
            threads.append(worker)
            worker.start()

        # Wait for all threads
        for thread in threads:
            assert thread.wait(1000)

        # Process queued signals from worker threads
        QApplication.processEvents()

        # Verify all chunks processed correctly
        assert len(processor.processed_data) == 3
        assert processor.processed_data[0] == [2, 4, 6]
        assert processor.processed_data[1] == [8, 10, 12]
        assert processor.processed_data[2] == [14, 16, 18]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
