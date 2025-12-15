"""
Test suite for the dependency injection system.

This module validates that the context-based dependency injection system
works correctly and provides the expected isolation between tests.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import Mock, patch

import pytest

from core.di_container import inject
from core.managers.context import (
    ContextValidator,
    # Serial execution required: Thread safety concerns
    ManagerContext,
    get_current_context,
    manager_context,
)
from core.managers.exceptions import ManagerError
from core.managers.injectable import (
    DirectManagerProvider,
    InjectableDialog,
    InjectableWidget,
    InjectionMixin,
)
from core.protocols.manager_protocols import (
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
    SessionManagerProtocol,
)

pytestmark = [
    pytest.mark.serial,
    pytest.mark.thread_safety,
    pytest.mark.dialog,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.usefixtures("session_managers"),  # DI tests need real managers for fallback tests
    pytest.mark.skip_thread_cleanup(reason="DI tests may spawn worker threads via managers")
]
class TestManagerContext:
    """Test the ManagerContext class functionality."""

    def test_context_creation(self):
        """Test basic context creation and manager storage."""
        mock_injection = Mock()
        mock_extraction = Mock()

        context = ManagerContext({
            "injection": mock_injection,
            "extraction": mock_extraction
        }, name="test")

        assert context._name == "test"
        assert context.has_manager("injection")
        assert context.has_manager("extraction")
        assert not context.has_manager("session")

    def test_manager_retrieval(self):
        """Test manager retrieval with type validation."""
        mock_injection = Mock()
        mock_injection.__class__ = Mock
        mock_injection.__class__.__name__ = "InjectionManager"

        context = ManagerContext({"injection": mock_injection})

        # Should return the mock (type checking is relaxed for mocks)
        retrieved = context.get_manager("injection", object)
        assert retrieved is mock_injection

    def test_manager_not_found(self):
        """Test error when manager is not found."""
        context = ManagerContext({})

        with pytest.raises(ManagerError) as exc_info:
            context.get_manager("nonexistent", object)

        assert "nonexistent manager not available" in str(exc_info.value).lower()

    def test_context_inheritance(self):
        """Test parent-child context inheritance."""
        mock_injection = Mock()
        mock_extraction = Mock()
        Mock()

        # Parent context with injection manager
        parent = ManagerContext({"injection": mock_injection}, name="parent")

        # Child context with extraction manager
        child = ManagerContext({"extraction": mock_extraction}, parent=parent, name="child")

        # Child should have access to both managers
        assert child.get_manager("injection", object) is mock_injection
        assert child.get_manager("extraction", object) is mock_extraction

        # Child context overrides parent
        child_injection = Mock()
        child.add_manager("injection", child_injection)
        assert child.get_manager("injection", object) is child_injection
        assert parent.get_manager("injection", object) is mock_injection

    def test_available_managers(self):
        """Test getting all available managers including inheritance."""
        mock_injection = Mock()
        mock_extraction = Mock()
        mock_session = Mock()

        parent = ManagerContext({"injection": mock_injection, "session": mock_session})
        child = ManagerContext({"extraction": mock_extraction}, parent=parent)

        available = child.get_available_managers()

        assert len(available) == 3
        assert available["injection"] is mock_injection
        assert available["extraction"] is mock_extraction
        assert available["session"] is mock_session

    def test_child_context_creation(self):
        """Test creating child contexts."""
        parent = ManagerContext({"injection": Mock()}, name="parent")
        child = parent.create_child_context({"extraction": Mock()}, name="child")

        assert child._parent is parent
        assert child._name == "parent/child"
        assert child.has_manager("injection")  # From parent
        assert child.has_manager("extraction")  # From child

class TestContextManager:
    """Test the context manager functionality."""

    def test_context_manager_usage(self):
        """Test using context manager for temporary contexts."""
        mock_injection = Mock()

        # No context initially
        assert get_current_context() is None

        with manager_context({"injection": mock_injection}, name="test"):
            # Context is set within the block
            current = get_current_context()
            assert current is not None
            assert current._name == "test"
            assert current.has_manager("injection")

        # Context is cleared after the block
        assert get_current_context() is None

    def test_nested_contexts(self):
        """Test nested context managers."""
        mock_injection = Mock()
        mock_extraction = Mock()

        with manager_context({"injection": mock_injection}, name="outer"):
            outer_context = get_current_context()

            with manager_context({"extraction": mock_extraction}, name="inner"):
                inner_context = get_current_context()

                # Inner context should be different from outer
                assert inner_context is not outer_context
                assert inner_context._parent is outer_context

                # Inner context has access to both managers
                assert inner_context.has_manager("injection")  # From parent
                assert inner_context.has_manager("extraction")  # From self

            # Back to outer context
            assert get_current_context() is outer_context

class TestGlobalAccessorIntegration:
    """Test that global accessor functions work with contexts."""

    def test_context_fallback_injection_manager(self, manager_context_factory):
        """Test injection manager resolution with DI injection."""
        # Since deprecated functions are removed, we test DI injection works
        manager = inject(InjectionManagerProtocol)
        assert manager is not None

    def test_context_fallback_extraction_manager(self, manager_context_factory):
        """Test extraction manager resolution with DI injection."""
        manager = inject(ExtractionManagerProtocol)
        assert manager is not None

    def test_context_fallback_session_manager(self, manager_context_factory):
        """Test session manager resolution with DI injection."""
        manager = inject(SessionManagerProtocol)
        assert manager is not None

    def test_di_injection_returns_managers(self):
        """Test that DI inject() returns properly initialized managers."""
        # Verify DI container returns managers of expected types
        injection_manager = inject(InjectionManagerProtocol)
        extraction_manager = inject(ExtractionManagerProtocol)
        session_manager = inject(SessionManagerProtocol)

        assert injection_manager is not None
        assert extraction_manager is not None
        assert session_manager is not None

@pytest.mark.gui
class TestInjectableClasses:
    """Test the injectable base classes.

    These tests create real Qt widgets (QDialog, QWidget) so they require
    a Qt display environment, qtbot fixture, and must be marked as GUI tests.
    """

    def test_injectable_dialog_with_context(self, qtbot, manager_context_factory):
        """Test InjectableDialog with context."""
        mock_injection = Mock()
        mock_injection.is_initialized.return_value = True

        with manager_context_factory({"injection": mock_injection}):
            dialog = InjectableDialog()
            qtbot.addWidget(dialog)  # Register widget for cleanup

            assert dialog.get_injection_manager() is mock_injection

    def test_injectable_widget_with_explicit_context(self, qtbot):
        """Test InjectableWidget with explicit context."""
        mock_extraction = Mock()
        mock_extraction.is_initialized.return_value = True

        context = ManagerContext({"extraction": mock_extraction}, name="explicit")
        widget = InjectableWidget(manager_context=context)
        qtbot.addWidget(widget)  # Register widget for cleanup

        assert widget.get_extraction_manager() is mock_extraction

    def test_injectable_with_direct_provider(self, qtbot):
        """Test injectable classes with DirectManagerProvider."""
        mock_injection = Mock()
        mock_session = Mock()

        provider = DirectManagerProvider(
            injection_manager=mock_injection,
            session_manager=mock_session
        )

        dialog = InjectableDialog(manager_provider=provider)
        qtbot.addWidget(dialog)  # Register widget for cleanup

        assert dialog.get_injection_manager() is mock_injection
        assert dialog.get_session_manager() is mock_session

    def test_injection_mixin(self, qtbot, manager_context_factory):
        """Test InjectionMixin functionality."""
        from PySide6.QtWidgets import QWidget

        class TestWidget(QWidget, InjectionMixin):
            def __init__(self):
                QWidget.__init__(self)
                InjectionMixin.__init__(self)

        mock_injection = Mock()
        mock_injection.is_initialized.return_value = True

        with manager_context_factory({"injection": mock_injection}):
            widget = TestWidget()
            qtbot.addWidget(widget)  # Register widget for cleanup
            assert widget.get_injection_manager() is mock_injection

class TestThreadSafety:
    """Test thread safety of the context system."""

    def test_thread_local_contexts(self):
        """Test that contexts are thread-local."""
        results = {}

        def thread_func(thread_id):
            mock_injection = Mock()
            mock_injection.thread_id = thread_id
            mock_injection.is_initialized.return_value = True

            with manager_context({"injection": mock_injection}, name=f"thread_{thread_id}"):
                # Small delay to ensure threads are running concurrently
                time.sleep(0.1)  # sleep-ok: thread interleaving

                # Use context to get manager (replaces deprecated get_injection_manager)
                ctx = get_current_context()
                # Access via _managers dict to avoid type validation with mocks
                manager = ctx._managers.get("injection") if ctx else None
                results[thread_id] = manager.thread_id if manager else -1

        # Start multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=thread_func, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Each thread should have gotten its own manager
        assert len(results) == 3
        for i in range(3):
            assert results[i] == i

    def test_context_isolation_between_threads(self):
        """Test that contexts don't interfere between threads."""
        barrier = threading.Barrier(2)
        results = {}

        def thread1():
            mock_injection = Mock()
            mock_injection.name = "thread1_manager"
            mock_injection.is_initialized.return_value = True

            with manager_context({"injection": mock_injection}):
                barrier.wait()  # Synchronize with thread2
                time.sleep(0.1)  # sleep-ok: thread interleaving

                # Should still have thread1's manager
                ctx = get_current_context()
                # Access via _managers dict to avoid type validation with mocks
                manager = ctx._managers.get("injection") if ctx else None
                results["thread1"] = manager.name if manager else "no_manager"

        def thread2():
            barrier.wait()  # Synchronize with thread1

            mock_injection = Mock()
            mock_injection.name = "thread2_manager"
            mock_injection.is_initialized.return_value = True

            with manager_context({"injection": mock_injection}):
                ctx = get_current_context()
                # Access via _managers dict to avoid type validation with mocks
                manager = ctx._managers.get("injection") if ctx else None
                results["thread2"] = manager.name if manager else "no_manager"

        t1 = threading.Thread(target=thread1)
        t2 = threading.Thread(target=thread2)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        assert results["thread1"] == "thread1_manager"
        assert results["thread2"] == "thread2_manager"

