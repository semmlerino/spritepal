"""Tests for TileSamplingService.

Focuses on the check_content_outside_tiles method which detects
AI frame content that extends beyond game sprite tile boundaries.
"""

from __future__ import annotations

import pytest

from core.services.tile_sampling_service import TileSamplingService


def make_tile_grid(x: int, y: int, width: int, height: int, tile_size: int = 8) -> list[tuple[int, int, int, int]]:
    """Create a grid of tiles covering the specified area.

    Args:
        x, y: Top-left corner of the tile area.
        width, height: Dimensions of the area to cover.
        tile_size: Size of each tile (default 8x8).

    Returns:
        List of (x, y, w, h) tuples for each tile.
    """
    tiles = []
    for ty in range(y, y + height, tile_size):
        for tx in range(x, x + width, tile_size):
            tiles.append((tx, ty, tile_size, tile_size))
    return tiles


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
        # Tiles covering 24x24 at origin (3x3 grid of 8x8 tiles)
        tiles = make_tile_grid(0, 0, 24, 24)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is False
        assert overflow_rects == []

    def test_content_fully_inside_with_offset(self, service: TileSamplingService) -> None:
        """Content offset but still within tile area should return no overflow."""
        content_bbox = (0, 0, 8, 8)
        # Tiles at (8, 8) to (24, 24) - 2x2 grid of 8x8 tiles
        tiles = make_tile_grid(8, 8, 16, 16)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=8,  # Places content at (8,8) to (16,16) in scene
            offset_y=8,
            scale=1.0,
        )

        assert has_overflow is False
        assert overflow_rects == []

    def test_none_content_bbox_returns_no_overflow(self, service: TileSamplingService) -> None:
        """Fully transparent image (None bbox) should return no overflow."""
        tiles = make_tile_grid(0, 0, 24, 24)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=None,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is False
        assert overflow_rects == []

    def test_content_extends_past_top_edge(self, service: TileSamplingService) -> None:
        """Content extending past top edge should return top overflow rect."""
        content_bbox = (0, 0, 16, 24)  # 16x24 in source
        # Tiles start at y=8 (2x2 grid)
        tiles = make_tile_grid(0, 8, 16, 16)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,  # Content at (0,0) to (16,24), tiles at (0,8) to (16,24)
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) >= 1
        # Should have overflow in the top area (y < 8)
        total_overflow_area = sum(r[2] * r[3] for r in overflow_rects)
        assert total_overflow_area == 16 * 8  # 16 wide, 8 tall top strip

    def test_content_extends_past_bottom_edge(self, service: TileSamplingService) -> None:
        """Content extending past bottom edge should return bottom overflow rect."""
        content_bbox = (0, 0, 16, 24)  # 16x24 in source
        # Tiles at origin, 16x16
        tiles = make_tile_grid(0, 0, 16, 16)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) >= 1
        # Should have overflow in the bottom area (y >= 16)
        total_overflow_area = sum(r[2] * r[3] for r in overflow_rects)
        assert total_overflow_area == 16 * 8  # 16 wide, 8 tall bottom strip

    def test_content_extends_past_left_edge(self, service: TileSamplingService) -> None:
        """Content extending past left edge should return left overflow rect."""
        content_bbox = (0, 0, 24, 16)  # 24x16 in source
        # Tiles start at x=8
        tiles = make_tile_grid(8, 0, 16, 16)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) >= 1
        # Should have overflow in the left area (x < 8)
        total_overflow_area = sum(r[2] * r[3] for r in overflow_rects)
        assert total_overflow_area == 8 * 16  # 8 wide, 16 tall left strip

    def test_content_extends_past_right_edge(self, service: TileSamplingService) -> None:
        """Content extending past right edge should return right overflow rect."""
        content_bbox = (0, 0, 24, 16)  # 24x16 in source
        # Tiles at origin, 16x16
        tiles = make_tile_grid(0, 0, 16, 16)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) >= 1
        # Should have overflow in the right area (x >= 16)
        total_overflow_area = sum(r[2] * r[3] for r in overflow_rects)
        assert total_overflow_area == 8 * 16  # 8 wide, 16 tall right strip

    def test_content_extends_multiple_edges(self, service: TileSamplingService) -> None:
        """Content extending past multiple edges should return multiple overflow rects."""
        content_bbox = (0, 0, 40, 40)  # 40x40 in source
        # Tiles in center: 16x16 at (8,8)
        tiles = make_tile_grid(8, 8, 16, 16)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        # Should have overflow on all sides
        assert len(overflow_rects) >= 4

    def test_scaled_content_overflow(self, service: TileSamplingService) -> None:
        """Scaled content should have bounds properly transformed."""
        content_bbox = (0, 0, 8, 8)  # 8x8 in source
        # 16x16 tile area
        tiles = make_tile_grid(0, 0, 16, 16)

        # At scale 2.5, content becomes 20x20 in scene coords
        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=2.5,
        )

        assert has_overflow is True
        # Content is 20x20 but tiles are only 16x16
        assert len(overflow_rects) >= 1

    def test_scaled_content_fits_within_tiles(self, service: TileSamplingService) -> None:
        """Scaled-down content that fits should return no overflow."""
        content_bbox = (0, 0, 32, 32)  # 32x32 in source
        # 16x16 tile area
        tiles = make_tile_grid(0, 0, 16, 16)

        # At scale 0.5, content becomes 16x16 in scene coords - exactly fits
        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=0.5,
        )

        assert has_overflow is False
        assert overflow_rects == []

    def test_offset_content_overflow(self, service: TileSamplingService) -> None:
        """Offset content should be checked at correct scene position."""
        content_bbox = (0, 0, 16, 16)  # 16x16 in source
        # Tiles at origin, 16x16
        tiles = make_tile_grid(0, 0, 16, 16)

        # Offset by 8,8 places content at (8,8) to (24,24)
        # Should overflow past right and bottom edges
        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=8,
            offset_y=8,
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) >= 1

    def test_content_bbox_not_at_origin(self, service: TileSamplingService) -> None:
        """Content bbox with non-zero origin should be handled correctly."""
        # Content has transparent border - actual content at (8,8) to (16,16)
        content_bbox = (8, 8, 16, 16)  # 8x8 content not at origin
        # Tiles covering 24x24 at origin
        tiles = make_tile_grid(0, 0, 24, 24)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        # Content at (8,8) to (16,16) fits within (0,0) to (24,24)
        assert has_overflow is False
        assert overflow_rects == []

    def test_empty_tile_list(self, service: TileSamplingService) -> None:
        """Empty tile list should detect any content as overflow."""
        content_bbox = (0, 0, 16, 16)
        tiles: list[tuple[int, int, int, int]] = []  # No tiles

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        assert len(overflow_rects) == 1
        # Should return the entire content as overflow
        assert overflow_rects[0] == (0, 0, 16, 16)

    def test_non_rectangular_tiles_detects_gap(self, service: TileSamplingService) -> None:
        """Non-rectangular tile arrangement should detect content in gaps.

        This tests the case like King Dedede's sprite where there are
        coattail tiles that stick out horizontally, leaving empty areas
        in the union bounding box that don't actually have tiles.

        Tile arrangement (X = tile, . = no tile):
          0  8  16 24
        0 XX XX
        8 XX XX
        16 .. XX  <- Gap on left at (0,16)
        """
        # Create non-rectangular tile arrangement
        tiles = [
            # Top-left 2x2 (16x16)
            (0, 0, 8, 8),
            (8, 0, 8, 8),
            (0, 8, 8, 8),
            (8, 8, 8, 8),
            # Bottom tiles (only right side - coattail pattern)
            (8, 16, 8, 8),
            (16, 16, 8, 8),
        ]

        # Content covers entire union bounding box (0,0) to (24,24)
        content_bbox = (0, 0, 24, 24)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        # Should detect the gap at (0,16) - (8,24) as overflow
        # Plus any area outside the actual tiles at right (16,0) to (24,16)
        # Plus bottom-right area (24, 16) to (24, 24) if content extends there

        # Find overflow in the gap area (bottom-left)
        gap_overflow = [r for r in overflow_rects if r[0] == 0 and r[1] == 16]
        assert len(gap_overflow) >= 1
        # The gap should be at least 8x8
        gap_rect = gap_overflow[0]
        assert gap_rect[2] == 8  # width
        assert gap_rect[3] == 8  # height

    def test_l_shaped_tiles(self, service: TileSamplingService) -> None:
        """L-shaped tile arrangement should detect content in the corner gap."""
        # L-shaped tiles:
        #   0  8  16
        # 0 XX XX XX
        # 8 XX .. ..
        # 16 XX .. ..
        tiles = [
            # Top row
            (0, 0, 8, 8),
            (8, 0, 8, 8),
            (16, 0, 8, 8),
            # Left column (below top)
            (0, 8, 8, 8),
            (0, 16, 8, 8),
        ]

        # Content covers 24x24
        content_bbox = (0, 0, 24, 24)

        has_overflow, overflow_rects = service.check_content_outside_tiles(
            content_bbox=content_bbox,
            tile_rects=tiles,
            offset_x=0,
            offset_y=0,
            scale=1.0,
        )

        assert has_overflow is True
        # Should detect the corner gap (8,8) to (24,24)
        total_overflow_area = sum(r[2] * r[3] for r in overflow_rects)
        # Gap is 16x16 = 256 pixels
        assert total_overflow_area == 16 * 16
