"""
Tests for manager registry

NOTE: This file intentionally uses deprecated ManagerRegistry.get_*_manager() methods
to test that they still work correctly (raising proper errors when not initialized).
The deprecation warnings are suppressed since we're testing the deprecated API.
"""
from __future__ import annotations

import threading
import time
import warnings

import pytest

# Suppress deprecation warnings for get_*_manager methods we're intentionally testing
warnings.filterwarnings(
    "ignore",
    message=r"ManagerRegistry\.get_\w+_manager\(\) is deprecated",
    category=DeprecationWarning,
)

from core.di_container import reset_container
from core.managers import (
    # Serial execution required: Thread safety concerns
    ManagerError,
    cleanup_managers,
    initialize_managers,
)
from core.managers.application_state_manager import ApplicationStateManager
from core.managers.base_manager import BaseManager
from core.managers.core_operations_manager import CoreOperationsManager
from core.managers import ManagerRegistry


def are_managers_initialized() -> bool:
    """Check if managers are initialized."""
    return ManagerRegistry().is_initialized()


def get_session_manager():
    """Get session manager via DI.

    Wraps inject() to raise ManagerError for compatibility with tests
    that expect the old API's error semantics.
    """
    from core.di_container import inject
    from core.managers.application_state_manager import ApplicationStateManager
    try:
        return inject(ApplicationStateManager)
    except ValueError as e:
        raise ManagerError("SessionManager not initialized") from e


def get_extraction_manager():
    """Get extraction manager via DI.

    Wraps inject() to raise ManagerError for compatibility with tests
    that expect the old API's error semantics.
    """
    from core.di_container import inject
    try:
        return inject(CoreOperationsManager)
    except ValueError as e:
        raise ManagerError("ExtractionManager not initialized") from e

