"""
Dependency Injection Migration Examples for SpritePal

This module demonstrates how to migrate from global singleton manager access
to dependency injection using the new context system.

The migration can be done gradually without breaking existing code.
"""
from __future__ import annotations

from unittest.mock import Mock

from PySide6.QtWidgets import QDialog, QWidget

from core.managers import (  # This now supports contexts!
    get_extraction_manager,
    get_injection_manager,
)

# Import the new dependency injection infrastructure
from core.managers.context import ManagerContext, manager_context
from core.managers.injectable import (
    DirectManagerProvider,
    InjectableDialog,
    InjectableWidget,
    InjectionMixin,
)


def example_1_existing_code_unchanged():
    """
    Example 1: Existing code continues to work unchanged

    This demonstrates backward compatibility - no changes needed
    to existing production code.
    """
    print("=== Example 1: Existing Code (Unchanged) ===")

    # This is how existing dialogs work and will continue to work
    class ExistingDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)

            # This continues to work exactly as before
            # But now it can use injected managers from tests!
            self.injection_manager = get_injection_manager()

    # Production code - uses global managers
    print("Production: Uses global managers")
    # dialog = ExistingDialog()  # Would use global managers

    # Test code - can now inject managers without changing the dialog!
    print("Test: Can inject managers without changing dialog code")
    mock_injection = Mock()
    mock_injection.is_initialized.return_value = True

    with manager_context({"injection": mock_injection}):
        dialog = ExistingDialog()
        # dialog.injection_manager is now the mock!
        print(f"Dialog uses mock: {dialog.injection_manager is mock_injection}")

def example_2_test_context_usage():
    """
    Example 2: Using contexts in tests

    This shows the primary use case - tests can inject their own
    manager instances for complete isolation.
    """
    print("\n=== Example 2: Test Context Usage ===")

    # Create mock managers for testing
    mock_injection = Mock()
    mock_injection.is_initialized.return_value = True
    mock_injection.load_metadata.return_value = None
    mock_injection.suggest_output_vram_path.return_value = "test.dmp"

    mock_extraction = Mock()
    mock_extraction.is_initialized.return_value = True
    mock_extraction.extract_from_vram.return_value = {"success": True}

    # Test with specific managers
    test_managers = {
        "injection": mock_injection,
        "extraction": mock_extraction
    }

    with manager_context(test_managers, name="dialog_test"):
        # Any dialog created in this context will use the test managers
        print("Inside context - dialogs will use test managers")

        # Example: InjectionDialog would use mock_injection
        injection_mgr = get_injection_manager()
        print(f"Got mock injection manager: {injection_mgr is mock_injection}")

        extraction_mgr = get_extraction_manager()
        print(f"Got mock extraction manager: {extraction_mgr is mock_extraction}")

def example_3_injectable_base_classes():
    """
    Example 3: Using injectable base classes

    For new code, you can inherit from injectable base classes
    which provide cleaner dependency injection support.
    """
    print("\n=== Example 3: Injectable Base Classes ===")

    # New dialog using injectable base class
    class ModernDialog(InjectableDialog):
        def __init__(self, parent=None, **kwargs):
            super().__init__(parent, **kwargs)

            # Use the injectable methods instead of global functions
            self.injection_manager = self.get_injection_manager()
            self.extraction_manager = self.get_extraction_manager()
            self.session_manager = self.get_session_manager()

    # Can be used normally (falls back to global managers)
    print("Normal usage - falls back to global managers")
    # dialog = ModernDialog()

    # Can be used with explicit context
    print("With explicit context")
    mock_injection = Mock()
    mock_injection.is_initialized.return_value = True
    test_context = ManagerContext({"injection": mock_injection}, name="explicit")

    dialog = ModernDialog(manager_context=test_context)
    print(f"Dialog uses explicit context: {dialog.get_injection_manager() is mock_injection}")

    # Can be used with current thread context
    print("With thread context")
    with manager_context({"injection": mock_injection}):
        dialog = ModernDialog()
        print(f"Dialog uses thread context: {dialog.get_injection_manager() is mock_injection}")

def example_4_direct_injection():
    """
    Example 4: Direct dependency injection

    For maximum control, you can inject managers directly
    using a DirectManagerProvider.
    """
    print("\n=== Example 4: Direct Injection ===")

    # Create mock managers
    mock_injection = Mock()
    mock_injection.is_initialized.return_value = True

    mock_session = Mock()
    mock_session.is_initialized.return_value = True

    # Create direct provider
    provider = DirectManagerProvider(
        injection_manager=mock_injection,
        session_manager=mock_session
        # extraction_manager=None (will fall back to global)
    )

    # Use with injectable dialog
    class DirectInjectionDialog(InjectableDialog):
        def __init__(self, parent=None, **kwargs):
            super().__init__(parent, **kwargs)
            self.injection_manager = self.get_injection_manager()

    dialog = DirectInjectionDialog(manager_provider=provider)
    print(f"Dialog uses directly injected manager: {dialog.injection_manager is mock_injection}")

