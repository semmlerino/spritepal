"""
Palette utilities for SNES sprite color conversion and quantization.

Provides functions to:
- Convert SNES BGR555 palette data to RGB tuples
- Quantize RGBA images to fixed 16-color indexed palettes using perceptual color matching
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from utils.color_distance import detect_rare_important_colors, perceptual_distance_sq, rgb_to_lab
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

# Palette extraction tuning for grouping similar colors and preserving distinct ones.
PALETTE_CLUSTER_THRESHOLD_SQ = 49.0  # 7.0² LAB units
PALETTE_DIVERSITY_MIN_DISTANCE = 8.0  # Minimum LAB delta between palette colors

# Cache for palette LAB conversions. Key: tuple of RGB tuples, Value: LAB numpy array.
# Palettes are typically reused many times during preview updates and interactive editing.
# Cache size is naturally limited since only a few palettes are used per session.
_palette_lab_cache: dict[tuple[tuple[int, int, int], ...], NDArray[np.float64]] = {}

# Maximum cache entries (each ~384 bytes for 16-color palette LAB data)
_PALETTE_CACHE_MAX_SIZE = 32


# Standard 4x4 Bayer Dithering Matrix
# Values 0-15 representing threshold biases
_BAYER_MATRIX_4x4 = (
    np.array(
        [
            [0, 8, 2, 10],
            [12, 4, 14, 6],
            [3, 11, 1, 9],
            [15, 7, 13, 5],
        ],
        dtype=np.float32,
    )
    / 16.0
    - 0.5
)  # Normalize to -0.5 to +0.4375


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


def _apply_bayer_dither(
    pixel_lab: NDArray[np.float64],
    strength: float,
) -> NDArray[np.float64]:
    """Apply ordered Bayer dithering to LAB Lightness channel.

    Args:
        pixel_lab: Array of shape (H, W, 3) in LAB color space.
        strength: Dithering strength (0.0 to 1.0).

    Returns:
        Modified LAB array with dithering applied to L channel.
    """
    height, width = pixel_lab.shape[:2]

    # Tile the Bayer matrix to cover the image
    bayer_h, bayer_w = _BAYER_MATRIX_4x4.shape
    tiled_bayer = np.tile(
        _BAYER_MATRIX_4x4,
        (math.ceil(height / bayer_h), math.ceil(width / bayer_w)),
    )[:height, :width]

    # Apply dither to Lightness (L) channel (index 0)
    # Scale strength: at 1.0, range is roughly -8 to +7 L units (significant)
    # L ranges 0-100, so this is ~±8% lightness variation
    dither_amount = 16.0 * strength
    pixel_lab_dithered = pixel_lab.copy()
    pixel_lab_dithered[:, :, 0] += tiled_bayer * dither_amount

    return pixel_lab_dithered


def _quantize_impl(
    img: Image.Image,
    palette_rgb: list[tuple[int, int, int]],
    color_mappings: dict[tuple[int, int, int], int],
    transparency_threshold: int,
    dither_mode: str,
    dither_strength: float,
) -> NDArray[np.uint8]:
    """Common implementation for quantization with optional dithering.

    Args:
        img: RGBA Image.
        palette_rgb: List of palette colors.
        color_mappings: Explicit color mappings.
        transparency_threshold: Alpha threshold.
        dither_mode: "none" or "bayer".
        dither_strength: 0.0-1.0.

    Returns:
        numpy array (H, W) of uint8 palette indices.
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

    # Apply Dithering (only if mode is bayer and strength > 0)
    if dither_mode == "bayer" and dither_strength > 0.0:
        pixel_lab = _apply_bayer_dither(pixel_lab, dither_strength)

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
    # Note: Dithering affects nearest-color fallback, but explicit mappings override it.
    mapped_count = 0
    for rgb_color, palette_idx in color_mappings.items():
        # Find pixels matching this exact RGB color
        mask = (r == rgb_color[0]) & (g == rgb_color[1]) & (b == rgb_color[2])
        if np.any(mask):
            indices[mask] = palette_idx
            mapped_count += int(np.sum(mask))

    # Override transparent pixels to index 0
    indices[transparent_mask] = 0

    if dither_mode == "bayer" and dither_strength > 0.0:
        logger.debug(
            "Quantized %dx%d with bayer dither (%.2f): %d mappings, %d pixels mapped",
            width,
            height,
            dither_strength,
            len(color_mappings),
            mapped_count,
        )

    return indices


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
    dither_mode: str = "none",
    dither_strength: float = 0.0,
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
        dither_mode: Dithering mode ("none" or "bayer", default "none")
        dither_strength: Dithering strength 0.0-1.0 (default 0.0, disabled)

    Returns:
        PIL Image in mode "P" (indexed) with the specified palette
    """
    # Use shared implementation
    indices = _quantize_impl(
        img,
        palette_rgb,
        {},  # No explicit mappings
        transparency_threshold,
        dither_mode,
        dither_strength,
    )

    # Create indexed PIL image
    indexed_img = Image.fromarray(indices, mode="P")

    # Build palette for PIL (flat list of RGB values, padded to 256 colors)
    flat_palette: list[int] = []
    for rgb in palette_rgb:
        flat_palette.extend([rgb[0], rgb[1], rgb[2]])
    # Pad to 256 colors (PIL requirement for mode P)
    flat_palette.extend([0] * (768 - len(flat_palette)))

    indexed_img.putpalette(flat_palette)

    if dither_mode == "none":
        # Only log here if dither is off (impl logs if on)
        height, width = indices.shape
        # Count transparent pixels (index 0)
        transparent_count = int(np.sum(indices == 0))
        logger.debug(
            "Quantized %dx%d image to %d-color palette (perceptual LAB distance, transparent pixels: %d)",
            width,
            height,
            len(palette_rgb),
            transparent_count,
        )

    return indexed_img


def quantize_with_mappings(
    img: Image.Image,
    palette_rgb: list[tuple[int, int, int]],
    color_mappings: dict[tuple[int, int, int], int],
    transparency_threshold: int = QUANTIZATION_TRANSPARENCY_THRESHOLD,
    dither_mode: str = "none",
    dither_strength: float = 0.0,
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
        dither_mode: Dithering mode ("none" or "bayer", default "none")
        dither_strength: Dithering strength 0.0-1.0 (default 0.0, disabled)

    Returns:
        PIL Image in mode "P" (indexed) with the specified palette
    """
    # Use shared implementation
    indices = _quantize_impl(
        img,
        palette_rgb,
        color_mappings,
        transparency_threshold,
        dither_mode,
        dither_strength,
    )

    # Create indexed PIL image
    indexed_img = Image.fromarray(indices, mode="P")

    # Build palette for PIL (flat list of RGB values, padded to 256 colors)
    flat_palette: list[int] = []
    for rgb in palette_rgb:
        flat_palette.extend([rgb[0], rgb[1], rgb[2]])
    # Pad to 256 colors (PIL requirement for mode P)
    flat_palette.extend([0] * (768 - len(flat_palette)))

    indexed_img.putpalette(flat_palette)

    if dither_mode == "none":
        height, width = indices.shape
        logger.debug(
            "Quantized %dx%d with mappings (perceptual LAB): %d explicit mappings",
            width,
            height,
            len(color_mappings),
        )

    return indexed_img


