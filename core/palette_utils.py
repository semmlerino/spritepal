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

# === Shared Quantization Constants ===
# These ensure preview and injection use identical behavior for WYSIWYG.

# SNES sprites use exactly 16 colors per palette (4-bit indexed)
SNES_PALETTE_SIZE = 16

# Transparency threshold for quantization - pixels with alpha below this become index 0.
# Value 128 treats semi-transparent pixels (alpha 1-127) as transparent, which is correct
# for AI-generated images with anti-aliased edges. Both preview and injection must use
# this same value to ensure WYSIWYG behavior.
QUANTIZATION_TRANSPARENCY_THRESHOLD = 128

# Just Noticeable Difference (JND) threshold for stable tie-breaking in quantization.
# LAB JND is ~2.3. When distances differ by less than JND² (~5.29), colors are
# perceptually equivalent → pick lowest palette index for consistency.
# This prevents symmetric pixels with near-identical RGB values from mapping to
# different palette entries due to floating-point decision boundary effects.
JND_THRESHOLD_SQ = 5.29

# Cache for palette LAB conversions. Key: tuple of RGB tuples, Value: LAB numpy array.
# Palettes are typically reused many times during preview updates and interactive editing.
# Cache size is naturally limited since only a few palettes are used per session.
_palette_lab_cache: dict[tuple[tuple[int, int, int], ...], NDArray[np.float64]] = {}

# Maximum cache entries (each ~384 bytes for 16-color palette LAB data)
_PALETTE_CACHE_MAX_SIZE = 32


def _get_cached_palette_lab(
    palette_rgb: list[tuple[int, int, int]],
) -> NDArray[np.float64]:
    """Get LAB representation of palette, using cache when available.

    Args:
        palette_rgb: List of RGB tuples (typically 16 colors)

    Returns:
        LAB array of shape (N, 3) where N is number of palette colors
    """
    cache_key = tuple(palette_rgb)

    if cache_key in _palette_lab_cache:
        return _palette_lab_cache[cache_key]

    # Compute LAB conversion
    palette_arr = np.array(palette_rgb, dtype=np.int32)
    palette_lab = _rgb_array_to_lab(palette_arr)

    # Add to cache (with simple LRU-like eviction)
    if len(_palette_lab_cache) >= _PALETTE_CACHE_MAX_SIZE:
        # Remove oldest entry (first key in dict order, Python 3.7+)
        oldest_key = next(iter(_palette_lab_cache))
        del _palette_lab_cache[oldest_key]

    _palette_lab_cache[cache_key] = palette_lab
    return palette_lab


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


def _stable_argmin(
    distances: NDArray[np.float64],
    jnd_sq: float = JND_THRESHOLD_SQ,
) -> NDArray[np.uint8]:
    """Select palette indices with stable tie-breaking for near-equal distances.

    When multiple palette colors are within JND of the minimum distance,
    consistently picks the lowest index. This ensures symmetric pixels with
    nearly-identical colors map to the same palette entry, preventing
    asymmetric visual artifacts during quantization.

    Args:
        distances: Array of shape (H, W, 16) with squared distances to each palette color
        jnd_sq: Squared JND threshold for treating distances as equivalent

    Returns:
        Array of shape (H, W) with palette indices (uint8)
    """
    min_dist = np.min(distances, axis=-1, keepdims=True)
    candidates = distances <= (min_dist + jnd_sq)
    # Create index array that broadcasts to (H, W, 16)
    index_array = np.arange(16, dtype=np.uint8).reshape(1, 1, 16)
    # For non-candidates, use 255 (max uint8) so argmin picks from candidates
    candidate_indices = np.where(candidates, index_array, np.uint8(255))
    return np.argmin(candidate_indices, axis=-1).astype(np.uint8)


def bgr555_to_rgb(bgr555: int) -> tuple[int, int, int]:
    """Convert single SNES BGR555 color to RGB888 with full 8-bit scaling.

    SNES uses 15-bit color (5 bits per channel, 0-31 range). To convert to
    8-bit (0-255 range), we use: (value << 3) | (value >> 2)

    This properly scales 31 (max 5-bit) to 255 (max 8-bit):
        31 << 3 = 248
        31 >> 2 = 7
        248 | 7 = 255

    Simply shifting left by 3 only produces 248, which causes slightly muted colors.

    Args:
        bgr555: SNES BGR555 format color (0bbbbbgggggrrrrr)

    Returns:
        RGB tuple with full 8-bit range (0-255)
    """
    # Extract 5-bit components
    r5 = bgr555 & 0x001F
    g5 = (bgr555 >> 5) & 0x001F
    b5 = (bgr555 >> 10) & 0x001F

    # Scale from 5-bit to 8-bit using proper formula
    r = (r5 << 3) | (r5 >> 2)
    g = (g5 << 3) | (g5 >> 2)
    b = (b5 << 3) | (b5 >> 2)

    return (r, g, b)


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
            # Convert BGR555 to RGB888 using shared utility
            result.append(bgr555_to_rgb(color))
    return result


