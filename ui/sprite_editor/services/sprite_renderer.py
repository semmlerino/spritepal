#!/usr/bin/env python3
"""
Sprite rendering service.
Handles extraction of sprites from VRAM and palette application.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    import numpy as np

from ..constants import (
    BYTES_PER_TILE_4BPP,
    PIXELS_PER_TILE,
    TILE_HEIGHT,
    TILE_WIDTH,
)
from ..core.palette_utils import get_grayscale_palette, read_cgram_palette
from ..core.tile_utils import calculate_dimensions_from_tile_data, decode_4bpp_tile
from .oam_palette_mapper import OAMPaletteMapper

logger = logging.getLogger(__name__)


class SpriteRenderer:
    """Service for sprite extraction and rendering."""

    def __init__(self, oam_mapper: OAMPaletteMapper | None = None) -> None:
        self.oam_mapper = oam_mapper

    def set_oam_mapper(self, oam_mapper: OAMPaletteMapper | None) -> None:
        """Set or update the OAM mapper for palette assignments."""
        self.oam_mapper = oam_mapper

    def _decode_all_tiles(self, data: bytes) -> list[int]:
        """Decode all tiles from VRAM data into a flat pixel array."""
        pixels: list[int] = []
        total_tiles = len(data) // BYTES_PER_TILE_4BPP
        for tile_idx in range(total_tiles):
            if tile_idx * BYTES_PER_TILE_4BPP + BYTES_PER_TILE_4BPP <= len(data):
                tile = decode_4bpp_tile(data, tile_idx * BYTES_PER_TILE_4BPP)
                pixels.extend(tile)
        return pixels

    def _arrange_tiles_in_indexed_image(
        self,
        pixels: list[int],
        total_tiles: int,
        tiles_x: int,
        tiles_y: int,
        width: int,
        height: int,
    ) -> list[int]:
        """Arrange decoded tile pixels into final image layout."""
        img_pixels = [0] * (width * height)
        for tile_idx in range(min(total_tiles, tiles_x * tiles_y)):
            tile_x = tile_idx % tiles_x
            tile_y = tile_idx // tiles_x

            for y in range(TILE_HEIGHT):
                for x in range(TILE_WIDTH):
                    src_idx = tile_idx * PIXELS_PER_TILE + y * TILE_WIDTH + x
                    dst_x = tile_x * TILE_WIDTH + x
                    dst_y = tile_y * TILE_HEIGHT + y

                    if src_idx < len(pixels) and dst_y < height and dst_x < width:
                        img_pixels[dst_y * width + dst_x] = pixels[src_idx]
        return img_pixels

    def extract(
        self,
        vram_file: str,
        offset: int,
        size: int,
        tiles_per_row: int = 16,
    ) -> tuple[Image.Image, int]:
        """
        Extract sprites from VRAM dump.

        Args:
            vram_file: Path to VRAM dump file
            offset: Byte offset to start extraction
            size: Number of bytes to extract
            tiles_per_row: Number of tiles per row in output image

        Returns:
            Tuple of (PIL Image in indexed mode, total_tiles)

        Raises:
            RuntimeError: If extraction fails
        """
        try:
            with Path(vram_file).open("rb") as f:
                f.seek(offset)
                data = f.read(size)

            # Warn if short read occurred
            if len(data) < size:
                logger.warning(
                    f"Short read: requested {size} bytes but only read {len(data)} bytes. "
                    f"File may be shorter than expected or offset too large."
                )

            total_tiles, tiles_x, tiles_y, width, height = calculate_dimensions_from_tile_data(len(data), tiles_per_row)

            img = Image.new("P", (width, height))
            img.putpalette(get_grayscale_palette())

            pixels = self._decode_all_tiles(data)
            img_pixels = self._arrange_tiles_in_indexed_image(pixels, total_tiles, tiles_x, tiles_y, width, height)

            img.putdata(img_pixels)
            return img, total_tiles

        except ValueError:
            raise
        except (OSError, IndexError, MemoryError) as e:
            raise RuntimeError(f"Error extracting sprites: {e}") from e

    def _load_palettes_from_cgram(self, cgram_file: str) -> list[list[int]]:
        """Load all 16 palettes from CGRAM file or use grayscale fallback."""
        palettes: list[list[int]] = []

        cgram_path = Path(cgram_file) if cgram_file else None
        if cgram_path and not cgram_path.exists():
            logger.warning(f"CGRAM file not found: {cgram_file}, using grayscale")
            cgram_file = ""

        if cgram_file:
            for i in range(16):
                try:
                    pal = read_cgram_palette(cgram_file, i)
                    if pal and len(pal) >= 48:
                        palettes.append(pal)
                    else:
                        logger.warning(f"Invalid palette {i} in CGRAM, using grayscale")
                        palettes.append(get_grayscale_palette())
                except Exception as e:
                    logger.warning(f"Error reading palette {i}: {e}, using grayscale")
                    palettes.append(get_grayscale_palette())
        else:
            for _ in range(16):
                palettes.append(get_grayscale_palette())

        return palettes

    def _get_tile_palette_assignment(self, tile_offset: int) -> int:
        """Get palette assignment for a tile at given VRAM offset."""
        if self.oam_mapper:
            pal = self.oam_mapper.get_palette_for_vram_offset(tile_offset)
            if pal is not None:
                return pal
        return 0

    def _draw_tile_to_rgba_array(
        self,
        img_array: np.ndarray,
        tile_data: list[int],
        palette: list[int],
        tile_x: int,
        tile_y: int,
        width: int,
        height: int,
        clamped_pixels: list[int] | None = None,
    ) -> None:
        """Draw a single tile to RGBA numpy array using specified palette (vectorized)."""
        import numpy as np

        # Convert tile_data to numpy array for vectorized operations
        tile_array = np.array(tile_data, dtype=np.uint8).reshape((TILE_HEIGHT, TILE_WIDTH))

        # Check for out-of-range pixels
        if clamped_pixels is not None:
            invalid_mask = tile_array > 15
            if invalid_mask.any():
                invalid_values = tile_array[invalid_mask]
                clamped_pixels.extend(invalid_values.tolist())
                tile_array = np.clip(tile_array, 0, 15)

        # Create RGBA tile (8x8x4)
        tile_rgba = np.zeros((TILE_HEIGHT, TILE_WIDTH, 4), dtype=np.uint8)

        # Build palette lookup table (16 colors x 4 RGBA channels)
        palette_lut = np.zeros((16, 4), dtype=np.uint8)
        for i in range(16):
            palette_idx = i * 3
            if palette_idx + 2 < len(palette):
                palette_lut[i] = [palette[palette_idx], palette[palette_idx + 1], palette[palette_idx + 2], 255]
            else:
                gray = (i * 255) // 15
                palette_lut[i] = [gray, gray, gray, 255]

        # Vectorized palette lookup for all pixels
        tile_rgba[:, :] = palette_lut[tile_array]

        # Set transparent pixels (color_idx == 0) to alpha=0
        tile_rgba[tile_array == 0, 3] = 0

        # Calculate target region in image
        target_x = tile_x * TILE_WIDTH
        target_y = tile_y * TILE_HEIGHT

        # Ensure we don't write outside image bounds
        if target_x >= width or target_y >= height:
            return

        # Calculate actual region to copy (handle edge tiles)
        copy_width = min(TILE_WIDTH, width - target_x)
        copy_height = min(TILE_HEIGHT, height - target_y)

        # Copy tile data directly to image array (very fast)
        img_array[target_y : target_y + copy_height, target_x : target_x + copy_width] = tile_rgba[
            :copy_height, :copy_width
        ]

    def extract_with_correct_palettes(
        self,
        vram_file: str,
        offset: int,
        size: int,
        cgram_file: str,
        tiles_per_row: int = 16,
    ) -> tuple[Image.Image, int]:
        """
        Extract sprites with each tile using its OAM-assigned palette.
        Returns RGBA image where each tile is rendered with its correct palette.
        """
        try:
            import numpy as np

            with Path(vram_file).open("rb") as f:
                f.seek(offset)
                data = f.read(size)

            total_tiles, tiles_x, _, width, height = calculate_dimensions_from_tile_data(len(data), tiles_per_row)

            # Create numpy array for image (much faster than PIL putpixel)
            img_array = np.zeros((height, width, 4), dtype=np.uint8)

            palettes = self._load_palettes_from_cgram(cgram_file)
            clamped_pixels: list[int] = []

            for tile_idx in range(total_tiles):
                if tile_idx * BYTES_PER_TILE_4BPP + BYTES_PER_TILE_4BPP <= len(data):
                    tile_data = decode_4bpp_tile(data, tile_idx * BYTES_PER_TILE_4BPP)

                    tile_offset = offset + (tile_idx * BYTES_PER_TILE_4BPP)
                    assigned_palette = self._get_tile_palette_assignment(tile_offset)

                    palette = palettes[assigned_palette] if assigned_palette < len(palettes) else palettes[0]

                    tile_x = tile_idx % tiles_x
                    tile_y = tile_idx // tiles_x

                    self._draw_tile_to_rgba_array(
                        img_array, tile_data, palette, tile_x, tile_y, width, height, clamped_pixels
                    )

            if clamped_pixels:
                unique_clamped = set(clamped_pixels)
                logger.warning(
                    f"{len(clamped_pixels)} pixel(s) had color index > 15 "
                    f"(values: {sorted(unique_clamped)}) and were clamped."
                )

            # Convert numpy array to PIL Image once at the end (very fast)
            img = Image.fromarray(img_array, mode="RGBA")
            return img, total_tiles

        except (OSError, IndexError) as e:
            raise RuntimeError(f"Error extracting sprites with correct palettes: {e}") from e

    def extract_multi_palette(
        self,
        vram_file: str,
        offset: int,
        size: int,
        cgram_file: str,
        tiles_per_row: int = 16,
    ) -> tuple[dict[str, Image.Image], int]:
        """
        Extract sprites with multiple palette previews based on OAM data.
        Returns dictionary of palette_name -> image.
        """
        try:
            base_img, total_tiles = self.extract(vram_file, offset, size, tiles_per_row)
            palette_images: dict[str, Image.Image] = {}

            cgram_path = Path(cgram_file) if cgram_file else None
            if self.oam_mapper and cgram_path and cgram_path.exists():
                try:
                    oam_correct_img, _ = self.extract_with_correct_palettes(
                        vram_file, offset, size, cgram_file, tiles_per_row
                    )
                    palette_images["oam_correct"] = oam_correct_img
                except Exception as e:
                    logger.warning(f"Could not create OAM-correct image: {e}")

            if self.oam_mapper:
                active_palettes = self.oam_mapper.get_active_palettes()
                if not active_palettes:
                    active_palettes = list(range(8))
            else:
                return {"palette_0": base_img}, total_tiles

            cgram_path_check = Path(cgram_file) if cgram_file else None
            for pal_num in active_palettes:
                # OAM palette numbers (0-7) map to CGRAM sprite palettes (8-15)
                cgram_palette_num = pal_num + 8 if pal_num < 8 else pal_num
                cgram_palette_num = max(8, min(15, cgram_palette_num))
                img = base_img.copy()

                if cgram_path_check and cgram_path_check.exists():
                    palette = read_cgram_palette(cgram_file, cgram_palette_num)
                    if palette:
                        img.putpalette(palette)
                else:
                    img.putpalette(get_grayscale_palette())

                # Use original OAM palette number in dict key for consistency
                palette_images[f"palette_{pal_num}"] = img

            return palette_images, total_tiles

        except (OSError, RuntimeError) as e:
            raise RuntimeError(f"Error extracting multi-palette sprites: {e}") from e
