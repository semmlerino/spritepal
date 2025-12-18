"""
Essential integration tests for the ComposedDialog architecture.

This module provides minimal but comprehensive tests that validate the
composition-based dialog architecture works correctly without Qt complications.
"""
from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from ui.components.base.composed.button_box_manager import ButtonBoxManager
from ui.components.base.composed.composed_dialog import ComposedDialog
from ui.components.base.composed.message_dialog_manager import MessageDialogManager
from ui.components.base.composed.status_bar_manager import StatusBarManager


@pytest.mark.mock_only
@pytest.mark.integration
class TestComposedDialogEssentialIntegration:
    """Essential integration tests for the ComposedDialog architecture."""

    def test_end_to_end_dialog_creation_workflow(self):
        """Test the complete end-to-end dialog creation workflow."""

        # Setup layout mock with addWidget
        mock_layout_instance = MagicMock()
        mock_layout_instance.addWidget = MagicMock()
        mock_layout_class = MagicMock(return_value=mock_layout_instance)

        # Setup QDialogButtonBox mock
        mock_button_box_class = MagicMock()
        mock_button_box_class.StandardButton = MagicMock()
        mock_button_box_class.StandardButton.Ok = 1
        mock_button_box_class.StandardButton.Cancel = 2

        # Mock all Qt dependencies at the top level
        with patch.multiple(
            'ui.components.base.composed.composed_dialog',
            QDialog=MagicMock,
            QVBoxLayout=mock_layout_class,
            QWidget=MagicMock
        ), patch.multiple(
            'ui.components.base.composed.button_box_manager',
            QDialogButtonBox=mock_button_box_class
        ), patch.multiple(
            'ui.components.base.composed.status_bar_manager',
            QStatusBar=MagicMock
        ):
            # Create dialog with full configuration
            dialog = ComposedDialog(
                with_button_box=True,
                with_status_bar=True,
                custom_option="test_value"
            )

            # VALIDATION 1: Dialog structure is correct
            assert dialog is not None
            assert isinstance(dialog, ComposedDialog)
            assert hasattr(dialog, 'context')
            assert hasattr(dialog, 'components')
            assert hasattr(dialog, 'config')

            # VALIDATION 2: Configuration is stored correctly
            assert dialog.config['with_button_box'] is True
            assert dialog.config['with_status_bar'] is True
            assert dialog.config['custom_option'] == "test_value"

            # VALIDATION 3: All expected components are created
            assert len(dialog.components) == 5
            message_mgr = dialog.get_component("message_dialog")
            button_mgr = dialog.get_component("button_box")
            status_mgr = dialog.get_component("status_bar")

            assert message_mgr is not None
            assert button_mgr is not None
            assert status_mgr is not None

            # VALIDATION 4: Components are properly typed
            assert isinstance(message_mgr, MessageDialogManager)
            assert isinstance(button_mgr, ButtonBoxManager)
            assert isinstance(status_mgr, StatusBarManager)

            # VALIDATION 5: Context is properly configured
            context = dialog.context
            assert context.dialog == dialog
            assert context.config == dialog.config
            assert context.has_component("message_dialog")
            assert context.has_component("button_box")
            assert context.has_component("status_bar")

            # VALIDATION 6: Component cleanup works
            cleanup_called = []
            for component in dialog.components:
                original_cleanup = component.cleanup
                def track_cleanup():
                    cleanup_called.append(component)
                    original_cleanup()
                component.cleanup = track_cleanup

            # Simulate close event
            with patch('PySide6.QtWidgets.QDialog.closeEvent') as mock_parent_close:
                mock_close_event = Mock()
                dialog.closeEvent(mock_close_event)

                # Verify cleanup was called on all components
                assert len(cleanup_called) == 5
                mock_parent_close.assert_called_once_with(mock_close_event)

    def test_selective_component_creation_scenarios(self, qtbot):
        """Test various component configuration scenarios."""

        test_scenarios = [
            # (config, expected_component_names)
            ({}, ["message_dialog", "button_box"]),
            ({"with_button_box": True}, ["message_dialog", "button_box"]),
            ({"with_button_box": False}, ["message_dialog"]),
            ({"with_status_bar": True}, ["message_dialog", "button_box", "status_bar"]),
            ({"with_button_box": False, "with_status_bar": True}, ["message_dialog", "status_bar"]),
            ({"with_button_box": True, "with_status_bar": True}, ["message_dialog", "button_box", "status_bar"])
        ]

        # Setup layout mock with addWidget
        mock_layout_instance = MagicMock()
        mock_layout_instance.addWidget = MagicMock()
        mock_layout_class = MagicMock(return_value=mock_layout_instance)

        # Setup QDialogButtonBox mock
        mock_button_box_class = MagicMock()
        mock_button_box_class.StandardButton = MagicMock()
        mock_button_box_class.StandardButton.Ok = 1
        mock_button_box_class.StandardButton.Cancel = 2

        for config, expected_components in test_scenarios:
            with patch.multiple(
                'ui.components.base.composed.composed_dialog',
                QDialog=MagicMock,
                QVBoxLayout=mock_layout_class,
                QWidget=MagicMock
            ), patch.multiple(
                'ui.components.base.composed.button_box_manager',
                QDialogButtonBox=mock_button_box_class
            ), patch.multiple(
                'ui.components.base.composed.status_bar_manager',
                QStatusBar=MagicMock
            ):
                dialog = ComposedDialog(**config)
                qtbot.addWidget(dialog)

                # Add always-present components to expectation
                full_expected_components = expected_components + ["dialog_signals", "qt_dialog_signals"]

                # Verify expected components exist
                for component_name in full_expected_components:
                    component = dialog.get_component(component_name)
                    assert component is not None, f"Expected component '{component_name}' not found"

                # Verify unexpected components don't exist
                # Only check variable components
                variable_components = ["button_box", "status_bar"]
                for component_name in variable_components:
                    if component_name not in expected_components:
                        component = dialog.get_component(component_name)
                        assert component is None, f"Unexpected component '{component_name}' found"

                # Verify component count matches
                assert len(dialog.components) == len(full_expected_components)

    def test_message_dialog_manager_end_to_end(self):
        """Test MessageDialogManager end-to-end functionality."""

        with patch('ui.components.base.composed.message_dialog_manager.QMessageBox') as mock_messagebox:
            # Create manager and mock dialog context
            manager = MessageDialogManager()
            mock_dialog = Mock()
            mock_context = Mock()
            mock_context.dialog = mock_dialog

            # Track signals
            signals_emitted = []
            manager.message_shown.connect(lambda msg_type, msg: signals_emitted.append((msg_type, msg)))

            # Initialize manager
            manager.initialize(mock_context)
            assert manager.is_initialized is True

            # Test all message types
            test_cases = [
                ('show_info', 'information', 'Info Title', 'Info message'),
                ('show_error', 'critical', 'Error Title', 'Error message'),
                ('show_warning', 'warning', 'Warning Title', 'Warning message')
            ]

            for method_name, messagebox_method, title, message in test_cases:
                # Call the method
                getattr(manager, method_name)(title, message)

                # Verify Qt method was called
                qt_method = getattr(mock_messagebox, messagebox_method)
                qt_method.assert_called_with(mock_dialog, title, message)

                # Verify signal was emitted
                expected_signal_type = method_name.replace('show_', '')
                assert (expected_signal_type, message) in signals_emitted

            # Test confirmation dialog
            mock_messagebox.question.return_value = mock_messagebox.StandardButton.Yes
            result = manager.confirm_action("Confirm", "Are you sure?")

            mock_messagebox.question.assert_called_with(mock_dialog, "Confirm", "Are you sure?")
            assert result is True
            assert ("confirmation", "Are you sure?") in signals_emitted

            # Test cleanup
            manager.cleanup()
            assert manager.is_initialized is False

    def test_component_lifecycle_management(self):
        """Test component lifecycle management throughout dialog lifetime."""

        # Setup layout mock
        mock_layout_instance = MagicMock()
        mock_layout_instance.addWidget = MagicMock()
        mock_layout_class = MagicMock(return_value=mock_layout_instance)

        # Setup QDialogButtonBox mock
        mock_button_box_class = MagicMock()
        mock_button_box_class.StandardButton = MagicMock()
        mock_button_box_class.StandardButton.Ok = 1
        mock_button_box_class.StandardButton.Cancel = 2

        with patch.multiple(
            'ui.components.base.composed.composed_dialog',
            QDialog=MagicMock,
            QVBoxLayout=mock_layout_class,
            QWidget=MagicMock
        ), patch.multiple(
            'ui.components.base.composed.button_box_manager',
            QDialogButtonBox=mock_button_box_class
        ):
            dialog = ComposedDialog(with_button_box=True)

            # PHASE 1: Initial state after creation
            assert len(dialog.components) == 4  # message + button + 2 signal managers

            list(dialog.components)
            message_mgr = dialog.get_component("message_dialog")
            button_mgr = dialog.get_component("button_box")

            # PHASE 2: Components are functional
            assert message_mgr.is_initialized is True
            assert button_mgr.is_available is True

            # PHASE 3: Context management
            context = dialog.context
            assert context.get_component("message_dialog") == message_mgr
            assert context.get_component("button_box") == button_mgr

            # PHASE 4: Dynamic component management
            # Test context operations
            test_component = Mock()
            context.register_component("test_dynamic", test_component)
            assert context.get_component("test_dynamic") == test_component

            context.unregister_component("test_dynamic")
            assert context.get_component("test_dynamic") is None

            # PHASE 5: Cleanup phase
            cleanup_tracking = {'message': False, 'button': False}

            def track_message_cleanup():
                cleanup_tracking['message'] = True

            def track_button_cleanup():
                cleanup_tracking['button'] = True

            message_mgr.cleanup = track_message_cleanup
            button_mgr.cleanup = track_button_cleanup

            # Trigger cleanup through close event
            mock_close_event = Mock()
            with patch('PySide6.QtWidgets.QDialog.closeEvent'):
                dialog.closeEvent(mock_close_event)

            # Verify all components were cleaned up
            assert cleanup_tracking['message'] is True
            assert cleanup_tracking['button'] is True

    def test_subclass_customization_workflow(self):
        """Test dialog subclass customization works correctly."""

        class TestCustomDialog(ComposedDialog):
            def __init__(self, **config):
                self.custom_setup_called = False
                self.custom_widgets_created = []
                super().__init__(**config)

            def setup_ui(self):
                self.custom_setup_called = True
                # Simulate adding custom widgets
                self.custom_widgets_created.append("custom_label")
                self.custom_widgets_created.append("custom_button")

        # Setup layout mock
        mock_layout_instance = MagicMock()
        mock_layout_instance.addWidget = MagicMock()
        mock_layout_class = MagicMock(return_value=mock_layout_instance)

        with patch.multiple(
            'ui.components.base.composed.composed_dialog',
            QDialog=MagicMock,
            QVBoxLayout=mock_layout_class,
            QWidget=MagicMock
        ):
            # Create custom dialog
            dialog = TestCustomDialog(with_status_bar=True, custom_param="test")

            # VALIDATION 1: Custom setup was called
            assert dialog.custom_setup_called is True

            # VALIDATION 2: Custom widgets were "created"
            assert len(dialog.custom_widgets_created) == 2
            assert "custom_label" in dialog.custom_widgets_created
            assert "custom_button" in dialog.custom_widgets_created

            # VALIDATION 3: Base functionality still works
            assert dialog.get_component("message_dialog") is not None
            assert dialog.get_component("button_box") is not None
            assert dialog.get_component("status_bar") is not None

            # VALIDATION 4: Configuration is preserved
            assert dialog.config["custom_param"] == "test"
            assert dialog.config["with_status_bar"] is True

    def test_architecture_integration_contract(self):
        """Test that the architecture fulfills its integration contract."""

        # Setup layout mock
        mock_layout_instance = MagicMock()
        mock_layout_instance.addWidget = MagicMock()
        mock_layout_class = MagicMock(return_value=mock_layout_instance)

        # Setup QDialogButtonBox mock
        mock_button_box_class = MagicMock()
        mock_button_box_class.StandardButton = MagicMock()
        mock_button_box_class.StandardButton.Ok = 1
        mock_button_box_class.StandardButton.Cancel = 2

        with patch.multiple(
            'ui.components.base.composed.composed_dialog',
            QDialog=MagicMock,
            QVBoxLayout=mock_layout_class,
            QWidget=MagicMock
        ), patch.multiple(
            'ui.components.base.composed.button_box_manager',
            QDialogButtonBox=mock_button_box_class
        ), patch.multiple(
            'ui.components.base.composed.status_bar_manager',
            QStatusBar=MagicMock
        ):
            dialog = ComposedDialog(
                with_button_box=True,
                with_status_bar=True
            )

            # CONTRACT 1: Composition over inheritance
            assert hasattr(dialog, 'components')
            assert len(dialog.components) > 0
            assert all(hasattr(c, 'initialize') for c in dialog.components)
            assert all(hasattr(c, 'cleanup') for c in dialog.components)

            # CONTRACT 2: Shared context for communication
            context = dialog.context
            assert hasattr(context, 'register_component')
            assert hasattr(context, 'get_component')
            assert hasattr(context, 'has_component')

            # CONTRACT 3: Configuration-driven initialization
            assert hasattr(dialog, 'config')
            assert len(dialog.config) >= 2  # at least button box and status bar config

            # CONTRACT 4: Component accessibility
            for component_name in ["message_dialog", "button_box", "status_bar"]:
                component = dialog.get_component(component_name)
                assert component is not None
                assert component == context.get_component(component_name)

            # CONTRACT 5: Proper lifecycle management
            # All components should be initialized
            message_mgr = dialog.get_component("message_dialog")
            button_mgr = dialog.get_component("button_box")
            status_mgr = dialog.get_component("status_bar")

            assert message_mgr.is_initialized is True
            assert button_mgr.is_available is True
            assert status_mgr.is_available is True

            # CONTRACT 6: Clean separation of concerns
            # Each manager should handle its own Qt widgets
            assert hasattr(message_mgr, 'show_info')
            assert hasattr(message_mgr, 'show_error')
            assert hasattr(button_mgr, 'add_button')
            assert hasattr(button_mgr, 'get_button')
            assert hasattr(status_mgr, 'show_message')
            assert hasattr(status_mgr, 'clear_message')

    @pytest.mark.parametrize("error_condition", [
        "missing_config",
        "invalid_dialog_context",
        "duplicate_component_registration",
    ])
    def test_error_handling_robustness(self, error_condition):
        """Test error handling in various failure scenarios."""

        if error_condition == "missing_config":
            # Test manager initialization with missing config
            manager = ButtonBoxManager()
            mock_context = Mock()
            del mock_context.config

            with pytest.raises(AttributeError, match="must have a 'config' attribute"):
                manager.initialize(mock_context)

        elif error_condition == "invalid_dialog_context":
            # Test message manager with invalid dialog
            manager = MessageDialogManager()
            mock_context = Mock()
            mock_context.dialog = "not a dialog"

            with pytest.raises(TypeError, match="Context must be a QDialog"):
                manager.initialize(mock_context)

        elif error_condition == "duplicate_component_registration":
            # Setup layout mock
            mock_layout_instance = MagicMock()
            mock_layout_instance.addWidget = MagicMock()
            mock_layout_class = MagicMock(return_value=mock_layout_instance)

            # Test duplicate component registration
            with patch.multiple(
                'ui.components.base.composed.composed_dialog',
                QDialog=MagicMock,
                QVBoxLayout=mock_layout_class,
                QWidget=MagicMock
            ):
                dialog = ComposedDialog()
                context = dialog.context

                test_component = Mock()
                context.register_component("test", test_component)

                with pytest.raises(ValueError, match="already registered"):
                    context.register_component("test", test_component)
