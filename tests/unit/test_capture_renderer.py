
import pytest
from PIL import Image
from core.mesen_integration.click_extractor import CaptureResult, OAMEntry, OBSELConfig, TileData
from core.mesen_integration.capture_renderer import CaptureRenderer

def test_render_selection_crops_to_bbox():
    # Mock data for a sprite at (100, 100) with size 16x16
    # and another at (110, 110) with size 16x16
    # Total bbox should be (100, 100, 26, 26)
    
    # Create empty tile data (32 bytes of zeros)
    empty_tile = "0" * 64
    
    entries = [
        OAMEntry(
            id=0, x=100, y=100, tile=0, width=16, height=16,
            flip_h=False, flip_v=False, palette=0, 
            tiles=[
                TileData(0, 0, 0, 0, empty_tile),
                TileData(1, 0, 1, 0, empty_tile),
                TileData(2, 0, 0, 1, empty_tile),
                TileData(3, 0, 1, 1, empty_tile),
            ]
        ),
        OAMEntry(
            id=1, x=110, y=110, tile=4, width=16, height=16,
            flip_h=False, flip_v=False, palette=0,
            tiles=[
                TileData(4, 0, 0, 0, empty_tile),
                TileData(5, 0, 1, 0, empty_tile),
                TileData(6, 0, 0, 1, empty_tile),
                TileData(7, 0, 1, 1, empty_tile),
            ]
        )
    ]
    
    capture = CaptureResult(
        frame=100,
        visible_count=2,
        obsel=OBSELConfig(0, 0, 0, 0, 0, 0, 0),
        entries=entries,
        palettes={0: [0] * 16}
    )
    
    renderer = CaptureRenderer(capture)
    
    # Test render_composite (should be 256x224)
    img_composite = renderer.render_composite()
    assert img_composite.width == 256
    assert img_composite.height == 224
    
    # Test render_selection (should be 26x26)
    img_selection = renderer.render_selection()
    assert img_selection.width == 26
    assert img_selection.height == 26
    
def test_render_selection_empty_capture():
    capture = CaptureResult(
        frame=100,
        visible_count=0,
        obsel=OBSELConfig(0, 0, 0, 0, 0, 0, 0),
        entries=[],
        palettes={}
    )
    renderer = CaptureRenderer(capture)
    img = renderer.render_selection()
    assert img.width == 8
    assert img.height == 8
