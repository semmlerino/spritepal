"""
Test suite for thread-safe singleton implementations.

Tests the thread safety of singleton patterns with concurrent access,
Qt thread affinity checking, and proper cleanup.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from core.thread_safe_singleton import (
    # Serial execution required: QApplication management, Thread safety concerns
    LazyThreadSafeSingleton,
    QtThreadSafeSingleton,
    ThreadSafeSingleton,
    create_qt_singleton,
    create_simple_singleton,
)

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Thread tests may intentionally leave threads running"),
    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.thread_safety,
    pytest.mark.ci_safe,
    pytest.mark.dialog,
    pytest.mark.gui,
    pytest.mark.requires_display,
    pytest.mark.worker_threads,
]
class MockClass:
    """Mock class for testing singleton patterns."""

    def __init__(self, value: str = "test"):
        self.value = value
        self.creation_thread = threading.current_thread().name
        self.creation_time = time.time()

    def get_value(self) -> str:
        return self.value

class MockQtClass(QWidget):
    """Mock Qt class for testing Qt singleton patterns."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.creation_thread = threading.current_thread().name
        self.creation_time = time.time()
        self.test_value = "qt_test"

class TestThreadSafeSingleton:
    """Test basic thread-safe singleton functionality."""

    def setup_method(self):
        """Reset singleton state before each test."""
        # Each test defines its own singleton class, so no global reset needed

    def test_basic_singleton_creation(self):
        """Test basic singleton instance creation."""

        class TestSingleton(ThreadSafeSingleton[MockClass]):
            _instance: MockClass | None = None
            _lock = threading.Lock()

            @classmethod
            def _create_instance(cls, value: str = "test") -> MockClass:
                return MockClass(value)

        # First call should create instance
        instance1 = TestSingleton.get("value1")
        assert instance1.value == "value1"

        # Second call should return same instance
        instance2 = TestSingleton.get("value2")
        assert instance1 is instance2
        assert instance2.value == "value1"  # Original value preserved

    def test_concurrent_singleton_creation(self):
        """Test thread safety with concurrent access."""

        class TestSingleton(ThreadSafeSingleton[MockClass]):
            _instance: MockClass | None = None
            _lock = threading.Lock()

            @classmethod
            def _create_instance(cls, value: str = "test") -> MockClass:
                # Add small delay to increase chance of race condition
                time.sleep(0.01)  # sleep-ok: race condition test
                return MockClass(value)

        instances = []
        num_threads = 10

        def create_instance(thread_id: int):
            instance = TestSingleton.get(f"thread_{thread_id}")
            instances.append(instance)
            return instance

        # Use ThreadPoolExecutor to create concurrent access
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(create_instance, i) for i in range(num_threads)]
            [future.result() for future in as_completed(futures)]

        # All instances should be the same object
        assert len(instances) == num_threads
        first_instance = instances[0]
        for instance in instances:
            assert instance is first_instance

        # Should only have one instance created
        assert TestSingleton.is_initialized()

    def test_singleton_reset(self):
        """Test singleton reset functionality."""

        class TestSingleton(ThreadSafeSingleton[MockClass]):
            _instance: MockClass | None = None
            _lock = threading.Lock()

            @classmethod
            def _create_instance(cls) -> MockClass:
                return MockClass("reset_test")

        # Create instance
        instance1 = TestSingleton.get()
        assert TestSingleton.is_initialized()

        # Reset singleton
        TestSingleton.reset()
        assert not TestSingleton.is_initialized()

        # Create new instance
        instance2 = TestSingleton.get()
        assert instance1 is not instance2
        assert TestSingleton.is_initialized()