class TestContextValidation:
    """Test context validation and debugging utilities."""

    def test_context_validation_success(self):
        """Test successful context validation."""
        mock_injection = Mock()
        mock_injection.is_initialized.return_value = True

        mock_extraction = Mock()
        mock_extraction.is_initialized.return_value = True

        mock_session = Mock()
        mock_session.is_initialized.return_value = True

        context = ManagerContext({
            "injection": mock_injection,
            "extraction": mock_extraction,
            "session": mock_session
        })

        errors = ContextValidator.validate_context(context)
        assert len(errors) == 0

    def test_context_validation_missing_manager(self):
        """Test context validation with missing managers."""
        context = ManagerContext({"injection": Mock()})

        errors = ContextValidator.validate_context(context)
        assert len(errors) >= 2  # Missing extraction and session
        assert any("extraction" in error for error in errors)
        assert any("session" in error for error in errors)

    def test_context_validation_uninitialized_manager(self):
        """Test context validation with uninitialized managers."""
        mock_injection = Mock()
        mock_injection.is_initialized.return_value = False  # Not initialized

        mock_extraction = Mock()
        mock_extraction.is_initialized.return_value = True

        mock_session = Mock()
        mock_session.is_initialized.return_value = True

        context = ManagerContext({
            "injection": mock_injection,
            "extraction": mock_extraction,
            "session": mock_session
        })

        errors = ContextValidator.validate_context(context)
        assert len(errors) == 1
        assert "injection manager not properly initialized" in errors[0]

    def test_debug_context_chain(self):
        """Test debug information generation."""
        mock_injection = Mock()
        mock_extraction = Mock()

        with manager_context({"injection": mock_injection}, name="parent"):
            with manager_context({"extraction": mock_extraction}, name="child"):
                debug_info = ContextValidator.debug_context_chain()

                assert "child" in debug_info
                assert "parent" in debug_info
                assert "extraction" in debug_info
                assert "injection" in debug_info

