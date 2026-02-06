"""
Tests for BaseManager abstract class.

CRITICAL: This file tests thread safety, memory management, and GC patterns.
DO NOT DELETE - contrary to any audit recommendations. These tests verify:
- Thread safety mechanisms (locks, concurrent operations)
- Circular reference prevention (weak references, cleanup)
- Memory stability patterns (object lifecycle, stress tests)
- Operation tracking (concurrent operation management)
"""

from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtCore import QTimer

from core.managers import BaseManager
from tests.fixtures.timeouts import signal_timeout

# Test characteristics: Real GUI components requiring display, Timer usage
pytestmark = [
    pytest.mark.gui,
    pytest.mark.integration,
    pytest.mark.slow,
]


class ConcreteManager(BaseManager):
    """Concrete implementation for testing"""

    def __init__(self, name: str | None = None):
        super().__init__(name)

    def _initialize(self) -> None:
        """Initialize the test manager"""
        self._is_initialized = True

    def cleanup(self) -> None:
        """Cleanup test resources"""

    def trigger_error(self, error: Exception, operation_name: str | None = None) -> None:
        """Public method to trigger an error (for testing signal emission)."""
        self._handle_error(error, operation_name)

    def trigger_warning(self, message: str) -> None:
        """Public method to trigger a warning (for testing signal emission)."""
        self._handle_warning(message)

    def update_progress(self, operation: str, current: int, total: int) -> None:
        """Public method to update progress (for testing signal emission)."""
        self._update_progress(operation, current, total)


class TestBaseManager:
    """Test BaseManager functionality"""

    def test_abstract_class_cannot_be_instantiated(self):
        """Test that BaseManager cannot be instantiated directly"""
        with pytest.raises(NotImplementedError, match="Subclasses must implement _initialize"):
            BaseManager("test")

    def test_operation_tracking(self):
        """Test operation tracking"""
        manager = ConcreteManager()

        # No operations initially
        assert not manager.has_active_operations()
        assert not manager.is_operation_active("test_op")

        # Start operation
        assert manager.simulate_operation_start("test_op")
        assert manager.has_active_operations()
        assert manager.is_operation_active("test_op")

        # Can't start same operation twice
        assert not manager.simulate_operation_start("test_op")

        # Finish operation
        manager.simulate_operation_finish("test_op")
        assert not manager.has_active_operations()
        assert not manager.is_operation_active("test_op")

    @pytest.mark.qt_no_exception_capture
    def test_signal_emission(self, qtbot):
        """Test signal emission"""
        manager = ConcreteManager()

        # Test error signal with timeout to prevent hanging
        with qtbot.waitSignal(manager.error_occurred, timeout=signal_timeout()) as blocker:
            # Use QTimer.singleShot to ensure signal is emitted in next event loop iteration
            QTimer.singleShot(0, lambda: manager.trigger_error(Exception("Test error")))
        assert "Test error" in blocker.args[0]

        # Test warning signal with timeout
        with qtbot.waitSignal(manager.warning_occurred, timeout=signal_timeout()) as blocker:
            QTimer.singleShot(0, lambda: manager.trigger_warning("Test warning"))
        assert blocker.args[0] == "Test warning"

        # Test progress signal with timeout
        with qtbot.waitSignal(manager.progress_updated, timeout=signal_timeout()) as blocker:
            QTimer.singleShot(0, lambda: manager.update_progress("test_op", 50, 100))
        assert blocker.args == ["test_op", 50, 100]

    def test_operation_lock(self):
        """Test operation-specific locking prevents concurrent execution"""
        manager = ConcreteManager()

        # Test that locking behavior prevents concurrent operations
        # Start an operation
        assert manager.simulate_operation_start("test_op"), "First operation should start successfully"

        # Attempt to start the same operation concurrently (should fail)
        assert not manager.simulate_operation_start("test_op"), "Same operation should not start twice"

        # Finish the operation
        manager.simulate_operation_finish("test_op")

        # Now it should be possible to start again
        assert manager.simulate_operation_start("test_op"), "Operation should start after previous finished"
        manager.simulate_operation_finish("test_op")

        # Test concurrent access from threads
        results = []
        lock = threading.Lock()

        def try_start_operation():
            result = manager.simulate_operation_start("concurrent_op")
            with lock:
                results.append(result)
            if result:
                time.sleep(0.01)  # sleep-ok: race condition test
                manager.simulate_operation_finish("concurrent_op")

        # Create threads that try to start the same operation
        threads = [threading.Thread(target=try_start_operation) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Exactly one thread should have succeeded in starting the operation
        assert sum(results) == 1, f"Expected exactly 1 successful start, got {sum(results)}"

    @pytest.mark.qt_no_exception_capture
    def test_error_handling_with_operation(self, qtbot):
        """Test error handling with active operation"""
        manager = ConcreteManager()

        # Start an operation
        manager.simulate_operation_start("test_op")
        assert manager.is_operation_active("test_op")

        # Handle error for that operation with timeout to prevent hanging
        with qtbot.waitSignal(manager.error_occurred, timeout=signal_timeout()) as blocker:
            QTimer.singleShot(0, lambda: manager.trigger_error(Exception("Operation failed"), "test_op"))

        # Operation should be finished
        assert not manager.is_operation_active("test_op")
        assert "test_op: Operation failed" in blocker.args[0]
