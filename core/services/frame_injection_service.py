"""Frame injection service for preparing ROM tile batches.

This service converts a composited sprite image into tile batches ready
for ROM injection. It handles:
- Tile grouping by ROM offset
- 8x8 tile extraction
- Counter-flip for correct ROM storage
- Per-tile palette quantization
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PIL import Image

from core.palette_utils import quantize_to_palette, snes_palette_to_rgb
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.mesen_integration.click_extractor import CaptureBoundingBox, CaptureResult, OAMEntry

logger = get_logger(__name__)


@dataclass
class TileInfo:
    """Information about a single tile for injection."""

    vram_addr: int
    screen_x: int
    screen_y: int
    palette_index: int
    tile_index_in_block: int | None
    flip_h: bool
    flip_v: bool


@dataclass
class TileInjectionBatch:
    """A batch of tiles for injection at a single ROM offset.

    Attributes:
        rom_offset: Where in the ROM to inject these tiles.
        tile_image: Grid of 8x8 tiles arranged for injection.
        tile_count: Number of tiles in this batch.
        palette_index: Palette used for quantization.
        is_raw: Whether this should be injected as RAW (uncompressed).
    """

    rom_offset: int
    tile_image: Image.Image
    tile_count: int
    palette_index: int
    is_raw: bool = False


@dataclass
class TileGroup:
    """A group of tiles at the same ROM offset."""

    rom_offset: int
    tiles: dict[int, TileInfo] = field(default_factory=dict)  # vram_addr -> TileInfo

    def add_tile(self, tile_info: TileInfo) -> None:
        """Add a tile if not already present (by vram_addr)."""
        if tile_info.vram_addr not in self.tiles:
            self.tiles[tile_info.vram_addr] = tile_info


class FrameInjectionService:
    """Service for preparing tile batches from composited images.

    Converts a masked/composited image into tile batches grouped by
    ROM offset, ready for injection via ROMInjector.
    """

    def prepare_injection_batches(
        self,
        masked_canvas: Image.Image,
        capture_result: CaptureResult,
        selected_entry_ids: list[int] | None = None,
    ) -> list[TileInjectionBatch]:
        """Prepare tile batches for ROM injection.

        Args:
            masked_canvas: The composited image (RGBA) with AI frame applied.
            capture_result: Parsed Mesen capture with OAM entries.
            selected_entry_ids: If provided, only these entries are processed.

        Returns:
            List of TileInjectionBatch ready for injection.
        """
        # Filter entries if specified
        if selected_entry_ids is not None:
            selected_ids = set(selected_entry_ids)
            entries = [e for e in capture_result.entries if e.id in selected_ids]
        else:
            entries = capture_result.entries

        if not entries:
            logger.warning("No entries to process for injection")
            return []

        # Get bounding box for coordinate conversion
        bbox = capture_result.bounding_box

        # Group tiles by ROM offset
        tile_groups = self._group_tiles_by_rom_offset(entries, bbox)

        logger.debug(
            "Tile grouping: %d unique ROM offsets from %d entries",
            len(tile_groups),
            len(entries),
        )

        # Process each group into an injection batch
        batches = []
        for rom_offset, group in tile_groups.items():
            batch = self._create_injection_batch(
                rom_offset=rom_offset,
                group=group,
                masked_canvas=masked_canvas,
                bbox=bbox,
                capture_result=capture_result,
            )
            if batch is not None:
                batches.append(batch)

        return batches

    def _group_tiles_by_rom_offset(
        self,
        entries: list[OAMEntry],
        bbox: CaptureBoundingBox,
    ) -> dict[int, TileGroup]:
        """Group tiles by their ROM offset.

        Returns a dict mapping rom_offset -> TileGroup with all tiles
        that should be injected at that offset.
        """
        groups: dict[int, TileGroup] = {}

        for entry in entries:
            for tile in entry.tiles:
                if tile.rom_offset is None:
                    continue

                # Calculate tile's screen position
                # tile.pos_x/pos_y are tile indices within the entry
                local_x = tile.pos_x * 8
                local_y = tile.pos_y * 8

                # Apply entry-level flips to get correct screen position
                # This mirrors CaptureRenderer._render_tile() logic
                if entry.flip_h:
                    local_x = entry.width - local_x - 8
                if entry.flip_v:
                    local_y = entry.height - local_y - 8

                # Convert to screen position
                screen_x = entry.x + local_x
                screen_y = entry.y + local_y

                # Create or get group
                if tile.rom_offset not in groups:
                    groups[tile.rom_offset] = TileGroup(rom_offset=tile.rom_offset)

                # Add tile info
                tile_info = TileInfo(
                    vram_addr=tile.vram_addr,
                    screen_x=screen_x,
                    screen_y=screen_y,
                    palette_index=entry.palette,
                    tile_index_in_block=tile.tile_index_in_block,
                    flip_h=entry.flip_h,
                    flip_v=entry.flip_v,
                )
                groups[tile.rom_offset].add_tile(tile_info)

        return groups

    def _create_injection_batch(
        self,
        rom_offset: int,
        group: TileGroup,
        masked_canvas: Image.Image,
        bbox: CaptureBoundingBox,
        capture_result: CaptureResult,
    ) -> TileInjectionBatch | None:
        """Create an injection batch for a single ROM offset."""
        if not group.tiles:
            return None

        # Sort tiles by tile_index_in_block (for proper ROM order)
        sorted_vram_addrs = self._sort_tiles(group.tiles)
        tile_count = len(sorted_vram_addrs)

        # Determine grid layout (square-ish, preferring wider)
        grid_width = math.ceil(math.sqrt(tile_count))
        grid_height = math.ceil(tile_count / grid_width)

        logger.debug(
            "ROM offset 0x%X: preparing %d tiles, grid %dx%d",
            rom_offset,
            tile_count,
            grid_width,
            grid_height,
        )

        # Create output image for this ROM offset's tiles
        chunk_img = Image.new(
            "RGBA",
            (grid_width * 8, grid_height * 8),
            (0, 0, 0, 0),
        )

        # Get palette from first tile
        first_tile = group.tiles[sorted_vram_addrs[0]]
        palette_index = first_tile.palette_index

        # Extract each 8x8 tile and place in grid
        for idx, vram_addr in enumerate(sorted_vram_addrs):
            tile_info = group.tiles[vram_addr]

            # Convert screen coords to masked_canvas coords
            canvas_x = tile_info.screen_x - bbox.x
            canvas_y = tile_info.screen_y - bbox.y

            # Extract 8x8 tile from masked canvas
            tile_img = masked_canvas.crop((canvas_x, canvas_y, canvas_x + 8, canvas_y + 8))

            # Counter-flip: undo screen-appearance flip for ROM storage
            # ROM stores tiles unflipped; SNES hardware applies flip at display time
            if tile_info.flip_h:
                tile_img = tile_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if tile_info.flip_v:
                tile_img = tile_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

            # Calculate position in output grid
            grid_x = (idx % grid_width) * 8
            grid_y = (idx // grid_width) * 8

            chunk_img.paste(tile_img, (grid_x, grid_y))

        # Quantize to game palette (per-tile palette)
        snes_palette = capture_result.palettes.get(palette_index, [])
        if snes_palette:
            palette_rgb = snes_palette_to_rgb(snes_palette)
            chunk_img = quantize_to_palette(chunk_img, palette_rgb)
            logger.debug(
                "Quantized chunk for offset 0x%X to palette %d (%d colors)",
                rom_offset,
                palette_index,
                len(palette_rgb),
            )
        else:
            logger.warning(
                "No palette data for palette index %d at offset 0x%X",
                palette_index,
                rom_offset,
            )

        return TileInjectionBatch(
            rom_offset=rom_offset,
            tile_image=chunk_img,
            tile_count=tile_count,
            palette_index=palette_index,
            is_raw=False,  # Caller will determine based on ROM structure
        )

    def _sort_tiles(self, tiles: dict[int, TileInfo]) -> list[int]:
        """Sort tiles by tile_index_in_block, falling back to vram_addr."""

        def tile_sort_key(vram_addr: int) -> tuple[int, int]:
            tile_info = tiles[vram_addr]
            # Use tile_index_in_block if available, otherwise vram_addr
            if tile_info.tile_index_in_block is not None:
                return (tile_info.tile_index_in_block, vram_addr)
            return (vram_addr, 0)

        return sorted(tiles.keys(), key=tile_sort_key)
