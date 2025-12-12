"""
Comprehensive test suite for Qt signal architecture and threading safety validation.

This test suite validates:
1. Signal connection architecture after protocol casting
2. Threading safety of signal emissions
3. Signal parameter passing and type safety
4. Protocol compliance with concrete implementations
5. Error scenarios and cleanup
"""
from __future__ import annotations

import threading
import time
from typing import cast
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication

from core.controller import ExtractionController
from core.managers import (
    # Serial execution required: QApplication management, Thread safety concerns, Real Qt components
    ExtractionManager,
    InjectionManager,
    initialize_managers,
)
from core.di_container import inject
from core.protocols.dialog_protocols import DialogFactoryProtocol
from core.protocols.manager_protocols import (
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
    SessionManagerProtocol,
    SettingsManagerProtocol,
)
from tests.infrastructure.real_component_factory import RealComponentFactory

pytestmark = [
    pytest.mark.usefixtures("session_managers"),  # Initialize DI container
    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.thread_safety,
    pytest.mark.cache,
    pytest.mark.headless,
    pytest.mark.memory,
    pytest.mark.performance,
    pytest.mark.requires_display,
    pytest.mark.signals_slots,
    pytest.mark.slow,
    pytest.mark.worker_threads,
]
class SignalCapture(QObject):
    """Helper class to capture Qt signals for testing"""

    def __init__(self):
        super().__init__()
        self.captured_signals = []
        self.signal_threads = []
        self.lock = threading.Lock()

    def capture(self, *args):
        """Capture signal emission with thread info"""
        with self.lock:
            current_thread = threading.current_thread()
            self.captured_signals.append(args)
            self.signal_threads.append({
                'thread_id': current_thread.ident,
                'thread_name': current_thread.name,
                'is_main': current_thread == threading.main_thread()
            })

    def reset(self):
        """Reset captured data"""
        with self.lock:
            self.captured_signals.clear()
            self.signal_threads.clear()

    def wait_for_signal(self, timeout=1.0):
        """Wait for at least one signal with timeout using Qt-safe waiting"""
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication

        start_time = time.time()
        while time.time() - start_time < timeout:
            with self.lock:
                if self.captured_signals:
                    return True
            # Process Qt events and use Qt-safe sleep
            app = QApplication.instance()
            if app:
                app.processEvents()
            current_thread = QThread.currentThread()
            if current_thread:
                current_thread.msleep(10)
            else:
                time.sleep(0.01)  # Fallback for non-Qt threads
        return False

