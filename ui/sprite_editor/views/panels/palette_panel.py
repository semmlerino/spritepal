#!/usr/bin/env python3
"""
Palette panel for the pixel editor.
Displays the color palette and handles color selection.
Integrates with PaletteSourceSelector for palette source management.
"""

import logging

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..widgets import ColorPaletteWidget, PaletteSourceSelector

logger = logging.getLogger(__name__)


class DismissibleWarningBanner(QFrame):
    """A dismissible warning banner with yellow background and X button."""

    dismissed = Signal()  # Emitted when user clicks X button

    def __init__(self, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("warningBanner")
        self._setup_ui(message)

    def _setup_ui(self, message: str) -> None:
        """Set up the banner UI."""
        self.setStyleSheet("""
            QFrame#warningBanner {
                background-color: #FFF3CD;
                border: 1px solid #FFEEBA;
                border-radius: 4px;
                padding: 4px;
            }
            QLabel {
                color: #856404;
                font-size: 11px;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #856404;
                font-weight: bold;
                font-size: 12px;
                padding: 2px 6px;
            }
            QPushButton:hover {
                background-color: #FFEEBA;
                border-radius: 2px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 4, 4)
        layout.setSpacing(4)

        # Warning icon
        icon_label = QLabel("\u26a0")  # Warning sign
        icon_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(icon_label)

        # Message text
        self._message_label = QLabel(message)
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label, 1)

        # Dismiss button (multiplication sign as X)
        dismiss_btn = QPushButton("\u00d7")
        dismiss_btn.setFixedSize(20, 20)
        dismiss_btn.setToolTip("Dismiss")
        dismiss_btn.clicked.connect(self._on_dismiss)
        layout.addWidget(dismiss_btn)

    def _on_dismiss(self) -> None:
        """Handle dismiss button click."""
        self.hide()
        self.dismissed.emit()

    def set_message(self, message: str) -> None:
        """Update the warning message."""
        self._message_label.setText(message)


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
    galleryPaletteSelected = Signal(int)  # Emitted when palette selected from gallery
    manualPaletteRequested = Signal()  # Emitted when manual palette offset is requested

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Store palette data for gallery popup
        self._rom_palettes: dict[int, list[tuple[int, int, int]]] = {}
        self._active_palette_indices: list[int] = []
        self._palette_descriptions: dict[int, str] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the palette panel UI."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Palette group box
        palette_group = QGroupBox("PALETTE")
        palette_layout = QVBoxLayout()

        # Create and add palette source selector
        self.palette_source_selector = PaletteSourceSelector()
        self.palette_source_selector.sourceChanged.connect(self.sourceChanged.emit)
        self.palette_source_selector.loadPaletteClicked.connect(self.loadPaletteClicked.emit)
        self.palette_source_selector.savePaletteClicked.connect(self.savePaletteClicked.emit)
        self.palette_source_selector.editColorClicked.connect(self.editColorClicked.emit)
        self.palette_source_selector.manualPaletteRequested.connect(self.manualPaletteRequested.emit)
        palette_layout.addWidget(self.palette_source_selector)

        # View All button (opens gallery popup)
        view_all_row = QHBoxLayout()
        view_all_row.setContentsMargins(0, 0, 0, 0)
        self._view_all_btn = QPushButton("View All Palettes...")
        self._view_all_btn.setToolTip("Open gallery to see all ROM palettes at once")
        self._view_all_btn.clicked.connect(self._show_palette_gallery)
        self._view_all_btn.setEnabled(False)  # Disabled until ROM palettes loaded
        view_all_row.addWidget(self._view_all_btn)
        view_all_row.addStretch()
        palette_layout.addLayout(view_all_row)

        # Create dismissible warning banner (hidden by default)
        self._warning_banner = DismissibleWarningBanner("", self)
        self._warning_banner.hide()
        palette_layout.addWidget(self._warning_banner)

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

    def add_palette_source(
        self,
        display_name: str,
        source_type: str,
        palette_index: int,
        colors: list[tuple[int, int, int]] | None = None,
        is_active: bool = False,
    ) -> None:
        """Add a palette source to the dropdown.

        Args:
            display_name: Display name for the source (e.g., "Mesen2 #1", "ROM Palette 8")
            source_type: Type of source ("default", "mesen", or "rom")
            palette_index: Palette index (0-15)
            colors: Optional list of RGB tuples for preview swatches
            is_active: Whether this palette is OAM-active (detected in use)
        """
        self.palette_source_selector.add_palette_source(display_name, source_type, palette_index, colors, is_active)

        # Store ROM palette data for gallery popup
        if source_type == "rom" and colors:
            self._rom_palettes[palette_index] = colors
            if is_active and palette_index not in self._active_palette_indices:
                self._active_palette_indices.append(palette_index)
            # Extract description if present (format: "ROM Palette X - Description")
            if " - " in display_name:
                desc = display_name.split(" - ", 1)[1]
                self._palette_descriptions[palette_index] = desc
            # Enable View All button when we have ROM palettes
            self._view_all_btn.setEnabled(True)

    def clear_mesen_sources(self) -> None:
        """Remove all Mesen2 sources, keeping only "Default"."""
        self.palette_source_selector.clear_mesen_sources()

    def clear_rom_sources(self) -> None:
        """Remove all ROM palette sources, keeping Default and Mesen sources."""
        self.palette_source_selector.clear_rom_sources()
        # Clear stored ROM palette data
        self._rom_palettes.clear()
        self._active_palette_indices.clear()
        self._palette_descriptions.clear()
        self._view_all_btn.setEnabled(False)

    def clear_palette_sources(self, source_type: str) -> None:
        """Clear palette sources of a specific type.

        Args:
            source_type: "rom", "mesen", or "all"
        """
        if source_type == "rom":
            self.clear_rom_sources()
        elif source_type == "mesen":
            self.clear_mesen_sources()
        elif source_type == "all":
            self.clear_rom_sources()
            self.clear_mesen_sources()
        else:
            logger.warning("Unknown palette source type to clear: %r", source_type)

    def _show_palette_gallery(self) -> None:
        """Show the palette gallery popup."""
        from ..dialogs import PaletteGalleryPopup

        if not self._rom_palettes:
            return

        popup = PaletteGalleryPopup(
            palettes=self._rom_palettes,
            active_indices=self._active_palette_indices,
            descriptions=self._palette_descriptions,
            parent=self,
        )
        popup.palette_selected.connect(self._on_gallery_palette_selected)
        popup.exec()

    def _on_gallery_palette_selected(self, palette_index: int) -> None:
        """Handle palette selection from gallery popup."""
        # Update the dropdown to match
        self.palette_source_selector.set_selected_source("rom", palette_index)
        # Emit signal for external handlers (e.g., controller)
        self.galleryPaletteSelected.emit(palette_index)

    def show_palette_warning(self, message: str) -> None:
        """Show a dismissible warning banner above the palette.

        Args:
            message: Warning message to display
        """
        self._warning_banner.set_message(message)
        self._warning_banner.show()

    def hide_palette_warning(self) -> None:
        """Hide the warning banner."""
        self._warning_banner.hide()
