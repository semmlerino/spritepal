"""Tests for the overlay canvas coordinate bug.

Bug: When a tile from source position (row, col) is placed at a DIFFERENT
canvas position (r, c), the overlay should sample at canvas position, not source.

Currently, with use_source_positions=True (default), the code samples at source
coordinates, causing 0 tiles to be modified when the overlay only covers the
canvas position.
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


def create_positioned_overlay(tmp_path, x: int, y: int, width: int, height: int):
    """Create an overlay positioned at specific pixel coordinates."""
    img_path = tmp_path / "positioned_overlay.png"
    img = Image.new("RGBA", (width, height), color=(255, 0, 0, 255))
    img.save(img_path)

    overlay = OverlayLayer()
    overlay.import_image(str(img_path))
    overlay.set_position(x, y)
    return overlay


class TestCanvasVsSourceCoordinateBug:
    """Tests demonstrating the canvas vs source coordinate mismatch bug."""

    def test_tile_at_different_canvas_position_receives_overlay(self, tmp_path):
        """BUG: Tile placed at different canvas position should still get overlay applied.

        Scenario:
        - Source tile at position (0, 0)
        - Placed on canvas at position (0, 4) (column 4, not column 0!)
        - Overlay covers canvas columns 3-4 (pixels 24-40 at 8px/tile)
        - Expected: Tile should be modified because overlay covers canvas (0, 4)
        - Actual BUG: 0 tiles modified because code samples at source (0, 0)
        """
        # Create tiles - we have a 4x4 grid of source tiles
        tiles = {}
        for r in range(4):
            for c in range(4):
                tiles[TilePosition(r, c)] = Image.new("L", (8, 8), color=0)

        # Place ONLY tile (0,0) at canvas position (0, 4) - shifted right by 4 columns
        # This is the key: source position != canvas position
        grid_mapping = {
            (0, 4): (ArrangementType.TILE, "0,0"),  # Source tile (0,0) at canvas (0,4)
        }

        # Create overlay that covers canvas position (0, 4)
        # At 8 pixels per tile, canvas column 4 = pixels 32-40
        overlay = create_positioned_overlay(
            tmp_path,
            x=32,  # Start at pixel 32 (column 4)
            y=0,  # Row 0
            width=8,
            height=8,
        )

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
            use_source_positions=True,  # Default - causes the bug
        )

        # Execute with force=True to bypass warnings
        result = operation.execute(force=True)

        # BUG: This assertion FAILS because code samples at source (0,0) not canvas (0,4)
        # The overlay is at canvas column 4, but code checks source column 0
        assert result.success is True
        assert TilePosition(0, 0) in result.modified_tiles, (
            "Tile (0,0) placed at canvas (0,4) should be modified by overlay at canvas (0,4). "
            "BUG: The code samples at source position (0,0) instead of canvas position (0,4), "
            "so the overlay (at pixels 32-40) doesn't cover source position (pixels 0-8)."
        )

    def test_overlay_at_source_position_but_tile_elsewhere_no_match(self, tmp_path):
        """Demonstrates the bug in reverse: overlay at source position, tile elsewhere.

        Scenario:
        - Source tile at position (0, 0) → source pixels (0-8, 0-8)
        - Placed on canvas at position (0, 4) → canvas pixels (32-40, 0-8)
        - Overlay covers source position (0, 0) at pixels (0-8, 0-8)
        - Expected: Tile should NOT be modified (overlay doesn't cover canvas position)
        - Actual BUG: Tile IS modified because code samples at source position
        """
        tiles = {TilePosition(0, 0): Image.new("L", (8, 8), color=0)}

        # Place tile at canvas (0, 4), but overlay covers (0, 0)
        grid_mapping = {
            (0, 4): (ArrangementType.TILE, "0,0"),
        }

        # Overlay at source position (0, 0) - pixels 0-8
        overlay = create_positioned_overlay(tmp_path, x=0, y=0, width=8, height=8)

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
            use_source_positions=True,
        )

        result = operation.execute(force=True)

        # With the bug, this PASSES because code wrongly samples at source position
        # After fix, this should change: tile at canvas (0,4) shouldn't match overlay at (0,0)
        # For now, this test documents the buggy behavior
        if TilePosition(0, 0) in result.modified_tiles:
            pytest.fail(
                "BUG CONFIRMED: Tile at canvas (0,4) was modified by overlay at source (0,0). "
                "This is wrong - overlay should be matched against canvas position, not source."
            )

    def test_canvas_position_sampling_works_correctly(self, tmp_path):
        """Verify that use_source_positions=False works correctly.

        This test should pass even before the fix, confirming that canvas
        coordinate sampling works when explicitly enabled.
        """
        tiles = {TilePosition(0, 0): Image.new("L", (8, 8), color=0)}

        # Place tile at canvas (0, 4)
        grid_mapping = {
            (0, 4): (ArrangementType.TILE, "0,0"),
        }

        # Overlay covers canvas position (0, 4)
        overlay = create_positioned_overlay(tmp_path, x=32, y=0, width=8, height=8)

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
            use_source_positions=False,  # Use canvas positions
        )

        result = operation.execute(force=True)

        # This should work correctly
        assert result.success is True
        assert TilePosition(0, 0) in result.modified_tiles, (
            "With use_source_positions=False, tile should be modified based on canvas position"
        )


class TestArrangementBridgeLogicalWidth:
    """Tests for ArrangementBridge logical width handling."""

    def test_bridge_uses_provided_logical_width(self):
        """ArrangementBridge should use provided logical_width, not recalculate.

        Bug: When user sets tiles_per_row=16 but only arranges 5 tiles,
        the bridge recalculates width as min(16, 5) = 5, scrambling the display.
        """
        # Import here to avoid circular import at module level
        from unittest.mock import MagicMock

        from ui.row_arrangement.grid_arrangement_manager import GridArrangementManager
        from ui.sprite_editor.services.arrangement_bridge import ArrangementBridge

        # Create mock manager with 5 arranged tiles
        manager = MagicMock(spec=GridArrangementManager)
        manager.get_arrangement_order.return_value = [
            (ArrangementType.TILE, "0,0"),
            (ArrangementType.TILE, "0,1"),
            (ArrangementType.TILE, "0,2"),
            (ArrangementType.TILE, "0,3"),
            (ArrangementType.TILE, "0,4"),
        ]
        manager.get_groups.return_value = {}

        # Create mock processor
        processor = MagicMock()
        processor.grid_cols = 16
        processor.grid_rows = 5

        # Create bridge WITH logical_width=16 (simulating dialog passing the value)
        bridge = ArrangementBridge(manager, processor, logical_width=16)

        # After fix, should use provided logical_width=16
        # Note: accessing private _logical_width since there's no public property yet
        actual_width = bridge._logical_width
        assert actual_width == 16, f"Bridge should use provided logical_width=16, but got {actual_width}."
