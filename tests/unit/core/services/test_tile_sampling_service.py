"""Tests for TileSamplingService.

Focuses on the check_content_outside_tiles method which detects
AI frame content that extends beyond game sprite tile boundaries.
"""

from __future__ import annotations

import pytest

from core.services.tile_sampling_service import TileSamplingService


class TestCheckContentOutsideTiles:
    """Tests for check_content_outside_tiles method."""

    @pytest.fixture
    def service(self) -> TileSamplingService:
        """Create a TileSamplingService instance."""
        return TileSamplingService()

    def test_content_fully_inside_tiles_returns_no_overflow(self, service: TileSamplingService) -> None:
        """Content completely within tile area should return no overflow."""
        # Content bbox: 10x10 at origin (in source coordinates)
        content_bbox = (0, 0, 10, 10)
        # Tile union: 20x20 at origin (in scene coordinates)
        tile_union = (0, 0, 20, 20)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is False
        assert overflow_rects == []

    def test_content_fully_inside_with_offset(self, service: TileSamplingService) -> None:
        """Content offset but still within tile area should return no overflow."""
        content_bbox = (0, 0, 10, 10)
        tile_union = (5, 5, 20, 20)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=5,  # Places content at (5,5) to (15,15) in scene
            offset_y=5,
            scale=1.0,
        )

        assert has_overflow is False
        assert overflow_rects == []

    def test_none_content_bbox_returns_no_overflow(self, service: TileSamplingService) -> None:
        """Fully transparent image (None bbox) should return no overflow."""
        tile_union = (0, 0, 20, 20)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=None,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is False
        assert overflow_rects == []

    def test_content_extends_past_top_edge(self, service: TileSamplingService) -> None:
        """Content extending past top edge should return top overflow rect."""
        content_bbox = (0, 0, 20, 20)  # 20x20 in source
        tile_union = (0, 10, 20, 30)  # Tiles start at y=10

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,  # Content at (0,0) to (20,20), tiles at (0,10) to (20,30)
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) == 1
        # Top overflow: x=0, y=0, w=20, h=10
        assert overflow_rects[0] == (0, 0, 20, 10)

    def test_content_extends_past_bottom_edge(self, service: TileSamplingService) -> None:
        """Content extending past bottom edge should return bottom overflow rect."""
        content_bbox = (0, 0, 20, 30)  # 20x30 in source
        tile_union = (0, 0, 20, 20)  # Tiles end at y=20

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) == 1
        # Bottom overflow: x=0, y=20, w=20, h=10
        assert overflow_rects[0] == (0, 20, 20, 10)

    def test_content_extends_past_left_edge(self, service: TileSamplingService) -> None:
        """Content extending past left edge should return left overflow rect."""
        content_bbox = (0, 0, 20, 20)  # 20x20 in source
        tile_union = (10, 0, 30, 20)  # Tiles start at x=10

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) == 1
        # Left overflow: x=0, y=0, w=10, h=20
        assert overflow_rects[0] == (0, 0, 10, 20)

    def test_content_extends_past_right_edge(self, service: TileSamplingService) -> None:
        """Content extending past right edge should return right overflow rect."""
        content_bbox = (0, 0, 30, 20)  # 30x20 in source
        tile_union = (0, 0, 20, 20)  # Tiles end at x=20

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) == 1
        # Right overflow: x=20, y=0, w=10, h=20
        assert overflow_rects[0] == (20, 0, 10, 20)

    def test_content_extends_multiple_edges(self, service: TileSamplingService) -> None:
        """Content extending past multiple edges should return multiple overflow rects."""
        content_bbox = (0, 0, 40, 40)  # 40x40 in source
        tile_union = (10, 10, 30, 30)  # 20x20 tile area in center

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        # Should have 4 overflow regions: top, bottom, left, right
        assert len(overflow_rects) == 4

        # Verify total overflow area coverage
        # Top: full width, height 10
        # Bottom: full width, height 10
        # Left: center height only (20), width 10
        # Right: center height only (20), width 10
        rects_by_y = sorted(overflow_rects, key=lambda r: r[1])
        top_rect = rects_by_y[0]
        assert top_rect[1] == 0  # Top starts at y=0
        assert top_rect[3] == 10  # Height 10

    def test_scaled_content_overflow(self, service: TileSamplingService) -> None:
        """Scaled content should have bounds properly transformed."""
        content_bbox = (0, 0, 10, 10)  # 10x10 in source
        tile_union = (0, 0, 16, 16)  # 16x16 tile area

        # At scale 2.0, content becomes 20x20 in scene coords
        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,
            scale=2.0,
        )

        assert has_overflow is True
        # Content is 20x20 but tiles are only 16x16
        # Should have bottom and right overflow
        assert len(overflow_rects) == 2

    def test_scaled_content_fits_within_tiles(self, service: TileSamplingService) -> None:
        """Scaled-down content that fits should return no overflow."""
        content_bbox = (0, 0, 20, 20)  # 20x20 in source
        tile_union = (0, 0, 16, 16)  # 16x16 tile area

        # At scale 0.5, content becomes 10x10 in scene coords
        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,
            scale=0.5,
        )

        assert has_overflow is False
        assert overflow_rects == []

    def test_offset_content_overflow(self, service: TileSamplingService) -> None:
        """Offset content should be checked at correct scene position."""
        content_bbox = (0, 0, 10, 10)  # 10x10 in source
        tile_union = (0, 0, 10, 10)  # 10x10 tile area at origin

        # Offset by 5,5 places content at (5,5) to (15,15)
        # Should overflow past right and bottom edges
        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=5,
            offset_y=5,
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) == 2  # Right and bottom overflow

    def test_content_bbox_not_at_origin(self, service: TileSamplingService) -> None:
        """Content bbox with non-zero origin should be handled correctly."""
        # Content has transparent border - actual content at (5,5) to (15,15)
        content_bbox = (5, 5, 15, 15)  # 10x10 content not at origin
        tile_union = (0, 0, 20, 20)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        # Content at (5,5) to (15,15) fits within (0,0) to (20,20)
        assert has_overflow is False
        assert overflow_rects == []

    def test_empty_tile_union(self, service: TileSamplingService) -> None:
        """Empty tile union (all zeros) should detect any content as overflow."""
        content_bbox = (0, 0, 10, 10)
        tile_union = (0, 0, 0, 0)  # No tiles

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_union_rect=tile_union,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
