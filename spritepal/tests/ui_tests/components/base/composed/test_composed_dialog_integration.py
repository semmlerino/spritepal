"""
Comprehensive integration tests for the ComposedDialog architecture.

This module provides comprehensive testing for the composition-based dialog
architecture, validating that all components work together correctly and
that the architecture provides the expected functionality.
"""
from __future__ import annotations

import os
import sys
from typing import Any
from unittest import mock
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

# Import test infrastructure
from tests.infrastructure.qt_real_testing import QtTestCase
from ui.components.base.composed.button_box_manager import ButtonBoxManager
from ui.components.base.composed.composed_dialog import ComposedDialog
from ui.components.base.composed.dialog_context import DialogContext
from ui.components.base.composed.message_dialog_manager import MessageDialogManager
from ui.components.base.composed.status_bar_manager import StatusBarManager


class SampleDialog(ComposedDialog):
    """Test dialog implementation for integration testing with realistic UI."""

    def __init__(self, parent: Any = None, **config: Any) -> None:
        """Initialize test dialog with custom UI setup."""
        self.setup_ui_called = False
        self.custom_widget_created = False
        self.form_valid = False
        super().__init__(parent, **config)

    def setup_ui(self) -> None:
        """Set up custom UI elements for testing."""
        self.setup_ui_called = True

        # Create main layout
        layout = QVBoxLayout(self.content_widget)

        # Add title label
        self.test_label = QLabel("Test Dialog Content")
        layout.addWidget(self.test_label)

        # Add form controls
        form_layout = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter name...")
        self.validate_button = QPushButton("Validate")
        self.validate_button.clicked.connect(self._validate_form)

        form_layout.addWidget(QLabel("Name:"))
        form_layout.addWidget(self.name_input)
        form_layout.addWidget(self.validate_button)
        layout.addLayout(form_layout)

        # Add progress bar for testing status updates
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Add result label
        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: green;")
        layout.addWidget(self.result_label)

        self.custom_widget_created = True

    def _validate_form(self) -> None:
        """Validate the form and update UI state."""
        name = self.name_input.text().strip()
        self.form_valid = len(name) >= 3

        if self.form_valid:
            self.result_label.setText(f"Valid name: {name}")
            self.result_label.setStyleSheet("color: green;")

            # Update button box state if available
            button_manager = self.get_component("button_box")
            if button_manager:
                ok_button = button_manager.get_button(QDialogButtonBox.StandardButton.Ok)
                if ok_button:
                    ok_button.setEnabled(True)
        else:
            self.result_label.setText("Name must be at least 3 characters")
            self.result_label.setStyleSheet("color: red;")

            # Disable OK button if available
            button_manager = self.get_component("button_box")
            if button_manager:
                ok_button = button_manager.get_button(QDialogButtonBox.StandardButton.Ok)
                if ok_button:
                    ok_button.setEnabled(False)

    def simulate_progress(self, value: int) -> None:
        """Simulate progress for testing status bar integration."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(value)

        # Update status bar if available
        status_manager = self.get_component("status_bar")
        if status_manager:
            status_manager.show_message(f"Processing... {value}%")

@pytest.mark.qt_real
@pytest.mark.integration
@pytest.mark.mock_only  # Allow running in headless environment
class TestComposedDialogIntegration(QtTestCase):
    """Integration tests for the ComposedDialog architecture."""

    def setup_method(self):
        """Setup before each test."""
        super().setup_method()
        # Ensure we have a QApplication for Qt widgets
        if not QApplication.instance():
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
            self.app = QApplication(sys.argv)
        else:
            self.app = QApplication.instance()

    def test_basic_dialog_creation_with_defaults(self) -> None:
        """Test dialog can be created with default configuration."""
        dialog = self.create_widget(SampleDialog)

        # Verify dialog was created successfully
        assert dialog is not None
        assert isinstance(dialog, ComposedDialog)
        assert dialog.setup_ui_called is True
        assert dialog.custom_widget_created is True

        # Verify main layout and content widget exist
        assert dialog.main_layout is not None
        assert dialog.content_widget is not None

        # Verify context was created
        assert dialog.context is not None
        assert isinstance(dialog.context, DialogContext)

        # Verify message dialog manager is always created
        message_manager = dialog.get_component("message_dialog")
        assert message_manager is not None
        assert isinstance(message_manager, MessageDialogManager)

        # Verify button box is created by default
        button_manager = dialog.get_component("button_box")
        assert button_manager is not None
        assert isinstance(button_manager, ButtonBoxManager)

        # Verify status bar is NOT created by default
        status_manager = dialog.get_component("status_bar")
        assert status_manager is None

    def test_dialog_creation_with_status_bar(self, qtbot: Any) -> None:
        """Test dialog creation with status bar enabled."""
        dialog = SampleDialog(with_status_bar=True)
        qtbot.addWidget(dialog)

        # Verify all components are created
        assert dialog.get_component("message_dialog") is not None
        assert dialog.get_component("button_box") is not None

        # Verify status bar is created
        status_manager = dialog.get_component("status_bar")
        assert status_manager is not None
        assert isinstance(status_manager, StatusBarManager)
        assert status_manager.is_available is True

    def test_dialog_creation_without_button_box(self, qtbot: Any) -> None:
        """Test dialog creation with button box disabled."""
        dialog = SampleDialog(with_button_box=False)
        qtbot.addWidget(dialog)

        # Verify message dialog is still created
        assert dialog.get_component("message_dialog") is not None

        # Verify button box is NOT created
        button_manager = dialog.get_component("button_box")
        assert button_manager is None

        # Verify status bar is still not created by default
        status_manager = dialog.get_component("status_bar")
        assert status_manager is None

    def test_dialog_creation_with_all_components(self, qtbot: Any) -> None:
        """Test dialog creation with all components enabled."""
        dialog = SampleDialog(with_status_bar=True, with_button_box=True)
        qtbot.addWidget(dialog)

        # Verify all components are created
        message_manager = dialog.get_component("message_dialog")
        button_manager = dialog.get_component("button_box")
        status_manager = dialog.get_component("status_bar")

        assert message_manager is not None
        assert button_manager is not None
        assert status_manager is not None

        # Verify components are properly initialized
        assert message_manager.is_initialized is True
        assert button_manager.is_available is True
        assert status_manager.is_available is True

    @patch('PySide6.QtWidgets.QMessageBox.information')
    def test_message_dialog_manager_integration(self, mock_info: Mock, qtbot: Any) -> None:
        """Test MessageDialogManager integration with ComposedDialog."""
        dialog = SampleDialog()
        qtbot.addWidget(dialog)

        message_manager = dialog.get_component("message_dialog")
        assert message_manager is not None

        # Test signal collection for message_shown signal
        signal_args: list[tuple] = []
        message_manager.message_shown.connect(lambda msg_type, msg: signal_args.append((msg_type, msg)))

        # Test show_info method
        message_manager.show_info("Test Title", "Test message")

        # Process events to ensure signal emission
        QApplication.processEvents()

        # Verify QMessageBox.information was called
        mock_info.assert_called_once_with(dialog, "Test Title", "Test message")

        # Verify signal was emitted
        assert len(signal_args) == 1
        assert signal_args[0][0] == "info"
        assert signal_args[0][1] == "Test message"

    @patch('PySide6.QtWidgets.QMessageBox.critical')
    def test_message_dialog_error_handling(self, mock_critical: Mock, qtbot: Any) -> None:
        """Test error message handling in MessageDialogManager."""
        dialog = SampleDialog()
        qtbot.addWidget(dialog)

        message_manager = dialog.get_component("message_dialog")

        # Test signal collection for message_shown signal
        signal_args: list[tuple] = []
        message_manager.message_shown.connect(lambda msg_type, msg: signal_args.append((msg_type, msg)))

        # Test show_error method
        message_manager.show_error("Error Title", "Error occurred")

        # Process events to ensure signal emission
        QApplication.processEvents()

        # Verify QMessageBox.critical was called
        mock_critical.assert_called_once_with(dialog, "Error Title", "Error occurred")

        # Verify signal was emitted with correct type
        assert len(signal_args) == 1
        assert signal_args[0][0] == "error"
        assert signal_args[0][1] == "Error occurred"

    @patch('PySide6.QtWidgets.QMessageBox.question', return_value=mock.MagicMock())
    def test_message_dialog_confirmation(self, mock_question: Mock, qtbot: Any) -> None:
        """Test confirmation dialog handling."""
        # Set up the mock to return Yes
        from PySide6.QtWidgets import QMessageBox
        mock_question.return_value = QMessageBox.StandardButton.Yes

        dialog = SampleDialog()
        qtbot.addWidget(dialog)

        message_manager = dialog.get_component("message_dialog")

        # Test signal collection for message_shown signal
        signal_args: list[tuple] = []
        message_manager.message_shown.connect(lambda msg_type, msg: signal_args.append((msg_type, msg)))

        # Test confirm_action method
        result = message_manager.confirm_action("Confirm Title", "Are you sure?")

        # Process events to ensure signal emission
        QApplication.processEvents()

        # Verify QMessageBox.question was called
        mock_question.assert_called_once_with(dialog, "Confirm Title", "Are you sure?")

        # Verify return value
        assert result is True

        # Verify signal was emitted
        assert len(signal_args) == 1
        assert signal_args[0][0] == "confirmation"
        assert signal_args[0][1] == "Are you sure?"

    def test_button_box_manager_integration(self, qtbot: Any) -> None:
        """Test ButtonBoxManager integration with ComposedDialog."""
        dialog = SampleDialog()
        qtbot.addWidget(dialog)

        button_manager = dialog.get_component("button_box")
        assert button_manager is not None

        # Test signal collection for button manager signals
        accepted_calls: list[bool] = []
        rejected_calls: list[bool] = []

        button_manager.accepted.connect(lambda: accepted_calls.append(True))
        button_manager.rejected.connect(lambda: rejected_calls.append(True))

        # Verify button box was created and added to layout
        assert button_manager.is_available is True
        button_box = button_manager.button_box
        assert button_box is not None
        assert button_box.parent() is not None  # Verify it's in the layout

        # Get standard buttons and verify they exist
        ok_button = button_manager.get_button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = button_manager.get_button(QDialogButtonBox.StandardButton.Cancel)

        assert ok_button is not None
        assert cancel_button is not None
        assert ok_button.isEnabled()  # Initially enabled
        assert cancel_button.isEnabled()  # Always enabled

        # Test real button clicking with Qt events
        QTest.mouseClick(ok_button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert len(accepted_calls) == 1

        QTest.mouseClick(cancel_button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert len(rejected_calls) == 1

    def test_button_box_custom_buttons(self, qtbot: Any) -> None:
        """Test custom button functionality in ButtonBoxManager."""
        dialog = SampleDialog()
        qtbot.addWidget(dialog)

        button_manager = dialog.get_component("button_box")
        assert button_manager is not None

        # Test signal collection for custom button clicks
        clicked_buttons: list[str] = []
        button_manager.button_clicked.connect(lambda btn_text: clicked_buttons.append(btn_text))

        # Add custom button with callback
        custom_callback = Mock()
        custom_button = button_manager.add_button("Custom", callback=custom_callback)

        assert custom_button is not None
        assert button_manager.custom_button_count == 1
        assert custom_button.text() == "Custom"  # Verify real button properties
        assert custom_button.isEnabled()  # Verify initial state

        # Test real custom button click with Qt events
        QTest.mouseClick(custom_button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()

        # Verify callback was called
        custom_callback.assert_called_once()

        # Verify signal was emitted with correct button text
        assert len(clicked_buttons) == 1
        assert clicked_buttons[0] == "Custom"

    def test_status_bar_manager_integration(self, qtbot: Any) -> None:
        """Test StatusBarManager integration with ComposedDialog."""
        dialog = SampleDialog(with_status_bar=True)
        qtbot.addWidget(dialog)

        status_manager = dialog.get_component("status_bar")
        assert status_manager is not None

        # Test signal collection for status changes
        status_messages: list[str] = []
        status_manager.status_changed.connect(lambda msg: status_messages.append(msg))

        # Verify status bar was created and is accessible
        assert status_manager.is_available is True
        status_bar = status_manager.status_bar
        assert status_bar is not None
        assert status_bar.parent() is not None  # Verify it's in the layout

        # Test showing message and verify real status bar state
        status_manager.show_message("Test status message")
        QApplication.processEvents()

        # Verify signal was emitted
        assert len(status_messages) == 1
        assert status_messages[0] == "Test status message"

        # Verify real status bar shows the message
        assert status_bar.currentMessage() == "Test status message"

        # Test clearing message
        status_manager.clear_message()
        QApplication.processEvents()

        # Verify signal was emitted again
        assert len(status_messages) == 2
        assert status_messages[1] == ""

        # Verify real status bar is cleared
        assert status_bar.currentMessage() == ""

    def test_component_access_via_get_component(self, qtbot: Any) -> None:
        """Test component access through get_component method."""
        dialog = SampleDialog(with_status_bar=True)
        qtbot.addWidget(dialog)

        # Test accessing existing components
        message_manager = dialog.get_component("message_dialog")
        button_manager = dialog.get_component("button_box")
        status_manager = dialog.get_component("status_bar")

        assert message_manager is not None
        assert button_manager is not None
        assert status_manager is not None

        # Test accessing non-existent component
        non_existent = dialog.get_component("non_existent")
        assert non_existent is None

        # Verify components are the correct types
        assert isinstance(message_manager, MessageDialogManager)
        assert isinstance(button_manager, ButtonBoxManager)
        assert isinstance(status_manager, StatusBarManager)

    def test_dialog_context_component_registration(self, qtbot: Any) -> None:
        """Test DialogContext component registration functionality."""
        dialog = SampleDialog()
        qtbot.addWidget(dialog)

        context = dialog.context

        # Test that components are properly registered
        assert context.has_component("message_dialog") is True
        assert context.has_component("button_box") is True
        assert context.has_component("status_bar") is False  # Not enabled by default

        # Test getting components through context
        message_manager = context.get_component("message_dialog")
        assert message_manager is not None
        assert isinstance(message_manager, MessageDialogManager)

        # Test component registration error handling
        with pytest.raises(ValueError, match="already registered"):
            context.register_component("message_dialog", Mock())

    def test_cleanup_on_close_event(self, qtbot: Any) -> None:
        """Test that cleanup is called on all components during closeEvent."""
        dialog = SampleDialog(with_status_bar=True)
        qtbot.addWidget(dialog)

        # Get all components and mock their cleanup methods
        message_manager = dialog.get_component("message_dialog")
        button_manager = dialog.get_component("button_box")
        status_manager = dialog.get_component("status_bar")

        assert message_manager is not None
        assert button_manager is not None
        assert status_manager is not None

        # Mock cleanup methods
        message_manager.cleanup = Mock()
        button_manager.cleanup = Mock()
        status_manager.cleanup = Mock()

        # Create close event and send it to dialog
        close_event = QCloseEvent()
        dialog.closeEvent(close_event)

        # Verify all cleanup methods were called
        message_manager.cleanup.assert_called_once()
        button_manager.cleanup.assert_called_once()
        status_manager.cleanup.assert_called_once()

    def test_dialog_with_custom_configuration(self, qtbot: Any) -> None:
        """Test dialog creation with custom button configuration."""
        custom_buttons = (
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Apply |
            QDialogButtonBox.StandardButton.Cancel
        )

        dialog = SampleDialog(
            buttons=custom_buttons,
            with_status_bar=True,
            custom_config_value="test_value"
        )
        qtbot.addWidget(dialog)

        # Verify custom configuration is stored
        assert dialog.config.get("custom_config_value") == "test_value"

        # Verify custom buttons were created
        button_manager = dialog.get_component("button_box")
        assert button_manager is not None

        ok_button = button_manager.get_button(QDialogButtonBox.StandardButton.Ok)
        apply_button = button_manager.get_button(QDialogButtonBox.StandardButton.Apply)
        cancel_button = button_manager.get_button(QDialogButtonBox.StandardButton.Cancel)

        assert ok_button is not None
        assert apply_button is not None
        assert cancel_button is not None

    def test_component_lifecycle_management(self, qtbot: Any) -> None:
        """Test that components are properly managed throughout dialog lifecycle."""
        dialog = SampleDialog(with_status_bar=True)
        qtbot.addWidget(dialog)

        # Verify all components are in the components list
        assert len(dialog.components) == 3  # message, button, status

        # Verify components are properly tracked
        component_names = ["message_dialog", "button_box", "status_bar"]
        for name in component_names:
            component = dialog.get_component(name)
            assert component is not None
            assert component in dialog.components

        # Test component removal from context
        context = dialog.context
        context.unregister_component("status_bar")

        # Verify component was removed from context
        assert context.has_component("status_bar") is False
        assert context.get_component("status_bar") is None

        # But still in dialog.components list (for cleanup)
        status_manager_in_list = next(
            (c for c in dialog.components if isinstance(c, StatusBarManager)),
            None
        )
        assert status_manager_in_list is not None

    def test_dialog_without_setup_ui_method(self, qtbot: Any) -> None:
        """Test dialog creation when subclass doesn't implement setup_ui."""
        class MinimalDialog(ComposedDialog):
            pass

        # Should not raise an error
        dialog = MinimalDialog()
        qtbot.addWidget(dialog)

        # Verify basic components are still created
        assert dialog.get_component("message_dialog") is not None
        assert dialog.get_component("button_box") is not None
        assert dialog.get_component("status_bar") is None

    def test_button_manager_dialog_connection(self, qtbot: Any) -> None:
        """Test that ButtonBoxManager properly connects to dialog accept/reject."""
        dialog = SampleDialog()
        qtbot.addWidget(dialog)

        button_manager = dialog.get_component("button_box")
        assert button_manager is not None

        # Test signal collection for button manager signals
        accepted_calls: list[bool] = []
        rejected_calls: list[bool] = []

        button_manager.accepted.connect(lambda: accepted_calls.append(True))
        button_manager.rejected.connect(lambda: rejected_calls.append(True))

        # Verify button box exists and is properly connected
        button_box = button_manager.button_box
        assert button_box is not None

        # Test real button clicking to verify signal forwarding
        ok_button = button_manager.get_button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = button_manager.get_button(QDialogButtonBox.StandardButton.Cancel)

        assert ok_button is not None
        assert cancel_button is not None

        # Click buttons and verify real signal emission
        QTest.mouseClick(ok_button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert len(accepted_calls) == 1

        QTest.mouseClick(cancel_button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert len(rejected_calls) == 1

        # Test that signals properly chain through the button box
        button_box.accepted.emit()
        QApplication.processEvents()
        assert len(accepted_calls) == 2  # Should be called again

        button_box.rejected.emit()
        QApplication.processEvents()
        assert len(rejected_calls) == 2  # Should be called again

    def test_complex_dialog_workflow(self, qtbot: Any) -> None:
        """Test a complex workflow involving multiple components."""
        dialog = SampleDialog(with_status_bar=True)
        qtbot.addWidget(dialog)

        # Get all components
        message_manager = dialog.get_component("message_dialog")
        button_manager = dialog.get_component("button_box")
        status_manager = dialog.get_component("status_bar")

        assert message_manager is not None
        assert button_manager is not None
        assert status_manager is not None

        # Set up signal collection
        message_events: list[tuple] = []
        status_events: list[str] = []
        button_events: list[str] = []

        message_manager.message_shown.connect(lambda msg_type, msg: message_events.append((msg_type, msg)))
        status_manager.status_changed.connect(lambda msg: status_events.append(msg))
        button_manager.button_clicked.connect(lambda btn: button_events.append(btn))

        # Simulate complex workflow with real component interaction
        status_manager.show_message("Loading data...")
        QApplication.processEvents()

        # Verify real status bar shows loading message
        status_bar = status_manager.status_bar
        assert status_bar.currentMessage() == "Loading data..."

        # Add custom button and verify it exists
        process_button = button_manager.add_button("Process Data")
        assert process_button.text() == "Process Data"
        assert process_button.isEnabled()

        # Show status update
        status_manager.show_message("Processing...")
        QApplication.processEvents()
        assert status_bar.currentMessage() == "Processing..."

        # Click custom button with real Qt events
        QTest.mouseClick(process_button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()

        # Show completion message with mocked QMessageBox
        with patch('PySide6.QtWidgets.QMessageBox.information') as mock_info:
            message_manager.show_info("Complete", "Processing complete!")
            QApplication.processEvents()
            mock_info.assert_called_once_with(dialog, "Complete", "Processing complete!")

        # Clear status and verify real status bar state
        status_manager.clear_message()
        QApplication.processEvents()
        assert status_bar.currentMessage() == ""

        # Verify all signals were emitted correctly
        assert len(status_events) == 3  # Loading, Processing, Clear
        assert status_events == ["Loading data...", "Processing...", ""]

        assert len(button_events) == 1  # Process Data button
        assert button_events[0] == "Process Data"

        assert len(message_events) == 1  # Info message
        assert message_events[0] == ("info", "Processing complete!")

        # Verify final component states
        assert button_manager.custom_button_count == 1
        assert status_manager.is_available is True
        assert message_manager.is_initialized is True

    def test_realistic_form_validation_workflow(self, qtbot: Any) -> None:
        """Test realistic form validation using the enhanced TestDialog."""
        dialog = SampleDialog(with_status_bar=True)
        qtbot.addWidget(dialog)

        # Verify form elements were created
        assert hasattr(dialog, 'name_input')
        assert hasattr(dialog, 'validate_button')
        assert hasattr(dialog, 'result_label')

        # Get button manager to test OK button state management
        button_manager = dialog.get_component("button_box")
        assert button_manager is not None
        ok_button = button_manager.get_button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button is not None

        # Initially OK should be enabled (default state)
        assert ok_button.isEnabled()

        # Test invalid input (too short)
        dialog.name_input.setText("ab")
        QTest.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()

        # Verify validation failed
        assert not dialog.form_valid
        assert "must be at least 3 characters" in dialog.result_label.text()
        assert "color: red" in dialog.result_label.styleSheet()
        assert not ok_button.isEnabled()  # Should be disabled

        # Test valid input
        dialog.name_input.setText("valid_name")
        QTest.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()

        # Verify validation passed
        assert dialog.form_valid
        assert "Valid name: valid_name" in dialog.result_label.text()
        assert "color: green" in dialog.result_label.styleSheet()
        assert ok_button.isEnabled()  # Should be re-enabled

    def test_progress_and_status_integration(self, qtbot: Any) -> None:
        """Test progress bar and status bar integration."""
        dialog = SampleDialog(with_status_bar=True)
        qtbot.addWidget(dialog)

        # Get status manager
        status_manager = dialog.get_component("status_bar")
        assert status_manager is not None
        status_bar = status_manager.status_bar
        assert status_bar is not None

        # Initially progress bar should be hidden
        assert hasattr(dialog, 'progress_bar')
        assert not dialog.progress_bar.isVisible()

        # Test progress simulation
        dialog.simulate_progress(25)
        QApplication.processEvents()

        # Verify progress bar is now visible and shows correct value
        assert dialog.progress_bar.isVisible()
        assert dialog.progress_bar.value() == 25

        # Verify status bar shows progress message
        assert status_bar.currentMessage() == "Processing... 25%"

        # Test different progress values
        dialog.simulate_progress(75)
        QApplication.processEvents()

        assert dialog.progress_bar.value() == 75
        assert status_bar.currentMessage() == "Processing... 75%"

        # Test completion
        dialog.simulate_progress(100)
        QApplication.processEvents()

        assert dialog.progress_bar.value() == 100
        assert status_bar.currentMessage() == "Processing... 100%"

    def test_component_state_consistency(self, qtbot: Any) -> None:
        """Test that all components maintain consistent state."""
        dialog = SampleDialog(with_status_bar=True)
        qtbot.addWidget(dialog)

        # Get all components
        message_manager = dialog.get_component("message_dialog")
        button_manager = dialog.get_component("button_box")
        status_manager = dialog.get_component("status_bar")

        # Verify all components are properly initialized
        assert message_manager.is_initialized
        assert button_manager.is_available
        assert status_manager.is_available

        # Test that context properly tracks all components
        context = dialog.context
        assert context.has_component("message_dialog")
        assert context.has_component("button_box")
        assert context.has_component("status_bar")

        # Verify components are also tracked in dialog.components
        assert len(dialog.components) == 3
        assert message_manager in dialog.components
        assert button_manager in dialog.components
        assert status_manager in dialog.components

        # Test component references are consistent
        assert context.get_component("message_dialog") is message_manager
        assert context.get_component("button_box") is button_manager
        assert context.get_component("status_bar") is status_manager

    def test_real_widget_properties_and_behavior(self, qtbot: Any) -> None:
        """Test real Qt widget properties and behavior."""
        dialog = SampleDialog(with_status_bar=True)
        qtbot.addWidget(dialog)

        # Test dialog properties
        assert isinstance(dialog, QDialog)
        assert dialog.main_layout is not None
        assert dialog.content_widget is not None
        assert dialog.content_widget.layout() is not None

        # Test button box widget properties
        button_manager = dialog.get_component("button_box")
        button_box = button_manager.button_box
        assert isinstance(button_box, QDialogButtonBox)
        assert button_box.parent() is not None

        # Test status bar widget properties
        status_manager = dialog.get_component("status_bar")
        status_bar = status_manager.status_bar
        from PySide6.QtWidgets import QStatusBar
        assert isinstance(status_bar, QStatusBar)
        assert status_bar.parent() is not None

        # Test custom widgets from TestDialog
        assert hasattr(dialog, 'test_label')
        assert isinstance(dialog.test_label, QLabel)
        assert dialog.test_label.text() == "Test Dialog Content"

        assert hasattr(dialog, 'name_input')
        assert isinstance(dialog.name_input, QLineEdit)
        assert dialog.name_input.placeholderText() == "Enter name..."

        assert hasattr(dialog, 'validate_button')
        assert isinstance(dialog.validate_button, QPushButton)
        assert dialog.validate_button.text() == "Validate"

        # Test widget hierarchy
        content_layout = dialog.content_widget.layout()
        assert content_layout.count() > 0  # Has child widgets

    @patch('PySide6.QtWidgets.QMessageBox.warning')
    def test_all_message_types_integration(self, mock_warning: Mock, qtbot: Any) -> None:
        """Test all message dialog types work properly."""
        dialog = SampleDialog()
        qtbot.addWidget(dialog)

        message_manager = dialog.get_component("message_dialog")
        assert message_manager is not None

        # Test signal collection for all message types
        all_messages: list[tuple] = []
        message_manager.message_shown.connect(lambda msg_type, msg: all_messages.append((msg_type, msg)))

        # Test warning message (we already tested info, error, confirmation above)
        message_manager.show_warning("Warning Title", "This is a warning")
        QApplication.processEvents()

        # Verify QMessageBox.warning was called
        mock_warning.assert_called_once_with(dialog, "Warning Title", "This is a warning")

        # Verify signal was emitted
        assert len(all_messages) == 1
        assert all_messages[0] == ("warning", "This is a warning")

        # Test that message manager maintains proper parent reference
        assert message_manager._dialog is dialog
        assert message_manager.is_initialized
