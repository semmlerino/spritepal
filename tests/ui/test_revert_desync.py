
import pytest
from unittest.mock import MagicMock, patch
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController

def test_revert_to_original_uses_dirty_data_repro():
    """
    Reproduction test for UI Desync Bug:
    revert_to_original() uses self.current_tile_data which might be dirty (e.g. from Arrangement),
    instead of forcing a fresh reload from the ROM via set_offset/preview_coordinator.
    """
    # Setup
    mock_editing = MagicMock()
    # Mock has_unsaved_changes to False so we don't get blocked by dialogs
    mock_editing.has_unsaved_changes.return_value = False
    
    controller = ROMWorkflowController(None, mock_editing)
    
    # Simulate loaded state
    controller.rom_path = "dummy.sfc"
    controller.current_offset = 0x1000
    controller.state = "edit"
    
    # Mock the preview coordinator so we can assert if it was called
    controller.preview_coordinator = MagicMock()
    
    # Mock current_tile_data with some "dirty" data (simulating an applied arrangement)
    controller.current_tile_data = b'\xFF' * 32
    
    # Mock open_in_editor to verify it is called (current behavior)
    with patch.object(controller, 'open_in_editor') as mock_open:
        # Action: Click "Revert to Original"
        controller.revert_to_original()
        
        # Current Behavior (Bug): It calls open_in_editor(), which uses the dirty current_tile_data
        mock_open.assert_called_once()
        
        # Expected Behavior (Fix): It should call set_offset or request_manual_preview to reload from ROM
        # This assertion FAILS currently because it's not called
        assert controller.preview_coordinator.request_manual_preview.called, \
            "revert_to_original did not request fresh data from ROM via preview_coordinator"

