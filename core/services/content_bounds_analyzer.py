"""Content bounds analysis for sprite images.

This module provides utilities for analyzing the content distribution
within sprite images, including centroid (center of mass) calculation
for content-weighted alignment.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray
from PIL import Image


class ContentBoundsAnalyzer:
    """Analyzes content distribution within images for alignment purposes."""

    @staticmethod
    def compute_centroid(image: Image.Image) -> tuple[float, float]:
        """Compute center of mass of opaque pixels.

        The centroid is weighted by alpha values, so dense regions (main body)
        pull more than sparse protrusions. This is useful for aligning sprites
        to their visual mass rather than their bounding box center.

        Args:
            image: PIL Image (will be converted to RGBA if not already)

        Returns:
            Tuple of (x, y) coordinates representing the center of mass.
            Returns image center if image has no opaque pixels.
        """
        arr = np.array(image.convert("RGBA"))
        alpha: NDArray[np.float64] = arr[:, :, 3].astype(np.float64)
        total = np.sum(alpha)

        if total == 0:
            # No opaque pixels - return image center
            return image.width / 2, image.height / 2

        # Create coordinate grids
        y_coords, x_coords = np.mgrid[0 : alpha.shape[0], 0 : alpha.shape[1]]

        # Compute weighted average (center of mass)
        centroid_x = float(np.sum(x_coords * alpha) / total)
        centroid_y = float(np.sum(y_coords * alpha) / total)

        return centroid_x, centroid_y


def compute_tile_centroid(
    tile_rects: list[tuple[int, int, int, int]],
) -> tuple[float, float]:
    """Compute centroid of tile coverage (weighted by area, ignores gaps).

    Unlike bounding box center, this accounts for non-contiguous tile layouts
    where gaps exist in the coverage. Each tile contributes proportionally
    to its area.

    Args:
        tile_rects: List of (x, y, width, height) tuples for each tile

    Returns:
        Tuple of (centroid_x, centroid_y) coordinates.
        Returns (0.0, 0.0) if tile_rects is empty.
    """
    if not tile_rects:
        return (0.0, 0.0)

    total_area = 0.0
    weighted_x = 0.0
    weighted_y = 0.0

    for x, y, w, h in tile_rects:
        area = w * h
        weighted_x += (x + w / 2) * area
        weighted_y += (y + h / 2) * area
        total_area += area

    if total_area == 0:
        return (0.0, 0.0)

    return (weighted_x / total_area, weighted_y / total_area)


def get_content_bbox(
    image: Image.Image,
    min_alpha: int = 5,
) -> tuple[int, int, int, int]:
    """Get bounding box of actual content in the image.

    Handles both transparent backgrounds (via alpha channel) and solid backgrounds
    (by detecting background color from corners). Uses a minimum alpha threshold
    to ignore near-transparent pixels (anti-aliasing artifacts, etc.).

    Args:
        image: PIL Image to analyze.
        min_alpha: Minimum alpha value to consider as content (default 5).
            Pixels with alpha <= min_alpha are treated as transparent.

    Returns:
        Bounding box as (left, top, right, bottom).
    """
    full_bounds = (0, 0, image.width, image.height)

    # Alpha-based detection with threshold
    rgba = image.convert("RGBA")
    alpha = np.array(rgba)[:, :, 3]

    # Apply minimum alpha threshold
    content_mask = alpha > min_alpha

    rows_with_content = np.any(content_mask, axis=1)
    cols_with_content = np.any(content_mask, axis=0)

    if rows_with_content.any() and cols_with_content.any():
        row_indices = np.where(rows_with_content)[0]
        col_indices = np.where(cols_with_content)[0]
        alpha_bbox: tuple[int, int, int, int] | None = (
            int(col_indices[0]),
            int(row_indices[0]),
            int(col_indices[-1] + 1),
            int(row_indices[-1] + 1),
        )
    else:
        alpha_bbox = None

    # If getbbox returned None or full image bounds, try color-based detection
    if alpha_bbox is None or alpha_bbox == full_bounds:
        # Convert to RGB for color analysis
        rgb_image = image.convert("RGB")
        pixels = np.array(rgb_image)

        # Sample background color from corners (average of 4 corners)
        corner_size = min(5, image.width // 10, image.height // 10)
        corner_size = max(corner_size, 1)

        corners = [
            pixels[:corner_size, :corner_size],  # top-left
            pixels[:corner_size, -corner_size:],  # top-right
            pixels[-corner_size:, :corner_size],  # bottom-left
            pixels[-corner_size:, -corner_size:],  # bottom-right
        ]
        bg_color = np.mean([c.mean(axis=(0, 1)) for c in corners], axis=0)

        # Find pixels that differ significantly from background
        tolerance = 30  # RGB distance threshold
        diff = np.sqrt(np.sum((pixels.astype(float) - bg_color) ** 2, axis=2))
        content_mask = diff > tolerance

        # Find bounding box of content
        rows_with_content = np.any(content_mask, axis=1)
        cols_with_content = np.any(content_mask, axis=0)

        if rows_with_content.any() and cols_with_content.any():
            row_indices = np.where(rows_with_content)[0]
            col_indices = np.where(cols_with_content)[0]
            return (
                int(col_indices[0]),
                int(row_indices[0]),
                int(col_indices[-1] + 1),
                int(row_indices[-1] + 1),
            )

    if alpha_bbox is not None:
        return alpha_bbox

    return full_bounds


def get_tight_content_bbox(
    image: Image.Image,
    percentile: float = 99.0,
) -> tuple[int, int, int, int]:
    """Get tight bounding box ignoring outlier pixels.

    Uses percentile-based bounds to exclude stray pixels that would make
    the standard bounding box much larger than the main content area.
    This is useful for AI-generated images that may have artifacts near edges.

    Args:
        image: PIL Image to analyze.
        percentile: Percentage of pixels to include (default 99% excludes 1% outliers).

    Returns:
        Bounding box as (left, top, right, bottom).
    """
    arr = np.array(image.convert("RGBA"))
    alpha = arr[:, :, 3]

    # Find all non-transparent pixel coordinates
    y_coords, x_coords = np.where(alpha > 0)

    if len(x_coords) == 0:
        return (0, 0, image.width, image.height)

    # Compute percentile bounds to exclude outliers
    lower_pct = (100 - percentile) / 2
    upper_pct = 100 - lower_pct

    left = int(np.percentile(x_coords, lower_pct))
    right = int(np.percentile(x_coords, upper_pct)) + 1
    top = int(np.percentile(y_coords, lower_pct))
    bottom = int(np.percentile(y_coords, upper_pct)) + 1

    # Clamp to image bounds
    left = max(0, left)
    top = max(0, top)
    right = min(image.width, right)
    bottom = min(image.height, bottom)

    return (left, top, right, bottom)


def detect_background_color(
    image: Image.Image,
    corner_size: int = 5,
    variance_threshold: float = 30.0,
) -> tuple[tuple[int, int, int] | None, bool]:
    """Detect solid background color by sampling image corners.

    Samples the four corners of the image and analyzes nearly-opaque pixels
    to detect a consistent background color.

    Args:
        image: PIL Image to analyze
        corner_size: Size of corner region to sample (pixels)
        variance_threshold: Maximum RGB variance across corners for high confidence

    Returns:
        (rgb_color, is_confident):
        - rgb_color: Detected background color as RGB tuple, or None if transparent
        - is_confident: True if variance across corners is below threshold
    """
    # Convert to RGBA for alpha analysis
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    width, height = image.size
    arr = np.array(image)

    # Check if image has significant transparency (use alpha channel)
    alpha = arr[:, :, 3]
    opaque_ratio = np.sum(alpha > 200) / alpha.size
    if opaque_ratio < 0.5:
        # Image is mostly transparent - no solid background
        return None, True

    # Sample 4 corners
    corner_size = min(corner_size, width // 4, height // 4)
    corner_size = max(corner_size, 1)

    corners = [
        arr[:corner_size, :corner_size],  # Top-left
        arr[:corner_size, -corner_size:],  # Top-right
        arr[-corner_size:, :corner_size],  # Bottom-left
        arr[-corner_size:, -corner_size:],  # Bottom-right
    ]

    # Collect RGB values from nearly-opaque pixels in each corner
    corner_colors: list[tuple[float, float, float]] = []
    for corner in corners:
        # Filter to nearly-opaque pixels (alpha > 200)
        opaque_mask = corner[:, :, 3] > 200
        if not np.any(opaque_mask):
            continue
        rgb = corner[:, :, :3][opaque_mask]
        avg_color = rgb.mean(axis=0)
        corner_colors.append((float(avg_color[0]), float(avg_color[1]), float(avg_color[2])))

    if len(corner_colors) < 2:
        # Not enough corners with opaque pixels
        return None, False

    # Compute average color across corners
    avg_r = sum(c[0] for c in corner_colors) / len(corner_colors)
    avg_g = sum(c[1] for c in corner_colors) / len(corner_colors)
    avg_b = sum(c[2] for c in corner_colors) / len(corner_colors)

    # Compute variance (max distance from average)
    max_variance = 0.0
    for r, g, b in corner_colors:
        dist = math.sqrt((r - avg_r) ** 2 + (g - avg_g) ** 2 + (b - avg_b) ** 2)
        max_variance = max(max_variance, dist)

    # Result
    detected_color = (round(avg_r), round(avg_g), round(avg_b))
    is_confident = max_variance < variance_threshold

    return detected_color, is_confident


def remove_background(
    image: Image.Image,
    background_color: tuple[int, int, int],
    tolerance: int = 30,
) -> Image.Image:
    """Remove background color by setting matching pixels to transparent.

    Uses RGB Euclidean distance to identify background pixels. Pixels within
    the tolerance threshold have their alpha set to 0.

    Args:
        image: PIL Image (will be converted to RGBA if needed)
        background_color: RGB tuple of the background color to remove
        tolerance: Maximum RGB Euclidean distance for a pixel to be considered background

    Returns:
        New RGBA image with background removed (input is not modified)
    """
    # Convert to RGBA
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    else:
        image = image.copy()  # Don't modify input

    arr = np.array(image)
    rgb = arr[:, :, :3].astype(np.float32)

    # Compute Euclidean distance from background color
    bg = np.array(background_color, dtype=np.float32)
    dist = np.sqrt(np.sum((rgb - bg) ** 2, axis=2))

    # Set alpha to 0 for pixels within tolerance
    mask = dist <= tolerance
    arr[:, :, 3][mask] = 0

    return Image.fromarray(arr)
