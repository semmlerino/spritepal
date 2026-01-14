"""
Audit tests for Sprite Editor -> Arrangement -> Apply Overlay workflow.
Reproduces:
1. Overlay position truncation (float vs int)
2. ArrangementBridge compaction (ignoring gaps)
"""

from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QMessageBox

from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition
from ui.sprite_editor.services.arrangement_bridge import ArrangementBridge


@pytest.fixture
def test_sprite(tmp_path):
    """Create a 16x8 sprite (2 tiles). Tile 0 is black, Tile 1 is dark gray."""
    img = Image.new("L", (16, 8), 0)
    img.putpixel((8, 0), 64) # Start of second tile
    path = tmp_path / "test_sprite.png"
    img.save(path)
    return str(path)

@pytest.fixture
def gradient_overlay(tmp_path):
    """Create a 16x8 gradient overlay."""
    img = Image.new("RGBA", (16, 8), (0, 0, 0, 255))
    for x in range(16):
        for y in range(8):
            img.putpixel((x, y), (x * 10, y * 10, 0, 255))
    path = tmp_path / "gradient_overlay.png"
    img.save(path)
    return str(path)

def test_overlay_position_precision_loss(qtbot, test_sprite, gradient_overlay):
    """
    Reproduce Bug 1: OverlayGraphicsItem truncates position to int,
    causing misalignment between what the user sees and what is sampled.
    """
    dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
    qtbot.addWidget(dialog)
    dialog.show()

    # Place tile at (0, 0)
    dialog.arrangement_manager.add_tile(TilePosition(0, 0))
    
    # Import overlay
    dialog.overlay_layer.import_image(gradient_overlay)
    
    # Ensure overlay_item exists
    dialog._update_arrangement_canvas()
    assert dialog.overlay_item is not None
    
    # Set a fractional position on the graphics item (simulating user drag)
    # Note: QGraphicsItem uses floats for position
    float_pos = QPointF(5.7, 3.2)
    dialog.overlay_item.setPos(float_pos)
    
    # Force sync back to layer (normally triggered by itemChange)
    # We simulate the itemChange call because qtbot might not trigger it instantly
    dialog.overlay_item.itemChange(dialog.overlay_item.GraphicsItemChange.ItemPositionChange, float_pos)
    
    # CHECK: Did the layer preserve the precision?
    # CURRENTLY it uses int(), so it will be (5, 3)
    assert dialog.overlay_layer.x == 5.7, f"Layer X should be 5.7, but got {dialog.overlay_layer.x}"
    assert dialog.overlay_layer.y == 3.2, f"Layer Y should be 3.2, but got {dialog.overlay_layer.y}"

def test_arrangement_bridge_compaction_with_gaps(test_sprite):
    """
    Reproduce Bug 2: ArrangementBridge compacts tiles, ignoring gaps
    placed by the user on the arrangement canvas.
    """
    dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
    # We don't need qtbot or show() for this model-level test
    
    # Place Tile 0 at (0, 0) and Tile 1 at (0, 2) -> Gap at (0, 1)
    # Target width is 16 by default.
    dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
    dialog.arrangement_manager.set_item_at(0, 2, ArrangementType.TILE, "0,1")
    
    # Check grid mapping
    mapping = dialog.arrangement_manager.get_grid_mapping()
    assert (0, 0) in mapping
    assert (0, 2) in mapping
    assert (0, 1) not in mapping
    
    # Create Bridge
    # This is what ROMWorkflowController does when Apply is clicked
    result = dialog.get_arrangement_result()
    assert result is not None
    bridge = result.bridge
    
    # Check logical size
    # If gaps are preserved, it should be at least 3 tiles wide (24 pixels)
    # If compacted, it will be 2 tiles wide (16 pixels)
    width_px, height_px = bridge.logical_size
    
    # CURRENTLY: bridge._build_mapping uses manager.get_arrangement_order()
    # which skips gaps.
    assert width_px >= 24, f"Bridge logical width should be at least 24px to accommodate gap, but got {width_px}px"

def test_apply_overlay_samples_canvas_pos(qtbot, test_sprite, gradient_overlay):
    """
    Verify that ApplyOverlay correctly samples based on CANVAS positions,
    not original source positions.
    """
    dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
    qtbot.addWidget(dialog)
    dialog.show()

    # Place Tile 0 at (0, 2) - away from origin
    dialog.arrangement_manager.set_item_at(0, 2, ArrangementType.TILE, "0,0")
    
    # Import overlay at (0, 0)
    dialog.overlay_layer.import_image(gradient_overlay)
    dialog.overlay_layer.set_position(0, 0)
    
    # Apply overlay
    # Tile 0 is at (0, 2) on canvas, so tile_x = 16, tile_y = 0.
    # It should sample from overlay at (16, 0).
    # BUT gradient_overlay is only 16x8! So it should NOT cover Tile 0.
    
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
            dialog._apply_overlay()
            
    # If it sampled correctly, it should find that Tile 0 is NOT covered.
    # (Since overlay ends at x=16 and tile starts at x=16)
    # Wait, 16x8 overlay covers x=0..15. Tile at x=16 starts at 16.
    
    assert TilePosition(0, 0) not in dialog.apply_result.modified_tiles
    
    # Now move Tile 0 back to (0, 0)
    dialog.arrangement_manager.clear()
    dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
    
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
            dialog._apply_overlay()
            
    assert TilePosition(0, 0) in dialog.apply_result.modified_tiles
    
    # Now move OVERLAY to (16, 0) and Tile 0 to (0, 2)
    # They should align again.
    dialog.arrangement_manager.clear()
    dialog.arrangement_manager.set_item_at(0, 2, ArrangementType.TILE, "0,0")
    dialog.overlay_layer.set_position(16, 0)

    # We need a bigger overlay for this test or just move it.
    # sample_region uses: rel_x = tile_x - self._x
    # tile_x = 16, self._x = 16 -> rel_x = 0.
    # It should sample from (0, 0) of the overlay.
    
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
            dialog._apply_overlay()
            
    assert TilePosition(0, 0) in dialog.apply_result.modified_tiles
    # Sampled pixel at (0,0) of overlay is (0,0,0) -> index 0.
    modified_img = dialog.apply_result.modified_tiles[TilePosition(0, 0)]
    assert modified_img.getpixel((0, 0)) == 0
