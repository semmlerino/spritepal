"""Service for managing frame mapping project palettes.

Provides palette extraction, generation, and manipulation for both AI sheet
palettes and game frame capture palettes.
"""

from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError

from PIL import Image
from PySide6.QtCore import QObject, Signal

from core.frame_mapping_project import FrameMappingProject, SheetPalette


@dataclass
class GamePaletteInfo:
    """Information about a game frame's palette for display in dialogs."""

    colors: list[tuple[int, int, int]]
    display_name: str  # GameFrame.name property (display_name or ID fallback)
from core.palette_utils import (
    extract_unique_colors,
    find_nearest_palette_index,
    quantize_colors_to_palette,
    snes_palette_to_rgb,
)
from core.repositories.capture_result_repository import CaptureResultRepository
from utils.logging_config import get_logger

logger = get_logger(__name__)


class PaletteService(QObject):
    """Service for palette operations in frame mapping projects.

    This is a stateless service - all methods take a project parameter
    rather than storing project state internally.

    Signals:
        sheet_palette_changed: Emitted when the sheet palette is modified
    """

    sheet_palette_changed = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        capture_repository: CaptureResultRepository,
    ) -> None:
        """Initialize the palette service.

        Args:
            parent: Optional Qt parent object
            capture_repository: Shared repository for caching parsed capture files.
        """
        super().__init__(parent)
        self._capture_repository = capture_repository

    def get_sheet_palette(self, project: FrameMappingProject | None) -> SheetPalette | None:
        """Get the current sheet palette.

        Args:
            project: The frame mapping project to query

        Returns:
            SheetPalette if defined, None otherwise
        """
        if project is None:
            return None
        return project.sheet_palette

    def set_sheet_palette(
        self,
        project: FrameMappingProject | None,
        palette: SheetPalette | None,
    ) -> None:
        """Set the sheet palette for the project.

        Args:
            project: The frame mapping project to modify
            palette: SheetPalette to set, or None to clear
        """
        if project is None:
            logger.warning("set_sheet_palette: No project loaded")
            return

        # Validate transparency index assumption
        if palette is not None and palette.colors and palette.colors[0] != (0, 0, 0):
            logger.warning(
                "SheetPalette index 0 is %s, not (0,0,0). "
                "SNES sprites assume index 0 is transparent. "
                "This may cause incorrect transparency.",
                palette.colors[0],
            )

        project.sheet_palette = palette
        self.sheet_palette_changed.emit()
        if palette is not None:
            logger.info("Set sheet palette with %d color mappings", len(palette.color_mappings))
        else:
            logger.info("Cleared sheet palette")

    def set_sheet_palette_color(
        self,
        project: FrameMappingProject | None,
        index: int,
        rgb: tuple[int, int, int],
    ) -> None:
        """Update a single color in the sheet palette.

        Args:
            project: The frame mapping project to modify
            index: Palette index (0-15)
            rgb: New RGB color tuple
        """
        if project is None:
            logger.warning("set_sheet_palette_color: No project loaded")
            return

        if project.sheet_palette is None:
            logger.warning("set_sheet_palette_color: No sheet palette defined")
            return

        if not 0 <= index < 16:
            logger.warning("set_sheet_palette_color: Invalid index %d", index)
            return

        # Update the palette color
        palette = project.sheet_palette
        colors = list(palette.colors)
        if index < len(colors):
            colors[index] = rgb
        else:
            # Extend if needed
            while len(colors) <= index:
                colors.append((0, 0, 0))
            colors[index] = rgb

        # Update color_mappings: keep existing mappings unchanged
        updated_mappings = dict(palette.color_mappings)

        # Preserve non-color settings (background removal + quantization)
        project.sheet_palette = SheetPalette(
            colors=colors,
            color_mappings=updated_mappings,
            background_color=palette.background_color,
            background_tolerance=palette.background_tolerance,
            alpha_threshold=palette.alpha_threshold,
            dither_mode=palette.dither_mode,
            dither_strength=palette.dither_strength,
        )

        self.sheet_palette_changed.emit()
        logger.info("Updated sheet palette color [%d] to RGB%s", index, rgb)

    def extract_sheet_colors(
        self,
        project: FrameMappingProject | None,
    ) -> dict[tuple[int, int, int], int]:
        """Extract unique colors from all AI frames in the project.

        Args:
            project: The frame mapping project to analyze

        Returns:
            Dict mapping RGB tuples to pixel counts
        """
        if project is None:
            return {}

        all_colors: dict[tuple[int, int, int], int] = {}

        for ai_frame in project.ai_frames:
            if not ai_frame.path.exists():
                continue

            try:
                with Image.open(ai_frame.path) as img:
                    frame_colors = extract_unique_colors(img, ignore_transparent=True)
                    # Merge with totals
                    for color, count in frame_colors.items():
                        all_colors[color] = all_colors.get(color, 0) + count
            except (OSError, ValueError) as e:
                logger.warning("Failed to extract colors from %s: %s", ai_frame.path, e)

        logger.info("Extracted %d unique colors from %d AI frames", len(all_colors), len(project.ai_frames))
        return all_colors

    def generate_sheet_palette_from_colors(
        self,
        project: FrameMappingProject | None,
        colors: dict[tuple[int, int, int], int] | None = None,
    ) -> SheetPalette:
        """Generate a 16-color palette from AI sheet colors.

        Args:
            project: The frame mapping project to use for color extraction
            colors: Color counts to use, or None to extract from AI frames

        Returns:
            Generated SheetPalette with auto-mapped colors
        """
        if colors is None:
            colors = self.extract_sheet_colors(project)

        # Generate 16-color palette
        palette_colors = quantize_colors_to_palette(colors, max_colors=16, snap_to_snes=True)

        # Auto-map all colors to nearest palette colors
        color_mappings: dict[tuple[int, int, int], int] = {}
        for color in colors:
            color_mappings[color] = find_nearest_palette_index(color, palette_colors)

        return SheetPalette(colors=palette_colors, color_mappings=color_mappings)

    def copy_game_palette_to_sheet(
        self,
        project: FrameMappingProject | None,
        game_frame_id: str,
    ) -> SheetPalette | None:
        """Create a SheetPalette from a game frame's palette.

        Args:
            project: The frame mapping project containing the game frame
            game_frame_id: ID of game frame to copy palette from

        Returns:
            SheetPalette with the game frame's colors, or None if not found
        """
        if project is None:
            return None

        game_frame = project.get_game_frame_by_id(game_frame_id)
        if game_frame is None or game_frame.capture_path is None:
            return None

        # Parse capture to get palette (use repository for caching)
        try:
            capture_result = self._capture_repository.get_or_parse(game_frame.capture_path)
            palette_index = game_frame.palette_index

            # Validate palette_index exists in capture
            if palette_index not in capture_result.palettes:
                available_palettes = list(capture_result.palettes.keys())
                logger.warning(
                    "GameFrame %s has palette_index=%d which doesn't exist in capture. "
                    "Available palettes: %s. Using first available.",
                    game_frame_id,
                    palette_index,
                    available_palettes,
                )
                if available_palettes:
                    palette_index = available_palettes[0]
                else:
                    logger.warning("No palettes found in capture for game frame %s", game_frame_id)
                    return None

            snes_palette = capture_result.palettes.get(palette_index, [])

            if not snes_palette:
                logger.warning("No palette found for game frame %s", game_frame_id)
                return None

            # Convert to RGB
            palette_rgb = snes_palette_to_rgb(snes_palette)

            # Ensure 16 colors
            while len(palette_rgb) < 16:
                palette_rgb.append((0, 0, 0))
            palette_rgb = palette_rgb[:16]

            # Auto-map sheet colors to this palette
            sheet_colors = self.extract_sheet_colors(project)
            color_mappings: dict[tuple[int, int, int], int] = {}
            for color in sheet_colors:
                color_mappings[color] = find_nearest_palette_index(color, palette_rgb)

            logger.info("Copied palette from game frame %s", game_frame_id)
            return SheetPalette(colors=palette_rgb, color_mappings=color_mappings)

        except (OSError, JSONDecodeError, KeyError, ValueError) as e:
            logger.exception("Failed to copy game palette from %s: %s", game_frame_id, e)
            return None

    def get_game_palettes(
        self,
        project: FrameMappingProject | None,
    ) -> dict[str, GamePaletteInfo]:
        """Get palettes from all game frames with display info.

        Args:
            project: The frame mapping project to query

        Returns:
            Dict mapping game frame IDs to GamePaletteInfo (colors + display name)
        """
        if project is None:
            return {}

        result: dict[str, GamePaletteInfo] = {}

        for game_frame in project.game_frames:
            if game_frame.capture_path is None or not game_frame.capture_path.exists():
                continue

            try:
                # Use repository for caching (important in loops)
                capture_result = self._capture_repository.get_or_parse(game_frame.capture_path)
                palette_index = game_frame.palette_index

                # Validate palette_index exists in capture
                if palette_index not in capture_result.palettes:
                    available_palettes = list(capture_result.palettes.keys())
                    logger.warning(
                        "GameFrame %s has palette_index=%d which doesn't exist in capture. Available: %s",
                        game_frame.id,
                        palette_index,
                        available_palettes,
                    )
                    if available_palettes:
                        palette_index = available_palettes[0]
                    else:
                        continue

                snes_palette = capture_result.palettes.get(palette_index, [])

                if snes_palette:
                    result[game_frame.id] = GamePaletteInfo(
                        colors=snes_palette_to_rgb(snes_palette),
                        display_name=game_frame.name,  # Uses display_name or ID fallback
                    )
            except (OSError, JSONDecodeError, KeyError, ValueError) as e:
                logger.debug("Could not load palette for %s: %s", game_frame.id, e)

        return result
