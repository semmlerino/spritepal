import pytest
from unittest.mock import MagicMock
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController
from ui.sprite_editor.controllers.editing_controller import EditingController

def test_palette_sources_not_duplicated_on_reopen(qtbot):
    """
    Test that ROM palette sources are cleared before registering new ones,
    preventing duplication when re-opening a sprite.
    """
    # Use real controller for state tracking
    editing_controller = EditingController()
    
    controller = ROMWorkflowController(None, editing_controller)
    controller.rom_path = "dummy.sfc"
    controller.current_tile_data = b'\x00' * 32
    controller.current_sprite_name = "test_sprite"
    
    # Mock ROM extractor to provide some palettes
    mock_extractor = MagicMock()
    mock_extractor.read_rom_header.return_value = MagicMock()
    mock_extractor._find_game_configuration.return_value = {"configs": {}}
    mock_extractor.get_palette_config_from_sprite_config.return_value = (0x100, [8])
    mock_extractor.extract_palette_range.return_value = {8: [(0,0,0)]*16}
    controller.rom_extractor = mock_extractor

    # Action 1: Open in editor first time
    controller.open_in_editor()
    sources_1 = editing_controller.get_palette_sources()
    count_1 = len([k for k in sources_1 if k[0] == "rom"])
    assert count_1 > 0
    
    # Action 2: Open in editor second time
    controller.open_in_editor()
    sources_2 = editing_controller.get_palette_sources()
    count_2 = len([k for k in sources_2 if k[0] == "rom"])
    
    # Verify: Count should not have doubled
    assert count_1 == count_2