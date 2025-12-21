"""CGRAM file selector widget for ROM extraction"""

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout

# UI Spacing Constants (imported from centralized module)
from ui.common.spacing_constants import (
    CONTROL_PANEL_BUTTON_WIDTH,
    EXTRACTION_BUTTON_MIN_HEIGHT as BUTTON_MIN_HEIGHT,
    SPACING_COMPACT_MEDIUM as SPACING_MEDIUM,
)

from .base_widget import BaseExtractionWidget


class CGRAMSelectorWidget(BaseExtractionWidget):
    """Widget for selecting optional CGRAM palette file"""

    # Signals
    browse_clicked = Signal()  # Emitted when browse button clicked

    def __init__(self, parent: Any | None = None) -> None:  # pyright: ignore[reportExplicitAny] - Qt parent type
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface - collapsible section, starts collapsed"""
        cgram_layout = QVBoxLayout()
        cgram_layout.setSpacing(SPACING_MEDIUM)
        cgram_layout.setContentsMargins(0, 0, 0, 0)

        # CGRAM path row
        cgram_row = QHBoxLayout()
        cgram_row.setSpacing(SPACING_MEDIUM)

        self.cgram_path_edit = QLineEdit()
        self.cgram_path_edit.setPlaceholderText(
            "Select custom palette file..."
        )
        self.cgram_path_edit.setReadOnly(True)
        self.cgram_path_edit.setMinimumWidth(250)
        cgram_row.addWidget(self.cgram_path_edit, 1)

        self.browse_cgram_btn = QPushButton("Browse...")
        self.browse_cgram_btn.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.browse_cgram_btn.setFixedWidth(CONTROL_PANEL_BUTTON_WIDTH)
        self.browse_cgram_btn.setToolTip(
            "Palettes are extracted from ROM when available.\n"
            "Common sprites have default palette fallbacks.\n"
            "Use this to load custom palette overrides."
        )
        _ = self.browse_cgram_btn.clicked.connect(self.browse_clicked.emit)
        cgram_row.addWidget(self.browse_cgram_btn)

        cgram_layout.addLayout(cgram_row)

        # Use collapsible group box, starts collapsed since this is optional
        self._collapsible = self._setup_widget_collapsible(
            "Palette Override (optional)", cgram_layout, collapsed=True
        )

    def get_cgram_path(self) -> str:
        """Get the current CGRAM path"""
        return self.cgram_path_edit.text()

    def set_cgram_path(self, path: str):
        """Set the CGRAM path"""
        self.cgram_path_edit.setText(path)

    def clear(self):
        """Clear the CGRAM path"""
        self.cgram_path_edit.clear()
