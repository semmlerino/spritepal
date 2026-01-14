"""Tests for overlay canvas coordinate sampling.

Verifies that when a tile from source position (row, col) is placed at a DIFFERENT
canvas position (r, c), the overlay samples at the canvas position.
"""

from __future__ import annotations

import pytest
from PIL import Image

from core.apply_operation import ApplyOperation
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition
from ui.row_arrangement.overlay_layer import OverlayLayer

pytestmark = [
    pytest.mark.headless,
    pytest.mark.unit,
]


def create_positioned_overlay(tmp_path, x: float, y: float, width: int, height: int):
    """Create an overlay positioned at specific pixel coordinates."""
    img_path = tmp_path / "positioned_overlay.png"
    img = Image.new("RGBA", (width, height), color=(255, 0, 0, 255))
    img.save(img_path)

    overlay = OverlayLayer()
    overlay.import_image(str(img_path))
    overlay.set_position(x, y)
    return overlay


class TestCanvasPositionSampling:
    """Tests verifying canvas-position based sampling."""

    def test_tile_at_different_canvas_position_receives_overlay(self, tmp_path):
        """Tile placed at different canvas position should get overlay applied based on that position.

        Scenario:
        - Source tile at position (0, 0)
        - Placed on canvas at position (0, 4) (column 4, not column 0!)
        - Overlay covers canvas columns 3-4 (pixels 24-40 at 8px/tile)
        - Expected: Tile should be modified because overlay covers canvas (0, 4)
        """
        tiles = {}
        for r in range(4):
            for c in range(4):
                tiles[TilePosition(r, c)] = Image.new("L", (8, 8), color=0)

        # Place Tile (0,0) at canvas position (0, 4)
        grid_mapping = {
            (0, 4): (ArrangementType.TILE, "0,0"),
        }

        # Overlay at canvas column 4 (pixel 32)
        overlay = create_positioned_overlay(
            tmp_path,
            x=32,
            y=0,
            width=8,
            height=8,
        )

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
        )

        result = operation.execute(force=True)

        assert result.success is True
        assert TilePosition(0, 0) in result.modified_tiles

    def test_overlay_at_source_position_but_tile_elsewhere_no_match(self, tmp_path):
        """Overlay at source position should NOT match tile moved to different canvas position.
        """
        tiles = {TilePosition(0, 0): Image.new("L", (8, 8), color=0)}

        # Place tile at canvas (0, 4), but overlay covers (0, 0)
        grid_mapping = {
            (0, 4): (ArrangementType.TILE, "0,0"),
        }

        # Overlay at canvas (0, 0) - pixels 0-8
        overlay = create_positioned_overlay(tmp_path, x=0, y=0, width=8, height=8)

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
        )

        result = operation.execute(force=True)

        assert TilePosition(0, 0) not in result.modified_tiles
