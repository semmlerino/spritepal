"""
Mocked integration tests for the ComposedDialog architecture.

This module provides comprehensive integration testing using mocked Qt components
to avoid Qt application requirements while still testing component interactions.
"""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from ui.components.base.composed.button_box_manager import ButtonBoxManager
from ui.components.base.composed.composed_dialog import ComposedDialog
from ui.components.base.composed.message_dialog_manager import MessageDialogManager
from ui.components.base.composed.status_bar_manager import StatusBarManager


@pytest.mark.mock_only
@pytest.mark.integration
class TestComposedDialogMockedIntegration:
    """Mocked integration tests for the ComposedDialog architecture."""

    @patch('ui.components.base.composed.composed_dialog.QWidget')
    @patch('ui.components.base.composed.composed_dialog.QVBoxLayout')
    @patch('ui.components.base.composed.composed_dialog.QDialog.__init__')
    def test_dialog_creation_and_component_initialization(self, mock_dialog_init, mock_layout, mock_widget):
        """Test dialog creation initializes all components correctly."""
        # Setup mocks
        mock_dialog_init.return_value = None
        mock_layout_instance = Mock()
        mock_widget_instance = Mock()
        mock_layout.return_value = mock_layout_instance
        mock_widget.return_value = mock_widget_instance

        # Create dialog with all components
        dialog = ComposedDialog(with_status_bar=True, with_button_box=True)

        # Verify dialog initialization
        mock_dialog_init.assert_called_once()
        mock_layout.assert_called_once()
        mock_widget.assert_called_once()
        mock_layout_instance.addWidget.assert_called_once_with(mock_widget_instance)

        # Verify components were created
        assert len(dialog.components) == 3  # message, button, status

        # Verify component access
        assert dialog.get_component("message_dialog") is not None
        assert dialog.get_component("button_box") is not None
        assert dialog.get_component("status_bar") is not None
        assert dialog.get_component("nonexistent") is None

        # Verify context was set up correctly
        assert dialog.context is not None
        assert dialog.context.dialog == dialog
        assert dialog.context.main_layout == mock_layout_instance
        assert dialog.context.content_widget == mock_widget_instance

    @patch('ui.components.base.composed.composed_dialog.QWidget')
    @patch('ui.components.base.composed.composed_dialog.QVBoxLayout')
    @patch('ui.components.base.composed.composed_dialog.QDialog.__init__')
    def test_dialog_selective_component_creation(self, mock_dialog_init, mock_layout, mock_widget):
        """Test dialog creates only requested components."""
        mock_dialog_init.return_value = None

        # Create dialog without button box
        dialog = ComposedDialog(with_button_box=False, with_status_bar=True)

        # Should have message dialog and status bar, but not button box
        assert dialog.get_component("message_dialog") is not None
        assert dialog.get_component("button_box") is None
        assert dialog.get_component("status_bar") is not None
        assert len(dialog.components) == 2

    @patch('ui.components.base.composed.message_dialog_manager.QMessageBox')
    def test_message_dialog_manager_integration(self, mock_messagebox):
        """Test MessageDialogManager integration with mocked QMessageBox."""
        # Create mock dialog
        mock_dialog = Mock()

        # Create and initialize manager
        manager = MessageDialogManager()
        manager.initialize(mock_dialog)

        # Set up signal spy equivalent
        messages_shown = []
        manager.message_shown.connect(lambda msg_type, msg: messages_shown.append((msg_type, msg)))

        # Test info message
        manager.show_info("Info Title", "Info message")
        mock_messagebox.information.assert_called_once_with(mock_dialog, "Info Title", "Info message")
        assert ("info", "Info message") in messages_shown

        # Test error message
        manager.show_error("Error Title", "Error message")
        mock_messagebox.critical.assert_called_once_with(mock_dialog, "Error Title", "Error message")
        assert ("error", "Error message") in messages_shown

        # Test warning message
        manager.show_warning("Warning Title", "Warning message")
        mock_messagebox.warning.assert_called_once_with(mock_dialog, "Warning Title", "Warning message")
        assert ("warning", "Warning message") in messages_shown

        # Test confirmation dialog
        mock_messagebox.question.return_value = mock_messagebox.StandardButton.Yes
        result = manager.confirm_action("Confirm Title", "Confirm message")
        mock_messagebox.question.assert_called_once_with(mock_dialog, "Confirm Title", "Confirm message")
        assert result is True
        assert ("confirmation", "Confirm message") in messages_shown

    @patch('ui.components.base.composed.button_box_manager.QDialogButtonBox')
    def test_button_box_manager_integration(self, mock_buttonbox):
        """Test ButtonBoxManager integration with mocked QDialogButtonBox."""
        # Create mock context
        mock_context = Mock()
        mock_context.config = {"with_button_box": True}
        mock_context.main_layout = Mock()
        mock_context.accept = Mock()
        mock_context.reject = Mock()

        # Create mock button box instance
        mock_box_instance = Mock()
        mock_buttonbox.return_value = mock_box_instance

        # Create and initialize manager
        manager = ButtonBoxManager()
        manager.initialize(mock_context)

        # Verify button box creation
        mock_buttonbox.assert_called_once()
        mock_context.main_layout.addWidget.assert_called_once_with(mock_box_instance)

        # Verify signal connections
        mock_box_instance.accepted.connect.assert_called()
        mock_box_instance.rejected.connect.assert_called()

        # Test button access
        mock_button = Mock()
        mock_box_instance.button.return_value = mock_button

        from PySide6.QtWidgets import QDialogButtonBox
        button = manager.get_button(QDialogButtonBox.StandardButton.Ok)
        assert button == mock_button

    @patch('ui.components.base.composed.status_bar_manager.QStatusBar')
    def test_status_bar_manager_integration(self, mock_statusbar):
        """Test StatusBarManager integration with mocked QStatusBar."""
        # Create mock context
        mock_context = Mock()
        mock_context.config = {"with_status_bar": True}
        mock_context.main_layout = Mock()

        # Create mock status bar instance
        mock_bar_instance = Mock()
        mock_statusbar.return_value = mock_bar_instance

        # Create and initialize manager
        manager = StatusBarManager()

        # Track status changes
        status_changes = []
        manager.status_changed.connect(lambda msg: status_changes.append(msg))

        manager.initialize(mock_context)

        # Verify status bar creation
        mock_statusbar.assert_called_once_with(mock_context)
        mock_context.main_layout.addWidget.assert_called_once_with(mock_bar_instance)

        # Test showing message
        manager.show_message("Test message", 5000)
        mock_bar_instance.showMessage.assert_called_once_with("Test message", 5000)
        assert "Test message" in status_changes

        # Test clearing message
        manager.clear_message()
        mock_bar_instance.clearMessage.assert_called_once()
        assert "" in status_changes

    @patch('ui.components.base.composed.composed_dialog.QWidget')
    @patch('ui.components.base.composed.composed_dialog.QVBoxLayout')
    @patch('ui.components.base.composed.composed_dialog.QDialog.__init__')
    def test_dialog_cleanup_on_close_event(self, mock_dialog_init, mock_layout, mock_widget):
        """Test dialog cleanup is called on all components during close."""
        mock_dialog_init.return_value = None

        # Create dialog
        dialog = ComposedDialog(with_status_bar=True)

        # Mock cleanup methods on components
        for component in dialog.components:
            component.cleanup = Mock()

        # Create and process close event
        from PySide6.QtGui import QCloseEvent
        with patch('PySide6.QtGui.QCloseEvent'):
            mock_close_event = Mock(spec=QCloseEvent)

            # Mock parent closeEvent
            with patch('PySide6.QtWidgets.QDialog.closeEvent') as mock_parent_close:
                dialog.closeEvent(mock_close_event)

                # Verify all component cleanup methods were called
                for component in dialog.components:
                    component.cleanup.assert_called_once()

                # Verify parent closeEvent was called
                mock_parent_close.assert_called_once_with(mock_close_event)

    @patch('ui.components.base.composed.composed_dialog.QWidget')
    @patch('ui.components.base.composed.composed_dialog.QVBoxLayout')
    @patch('ui.components.base.composed.composed_dialog.QDialog.__init__')
    def test_dialog_context_component_registration(self, mock_dialog_init, mock_layout, mock_widget):
        """Test DialogContext correctly registers components during initialization."""
        mock_dialog_init.return_value = None

        # Create dialog
        dialog = ComposedDialog(with_status_bar=True, with_button_box=True)

        context = dialog.context

        # Test component registration
        assert context.has_component("message_dialog") is True
        assert context.has_component("button_box") is True
        assert context.has_component("status_bar") is True

        # Test getting components through context
        message_manager = context.get_component("message_dialog")
        button_manager = context.get_component("button_box")
        status_manager = context.get_component("status_bar")

        assert message_manager is not None
        assert button_manager is not None
        assert status_manager is not None

        # Verify these are the same objects accessible through dialog
        assert message_manager == dialog.get_component("message_dialog")
        assert button_manager == dialog.get_component("button_box")
        assert status_manager == dialog.get_component("status_bar")

    def test_custom_dialog_subclass_setup_ui_called(self):
        """Test that custom dialog subclass setup_ui method is called."""

        class CustomTestDialog(ComposedDialog):
            def __init__(self, **config):
                self.setup_ui_called = False
                super().__init__(**config)

            def setup_ui(self):
                self.setup_ui_called = True

        with patch('ui.components.base.composed.composed_dialog.QWidget'), \
             patch('ui.components.base.composed.composed_dialog.QVBoxLayout'), \
             patch('ui.components.base.composed.composed_dialog.QDialog.__init__'):

            dialog = CustomTestDialog()
            assert dialog.setup_ui_called is True

    def test_dialog_without_setup_ui_method(self):
        """Test dialog works correctly when subclass doesn't implement setup_ui."""

        class MinimalDialog(ComposedDialog):
            pass

        with patch('ui.components.base.composed.composed_dialog.QWidget'), \
             patch('ui.components.base.composed.composed_dialog.QVBoxLayout'), \
             patch('ui.components.base.composed.composed_dialog.QDialog.__init__'):

            # Should not raise any errors
            dialog = MinimalDialog()

            # Basic components should still be available
            assert dialog.get_component("message_dialog") is not None
            assert dialog.get_component("button_box") is not None

    @patch('ui.components.base.composed.composed_dialog.QWidget')
    @patch('ui.components.base.composed.composed_dialog.QVBoxLayout')
    @patch('ui.components.base.composed.composed_dialog.QDialog.__init__')
    def test_dialog_configuration_persistence(self, mock_dialog_init, mock_layout, mock_widget):
        """Test that dialog configuration is properly stored and accessible."""
        mock_dialog_init.return_value = None

        test_config = {
            "with_status_bar": True,
            "with_button_box": False,
            "custom_option": "test_value",
            "numeric_option": 42
        }

        dialog = ComposedDialog(**test_config)

        # Verify configuration is stored
        assert dialog.config == test_config

        # Verify configuration is accessible through context
        assert dialog.context.config == test_config

        # Verify configuration affects component creation
        assert dialog.get_component("message_dialog") is not None  # Always created
        assert dialog.get_component("button_box") is None  # Disabled
        assert dialog.get_component("status_bar") is not None  # Enabled

    @pytest.mark.parametrize("manager_class,config_key,expected_available", [
        (ButtonBoxManager, "with_button_box", True),
        (ButtonBoxManager, "with_button_box", False),
        (StatusBarManager, "with_status_bar", True),
        (StatusBarManager, "with_status_bar", False),
    ])
    def test_manager_availability_based_on_config(self, manager_class, config_key, expected_available):
        """Test manager availability is correctly determined by configuration."""

        # Create mock context
        mock_context = Mock()
        mock_context.config = {config_key: expected_available}
        mock_context.main_layout = Mock()

        # Mock Qt components appropriately
        if manager_class == ButtonBoxManager:
            with patch('ui.components.base.composed.button_box_manager.QDialogButtonBox'):
                manager = manager_class()
                manager.initialize(mock_context)
                assert manager.is_available == expected_available
        else:  # StatusBarManager
            with patch('ui.components.base.composed.status_bar_manager.QStatusBar'):
                manager = manager_class()
                manager.initialize(mock_context)
                assert manager.is_available == expected_available
