#!/usr/bin/env python3
"""
RGB to indexed image conversion service.

Provides conversion between RGB images (from AI frames) and indexed
palette-based images (for SNES injection).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from core.palette_utils import snap_to_snes_color
from utils.color_distance import perceptual_distance, perceptual_distance_sq

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette


def convert_rgb_to_indexed(
    image: Image.Image,
    palette: SheetPalette,
    *,
    transparency_threshold: int = 128,
) -> np.ndarray:
    """Convert an RGB(A) image to indexed palette format.

    Uses explicit color_mappings first, then falls back to nearest-color
    matching in RGB space.

    Args:
        image: PIL Image in RGB or RGBA mode
        palette: SheetPalette with colors and optional color_mappings
        transparency_threshold: Alpha values below this become index 0

    Returns:
        2D numpy array (H, W) of uint8 palette indices (0-15)
    """
    # Ensure RGBA mode for alpha handling
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # Get image data as numpy array
    img_data = np.array(image)
    height, width = img_data.shape[:2]

    # Output array of palette indices
    indexed = np.zeros((height, width), dtype=np.uint8)

    # Process each pixel
    for y in range(height):
        for x in range(width):
            r, g, b, a = img_data[y, x]

            # Transparent pixels -> index 0
            if a < transparency_threshold:
                indexed[y, x] = 0
                continue

            rgb = (int(r), int(g), int(b))

            # Check explicit color mapping first
            if rgb in palette.color_mappings:
                indexed[y, x] = palette.color_mappings[rgb]
                continue

            # Fall back to nearest color (perceptual LAB distance)
            best_idx = _find_nearest_color(rgb, palette.colors)
            indexed[y, x] = best_idx

    return indexed


def _find_nearest_color(rgb: tuple[int, int, int], palette_colors: list[tuple[int, int, int]]) -> int:
    """Find the palette index with the nearest color to the given RGB.

    Uses perceptual CIELAB distance for better color matching.
    Skips index 0 (reserved for transparency) for opaque pixels.

    Args:
        rgb: RGB color tuple to match
        palette_colors: List of RGB tuples (16 colors)

    Returns:
        Palette index (1-15) of nearest color (never returns 0)
    """
    min_dist = float("inf")
    best_idx = 1  # Skip index 0 (transparent)

    for idx, pal_color in enumerate(palette_colors):
        if idx == 0:
            continue  # Skip transparent index
        dist = perceptual_distance_sq(rgb, pal_color)
        if dist < min_dist:
            min_dist = dist
            best_idx = idx

    return best_idx


def convert_indexed_to_rgb(
    indexed: np.ndarray,
    palette: SheetPalette,
    *,
    transparent_color: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> Image.Image:
    """Convert indexed palette data back to an RGBA image.

    Applies SNES color snapping for WYSIWYG fidelity - the colors shown
    match what will be injected into the ROM (5-bit BGR555 precision).

    Args:
        indexed: 2D numpy array (H, W) of palette indices (0-15)
        palette: SheetPalette with colors
        transparent_color: RGBA color for index 0 (default fully transparent)

    Returns:
        PIL Image in RGBA mode
    """
    height, width = indexed.shape

    # Pre-compute SNES-snapped palette colors for WYSIWYG fidelity
    snapped_colors = [snap_to_snes_color(c) for c in palette.colors]

    # Create output RGBA array
    rgba = np.zeros((height, width, 4), dtype=np.uint8)

    for y in range(height):
        for x in range(width):
            idx = indexed[y, x]
            if idx == 0:
                rgba[y, x] = transparent_color
            elif 0 < idx < len(snapped_colors):
                r, g, b = snapped_colors[idx]
                rgba[y, x] = (r, g, b, 255)
            else:
                # Out of range - use transparent
                rgba[y, x] = transparent_color

    return Image.fromarray(rgba, mode="RGBA")


def convert_indexed_to_pil_indexed(
    data: np.ndarray,
    palette: SheetPalette,
) -> Image.Image:
    """Convert indexed data to a PIL Image in indexed/palette mode.

    This creates a true indexed PNG with the palette embedded,
    which is what we want for the edited output.
    Index 0 is marked as transparent.

    Args:
        data: 2D numpy array (H, W) of palette indices (0-15)
        palette: SheetPalette with colors

    Returns:
        PIL Image in "P" (palette) mode with index 0 as transparent
    """
    height, width = data.shape

    # Create palette mode image
    img = Image.new("P", (width, height))

    # Set the palette (256 colors, each 3 bytes RGB)
    # We fill the first 16 with our colors, rest with black
    flat_palette: list[int] = []
    for i in range(256):
        if i < len(palette.colors):
            r, g, b = palette.colors[i]
            flat_palette.extend([r, g, b])
        else:
            flat_palette.extend([0, 0, 0])

    img.putpalette(flat_palette)

    # Set pixel data
    img.putdata(list(data.flatten()))

    # Mark index 0 as transparent
    # This sets the tRNS chunk in the PNG
    img.info["transparency"] = 0

    return img


def get_color_distance(color1: tuple[int, int, int], color2: tuple[int, int, int]) -> float:
    """Calculate perceptual distance between two RGB colors using CIELAB.

    Uses CIELAB color space for perceptually accurate distance measurement.
    This better matches human perception than RGB Euclidean distance.

    Args:
        color1: First RGB color tuple
        color2: Second RGB color tuple

    Returns:
        Perceptual distance (Delta E) in CIELAB space
    """
    return perceptual_distance(color1, color2)


def find_closest_palette_index(
    rgb: tuple[int, int, int],
    palette: SheetPalette,
    *,
    skip_transparent: bool = True,
) -> tuple[int, float]:
    """Find the palette index closest to a given RGB color.

    Uses perceptual CIELAB distance for better color matching.

    Args:
        rgb: RGB color to match
        palette: SheetPalette with colors
        skip_transparent: If True, skip index 0 (transparent)

    Returns:
        Tuple of (palette_index, perceptual_distance)
    """
    best_idx = 0 if not skip_transparent else 1
    best_distance = float("inf")

    start_idx = 1 if skip_transparent else 0
    for idx in range(start_idx, len(palette.colors)):
        distance = perceptual_distance(rgb, palette.colors[idx])
        if distance < best_distance:
            best_distance = distance
            best_idx = idx

    return best_idx, best_distance


def analyze_color_usage(
    image: Image.Image,
    palette: SheetPalette,
    *,
    transparency_threshold: int = 128,
) -> dict[str, object]:
    """Analyze how colors in an image map to a palette.

    Useful for identifying quantization issues before conversion.

    Args:
        image: PIL Image to analyze
        palette: SheetPalette to map against
        transparency_threshold: Alpha threshold for transparency

    Returns:
        Dict with analysis results including:
        - exact_matches: Colors with exact palette matches
        - nearest_matches: Colors requiring nearest-neighbor
        - unmapped_colors: Unique colors not in explicit mappings
        - distance_stats: Min/max/avg distance for nearest matches
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    img_data = np.array(image)
    height, width = img_data.shape[:2]

    exact_matches: set[tuple[int, int, int]] = set()
    nearest_matches: dict[tuple[int, int, int], tuple[int, float]] = {}

    for y in range(height):
        for x in range(width):
            r, g, b, a = img_data[y, x]

            if a < transparency_threshold:
                continue

            rgb = (int(r), int(g), int(b))

            if rgb in palette.color_mappings:
                exact_matches.add(rgb)
            elif rgb not in nearest_matches:
                idx, dist = find_closest_palette_index(rgb, palette)
                nearest_matches[rgb] = (idx, dist)

    # Compute statistics
    distances = [d for _, d in nearest_matches.values()]
    distance_stats = {
        "min": min(distances) if distances else 0,
        "max": max(distances) if distances else 0,
        "avg": sum(distances) / len(distances) if distances else 0,
    }

    return {
        "exact_matches": list(exact_matches),
        "nearest_matches": {str(k): v for k, v in nearest_matches.items()},
        "unmapped_count": len(nearest_matches),
        "exact_count": len(exact_matches),
        "distance_stats": distance_stats,
    }


