"""
Dialog wrapper for the Paged Tile View widget.

Provides a resizable popup dialog for browsing ROM tiles in a grid format,
launched from the Manual Offset Dialog.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialogButtonBox, QPushButton, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent

    from core.rom_extractor import ROMExtractor

from core.default_palette_loader import DefaultPaletteLoader
from ui.common.spacing_constants import SPACING_SMALL
from ui.components.base.cleanup_dialog import CleanupDialog
from ui.widgets.paged_tile_view import PagedTileViewWidget

# Settings keys for user palettes
USER_PALETTES_CATEGORY = "tile_grid_browser"
USER_PALETTES_KEY = "user_palettes"

logger = logging.getLogger(__name__)

# Default dialog size
DEFAULT_WIDTH = 900
DEFAULT_HEIGHT = 700
MIN_WIDTH = 600
MIN_HEIGHT = 400


class PagedTileViewDialog(CleanupDialog):
    """
    Popup dialog for browsing ROM tiles in a paged grid view.

    This dialog wraps the PagedTileViewWidget and provides:
    - Non-modal display so users can compare with the main dialog
    - "Go to Offset" button to navigate the parent dialog to a clicked tile
    - Proper cleanup of background workers on close

    Signals:
        offset_selected: Emitted when user wants to navigate to an offset.
            Args: ROM offset (int)
    """

    offset_selected = Signal(int)

    def __init__(
        self,
        parent: QWidget | None,
        rom_data: bytes,
        palette: list[list[int]] | None = None,
        initial_offset: int = 0,
        rom_extractor: ROMExtractor | None = None,
    ) -> None:
        """
        Initialize the paged tile view dialog.

        Args:
            parent: Parent widget (typically the Manual Offset Dialog)
            rom_data: Raw ROM byte data to display
            palette: Optional palette for tile rendering
            initial_offset: Starting offset to navigate to
            rom_extractor: Optional ROM extractor for decompression mode
        """
        # Store data before super().__init__ calls _setup_ui
        self._rom_data = rom_data
        self._palette = palette
        self._initial_offset = initial_offset
        self._rom_extractor = rom_extractor
        self._selected_offset: int | None = None

        # Initialize tile view widget reference
        self._tile_view: PagedTileViewWidget | None = None

        super().__init__(
            parent,
            title="Tile Grid Browser",
            modal=False,  # Non-modal so user can compare
            min_size=(MIN_WIDTH, MIN_HEIGHT),
            size=(DEFAULT_WIDTH, DEFAULT_HEIGHT),
            with_button_box=False,  # We'll create custom buttons
        )

    @override
    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        # Get the content widget from base class
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)
        layout.setSpacing(SPACING_SMALL)

        # Create tile view widget
        self._tile_view = PagedTileViewWidget()
        self._tile_view.set_rom_data(self._rom_data)

        # Set ROM injector for decompression mode (if extractor provided)
        if self._rom_extractor is not None:
            self._tile_view.set_rom_injector(self._rom_extractor.rom_injector)

        # Load default palettes from config
        self._load_default_palettes()

        # Load saved user palettes from settings
        self._load_saved_user_palettes()

        # Set the provided palette (if any) as "Current" and select it
        if self._palette is not None:
            self._tile_view.set_palette(self._palette, name="Current")

        # Navigate to initial offset
        if self._initial_offset > 0:
            self._tile_view.go_to_offset(self._initial_offset)

        # Connect signals
        self._tile_view.tile_clicked.connect(self._on_tile_clicked)

        layout.addWidget(self._tile_view, stretch=1)

        # Custom button box
        button_box = QDialogButtonBox()

        # "Go to Offset" button - navigates parent dialog
        self._go_to_btn = QPushButton("Go to Offset")
        self._go_to_btn.setToolTip("Navigate to the selected tile in the Manual Offset dialog")
        self._go_to_btn.setEnabled(False)
        self._go_to_btn.clicked.connect(self._on_go_to_clicked)
        button_box.addButton(self._go_to_btn, QDialogButtonBox.ButtonRole.ActionRole)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_box.addButton(close_btn, QDialogButtonBox.ButtonRole.RejectRole)

        layout.addWidget(button_box)

    def _load_default_palettes(self) -> None:
        """Load default palettes into the dropdown."""
        if self._tile_view is None:
            return

        try:
            # Try to get loader from app context first
            try:
                from core.app_context import get_app_context

                loader = get_app_context().default_palette_loader
            except (RuntimeError, AttributeError):
                # App context not available, create standalone loader
                loader = DefaultPaletteLoader()

            # Get all Kirby palettes
            kirby_palettes = loader.get_all_kirby_palettes()

            # Add each palette to the dropdown
            for index, colors in sorted(kirby_palettes.items()):
                # Find the palette name from the loader data
                name = f"Kirby Palette {index}"

                # Look for specific names in the palette data
                for palette_entry in loader.get_all_presets():
                    if palette_entry.get("index") == index:
                        name = palette_entry.get("name", name)
                        break

                # Convert RGBColor tuples to lists for compatibility
                palette_as_lists: list[list[int]] = [list(c) for c in colors]
                self._tile_view.add_palette_option(name, palette_as_lists)

            logger.debug(f"Loaded {len(kirby_palettes)} default palettes")

        except Exception as e:
            logger.warning(f"Failed to load default palettes: {e}")

    def _load_saved_user_palettes(self) -> None:
        """Load saved user palettes from application settings."""
        if self._tile_view is None:
            return

        try:
            from core.app_context import get_app_context

            state_manager = get_app_context().application_state_manager
            saved_palettes = state_manager.get(USER_PALETTES_CATEGORY, USER_PALETTES_KEY, None)

            if saved_palettes and isinstance(saved_palettes, dict):
                # Convert back to proper format (JSON may have nested lists)
                palettes: dict[str, list[list[int]]] = {}
                for name, colors in saved_palettes.items():
                    if isinstance(colors, list) and len(colors) > 0:
                        # Ensure colors are in list[list[int]] format
                        palettes[name] = [[int(c) for c in color] for color in colors]

                self._tile_view.load_user_palettes(palettes)
                logger.debug(f"Loaded {len(palettes)} saved user palettes")

        except (RuntimeError, AttributeError) as e:
            logger.debug(f"App context not available for loading palettes: {e}")
        except Exception as e:
            logger.warning(f"Failed to load saved user palettes: {e}")

    def _save_user_palettes(self) -> None:
        """Save user palettes to application settings."""
        if self._tile_view is None:
            return

        try:
            from core.app_context import get_app_context

            state_manager = get_app_context().application_state_manager
            user_palettes = self._tile_view.get_user_palettes()

            if user_palettes:
                state_manager.set(USER_PALETTES_CATEGORY, USER_PALETTES_KEY, user_palettes)
                logger.debug(f"Saved {len(user_palettes)} user palettes")
            else:
                # Clear saved palettes if none remain
                state_manager.set(USER_PALETTES_CATEGORY, USER_PALETTES_KEY, {})
                logger.debug("Cleared saved user palettes")

        except (RuntimeError, AttributeError) as e:
            logger.debug(f"App context not available for saving palettes: {e}")
        except Exception as e:
            logger.warning(f"Failed to save user palettes: {e}")

    def _on_tile_clicked(self, offset: int) -> None:
        """Handle tile click from the tile view."""
        self._selected_offset = offset
        self._go_to_btn.setEnabled(True)
        self._go_to_btn.setText(f"Go to 0x{offset:06X}")
        logger.debug(f"Tile selected: 0x{offset:06X}")

    def _on_go_to_clicked(self) -> None:
        """Handle "Go to Offset" button click."""
        if self._selected_offset is not None:
            logger.debug(f"Navigating to offset 0x{self._selected_offset:06X}")
            self.offset_selected.emit(self._selected_offset)

    def set_palette(self, palette: list[list[int]] | None) -> None:
        """
        Update the tile rendering palette.

        Args:
            palette: New palette or None for grayscale
        """
        self._palette = palette
        if self._tile_view is not None:
            self._tile_view.set_palette(palette)

    def go_to_offset(self, offset: int) -> None:
        """
        Navigate to the page containing a specific offset.

        Args:
            offset: ROM byte offset
        """
        if self._tile_view is not None:
            self._tile_view.go_to_offset(offset)

    def get_current_offset(self) -> int:
        """Get the starting offset of the current page."""
        if self._tile_view is not None:
            return self._tile_view.get_current_offset()
        return 0

    @override
    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Handle dialog close."""
        # Save user palettes before cleanup
        self._save_user_palettes()

        # Clean up the tile view
        if self._tile_view is not None:
            self._tile_view.cleanup()

        super().closeEvent(event)
