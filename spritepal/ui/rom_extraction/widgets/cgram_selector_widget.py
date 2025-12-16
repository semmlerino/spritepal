from typing import Any

"""CGRAM file selector widget for ROM extraction"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

# UI Spacing Constants (imported from centralized module)
from ui.common.spacing_constants import (
    EXTRACTION_BUTTON_MAX_WIDTH as BUTTON_MAX_WIDTH,
    EXTRACTION_BUTTON_MIN_HEIGHT as BUTTON_MIN_HEIGHT,
    SPACING_COMPACT_MEDIUM as SPACING_MEDIUM,
)
from ui.styles.theme import COLORS

from .base_widget import BaseExtractionWidget


class CGRAMSelectorWidget(BaseExtractionWidget):
    """Widget for selecting optional CGRAM palette file"""

    # Signals
    browse_clicked = Signal()  # Emitted when browse button clicked

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # CGRAM for palettes - cleaner title
        cgram_group = self._create_group_box("Optional Palette Override")
        cgram_layout = QVBoxLayout()
        cgram_layout.setSpacing(SPACING_MEDIUM)
        cgram_layout.setContentsMargins(SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM)

        # Condensed caption instead of dense info box
        caption = QLabel("Override ROM palettes with custom CGRAM file")
        caption.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        cgram_layout.addWidget(caption)

        # CGRAM path row
        cgram_row = QHBoxLayout()
        cgram_row.setSpacing(SPACING_MEDIUM)

        cgram_label = QLabel("CGRAM:")
        cgram_label.setMinimumWidth(60)
        cgram_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        cgram_row.addWidget(cgram_label)

        self.cgram_path_edit = QLineEdit()
        self.cgram_path_edit.setPlaceholderText(
            "Select CGRAM file for custom palettes (optional)..."
        )
        self.cgram_path_edit.setReadOnly(True)
        self.cgram_path_edit.setMinimumWidth(250)
        cgram_row.addWidget(self.cgram_path_edit, 1)

        self.browse_cgram_btn = QPushButton("Browse...")
        self.browse_cgram_btn.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.browse_cgram_btn.setFixedWidth(BUTTON_MAX_WIDTH)
        self.browse_cgram_btn.setToolTip(
            "Palettes are extracted from ROM when available.\n"
            "Common sprites have default palette fallbacks.\n"
            "Use CGRAM for custom palette overrides."
        )
        _ = self.browse_cgram_btn.clicked.connect(self.browse_clicked.emit)
        cgram_row.addWidget(self.browse_cgram_btn)

        cgram_layout.addLayout(cgram_row)
        cgram_group.setLayout(cgram_layout)
        layout.addWidget(cgram_group)

        self.setLayout(layout)

    def get_cgram_path(self) -> str:
        """Get the current CGRAM path"""
        return self.cgram_path_edit.text()

    def set_cgram_path(self, path: str):
        """Set the CGRAM path"""
        self.cgram_path_edit.setText(path)

    def clear(self):
        """Clear the CGRAM path"""
        self.cgram_path_edit.clear()