def load_image_preserving_indices(
    path: Path,
    *,
    sheet_palette: SheetPalette | None = None,
) -> tuple[np.ndarray | None, Image.Image]:
    """Load image, extracting palette indices if it's an indexed PNG.

    BUG-1 FIX: When loading AI frames that were edited in the palette editor,
    preserve the original palette indices to avoid re-quantization during
    injection. This ensures that edited pixels maintain their exact palette
    index assignment even when palette colors are duplicated.

    If a sheet palette is provided, the embedded palette must match the
    sheet palette colors to preserve indices. This avoids misaligned indices
    when an indexed PNG was created with a different palette.

    Args:
        path: Path to the image file
        sheet_palette: Optional sheet palette used to validate palette matches

    Returns:
        Tuple of (index_map, rgba_image):
        - index_map: numpy array of palette indices (uint8) if image is indexed PNG,
          None if image is not indexed (RGB/RGBA)
        - rgba_image: PIL Image converted to RGBA for compositing
    """
    with Image.open(path) as img:
        if img.mode == "P":
            # Indexed PNG - extract indices BEFORE converting
            index_map = np.array(img, dtype=np.uint8)

            if sheet_palette is not None:
                palette_data = img.getpalette() or []
                expected_colors = sheet_palette.colors
                needed = len(expected_colors) * 3
                if len(palette_data) < needed:
                    return None, img.convert("RGBA")

                palette_colors = [
                    (palette_data[i], palette_data[i + 1], palette_data[i + 2])
                    for i in range(0, needed, 3)
                ]

                if palette_colors != expected_colors:
                    return None, img.convert("RGBA")

            return index_map, img.convert("RGBA")
        # Non-indexed image - no indices to preserve
        return None, img.convert("RGBA")
