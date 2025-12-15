"""Output name widget for ROM extraction"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout

from .base_widget import BaseExtractionWidget

# UI Spacing Constants (matching main panel)
SPACING_SMALL = 6
SPACING_MEDIUM = 10
SPACING_LARGE = 16
SPACING_XLARGE = 20
BUTTON_MIN_HEIGHT = 32
COMBO_MIN_WIDTH = 200
BUTTON_MAX_WIDTH = 150
LABEL_MIN_WIDTH = 120

class OutputNameWidget(BaseExtractionWidget):
    """Widget for managing output file naming"""

    # Signals
    text_changed = Signal(str)  # Emitted when output name changes

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Output name group
        output_group = self._create_group_box("Output")
        output_layout = QHBoxLayout()
        output_layout.setSpacing(SPACING_MEDIUM)
        output_layout.setContentsMargins(SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM)

        name_label = QLabel("Name:")
        name_label.setMinimumWidth(60)
        name_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        output_layout.addWidget(name_label)

        self.output_name_edit = QLineEdit()
        self.output_name_edit.setPlaceholderText("Enter output base name...")
        self.output_name_edit.setMinimumWidth(250)
        _ = self.output_name_edit.textChanged.connect(self.text_changed.emit)
        output_layout.addWidget(self.output_name_edit, 1)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        self.setLayout(layout)

    def get_output_name(self) -> str:
        """Get the current output name"""
        return self.output_name_edit.text().strip()

    def set_output_name(self, name: str):
        """Set the output name"""
        self.output_name_edit.setText(name)

    def clear(self):
        """Clear the output name"""
        self.output_name_edit.clear()
