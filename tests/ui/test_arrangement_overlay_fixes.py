from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from core.apply_operation import ApplyOperation
from core.arrangement_persistence import ArrangementConfig
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition
from ui.row_arrangement.overlay_layer import OverlayLayer


def test_arrangement_config_persists_overlay_scale(tmp_path):
    """Regression test: ArrangementConfig must persist overlay_scale."""
    config_path = tmp_path / "test.json"

    # Create config with scale - simulating initialization
    config = ArrangementConfig(
        rom_hash="hash",
        rom_offset=0,
        sprite_name="test",
        grid_dimensions={},
        arrangement_order=[],
        groups=[],
        total_tiles=0,
        logical_width=16,
        overlay_path="img.png",
        overlay_x=10,
        overlay_y=20,
        overlay_opacity=0.8,
        overlay_visible=True,
        overlay_scale=2.5,  # This should now be supported
    )

    config.save(config_path)

    loaded = ArrangementConfig.load(config_path)
    assert hasattr(loaded, "overlay_scale"), "Loaded config missing overlay_scale"
    assert loaded.overlay_scale == 2.5, f"Scale not persisted. Got {getattr(loaded, 'overlay_scale', 'MISSING')}"


def test_apply_operation_replaces_partially_covered_tiles():
    """Regression test: ApplyOperation must completely REPLACE partially covered tiles (no composition)."""
    # Setup
    overlay = OverlayLayer()
    # Create 10x10 overlay
    img = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
    overlay._image = img
    overlay.set_scale(1.0)
    overlay.set_position(4.0, 4.0)  # Place at 4,4

    # Tile 0 at 0,0 (8x8). Overlap: (4,4) to (8,8) -> 4x4 area (bottom-right of tile).
    # Tile is NOT fully covered.

    grid_mapping = {(0, 0): (ArrangementType.TILE, "0,0")}
    tile_pos = TilePosition(0, 0)

    # Original tile is FILLED with index 1 (Gray)
    # This allows us to verify if original content persists
    original_tile = Image.new("L", (8, 8), 1)
    tiles = {tile_pos: original_tile}

    op = ApplyOperation(overlay=overlay, grid_mapping=grid_mapping, tiles=tiles, tile_width=8, tile_height=8)

    # Execute (force=True to bypass warnings)
    result = op.execute(force=True)

    # Expectation 1: Tile should be modified
    assert result.success
    assert tile_pos in result.modified_tiles, "Partially covered tile was skipped"

    # Expectation 2: Verify REPLACEMENT (untouched pixels should become transparent/0)
    modified = result.modified_tiles[tile_pos]

    # Pixel (0,0) is outside overlay -> should be 0 (Transparent), NOT 1 (Original)
    val_0_0 = modified.getpixel((0, 0))
    assert val_0_0 == 0, f"Untouched pixel was not cleared! Expected 0, got {val_0_0}"

    # Pixel (6,6) is inside overlay -> should be index > 0
    # (Red overlay)
    val_6_6 = modified.getpixel((6, 6))
    assert val_6_6 != 0, f"Covered pixel was not modified! Got {val_6_6}"


# --- Risk 1: Duplicate Tile Prevention Tests ---


def test_duplicate_tile_placement_rejected():
    """Risk 1: Same physical tile placed at multiple canvas positions should be rejected.

    When the same tile key (e.g., "1,2") is already placed on the canvas,
    attempting to place it at a different position should fail.
    This prevents ambiguous "last write wins" behavior during overlay apply.
    """
    from ui.row_arrangement.grid_arrangement_manager import GridArrangementManager

    manager = GridArrangementManager(total_rows=4, total_cols=4)

    # Place tile "1,2" at canvas position (0, 0)
    result1 = manager.set_item_at(0, 0, ArrangementType.TILE, "1,2")
    assert result1 is True, "First placement should succeed"

    # Verify tile is placed
    mapping = manager.get_grid_mapping()
    assert (0, 0) in mapping
    assert mapping[(0, 0)] == (ArrangementType.TILE, "1,2")

    # Try to place the SAME tile "1,2" at a DIFFERENT canvas position (1, 1)
    # This should be REJECTED because the tile is already placed elsewhere
    result2 = manager.set_item_at(1, 1, ArrangementType.TILE, "1,2")

    # CRITICAL CHECK: Second placement of same tile should be rejected
    assert result2 is False, (
        "Duplicate tile placement should be rejected! "
        "Tile '1,2' already placed at (0,0), cannot place at (1,1). "
        "This would cause ambiguous 'last write wins' during overlay apply."
    )

    # Verify only one instance exists in mapping
    mapping_after = manager.get_grid_mapping()
    tile_count = sum(1 for v in mapping_after.values() if v == (ArrangementType.TILE, "1,2"))
    assert tile_count == 1, f"Expected exactly 1 instance of tile '1,2', found {tile_count}"


def test_move_tile_allows_same_key():
    """Moving a tile (remove + place) should work even though key is 'duplicate'.

    When a tile is MOVED from (0,0) to (1,1), it's removed first then placed.
    This is NOT a duplicate scenario - it's the same tile being relocated.
    """
    from ui.row_arrangement.grid_arrangement_manager import GridArrangementManager

    manager = GridArrangementManager(total_rows=4, total_cols=4)

    # Place tile at (0, 0)
    manager.set_item_at(0, 0, ArrangementType.TILE, "1,2")

    # Move tile using move_grid_item (which removes old, adds new)
    manager.move_grid_item((0, 0), (1, 1))

    # Tile should now be at (1, 1), not at (0, 0)
    mapping = manager.get_grid_mapping()
    assert (0, 0) not in mapping, "Tile should no longer be at old position"
    assert (1, 1) in mapping, "Tile should be at new position"
    assert mapping[(1, 1)] == (ArrangementType.TILE, "1,2")