def quantize_to_palette(
    img: Image.Image,
    palette_rgb: list[tuple[int, int, int]],
    transparency_threshold: int = QUANTIZATION_TRANSPARENCY_THRESHOLD,
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

    # Convert palette to LAB (cached for performance - same palette reused across updates)
    palette_lab = _get_cached_palette_lab(palette_rgb)  # Shape: (16, 3)

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

    # Find nearest color for each pixel using stable tie-breaking
    # This ensures symmetric pixels with near-identical colors map consistently
    indices = _stable_argmin(distances)  # Shape: (H, W)

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
    transparency_threshold: int = QUANTIZATION_TRANSPARENCY_THRESHOLD,
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

    # Convert palette to LAB (cached for performance - same palette reused across updates)
    palette_lab = _get_cached_palette_lab(palette_rgb)  # Shape: (16, 3)

    # Calculate squared distances in LAB space for nearest-color fallback
    pixel_lab_broadcast = pixel_lab[:, :, np.newaxis, :]  # Shape: (H, W, 1, 3)
    palette_lab_broadcast = palette_lab[np.newaxis, np.newaxis, :, :]  # Shape: (1, 1, 16, 3)

    # Squared perceptual distance (Delta E squared)
    distances = np.sum((pixel_lab_broadcast - palette_lab_broadcast) ** 2, axis=-1)  # Shape: (H, W, 16)

    # For opaque pixels: exclude index 0 from consideration in fallback
    # Index 0 is reserved for transparency in SNES sprites
    opaque_mask = ~transparent_mask
    distances[opaque_mask, 0] = np.inf

    # Find nearest color for each pixel (fallback) using stable tie-breaking
    # This ensures symmetric pixels with near-identical colors map consistently
    indices = _stable_argmin(distances)  # Shape: (H, W)

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


# === Helper Functions for Palette Operations ===
# Moved from ui/dialogs/color_mapping_dialog.py to centralize core logic.


def snap_to_snes_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Snap an RGB color to the nearest SNES-valid color.

    SNES uses BGR555 (5 bits per channel). Valid RGB888 values are those
    that round-trip correctly through 5-bit conversion using the formula:
    (c5 << 3) | (c5 >> 2)

    This produces values: 0, 8, 16, 24, 33, 41, ... 231, 239, 247, 255
    (NOT simple multiples of 8).

    Args:
        color: RGB tuple with 8-bit values (0-255)

    Returns:
        RGB tuple snapped to nearest SNES-valid values that round-trip correctly
    """

    def snap_component(val: int) -> int:
        # Round to nearest 5-bit value, clamped to valid range
        c5 = round(val / 8)
        c5 = max(0, min(31, c5))
        # Expand back to 8-bit using the standard SNES formula
        return (c5 << 3) | (c5 >> 2)

    return (snap_component(color[0]), snap_component(color[1]), snap_component(color[2]))


def find_nearest_palette_index(
    color: tuple[int, int, int],
    palette: list[tuple[int, int, int]],
    skip_zero: bool = True,
) -> int:
    """Find the palette index with the nearest color using perceptual distance.

    Uses CIELAB perceptual distance for better color matching.

    Args:
        color: RGB color tuple to match
        palette: List of RGB palette colors
        skip_zero: If True, skip index 0 (transparency) for opaque colors

    Returns:
        Index of nearest palette color
    """
    from utils.color_distance import perceptual_distance_sq

    min_dist = float("inf")
    best_idx = 1 if skip_zero else 0

    for idx, pal_color in enumerate(palette):
        if skip_zero and idx == 0:
            continue
        dist = perceptual_distance_sq(color, pal_color)
        if dist < min_dist:
            min_dist = dist
            best_idx = idx

    return best_idx


def extract_unique_colors(
    image: Image.Image,
    ignore_transparent: bool = True,
    alpha_threshold: int = QUANTIZATION_TRANSPARENCY_THRESHOLD,
) -> dict[tuple[int, int, int], int]:
    """Extract unique RGB colors from an image with their pixel counts.

    Args:
        image: PIL Image to analyze
        ignore_transparent: If True, skip pixels with alpha < threshold
        alpha_threshold: Alpha value below which pixels are considered transparent

    Returns:
        Dict mapping RGB tuples to pixel counts
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # Convert to numpy array for fast processing
    pixels = np.array(image)

    # Flatten to (N, 4) where N is total pixels
    flat_pixels = pixels.reshape(-1, 4)

    # Filter out transparent pixels if requested
    if ignore_transparent:
        opaque_mask = flat_pixels[:, 3] >= alpha_threshold
        flat_pixels = flat_pixels[opaque_mask]

    if len(flat_pixels) == 0:
        return {}

    # Get RGB only (drop alpha)
    rgb_pixels = flat_pixels[:, :3]

    # Use numpy unique to count colors efficiently
    # Pack RGB into single integers for fast comparison
    packed = (
        rgb_pixels[:, 0].astype(np.uint32) << 16
        | rgb_pixels[:, 1].astype(np.uint32) << 8
        | rgb_pixels[:, 2].astype(np.uint32)
    )
    unique_packed, counts = np.unique(packed, return_counts=True)

    # Unpack back to RGB tuples
    color_counts: dict[tuple[int, int, int], int] = {}
    for packed_color, count in zip(unique_packed, counts, strict=False):
        r = int((packed_color >> 16) & 0xFF)
        g = int((packed_color >> 8) & 0xFF)
        b = int(packed_color & 0xFF)
        color_counts[(r, g, b)] = int(count)

    return color_counts


def quantize_colors_to_palette(
    color_counts: dict[tuple[int, int, int], int],
    max_colors: int = SNES_PALETTE_SIZE,
    *,
    snap_to_snes: bool = True,
) -> list[tuple[int, int, int]]:
    """Quantize colors to a limited palette.

    Uses PIL's median-cut quantization to reduce colors.
    Index 0 is reserved for transparency (black).

    Args:
        color_counts: Dict mapping RGB tuples to pixel counts
        max_colors: Maximum colors in output palette (default 16 for SNES)
        snap_to_snes: If True, snap colors to SNES-valid values (multiples of 8)

    Returns:
        List of RGB tuples (max_colors entries, index 0 = transparency)
    """
    if not color_counts:
        # Return empty palette with black at index 0
        return [(0, 0, 0)] * max_colors

    # Optionally snap input colors to SNES-valid values first
    # This merges similar colors that would map to the same SNES color
    if snap_to_snes:
        snapped_counts: dict[tuple[int, int, int], int] = {}
        for color, count in color_counts.items():
            snapped = snap_to_snes_color(color)
            snapped_counts[snapped] = snapped_counts.get(snapped, 0) + count
        color_counts = snapped_counts

    # Sort colors by frequency
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)

    # If we have few enough colors, use them directly
    if len(sorted_colors) <= max_colors - 1:  # -1 for transparency
        palette: list[tuple[int, int, int]] = [(0, 0, 0)]  # Index 0 = transparent/black
        for color, _count in sorted_colors:
            palette.append(color)
        # Pad with black if needed
        while len(palette) < max_colors:
            palette.append((0, 0, 0))
        return palette

    # Create a small image with all colors weighted by frequency
    # This gives better quantization results
    total_pixels = sum(color_counts.values())
    img_size = min(256, max(16, int(total_pixels**0.5)))  # Reasonable size

    # Build image data
    pixel_data: list[tuple[int, int, int]] = []
    for color, count in sorted_colors:
        # Add each color proportionally to its frequency
        weight = max(1, int(count * img_size * img_size / total_pixels))
        pixel_data.extend([color] * weight)

    # Ensure we have enough pixels
    while len(pixel_data) < img_size * img_size:
        pixel_data.append(sorted_colors[0][0])  # Pad with most common color

    # Create image and quantize
    img = Image.new("RGB", (img_size, img_size))
    img.putdata(pixel_data[: img_size * img_size])

    # Quantize to max_colors - 1 (reserve index 0 for transparency)
    quantized = img.quantize(colors=max_colors - 1, method=Image.Quantize.MEDIANCUT)
    raw_palette = quantized.getpalette()

    if raw_palette is None:
        # Fallback: use most frequent colors (already snapped if snap_to_snes)
        palette = [(0, 0, 0)]
        for color, _count in sorted_colors[: max_colors - 1]:
            palette.append(color)
        while len(palette) < max_colors:
            palette.append((0, 0, 0))
        return palette

    # Extract palette colors from quantization result
    palette = [(0, 0, 0)]  # Index 0 = transparent
    for i in range(max_colors - 1):
        r = raw_palette[i * 3]
        g = raw_palette[i * 3 + 1]
        b = raw_palette[i * 3 + 2]
        color = (r, g, b)
        # Snap quantized colors to SNES-valid values
        if snap_to_snes:
            color = snap_to_snes_color(color)
        palette.append(color)

    return palette