def quantize_to_index_map(
    img: Image.Image,
    palette_rgb: list[tuple[int, int, int]],
    color_mappings: dict[tuple[int, int, int], int],
    transparency_threshold: int = QUANTIZATION_TRANSPARENCY_THRESHOLD,
    dither_mode: str = "none",
    dither_strength: float = 0.0,
) -> np.ndarray:
    """Generate palette index map from RGBA image using color mappings.

    Returns numpy array (H, W) of uint8 indices instead of PIL Image.
    Used for "quantize full-res, scale indexed" approach.

    Args:
        img: PIL Image in RGBA mode
        palette_rgb: List of 16 RGB tuples defining the target palette
        color_mappings: Dict mapping RGB tuples to palette indices
        transparency_threshold: Alpha values below this map to index 0
        dither_mode: Dithering mode ("none" or "bayer", default "none")
        dither_strength: Dithering strength 0.0-1.0 (default 0.0, disabled)

    Returns:
        numpy array of shape (H, W) with uint8 palette indices.
        Index 0 = transparent, indices 1-15 = opaque colors.
    """
    return _quantize_impl(
        img,
        palette_rgb,
        color_mappings,
        transparency_threshold,
        dither_mode,
        dither_strength,
    )


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


def _snap_color_counts(
    color_counts: dict[tuple[int, int, int], int],
) -> dict[tuple[int, int, int], int]:
    """Snap all colors in a count dict to SNES-valid values, merging counts."""
    snapped_counts: dict[tuple[int, int, int], int] = {}
    for color, count in color_counts.items():
        snapped = snap_to_snes_color(color)
        snapped_counts[snapped] = snapped_counts.get(snapped, 0) + count
    return snapped_counts


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


