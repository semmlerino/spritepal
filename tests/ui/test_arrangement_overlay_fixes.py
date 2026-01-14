from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

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
        overlay_scale=2.5  # This should now be supported
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
    overlay.set_position(4.0, 4.0) # Place at 4,4
    
    # Tile 0 at 0,0 (8x8). Overlap: (4,4) to (8,8) -> 4x4 area (bottom-right of tile).
    # Tile is NOT fully covered.
    
    grid_mapping = {(0, 0): (ArrangementType.TILE, "0,0")}
    tile_pos = TilePosition(0, 0)
    
    # Original tile is FILLED with index 1 (Gray)
    # This allows us to verify if original content persists
    original_tile = Image.new("L", (8, 8), 1) 
    tiles = {tile_pos: original_tile}
    
    op = ApplyOperation(
        overlay=overlay,
        grid_mapping=grid_mapping,
        tiles=tiles,
        tile_width=8,
        tile_height=8
    )
    
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
