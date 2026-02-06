"""Facade for palette operations.

Groups palette-related controller methods: get/set sheet palette,
color extraction, and palette generation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ui.frame_mapping.services.palette_service import GamePaletteInfo, PaletteService
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette
    from ui.frame_mapping.facades.controller_context import ControllerContext

logger = get_logger(__name__)


class PaletteSignals(Protocol):
    """Protocol for palette-related signal emissions."""

    def emit_project_changed(self) -> None: ...
    def emit_save_requested(self) -> None: ...


class PaletteFacade:
    """Facade for palette operations.

    Handles sheet palette management, color extraction, and palette generation.
    """

    def __init__(
        self,
        context: ControllerContext,
        signals: PaletteSignals,
        palette_service: PaletteService,
    ) -> None:
        """Initialize the palette facade.

        Args:
            context: Shared controller context for project access.
            signals: Signal emitter for UI updates.
            palette_service: Service for palette operations.
        """
        self._context = context
        self._signals = signals
        self._palette_service = palette_service

    # ─── Sheet Palette ────────────────────────────────────────────────────────

    def get_sheet_palette(self) -> SheetPalette | None:
        """Get the current sheet palette.

        Returns:
            SheetPalette if defined, None otherwise.
        """
        return self._palette_service.get_sheet_palette(self._context.project)

    def set_sheet_palette(self, palette: SheetPalette | None) -> None:
        """Set the sheet palette for the project.

        Args:
            palette: SheetPalette to set, or None to clear.
        """
        self._palette_service.set_sheet_palette(self._context.project, palette)
        self._signals.emit_project_changed()
        self._signals.emit_save_requested()

    def set_sheet_palette_color(self, index: int, rgb: tuple[int, int, int]) -> None:
        """Update a single color in the sheet palette.

        Args:
            index: Palette index (0-15).
            rgb: New RGB color tuple.
        """
        self._palette_service.set_sheet_palette_color(self._context.project, index, rgb)
        self._signals.emit_project_changed()
        self._signals.emit_save_requested()

    # ─── Color Extraction ─────────────────────────────────────────────────────

    def extract_sheet_colors(self) -> dict[tuple[int, int, int], int]:
        """Extract unique colors from all AI frames in the project.

        Returns:
            Dict mapping RGB tuples to pixel counts.
        """
        return self._palette_service.extract_sheet_colors(self._context.project)

    def generate_sheet_palette_from_colors(
        self,
        colors: dict[tuple[int, int, int], int] | None = None,
    ) -> SheetPalette:
        """Generate a 16-color palette from AI sheet colors.

        Args:
            colors: Color counts to use, or None to extract from AI frames.

        Returns:
            Generated SheetPalette with auto-mapped colors.
        """
        return self._palette_service.generate_sheet_palette_from_colors(self._context.project, colors)

    # ─── Game Frame Palettes ──────────────────────────────────────────────────

    def copy_game_palette_to_sheet(self, game_frame_id: str) -> SheetPalette | None:
        """Create a SheetPalette from a game frame's palette.

        Args:
            game_frame_id: ID of game frame to copy palette from.

        Returns:
            SheetPalette with the game frame's colors, or None if not found.
        """
        return self._palette_service.copy_game_palette_to_sheet(self._context.project, game_frame_id)

    def get_game_palettes(self) -> dict[str, GamePaletteInfo]:
        """Get palettes from all game frames with display info.

        Returns:
            Dict mapping game frame IDs to GamePaletteInfo (colors + display name).
        """
        return self._palette_service.get_game_palettes(self._context.project)