pytestmark = [
    pytest.mark.headless,
    pytest.mark.allows_registry_state(reason="Tests ManagerRegistry lifecycle"),
]
class TestManagerRegistry:
    """Test ManagerRegistry functionality"""

    @pytest.fixture(autouse=True)
    def cleanup_registry(self, clean_registry_state):
        """Ensure clean registry state for each test."""
        yield

    def test_singleton_pattern(self):
        """Test that registry is a singleton"""
        registry1 = ManagerRegistry()
        registry2 = ManagerRegistry()
        registry3 = ManagerRegistry()

        assert registry1 is registry2
        assert registry2 is registry3

    def test_managers_not_initialized_after_cleanup(self):
        """Test managers are not initialized after cleanup.

        Note: This test requires exclusive control of the manager registry state.
        When session_managers is active, the cleanup_registry fixture skips cleanup
        to avoid breaking other tests, so this test cannot run.
        """
        # The cleanup_registry fixture should have cleaned up before this test
        # Verify we're in an uninitialized state
        assert not are_managers_initialized(), (
            "Managers should be uninitialized after cleanup_registry fixture runs"
        )

        with pytest.raises(ManagerError, match="SessionManager not initialized"):
            get_session_manager()

        with pytest.raises(ManagerError, match="ExtractionManager not initialized"):
            get_extraction_manager()

    def test_cleanup_managers(self):
        """Test cleaning up managers"""
        # Initialize first
        initialize_managers()
        assert are_managers_initialized()

        # Cleanup
        cleanup_managers()
        assert not are_managers_initialized()

        # Should not be able to get managers after cleanup
        with pytest.raises(ManagerError):
            get_session_manager()

    def test_get_all_managers(self):
        """Test getting all managers"""
        registry = ManagerRegistry()

        # Initially empty
        assert registry.get_all_managers() == {}

        # After initialization
        initialize_managers()
        all_managers = registry.get_all_managers()

        # Keys are now class names (DI container is single source of truth)
        assert "ApplicationStateManager" in all_managers
        assert "CoreOperationsManager" in all_managers
        # Consolidated architecture: state returns ApplicationStateManager
        assert isinstance(all_managers["ApplicationStateManager"], ApplicationStateManager)
        # Consolidated architecture: CoreOperationsManager handles extraction and injection
        assert isinstance(all_managers["CoreOperationsManager"], CoreOperationsManager)

    def test_double_initialization(self):
        """Test that double initialization doesn't create new instances"""
        # First initialization
        initialize_managers()
        session_mgr1 = get_session_manager()
        extraction_mgr1 = get_extraction_manager()

        # Second initialization
        initialize_managers()
        session_mgr2 = get_session_manager()
        extraction_mgr2 = get_extraction_manager()

        # Should be the same instances
        assert session_mgr1 is session_mgr2
        assert extraction_mgr1 is extraction_mgr2

    def test_manager_type_checking(self):
        """Test that registry raises appropriate error when managers not initialized"""
        # Ensure clean state - managers not initialized
        if are_managers_initialized():
            cleanup_managers()

        # Verify that getting a manager without initialization raises ManagerError
        with pytest.raises(ManagerError, match="not initialized"):
            get_session_manager()

    def test_concurrent_access(self):
        """Test thread-safe access to registry"""
        import threading

        # Ensure clean state before test
        if are_managers_initialized():
            cleanup_managers()

        results = []
        errors = []
        barrier = threading.Barrier(10)  # Synchronize thread start
        results_lock = threading.Lock()  # Protect shared lists

        def access_registry():
            try:
                # Wait for all threads to be ready
                barrier.wait()

                # Try to initialize
                initialize_managers()

                # Get managers
                session = get_session_manager()
                extraction = get_extraction_manager()

                # Store results with lock
                with results_lock:
                    results.append((session, extraction))
            except Exception as e:
                with results_lock:
                    errors.append(e)

        # Create multiple threads
        threads = []
        for _ in range(10):
            t = threading.Thread(target=access_registry)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # All threads should get the same manager instances
        if results:
            first_session, first_extraction = results[0]
            for i, (session, extraction) in enumerate(results[1:], 1):
                assert session is first_session, f"Result {i} session differs"
                assert extraction is first_extraction, f"Result {i} extraction differs"

    def test_qt_cleanup_registration_with_qapplication(self, qtbot):
        """Test that cleanup hooks are registered when QApplication is available."""
        from PySide6.QtWidgets import QApplication

        # Ensure we have a QApplication (qtbot provides one)
        app = QApplication.instance()
        assert app is not None

        # Reset both module-level and class-level flags for clean test
        import core.managers as managers_module
        managers_module._cleanup_registered = False
        ManagerRegistry._cleanup_registered = False

        # Initialize managers - should register with aboutToQuit
        initialize_managers()

        # Verify cleanup was registered
        assert ManagerRegistry._cleanup_registered

    def test_atexit_cleanup_fallback(self):
        """Test that atexit cleanup works when QApplication is not available."""
        from unittest.mock import patch

        from core.managers import cleanup_managers as _cleanup_global_registry

        # Reset state - both module and class level
        import core.managers as managers_module
        managers_module._cleanup_registered = False
        ManagerRegistry._cleanup_registered = False

        # Mock QApplication.instance() to return None
        # The import is from PySide6.QtWidgets inside initialize_managers
        with patch("PySide6.QtWidgets.QApplication") as mock_qapp:
            mock_qapp.instance.return_value = None

            # Initialize managers without Qt
            initialize_managers()

            # Verify Qt cleanup was NOT registered (no app available)
            assert not ManagerRegistry._cleanup_registered

        # Verify managers are initialized
        assert are_managers_initialized()

        # Call atexit handler directly
        _cleanup_global_registry()

        # Verify cleanup happened
        assert not are_managers_initialized()

    def test_cleanup_managers_idempotent(self):
        """Test that calling cleanup_managers multiple times is safe."""
        # Initialize first
        initialize_managers()
        assert are_managers_initialized()

        # First cleanup
        cleanup_managers()
        assert not are_managers_initialized()

        # Second cleanup should not raise
        cleanup_managers()  # Should be a no-op
        assert not are_managers_initialized()

        # Third cleanup also safe
        cleanup_managers()
        assert not are_managers_initialized()


