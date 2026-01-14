from unittest.mock import ANY, MagicMock, patch

import pytest

from core.sprite_library import LibrarySprite
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


def test_palette_association_persistence(qtbot):
    """Verify that a manually loaded palette stays associated with a sprite via library."""
    # Mock dependencies
    mock_editing_controller = MagicMock()
    mock_rom_extractor = MagicMock()
    mock_sprite_library = MagicMock()
    mock_view = MagicMock()
    mock_workspace = MagicMock()
    mock_palette_panel = MagicMock()
    mock_view.workspace = mock_workspace
    mock_workspace.palette_panel = mock_palette_panel

    # Setup mock library behavior
    mock_sprite_library.compute_rom_hash.return_value = "fake_hash"
    
    # Create controller
    controller = ROMWorkflowController(
        parent=None, 
        editing_controller=mock_editing_controller, 
        rom_extractor=mock_rom_extractor,
        sprite_library=mock_sprite_library
    )
    controller.set_view(mock_view)

    # 1. Setup initial sprite state
    controller.rom_path = "test.sfc"
    controller.current_offset = 0x123456
    controller.current_tile_data = b"\x00" * 32
    controller.current_width = 8
    controller.current_height = 8
    controller.current_sprite_name = "test_sprite"

    # 2. Simulate manual palette choice (e.g. from file)
    custom_palette = [(255, 0, 0)] + [(0, 0, 0)] * 15
    custom_source = ("file", 0)
    mock_editing_controller.get_current_colors.return_value = custom_palette
    mock_editing_controller.get_current_palette_source.return_value = custom_source
    mock_editing_controller.palette_model.name = "Custom Palette"

    # 3. Simulate "Save to Library" (where association is created)
    # Initially not in library
    mock_sprite_library.get_by_offset.return_value = []
    
    # Mock return value for add_sprite
    lib_sprite = LibrarySprite(
        rom_offset=0x123456,
        rom_hash="fake_hash",
        name="test_sprite",
        palette_colors=custom_palette,
        palette_name="Custom Palette",
        palette_source=custom_source
    )
    mock_sprite_library.add_sprite.return_value = lib_sprite

    # Trigger save
    controller._on_save_to_library(0x123456, "rom")

    # Verify add_sprite was called with palette info
    mock_sprite_library.add_sprite.assert_called_with(
        rom_offset=0x123456,
        rom_path="test.sfc",
        name=ANY,
        thumbnail=ANY,
        palette_colors=custom_palette,
        palette_name="Custom Palette",
        palette_source=custom_source
    )

    # 4. Simulate switching back to this sprite (loading it)
    # Reset mocks to verify loading logic
    mock_editing_controller.reset_mock()
    mock_rom_extractor.reset_mock()
    
    # Mock existing sprite in library for the re-load
    mock_sprite_library.get_by_offset.return_value = [lib_sprite]
    
    # Mock ROM extraction success (it will extract default ROM palettes)
    mock_rom_extractor.rom_injector.read_rom_header.return_value = MagicMock()
    mock_rom_extractor.get_palette_config_from_sprite_config.return_value = (0x1000, [8])
    rom_palette = [(0, 255, 0)] * 16  # Green
    mock_rom_extractor.extract_palette_range.return_value = {8: rom_palette}

    # Execute open_in_editor (re-loading the sprite)
    controller.open_in_editor()

    # VERIFY: Even though ROM extraction found a green palette, 
    # the library association should have OVERRIDDEN it with the red one.
    
    # 1. verify set_palette was called with custom_palette
    mock_editing_controller.set_palette.assert_any_call(custom_palette, "Custom Palette")
    
    # 2. verify set_palette_source was called with custom_source
    mock_editing_controller.set_palette_source.assert_called_with("file", 0)
    
    # 3. verify custom file source was re-registered
    mock_editing_controller.register_palette_source.assert_any_call(
        "file", 0, custom_palette, "Custom Palette"
    )

def test_on_palette_changed_updates_library(qtbot):
    """Verify that changing a palette color updates the library association if present."""
    # Mock dependencies
    mock_editing_controller = MagicMock()
    mock_sprite_library = MagicMock()
    
    # Create controller
    controller = ROMWorkflowController(
        parent=None, 
        editing_controller=mock_editing_controller, 
        sprite_library=mock_sprite_library
    )

    # Setup state
    controller.rom_path = "test.sfc"
    controller.current_offset = 0x123456
    
    # Mock existing sprite in library
    lib_sprite = LibrarySprite(
        rom_offset=0x123456,
        rom_hash="fake_hash",
        name="test_sprite"
    )
    mock_sprite_library.compute_rom_hash.return_value = "fake_hash"
    mock_sprite_library.get_by_offset.return_value = [lib_sprite]

    # Setup current palette state in controller
    current_colors = [(10, 20, 30)] * 16
    mock_editing_controller.get_current_colors.return_value = current_colors
    mock_editing_controller.palette_model.name = "My Palette"
    mock_editing_controller.get_current_palette_source.return_value = ("rom", 8)

    # Trigger paletteChanged
    controller._on_palette_changed()

    # Verify update_sprite was called
    mock_sprite_library.update_sprite.assert_called_with(
        ANY, # unique_id
        palette_colors=current_colors,
        palette_name="My Palette",
        palette_source=("rom", 8)
    )