class TestQtThreadSafeSingleton:
    """Test Qt-specific thread-safe singleton functionality."""

    def setup_method(self):
        """Setup Qt application if not present."""
        if QApplication.instance() is None:
            self.app = QApplication([])
        else:
            self.app = QApplication.instance()

    def test_qt_singleton_main_thread_creation(self):
        """Test Qt singleton creation on main thread."""

        class TestQtSingleton(QtThreadSafeSingleton[MockQtClass]):
            _instance: MockQtClass | None = None
            _lock = threading.Lock()

            @classmethod
            def _create_instance(cls) -> MockQtClass:
                cls._ensure_main_thread()
                return MockQtClass()

        # Should work on main thread
        instance = TestQtSingleton.get()
        assert isinstance(instance, MockQtClass)
        assert instance.creation_thread == threading.current_thread().name

    def test_qt_singleton_wrong_thread_creation(self):
        """Test Qt singleton creation fails on wrong thread."""

        class TestQtSingleton(QtThreadSafeSingleton[MockQtClass]):
            _instance: MockQtClass | None = None
            _lock = threading.Lock()

            @classmethod
            def _create_instance(cls) -> MockQtClass:
                cls._ensure_main_thread()
                return MockQtClass()

        exception_caught = threading.Event()

        def worker_thread():
            try:
                TestQtSingleton.get()
                # Should not reach here
                raise AssertionError("Expected RuntimeError was not raised")
            except RuntimeError as e:
                assert "Qt object method called from wrong thread" in str(e)
                exception_caught.set()

        thread = threading.Thread(target=worker_thread)
        thread.start()
        thread.join()

        assert exception_caught.is_set()

    def test_safe_qt_call(self):
        """Test safe Qt method calling."""

        class TestQtSingleton(QtThreadSafeSingleton[MockQtClass]):
            _instance: MockQtClass | None = None
            _lock = threading.Lock()

            @classmethod
            def _create_instance(cls) -> MockQtClass:
                cls._ensure_main_thread()
                return MockQtClass()

        # Create instance on main thread
        instance = TestQtSingleton.get()

        # Test safe call on main thread
        result = TestQtSingleton.safe_qt_call(lambda: instance.isVisible())
        assert result is False  # Widget not shown yet

        # Test safe call from worker thread
        worker_result = []

        def worker_thread():
            result = TestQtSingleton.safe_qt_call(lambda: instance.isVisible())
            worker_result.append(result)

        thread = threading.Thread(target=worker_thread)
        thread.start()
        thread.join()

        # Should return None from worker thread (safe failure)
        assert worker_result[0] is None

class TestLazyThreadSafeSingleton:
    """Test lazy initialization singleton functionality."""

    def test_lazy_initialization(self):
        """Test lazy initialization behavior."""

        class TestLazySingleton(LazyThreadSafeSingleton[MockClass]):
            _instance: MockClass | None = None
            _lock = threading.Lock()
            _initialization_lock = threading.Lock()
            _initialized = False

            @classmethod
            def _create_instance(cls, value: str = "lazy") -> MockClass:
                return MockClass(value)

        # Should not be initialized initially
        assert not TestLazySingleton.is_initialized()
        assert TestLazySingleton.get_if_initialized() is None

        # Initialize explicitly
        instance = TestLazySingleton.initialize("initialized")
        assert TestLazySingleton.is_initialized()
        assert TestLazySingleton.get_if_initialized() is instance

        # Subsequent get should return same instance
        same_instance = TestLazySingleton.get("different")
        assert same_instance is instance
        assert same_instance.value == "initialized"  # Original value preserved

class TestSingletonFactories:
    """Test singleton factory functions."""

    def test_create_simple_singleton(self):
        """Test simple singleton factory."""

        MockSingleton = create_simple_singleton(MockClass)

        instance1 = MockSingleton.get("factory_test")
        instance2 = MockSingleton.get("different")

        assert instance1 is instance2
        assert instance1.value == "factory_test"
        assert MockSingleton.__name__ == "MockClassSingleton"

    def test_create_qt_singleton(self):
        """Test Qt singleton factory."""
        if QApplication.instance() is None:
            QApplication([])

        MockQtSingleton = create_qt_singleton(MockQtClass)

        instance1 = MockQtSingleton.get()
        instance2 = MockQtSingleton.get()

        assert instance1 is instance2
        assert isinstance(instance1, MockQtClass)
        assert MockQtSingleton.__name__ == "MockQtClassSingleton"

