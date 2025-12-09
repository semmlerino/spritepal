"""
User-friendly error dialog for SpritePal
Provides clear error messages and recovery suggestions
"""
from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.components.base import BaseDialog
from ui.styles import (
    get_bold_text_style,
    get_dialog_button_box_style,
    get_muted_text_style,
)


class UserErrorDialog(BaseDialog):
    """Dialog that displays user-friendly error messages with recovery suggestions"""

    # Common error mappings
    ERROR_MAPPINGS: ClassVar[dict[str, dict[str, str]]] = {
        "no hal compressed data": {
            "title": "Invalid Sprite Data",
            "message": "No sprite data found at this location",
            "suggestion": "Try using the navigation buttons to find valid sprites, or use 'Find Sprites' to scan the ROM.",
            "technical": "No HAL compressed data detected"
        },
        "decompression failed": {
            "title": "Sprite Extraction Failed",
            "message": "Unable to extract sprite data from this location",
            "suggestion": "The data may be corrupted or in a different format. Try a different offset or sprite.",
            "technical": "HAL decompression failed"
        },
        "file not found": {
            "title": "File Not Found",
            "message": "The selected file could not be found",
            "suggestion": "The file may have been moved or deleted. Please select a different file.",
            "technical": "File not found error"
        },
        "permission denied": {
            "title": "Access Denied",
            "message": "Cannot access the selected file",
            "suggestion": "Check that you have permission to read the file and that it's not in use by another program.",
            "technical": "Permission denied"
        },
        "invalid rom": {
            "title": "Invalid ROM File",
            "message": "The selected file is not a valid SNES ROM",
            "suggestion": "Please select a valid .sfc or .smc ROM file. The file may be corrupted or in the wrong format.",
            "technical": "Invalid ROM format"
        },
        "out of bounds": {
            "title": "Invalid Offset",
            "message": "The specified offset is outside the ROM data",
            "suggestion": "Use a smaller offset value or check the ROM size. Valid offsets are typically below 0x400000.",
            "technical": "Offset out of bounds"
        },
        "memory error": {
            "title": "Memory Error",
            "message": "Not enough memory to complete the operation",
            "suggestion": "Try extracting a smaller sprite or close other applications to free up memory.",
            "technical": "Memory allocation failed"
        },
        "no sprite data": {
            "title": "No Sprite Data",
            "message": "No valid sprite data found at this location",
            "suggestion": "This offset doesn't contain sprite data. Try selecting a different sprite or using 'Find Sprites' to locate valid sprites.",
            "technical": "No sprite data detected"
        },
        "extraction failed": {
            "title": "Extraction Failed",
            "message": "Unable to extract sprites from the ROM",
            "suggestion": "The ROM may be corrupted or in an unsupported format. Try a different ROM or sprite location.",
            "technical": "Sprite extraction failed"
        },
        "hal tools not found": {
            "title": "Compression Tools Missing",
            "message": "Required compression tools are not available",
            "suggestion": "The HAL compression tools (exhal/inhal) are required for ROM extraction. Please ensure they are installed.",
            "technical": "HAL compression tools not found"
        }
    }

    def __init__(
        self,
        error_message: str,
        technical_details: str | None = None,
        parent: QWidget | None = None
    ):
        # Find matching error type first
        error_info = self._find_error_mapping(error_message)

        # Initialize BaseDialog with error-specific configuration
        super().__init__(
            parent=parent,
            title=error_info.get("title", "Error"),
            modal=True,
            min_size=(500, None),  # Only set minimum width
            with_status_bar=False,
            with_button_box=False,  # We'll create custom OK-only button box
        )

        # Create main content layout
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Header with icon and message
        header_layout = QHBoxLayout()

        # Error icon
        icon_label = QLabel()
        style = self.style()
        if style:
            pixmap = style.standardPixmap(
                style.StandardPixmap.SP_MessageBoxCritical
            )
            if pixmap:
                icon_label.setPixmap(
                    pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio)
                )
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(icon_label)

        # Error message
        message_layout = QVBoxLayout()

        main_message = QLabel(error_info.get("message", "An error occurred"))
        main_message.setWordWrap(True)
        main_message.setStyleSheet(get_bold_text_style("default"))
        message_layout.addWidget(main_message)

        # Suggestion
        if error_info.get("suggestion"):
            suggestion_label = QLabel(error_info["suggestion"])
            suggestion_label.setWordWrap(True)
            suggestion_label.setStyleSheet(get_muted_text_style(color_level="dark"))
            message_layout.addWidget(suggestion_label)

        header_layout.addLayout(message_layout, 1)
        layout.addLayout(header_layout)

        # Technical details (collapsible)
        if technical_details or error_info.get("technical"):
            details_text = QTextEdit()
            details_text.setReadOnly(True)
            details_text.setMaximumHeight(100)
            details_text.setPlainText(
                f"Technical Details:\n{error_info.get('technical', '')}\n\n"
                f"Full Error:\n{technical_details or error_message}"
            )
            details_text.setStyleSheet(
                "QTextEdit { background-color: #f5f5f5; color: #000000; font-family: monospace; }"
            )
            details_text.hide()  # Hidden by default

            # Show/hide details button
            self.details_button = QPushButton("Show Details")
            self.details_button.setCheckable(True)
            self.details_button.toggled.connect(
                lambda checked: (
                    details_text.show() if checked else details_text.hide(),
                    self.details_button.setText(
                        "Hide Details" if checked else "Show Details"
                    )
                )
            )

            layout.addWidget(self.details_button)
            layout.addWidget(details_text)

        # Set the content layout
        self.set_content_layout(layout)

        # Create custom OK-only button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.setStyleSheet(get_dialog_button_box_style())
        button_box.accepted.connect(self.accept)
        self.main_layout.addWidget(button_box)

    def _find_error_mapping(self, error_message: str) -> dict[str, str]:
        """Find the appropriate error mapping based on the error message"""
        error_lower = error_message.lower()

        for key, mapping in self.ERROR_MAPPINGS.items():
            if key in error_lower:
                return mapping

        # Default error info
        return {
            "title": "Error",
            "message": "An unexpected error occurred",
            "suggestion": "Please try again or contact support if the problem persists.",
            "technical": error_message
        }

    @staticmethod
    def show_error(
        parent: QWidget | None,
        error_message: str,
        technical_details: str | None = None
    ) -> None:
        """Convenience method to show error dialog"""
        dialog = UserErrorDialog(error_message, technical_details, parent)
        dialog.exec()
