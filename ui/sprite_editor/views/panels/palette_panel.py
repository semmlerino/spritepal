#!/usr/bin/env python3
"""
Palette panel for the pixel editor.
Displays the color palette and handles color selection.
Integrates with PaletteSourceSelector for palette source management.
"""

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget

from ..widgets import ColorPaletteWidget, PaletteSourceSelector


class PalettePanel(QWidget):
    """Panel for color palette display and selection.

    Provides palette source selection (default or Mesen2-captured),
    color palette display, and action buttons for palette management.
    """

    # Signals
    colorSelected = Signal(int)  # Emits color index when selected
    sourceChanged = Signal(str, int)  # Emits source_type, palette_index when palette source changes
    loadPaletteClicked = Signal()  # Emitted when "Load Palette..." button is clicked
    savePaletteClicked = Signal()  # Emitted when "Save Palette..." button is clicked
    editColorClicked = Signal()  # Emitted when "Edit Color" button is clicked

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

        # Create and add palette source selector
        self.palette_source_selector = PaletteSourceSelector()
        self.palette_source_selector.sourceChanged.connect(self.sourceChanged.emit)
        self.palette_source_selector.loadPaletteClicked.connect(self.loadPaletteClicked.emit)
        self.palette_source_selector.savePaletteClicked.connect(self.savePaletteClicked.emit)
        self.palette_source_selector.editColorClicked.connect(self.editColorClicked.emit)
        palette_layout.addWidget(self.palette_source_selector)

        # Create palette widget with larger cell size (48px instead of 32px)
        self.palette_widget = ColorPaletteWidget()
        self.palette_widget.cell_size = 48
        self.palette_widget.setMinimumSize(
            4 * self.palette_widget.cell_size + 10, 4 * self.palette_widget.cell_size + 10
        )
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

    def get_selected_palette_source(self) -> tuple[str, int]:
        """Get the currently selected palette source.

        Returns:
            Tuple of (source_type, palette_index) where source_type is "default"
            or "mesen" and palette_index is the palette number (0-7).
        """
        return self.palette_source_selector.get_selected_source()

    def set_selected_palette_source(self, source_type: str, palette_index: int) -> None:
        """Set the selected palette source.

        Args:
            source_type: Type of source ("default" or "mesen")
            palette_index: Palette index (0-7)
        """
        self.palette_source_selector.set_selected_source(source_type, palette_index)

    def add_palette_source(self, display_name: str, source_type: str, palette_index: int) -> None:
        """Add a palette source to the dropdown.

        Args:
            display_name: Display name for the source (e.g., "Mesen2 #1")
            source_type: Type of source ("default" or "mesen")
            palette_index: Palette index (0-7)
        """
        self.palette_source_selector.add_palette_source(display_name, source_type, palette_index)

    def clear_mesen_sources(self) -> None:
        """Remove all Mesen2 sources, keeping only "Default"."""
        self.palette_source_selector.clear_mesen_sources()
