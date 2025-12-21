"""Output name widget for ROM extraction"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from ui.common.spacing_constants import (
    CONTROL_PANEL_LABEL_WIDTH,
    SPACING_COMPACT_MEDIUM as SPACING_MEDIUM,
)

from .base_widget import BaseExtractionWidget


class OutputNameWidget(BaseExtractionWidget):
    """Widget for managing output file naming"""

    # Signals
    text_changed = Signal(str)  # Emitted when output name changes

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface"""
        output_layout = QHBoxLayout()
        output_layout.setSpacing(SPACING_MEDIUM)
        output_layout.setContentsMargins(0, 0, 0, 0)  # Group box CSS provides padding

        name_label = QLabel("Name:")
        name_label.setMinimumWidth(CONTROL_PANEL_LABEL_WIDTH)
        name_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        output_layout.addWidget(name_label)

        self.output_name_edit = QLineEdit()
        self.output_name_edit.setPlaceholderText("Enter output base name...")
        self.output_name_edit.setMinimumWidth(250)
        _ = self.output_name_edit.textChanged.connect(self.text_changed.emit)
        output_layout.addWidget(self.output_name_edit, 1)

        self._setup_widget_with_group("Output", output_layout)

    def get_output_name(self) -> str:
        """Get the current output name"""
        return self.output_name_edit.text().strip()

    def set_output_name(self, name: str):
        """Set the output name"""
        self.output_name_edit.setText(name)

    def clear(self):
        """Clear the output name"""
        self.output_name_edit.clear()
