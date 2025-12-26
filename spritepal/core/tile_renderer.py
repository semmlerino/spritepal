"""
Tile renderer for converting 4bpp SNES tile data to images.
"""

from __future__ import annotations

from PIL import Image

from core.default_palette_loader import DefaultPaletteLoader
from core.tile_utils import decode_4bpp_tile
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
            self.default_palettes = {8: [[i * 16, i * 16, i * 16] for i in range(16)]}

    def render_tiles(
        self, tile_data: bytes, width_tiles: int, height_tiles: int, palette_index: int | None = None
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
        logger.debug(
            f"render_tiles called: data_len={len(tile_data)}, dims={width_tiles}x{height_tiles}, palette={palette_index}"
        )
        try:
            # Validate input
            bytes_per_tile = 32
            expected_size = width_tiles * height_tiles * bytes_per_tile

            if len(tile_data) < expected_size:
                # Pad with zeros if needed
                tile_data = tile_data + b"\x00" * (expected_size - len(tile_data))
                logger.debug(
                    f"Padded tile data from {len(tile_data) - (expected_size - len(tile_data))} to {expected_size} bytes"
                )

            # Get palette
            if palette_index is None:
                # Use grayscale palette when None is specified
                palette = [[i * 17, i * 17, i * 17] for i in range(16)]  # 0-255 range
                logger.debug("Using grayscale palette (palette_index=None)")
            elif palette_index not in self.default_palettes:
                logger.warning(
                    f"Palette index {palette_index} not found in loaded palettes "
                    f"(available: {sorted(self.default_palettes.keys())}). "
                    "Using grayscale fallback - sprite colors may be incorrect."
                )
                palette = [[i * 17, i * 17, i * 17] for i in range(16)]  # Grayscale fallback
            else:
                # Get the specified palette
                palette = self.default_palettes[palette_index]
                logger.debug(f"Using palette index {palette_index}")

            logger.debug(f"Using palette {palette_index} with {len(palette)} colors")

            # Create output image
            width_pixels = width_tiles * 8
            height_pixels = height_tiles * 8
            image = Image.new("RGBA", (width_pixels, height_pixels), (0, 0, 0, 0))
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
                    tile_pixels = decode_4bpp_tile(tile_data[tile_offset : tile_offset + bytes_per_tile])

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
