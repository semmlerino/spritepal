"""
PNG to SNES 4bpp tile data conversion service.

This module consolidates PNG→4bpp conversion logic that was previously duplicated in:
- core/injector.py (SpriteInjector.convert_png_to_4bpp)
- ui/sprite_editor/services/image_converter.py (ImageConverter.png_to_tiles)

Key decisions:
- Strict mode (default): Only accepts indexed PNG (mode "P") with indices 0-15
- Permissive mode: Also accepts grayscale ("L") and converts RGB/RGBA to grayscale
- Explicit padding: Pre-pads image to tile-aligned size before conversion
- Validation: Raises ValueError if palette indices exceed 15 (no silent masking)

Usage:
    from core.services.png_conversion import convert_png_to_4bpp

    # Strict mode (indexed PNG only)
    tile_data, tile_count = convert_png_to_4bpp("sprite.png")

    # Permissive mode (also accepts grayscale)
    tile_data, tile_count = convert_png_to_4bpp("sprite.png", mode_policy="permissive")
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

from core.tile_utils import encode_4bpp_tile
from utils.constants import TILE_HEIGHT, TILE_WIDTH
from utils.logging_config import get_logger

logger = get_logger(__name__)

# 4-bit pixel mask
PIXEL_MASK_4BIT = 0x0F


def convert_png_to_4bpp(
    source: str | Path | Image.Image,
    *,
    mode_policy: Literal["strict", "permissive"] = "strict",
) -> tuple[bytes, int]:
    """Convert PNG to SNES 4bpp tile data.

    Args:
        source: Path to PNG file or PIL Image object
        mode_policy: "strict" requires indexed color mode (P) with indices 0-15;
                    "permissive" also accepts grayscale (L) and converts RGB/RGBA

    Returns:
        Tuple of (tile_data_bytes, tile_count)

    Raises:
        ValueError: If image mode is incompatible with mode_policy, or if
                   palette indices exceed 15 in strict mode
        RuntimeError: If file operations fail
        FileNotFoundError: If source file doesn't exist
    """
    try:
        # Handle both path and Image inputs
        if isinstance(source, Image.Image):
            img = source
            should_close = False
            source_name = "<Image>"
        else:
            source_path = Path(source)
            if not source_path.exists():
                raise FileNotFoundError(f"PNG file not found: {source}")
            img = Image.open(source_path)
            should_close = True
            source_name = str(source)

        try:
            return _convert_image_to_4bpp(img, mode_policy, source_name)
        finally:
            if should_close:
                img.close()

    except (ValueError, FileNotFoundError):
        raise
    except (OSError, AttributeError) as e:
        raise RuntimeError(f"Error converting PNG: {e}") from e


def _convert_image_to_4bpp(
    img: Image.Image,
    mode_policy: Literal["strict", "permissive"],
    source_name: str,
) -> tuple[bytes, int]:
    """Internal conversion logic."""
    width, height = img.size
    logger.info(f"Converting PNG to 4bpp: {source_name} ({width}x{height}, mode={img.mode})")

    # Get pixel array based on mode policy
    pixels = _get_pixel_array(img, mode_policy)

    # Pre-pad to tile-aligned dimensions
    padded_width = ((width + 7) // 8) * 8
    padded_height = ((height + 7) // 8) * 8

    if width != padded_width or height != padded_height:
        logger.info(f"Padding image from {width}x{height} to {padded_width}x{padded_height}")
        # Create padded array with zeros (transparent)
        padded_pixels = np.zeros((padded_height, padded_width), dtype=np.uint8)
        padded_pixels[:height, :width] = pixels.reshape(height, width)
        pixels = padded_pixels
        width, height = padded_width, padded_height
    else:
        pixels = pixels.reshape(height, width)

    # Calculate tile grid
    tiles_x = width // TILE_WIDTH
    tiles_y = height // TILE_HEIGHT
    total_tiles = tiles_x * tiles_y
    logger.debug(f"Processing {total_tiles} tiles ({tiles_x}x{tiles_y})")

    # Mask to 4-bit values (safety measure, validation already done)
    pixels = pixels & PIXEL_MASK_4BIT

    # Reshape to extract tiles efficiently using NumPy
    # From (height, width) to (tiles_y, TILE_HEIGHT, tiles_x, TILE_WIDTH)
    # Then transpose to (tiles_y, tiles_x, TILE_HEIGHT, TILE_WIDTH)
    tiles = pixels.reshape(tiles_y, TILE_HEIGHT, tiles_x, TILE_WIDTH)
    tiles = tiles.transpose(0, 2, 1, 3)  # Shape: (tiles_y, tiles_x, 8, 8)

    # Flatten to (total_tiles, 64) for processing
    tiles = tiles.reshape(total_tiles, 64)

    # Process all tiles
    output_data = bytearray(total_tiles * 32)
    for i in range(total_tiles):
        tile_data = encode_4bpp_tile(tiles[i])
        output_data[i * 32 : (i + 1) * 32] = tile_data

    logger.info(f"Converted {total_tiles} tiles to {len(output_data)} bytes of 4bpp tile data")
    return bytes(output_data), total_tiles


def _get_pixel_array(
    img: Image.Image,
    mode_policy: Literal["strict", "permissive"],
) -> np.ndarray:
    """Extract pixel array from image based on mode policy.

    Returns:
        1D numpy array of pixel values (0-15)
    """
    if img.mode == "P":
        # Indexed mode - validate palette indices
        pixels = np.array(img, dtype=np.uint8)
        max_index = int(pixels.max()) if pixels.size > 0 else 0

        if max_index > 15:
            raise ValueError(
                f"PNG palette indices exceed 4bpp limit: max {max_index} (must be 0-15). "
                "Please use a PNG with 16 or fewer colors."
            )

        logger.debug(f"Using indexed palette: max index={max_index}")
        return pixels.flatten()

    elif img.mode == "L":
        # Grayscale mode
        if mode_policy == "strict":
            raise ValueError(
                "Image is in grayscale mode (L), but strict mode requires indexed color (P). "
                "Use mode_policy='permissive' to allow grayscale conversion."
            )

        pixels = np.array(img, dtype=np.uint8)
        # Map 0-255 to 0-15 (255 // 17 = 15)
        pixels = np.minimum(15, pixels // 17).astype(np.uint8)
        logger.debug(f"Converted grayscale to palette indices: max index={int(pixels.max())}")
        return pixels.flatten()

    else:
        # RGB, RGBA, or other modes
        if mode_policy == "strict":
            raise ValueError(
                f"Image is in {img.mode} mode, but strict mode requires indexed color (P). "
                "Use mode_policy='permissive' to allow conversion, or convert to indexed PNG first."
            )

        logger.warning(f"Converting {img.mode} to grayscale for palette index recovery")
        gray = img.convert("L")
        pixels = np.array(gray, dtype=np.uint8)
        # Map 0-255 to 0-15
        pixels = np.minimum(15, pixels // 17).astype(np.uint8)
        return pixels.flatten()