class TestQtSignalArchitecture:
    """Test Qt signal architecture after controller fixes"""

    @pytest.fixture
    def app(self):
        """Ensure QApplication exists for Qt testing"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    @pytest.fixture
    def signal_capture(self):
        """Create signal capture helper"""
        return SignalCapture()

    @pytest.fixture
    def mock_factory(self):
        """Get mock factory instance"""
        return RealComponentFactory()

    def test_signal_connection_with_casting(self, app, mock_factory, signal_capture):
        """Test that signal connections work correctly with protocol casting"""
        # Initialize managers first
        initialize_managers()

        # Create real managers
        injection_mgr = InjectionManager()
        extraction_mgr = ExtractionManager()

        # Create mock main window
        main_window = mock_factory.create_main_window()

        # Create controller with managers as protocols
        controller = ExtractionController(
            main_window=main_window,
            extraction_manager=extraction_mgr,
            session_manager=inject(SessionManagerProtocol),
            injection_manager=injection_mgr,
            settings_manager=inject(SettingsManagerProtocol),
            dialog_factory=inject(DialogFactoryProtocol),
        )

        # Connect signal capture to manager signals
        injection_mgr.injection_progress.connect(signal_capture.capture)
        injection_mgr.injection_finished.connect(signal_capture.capture)
        extraction_mgr.cache_saved.connect(signal_capture.capture)

        # Test 1: Verify signals are properly connected
        assert controller.injection_manager is injection_mgr
        assert controller.extraction_manager is extraction_mgr

        # Test 2: Emit signals and verify they're received
        injection_mgr.injection_progress.emit("Test progress")
        assert signal_capture.wait_for_signal()
        assert signal_capture.captured_signals[0] == ("Test progress",)

        signal_capture.reset()
        injection_mgr.injection_finished.emit(True, "Success")
        assert signal_capture.wait_for_signal()
        assert signal_capture.captured_signals[0] == (True, "Success")

        signal_capture.reset()
        extraction_mgr.cache_saved.emit("sprite_cache", 10)
        assert signal_capture.wait_for_signal()
        assert signal_capture.captured_signals[0] == ("sprite_cache", 10)

    def test_protocol_compliance(self):
        """Test that concrete managers comply with protocols via duck typing"""
        # Test InjectionManager compliance via duck typing
        # (Protocols aren't @runtime_checkable, so use hasattr checks)
        injection_mgr = InjectionManager()

        # Verify InjectionManagerProtocol signals exist
        injection_signals = ['injection_progress', 'injection_finished', 'compression_info']
        for signal_name in injection_signals:
            assert hasattr(injection_mgr, signal_name), f"Missing {signal_name}"
            signal = getattr(injection_mgr, signal_name)
            assert isinstance(signal, Signal), f"{signal_name} is not a Signal"

        # Test ExtractionManager compliance via duck typing
        extraction_mgr = ExtractionManager()

        # Verify ExtractionManagerProtocol signals exist (actual signals on the class)
        extraction_signals = ['extraction_progress', 'cache_saved', 'preview_generated']
        for signal_name in extraction_signals:
            assert hasattr(extraction_mgr, signal_name), f"Missing {signal_name}"
            signal = getattr(extraction_mgr, signal_name)
            assert isinstance(signal, Signal), f"{signal_name} is not a Signal"

    def test_thread_safety_signal_emission(self, app, signal_capture):
        """Test that signals work correctly across thread boundaries"""
        manager = InjectionManager()
        manager.injection_progress.connect(signal_capture.capture)

        # Define worker thread function
        def worker_thread():
            # Emit signal from worker thread
            manager.injection_progress.emit("Progress from worker thread")

        # Start worker thread
        thread = threading.Thread(target=worker_thread)
        thread.start()
        thread.join()

        # Verify signal was received
        assert signal_capture.wait_for_signal()
        assert signal_capture.captured_signals[0] == ("Progress from worker thread",)

        # Verify signal was handled in main thread (Qt queued connection)
        thread_info = signal_capture.signal_threads[0]
        assert thread_info['is_main']  # Signal should be delivered to main thread

    def test_signal_parameter_types(self, app, signal_capture):
        """Test that signal parameters are passed correctly with proper types"""
        manager = ExtractionManager()

        # Test different signal parameter types
        # Note: Qt signal/slot mechanism converts tuples to lists in dict values
        test_cases = [
            (manager.extraction_progress, ("Test message",)),
            (manager.preview_generated, (Mock(spec=object), 42)),
            (manager.palettes_extracted, ({"palette1": [[255, 0, 0]]},)),  # List not tuple
            (manager.active_palettes_found, ([1, 2, 3],)),
            (manager.cache_hit, ("sprite_cache", 1.5)),
        ]

        for signal, params in test_cases:
            signal_capture.reset()
            signal.connect(signal_capture.capture)
            signal.emit(*params)

            assert signal_capture.wait_for_signal()
            assert signal_capture.captured_signals[0] == params

            signal.disconnect(signal_capture.capture)

    def test_signal_cleanup_on_deletion(self, app):
        """Test that signals are properly cleaned up when objects are deleted"""
        manager = InjectionManager()

        # Create a receiver object
        receiver = SignalCapture()
        manager.injection_progress.connect(receiver.capture)

        # Verify connection works
        manager.injection_progress.emit("Test")
        assert receiver.wait_for_signal()

        # Delete manager and verify no crashes
        del manager

        # Receiver should still exist and be functional
        assert receiver is not None
        assert len(receiver.captured_signals) == 1

    def test_casting_preserves_functionality(self, app, mock_factory):
        """Test that casting to protocol and back preserves all functionality"""
        # Create concrete manager
        concrete_mgr = InjectionManager()

        # Cast to protocol
        protocol_mgr: InjectionManagerProtocol = concrete_mgr

        # Cast back to concrete type (as done in controller)
        casted_mgr = cast(InjectionManager, protocol_mgr)

        # Verify all signals still work
        capture = SignalCapture()
        casted_mgr.injection_progress.connect(capture.capture)
        casted_mgr.injection_progress.emit("Test after casting")

        assert capture.wait_for_signal()
        assert capture.captured_signals[0] == ("Test after casting",)

        # Verify object identity is preserved
        assert casted_mgr is concrete_mgr
        assert protocol_mgr is concrete_mgr

    def test_error_handling_with_signals(self, app, signal_capture):
        """Test signal behavior during error conditions"""
        manager = InjectionManager()
        manager.error_occurred.connect(signal_capture.capture)

        # Emit error signal directly (there's no _emit_error helper method)
        manager.error_occurred.emit("Test error: Simulated error")

        # Verify error signal was emitted
        assert signal_capture.wait_for_signal()
        assert "Test error" in str(signal_capture.captured_signals[0])

    def test_concurrent_signal_emissions(self, app, signal_capture):
        """Test concurrent signal emissions from multiple threads"""
        manager = ExtractionManager()
        manager.extraction_progress.connect(signal_capture.capture)

        num_threads = 5
        emissions_per_thread = 10

        def worker(thread_id):
            for i in range(emissions_per_thread):
                manager.extraction_progress.emit(f"Thread {thread_id} - Message {i}")
                time.sleep(0.001)  # Small delay to encourage interleaving

        # Start multiple threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify all signals were received
        expected_count = num_threads * emissions_per_thread
        timeout = 5.0
        start_time = time.time()

        while len(signal_capture.captured_signals) < expected_count and time.time() - start_time < timeout:
            # Use Qt-safe waiting
            app.processEvents()
            from PySide6.QtCore import QThread
            current_thread = QThread.currentThread()
            if current_thread:
                current_thread.msleep(10)
            else:
                time.sleep(0.01)

        assert len(signal_capture.captured_signals) == expected_count

        # Verify all were delivered to main thread
        for thread_info in signal_capture.signal_threads:
            assert thread_info['is_main']

    def test_signal_disconnection(self, app, signal_capture):
        """Test proper signal disconnection"""
        manager = InjectionManager()

        # Connect signal
        manager.injection_progress.connect(signal_capture.capture)

        # Emit and verify reception
        manager.injection_progress.emit("Connected")
        assert signal_capture.wait_for_signal()
        assert len(signal_capture.captured_signals) == 1

        # Disconnect
        manager.injection_progress.disconnect(signal_capture.capture)

        # Emit again and verify no reception
        signal_capture.reset()
        manager.injection_progress.emit("Disconnected")
        # Give time for potential delivery using Qt-safe wait
        from PySide6.QtTest import QTest
        QTest.qWait(100)
        assert len(signal_capture.captured_signals) == 0

    def test_controller_signal_forwarding(self, app, mock_factory, signal_capture):
        """Test that controller properly forwards signals from managers"""
        # Create managers and controller
        injection_mgr = InjectionManager()
        extraction_mgr = ExtractionManager()
        main_window = mock_factory.create_main_window()

        controller = ExtractionController(
            main_window=main_window,
            extraction_manager=extraction_mgr,
            session_manager=inject(SessionManagerProtocol),
            injection_manager=injection_mgr,
            settings_manager=inject(SettingsManagerProtocol),
            dialog_factory=inject(DialogFactoryProtocol),
        )

        # Capture controller's handling of manager signals
        called_methods = []

        def capture_method_call(method_name):
            def wrapper(*args, **kwargs):
                called_methods.append((method_name, args, kwargs))
            return wrapper

        # Mock controller handler methods
        controller._on_injection_progress = capture_method_call('_on_injection_progress')
        controller._on_injection_finished = capture_method_call('_on_injection_finished')
        controller._on_cache_saved = capture_method_call('_on_cache_saved')

        # Emit signals from managers
        injection_mgr.injection_progress.emit("Test progress")
        injection_mgr.injection_finished.emit(True, "Success")
        extraction_mgr.cache_saved.emit("sprite_cache", 5)

        # Process events to ensure signal delivery
        app.processEvents()
        from PySide6.QtTest import QTest
        QTest.qWait(100)

        # Verify controller methods were called
        assert len(called_methods) == 3
        assert called_methods[0] == ('_on_injection_progress', ("Test progress",), {})
        assert called_methods[1] == ('_on_injection_finished', (True, "Success"), {})
        assert called_methods[2] == ('_on_cache_saved', ("sprite_cache", 5), {})

    def test_worker_thread_signal_pattern(self, app, signal_capture):
        """Test the worker thread pattern with proper signal handling"""
        from PySide6.QtTest import QTest

        class TestWorker(QThread):
            progress = Signal(str)
            finished_signal = Signal(bool)  # Renamed to avoid conflict with QThread.finished

            def run(self):
                # Simulate work with progress updates
                for i in range(5):
                    self.progress.emit(f"Step {i + 1}/5")
                    self.msleep(10)  # Use Qt-safe sleep
                self.finished_signal.emit(True)

        # Create and connect worker
        worker = TestWorker()
        worker.progress.connect(signal_capture.capture)
        worker.finished_signal.connect(signal_capture.capture)

        # Start worker
        worker.start()

        # Wait for worker and process events to receive signals
        timeout_ms = 2000
        start_time = time.time()
        while worker.isRunning() and (time.time() - start_time) * 1000 < timeout_ms:
            app.processEvents()
            QTest.qWait(10)  # Small wait that processes events

        # Process any remaining pending signals
        app.processEvents()
        QTest.qWait(100)
        app.processEvents()

        # Verify signals were received in order
        assert len(signal_capture.captured_signals) >= 6, f"Got {len(signal_capture.captured_signals)} signals"

        # Check progress signals
        for i in range(5):
            assert signal_capture.captured_signals[i] == (f"Step {i + 1}/5",)

        # Check finished signal
        assert signal_capture.captured_signals[-1] == (True,)

        # Verify all signals were delivered to main thread
        for thread_info in signal_capture.signal_threads:
            assert thread_info['is_main']

class TestMemoryManagement:
    """Test memory management and leak prevention in signal architecture"""

    @pytest.fixture
    def app(self):
        """Ensure QApplication exists for Qt testing"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_circular_reference_prevention(self, app):
        """Test that signal connections don't create circular references"""
        import weakref

        # Create manager
        manager = InjectionManager()
        manager_ref = weakref.ref(manager)

        # Create receiver that holds reference to manager
        class Receiver(QObject):
            def __init__(self, mgr):
                super().__init__()
                self.manager = mgr  # Potential circular reference

            def on_signal(self, msg):
                pass

        receiver = Receiver(manager)
        receiver_ref = weakref.ref(receiver)

        # Connect signal
        manager.injection_progress.connect(receiver.on_signal)

        # Delete strong references
        del manager
        del receiver

        # Process events and garbage collect
        app.processEvents()
        import gc
        gc.collect()

        # Both should be garbage collected (no circular reference)
        assert manager_ref() is None
        assert receiver_ref() is None

    def test_signal_cleanup_on_thread_deletion(self, app):
        """Test that worker thread signals are properly cleaned up"""
        import weakref

        from PySide6.QtTest import QTest

        class Worker(QThread):
            work_signal = Signal(str)  # Renamed to avoid confusion

            def run(self):
                self.work_signal.emit("Working")

        # Create worker and capture
        worker = Worker()
        worker_ref = weakref.ref(worker)

        capture = SignalCapture()
        worker.work_signal.connect(capture.capture)

        # Run worker
        worker.start()

        # Wait for worker and process events to receive the signal
        timeout_ms = 1000
        start_time = time.time()
        while worker.isRunning() and (time.time() - start_time) * 1000 < timeout_ms:
            app.processEvents()
            QTest.qWait(10)

        # Process any remaining signals
        app.processEvents()
        QTest.qWait(50)
        app.processEvents()

        # Verify signal was received before cleanup
        assert len(capture.captured_signals) == 1, f"Expected 1 signal, got {len(capture.captured_signals)}"

        # Delete worker
        del worker

        # Force garbage collection
        import gc
        gc.collect()

        # Worker should be collected
        assert worker_ref() is None

        # Capture should still be valid
        assert capture is not None

