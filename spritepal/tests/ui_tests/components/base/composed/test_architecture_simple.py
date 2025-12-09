"""
Simple unit tests for ComposedDialog architecture components.

These tests validate the core architecture without Qt dependencies.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

pytestmark = [
    pytest.mark.dialog,
    pytest.mark.headless,
    pytest.mark.mock_dialogs,
    pytest.mark.qt_real,
]


def test_dialog_context_basics():
    """Test DialogContext basic functionality."""
    # Mock Qt modules before import
    with patch.dict('sys.modules', {
        'PySide6': MagicMock(),
        'PySide6.QtCore': MagicMock(),
        'PySide6.QtWidgets': MagicMock(),
        'PySide6.QtGui': MagicMock()
    }):
        from ui.components.base.composed.dialog_context import DialogContext

        # Create context with mock objects
        context = DialogContext(
            dialog=Mock(),
            main_layout=Mock(),
            content_widget=Mock()
        )

        # Test basic properties
        assert context.dialog is not None
        assert context.main_layout is not None
        assert context.content_widget is not None
        assert context.button_box is None
        assert context.status_bar is None
        assert isinstance(context.config, dict)
        assert isinstance(context.components, dict)

        # Test component registration
        component = Mock()
        context.register_component("test", component)
        assert context.has_component("test")
        assert context.get_component("test") == component

        # Test unregistration (should not raise)
        context.unregister_component("test")
        assert not context.has_component("test")
        context.unregister_component("nonexistent")  # Should not raise

def test_message_dialog_manager_basics():
    """Test MessageDialogManager basic functionality."""
    with patch.dict('sys.modules', {
        'PySide6': MagicMock(),
        'PySide6.QtCore': MagicMock(),
        'PySide6.QtWidgets': MagicMock(),
        'PySide6.QtGui': MagicMock()
    }):
        # Mock QMessageBox before import
        mock_qmessagebox = Mock()
        sys.modules['PySide6.QtWidgets'].QMessageBox = mock_qmessagebox

        from ui.components.base.composed.dialog_context import DialogContext
        from ui.components.base.composed.message_dialog_manager import MessageDialogManager

        # Create manager
        manager = MessageDialogManager()

        # Test initialization
        mock_dialog = Mock()
        mock_dialog.accept = Mock()
        mock_dialog.reject = Mock()

        context = DialogContext(
            dialog=mock_dialog,
            main_layout=Mock(),
            content_widget=Mock()
        )

        manager.initialize(context)
        assert manager.context == context

        # Test cleanup
        manager.cleanup()
        assert manager.context is None

def test_status_bar_manager_basics():
    """Test StatusBarManager basic functionality."""
    with patch.dict('sys.modules', {
        'PySide6': MagicMock(),
        'PySide6.QtCore': MagicMock(),
        'PySide6.QtWidgets': MagicMock(),
        'PySide6.QtGui': MagicMock()
    }):
        from ui.components.base.composed.dialog_context import DialogContext
        from ui.components.base.composed.status_bar_manager import StatusBarManager

        # Test with status bar disabled
        context = DialogContext(
            dialog=Mock(),
            main_layout=Mock(),
            content_widget=Mock(),
            config={'with_status_bar': False}
        )

        manager = StatusBarManager()
        manager.initialize(context)

        assert manager.context == context
        assert manager.status_bar is None
        assert not manager.is_available

def test_button_box_manager_basics():
    """Test ButtonBoxManager basic functionality."""
    with patch.dict('sys.modules', {
        'PySide6': MagicMock(),
        'PySide6.QtCore': MagicMock(),
        'PySide6.QtWidgets': MagicMock(),
        'PySide6.QtGui': MagicMock()
    }):
        from ui.components.base.composed.button_box_manager import ButtonBoxManager
        from ui.components.base.composed.dialog_context import DialogContext

        # Test with button box disabled
        context = DialogContext(
            dialog=Mock(),
            main_layout=Mock(),
            content_widget=Mock(),
            config={'with_button_box': False}
        )

        manager = ButtonBoxManager()
        manager.initialize(context)

        assert manager.context == context
        assert manager.button_box is None
        assert not manager.is_available

def test_composed_dialog_architecture():
    """Test ComposedDialog component registration."""
    with patch.dict('sys.modules', {
        'PySide6': MagicMock(),
        'PySide6.QtCore': MagicMock(),
        'PySide6.QtWidgets': MagicMock(),
        'PySide6.QtGui': MagicMock()
    }):
        # Mock Qt classes
        mock_qdialog = Mock()
        mock_qlayout = Mock()
        mock_qwidget = Mock()

        sys.modules['PySide6.QtWidgets'].QDialog = mock_qdialog
        sys.modules['PySide6.QtWidgets'].QVBoxLayout = mock_qlayout
        sys.modules['PySide6.QtWidgets'].QWidget = mock_qwidget

        from ui.components.base.composed.composed_dialog import ComposedDialog

        # Create dialog with mocked parent
        with patch.object(mock_qdialog, '__init__', return_value=None):
            dialog = ComposedDialog(
                None,
                with_status_bar=False,
                with_button_box=False
            )

            # Test that context was created
            assert dialog.context is not None
            assert dialog.context.dialog is dialog

            # Test that message manager is always registered
            assert dialog.context.has_component("messages")

            # Test that optional components are not registered
            assert not dialog.context.has_component("status_bar")
            assert not dialog.context.has_component("button_box")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