def test_replace_tile_at_same_position_allowed():
    """Placing a different tile at an occupied position should replace the existing one.

    This is valid use case - user wants to swap which tile is at position (0,0).
    """
    from ui.row_arrangement.grid_arrangement_manager import GridArrangementManager

    manager = GridArrangementManager(total_rows=4, total_cols=4)

    # Place tile "1,2" at (0, 0)
    manager.set_item_at(0, 0, ArrangementType.TILE, "1,2")

    # Place DIFFERENT tile "2,3" at same position (0, 0) - this should replace
    result = manager.set_item_at(0, 0, ArrangementType.TILE, "2,3")
    assert result is True, "Replacing tile at same position should succeed"

    # Verify replacement
    mapping = manager.get_grid_mapping()
    assert mapping[(0, 0)] == (ArrangementType.TILE, "2,3")


# --- Risk 3: Empty grid_mapping Tests ---


def test_apply_disabled_when_no_tiles_placed(qapp, tmp_path):
    """Risk 3: Apply button should be disabled when no tiles are placed on canvas.

    Even with a valid overlay loaded, applying to zero tiles is a no-op.
    The UI should prevent this by disabling the Apply button.
    """
    from unittest.mock import patch

    from PySide6.QtWidgets import QMessageBox

    from ui.grid_arrangement_dialog import GridArrangementDialog

    # Create a simple 16x16 sprite (2x2 tiles)
    sprite_img = Image.new("L", (16, 16), 128)
    sprite_path = tmp_path / "sprite.png"
    sprite_img.save(sprite_path)

    # Create an overlay image
    overlay_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
    overlay_path = tmp_path / "overlay.png"
    overlay_img.save(overlay_path)

    # Patch any message boxes that might appear
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
            # Create dialog
            dialog = GridArrangementDialog(str(sprite_path), tiles_per_row=2)
            dialog.show()

            # Clear any tiles from canvas (ensure empty grid_mapping)
            dialog.arrangement_manager.clear()

            # Import overlay
            dialog.overlay_layer.import_image(str(overlay_path))
            dialog.overlay_layer.set_visible(True)

            # Trigger overlay changed to update button state
            dialog._on_overlay_changed()

            # CRITICAL CHECK: Apply button should be DISABLED when no tiles placed
            assert hasattr(dialog, "apply_overlay_btn"), "Dialog should have apply button"
            is_enabled = dialog.apply_overlay_btn.isEnabled()

            # This test will FAIL until we implement the fix
            assert is_enabled is False, (
                "Apply button should be disabled when no tiles are placed on canvas! "
                "Currently enabled, which would result in 'Applied overlay to 0 tile(s)' no-op."
            )


def test_apply_enabled_when_tiles_placed(qapp, tmp_path):
    """Apply button should be enabled when tiles ARE placed and overlay is valid."""
    from unittest.mock import patch

    from PySide6.QtWidgets import QMessageBox

    from ui.grid_arrangement_dialog import GridArrangementDialog

    # Create a simple 16x16 sprite (2x2 tiles)
    sprite_img = Image.new("L", (16, 16), 128)
    sprite_path = tmp_path / "sprite.png"
    sprite_img.save(sprite_path)

    # Create an overlay image
    overlay_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
    overlay_path = tmp_path / "overlay.png"
    overlay_img.save(overlay_path)

    with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
            dialog = GridArrangementDialog(str(sprite_path), tiles_per_row=2)
            dialog.show()

            # Place a tile on canvas
            dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

            # Import overlay
            dialog.overlay_layer.import_image(str(overlay_path))
            dialog.overlay_layer.set_visible(True)

            # Trigger overlay changed to update button state
            dialog._on_overlay_changed()

            # Apply button should be ENABLED when tiles are placed and overlay is valid
            assert dialog.apply_overlay_btn.isEnabled() is True, (
                "Apply button should be enabled when tiles are placed and overlay is valid"
            )


# --- Risk 2: tiles_per_row Drift Tests ---


@patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
@patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
def test_tiles_per_row_preserved_in_result(mock_info, mock_warning, qapp, tmp_path, qtbot):
    """Risk 2: tiles_per_row must be preserved in ArrangementResult for correct byte offset calculation.

    The tiles_per_row value used to slice the source image must be the same value
    used for patching byte offsets. This test verifies the value is captured in the result.
    """
    from ui.grid_arrangement_dialog import GridArrangementDialog

    # Create a 32x16 sprite (4x2 = 8 tiles, tiles_per_row=4)
    sprite_img = Image.new("L", (32, 16), 128)
    sprite_path = tmp_path / "sprite.png"
    sprite_img.save(sprite_path)

    # Create overlay
    overlay_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
    overlay_path = tmp_path / "overlay.png"
    overlay_img.save(overlay_path)

    # Create dialog with specific tiles_per_row=4
    dialog = GridArrangementDialog(str(sprite_path), tiles_per_row=4)
    dialog.show()

    # Place a tile and apply overlay
    dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
    dialog.overlay_layer.import_image(str(overlay_path))
    dialog.overlay_layer.set_position(0, 0)
    dialog._apply_overlay()
    # Process events to handle the deferred QMessageBox
    qtbot.wait(10)

    # Close dialog
    dialog.accept()

    result = dialog.arrangement_result
    assert result is not None, "Result should exist after accept"

    # CRITICAL CHECK: tiles_per_row must be preserved in result
    assert hasattr(result, "tiles_per_row"), (
        "ArrangementResult must have tiles_per_row field! "
        "Without it, byte offset calculation may use wrong value if current_width changes."
    )
    assert result.tiles_per_row == 4, f"tiles_per_row should be 4 (from dialog init), got {result.tiles_per_row}"
