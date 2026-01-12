#!/usr/bin/env python3
"""
Image conversion service.
Handles PNG to SNES tile data conversion and validation.
"""

import logging
from collections.abc import Iterable
from typing import cast

from PIL import Image

from ..constants import (
    PIXEL_4BPP_MASK,
    TILE_HEIGHT,
    TILE_WIDTH,
)
from ..core.tile_utils import calculate_tile_grid_padded, encode_4bpp_tile

logger = logging.getLogger(__name__)


class ImageConverter:
    """Service for PNG to SNES tile conversion."""

    def _extract_tile_from_image(
        self,
        pixels: list[int],
        tile_x: int,
        tile_y: int,
        img_width: int,
        padded_count: list[int] | None = None,
    ) -> list[int]:
        """
        Extract an 8x8 tile from image pixel data.

        Args:
            pixels: Flat list of pixel indices
            tile_x: Tile X coordinate in grid
            tile_y: Tile Y coordinate in grid
            img_width: Image width in pixels
            padded_count: Optional list to track padded pixels [count]

        Returns:
            List of 64 pixel values for the tile
        """
        tile_pixels: list[int] = []
        for y in range(TILE_HEIGHT):
            for x in range(TILE_WIDTH):
                pixel_x = tile_x * TILE_WIDTH + x
                pixel_y = tile_y * TILE_HEIGHT + y
                pixel_index = pixel_y * img_width + pixel_x

                if pixel_index < len(pixels):
                    tile_pixels.append(pixels[pixel_index] & PIXEL_4BPP_MASK)
                else:
                    tile_pixels.append(0)
                    if padded_count is not None:
                        padded_count[0] += 1
        return tile_pixels

    def png_to_tiles(self, png_file: str) -> tuple[bytes, int]:
        """
        Convert PNG to SNES 4bpp tile data.

        Args:
            png_file: Path to PNG file (must be indexed color mode)

        Returns:
            Tuple of (tile_data_bytes, total_tiles)

        Raises:
            ValueError: If image is not in indexed color mode
            RuntimeError: If file operations fail
        """
        try:
            with Image.open(png_file) as img:
                if img.mode != "P":
                    raise ValueError(f"Image must be in indexed color mode (current: {img.mode})")

                width, height = img.size
                tiles_x, tiles_y, total_tiles = calculate_tile_grid_padded(width, height)

                pixels = list(cast(Iterable[int], img.getdata()))

            output_data = bytearray()
            padded_count = [0]

            for tile_y_idx in range(tiles_y):
                for tile_x_idx in range(tiles_x):
                    tile_pixels = self._extract_tile_from_image(pixels, tile_x_idx, tile_y_idx, width, padded_count)
                    tile_data = encode_4bpp_tile(tile_pixels)
                    output_data.extend(tile_data)

            if padded_count[0] > 0:
                logger.warning(
                    f"{padded_count[0]} pixel(s) were out of bounds and "
                    f"padded with transparent (0). Image may not be tile-aligned."
                )

            return bytes(output_data), total_tiles

        except ValueError:
            raise
        except (OSError, AttributeError) as e:
            raise RuntimeError(f"Error converting PNG: {e}") from e

    def image_to_tiles(self, img: Image.Image) -> bytes:
        """
        Convert an in-memory indexed image to SNES 4bpp tile data.

        Args:
            img: PIL Image in indexed (P) mode.

        Returns:
            Tile data bytes.
        """
        if img.mode != "P":
            raise ValueError(f"Image must be in indexed color mode (current: {img.mode})")

        width, height = img.size
        tiles_x, tiles_y, _ = calculate_tile_grid_padded(width, height)
        pixels = list(cast(Iterable[int], img.getdata()))

        output_data = bytearray()
        padded_count = [0]

        for tile_y_idx in range(tiles_y):
            for tile_x_idx in range(tiles_x):
                tile_pixels = self._extract_tile_from_image(pixels, tile_x_idx, tile_y_idx, width, padded_count)
                tile_data = encode_4bpp_tile(tile_pixels)
                output_data.extend(tile_data)

        if padded_count[0] > 0:
            logger.warning(
                f"{padded_count[0]} pixel(s) were out of bounds and "
                "padded with transparent (0). Image may not be tile-aligned."
            )

        return bytes(output_data)

    def validate_png(self, png_file: str) -> tuple[bool, list[str]]:
        """
        Validate PNG file is suitable for SNES conversion.

        Args:
            png_file: Path to PNG file

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        try:
            with Image.open(png_file) as img:
                issues: list[str] = []

                if img.mode != "P":
                    issues.append(f"Image is in {img.mode} mode, must be indexed (P) mode")

                width, height = img.size
                if width % TILE_WIDTH != 0:
                    issues.append(f"Width ({width}) must be multiple of {TILE_WIDTH}")
                if height % TILE_HEIGHT != 0:
                    issues.append(f"Height ({height}) must be multiple of {TILE_HEIGHT}")

                if img.mode == "P":
                    pixels = list(cast(Iterable[int], img.getdata()))
                    colors_used = len(set(pixels))
                    if colors_used > 16:
                        issues.append(f"Too many colors ({colors_used}), maximum is 16")
                    if pixels:
                        max_index = max(pixels)
                        if max_index > 15:
                            issues.append(f"Palette index {max_index} exceeds 4bpp limit (15)")
                elif img.mode in ("RGB", "RGBA", "L", "LA"):
                    colors_used = len(set(cast(Iterable[object], img.getdata())))
                    if colors_used > 16:
                        issues.append(
                            f"Too many unique colors ({colors_used}), maximum is 16 for SNES 4bpp. "
                            f"Convert to indexed (P) mode first."
                        )

                return len(issues) == 0, issues

        except ValueError:
            raise
        except (OSError, AttributeError, RuntimeError) as e:
            return False, [str(e)]