def example_5_migration_with_mixin():
    """
    Example 5: Gradual migration using mixin

    For existing widgets/dialogs, you can add injection support
    without changing the inheritance hierarchy.
    """
    print("\n=== Example 5: Migration with Mixin ===")

    # Existing widget that we want to migrate gradually
    class ExistingWidget(QWidget, InjectionMixin):
        def __init__(self, parent=None):
            QWidget.__init__(self, parent)
            InjectionMixin.__init__(self)  # Add injection support

            # Now we can use injection methods
            self.injection_manager = self.get_injection_manager()
            self.session_manager = self.get_session_manager()

    # Works with global managers
    print("Mixin widget with global managers")
    # widget = ExistingWidget()

    # Works with injected managers
    print("Mixin widget with injected managers")
    mock_injection = Mock()
    mock_injection.is_initialized.return_value = True

    with manager_context({"injection": mock_injection}):
        widget = ExistingWidget()
        print(f"Widget uses injected manager: {widget.injection_manager is mock_injection}")

def example_6_pytest_integration():
    """
    Example 6: Integration with pytest fixtures

    This shows how to use the new fixtures in actual tests.
    """
    print("\n=== Example 6: Pytest Integration ===")

    # This is how you would write tests with the new fixtures
    test_code = '''
    def test_injection_dialog(manager_context_factory):
        """Test InjectionDialog with mocked injection manager."""
        mock_injection = Mock()
        mock_injection.load_metadata.return_value = None

        with manager_context_factory({"injection": mock_injection}):
            dialog = InjectionDialog()

            # Dialog uses the mock manager
            assert dialog.injection_manager is mock_injection

            # Test specific behavior
            dialog._load_metadata()
            mock_injection.load_metadata.assert_called_once()

    def test_with_complete_context(complete_test_context):
        """Test with a complete set of test managers."""
        with manager_context(complete_test_context.get_available_managers()):
            dialog = SomeDialog()
            # All managers are available and properly mocked

    def test_minimal_context(minimal_injection_context):
        """Test with just injection manager."""
        with manager_context(minimal_injection_context.get_available_managers()):
            dialog = InjectionDialog()
            # Only injection manager is mocked, others fall back to global
    '''

    print("Example pytest test code:")
    print(test_code)

def example_7_debugging_contexts():
    """
    Example 7: Debugging context issues

    The system provides debugging tools to help understand
    context chains and validate configurations.
    """
    print("\n=== Example 7: Debugging Contexts ===")

    from core.managers.context import ContextValidator

    # Create nested contexts for demonstration
    mock_injection = Mock()
    mock_injection.is_initialized.return_value = True

    mock_extraction = Mock()
    mock_extraction.is_initialized.return_value = True

    # Parent context with injection manager
    with manager_context({"injection": mock_injection}, name="parent"):
        print("Parent context debug info:")
        print(ContextValidator.debug_context_chain())

        # Child context with extraction manager
        with manager_context({"extraction": mock_extraction}, name="child"):
            print("\nChild context debug info:")
            print(ContextValidator.debug_context_chain())

            # Validate current context
            is_valid, errors = ContextValidator.validate_current_context()
            print(f"\nContext validation: valid={is_valid}")
            if errors:
                print("Errors:", errors)

def example_8_performance_considerations():
    """
    Example 8: Performance considerations

    The dependency injection system is designed to have minimal
    performance impact on production code.
    """
    print("\n=== Example 8: Performance Considerations ===")

    print("Performance characteristics:")
    print("- Thread-local storage: O(1) lookup")
    print("- Context chain traversal: O(n) where n = context depth")
    print("- Global fallback: Same performance as original code")
    print("- No overhead when contexts are not used")

    print("\nBest practices:")
    print("- Keep context chains shallow (usually 1-2 levels)")
    print("- Use contexts primarily in tests, not production")
    print("- Cache manager references in frequently-used code")

    # Example of caching for performance
    class PerformantWidget(InjectableWidget):
        def __init__(self, parent=None):
            super().__init__(parent)

            # Cache manager references for better performance
            self._injection_manager = self.get_injection_manager()
            self._session_manager = self.get_session_manager()

        def some_frequent_operation(self):
            # Use cached references instead of calling get_*_manager repeatedly
            return self._injection_manager.some_method()

if __name__ == "__main__":
    print("SpritePal Dependency Injection Migration Examples")
    print("=" * 55)

    # Run all examples
    example_1_existing_code_unchanged()
    example_2_test_context_usage()
    example_3_injectable_base_classes()
    example_4_direct_injection()
    example_5_migration_with_mixin()
    example_6_pytest_integration()
    example_7_debugging_contexts()
    example_8_performance_considerations()

    print("\n" + "=" * 55)
    print("Migration Summary:")
    print("1. Existing code works unchanged ✓")
    print("2. Tests can inject managers ✓")
    print("3. New code can use injectable bases ✓")
    print("4. Gradual migration path available ✓")
    print("5. Thread-safe and performant ✓")
