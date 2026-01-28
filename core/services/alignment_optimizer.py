"""Alignment optimizer for finding maximum scale without overflow.

Uses binary search on scale with position optimization to find the largest
scale where AI content fits entirely within tile coverage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.services.tile_sampling_service import TileSamplingService

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
    """Optimizer for finding optimal alignment that maximizes scale.

    Uses binary search on scale combined with position search to find
    the largest scale where AI content fits within tile coverage.
    Tiles are assumed to be contiguous (no internal gaps).
    """

    def __init__(self, min_scale: float = 0.01, max_scale: float = 1.0) -> None:
        """Initialize optimizer with scale bounds.

        Args:
            min_scale: Minimum allowed scale
            max_scale: Maximum allowed scale
        """
        self._min_scale = min_scale
        self._max_scale = max_scale
        self._service = TileSamplingService()

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
            initial_scale: Optional initial scale estimate

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

        # Compute tile coverage bounds
        tile_min_x = min(x for x, _, _, _ in tile_rects)
        tile_min_y = min(y for _, y, _, _ in tile_rects)
        tile_max_x = max(x + w for x, _, w, _ in tile_rects)
        tile_max_y = max(y + h for _, y, _, h in tile_rects)
        tile_width = tile_max_x - tile_min_x
        tile_height = tile_max_y - tile_min_y

        # Compute tile centroid for centering
        centroid_x, centroid_y = self._compute_centroid(tile_rects)

        # Initial scale estimate based on bounding box fit
        if initial_scale is None:
            scale_x = tile_width / ai_width
            scale_y = tile_height / ai_height
            initial_scale = min(scale_x, scale_y)
            initial_scale = max(self._min_scale, min(self._max_scale, initial_scale))

        def find_valid_position(scale: float) -> tuple[bool, int, int]:
            """Find a valid position for AI content at given scale.

            Returns (success, offset_x, offset_y).
            """
            scaled_width = ai_width * scale
            scaled_height = ai_height * scale

            # Center over tile centroid
            center_x = int(centroid_x - scaled_width / 2 - ai_left * scale)
            center_y = int(centroid_y - scaled_height / 2 - ai_top * scale)

            # Check centered position first
            has_overflow, _ = self._service.check_content_outside_tiles(ai_bbox, tile_rects, center_x, center_y, scale)
            if not has_overflow:
                return (True, center_x, center_y)

            # Search for valid position in expanding squares
            # Use larger search radius for non-rectangular tile coverage
            search_radius = max(tile_width, tile_height)

            for radius in range(1, search_radius + 1):
                # Check perimeter of square at this radius
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        # Only check perimeter points
                        if abs(dx) != radius and abs(dy) != radius:
                            continue

                        test_x = center_x + dx
                        test_y = center_y + dy

                        has_overflow, _ = self._service.check_content_outside_tiles(
                            ai_bbox, tile_rects, test_x, test_y, scale
                        )
                        if not has_overflow:
                            return (True, test_x, test_y)

            return (False, center_x, center_y)

        # Binary search for maximum scale
        # Start with very high upper bound - the binary search will find the true max
        low = self._min_scale
        high = min(initial_scale * 5.0, self._max_scale)  # Allow up to 5x initial estimate

        best_scale = self._min_scale
        best_offset_x = 0
        best_offset_y = 0
        iterations = 0

        # First check if initial scale fits
        fits, offset_x, offset_y = find_valid_position(initial_scale)
        if fits:
            best_scale = initial_scale
            best_offset_x = offset_x
            best_offset_y = offset_y
            low = initial_scale  # Search above initial
        else:
            high = initial_scale  # Initial doesn't fit, search below

        # Binary search iterations
        max_iterations = 30
        for i in range(max_iterations):
            iterations = i + 1
            mid = (low + high) / 2

            fits, offset_x, offset_y = find_valid_position(mid)
            if fits:
                best_scale = mid
                best_offset_x = offset_x
                best_offset_y = offset_y
                low = mid
            else:
                high = mid

            # Converged to sufficient precision
            if high - low < 0.001:
                break

        # Final verification
        fits, final_x, final_y = find_valid_position(best_scale)
        if fits:
            logger.debug(
                "Optimal alignment: scale=%.4f, offset=(%d, %d), iterations=%d",
                best_scale,
                final_x,
                final_y,
                iterations,
            )
            return AlignmentResult(
                offset_x=final_x,
                offset_y=final_y,
                scale=best_scale,
                success=True,
                iterations=iterations,
            )

        return AlignmentResult(
            offset_x=best_offset_x,
            offset_y=best_offset_y,
            scale=best_scale,
            success=False,
            iterations=iterations,
        )

    def _compute_centroid(self, tile_rects: list[tuple[int, int, int, int]]) -> tuple[float, float]:
        """Compute area-weighted centroid of tile rectangles."""
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


def compute_tile_centroid(
    tile_rects: list[tuple[int, int, int, int]],
) -> tuple[float, float]:
    """Compute area-weighted centroid of tile rectangles.

    Args:
        tile_rects: List of (x, y, w, h) rectangles

    Returns:
        (centroid_x, centroid_y) in scene coordinates
    """
    optimizer = AlignmentOptimizer()
    return optimizer._compute_centroid(tile_rects)
