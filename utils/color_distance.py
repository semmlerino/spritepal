"""Perceptual color distance utilities using CIELAB color space.

The CIELAB color space is designed to approximate human vision, making
distance calculations more perceptually accurate than RGB Euclidean distance.

This is critical for sprite quantization where small but important details
(like eye whites against skin tones) may have similar RGB values but are
perceptually distinct.
"""

from __future__ import annotations

import math
from functools import lru_cache


@lru_cache(maxsize=4096)
def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Convert RGB to CIELAB color space.

    Uses D65 standard illuminant (daylight).

    Args:
        rgb: RGB tuple with 8-bit values (0-255)

    Returns:
        LAB tuple (L*, a*, b*) where L* is 0-100, a* and b* are approximately -128 to 128
    """
    # Normalize RGB to 0-1 and apply sRGB gamma correction
    r = rgb[0] / 255.0
    g = rgb[1] / 255.0
    b = rgb[2] / 255.0

    # sRGB to linear RGB
    def srgb_to_linear(c: float) -> float:
        if c <= 0.04045:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    r_lin = srgb_to_linear(r)
    g_lin = srgb_to_linear(g)
    b_lin = srgb_to_linear(b)

    # Linear RGB to XYZ (D65 illuminant)
    x = r_lin * 0.4124564 + g_lin * 0.3575761 + b_lin * 0.1804375
    y = r_lin * 0.2126729 + g_lin * 0.7151522 + b_lin * 0.0721750
    z = r_lin * 0.0193339 + g_lin * 0.1191920 + b_lin * 0.9503041

    # Reference white D65
    x_ref = 0.95047
    y_ref = 1.00000
    z_ref = 1.08883

    # Normalize by reference white
    x_n = x / x_ref
    y_n = y / y_ref
    z_n = z / z_ref

    # XYZ to LAB
    def f(t: float) -> float:
        delta = 6.0 / 29.0
        if t > delta**3:
            return t ** (1.0 / 3.0)
        return t / (3.0 * delta**2) + 4.0 / 29.0

    L = 116.0 * f(y_n) - 16.0
    a = 500.0 * (f(x_n) - f(y_n))
    b_val = 200.0 * (f(y_n) - f(z_n))

    return (L, a, b_val)


def perceptual_distance_sq(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """Calculate squared perceptual distance using CIELAB color space.

    This distance better matches human perception than RGB Euclidean distance.
    A distance of ~2.3 is the "just noticeable difference" (JND) threshold.

    Args:
        c1: First RGB color tuple (0-255 per channel)
        c2: Second RGB color tuple (0-255 per channel)

    Returns:
        Squared perceptual distance (Delta E squared)
    """
    lab1 = rgb_to_lab(c1)
    lab2 = rgb_to_lab(c2)

    dL = lab1[0] - lab2[0]
    da = lab1[1] - lab2[1]
    db = lab1[2] - lab2[2]

    return dL * dL + da * da + db * db


def perceptual_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """Calculate perceptual distance (Delta E) using CIELAB color space.

    Args:
        c1: First RGB color tuple (0-255 per channel)
        c2: Second RGB color tuple (0-255 per channel)

    Returns:
        Perceptual distance (Delta E)
    """
    return math.sqrt(perceptual_distance_sq(c1, c2))


def rgb_distance_sq(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> int:
    """Calculate squared Euclidean distance in RGB space.

    Provided for cases where RGB distance is explicitly needed.

    Args:
        c1: First RGB color tuple
        c2: Second RGB color tuple

    Returns:
        Squared Euclidean distance
    """
    return (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2


def detect_rare_important_colors(
    color_counts: dict[tuple[int, int, int], int],
    rarity_threshold: float = 0.01,
    distinctness_threshold: float = 20.0,
    max_candidates: int = 5,
) -> list[tuple[tuple[int, int, int], int, float]]:
    """Detect rare colors that are perceptually distinct (potentially important details).

    Identifies colors that:
    1. Appear in less than rarity_threshold (default 1%) of total pixels
    2. Are perceptually distinct from common colors (LAB delta > distinctness_threshold)

    These are often important visual details like eye whites, highlights, or small
    decorative elements that should not be lost during quantization.

    Args:
        color_counts: Dict mapping RGB tuples to pixel counts
        rarity_threshold: Colors below this pixel fraction are "rare" (0.0-1.0)
        distinctness_threshold: Minimum LAB delta to be considered distinct
        max_candidates: Maximum number of candidates to return

    Returns:
        List of tuples: (rgb_color, pixel_count, min_distance_to_common)
        Sorted by distinctness (most distinct first)
    """
    if not color_counts:
        return []

    total_pixels = sum(color_counts.values())
    if total_pixels == 0:
        return []

    pixel_threshold = int(total_pixels * rarity_threshold)

    # Separate rare and common colors
    rare_colors: list[tuple[tuple[int, int, int], int]] = []
    common_colors: list[tuple[int, int, int]] = []

    for color, count in color_counts.items():
        if count <= pixel_threshold:
            rare_colors.append((color, count))
        else:
            common_colors.append(color)

    if not rare_colors or not common_colors:
        return []

    # For each rare color, find minimum perceptual distance to common colors
    candidates: list[tuple[tuple[int, int, int], int, float]] = []

    for rare_color, pixel_count in rare_colors:
        min_distance = float("inf")
        for common_color in common_colors:
            dist = perceptual_distance(rare_color, common_color)
            min_distance = min(min_distance, dist)

        # Only include if perceptually distinct
        if min_distance >= distinctness_threshold:
            candidates.append((rare_color, pixel_count, min_distance))

    # Sort by distinctness (most distinct first)
    candidates.sort(key=lambda x: x[2], reverse=True)

    return candidates[:max_candidates]
