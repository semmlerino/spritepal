"""
Message dialog manager component for displaying user messages.

This component handles all message dialog operations including errors, warnings,
information messages, and confirmation dialogs. It's designed to be composed
into dialogs via the DialogBase composition system.
"""
from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog, QMessageBox


class MessageDialogManager(QObject):
    """
    Manages message dialog operations for composed dialogs.

    This manager provides a centralized way to display various types of
    message dialogs (error, info, warning, confirmation) with consistent
    behavior and optional signal emission for tracking.

    Signals:
        message_shown: Emitted when any message dialog is shown,
                      with message type and content
    """

    # Signal emitted when a message is shown (type, message)
    message_shown = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        """
        Initialize the message dialog manager.

        Args:
            parent: Optional parent QObject for proper cleanup
        """
        super().__init__(parent)
        self.context: Any = None
        self._dialog: QDialog | None = None

    def initialize(self, context: Any) -> None:
        """
        Initialize the manager with a dialog context.

        This method sets up the reference to the parent dialog that will
        be used as the parent for all message boxes.

        Args:
            context: The dialog context containing the parent dialog
        """
        self.context = context
        # Extract dialog from context
        if hasattr(context, 'dialog'):
            dialog = context.dialog
        else:
            # Fallback: assume context is the dialog itself (backward compatibility)
            dialog = context

        # For testing/mocking support, check if it's a real QDialog
        # If it's a mock object (has __class__.__module__ starting with 'unittest.mock'),
        # or if it's not a QDialog but has necessary dialog methods, we'll accept it
        is_mock = (hasattr(dialog, '__class__') and
                   hasattr(dialog.__class__, '__module__') and
                   dialog.__class__.__module__.startswith('unittest.mock'))

        if not is_mock and not isinstance(dialog, QDialog):
            # For non-mock objects, check if they at least have dialog-like methods
            # This allows for duck-typing in tests
            if not (hasattr(dialog, 'accept') and hasattr(dialog, 'reject')):
                raise TypeError(f"Context must be a QDialog or dialog-like object, got {type(dialog).__name__}")

        self._dialog = dialog

    def cleanup(self) -> None:
        """
        Clean up references and resources.

        This should be called when the manager is no longer needed
        to prevent reference cycles.
        """
        self._dialog = None
        self.context = None

    def show_error(self, title: str, message: str) -> None:
        """
        Show an error message dialog.

        Args:
            title: Error dialog title
            message: Error message to display

        Raises:
            RuntimeError: If initialize() hasn't been called
        """
        if self._dialog is None:
            raise RuntimeError("MessageDialogManager not initialized. Call initialize() first.")

        QMessageBox.critical(self._dialog, title, message)
        self.message_shown.emit("error", message)

    def show_info(self, title: str, message: str) -> None:
        """
        Show an information message dialog.

        Args:
            title: Info dialog title
            message: Info message to display

        Raises:
            RuntimeError: If initialize() hasn't been called
        """
        if self._dialog is None:
            raise RuntimeError("MessageDialogManager not initialized. Call initialize() first.")

        QMessageBox.information(self._dialog, title, message)
        self.message_shown.emit("info", message)

    def show_warning(self, title: str, message: str) -> None:
        """
        Show a warning message dialog.

        Args:
            title: Warning dialog title
            message: Warning message to display

        Raises:
            RuntimeError: If initialize() hasn't been called
        """
        if self._dialog is None:
            raise RuntimeError("MessageDialogManager not initialized. Call initialize() first.")

        QMessageBox.warning(self._dialog, title, message)
        self.message_shown.emit("warning", message)

    def confirm_action(self, title: str, message: str) -> bool:
        """
        Show a confirmation dialog.

        Args:
            title: Confirmation dialog title
            message: Confirmation message

        Returns:
            True if user confirmed (clicked Yes), False otherwise

        Raises:
            RuntimeError: If initialize() hasn't been called
        """
        if self._dialog is None:
            raise RuntimeError("MessageDialogManager not initialized. Call initialize() first.")

        reply = QMessageBox.question(self._dialog, title, message)
        self.message_shown.emit("confirmation", message)
        return reply == QMessageBox.StandardButton.Yes

    @property
    def is_initialized(self) -> bool:
        """
        Check if the manager has been initialized.

        Returns:
            True if initialize() has been called with a valid dialog
        """
        return self._dialog is not None

    @override
    def __repr__(self) -> str:
        """Return string representation of the manager."""
        status = "initialized" if self.is_initialized else "not initialized"
        return f"<MessageDialogManager({status})>"
