"""
Tests for BaseManager abstract class
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QTimer

from core.managers import BaseManager, ValidationError
from tests.fixtures.timeouts import signal_timeout

# Test characteristics: Real GUI components requiring display, Timer usage
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.gui,
    pytest.mark.integration,
    pytest.mark.qt_app,
    pytest.mark.qt_real,
    pytest.mark.rom_data,
    pytest.mark.serial,
    pytest.mark.slow,
    pytest.mark.worker_threads,
    pytest.mark.signals_slots,
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

class TestBaseManager:
    """Test BaseManager functionality"""

    def test_abstract_class_cannot_be_instantiated(self):
        """Test that BaseManager cannot be instantiated directly"""
        with pytest.raises(NotImplementedError, match="Subclasses must implement _initialize"):
            BaseManager("test")

    def test_concrete_manager_creation(self):
        """Test creating a concrete manager"""
        manager = ConcreteManager("TestManager")
        assert manager.get_name() == "TestManager"
        assert manager.is_initialized()

    def test_default_name(self):
        """Test manager with default name"""
        manager = ConcreteManager()
        assert manager.get_name() == "ConcreteManager"

    def test_operation_tracking(self):
        """Test operation tracking"""
        manager = ConcreteManager()

        # No operations initially
        assert not manager.has_active_operations()
        assert not manager.is_operation_active("test_op")

        # Start operation
        assert manager._start_operation("test_op")
        assert manager.has_active_operations()
        assert manager.is_operation_active("test_op")

        # Can't start same operation twice
        assert not manager._start_operation("test_op")

        # Finish operation
        manager._finish_operation("test_op")
        assert not manager.has_active_operations()
        assert not manager.is_operation_active("test_op")

    def test_validation_required(self):
        """Test required parameter validation"""
        manager = ConcreteManager()

        # All required present
        manager._validate_required(
            {"a": 1, "b": "test", "c": None},
            ["a", "b"]
        )

        # Missing required
        with pytest.raises(ValidationError, match="Missing required parameters: b, c"):
            manager._validate_required(
                {"a": 1},
                ["a", "b", "c"]
            )

    def test_validation_type(self):
        """Test type validation"""
        manager = ConcreteManager()

        # Correct type
        manager._validate_type("test", "param", str)
        manager._validate_type(123, "param", int)
        manager._validate_type([1, 2], "param", list)

        # Wrong type
        with pytest.raises(ValidationError, match="Invalid type for 'param'"):
            manager._validate_type("test", "param", int)

    def test_validation_file_exists(self, tmp_path):
        """Test file existence validation"""
        manager = ConcreteManager()

        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        # Existing file
        manager._validate_file_exists(str(test_file), "test file")

        # Non-existing file
        with pytest.raises(ValidationError, match="test file does not exist"):
            manager._validate_file_exists(str(tmp_path / "missing.txt"), "test file")

    def test_validation_range(self):
        """Test range validation"""
        manager = ConcreteManager()

        # Within range
        manager._validate_range(5, "value", min_val=0, max_val=10)
        manager._validate_range(0, "value", min_val=0)
        manager._validate_range(10, "value", max_val=10)

        # Out of range
        with pytest.raises(ValidationError, match="value must be >= 0"):
            manager._validate_range(-1, "value", min_val=0)

        with pytest.raises(ValidationError, match="value must be <= 10"):
            manager._validate_range(11, "value", max_val=10)

    @pytest.mark.qt_no_exception_capture
    def test_signal_emission(self, qtbot):
        """Test signal emission"""
        manager = ConcreteManager()

        # Test error signal with timeout to prevent hanging
        with qtbot.waitSignal(manager.error_occurred, timeout=signal_timeout()) as blocker:
            # Use QTimer.singleShot to ensure signal is emitted in next event loop iteration
            QTimer.singleShot(0, lambda: manager._handle_error(Exception("Test error")))
        assert "Test error" in blocker.args[0]

        # Test warning signal with timeout
        with qtbot.waitSignal(manager.warning_occurred, timeout=signal_timeout()) as blocker:
            QTimer.singleShot(0, lambda: manager._handle_warning("Test warning"))
        assert blocker.args[0] == "Test warning"

        # Test progress signal with timeout
        with qtbot.waitSignal(manager.progress_updated, timeout=signal_timeout()) as blocker:
            QTimer.singleShot(0, lambda: manager._update_progress("test_op", 50, 100))
        assert blocker.args == ["test_op", 50, 100]

    def test_operation_lock(self):
        """Test operation-specific locking"""
        manager = ConcreteManager()

        counter = 0

        def increment():
            nonlocal counter
            counter += 1
            return counter

        # Run with lock
        result = manager._with_operation_lock("test_op", increment)
        assert result == 1
        assert counter == 1

        # Run again with same lock
        result = manager._with_operation_lock("test_op", increment)
        assert result == 2
        assert counter == 2

    @pytest.mark.qt_no_exception_capture
    def test_error_handling_with_operation(self, qtbot):
        """Test error handling with active operation"""
        manager = ConcreteManager()

        # Start an operation
        manager._start_operation("test_op")
        assert manager.is_operation_active("test_op")

        # Handle error for that operation with timeout to prevent hanging
        with qtbot.waitSignal(manager.error_occurred, timeout=signal_timeout()) as blocker:
            QTimer.singleShot(0, lambda: manager._handle_error(Exception("Operation failed"), "test_op"))

        # Operation should be finished
        assert not manager.is_operation_active("test_op")
        assert "test_op: Operation failed" in blocker.args[0]
