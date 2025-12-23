"""
File selector component with browse functionality

Provides a standardized file selection widget with path input and browse button,
exactly replicating the file selection patterns from InjectionDialog.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from utils.logging_config import get_logger

logger = get_logger(__name__)

from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from ui.common.file_dialogs import FileDialogHelper

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ApplicationStateManagerProtocol


class FileSelector(QWidget):
    """
    File selector widget with path input and browse functionality.

    Features:
    - Path input field (can be read-only or editable)
    - Browse button with file dialogs
    - Support for open/save dialogs with file filters
    - Settings manager integration for directory tracking
    - Validation state (file exists/doesn't exist)
    - callback functionality after selection

    Exactly replicates the file selection patterns from InjectionDialog.
    """

    # Signals
    file_selected = Signal(str)     # Emits selected file path
    path_changed = Signal(str)      # Emits when path text changes

    def __init__(
        self,
        parent: QWidget | None = None,
        label_text: str = "",
        placeholder: str = "",
        browse_text: str = "Browse...",
        dialog_title: str = "Select File",
        file_filter: str = "All Files (*.*)",
        mode: str = "open",  # "open" or "save"
        read_only: bool = False,
        initial_path: str = "",
        selection_callback: Callable[[str], None] | None = None,
        settings_key: str | None = None,
        settings_namespace: str | None = None,
        *,
        settings_manager: ApplicationStateManagerProtocol,
    ):
        super().__init__(parent)

        self._dialog_title = dialog_title
        self._file_filter = file_filter
        self._mode = mode
        self._selection_callback = selection_callback
        self._settings_key = settings_key
        self._settings_namespace = settings_namespace
        self.settings_manager = settings_manager

        # Create UI components
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        # label
        if label_text:
            self.label = QLabel(label_text)
            self._layout.addWidget(self.label)

        # Path input field
        self.path_edit = QLineEdit(initial_path)
        self.path_edit.setPlaceholderText(placeholder)
        self.path_edit.setReadOnly(read_only)
        _ = self.path_edit.textChanged.connect(self._on_path_changed)
        self._layout.addWidget(self.path_edit)

        # Browse button
        self.browse_button = QPushButton(browse_text)
        _ = self.browse_button.clicked.connect(self._browse_file)
        self._layout.addWidget(self.browse_button)

    def _on_path_changed(self, text: str):
        """Handle path text changes"""
        self.path_changed.emit(text)

    def _browse_file(self):
        """
        Browse for file using appropriate dialog.

        Uses FileDialogHelper for consistent dialog behavior and settings persistence.
        """
        # Get current path for initial directory
        current_path = self.path_edit.text()

        # Show appropriate file dialog using FileDialogHelper
        filename = None
        if self._mode == "open":
            filename = FileDialogHelper.browse_open_file(
                self,
                self._dialog_title,
                self._file_filter,
                current_path,
                self._settings_key,
                self._settings_namespace or "file_selector"
            )
        elif self._mode == "save":
            filename = FileDialogHelper.browse_save_file(
                self,
                self._dialog_title,
                self._file_filter,
                current_path,
                self._settings_key,
                self._settings_namespace or "file_selector"
            )

        if filename:
            # Update the path
            self.path_edit.setText(filename)

            # Emit signal
            self.file_selected.emit(filename)

            # Call selection callback if provided
            if self._selection_callback:
                try:
                    self._selection_callback(filename)
                except Exception as e:
                    # Log error but don't crash
                    logger.exception("Error in file selection callback: %s", e)

    def get_path(self) -> str:
        """Get the current file path"""
        return self.path_edit.text()

    def set_path(self, path: str | None):
        """Set the file path"""
        if path is None:
            converted_path = ""
        else:
            # Convert any type to string
            converted_path = str(path)

        self.path_edit.setText(converted_path)

    def clear_path(self):
        """Clear the file path"""
        self.path_edit.clear()

    def is_valid(self) -> bool:
        """Check if current path exists (for validation)"""
        path = self.get_path()
        if not path:
            return True  # Empty path is considered valid (optional field)

        path_obj = Path(path)
        if self._mode == "open":
            return path_obj.exists() and path_obj.is_file()
        # save mode
        # For save mode, check if directory exists
        dir_path = path_obj.parent
        return dir_path.exists() if dir_path != Path() else True

    def set_placeholder(self, placeholder: str):
        """Set the placeholder text"""
        self.path_edit.setPlaceholderText(placeholder)

    def set_read_only(self, read_only: bool):
        """Set read-only state of the path input"""
        self.path_edit.setReadOnly(read_only)

    @override
    def setFocus(self, reason: Qt.FocusReason | None = None) -> None:
        """Set focus to the path input field"""
        if reason is not None:
            self.path_edit.setFocus(reason)
        else:
            self.path_edit.setFocus()

    def set_browse_enabled(self, enabled: bool):
        """Enable/disable the browse button"""
        self.browse_button.setEnabled(enabled)
