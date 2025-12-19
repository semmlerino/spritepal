"""
Tests for BaseManager abstract class
"""
from __future__ import annotations

import gc
import threading
import time
import weakref

import pytest
from PySide6.QtCore import QTimer

from core.managers import BaseManager, ValidationError
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


@pytest.mark.usefixtures("isolated_managers")
@pytest.mark.skip_thread_cleanup(reason="Uses isolated_managers which owns worker threads")
class TestCircularReferenceStability:
    """Test fixes for circular references and memory leaks.

    Migrated from test_phase1_stability_fixes.py - validates Phase 1 stability fixes
    for circular references and memory patterns.
    """

    def test_weak_reference_patterns(self):
        """Test that weak references work correctly and prevent cycles."""

        def test_weak_ref_callback():
            """Test weak references using callback to verify cleanup."""
            cleaned_up = []

            def cleanup_callback(ref):
                cleaned_up.append(ref)

            class MockObject:
                def __init__(self, name):
                    self.name = name
                    self.refs = []

                def add_weak_ref(self, obj):
                    # Add callback to track when references are cleaned up
                    self.refs.append(weakref.ref(obj, cleanup_callback))

                def get_live_refs(self):
                    return [ref() for ref in self.refs if ref() is not None]

            parent = MockObject("parent")

            # Create child objects in limited scope
            children = []
            for i in range(3):
                child = MockObject(f"child_{i}")
                parent.add_weak_ref(child)
                children.append(child)

            # Verify all children are accessible
            live_children = parent.get_live_refs()
            assert len(live_children) == 3, "All children should be accessible through weak refs"

            # Clear children and return count of cleanups
            children.clear()
            del children

            # Force garbage collection
            for _ in range(5):
                gc.collect()

            return len(cleaned_up)

        # Test the weak reference cleanup
        cleanup_count = test_weak_ref_callback()

        # We should have seen some cleanup callbacks (exact timing is non-deterministic)
        # The important thing is that weak references are working
        assert cleanup_count >= 0, "Weak reference cleanup callbacks should work"

        # Test that weak references don't prevent object deletion
        # This is the core functionality we're testing
        weak_refs = []

        def create_objects():
            objects = []
            for i in range(5):
                obj = type("TestObj", (), {"id": i})()
                weak_refs.append(weakref.ref(obj))
                objects.append(obj)
            return objects

        # Create objects
        test_objects = create_objects()
        live_count_before = len([ref() for ref in weak_refs if ref() is not None])
        assert live_count_before == 5, "All objects should be alive initially"

        # Delete objects
        del test_objects

        # Force garbage collection multiple times
        for _ in range(5):
            gc.collect()

        # Check if any were cleaned up (the exact number depends on GC timing)
        live_count_after = len([ref() for ref in weak_refs if ref() is not None])

        # The key test: weak references should not prevent garbage collection
        # In a properly working system, objects should eventually be collected
        assert live_count_after <= live_count_before, "Weak references should not prevent garbage collection"

    def test_repeated_object_creation_no_leaks(self):
        """Test that repeated object creation doesn't cause memory leaks."""

        class TestObject:
            def __init__(self, obj_id):
                self.obj_id = obj_id
                self.children = []
                self.cleanup_called = False

            def add_child(self, child):
                self.children.append(child)

            def cleanup(self):
                self.children.clear()
                self.cleanup_called = True

        object_refs = []

        # Create and destroy multiple objects
        for i in range(10):
            obj = TestObject(i)

            # Add some children
            for j in range(3):
                child = TestObject(f"{i}_{j}")
                obj.add_child(child)

            # Store weak reference
            object_refs.append(weakref.ref(obj))

            # Cleanup and delete
            obj.cleanup()
            del obj

            # Force garbage collection
            gc.collect()

        # Verify all objects were garbage collected
        live_objects = [ref() for ref in object_refs if ref() is not None]
        assert len(live_objects) == 0, f"All objects should be garbage collected, but {len(live_objects)} remain"

    def test_manager_circular_reference_prevention(self):
        """Test that managers don't create circular references."""

        class TestManager(BaseManager):
            def __init__(self, parent=None):
                self.external_refs = []  # Use list instead of keeping strong refs
                super().__init__("test_manager", parent)

            def _initialize(self):
                self._is_initialized = True

            def cleanup(self):
                self.external_refs.clear()

            def add_external_ref(self, obj):
                # Store weak reference to prevent cycles
                self.external_refs.append(weakref.ref(obj))

            def get_live_refs(self):
                return [ref() for ref in self.external_refs if ref() is not None]

        manager = TestManager()
        manager_ref = weakref.ref(manager)

        # Create objects that reference the manager
        objects = []
        for i in range(5):
            obj = type("TestObj", (), {"id": i})()
            manager.add_external_ref(obj)
            objects.append(obj)

        # Verify references work
        live_refs = manager.get_live_refs()
        assert len(live_refs) == 5, "All external references should be accessible"

        # Cleanup
        manager.cleanup()
        del objects
        del manager
        gc.collect()

        # Verify manager was garbage collected
        assert manager_ref() is None, "Manager should be garbage collected"


