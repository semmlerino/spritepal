"""Content bounds analysis for sprite images.

This module provides utilities for analyzing the content distribution
within sprite images, including centroid (center of mass) calculation
for content-weighted alignment.
"""

from __future__ import annotations

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
