#!/usr/bin/env python3
"""
Editor status bar widget for the sprite editor.
Displays cursor position, tile ID, ROM address, and current color preview.
"""

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ui.common.spacing_constants import SPACING_SMALL
from ui.styles.theme import COLORS


class EditorStatusBar(QWidget):
    """
    Horizontal status bar displaying cursor position, tile ID, ROM address, and color.

    Layout (left to right):
    [Cursor: (12, 15)] [Tile: 0x45] [Address: 0x2847C8] [Color Preview]

    Updates are display-only (no signals emitted).
    """

    # Status bar height
    STATUS_BAR_HEIGHT = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("editorStatusBar")
        self.setFixedHeight(self.STATUS_BAR_HEIGHT)

        # Monospace font for hex values
        self._monospace_font = QFont("Courier", 10)
        self._monospace_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)

        # Create label widgets
        self.cursor_label: QLabel | None = None
        self.tile_label: QLabel | None = None
        self.address_label: QLabel | None = None
        self.color_preview: QLabel | None = None
        self.color_index_label: QLabel | None = None

        # Current state
        self._current_color = (128, 128, 128)
        self._current_index: int | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the status bar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(SPACING_SMALL)

        # Cursor position
        self.cursor_label = QLabel("Cursor: --")
        self.cursor_label.setFont(self._monospace_font)
        self.cursor_label.setMinimumWidth(100)
        layout.addWidget(self.cursor_label)

        # Spacing
        layout.addSpacing(SPACING_SMALL)

        # Tile ID
        self.tile_label = QLabel("Tile: 0x00")
        self.tile_label.setFont(self._monospace_font)
        self.tile_label.setMinimumWidth(80)
        layout.addWidget(self.tile_label)

        # Spacing
        layout.addSpacing(SPACING_SMALL)

        # ROM address
        self.address_label = QLabel("Address: 0x000000")
        self.address_label.setFont(self._monospace_font)
        self.address_label.setMinimumWidth(140)
        layout.addWidget(self.address_label)

        # Stretch space
        layout.addStretch(1)

        # Color index label
        self.color_index_label = QLabel("Index: --")
        self.color_index_label.setFont(self._monospace_font)
        self.color_index_label.setMinimumWidth(60)
        layout.addWidget(self.color_index_label)

        # Spacing
        layout.addSpacing(SPACING_SMALL)

        # Color preview
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(20, 20)
        self.color_preview.setAutoFillBackground(True)
        self.color_preview.setToolTip("Current color: RGB(128, 128, 128)")
        self._update_color_preview()
        layout.addWidget(self.color_preview)

        # Apply background styling
        self._apply_theme()

    def _apply_theme(self) -> None:
        """Apply theme styling to the status bar."""
        # Set background color
        palette = self.palette()
        palette.setColor(
            QPalette.ColorRole.Window,
            QColor(COLORS["panel_background"]),
        )
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Set text color
        text_color = QColor(COLORS["text_secondary"])
        for label in [self.cursor_label, self.tile_label, self.address_label]:
            if label is not None:
                label_palette = label.palette()
                label_palette.setColor(QPalette.ColorRole.WindowText, text_color)
                label.setPalette(label_palette)

    def _update_color_preview(self) -> None:
        """Update the color preview widget with current color."""
        if self.color_preview is None:
            return

        r, g, b = self._current_color
        color = QColor(r, g, b)

        # Set background color
        palette = self.color_preview.palette()
        palette.setColor(QPalette.ColorRole.Window, color)
        self.color_preview.setPalette(palette)

        # Update tooltip with index if available
        if self._current_index is not None:
            self.color_preview.setToolTip(f"Index {self._current_index}: RGB({r}, {g}, {b})")
        else:
            self.color_preview.setToolTip(f"Current color: RGB({r}, {g}, {b})")

    def update_cursor(self, x: int, y: int) -> None:
        """
        Update cursor position display.

        Args:
            x: Cursor X coordinate.
            y: Cursor Y coordinate.
        """
        if self.cursor_label is not None:
            self.cursor_label.setText(f"Cursor: ({x:2d}, {y:2d})")

    def update_tile(self, tile_id: int) -> None:
        """
        Update tile ID display.

        Args:
            tile_id: Tile ID as integer (0-255).
        """
        if self.tile_label is not None:
            # Clamp to valid range
            tile_id = max(0, min(255, tile_id))
            self.tile_label.setText(f"Tile: 0x{tile_id:02X}")

    def update_address(self, address: int) -> None:
        """
        Update ROM address display.

        Args:
            address: ROM address as integer (0x000000 - 0xFFFFFF).
        """
        if self.address_label is not None:
            # Clamp to valid 24-bit range
            address = max(0, min(0xFFFFFF, address))
            self.address_label.setText(f"Address: 0x{address:06X}")

    def update_color(self, color: tuple[int, int, int]) -> None:
        """
        Update the color preview display.

        Args:
            color: RGB color as tuple (r, g, b) with values 0-255.
        """
        # Clamp each component to valid range
        r = max(0, min(255, color[0]))
        g = max(0, min(255, color[1]))
        b = max(0, min(255, color[2]))
        self._current_color = (r, g, b)

        self._update_color_preview()

    def update_color_with_index(self, color: tuple[int, int, int], index: int | None) -> None:
        """Update the color preview display with palette index.

        Args:
            color: RGB color as tuple (r, g, b) with values 0-255.
            index: Palette index (0-15), or None if unknown.
        """
        # Clamp each component to valid range
        r = max(0, min(255, color[0]))
        g = max(0, min(255, color[1]))
        b = max(0, min(255, color[2]))
        self._current_color = (r, g, b)
        self._current_index = index

        # Update the index label
        if self.color_index_label is not None:
            if index is not None:
                self.color_index_label.setText(f"Index: {index}")
            else:
                self.color_index_label.setText("Index: --")

        self._update_color_preview()

    def clear_cursor(self) -> None:
        """
        Clear cursor display (show "--" when not hovering).
        """
        if self.cursor_label is not None:
            self.cursor_label.setText("Cursor: --")

    def get_current_color(self) -> tuple[int, int, int]:
        """Get the currently displayed color.

        Returns:
            RGB tuple (r, g, b) with values 0-255.
        """
        return self._current_color