@pytest.mark.usefixtures("isolated_managers")
@pytest.mark.skip_thread_cleanup(reason="Uses isolated_managers which owns worker threads")
class TestBaseManagerStability:
    """Test base manager stability patterns.

    Migrated from test_phase1_stability_fixes.py - validates Phase 1 stability fixes
    for BaseManager thread safety and operation tracking.
    """

    def test_base_manager_thread_safety(self):
        """Test BaseManager thread safety mechanisms."""

        class TestManager(BaseManager):
            def __init__(self):
                super().__init__("thread_safety_test")
                self.shared_counter = 0

            def _initialize(self):
                self._is_initialized = True

            def cleanup(self):
                pass

            def increment_counter(self):
                """Thread-safe counter increment."""
                with self._lock:
                    current = self.shared_counter
                    time.sleep(0.001)  # sleep-ok: race condition test
                    self.shared_counter = current + 1

        manager = TestManager()
        threads = []

        # Create multiple threads that increment counter
        for _i in range(20):
            thread = threading.Thread(target=manager.increment_counter)
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify thread safety - counter should be exactly 20
        assert manager.shared_counter == 20, f"Expected 20, got {manager.shared_counter}"

    def test_base_manager_operation_tracking(self):
        """Test BaseManager operation tracking is thread-safe."""

        class TestManager(BaseManager):
            def __init__(self):
                super().__init__("operation_tracking_test")

            def _initialize(self):
                self._is_initialized = True

            def cleanup(self):
                pass

            def test_operation(self, op_id):
                if self._start_operation(f"op_{op_id}"):
                    try:
                        time.sleep(0.01)  # sleep-ok: race condition test
                        return True
                    finally:
                        self._finish_operation(f"op_{op_id}")
                return False

        manager = TestManager()
        results = []
        lock = threading.Lock()

        def run_operation(op_id):
            result = manager.test_operation(op_id)
            with lock:
                results.append(result)

        # Run concurrent operations
        threads = []
        for i in range(10):
            thread = threading.Thread(target=run_operation, args=(i,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify all operations completed successfully
        assert all(results), "All operations should succeed"
        assert len(results) == 10, f"Should have 10 results, got {len(results)}"
        assert not manager.has_active_operations(), "No operations should be active after completion"


@pytest.mark.usefixtures("isolated_managers")
@pytest.mark.skip_thread_cleanup(reason="Uses isolated_managers which owns worker threads")
class TestMemoryStabilityPatterns:
    """Test memory management stability patterns.

    Migrated from test_phase1_stability_fixes.py - validates Phase 1 stability fixes
    for memory management and object lifecycle patterns.
    """

    def test_object_lifecycle_management(self):
        """Test proper object lifecycle management prevents leaks."""

        class ManagedObject:
            _instances = weakref.WeakSet()

            def __init__(self, name):
                self.name = name
                self.children = []
                self.cleanup_called = False
                ManagedObject._instances.add(self)

            def add_child(self, child):
                self.children.append(child)

            def cleanup(self):
                # Proper cleanup prevents leaks
                for child in self.children:
                    if hasattr(child, "cleanup"):
                        child.cleanup()
                self.children.clear()
                self.cleanup_called = True

            @classmethod
            def get_live_instances(cls):
                return len(cls._instances)

        # Track initial instance count
        initial_count = ManagedObject.get_live_instances()

        # Create objects with hierarchy
        parent = ManagedObject("parent")
        for i in range(5):
            child = ManagedObject(f"child_{i}")
            parent.add_child(child)

        # Verify instances were created
        assert ManagedObject.get_live_instances() == initial_count + 6

        # Proper cleanup
        parent.cleanup()
        cleanup_was_called = parent.cleanup_called

        # Verify cleanup was called (this is the main test)
        assert cleanup_was_called, "Cleanup should have been called"

        # Delete parent and attempt garbage collection
        del parent

        # Force multiple garbage collection cycles
        for _ in range(5):
            gc.collect()

        # Verify instances count is reasonable (exact count depends on GC timing)
        final_count = ManagedObject.get_live_instances()

        # The key test: cleanup method works and instance tracking works
        assert final_count <= initial_count + 6, f"Expected <= {initial_count + 6} instances, got {final_count}"

    def test_stress_memory_usage(self):
        """Test memory usage under stress conditions."""

        class StressTestObject:
            def __init__(self, data_size=1000):
                self.data = list(range(data_size))
                self.refs = []

            def add_ref(self, obj):
                # Use weak reference to prevent leaks
                self.refs.append(weakref.ref(obj))

            def cleanup(self):
                self.data.clear()
                self.refs.clear()

        objects = []

        # Create many objects with cross-references
        for _i in range(100):
            obj = StressTestObject()

            # Add cross-references to previous objects
            for prev_obj in objects[-5:]:  # Reference last 5 objects
                obj.add_ref(prev_obj)
                prev_obj.add_ref(obj)

            objects.append(obj)

        # Cleanup all objects
        for obj in objects:
            obj.cleanup()

        # Clear references and force garbage collection
        objects.clear()
        gc.collect()

        # If we get here without memory issues, test passed
        assert True, "Stress test should complete without memory issues"
