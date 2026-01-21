"""
Palette utilities for SNES sprite color conversion and quantization.

Provides functions to:
- Convert SNES BGR555 palette data to RGB tuples
- Quantize RGBA images to fixed 16-color indexed palettes using nearest-color matching
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from utils.logging_config import get_logger

logger = get_logger(__name__)


def snes_palette_to_rgb(snes_colors: list[int | list[int]]) -> list[tuple[int, int, int]]:
    """Convert SNES BGR555 palette to RGB tuples.

    Args:
        snes_colors: List of 16 colors, each either:
            - int: SNES BGR555 format (15-bit color)
            - list[int]: Already RGB triplet [r, g, b]

    Returns:
        List of 16 RGB tuples (r, g, b), each channel 0-255
    """
    result: list[tuple[int, int, int]] = []
    for color in snes_colors:
        if isinstance(color, list):
            # Already RGB triplet
            result.append((color[0], color[1], color[2]))
        else:
            # SNES BGR555 format: 0bbbbbgggggrrrrr
            r = (color & 0x1F) << 3
            g = ((color >> 5) & 0x1F) << 3
            b = ((color >> 10) & 0x1F) << 3
            result.append((r, g, b))
    return result


def quantize_to_palette(
    img: Image.Image,
    palette_rgb: list[tuple[int, int, int]],
    transparency_threshold: int = 1,
) -> Image.Image:
    """Quantize RGBA image to a fixed 16-color indexed palette.

    Uses nearest-color matching (Euclidean distance in RGB space).
    Transparent pixels (alpha < threshold) map to index 0.

    Args:
        img: PIL Image in RGBA mode
        palette_rgb: List of 16 RGB tuples defining the target palette
        transparency_threshold: Alpha values below this map to index 0

    Returns:
        PIL Image in mode "P" (indexed) with the specified palette
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Convert image to numpy array
    pixels = np.array(img, dtype=np.uint8)
    height, width = pixels.shape[:2]

    # Extract RGBA channels
    r = pixels[:, :, 0].astype(np.int32)
    g = pixels[:, :, 1].astype(np.int32)
    b = pixels[:, :, 2].astype(np.int32)
    alpha = pixels[:, :, 3]

    # Create transparency mask
    transparent_mask = alpha < transparency_threshold

    # Build palette as numpy array for vectorized distance calculation
    palette_arr = np.array(palette_rgb, dtype=np.int32)  # Shape: (16, 3)

    # Calculate squared distances to all palette colors
    # Reshape for broadcasting: pixels (H, W, 1, 3) vs palette (1, 1, 16, 3)
    pixel_rgb = np.stack([r, g, b], axis=-1)  # Shape: (H, W, 3)
    pixel_rgb = pixel_rgb[:, :, np.newaxis, :]  # Shape: (H, W, 1, 3)
    palette_broadcast = palette_arr[np.newaxis, np.newaxis, :, :]  # Shape: (1, 1, 16, 3)

    # Squared Euclidean distance (no need for sqrt since we only compare)
    distances = np.sum((pixel_rgb - palette_broadcast) ** 2, axis=-1)  # Shape: (H, W, 16)

    # Find nearest color for each pixel
    # Skip index 0 (transparency) for opaque pixels - find nearest among indices 1-15
    # For transparent pixels, we'll override to 0 anyway
    indices = np.argmin(distances, axis=-1).astype(np.uint8)  # Shape: (H, W)

    # Override transparent pixels to index 0
    indices[transparent_mask] = 0

    # Create indexed PIL image
    indexed_img = Image.fromarray(indices, mode="P")

    # Build palette for PIL (flat list of RGB values, padded to 256 colors)
    flat_palette: list[int] = []
    for rgb in palette_rgb:
        flat_palette.extend([rgb[0], rgb[1], rgb[2]])
    # Pad to 256 colors (PIL requirement for mode P)
    flat_palette.extend([0] * (768 - len(flat_palette)))

    indexed_img.putpalette(flat_palette)

    logger.debug(
        "Quantized %dx%d image to %d-color palette (transparent pixels: %d)",
        width,
        height,
        len(palette_rgb),
        int(np.sum(transparent_mask)),
    )

    return indexed_img
