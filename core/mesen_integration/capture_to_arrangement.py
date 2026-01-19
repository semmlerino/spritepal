"""Convert Mesen 2 sprite captures to arrangement grid tiles.

This module provides functionality to:
1. Group OAM entries by palette
2. Render each group's sprites
3. Split into 8x8 tiles for grid arrangement
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from PIL import Image

from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import CaptureResult, OAMEntry, OBSELConfig

logger = logging.getLogger(__name__)


@dataclass
class PaletteGroup:
    """OAM entries grouped by palette."""

    palette_index: int
    entries: list[OAMEntry]
    tiles: dict[tuple[int, int], Image.Image] = field(default_factory=dict)  # (row, col) -> 8x8 tile
    width_tiles: int = 0
    height_tiles: int = 0

    @property
    def entry_count(self) -> int:
        """Number of OAM entries in this group."""
        return len(self.entries)


@dataclass
class CaptureArrangementData:
    """Capture data converted to grid tiles."""

    source_path: str
    frame: int
    groups: list[PaletteGroup]
    palettes: dict[int, list[tuple[int, int, int]]]  # RGB palettes by index
    obsel: OBSELConfig
    total_tiles: int

    @property
    def has_tiles(self) -> bool:
        """Check if any tiles were extracted."""
        return self.total_tiles > 0

    @property
    def palette_indices(self) -> list[int]:
        """Get sorted list of palette indices with groups."""
        return sorted(g.palette_index for g in self.groups)


# Default garbage tile indices for Kirby games
DEFAULT_GARBAGE_TILES: set[int] = {0x03, 0x04}


class CaptureToArrangementConverter:
    """Converts Mesen captures to arrangement grid tiles."""

    def convert(
        self,
        capture: CaptureResult,
        source_path: str = "",
        selected_palettes: set[int] | None = None,
        filter_garbage_tiles: bool = True,
        garbage_tile_indices: set[int] | None = None,
        tile_size: int = 8,
    ) -> CaptureArrangementData:
        """
        Convert capture to grid-ready tile data.

        Args:
            capture: Mesen capture result to convert
            source_path: Path to the capture file (for reference)
            selected_palettes: Which palette indices to include (None = all)
            filter_garbage_tiles: Whether to exclude common garbage tiles
            garbage_tile_indices: Custom garbage tile indices (default: {0x03, 0x04})
            tile_size: Size of output tiles (default 8x8)

        Returns:
            CaptureArrangementData with tiles ready for grid display
        """
        if garbage_tile_indices is None:
            garbage_tile_indices = DEFAULT_GARBAGE_TILES

        # Filter entries by palette if requested
        entries = capture.entries
        if selected_palettes is not None:
            entries = [e for e in entries if e.palette in selected_palettes]

        # Filter garbage tiles if enabled
        if filter_garbage_tiles:
            entries = self._filter_garbage_entries(entries, garbage_tile_indices)

        # Group entries by palette
        palette_groups = self._group_by_palette(entries)

        # Convert palettes to RGB tuples
        rgb_palettes = self._convert_palettes(capture.palettes)

        # Create renderer for this capture
        renderer = CaptureRenderer(capture)

        # Process each group
        groups: list[PaletteGroup] = []
        total_tiles = 0

        for palette_idx, group_entries in sorted(palette_groups.items()):
            if selected_palettes is not None and palette_idx not in selected_palettes:
                continue

            group = self._render_and_split_group(
                palette_idx=palette_idx,
                entries=group_entries,
                renderer=renderer,
                tile_size=tile_size,
            )
            groups.append(group)
            total_tiles += len(group.tiles)

        return CaptureArrangementData(
            source_path=source_path,
            frame=capture.frame,
            groups=groups,
            palettes=rgb_palettes,
            obsel=capture.obsel,
            total_tiles=total_tiles,
        )

    def _filter_garbage_entries(
        self,
        entries: list[OAMEntry],
        garbage_indices: set[int],
    ) -> list[OAMEntry]:
        """Filter out entries that use common garbage tile indices."""
        filtered = []
        for entry in entries:
            # Check if any of the entry's tiles are garbage
            has_garbage = any(tile.tile_index in garbage_indices for tile in entry.tiles)
            if not has_garbage:
                filtered.append(entry)
            else:
                logger.debug(f"Filtered garbage entry: tile={entry.tile}, tiles={[t.tile_index for t in entry.tiles]}")
        return filtered

    def _group_by_palette(self, entries: list[OAMEntry]) -> dict[int, list[OAMEntry]]:
        """Group entries by their palette index."""
        groups: dict[int, list[OAMEntry]] = {}
        for entry in entries:
            if entry.palette not in groups:
                groups[entry.palette] = []
            groups[entry.palette].append(entry)
        return groups

    def _convert_palettes(
        self,
        palettes: dict[int, list[int | list[int]]],
    ) -> dict[int, list[tuple[int, int, int]]]:
        """Convert palette format to list of (R,G,B) tuples.

        Handles both packed RGB integers and RGB triplets.
        """
        rgb_palettes: dict[int, list[tuple[int, int, int]]] = {}
        for idx, colors in palettes.items():
            rgb_colors: list[tuple[int, int, int]] = []
            for color in colors:
                if isinstance(color, int):
                    # Colors stored as packed RGB integer (0xRRGGBB)
                    r = (color >> 16) & 0xFF
                    g = (color >> 8) & 0xFF
                    b = color & 0xFF
                    rgb_colors.append((r, g, b))
                else:
                    # Already RGB triplet (list[int]) - convert to tuple
                    rgb_colors.append((int(color[0]), int(color[1]), int(color[2])))
            rgb_palettes[idx] = rgb_colors
        return rgb_palettes

    def _render_and_split_group(
        self,
        palette_idx: int,
        entries: list[OAMEntry],
        renderer: CaptureRenderer,
        tile_size: int = 8,
    ) -> PaletteGroup:
        """
        Render entries and split into tiles.

        1. Calculate group bounding box
        2. Render each entry relative to group origin
        3. Composite into single image
        4. Split into tile_size x tile_size tiles
        """
        if not entries:
            return PaletteGroup(palette_index=palette_idx, entries=[])

        # Calculate bounding box for all entries in group
        min_x = min(entry.x for entry in entries)
        min_y = min(entry.y for entry in entries)
        max_x = max(entry.x + entry.width for entry in entries)
        max_y = max(entry.y + entry.height for entry in entries)

        # Calculate dimensions
        width = max_x - min_x
        height = max_y - min_y

        # Round up to tile boundaries
        width_tiles = (width + tile_size - 1) // tile_size
        height_tiles = (height + tile_size - 1) // tile_size
        canvas_width = width_tiles * tile_size
        canvas_height = height_tiles * tile_size

        # Create composite canvas
        composite = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

        # Render each entry onto canvas
        for entry in entries:
            entry_img = renderer.render_entry(entry, transparent_bg=True)
            # Position relative to group origin
            x = entry.x - min_x
            y = entry.y - min_y
            composite.paste(entry_img, (x, y), entry_img)

        # Split into tiles
        tiles: dict[tuple[int, int], Image.Image] = {}
        for row in range(height_tiles):
            for col in range(width_tiles):
                x = col * tile_size
                y = row * tile_size
                tile_img = composite.crop((x, y, x + tile_size, y + tile_size))

                # Only include non-empty tiles (with any visible pixels)
                if tile_img.getbbox() is not None:
                    tiles[(row, col)] = tile_img

        return PaletteGroup(
            palette_index=palette_idx,
            entries=entries,
            tiles=tiles,
            width_tiles=width_tiles,
            height_tiles=height_tiles,
        )
