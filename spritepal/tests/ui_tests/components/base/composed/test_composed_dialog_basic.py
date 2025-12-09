"""
Basic functionality tests for the ComposedDialog architecture.

This module provides basic tests to verify that the composition-based dialog
architecture components can be imported and instantiated correctly.
"""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

# Test imports to ensure no import errors
from ui.components.base.composed.button_box_manager import ButtonBoxManager
from ui.components.base.composed.composed_dialog import ComposedDialog
from ui.components.base.composed.dialog_context import DialogContext
from ui.components.base.composed.message_dialog_manager import MessageDialogManager
from ui.components.base.composed.status_bar_manager import StatusBarManager


class TestComposedDialogBasics:
    """Basic tests for ComposedDialog architecture components."""

    def test_imports_successful(self) -> None:
        """Test that all components can be imported without errors."""
        # If we get here, all imports were successful
        assert ButtonBoxManager is not None
        assert ComposedDialog is not None
        assert DialogContext is not None
        assert MessageDialogManager is not None
        assert StatusBarManager is not None

    def test_component_classes_exist(self) -> None:
        """Test that component classes are properly defined."""
        # Verify classes have expected attributes
        assert hasattr(ButtonBoxManager, 'initialize')
        assert hasattr(MessageDialogManager, 'initialize')
        assert hasattr(StatusBarManager, 'initialize')
        assert hasattr(ComposedDialog, '__init__')
        assert hasattr(DialogContext, 'register_component')

    def test_dialog_context_basic_functionality(self) -> None:
        """Test DialogContext basic functionality without Qt."""
        # Create mock dialog and layout
        mock_dialog = Mock()
        mock_layout = Mock()
        mock_widget = Mock()

        context = DialogContext(
            dialog=mock_dialog,
            main_layout=mock_layout,
            content_widget=mock_widget,
            config={"test": True}
        )

        # Test component registration
        mock_component = Mock()
        context.register_component("test_component", mock_component)

        # Test component retrieval
        assert context.get_component("test_component") == mock_component
        assert context.get_component("nonexistent") is None

        # Test component existence check
        assert context.has_component("test_component") is True
        assert context.has_component("nonexistent") is False

        # Test component removal
        context.unregister_component("test_component")
        assert context.has_component("test_component") is False

    def test_dialog_context_error_handling(self) -> None:
        """Test DialogContext error handling."""
        mock_dialog = Mock()
        mock_layout = Mock()
        mock_widget = Mock()

        context = DialogContext(
            dialog=mock_dialog,
            main_layout=mock_layout,
            content_widget=mock_widget
        )

        # Test duplicate registration error
        mock_component = Mock()
        context.register_component("duplicate", mock_component)

        with pytest.raises(ValueError, match="already registered"):
            context.register_component("duplicate", mock_component)

        # Test removing non-existent component error
        with pytest.raises(KeyError, match="not registered"):
            context.unregister_component("nonexistent")

    def test_message_dialog_manager_basic_functionality(self) -> None:
        """Test MessageDialogManager basic functionality without Qt."""
        manager = MessageDialogManager()

        # Test initial state
        assert not manager.is_initialized

        # Test initialization with non-dialog object should fail
        with pytest.raises(TypeError, match="must be a QDialog"):
            manager.initialize("not a dialog")

        # Test methods without initialization should fail
        with pytest.raises(RuntimeError, match="not initialized"):
            manager.show_info("title", "message")

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.show_error("title", "message")

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.show_warning("title", "message")

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.confirm_action("title", "message")

    def test_button_box_manager_basic_functionality(self) -> None:
        """Test ButtonBoxManager basic functionality without Qt."""
        manager = ButtonBoxManager()

        # Test initial state
        assert not manager.is_available
        assert manager.custom_button_count == 0

        # Test methods without initialization should fail
        with pytest.raises(RuntimeError, match="not created"):
            manager.add_button("Test")

        # Test initialization with invalid context
        mock_context = Mock()
        del mock_context.config  # Remove required attribute

        with pytest.raises(AttributeError, match="must have a 'config' attribute"):
            manager.initialize(mock_context)

    def test_status_bar_manager_basic_functionality(self) -> None:
        """Test StatusBarManager basic functionality without Qt."""
        manager = StatusBarManager()

        # Test initial state
        assert not manager.is_available

        # Test methods without initialization should fail
        with pytest.raises(RuntimeError, match="not created"):
            manager.show_message("Test message")

        with pytest.raises(RuntimeError, match="not created"):
            manager.clear_message()

        # Test initialization with invalid context
        mock_context = Mock()
        del mock_context.config  # Remove required attribute

        with pytest.raises(AttributeError, match="must have a 'config' attribute"):
            manager.initialize(mock_context)

    def test_component_repr_methods(self) -> None:
        """Test string representations of components."""
        # Test MessageDialogManager repr
        msg_manager = MessageDialogManager()
        repr_str = repr(msg_manager)
        assert "MessageDialogManager" in repr_str
        assert "not initialized" in repr_str

        # Test ButtonBoxManager repr
        btn_manager = ButtonBoxManager()
        repr_str = repr(btn_manager)
        assert "ButtonBoxManager" in repr_str
        assert "not available" in repr_str
        assert "0 custom buttons" in repr_str

        # Test StatusBarManager repr
        status_manager = StatusBarManager()
        repr_str = repr(status_manager)
        assert "StatusBarManager" in repr_str
        assert "not available" in repr_str
        assert "0 permanent widgets" in repr_str

    def test_manager_cleanup_methods(self) -> None:
        """Test manager cleanup methods work without errors."""
        # Test all managers have cleanup methods and they run without error
        msg_manager = MessageDialogManager()
        btn_manager = ButtonBoxManager()
        status_manager = StatusBarManager()

        # These should not raise errors even when not initialized
        msg_manager.cleanup()
        btn_manager.cleanup()
        status_manager.cleanup()

        # Verify cleanup resets state
        assert msg_manager._dialog is None
        assert btn_manager._button_box is None
        assert status_manager._status_bar is None

    @pytest.mark.parametrize("config,expected_components", [
        ({}, ["message_dialog", "button_box"]),  # Default config
        ({"with_button_box": True}, ["message_dialog", "button_box"]),
        ({"with_button_box": False}, ["message_dialog"]),
        ({"with_status_bar": True}, ["message_dialog", "button_box", "status_bar"]),
        ({"with_button_box": False, "with_status_bar": True}, ["message_dialog", "status_bar"]),
        ({"with_button_box": True, "with_status_bar": True}, ["message_dialog", "button_box", "status_bar"]),
    ])
    def test_composed_dialog_configuration_logic(self, config, expected_components) -> None:
        """Test ComposedDialog component initialization logic without Qt."""
        with patch('ui.components.base.composed.composed_dialog.QDialog.__init__'):
            with patch('ui.components.base.composed.composed_dialog.QVBoxLayout'):
                with patch('ui.components.base.composed.composed_dialog.QWidget'):
                    # Mock the managers to avoid Qt dependencies
                    with patch('ui.components.base.composed.composed_dialog.MessageDialogManager') as MockMessage:
                        with patch('ui.components.base.composed.composed_dialog.ButtonBoxManager') as MockButton:
                            with patch('ui.components.base.composed.composed_dialog.StatusBarManager') as MockStatus:

                                # Create mock instances
                                mock_msg = Mock()
                                mock_btn = Mock()
                                mock_status = Mock()

                                MockMessage.return_value = mock_msg
                                MockButton.return_value = mock_btn
                                MockStatus.return_value = mock_status

                                # Create dialog (constructor will be mocked)
                                ComposedDialog(**config)

                                # Verify expected managers were created
                                if "message_dialog" in expected_components:
                                    MockMessage.assert_called_once()
                                    mock_msg.initialize.assert_called_once()

                                if "button_box" in expected_components:
                                    MockButton.assert_called_once()
                                    mock_btn.initialize.assert_called_once()
                                else:
                                    MockButton.assert_not_called()

                                if "status_bar" in expected_components:
                                    MockStatus.assert_called_once()
                                    mock_status.initialize.assert_called_once()
                                else:
                                    MockStatus.assert_not_called()
