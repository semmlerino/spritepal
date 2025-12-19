"""
Test thread safety of the error handler singleton pattern.

Tests the double-check locking implementation and concurrent access scenarios
to ensure the singleton pattern works correctly under concurrent load.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from PySide6.QtWidgets import QWidget

from ui.common import get_error_handler, reset_error_handler

# Serial execution required: Thread safety concerns
pytestmark = [pytest.mark.headless]

class TestErrorHandlerThreadSafety:
    """Test thread safety of error handler singleton"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset error handler before each test"""
        reset_error_handler()
        yield
        reset_error_handler()

    def test_singleton_thread_safety(self, qtbot):
        """Test that get_error_handler returns same instance across threads"""
        instances = []
        errors = []

        def get_handler_instance():
            """Thread worker to get error handler instance"""
            try:
                handler = get_error_handler()
                instances.append(handler)
                return handler
            except Exception as e:
                errors.append(e)
                return None

        # Launch multiple threads concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_handler_instance) for _ in range(20)]
            [future.result() for future in as_completed(futures)]

        # Verify no errors occurred
        assert not errors, f"Errors in threads: {errors}"

        # Verify all instances are the same object
        assert len(instances) == 20, "Not all threads returned an instance"
        first_instance = instances[0]
        assert all(instance is first_instance for instance in instances), \
            "Thread safety failed: got different instances"

    def test_parent_widget_assignment_thread_safety(self, qtbot):
        """Test thread-safe parent widget assignment in double-check locking"""
        parent1 = QWidget()
        parent2 = QWidget()
        qtbot.addWidget(parent1)
        qtbot.addWidget(parent2)

        assigned_parents = []
        errors = []

        def assign_parent(parent):
            """Thread worker to assign parent to error handler"""
            try:
                handler = get_error_handler(parent)
                assigned_parents.append(handler._parent_widget)
                return handler._parent_widget
            except Exception as e:
                errors.append(e)
                return None

        # First thread assigns parent1, second assigns parent2
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(assign_parent, parent1),
                executor.submit(assign_parent, parent2)
            ]
            [future.result() for future in as_completed(futures)]

        # Verify no errors occurred
        assert not errors, f"Errors in threads: {errors}"

        # The first parent to be assigned should win (due to double-check locking)
        handler = get_error_handler()
        assert handler._parent_widget in [parent1, parent2], \
            "Parent widget not assigned correctly"

        # All subsequent calls should return same parent
        final_parent = handler._parent_widget
        assert all(parent is final_parent for parent in assigned_parents), \
            "Parent assignment not consistent across threads"

    def test_concurrent_singleton_creation_race_condition(self):
        """Test race condition handling in singleton creation"""
        creation_order = []
        errors = []

        def create_singleton_with_delay(delay_ms):
            """Create singleton with artificial delay to increase race condition probability"""
            try:
                # Add small delay to increase chance of race condition
                time.sleep(delay_ms / 1000.0)  # sleep-ok: race condition test
                handler = get_error_handler()
                creation_order.append(threading.current_thread().ident)
                return handler
            except Exception as e:
                errors.append(e)
                return None

        # Create many threads with different delays
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = [
                executor.submit(create_singleton_with_delay, i % 5)
                for i in range(30)
            ]
            handlers = [future.result() for future in as_completed(futures)]

        # Verify no errors occurred
        assert not errors, f"Race condition caused errors: {errors}"

        # Verify all handlers are the same instance
        first_handler = handlers[0]
        assert all(handler is first_handler for handler in handlers), \
            "Race condition created multiple singleton instances"

        # Verify creation order was tracked (shows threads executed)
        assert len(creation_order) == 30, "Not all threads completed"

    def test_fast_path_optimization(self):
        """Test that fast path (no lock) optimization works correctly"""
        # First call creates singleton
        handler1 = get_error_handler()

        # Track lock acquisition by patching the singleton's lock
        from ui.common.error_handler import _ErrorHandlerSingleton
        original_lock = _ErrorHandlerSingleton._lock
        lock_calls = []

        # Create a mock lock that tracks acquisitions
        class TrackingLock:
            def __init__(self):
                self._real_lock = threading.Lock()

            def __enter__(self):
                lock_calls.append(threading.current_thread().ident)
                return self._real_lock.__enter__()

            def __exit__(self, *args):
                return self._real_lock.__exit__(*args)

            def acquire(self, blocking=True, timeout=-1):
                lock_calls.append(threading.current_thread().ident)
                return self._real_lock.acquire(blocking, timeout)

            def release(self):
                return self._real_lock.release()

        # Replace the singleton's lock
        _ErrorHandlerSingleton._lock = TrackingLock()

        try:
            # Subsequent calls should use fast path (no lock)
            for _ in range(5):
                handler = get_error_handler()
                assert handler is handler1, "Fast path failed to return same instance"

            # Fast path should not acquire locks
            assert len(lock_calls) == 0, \
                f"Fast path acquired locks unnecessarily: {len(lock_calls)} times"

        finally:
            # Restore original lock
            _ErrorHandlerSingleton._lock = original_lock

    def test_parent_update_after_creation(self, qtbot):
        """Test parent widget update after singleton creation"""
        # Create singleton without parent
        handler = get_error_handler()
        assert handler._parent_widget is None

        # Create parent widget
        parent = QWidget()
        qtbot.addWidget(parent)

        # Update with parent should work
        handler_with_parent = get_error_handler(parent)
        assert handler_with_parent is handler, "Should return same singleton"
        assert handler._parent_widget is parent, "Parent should be updated"

        # Second parent should not override
        parent2 = QWidget()
        qtbot.addWidget(parent2)
        handler_with_parent2 = get_error_handler(parent2)
        assert handler_with_parent2 is handler, "Should return same singleton"
        assert handler._parent_widget is parent, "Original parent should be preserved"

    def test_exception_in_thread_during_singleton_access(self):
        """Test error handler behavior when exceptions occur during threading"""
        errors = []
        handlers = []

        def access_with_exception():
            """Access error handler and then raise exception"""
            try:
                handler = get_error_handler()
                handlers.append(handler)
                # Simulate some work that might fail
                if threading.current_thread().ident % 2 == 0:
                    raise ValueError("Simulated thread error")
                return handler
            except Exception as e:
                errors.append(e)
                return None

        # Run multiple threads, some will raise exceptions
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(access_with_exception) for _ in range(16)]
            [future.result() for future in as_completed(futures)]

        # Should have some ValueError exceptions from our simulation
        value_errors = [e for e in errors if isinstance(e, ValueError)]
        assert len(value_errors) > 0, "Expected some simulated errors"

        # But all successful handlers should be the same instance
        successful_handlers = [h for h in handlers if h is not None]
        assert len(successful_handlers) > 0, "Expected some successful handlers"
        first_handler = successful_handlers[0]
        assert all(h is first_handler for h in successful_handlers), \
            "All handlers should be same instance despite thread exceptions"
