"""Output name widget for ROM extraction"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit, QWidget

from ui.common.spacing_constants import PATH_EDIT_MIN_WIDTH

from .base_widget import BaseExtractionWidget


class OutputNameWidget(BaseExtractionWidget):
    """Widget for managing output file naming"""

    # Signals
    text_changed = Signal(str)  # Emitted when output name changes

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the user interface"""
        output_layout = self._create_hbox_layout()

        name_label = self._create_control_label("Name:")
        output_layout.addWidget(name_label)

        self.output_name_edit = QLineEdit()
        self.output_name_edit.setPlaceholderText("Enter output base name...")
        self.output_name_edit.setMinimumWidth(PATH_EDIT_MIN_WIDTH)
        _ = self.output_name_edit.textChanged.connect(self.text_changed.emit)
        output_layout.addWidget(self.output_name_edit, 1)

        self._setup_widget_with_group("Output", output_layout)

    def get_output_name(self) -> str:
        """Get the current output name"""
        return self.output_name_edit.text().strip()

    def set_output_name(self, name: str) -> None:
        """Set the output name"""
        self.output_name_edit.setText(name)

    def clear(self) -> None:
        """Clear the output name"""
        self.output_name_edit.clear()