def _cluster_similar_colors(
    color_counts: dict[tuple[int, int, int], int],
    threshold_sq: float = 25.0,  # 5.0² LAB units
) -> dict[tuple[int, int, int], int]:
    """Merge perceptually similar colors, keeping most frequent as representative.

    Uses greedy frequency-weighted clustering in LAB space.

    Args:
        color_counts: Dict mapping RGB tuples to pixel counts
        threshold_sq: Squared LAB distance threshold for merging (default 25.0 = 5.0²)

    Returns:
        Dict with merged colors and combined pixel counts
    """
    if not color_counts:
        return {}

    # Sort colors by frequency (descending), then by RGB tuple (for determinism)
    sorted_colors = sorted(
        color_counts.items(),
        key=lambda x: (-x[1], x[0]),  # Most frequent first, then by RGB tuple
    )

    # Convert all colors to LAB once
    color_to_lab: dict[tuple[int, int, int], tuple[float, float, float]] = {}
    for color, _count in sorted_colors:
        color_to_lab[color] = rgb_to_lab(color)

    # Track which colors have been merged
    merged: set[tuple[int, int, int]] = set()
    result: dict[tuple[int, int, int], int] = {}

    # For each color (most frequent first)
    for representative, rep_count in sorted_colors:
        if representative in merged:
            continue

        # This color becomes a cluster representative
        total_count = rep_count
        rep_lab = color_to_lab[representative]

        # Find all unmerged colors within threshold_sq LAB distance
        for candidate, cand_count in sorted_colors:
            if candidate == representative or candidate in merged:
                continue

            cand_lab = color_to_lab[candidate]

            # Calculate squared LAB distance
            dL = rep_lab[0] - cand_lab[0]
            da = rep_lab[1] - cand_lab[1]
            db = rep_lab[2] - cand_lab[2]
            dist_sq = dL * dL + da * da + db * db

            if dist_sq <= threshold_sq:
                # Merge this color into representative
                total_count += cand_count
                merged.add(candidate)

        # Store representative with combined count
        result[representative] = total_count

    return result


