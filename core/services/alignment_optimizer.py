"""Scipy-based alignment optimizer for finding maximum scale without overflow.

Uses scipy.optimize to efficiently search the (offset_x, offset_y, scale) space
to find the largest scale where AI content fits entirely within tile coverage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy import optimize

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


@dataclass
class AlignmentResult:
    """Result of alignment optimization."""

    offset_x: int
    offset_y: int
    scale: float
    success: bool
    iterations: int = 0


class AlignmentOptimizer:
    """Scipy-based optimizer for finding optimal alignment.

    Uses differential evolution for global optimization over the
    (offset_x, offset_y, scale) space, maximizing scale while ensuring
    no overflow of AI content outside tile coverage.
    """

    def __init__(self, min_scale: float = 0.01, max_scale: float = 1.0) -> None:
        """Initialize optimizer with scale bounds.

        Args:
            min_scale: Minimum allowed scale
            max_scale: Maximum allowed scale
        """
        self._min_scale = min_scale
        self._max_scale = max_scale

    def compute_optimal_alignment(
        self,
        ai_bbox: tuple[int, int, int, int],
        tile_rects: list[tuple[int, int, int, int]],
        initial_scale: float | None = None,
    ) -> AlignmentResult:
        """Find the optimal alignment that maximizes scale without overflow.

        Args:
            ai_bbox: AI content bounding box (left, top, right, bottom) in source coords
            tile_rects: List of (x, y, w, h) tile rectangles in scene coords
            initial_scale: Optional initial scale estimate for bounds

        Returns:
            AlignmentResult with optimal offset and scale
        """
        if not tile_rects:
            return AlignmentResult(0, 0, 1.0, success=False)

        ai_left, ai_top, ai_right, ai_bottom = ai_bbox
        ai_width = ai_right - ai_left
        ai_height = ai_bottom - ai_top

        if ai_width <= 0 or ai_height <= 0:
            return AlignmentResult(0, 0, 1.0, success=False)

        # Compute tile coverage bounds and create coverage mask
        tile_min_x = min(x for x, _, _, _ in tile_rects)
        tile_min_y = min(y for _, y, _, _ in tile_rects)
        tile_max_x = max(x + w for x, _, w, _ in tile_rects)
        tile_max_y = max(y + h for _, y, _, h in tile_rects)
        tile_width = tile_max_x - tile_min_x
        tile_height = tile_max_y - tile_min_y

        # Compute tile centroid for centering
        centroid_x, centroid_y = self._compute_centroid(tile_rects)

        # Create a bitmap mask for tile coverage (8x8 cell resolution)
        cell_size = 8
        mask_width = (tile_max_x - tile_min_x + cell_size - 1) // cell_size + 2
        mask_height = (tile_max_y - tile_min_y + cell_size - 1) // cell_size + 2
        tile_mask = np.zeros((mask_height, mask_width), dtype=np.uint8)

        for tx, ty, tw, th in tile_rects:
            # Convert to cell coordinates relative to tile_min
            cx_start = (tx - tile_min_x) // cell_size
            cy_start = (ty - tile_min_y) // cell_size
            cx_end = (tx + tw - tile_min_x + cell_size - 1) // cell_size
            cy_end = (ty + th - tile_min_y + cell_size - 1) // cell_size
            tile_mask[cy_start:cy_end, cx_start:cx_end] = 1

        # Estimate scale bounds
        scale_estimate = min(tile_width / ai_width, tile_height / ai_height)
        scale_estimate = max(self._min_scale, min(self._max_scale, scale_estimate))

        if initial_scale is not None:
            scale_estimate = initial_scale

        # Allow exploring up to 3x the initial estimate (capped at max_scale)
        scale_upper = min(scale_estimate * 3.0, self._max_scale)
        scale_lower = self._min_scale

        # Position bounds: allow content to move within extended tile coverage area
        margin = max(tile_width, tile_height) * 2
        pos_min_x = tile_min_x - int(margin)
        pos_max_x = tile_max_x + int(margin)
        pos_min_y = tile_min_y - int(margin)
        pos_max_y = tile_max_y + int(margin)

        def overflow_count(offset_x: float, offset_y: float, scale: float) -> int:
            """Count overflow cells (AI content outside tile coverage)."""
            # Scale and position the AI content bbox
            scene_left = int(ai_left * scale + offset_x)
            scene_top = int(ai_top * scale + offset_y)
            scene_right = int(ai_right * scale + offset_x)
            scene_bottom = int(ai_bottom * scale + offset_y)

            # Convert to cell coordinates
            cx_start = (scene_left - tile_min_x) // cell_size
            cy_start = (scene_top - tile_min_y) // cell_size
            cx_end = (scene_right - tile_min_x + cell_size - 1) // cell_size
            cy_end = (scene_bottom - tile_min_y + cell_size - 1) // cell_size

            # Count cells outside mask
            overflow = 0
            for cy in range(cy_start, cy_end):
                for cx in range(cx_start, cx_end):
                    if cy < 0 or cy >= mask_height or cx < 0 or cx >= mask_width or tile_mask[cy, cx] == 0:
                        overflow += 1
            return overflow

        def objective(params: NDArray[np.float64]) -> float:
            """Objective: minimize negative scale + overflow penalty."""
            offset_x, offset_y, scale = params
            overflow = overflow_count(offset_x, offset_y, scale)
            # Heavy penalty for overflow, reward for larger scale
            if overflow > 0:
                return 1000 * overflow - scale  # Penalty dominates
            return -scale  # Maximize scale (minimize negative)

        # Use differential evolution for global optimization
        bounds = [
            (pos_min_x, pos_max_x),  # offset_x
            (pos_min_y, pos_max_y),  # offset_y
            (scale_lower, scale_upper),  # scale
        ]

        # Initial guess: centered over tile centroid
        center_offset_x = centroid_x - (ai_left + ai_width / 2) * scale_estimate
        center_offset_y = centroid_y - (ai_top + ai_height / 2) * scale_estimate

        result = optimize.differential_evolution(
            objective,
            bounds,
            seed=42,  # pyright: ignore[reportCallIssue]  # scipy stubs incomplete
            maxiter=200,
            tol=1e-4,
            atol=0.5,  # Absolute tolerance in scale
            workers=1,  # Single-threaded for Qt compatibility
            updating="deferred",
            polish=True,  # Local refinement at end
            x0=[center_offset_x, center_offset_y, scale_estimate],
            init="sobol",  # Better space coverage than random
        )

        offset_x, offset_y, scale = result.x
        final_overflow = overflow_count(offset_x, offset_y, scale)

        if final_overflow > 0:
            # Fallback: find any valid position at estimated scale
            logger.warning(
                "Optimization found overflow=%d, falling back to grid search",
                final_overflow,
            )
            fallback = self._grid_search_position(
                ai_bbox,
                tile_rects,
                tile_mask,
                tile_min_x,
                tile_min_y,
                cell_size,
                mask_width,
                mask_height,
                scale_estimate,
                centroid_x,
                centroid_y,
            )
            if fallback is not None:
                return AlignmentResult(
                    offset_x=fallback[0],
                    offset_y=fallback[1],
                    scale=fallback[2],
                    success=True,
                    iterations=result.nit,
                )
            return AlignmentResult(
                offset_x=int(center_offset_x),
                offset_y=int(center_offset_y),
                scale=scale_estimate,
                success=False,
                iterations=result.nit,
            )

        logger.debug(
            "Optimal alignment found: scale=%.4f, offset=(%d, %d), iterations=%d",
            scale,
            int(offset_x),
            int(offset_y),
            result.nit,
        )

        return AlignmentResult(
            offset_x=int(offset_x + 0.5),  # Round to nearest int
            offset_y=int(offset_y + 0.5),  # Round to nearest int
            scale=scale,
            success=True,
            iterations=result.nit,
        )

    def _compute_centroid(self, tile_rects: list[tuple[int, int, int, int]]) -> tuple[float, float]:
        """Compute centroid of tile coverage."""
        total_area = 0
        cx_sum = 0.0
        cy_sum = 0.0
        for x, y, w, h in tile_rects:
            area = w * h
            cx_sum += (x + w / 2) * area
            cy_sum += (y + h / 2) * area
            total_area += area
        if total_area == 0:
            return (0.0, 0.0)
        return (cx_sum / total_area, cy_sum / total_area)

    def _grid_search_position(
        self,
        ai_bbox: tuple[int, int, int, int],
        tile_rects: list[tuple[int, int, int, int]],
        tile_mask: NDArray[np.uint8],
        tile_min_x: int,
        tile_min_y: int,
        cell_size: int,
        mask_width: int,
        mask_height: int,
        scale: float,
        centroid_x: float,
        centroid_y: float,
    ) -> tuple[int, int, float] | None:
        """Grid search for valid position at given scale."""
        ai_left, ai_top, ai_right, ai_bottom = ai_bbox
        ai_width = ai_right - ai_left
        ai_height = ai_bottom - ai_top

        # Center position
        center_x = int(centroid_x - (ai_left + ai_width / 2) * scale)
        center_y = int(centroid_y - (ai_top + ai_height / 2) * scale)

        def check_overflow(ox: int, oy: int) -> bool:
            scene_left = int(ai_left * scale + ox)
            scene_top = int(ai_top * scale + oy)
            scene_right = int(ai_right * scale + ox)
            scene_bottom = int(ai_bottom * scale + oy)

            cx_start = (scene_left - tile_min_x) // cell_size
            cy_start = (scene_top - tile_min_y) // cell_size
            cx_end = (scene_right - tile_min_x + cell_size - 1) // cell_size
            cy_end = (scene_bottom - tile_min_y + cell_size - 1) // cell_size

            for cy in range(cy_start, cy_end):
                for cx in range(cx_start, cx_end):
                    if cy < 0 or cy >= mask_height or cx < 0 or cx >= mask_width:
                        return True
                    if tile_mask[cy, cx] == 0:
                        return True
            return False

        # Search in expanding squares
        max_radius = 100
        for radius in range(max_radius + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if radius > 0 and abs(dx) != radius and abs(dy) != radius:
                        continue
                    test_x = center_x + dx
                    test_y = center_y + dy
                    if not check_overflow(test_x, test_y):
                        return (test_x, test_y, scale)
        return None


def compute_tile_centroid(tile_rects: list[tuple[int, int, int, int]]) -> tuple[float, float]:
    """Compute area-weighted centroid of tile rectangles.

    Args:
        tile_rects: List of (x, y, w, h) rectangles

    Returns:
        (centroid_x, centroid_y) in scene coordinates
    """
    optimizer = AlignmentOptimizer()
    return optimizer._compute_centroid(tile_rects)
