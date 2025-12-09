"""
Tile renderer for converting 4bpp SNES tile data to images.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from core.default_palette_loader import DefaultPaletteLoader
from utils.logging_config import get_logger

logger = get_logger(__name__)

class TileRenderer:
    """Renders 4bpp SNES tile data to images."""

    def __init__(self):
        """Initialize the tile renderer."""
        self.palette_loader = DefaultPaletteLoader()
        # Get all Kirby palettes as a dictionary indexed by palette number
        self.default_palettes = self.palette_loader.get_all_kirby_palettes()
        # If no palettes found, create a default one
        if not self.default_palettes:
            logger.warning("No default palettes found, using grayscale")
            # Create a simple grayscale palette as fallback
            self.default_palettes = {
                8: [[i * 16, i * 16, i * 16] for i in range(16)]
            }

    def render_tiles(
        self,
        tile_data: bytes,
        width_tiles: int,
        height_tiles: int,
        palette_index: int | None = None
    ) -> Image.Image | None:
        """
        Render 4bpp tile data to an image.

        Args:
            tile_data: Raw 4bpp tile data (32 bytes per 8x8 tile)
            width_tiles: Width in tiles
            height_tiles: Height in tiles
            palette_index: Palette index to use (0-15) or None for grayscale

        Returns:
            PIL Image or None if rendering fails
        """
        logger.debug(f"render_tiles called: data_len={len(tile_data)}, dims={width_tiles}x{height_tiles}, palette={palette_index}")
        try:
            # Validate input
            bytes_per_tile = 32
            expected_size = width_tiles * height_tiles * bytes_per_tile

            if len(tile_data) < expected_size:
                # Pad with zeros if needed
                tile_data = tile_data + b'\x00' * (expected_size - len(tile_data))
                logger.debug(f"Padded tile data from {len(tile_data) - (expected_size - len(tile_data))} to {expected_size} bytes")

            # Get palette
            if palette_index is None:
                # Use grayscale palette when None is specified
                palette = [[i * 17, i * 17, i * 17] for i in range(16)]  # 0-255 range
                logger.debug("Using grayscale palette (palette_index=None)")
            elif palette_index not in self.default_palettes:
                logger.debug(f"Palette index {palette_index} not found, using grayscale")
                palette = [[i * 17, i * 17, i * 17] for i in range(16)]  # Grayscale fallback
            else:
                # Get the specified palette
                palette = self.default_palettes[palette_index]
                logger.debug(f"Using palette index {palette_index}")

            logger.debug(f"Using palette {palette_index} with {len(palette)} colors")

            # Create output image
            width_pixels = width_tiles * 8
            height_pixels = height_tiles * 8
            image = Image.new('RGBA', (width_pixels, height_pixels), (0, 0, 0, 0))
            pixels = image.load()

            # Check if pixels is None (can happen if image.load() fails)
            if pixels is None:
                raise ValueError("Failed to load image pixels")

            # Process each tile
            for tile_y in range(height_tiles):
                for tile_x in range(width_tiles):
                    tile_index = tile_y * width_tiles + tile_x
                    tile_offset = tile_index * bytes_per_tile

                    if tile_offset >= len(tile_data):
                        continue

                    # Decode the tile
                    tile_pixels = self._decode_4bpp_tile(
                        tile_data[tile_offset:tile_offset + bytes_per_tile]
                    )

                    # Apply palette and draw to image
                    for y in range(8):
                        for x in range(8):
                            color_index = tile_pixels[y][x]

                            # Color 0 is usually transparent
                            if color_index == 0:
                                color = (0, 0, 0, 0)
                            else:
                                rgb = palette[color_index]
                                color = (rgb[0], rgb[1], rgb[2], 255)

                            # Calculate pixel position
                            px = tile_x * 8 + x
                            py = tile_y * 8 + y

                            if px < width_pixels and py < height_pixels:
                                pixels[px, py] = color

            logger.debug(f"Successfully rendered image: {width_pixels}x{height_pixels} pixels")
            return image

        except Exception as e:
            logger.error(f"Failed to render tiles: {e}", exc_info=True)
            return None

    def _decode_4bpp_tile(self, tile_bytes: bytes) -> list[list[int]]:
        """
        Decode a single 4bpp SNES tile.

        Args:
            tile_bytes: 32 bytes of tile data

        Returns:
            8x8 array of color indices (0-15)
        """
        if len(tile_bytes) < 32:
            # Pad if needed
            tile_bytes = tile_bytes + b'\x00' * (32 - len(tile_bytes))

        # Initialize 8x8 pixel array
        pixels = [[0 for _ in range(8)] for _ in range(8)]

        # SNES 4bpp format:
        # 2 bytes for plane 0-1 of row 0
        # 2 bytes for plane 0-1 of row 1
        # ... (8 rows)
        # 2 bytes for plane 2-3 of row 0
        # 2 bytes for plane 2-3 of row 1
        # ... (8 rows)

        for row in range(8):
            # Get the 4 plane bytes for this row
            plane_01_offset = row * 2
            plane_23_offset = 16 + row * 2

            if plane_01_offset + 1 < len(tile_bytes):
                plane0 = tile_bytes[plane_01_offset]
                plane1 = tile_bytes[plane_01_offset + 1]
            else:
                plane0 = plane1 = 0

            if plane_23_offset + 1 < len(tile_bytes):
                plane2 = tile_bytes[plane_23_offset]
                plane3 = tile_bytes[plane_23_offset + 1]
            else:
                plane2 = plane3 = 0

            # Decode each pixel in the row
            for col in range(8):
                bit_mask = 1 << (7 - col)

                # Extract bit from each plane
                bit0 = 1 if (plane0 & bit_mask) else 0
                bit1 = 2 if (plane1 & bit_mask) else 0
                bit2 = 4 if (plane2 & bit_mask) else 0
                bit3 = 8 if (plane3 & bit_mask) else 0

                # Combine to get color index (0-15)
                color_index = bit0 | bit1 | bit2 | bit3
                pixels[row][col] = color_index

        return pixels

    def render_sprite_preview(
        self,
        sprite_data: bytes,
        palette_index: int = 8,
        max_width: int = 256,
        max_height: int = 256
    ) -> Image.Image | None:
        """
        Render a sprite preview with automatic layout.

        Args:
            sprite_data: Sprite tile data
            palette_index: Palette to use
            max_width: Maximum width in pixels
            max_height: Maximum height in pixels

        Returns:
            PIL Image or None
        """
        if not sprite_data:
            return None

        # Calculate tile count
        tile_count = len(sprite_data) // 32
        if tile_count == 0:
            return None

        # Calculate optimal layout
        max_width_tiles = max_width // 8
        max_height_tiles = max_height // 8

        # Try to make roughly square
        width_tiles = min(max_width_tiles, int(np.sqrt(tile_count)) + 1)
        height_tiles = min(max_height_tiles, (tile_count + width_tiles - 1) // width_tiles)

        # Adjust if we cut off too many tiles
        while width_tiles * height_tiles < tile_count and width_tiles < max_width_tiles:
            width_tiles += 1
            height_tiles = min(max_height_tiles, (tile_count + width_tiles - 1) // width_tiles)

        return self.render_tiles(sprite_data, width_tiles, height_tiles, palette_index)