class TestRealWorldScenarios:
    """Test realistic usage scenarios."""

    def test_high_concurrency_stress_test(self):
        """Stress test with high concurrency."""

        class StressSingleton(ThreadSafeSingleton[MockClass]):
            _instance: MockClass | None = None
            _lock = threading.Lock()

            @classmethod
            def _create_instance(cls) -> MockClass:
                # Simulate some work during creation
                time.sleep(0.001)  # sleep-ok: race condition test
                return MockClass("stress_test")

        num_threads = 50
        num_calls_per_thread = 10
        all_instances = []

        def worker(worker_id: int):
            instances = []
            for _i in range(num_calls_per_thread):
                instance = StressSingleton.get()
                instances.append(instance)
                time.sleep(0.001)  # sleep-ok: thread interleaving
            return instances

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]

            for future in as_completed(futures):
                all_instances.extend(future.result())

        # All instances should be the same object
        first_instance = all_instances[0]
        for instance in all_instances:
            assert instance is first_instance

        assert len(all_instances) == num_threads * num_calls_per_thread

    def test_singleton_with_cleanup(self):
        """Test singleton with proper cleanup."""

        cleanup_called = threading.Event()

        class CleanupSingleton(ThreadSafeSingleton[MockClass]):
            _instance: MockClass | None = None
            _lock = threading.Lock()

            @classmethod
            def _create_instance(cls) -> MockClass:
                return MockClass("cleanup_test")

            @classmethod
            def _cleanup_instance(cls, instance: MockClass) -> None:
                cleanup_called.set()

        # Create and use instance
        instance = CleanupSingleton.get()
        assert instance.value == "cleanup_test"

        # Reset should trigger cleanup
        CleanupSingleton.reset()
        assert cleanup_called.is_set()
        assert not CleanupSingleton.is_initialized()

# Integration tests with real singleton classes

class TestManualOffsetDialogSingletonIntegration:
    """Integration tests for the fixed ManualOffsetDialogSingleton."""

    @pytest.mark.integration
    def test_dialog_singleton_thread_safety(self):
        """Test that ManualOffsetDialogSingleton is thread-safe."""
        from ui.rom_extraction_panel import ManualOffsetDialogSingleton

        # Reset singleton state
        ManualOffsetDialogSingleton.reset()

        # Test that accessing from worker thread doesn't crash
        worker_result = []

        def worker_thread():
            try:
                # This should not crash, but should handle thread safety
                is_open = ManualOffsetDialogSingleton.is_dialog_open()
                worker_result.append(("success", is_open))
            except Exception as e:
                worker_result.append(("error", str(e)))

        thread = threading.Thread(target=worker_thread)
        thread.start()
        thread.join()

        assert len(worker_result) == 1
        result_type, result_value = worker_result[0]

        # Should either succeed safely or handle the error gracefully
        if result_type == "success":
            assert isinstance(result_value, bool)
        else:
            # Should be a controlled error, not a crash
            assert "thread" in result_value.lower()

@pytest.mark.usefixtures("class_managers")
class TestSettingsManagerSingletonIntegration:
    """Integration tests for the fixed SettingsManagerSingleton."""

    @pytest.mark.integration
    def test_settings_manager_thread_safety(self):
        """Test that SettingsManagerSingleton is thread-safe."""
        from core.di_container import inject
        from core.protocols.manager_protocols import SettingsManagerProtocol

        instances = []

        def worker_thread(thread_id: int):
            # Use DI injection (replaces deprecated get_settings_manager)
            manager = inject(SettingsManagerProtocol)
            instances.append((thread_id, manager))
            return manager

        # Create multiple threads accessing settings manager
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_thread, i) for i in range(5)]
            results = [future.result() for future in as_completed(futures)]

        # All should be the same instance
        first_manager = results[0]
        for manager in results:
            assert manager is first_manager

        # All instances collected should be the same
        first_instance = instances[0][1]
        for _thread_id, instance in instances:
            assert instance is first_instance

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