class TestPerformanceImpact:
    """Test performance impact of casting approach"""

    def test_signal_delivery_performance(self, qapp):
        """Test signal delivery performance across threads"""
        import statistics

        manager = ExtractionManager()

        # Measure signal delivery times
        delivery_times = []

        class TimingCapture(QObject):
            def __init__(self):
                super().__init__()
                self.emit_time = None

            def on_signal(self, msg):
                if self.emit_time:
                    delivery_time = time.time() - self.emit_time
                    delivery_times.append(delivery_time)

        capture = TimingCapture()
        manager.extraction_progress.connect(capture.on_signal)

        # Emit signals and measure delivery time
        for _ in range(100):
            capture.emit_time = time.time()
            manager.extraction_progress.emit("Test")
            qapp.processEvents()
            # Use Qt-safe delay
            from PySide6.QtCore import QThread
            current_thread = QThread.currentThread()
            if current_thread:
                current_thread.msleep(1)
            else:
                time.sleep(0.001)

        # Analyze delivery times
        if delivery_times:
            avg_time = statistics.mean(delivery_times)
            max_time = max(delivery_times)

            # Signal delivery should be fast
            assert avg_time < 0.001, f"Average delivery time too high: {avg_time:.6f}s"
            assert max_time < 0.01, f"Max delivery time too high: {max_time:.6f}s"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