def _dedupe_preserve_order(
    colors: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    """Deduplicate colors while preserving original order."""
    seen: set[tuple[int, int, int]] = set()
    deduped: list[tuple[int, int, int]] = []
    for color in colors:
        if color in seen:
            continue
        seen.add(color)
        deduped.append(color)
    return deduped


def _ensure_palette_diversity(
    palette: list[tuple[int, int, int]],
    color_counts: dict[tuple[int, int, int], int],
    *,
    max_colors: int,
    protected_colors: set[tuple[int, int, int]],
    min_distance: float,
) -> list[tuple[int, int, int]]:
    """Remove overly similar colors and refill with more distinct choices."""
    if max_colors <= 0:
        return []

    if not palette:
        return [(0, 0, 0)] * max_colors

    transparency = palette[0]
    palette_colors = [color for color in _dedupe_preserve_order(palette[1:]) if color != transparency]

    protected_list = [color for color in palette_colors if color in protected_colors]
    non_protected = [color for color in palette_colors if color not in protected_colors]

    def score(color: tuple[int, int, int]) -> int:
        bonus = 1_000_000 if color in protected_colors else 0
        return bonus + color_counts.get(color, 0)

    non_protected.sort(key=lambda color: (score(color), color), reverse=True)

    min_distance_sq = min_distance * min_distance
    target_count = max(0, max_colors - 1)

    kept: list[tuple[int, int, int]] = []
    for color in _dedupe_preserve_order(protected_list):
        if len(kept) >= target_count:
            break
        kept.append(color)

    for color in non_protected:
        if len(kept) >= target_count:
            break
        if all(perceptual_distance_sq(color, kept_color) >= min_distance_sq for kept_color in kept):
            kept.append(color)

    if len(kept) < target_count:
        candidates = [color for color in color_counts if color != transparency and color not in kept]
        candidates.sort(key=lambda color: (-color_counts.get(color, 0), color))

        while len(kept) < target_count and candidates:
            best_color: tuple[int, int, int] | None = None
            best_min_distance = -1.0
            best_count = -1

            for candidate in candidates:
                if kept:
                    min_distance_candidate = min(perceptual_distance_sq(candidate, kept_color) for kept_color in kept)
                else:
                    min_distance_candidate = float("inf")

                count = color_counts.get(candidate, 0)
                if min_distance_candidate > best_min_distance or (
                    min_distance_candidate == best_min_distance
                    and (count > best_count or (count == best_count and (best_color is None or candidate < best_color)))
                ):
                    best_color = candidate
                    best_min_distance = min_distance_candidate
                    best_count = count

            if best_color is None:
                break

            kept.append(best_color)
            candidates.remove(best_color)

    diversified = [transparency, *kept]
    while len(diversified) < max_colors:
        diversified.append((0, 0, 0))

    return diversified


def quantize_colors_to_palette(
    color_counts: dict[tuple[int, int, int], int],
    max_colors: int = SNES_PALETTE_SIZE,
    *,
    snap_to_snes: bool = True,
    dither_mode: str = "none",
    dither_strength: float = 0.0,
    background_color: tuple[int, int, int] | None = None,
    background_tolerance: int = 30,
    cluster_threshold: float | None = None,
    diversity_min_distance: float = PALETTE_DIVERSITY_MIN_DISTANCE,
    rare_rarity_threshold: float = 0.01,
    rare_distinctness_threshold: float = 12.0,
    rare_max_candidates: int = 5,
) -> list[tuple[int, int, int]]:
    """Quantize colors to a limited palette.

    Uses PIL's median-cut quantization to reduce colors.
    Index 0 is reserved for transparency (black).

    Args:
        color_counts: Dict mapping RGB tuples to pixel counts
        max_colors: Maximum colors in output palette (default 16 for SNES)
        snap_to_snes: If True, snap colors to SNES-valid values (multiples of 8)
        dither_mode: Dithering mode ("none" or "bayer", default "none")
        dither_strength: Dithering strength 0.0-1.0 (default 0.0, disabled)
        background_color: If provided, colors within tolerance are filtered out
        background_tolerance: Max RGB component difference to match background (default 30)
        cluster_threshold: LAB delta for grouping similar colors before quantization
        diversity_min_distance: Minimum LAB delta between palette colors
        rare_rarity_threshold: Pixel fraction threshold for rare color detection (0.0-1.0)
        rare_distinctness_threshold: LAB delta for rare color distinctness
        rare_max_candidates: Max rare colors to reserve before quantization

    Returns:
        List of RGB tuples (max_colors entries, index 0 = transparency)
    """
    if cluster_threshold is None:
        cluster_threshold = math.sqrt(PALETTE_CLUSTER_THRESHOLD_SQ)
    if not color_counts:
        # Return empty palette with black at index 0
        return [(0, 0, 0)] * max_colors

    # Filter background colors
    if background_color is not None:
        filtered_counts: dict[tuple[int, int, int], int] = {}
        for color, count in color_counts.items():
            # Check if color is within tolerance of background
            dr = abs(color[0] - background_color[0])
            dg = abs(color[1] - background_color[1])
            db = abs(color[2] - background_color[2])
            if dr <= background_tolerance and dg <= background_tolerance and db <= background_tolerance:
                continue  # Skip background-like colors
            filtered_counts[color] = count
        color_counts = filtered_counts
        if not color_counts:
            return [(0, 0, 0)] * max_colors

    cluster_threshold = max(0.0, cluster_threshold)
    diversity_min_distance = max(0.0, diversity_min_distance)
    rare_rarity_threshold = max(0.0, min(1.0, rare_rarity_threshold))
    rare_distinctness_threshold = max(0.0, rare_distinctness_threshold)
    rare_max_candidates = max(0, rare_max_candidates)

    original_counts = dict(color_counts)

    max_reserved = max(0, max_colors - 1)
    rare_colors = detect_rare_important_colors(
        original_counts,
        rarity_threshold=rare_rarity_threshold,
        distinctness_threshold=rare_distinctness_threshold,
        max_candidates=min(rare_max_candidates, max_reserved),
    )
    reserved_colors = _dedupe_preserve_order([rc[0] for rc in rare_colors if rc[0] != (0, 0, 0)])

    if snap_to_snes:
        reserved_colors = _dedupe_preserve_order(
            [snap_to_snes_color(color) for color in reserved_colors if color != (0, 0, 0)]
        )
        original_counts_snapped = _snap_color_counts(original_counts)
    else:
        original_counts_snapped = original_counts

    if len(reserved_colors) > max_reserved:
        reserved_colors = reserved_colors[:max_reserved]

    # Build working counts for quantization (exclude reserved to avoid wasting slots)
    color_counts = dict(original_counts_snapped)
    for color in reserved_colors:
        color_counts.pop(color, None)

    # Cluster similar colors to group near-duplicates
    color_counts = _cluster_similar_colors(
        color_counts,
        threshold_sq=cluster_threshold * cluster_threshold,
    )

    # Sort colors by frequency
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)

    reserved_set = set(reserved_colors)
    available_slots = max(0, max_colors - 1 - len(reserved_set))  # -1 for transparency

    if available_slots <= 0 or len(sorted_colors) <= available_slots:
        palette = [(0, 0, 0)]
        for color in reserved_colors:
            if color != (0, 0, 0) and color not in palette:
                palette.append(color)
        for color, _count in sorted_colors:
            if color not in palette and len(palette) < max_colors:
                palette.append(color)
    else:
        # Create a small image with all colors weighted by frequency
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

        # Quantize to available_slots colors (after reserving slots for rare important colors)
        quantized = img.quantize(colors=available_slots, method=Image.Quantize.MEDIANCUT)
        raw_palette = quantized.getpalette()

        if raw_palette is None:
            palette = [(0, 0, 0)]
            for color in reserved_colors:
                if color != (0, 0, 0):
                    palette.append(color)
            for color, _count in sorted_colors:
                if color not in palette and len(palette) < max_colors:
                    palette.append(color)
        else:
            palette = [(0, 0, 0)]  # Index 0 = transparent
            for color in reserved_colors:
                if color != (0, 0, 0):
                    palette.append(color)

            for i in range(available_slots):
                if len(palette) >= max_colors:
                    break
                r = raw_palette[i * 3]
                g = raw_palette[i * 3 + 1]
                b = raw_palette[i * 3 + 2]
                color = (r, g, b)
                if snap_to_snes:
                    color = snap_to_snes_color(color)
                if color not in palette:
                    palette.append(color)

    while len(palette) < max_colors:
        palette.append((0, 0, 0))

    return _ensure_palette_diversity(
        palette,
        original_counts_snapped,
        max_colors=max_colors,
        protected_colors=reserved_set,
        min_distance=diversity_min_distance,
    )
