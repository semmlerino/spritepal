"""
Form row layout helper component

Provides a standardized layout for label + input combinations
used throughout SpritePal dialogs.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.common.spacing_constants import SPACING_SMALL, SPACING_TINY
from ui.styles import get_muted_text_style


class FormRow(QWidget):
    """
    Form row layout helper for label + input combinations.

    Features:
    - Consistent spacing and alignment
    - Support for horizontal and vertical layouts
    - validation state display
    - Flexible input widget support
    - help text display

    Common pattern used throughout all SpritePal dialogs.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        label_text: str = "",
        input_widget: QWidget | None = None,
        orientation: str = "horizontal",  # "horizontal" or "vertical"
        label_width: int | None = None,
        spacing: int = SPACING_SMALL,
        help_text: str = "",
        label_alignment: Qt.AlignmentFlag | None = None,
    ):
        super().__init__(parent)

        self._orientation = orientation
        self._help_text = help_text

        # Create main layout
        if orientation == "horizontal":
            self.main_layout = QHBoxLayout(self)
        else:
            self.main_layout = QVBoxLayout(self)

        self.main_layout.setSpacing(spacing)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Create label
        self.label = QLabel(label_text)
        if label_width:
            self.label.setMinimumWidth(label_width)

        # For horizontal layout, use provided alignment or default to VCenter
        if orientation == "horizontal":
            alignment = label_alignment if label_alignment else Qt.AlignmentFlag.AlignVCenter
            self.label.setAlignment(alignment)

        self.main_layout.addWidget(self.label)

        # Create input container
        if orientation == "horizontal":
            self.input_container = QWidget()
            self.input_layout = QVBoxLayout(self.input_container)
        else:
            self.input_container = self
            self.input_layout = self.main_layout

        self.input_layout.setContentsMargins(0, 0, 0, 0)
        self.input_layout.setSpacing(SPACING_TINY)

        # Initialize help label
        self.help_label: QLabel | None = None

        # Add input widget if provided
        self.input_widget: QWidget | None = None
        if input_widget is not None:
            self.set_input_widget(input_widget)

        # Add help text if provided
        if help_text:
            self.help_label = QLabel(help_text)
            self.help_label.setStyleSheet(get_muted_text_style(color_level="medium"))
            self.help_label.setWordWrap(True)
            self.input_layout.addWidget(self.help_label)

        # Add input container to main layout (for horizontal layout)
        if orientation == "horizontal":
            self.main_layout.addWidget(self.input_container, 1)  # Stretch factor 1

    def set_input_widget(self, widget: QWidget):
        """Set or replace the input widget"""
        # Remove existing input widget if any
        if self.input_widget is not None:
            self.input_layout.removeWidget(self.input_widget)
            self.input_widget.setParent(None)

        # Add new input widget
        self.input_widget = widget
        # Insert before help text if it exists
        insert_index = 0 if self.help_label is None else self.input_layout.count() - 1
        self.input_layout.insertWidget(insert_index, widget)

    def set_label_text(self, text: str):
        """Update the label text"""
        if self.label:
            self.label.setText(text)

    def get_label_text(self) -> str:
        """Get the current label text"""
        return self.label.text()

    def set_help_text(self, text: str):
        """Set or update help text"""
        if self.help_label is not None:
            self.help_label.setText(text)
        else:
            self.help_label = QLabel(text)
            self.help_label.setStyleSheet(get_muted_text_style(color_level="medium"))
            self.help_label.setWordWrap(True)
            self.input_layout.addWidget(self.help_label)

    def clear_help_text(self):
        """Remove help text"""
        if self.help_label is not None:
            self.input_layout.removeWidget(self.help_label)
            self.help_label.setParent(None)
            self.help_label = None

    def set_validation_state(self, is_valid: bool, error_message: str = ""):
        """Set validation state with optional error message"""
        if not is_valid and error_message:
            if self.help_label is None:
                self.set_help_text(error_message)
            elif self.help_label:
                self.help_label.setText(error_message)
            # Change help label to error styling
            if self.help_label:
                self.help_label.setStyleSheet(get_muted_text_style(color_level="dark"))
        elif is_valid and self.help_label is not None and not self._help_text:
            # Clear error message if no permanent help text
            self.clear_help_text()
        elif is_valid and self.help_label is not None and self._help_text:
            # Restore original help text
            if self.help_label:
                self.help_label.setText(self._help_text)
            if self.help_label:
                self.help_label.setStyleSheet(get_muted_text_style(color_level="medium"))

    def set_label_width(self, width: int):
        """Set the label width"""
        self.label.setMinimumWidth(width)

    def add_stretch(self):
        """Add stretch to the main layout"""
        self.main_layout.addStretch()


def create_horizontal_form_row(
    label_text: str,
    input_widget: QWidget,
    label_width: int | None = None,
    help_text: str = "",
    label_alignment: Qt.AlignmentFlag | None = None,
) -> FormRow:
    """Convenience function to create a horizontal form row"""
    return FormRow(
        label_text=label_text,
        input_widget=input_widget,
        orientation="horizontal",
        label_width=label_width,
        help_text=help_text,
        label_alignment=label_alignment,
    )


def create_vertical_form_row(label_text: str, input_widget: QWidget, help_text: str = "") -> FormRow:
    """Convenience function to create a vertical form row"""
    return FormRow(label_text=label_text, input_widget=input_widget, orientation="vertical", help_text=help_text)
