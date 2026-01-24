"""
Palette utilities for SNES sprite color conversion and quantization.

Provides functions to:
- Convert SNES BGR555 palette data to RGB tuples
- Quantize RGBA images to fixed 16-color indexed palettes using perceptual color matching
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from utils.logging_config import get_logger

logger = get_logger(__name__)


def _rgb_array_to_lab(rgb: NDArray[np.int32]) -> NDArray[np.float64]:
    """Convert RGB array to CIELAB color space (vectorized).

    Args:
        rgb: Array of shape (..., 3) with RGB values 0-255

    Returns:
        Array of shape (..., 3) with LAB values
    """
    # Normalize to 0-1
    rgb_norm = rgb.astype(np.float64) / 255.0

    # sRGB to linear RGB (vectorized)
    def srgb_to_linear(c: NDArray[np.float64]) -> NDArray[np.float64]:
        mask = c <= 0.04045
        result = np.empty_like(c)
        result[mask] = c[mask] / 12.92
        result[~mask] = ((c[~mask] + 0.055) / 1.055) ** 2.4
        return result

    r_lin = srgb_to_linear(rgb_norm[..., 0])
    g_lin = srgb_to_linear(rgb_norm[..., 1])
    b_lin = srgb_to_linear(rgb_norm[..., 2])

    # Linear RGB to XYZ (D65 illuminant)
    x = r_lin * 0.4124564 + g_lin * 0.3575761 + b_lin * 0.1804375
    y = r_lin * 0.2126729 + g_lin * 0.7151522 + b_lin * 0.0721750
    z = r_lin * 0.0193339 + g_lin * 0.1191920 + b_lin * 0.9503041

    # Reference white D65
    x_n = x / 0.95047
    y_n = y / 1.00000
    z_n = z / 1.08883

    # XYZ to LAB
    delta = 6.0 / 29.0

    def f(t: NDArray[np.float64]) -> NDArray[np.float64]:
        mask = t > delta**3
        result = np.empty_like(t)
        result[mask] = t[mask] ** (1.0 / 3.0)
        result[~mask] = t[~mask] / (3.0 * delta**2) + 4.0 / 29.0
        return result

    f_x = f(x_n)
    f_y = f(y_n)
    f_z = f(z_n)

    L = 116.0 * f_y - 16.0
    a = 500.0 * (f_x - f_y)
    b_val = 200.0 * (f_y - f_z)

    return np.stack([L, a, b_val], axis=-1)


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

    Uses nearest-color matching with perceptual distance (CIELAB color space).
    This provides better results for human perception than RGB Euclidean distance,
    preserving important details like eye whites and small highlights.

    Transparent pixels (alpha < threshold) map to index 0.
    Opaque pixels never map to index 0 (reserved for transparency).

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

    # Build pixel RGB array and convert to LAB for perceptual distance
    pixel_rgb = np.stack([r, g, b], axis=-1)  # Shape: (H, W, 3)
    pixel_lab = _rgb_array_to_lab(pixel_rgb)  # Shape: (H, W, 3)

    # Convert palette to LAB
    palette_arr = np.array(palette_rgb, dtype=np.int32)  # Shape: (16, 3)
    palette_lab = _rgb_array_to_lab(palette_arr)  # Shape: (16, 3)

    # Calculate squared distances in LAB space (perceptual distance)
    # Reshape for broadcasting: pixels (H, W, 1, 3) vs palette (1, 1, 16, 3)
    pixel_lab_broadcast = pixel_lab[:, :, np.newaxis, :]  # Shape: (H, W, 1, 3)
    palette_lab_broadcast = palette_lab[np.newaxis, np.newaxis, :, :]  # Shape: (1, 1, 16, 3)

    # Squared perceptual distance (Delta E squared)
    distances = np.sum((pixel_lab_broadcast - palette_lab_broadcast) ** 2, axis=-1)  # Shape: (H, W, 16)

    # For opaque pixels: exclude index 0 from consideration
    # Index 0 is reserved for transparency in SNES sprites
    # Set distance to index 0 to infinity for opaque pixels so argmin picks index 1+
    opaque_mask = ~transparent_mask
    distances[opaque_mask, 0] = np.inf

    # Find nearest color for each pixel
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
        "Quantized %dx%d image to %d-color palette (perceptual LAB distance, transparent pixels: %d)",
        width,
        height,
        len(palette_rgb),
        int(np.sum(transparent_mask)),
    )

    return indexed_img


def quantize_with_mappings(
    img: Image.Image,
    palette_rgb: list[tuple[int, int, int]],
    color_mappings: dict[tuple[int, int, int], int],
    transparency_threshold: int = 1,
) -> Image.Image:
    """Quantize RGBA image using explicit color mappings with perceptual fallback.

    User-defined mappings are applied first. Any colors not in the mapping
    fall back to nearest-color matching using perceptual distance (CIELAB space).
    Transparent pixels (alpha < threshold) always map to index 0.
    Opaque pixels never map to index 0 in fallback (reserved for transparency).

    Args:
        img: PIL Image in RGBA mode
        palette_rgb: List of 16 RGB tuples defining the target palette
        color_mappings: Dict mapping RGB tuples to palette indices (user-defined)
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

    # Build pixel RGB array and convert to LAB for perceptual distance
    pixel_rgb = np.stack([r, g, b], axis=-1)  # Shape: (H, W, 3)
    pixel_lab = _rgb_array_to_lab(pixel_rgb)  # Shape: (H, W, 3)

    # Convert palette to LAB
    palette_arr = np.array(palette_rgb, dtype=np.int32)  # Shape: (16, 3)
    palette_lab = _rgb_array_to_lab(palette_arr)  # Shape: (16, 3)

    # Calculate squared distances in LAB space for nearest-color fallback
    pixel_lab_broadcast = pixel_lab[:, :, np.newaxis, :]  # Shape: (H, W, 1, 3)
    palette_lab_broadcast = palette_lab[np.newaxis, np.newaxis, :, :]  # Shape: (1, 1, 16, 3)

    # Squared perceptual distance (Delta E squared)
    distances = np.sum((pixel_lab_broadcast - palette_lab_broadcast) ** 2, axis=-1)  # Shape: (H, W, 16)

    # For opaque pixels: exclude index 0 from consideration in fallback
    # Index 0 is reserved for transparency in SNES sprites
    opaque_mask = ~transparent_mask
    distances[opaque_mask, 0] = np.inf

    # Find nearest color for each pixel (fallback)
    indices = np.argmin(distances, axis=-1).astype(np.uint8)  # Shape: (H, W)

    # Apply explicit color mappings (override nearest-color for mapped colors)
    mapped_count = 0
    for rgb_color, palette_idx in color_mappings.items():
        # Find pixels matching this exact RGB color
        mask = (r == rgb_color[0]) & (g == rgb_color[1]) & (b == rgb_color[2])
        if np.any(mask):
            indices[mask] = palette_idx
            mapped_count += int(np.sum(mask))

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
        "Quantized %dx%d with mappings (perceptual LAB): %d explicit mappings, %d pixels mapped",
        width,
        height,
        len(color_mappings),
        mapped_count,
    )

    return indexed_img
