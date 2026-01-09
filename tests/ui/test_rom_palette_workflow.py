
from unittest.mock import MagicMock, patch

import pytest

from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


def test_open_in_editor_uses_extracted_palette(qtbot):
    """Verify that open_in_editor attempts to extract palette from ROM."""
    # Mock dependencies
    mock_editing_controller = MagicMock()
    mock_rom_extractor = MagicMock()
    
    # Create controller
    controller = ROMWorkflowController(
        parent=None, 
        editing_controller=mock_editing_controller,
        rom_extractor=mock_rom_extractor
    )
    
    # Setup state
    controller.current_tile_data = b'\x00' * 32  # Dummy tile data
    controller.current_width = 8
    controller.current_height = 8
    controller.current_sprite_name = "test_sprite"
    controller.rom_path = "test.sfc"
    
    # Mock chain of calls for palette extraction
    mock_header = MagicMock()
    mock_rom_extractor.rom_injector.read_rom_header.return_value = mock_header
    
    mock_game_config = {"some": "config"}
    mock_rom_extractor._find_game_configuration.return_value = mock_game_config
    
    # Setup successful palette config
    mock_rom_extractor.rom_palette_extractor.get_palette_config_from_sprite_config.return_value = (0x1000, [2])
    
    # Setup successful palette extraction
    expected_palette = [(0,0,0)] * 16
    expected_palette[0] = (255, 0, 0) # Distinctive color
    mock_rom_extractor.rom_palette_extractor.extract_palette_colors_from_rom.return_value = expected_palette
    
    # Execute
    with patch('ui.sprite_editor.core.palette_utils.get_default_snes_palette') as mock_default:
        controller.open_in_editor()
        
        # Verify extraction was attempted with correct params
        mock_rom_extractor.rom_palette_extractor.get_palette_config_from_sprite_config.assert_called_with(
            mock_game_config, "test_sprite"
        )
        
        mock_rom_extractor.rom_palette_extractor.extract_palette_colors_from_rom.assert_called_with(
            "test.sfc", 0x1000, 2
        )
        
        # Verify editing controller received the extracted palette
        mock_editing_controller.load_image.assert_called()
        args = mock_editing_controller.load_image.call_args
        assert args[0][1] == expected_palette
        
        # Verify default palette was NOT used
        mock_default.assert_not_called()

def test_open_in_editor_fallback_to_default(qtbot):
    """Verify that open_in_editor falls back to default palette on failure."""
    # Mock dependencies
    mock_editing_controller = MagicMock()
    mock_rom_extractor = MagicMock()
    
    # Create controller
    controller = ROMWorkflowController(
        parent=None, 
        editing_controller=mock_editing_controller,
        rom_extractor=mock_rom_extractor
    )
    
    # Setup state
    controller.current_tile_data = b'\x00' * 32
    controller.current_width = 8
    controller.current_height = 8
    controller.current_sprite_name = "test_sprite"
    controller.rom_path = "test.sfc"
    
    # Mock failure at config step
    mock_rom_extractor.rom_injector.read_rom_header.return_value = MagicMock()
    mock_rom_extractor._find_game_configuration.return_value = None # No config found
    
    # Execute
    with patch('ui.sprite_editor.core.palette_utils.get_default_snes_palette') as mock_default:
        mock_default_palette = [(1,1,1)] * 16
        mock_default.return_value = mock_default_palette
        
        controller.open_in_editor()
        
        # Verify editing controller received the default palette
        mock_editing_controller.load_image.assert_called()
        args = mock_editing_controller.load_image.call_args
        assert args[0][1] == mock_default_palette
        
        # Verify default palette WAS used
        mock_default.assert_called_once()
