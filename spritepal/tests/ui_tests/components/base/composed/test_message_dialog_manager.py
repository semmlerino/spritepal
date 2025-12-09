"""
Tests for the MessageDialogManager component.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDialog, QMessageBox

from ui.components.base.composed.message_dialog_manager import MessageDialogManager

pytestmark = [
    pytest.mark.dialog,
    pytest.mark.headless,
    pytest.mark.signals_slots,
]


class TestMessageDialogManager:
    """Test suite for MessageDialogManager."""

    @pytest.fixture
    def manager(self):
        """Create a MessageDialogManager instance."""
        return MessageDialogManager()

    @pytest.fixture
    def mock_dialog(self, qapp):
        """Create a mock QDialog for testing."""
        dialog = QDialog()
        return dialog

    def test_initialization(self, manager):
        """Test manager initialization."""
        assert not manager.is_initialized
        assert manager._dialog is None

    def test_initialize_with_dialog(self, manager, mock_dialog):
        """Test initializing with a valid dialog."""
        manager.initialize(mock_dialog)
        assert manager.is_initialized
        assert manager._dialog is mock_dialog

    def test_initialize_with_invalid_context(self, manager):
        """Test that initialization fails with non-dialog context."""
        with pytest.raises(TypeError, match="Context must be a QDialog"):
            manager.initialize("not a dialog")

    def test_cleanup(self, manager, mock_dialog):
        """Test cleanup removes references."""
        manager.initialize(mock_dialog)
        assert manager.is_initialized

        manager.cleanup()
        assert not manager.is_initialized
        assert manager._dialog is None

    @patch.object(QMessageBox, 'critical')
    def test_show_error(self, mock_critical, manager, mock_dialog):
        """Test showing error dialog."""
        manager.initialize(mock_dialog)

        # Connect signal spy
        signal_spy = []
        manager.message_shown.connect(lambda t, m: signal_spy.append((t, m)))

        manager.show_error("Test Error", "Error message")

        mock_critical.assert_called_once_with(mock_dialog, "Test Error", "Error message")
        assert signal_spy == [("error", "Error message")]

    @patch.object(QMessageBox, 'information')
    def test_show_info(self, mock_info, manager, mock_dialog):
        """Test showing info dialog."""
        manager.initialize(mock_dialog)

        # Connect signal spy
        signal_spy = []
        manager.message_shown.connect(lambda t, m: signal_spy.append((t, m)))

        manager.show_info("Test Info", "Info message")

        mock_info.assert_called_once_with(mock_dialog, "Test Info", "Info message")
        assert signal_spy == [("info", "Info message")]

    @patch.object(QMessageBox, 'warning')
    def test_show_warning(self, mock_warning, manager, mock_dialog):
        """Test showing warning dialog."""
        manager.initialize(mock_dialog)

        # Connect signal spy
        signal_spy = []
        manager.message_shown.connect(lambda t, m: signal_spy.append((t, m)))

        manager.show_warning("Test Warning", "Warning message")

        mock_warning.assert_called_once_with(mock_dialog, "Test Warning", "Warning message")
        assert signal_spy == [("warning", "Warning message")]

    @patch.object(QMessageBox, 'question')
    def test_confirm_action_yes(self, mock_question, manager, mock_dialog):
        """Test confirmation dialog when user clicks Yes."""
        manager.initialize(mock_dialog)
        mock_question.return_value = QMessageBox.StandardButton.Yes

        # Connect signal spy
        signal_spy = []
        manager.message_shown.connect(lambda t, m: signal_spy.append((t, m)))

        result = manager.confirm_action("Confirm", "Are you sure?")

        assert result is True
        mock_question.assert_called_once_with(mock_dialog, "Confirm", "Are you sure?")
        assert signal_spy == [("confirmation", "Are you sure?")]

    @patch.object(QMessageBox, 'question')
    def test_confirm_action_no(self, mock_question, manager, mock_dialog):
        """Test confirmation dialog when user clicks No."""
        manager.initialize(mock_dialog)
        mock_question.return_value = QMessageBox.StandardButton.No

        result = manager.confirm_action("Confirm", "Are you sure?")

        assert result is False

    def test_methods_require_initialization(self, manager):
        """Test that methods fail without initialization."""
        with pytest.raises(RuntimeError, match="not initialized"):
            manager.show_error("Title", "Message")

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.show_info("Title", "Message")

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.show_warning("Title", "Message")

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.confirm_action("Title", "Message")

    def test_repr(self, manager, mock_dialog):
        """Test string representation."""
        assert repr(manager) == "<MessageDialogManager(not initialized)>"

        manager.initialize(mock_dialog)
        assert repr(manager) == "<MessageDialogManager(initialized)>"

    def test_parent_object(self):
        """Test that manager can have a parent QObject."""
        parent = QObject()
        manager = MessageDialogManager(parent)
        assert manager.parent() is parent
