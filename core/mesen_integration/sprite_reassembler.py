"""
Sprite reassembler for composing multi-OAM sprites.

Takes capture data from Mesen 2 and extracts + composes complete sprites
using OAM layout information (positions, flips, etc.).

NOTE: This module is a work-in-progress. It expects CaptureResult entries to
include optional `rom_offset` values populated by a mapping step.
Use CaptureRenderer for rendering captured tiles, and CaptureToROMMapper for
ROM offset mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from core.hal_compression import HALCompressor
from core.mesen_integration.click_extractor import CaptureResult, OAMEntry
from core.tile_renderer import TileRenderer
from utils.constants import BYTES_PER_TILE
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ReassembledSprite:
    """Result of sprite reassembly."""

    image: Image.Image
    width: int
    height: int
    source_oam_entries: list[dict[str, object]] = field(default_factory=list)
    source_rom_offsets: list[int] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def save(self, path: str | Path) -> None:
        """Save composed sprite image to file."""
        self.image.save(path)
        logger.info(f"Saved sprite to {path}")


class SpriteReassembler:
    """
    Reassembles multi-OAM sprites using capture layout data.

    Handles:
    - Multiple ROM sources (tiles from different compressed blocks)
    - OAM-specified flips and positions
    - Variable tile sizes (8x8, 16x16, 32x32, 64x64)
    """

    def __init__(
        self,
        rom_path: str | Path,
        hal_compressor: HALCompressor | None = None,
        tile_renderer: TileRenderer | None = None,
    ):
        """
        Initialize reassembler.

        Args:
            rom_path: Path to ROM file
            hal_compressor: HAL compressor instance (created if None)
            tile_renderer: Tile renderer instance (created if None)
        """
        self.rom_path = Path(rom_path)
        self.hal_compressor = hal_compressor or HALCompressor()
        self.tile_renderer = tile_renderer or TileRenderer()
        self._decompression_cache: dict[int, bytes] = {}

    def reassemble(
        self,
        capture: CaptureResult,
        palette_index: int | None = None,
    ) -> ReassembledSprite:
        """
        Reassemble sprite from capture data.

        Args:
            capture: Capture result from MesenCaptureParser
            palette_index: Palette to use (None = grayscale)

        Returns:
            ReassembledSprite with composed image
        """
        if not capture.oam_entries:
            logger.warning("No OAM entries in capture")
            return ReassembledSprite(
                image=Image.new("RGBA", (8, 8), (0, 0, 0, 0)),
                width=8,
                height=8,
            )

        # Calculate canvas size from bounding box
        bbox = capture.bounding_box
        canvas_width = max(bbox.width, 8)
        canvas_height = max(bbox.height, 8)
        origin_x = bbox.x
        origin_y = bbox.y

        logger.info(
            f"Reassembling sprite: {len(capture.oam_entries)} OAM entries, "
            f"canvas {canvas_width}x{canvas_height}, origin ({origin_x}, {origin_y})"
        )

        # Create transparent canvas
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

        # Process each OAM entry
        entries_placed = 0
        for entry in capture.oam_entries:
            if entry.rom_offset is None:
                logger.debug(f"OAM entry {entry.id} has no ROM offset, skipping")
                continue

            try:
                tile_image = self._render_oam_entry(entry, palette_index)
                if tile_image is None:
                    continue

                # Position relative to sprite origin
                paste_x = entry.x - origin_x
                paste_y = entry.y - origin_y

                # Ensure we're within canvas bounds
                if paste_x < 0 or paste_y < 0:
                    logger.warning(f"OAM entry {entry.id} at ({paste_x}, {paste_y}) is outside canvas")
                    continue

                # Composite onto canvas (using alpha mask)
                canvas.paste(tile_image, (paste_x, paste_y), tile_image)
                entries_placed += 1

            except Exception as e:
                logger.warning(f"Failed to render OAM entry {entry.id}: {e}")
                continue

        logger.info(f"Placed {entries_placed}/{len(capture.oam_entries)} OAM entries")

        return ReassembledSprite(
            image=canvas,
            width=canvas_width,
            height=canvas_height,
            source_oam_entries=[self._entry_to_dict(e) for e in capture.oam_entries],
            source_rom_offsets=capture.unique_rom_offsets,
            metadata={
                "frame": capture.frame,
                "obsel": capture.obsel.__dict__ if capture.obsel else None,
                "origin": (origin_x, origin_y),
                "entries_placed": entries_placed,
            },
        )

    def reassemble_single_offset(
        self,
        capture: CaptureResult,
        rom_offset: int,
        palette_index: int | None = None,
    ) -> ReassembledSprite:
        """
        Reassemble only sprites from a specific ROM offset.

        Useful when multiple ROM sources are captured but you want
        to extract from just one.

        Args:
            capture: Capture result
            rom_offset: ROM offset to extract from
            palette_index: Palette to use

        Returns:
            ReassembledSprite with only tiles from specified offset
        """
        # Filter to entries with matching ROM offset
        filtered_entries = capture.get_entries_for_rom_offset(rom_offset)

        if not filtered_entries:
            logger.warning(f"No OAM entries found for ROM offset 0x{rom_offset:X}")
            return ReassembledSprite(
                image=Image.new("RGBA", (8, 8), (0, 0, 0, 0)),
                width=8,
                height=8,
            )

        # Calculate bounding box for filtered entries
        min_x = min(e.x for e in filtered_entries)
        min_y = min(e.y for e in filtered_entries)
        max_x = max(e.x + e.width for e in filtered_entries)
        max_y = max(e.y + e.height for e in filtered_entries)

        canvas_width = max_x - min_x
        canvas_height = max_y - min_y

        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

        for entry in filtered_entries:
            try:
                tile_image = self._render_oam_entry(entry, palette_index)
                if tile_image is None:
                    continue

                paste_x = entry.x - min_x
                paste_y = entry.y - min_y
                canvas.paste(tile_image, (paste_x, paste_y), tile_image)

            except Exception as e:
                logger.warning(f"Failed to render OAM entry {entry.id}: {e}")

        return ReassembledSprite(
            image=canvas,
            width=canvas_width,
            height=canvas_height,
            source_oam_entries=[self._entry_to_dict(e) for e in filtered_entries],
            source_rom_offsets=[rom_offset],
            metadata={
                "frame": capture.frame,
                "origin": (min_x, min_y),
                "single_offset": True,
            },
        )

    def extract_all_tiles(
        self,
        rom_offset: int,
        palette_index: int | None = None,
        tiles_per_row: int = 16,
    ) -> Image.Image | None:
        """
        Extract and render ALL tiles from a ROM offset as a grid.

        Useful for viewing complete tile data at an offset.

        Args:
            rom_offset: ROM offset to extract from
            palette_index: Palette to use
            tiles_per_row: Tiles per row in output grid

        Returns:
            Image with all tiles arranged in a grid
        """
        tiles_data = self._get_decompressed_data(rom_offset)
        if tiles_data is None:
            return None

        tile_count = len(tiles_data) // BYTES_PER_TILE
        if tile_count == 0:
            logger.warning(f"No complete tiles in data from 0x{rom_offset:X}")
            return None

        # Calculate grid dimensions
        rows = (tile_count + tiles_per_row - 1) // tiles_per_row
        actual_width = min(tile_count, tiles_per_row)

        logger.info(f"Rendering {tile_count} tiles from 0x{rom_offset:X} as {actual_width}x{rows} grid")

        return self.tile_renderer.render_tiles(tiles_data, actual_width, rows, palette_index)

    def _render_oam_entry(
        self,
        entry: OAMEntry,
        palette_index: int | None,
    ) -> Image.Image | None:
        """Render a single OAM entry's tiles."""
        if entry.rom_offset is None:
            return None

        tiles_data = self._get_decompressed_data(entry.rom_offset)
        if tiles_data is None:
            return None

        # Calculate how many 8x8 tiles make up this sprite
        tiles_wide = entry.width // 8
        tiles_high = entry.height // 8

        # SNES tile indexing: each OAM entry's tile number is the base
        # For 16x16 sprites, tiles are arranged as:
        #   [tile]   [tile+1]
        #   [tile+16][tile+17]
        # For larger sprites, pattern continues with 16-tile row stride

        # For now, assume contiguous tiles (simpler case)
        # TODO: Handle SNES tile arrangement with 16-tile row stride
        tile_count = tiles_wide * tiles_high
        start_offset = entry.tile * BYTES_PER_TILE
        end_offset = start_offset + (tile_count * BYTES_PER_TILE)

        if end_offset > len(tiles_data):
            logger.warning(
                f"OAM entry {entry.id} tile range exceeds decompressed data (need {end_offset}, have {len(tiles_data)})"
            )
            # Try to render what we have
            available_tiles = (len(tiles_data) - start_offset) // BYTES_PER_TILE
            if available_tiles <= 0:
                return None
            tiles_wide = min(tiles_wide, available_tiles)
            tiles_high = 1
            end_offset = start_offset + (tiles_wide * BYTES_PER_TILE)

        tile_bytes = tiles_data[start_offset:end_offset]

        # Render tiles
        img = self.tile_renderer.render_tiles(tile_bytes, tiles_wide, tiles_high, palette_index)

        if img is None:
            return None

        # Apply flips
        if entry.flip_h:
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if entry.flip_v:
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        return img

    def _get_decompressed_data(self, rom_offset: int) -> bytes | None:
        """Get decompressed data from ROM offset, with caching."""
        if rom_offset in self._decompression_cache:
            return self._decompression_cache[rom_offset]

        try:
            data = self.hal_compressor.decompress_from_rom(str(self.rom_path), rom_offset)
            self._decompression_cache[rom_offset] = data
            logger.debug(f"Decompressed {len(data)} bytes from ROM offset 0x{rom_offset:X}")
            return data
        except Exception as e:
            logger.error(f"Failed to decompress from 0x{rom_offset:X}: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear the decompression cache."""
        self._decompression_cache.clear()

    @staticmethod
    def _entry_to_dict(entry: OAMEntry) -> dict[str, object]:
        """Convert OAMEntry to dict for serialization."""
        return {
            "id": entry.id,
            "x": entry.x,
            "y": entry.y,
            "tile": entry.tile,
            "width": entry.width,
            "height": entry.height,
            "flip_h": entry.flip_h,
            "flip_v": entry.flip_v,
            "palette": entry.palette,
            "rom_offset": entry.rom_offset,
        }
