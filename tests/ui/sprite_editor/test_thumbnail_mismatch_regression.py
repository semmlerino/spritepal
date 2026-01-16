
import pytest
from unittest.mock import MagicMock, patch
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController

def test_thumbnail_generation_uses_stale_data():
    """
    Reproduction test for thumbnail mismatch.
    
    Scenario:
    1. Controller is at offset A with valid data for A.
    2. User switches to offset B.
    3. Controller updates current_offset to B, but hasn't received new data yet.
    4. Asset browser requests thumbnail for B.
    5. Controller generates thumbnail using STALE data from A because it thinks
       current_tile_data matches the current_offset.
    """
    # Setup controller with mocks
    mock_editing = MagicMock()
    controller = ROMWorkflowController(None, mock_editing)
    
    # Set initial state (Offset A)
    OFFSET_A = 0x1000
    DATA_A = b"\x00" * 32  # Dummy tile data
    
    controller.rom_path = "dummy.sfc"
    controller.rom_size = 0x10000  # Set ROM size to allow offsets
    controller.current_offset = OFFSET_A
    controller.current_tile_data = DATA_A
    controller.current_tile_offset = OFFSET_A
    controller.current_width = 8
    controller.current_height = 8
    
    # Mock _generate_library_thumbnail dependencies to avoid rendering
    # We just want to check which data path it takes
    
    # Trigger the bug: Switch to Offset B
    OFFSET_B = 0x2000
    
    # We mock request_manual_preview to prevent it from actually doing anything async
    # that might accidentally fix the state if we were running a full event loop.
    controller.preview_coordinator.request_manual_preview = MagicMock()
    
    # Act: Change offset
    controller.set_offset(OFFSET_B)
    
    # Verify intermediate state: Offset is B, but data is now CLEARED (Fix)
    assert controller.current_offset == OFFSET_B
    assert controller.current_tile_data is None, "Data should be CLEARED immediately after set_offset to prevent stale usage"
    assert controller.current_tile_offset == -1, "Tile offset should be invalidated immediately after set_offset"
    
    # Now verify that generating a thumbnail for B does NOT use the stale data
    # logic in _generate_library_thumbnail:
    # if self.current_tile_offset == offset and self.current_tile_data:
    #     data_to_render = self.current_tile_data
    
    use_cached_data = (controller.current_tile_offset == OFFSET_B) and (controller.current_tile_data is not None)
    
    assert use_cached_data is False, "Controller should NOT use stale data because data was cleared and offset invalidated"
    
    print("\n[SUCCESS] Regression test passed: Stale data cleared and invalidated on offset change.")

if __name__ == "__main__":
    try:
        test_thumbnail_generation_uses_stale_data()
    except AssertionError as e:
        print(f"\n[FAILURE] Assertion failed: {e}")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
