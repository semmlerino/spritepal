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