@pytest.mark.usefixtures("isolated_managers")
@pytest.mark.skip_thread_cleanup(reason="Uses isolated_managers which owns worker threads")
@pytest.mark.allows_registry_state(reason="Tests ManagerRegistry lifecycle")
class TestTOCTOURaceConditionStability:
    """Test fixes for Time-of-Check-Time-of-Use race conditions.

    Migrated from test_phase1_stability_fixes.py - validates Phase 1 stability fixes
    for TOCTOU race conditions in manager initialization and concurrent access.
    """

    def test_manager_registry_thread_safety(self):
        """Test ManagerRegistry handles concurrent access safely."""

        errors = []
        registries = []
        lock = threading.Lock()

        def create_registry():
            try:
                registry = ManagerRegistry()
                with lock:
                    registries.append(registry)
            except Exception as e:
                with lock:
                    errors.append(e)

        # Create multiple threads trying to create registry
        threads = []
        for _i in range(10):
            thread = threading.Thread(target=create_registry)
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify no errors occurred
        assert not errors, f"Registry creation should be thread-safe, but got errors: {errors}"

        # Verify all registries are the same instance (singleton)
        assert len(registries) == 10, "Should have 10 registry references"
        first_registry = registries[0]
        for registry in registries[1:]:
            assert registry is first_registry, "All registries should be the same instance"

    def test_manager_concurrent_operations(self):
        """Test managers handle concurrent operations safely."""

        class TestManager(BaseManager):
            def __init__(self):
                super().__init__("test_concurrent")
                self.operation_count = 0
                self.operation_results = []

            def _initialize(self):
                self._is_initialized = True

            def cleanup(self):
                pass

            def test_operation(self, operation_id):
                """Thread-safe operation using manager's built-in locking."""
                def _do_operation():
                    # Simulate work
                    time.sleep(0.01)  # sleep-ok: race condition test
                    self.operation_count += 1
                    self.operation_results.append(f"operation_{operation_id}")
                    return f"result_{operation_id}"

                return self._with_operation_lock(f"test_op_{operation_id}", _do_operation)

        manager = TestManager()
        results = []
        errors = []
        lock = threading.Lock()

        def run_operation(op_id):
            try:
                result = manager.test_operation(op_id)
                with lock:
                    results.append(result)
            except Exception as e:
                with lock:
                    errors.append(e)

        # Run concurrent operations
        threads = []
        for i in range(20):
            thread = threading.Thread(target=run_operation, args=(i,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify results
        assert not errors, f"Concurrent operations should not cause errors: {errors}"
        assert len(results) == 20, f"Should have 20 results, got {len(results)}"
        assert manager.operation_count == 20, f"Should have 20 operations, got {manager.operation_count}"

    def test_manager_initialization_race_conditions(self):
        """Test manager initialization is safe under concurrent access."""
        # This test requires exclusive control of manager initialization
        # With isolated_managers, each test has its own managers, so this is safe

        # Skip this test in mock environment where Qt objects can't be created properly
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and "Mock" in app.__class__.__name__:
            pytest.skip("Skipping manager initialization test in mock environment")

        # Get fresh registry for clean test
        registry = ManagerRegistry()

        errors = []
        lock = threading.Lock()

        def initialize_managers_thread():
            try:
                # This should be safe to call from multiple threads
                registry.initialize_managers("TestApp")
            except Exception as e:
                with lock:
                    errors.append(e)

        # Try to initialize from multiple threads
        threads = []
        for _i in range(5):
            thread = threading.Thread(target=initialize_managers_thread)
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify no errors occurred
        assert not errors, f"Concurrent initialization should be safe: {errors}"

    def test_manager_validity_during_operations(self):
        """Test that managers remain valid during long operations."""

        class TestManager(BaseManager):
            def __init__(self):
                super().__init__("test_validity")

            def _initialize(self):
                self._is_initialized = True

            def cleanup(self):
                pass

            def long_operation(self):
                """Simulate a long operation that checks manager validity."""
                if not self._start_operation("long_op"):
                    return False

                try:
                    # Simulate work while checking validity
                    for _i in range(50):
                        if not self.is_initialized():
                            return False
                        time.sleep(0.001)  # sleep-ok: race condition test
                    return True
                finally:
                    self._finish_operation("long_op")

        manager = TestManager()

        # Start long operation in background
        result_container = [None]
        error_container = [None]

        def run_long_operation():
            try:
                result_container[0] = manager.long_operation()
            except Exception as e:
                error_container[0] = e

        thread = threading.Thread(target=run_long_operation)
        thread.start()

        # While operation is running, verify manager state
        time.sleep(0.01)  # sleep-ok: thread interleaving
        assert manager.has_active_operations(), "Manager should have active operations"
        assert manager.is_operation_active("long_op"), "Specific operation should be active"

        # Wait for completion
        thread.join()

        # Verify results
        assert error_container[0] is None, f"Long operation should not error: {error_container[0]}"
        assert result_container[0] is True, "Long operation should succeed"
        assert not manager.has_active_operations(), "Manager should have no active operations after completion"
