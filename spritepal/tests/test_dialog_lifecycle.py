"""
Test dialog lifecycle to prevent Qt widget deletion issues.
These tests ensure dialogs can be safely opened, closed, and reopened.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from core.di_container import inject
from core.protocols.manager_protocols import InjectionManagerProtocol
from ui.dialogs import UnifiedManualOffsetDialog as ManualOffsetDialog

# Test characteristics: Real GUI components requiring display
pytestmark = [
    pytest.mark.dialog,
    pytest.mark.gui,
    pytest.mark.qt_app,
    pytest.mark.qt_real,
    pytest.mark.rom_data,
    pytest.mark.slow,
    pytest.mark.widget,
    pytest.mark.headless,
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Dialogs may spawn worker threads via managers")
]

class TestDialogLifecycle:
    """Test dialog lifecycle management"""

    @pytest.mark.gui
    def test_manual_offset_dialog_normal_lifecycle(self, qtbot):
        """Test that ManualOffsetDialog follows normal Qt lifecycle"""
        # Create dialog with parent
        parent = QWidget()
        qtbot.addWidget(parent)

        # Don't register with qtbot since WA_DeleteOnClose will handle cleanup
        dialog1 = ManualOffsetDialog(parent)

        # Verify WA_DeleteOnClose is enabled for normal lifecycle
        assert dialog1.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose), \
            "Dialogs should have WA_DeleteOnClose=True for proper cleanup"

        # Show dialog
        dialog1.show()
        qtbot.waitUntil(dialog1.isVisible)

        # Access tabs to ensure they exist
        assert dialog1.browse_tab is not None
        assert dialog1.smart_tab is not None
        assert dialog1.history_tab is not None

        # Close dialog
        dialog1.close()
        qtbot.waitUntil(lambda: not dialog1.isVisible())

        # Create new instance - should be different object
        # Don't register with qtbot since WA_DeleteOnClose will handle cleanup
        dialog2 = ManualOffsetDialog(parent)
        assert dialog2 is not dialog1, "Should create new instance each time"

        # Show dialog again
        dialog2.show()
        qtbot.waitUntil(dialog2.isVisible)

        # Verify tabs exist and are accessible
        assert dialog2.browse_tab is not None
        assert dialog2.smart_tab is not None
        assert dialog2.history_tab is not None

        # Try to access browse tab controls
        if hasattr(dialog2.browse_tab, "offset_widget"):
            # This should work without errors
            dialog2.browse_tab.offset_widget.setMaximum(1000)

        # Cleanup
        dialog2.close()

    @pytest.mark.gui
    def test_dialog_with_parent_lifecycle(self, qtbot):
        """Test dialog follows proper Qt parent-child lifecycle management"""
        from PySide6.QtWidgets import QWidget

        # Create a parent widget
        parent = QWidget()
        qtbot.addWidget(parent)

        # Create dialog with parent (normal instantiation)
        # Don't register with qtbot since parent will manage lifecycle
        dialog = ManualOffsetDialog(parent)

        # Verify dialog has the correct parent
        assert dialog.parent() is parent, "Dialog should have the specified parent"

        # Verify dialog is non-modal by default (as per new dialog pattern)
        assert dialog.windowModality() == Qt.WindowModality.NonModal

        # Show dialog
        dialog.show()
        qtbot.waitUntil(dialog.isVisible)

        # Verify dialog is functional before parent deletion
        assert dialog.browse_tab is not None
        assert dialog.smart_tab is not None
        assert dialog.history_tab is not None

        # Close dialog explicitly before parent deletion to avoid Qt lifecycle issues
        dialog.close()

        # Now delete parent
        parent.deleteLater()

class TestDialogReopenScenarios:
    """Test various dialog reopen scenarios"""

    @pytest.mark.gui
    def test_non_singleton_dialog_lifecycle(self, qtbot):
        """Test that non-singleton dialogs are properly recreated"""
        from ui.injection_dialog import InjectionDialog

        injection_manager = inject(InjectionManagerProtocol)

        # Create first instance
        dialog1 = InjectionDialog(None, "test.png", "", injection_manager=injection_manager)
        qtbot.addWidget(dialog1)

        # Non-singleton dialogs CAN have DeleteOnClose
        # They should be recreated each time

        # Store the id
        id1 = id(dialog1)

        # Close dialog
        dialog1.close()

        # Create new instance - should be different object
        dialog2 = InjectionDialog(None, "test.png", "", injection_manager=injection_manager)
        qtbot.addWidget(dialog2)
        id2 = id(dialog2)

        assert id1 != id2, "Non-singleton dialogs should create new instances"

        # Cleanup
        dialog2.close()

def test_dialog_lifecycle_best_practices():
    """Document dialog lifecycle best practices"""
    best_practices = """
    Dialog Lifecycle Best Practices:

    1. BaseDialog sets WA_DeleteOnClose=True by default
       - Good for one-time dialogs
       - Bad for singletons or reusable dialogs

    2. Singleton dialogs MUST:
       - Set setAttribute(WA_DeleteOnClose, False)
       - Be created with parent=None
       - Implement proper cleanup in closeEvent

    3. Parent-child relationships:
       - When parent is deleted, ALL children are deleted
       - Singletons should not have parents
       - Use window modality instead of parent for dialog relationships

    4. Testing dialog lifecycle:
       - Test open → close → reopen scenarios
       - Test parent deletion scenarios
       - Use real Qt widgets, not mocks, for lifecycle tests
    """

    assert True, best_practices
