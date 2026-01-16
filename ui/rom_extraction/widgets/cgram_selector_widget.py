"""CGRAM file selector widget for ROM extraction"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from .base_widget import BaseExtractionWidget


class CGRAMSelectorWidget(BaseExtractionWidget):
    """Widget for selecting optional CGRAM palette file"""

    # Signals
    browse_clicked = Signal()  # Emitted when browse button clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the user interface - collapsible section, starts collapsed"""
        cgram_layout = self._create_vbox_layout()

        # CGRAM path row
        cgram_row = self._create_hbox_layout()

        self.cgram_path_edit = self._create_readonly_path_edit("Select custom palette file...")
        cgram_row.addWidget(self.cgram_path_edit, 1)

        self.browse_cgram_btn = self._create_browse_button(
            signal=self.browse_clicked,
            tooltip=(
                "Palettes are extracted from ROM when available.\n"
                "Common sprites have default palette fallbacks.\n"
                "Use this to load custom palette overrides."
            ),
        )
        cgram_row.addWidget(self.browse_cgram_btn)

        cgram_layout.addLayout(cgram_row)

        # Use collapsible group box, starts collapsed since this is optional
        # muted=True uses subdued styling for optional sections
        self._collapsible = self._setup_widget_collapsible(
            "Palette Override (optional)", cgram_layout, collapsed=True, muted=True
        )

    def get_cgram_path(self) -> str:
        """Get the current CGRAM path"""
        return self.cgram_path_edit.text()

    def set_cgram_path(self, path: str) -> None:
        """Set the CGRAM path"""
        self.cgram_path_edit.setText(path)

    def clear(self) -> None:
        """Clear the CGRAM path"""
        self.cgram_path_edit.clear()
