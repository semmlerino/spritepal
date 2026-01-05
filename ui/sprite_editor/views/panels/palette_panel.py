#!/usr/bin/env python3
"""
Palette panel for the pixel editor.
Displays the color palette and handles color selection.
"""

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget

from ..widgets import ColorPaletteWidget


class PalettePanel(QWidget):
    """Panel for color palette display and selection."""

    # Signals
    colorSelected = Signal(int)  # Emits color index when selected

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the palette panel UI."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Palette group box
        palette_group = QGroupBox("Palette")
        palette_layout = QVBoxLayout()

        # Create palette widget
        self.palette_widget = ColorPaletteWidget()
        self.palette_widget.colorSelected.connect(self.colorSelected.emit)

        palette_layout.addWidget(self.palette_widget)
        palette_group.setLayout(palette_layout)

        # Add to main layout
        layout.addWidget(palette_group)

    def get_selected_color(self) -> int:
        """Get the currently selected color index."""
        return self.palette_widget.selected_index

    def set_selected_color(self, index: int) -> None:
        """Set the selected color by index (programmatic update from controller).

        Uses QSignalBlocker to prevent re-emitting the signal that triggered this update.
        """
        # Block signals during programmatic update
        blocker = QSignalBlocker(self.palette_widget)  # noqa: F841  # pyright: ignore[reportUnusedVariable]
        self.palette_widget.selected_index = index
        self.palette_widget.update()
        # Signal blocking ends automatically when blocker goes out of scope

    def set_palette(self, colors: list[tuple[int, int, int]], name: str = "") -> None:
        """Update the displayed palette."""
        self.palette_widget.set_palette(colors, name)

    def get_palette_colors(self) -> list[tuple[int, int, int]]:
        """Get the current palette colors."""
        return self.palette_widget.colors

    def get_color_at(self, index: int) -> tuple[int, int, int]:
        """Get RGB color at specific index."""
        if 0 <= index < len(self.palette_widget.colors):
            return self.palette_widget.colors[index]
        return (0, 0, 0)