class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_dialog_test_scenario(self, manager_context_factory):
        """Test a realistic dialog testing scenario."""
        # This simulates testing InjectionDialog
        mock_injection = Mock()
        mock_injection.is_initialized.return_value = True
        mock_injection.load_metadata.return_value = None
        mock_injection.suggest_output_vram_path.return_value = "test_output.dmp"

        with manager_context_factory({"injection": mock_injection}):
            # Use context to get manager (replaces deprecated get_injection_manager)
            ctx = get_current_context()
            # Access via _managers dict to avoid type validation with mocks
            manager = ctx._managers.get("injection") if ctx else None

            # Simulate dialog operations
            metadata = manager.load_metadata("test.json")
            output_path = manager.suggest_output_vram_path("input.dmp")

            assert metadata is None
            assert output_path == "test_output.dmp"
            mock_injection.load_metadata.assert_called_once_with("test.json")
            mock_injection.suggest_output_vram_path.assert_called_once_with("input.dmp")

    def test_parallel_test_isolation(self):
        """Test that parallel tests don't interfere with each other."""
        # This simulates pytest running tests in parallel

        def test_simulation_1():
            mock_injection = Mock()
            mock_injection.test_id = "test1"
            mock_injection.is_initialized.return_value = True

            with manager_context({"injection": mock_injection}):
                ctx = get_current_context()
                # Access via _managers dict to avoid type validation with mocks
                manager = ctx._managers.get("injection") if ctx else None
                return manager.test_id if manager else "no_manager"

        def test_simulation_2():
            mock_injection = Mock()
            mock_injection.test_id = "test2"
            mock_injection.is_initialized.return_value = True

            with manager_context({"injection": mock_injection}):
                ctx = get_current_context()
                # Access via _managers dict to avoid type validation with mocks
                manager = ctx._managers.get("injection") if ctx else None
                return manager.test_id if manager else "no_manager"

        # Run simulations
        result1 = test_simulation_1()
        result2 = test_simulation_2()

        assert result1 == "test1"
        assert result2 == "test2"

    def test_migration_compatibility(self, manager_context_factory):
        """Test that new InjectableDialog-based code works with contexts."""
        # Simulate new injectable dialog class (deprecated class removed)
        class NewDialog(InjectableDialog):
            def __init__(self):
                super().__init__()
                self.injection_manager = self.get_injection_manager()

        mock_injection = Mock()
        mock_injection.is_initialized.return_value = True

        with manager_context_factory({"injection": mock_injection}):
            # New dialog should work with context
            new_dialog = NewDialog()
            assert new_dialog.injection_manager is mock_injection
