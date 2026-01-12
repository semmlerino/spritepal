from unittest.mock import ANY, MagicMock, patch

from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


def test_open_in_editor_uses_extracted_palette(qtbot):
    """Verify that open_in_editor extracts all ROM palettes and registers them."""
    # Mock dependencies
    mock_editing_controller = MagicMock()
    mock_rom_extractor = MagicMock()

    # Create controller
    controller = ROMWorkflowController(
        parent=None, editing_controller=mock_editing_controller, rom_extractor=mock_rom_extractor
    )

    # Setup state
    controller.current_tile_data = b"\x00" * 32  # Dummy tile data
    controller.current_width = 8
    controller.current_height = 8
    controller.current_sprite_name = "test_sprite"
    controller.rom_path = "test.sfc"

    # Mock chain of calls for palette extraction
    mock_header = MagicMock()
    mock_rom_extractor.rom_injector.read_rom_header.return_value = mock_header

    # We mock the public palette extractor façade methods on rom_extractor.
    # _find_game_configuration is an internal detail; if it returns a mock (default behavior),
    # and we mock the next step (get_palette_config_from_sprite_config), the flow should work.

    # Setup successful palette config - sprite uses palette 10, with indices [10, 11]
    # This mocks the result of the palette extraction logic regardless of how config was found
    mock_rom_extractor.get_palette_config_from_sprite_config.return_value = (
        0x1000,
        [10, 11],
    )

    # Setup successful palette range extraction - return all 8 sprite palettes (8-15)
    expected_palette_10 = [(0, 0, 0)] * 16
    expected_palette_10[0] = (255, 0, 0)  # Distinctive color for palette 10
    all_palettes = {
        8: [(0, 0, 0)] * 16,
        9: [(0, 0, 0)] * 16,
        10: expected_palette_10,  # This is the one that should be used
        11: [(0, 0, 0)] * 16,
        12: [(0, 0, 0)] * 16,
        13: [(0, 0, 0)] * 16,
        14: [(0, 0, 0)] * 16,
        15: [(0, 0, 0)] * 16,
    }
    mock_rom_extractor.extract_palette_range.return_value = all_palettes

    # Execute
    with patch("ui.sprite_editor.core.palette_utils.get_default_snes_palette") as mock_default:
        controller.open_in_editor()

        # Verify extract_palette_range was called for all sprite palettes (8-15)
        # This confirms the controller attempted to extract palettes
        mock_rom_extractor.extract_palette_range.assert_called_with("test.sfc", 0x1000, 8, 15)

        # Verify all palettes were registered (with optional metadata)
        mock_editing_controller.register_rom_palettes.assert_called_once_with(
            all_palettes, active_indices=ANY, descriptions=ANY
        )

        # Verify the correct palette source was selected (first from config: 10)
        mock_editing_controller.set_palette_source.assert_called_with("rom", 10)

        # Verify editing controller received the correct palette (palette 10)
        # This is the key "outcome" assertion
        mock_editing_controller.load_image.assert_called()
        args = mock_editing_controller.load_image.call_args
        assert args[0][1] == expected_palette_10

        # Verify default palette was NOT used
        mock_default.assert_not_called()


def test_open_in_editor_fallback_to_default(qtbot):
    """Verify that open_in_editor falls back to default palette on failure."""
    # Mock dependencies
    mock_editing_controller = MagicMock()
    mock_rom_extractor = MagicMock()

    # Create controller
    controller = ROMWorkflowController(
        parent=None, editing_controller=mock_editing_controller, rom_extractor=mock_rom_extractor
    )

    # Setup state
    controller.current_tile_data = b"\x00" * 32
    controller.current_width = 8
    controller.current_height = 8
    controller.current_sprite_name = "test_sprite"
    controller.rom_path = "test.sfc"

    # Mock failure at config step
    mock_rom_extractor.rom_injector.read_rom_header.return_value = MagicMock()
    # We don't mock _find_game_configuration. If it returns a mock, the next step needs to fail or return None.
    # The controller logic:
    # game_config = ..._find_game_configuration...
    # if game_config and ...:
    #    ...get_palette_config_from_sprite_config...

    # If we want to simulate "no config found", we can make the mock return None implicitly
    # or ensure get_palette_config_from_sprite_config raises or returns None.

    # Actually, simpler: if we don't mock _find_game_configuration, it returns a MagicMock (truthy).
    # So we need to ensure the next step fails or returns None to trigger fallback.
    mock_rom_extractor.get_palette_config_from_sprite_config.return_value = (None, None)

    # OR, we can mock _find_game_configuration to return None IF we assume the controller calls it.
    # But we want to avoid mocking private methods.
    # The observable behavior is "if palette extraction fails, use default".
    # So let's make the public method `get_palette_config_from_sprite_config` return (None, None)
    # which simulates "no palette config found for this sprite".

    # Execute
    with patch("ui.sprite_editor.core.palette_utils.get_default_snes_palette") as mock_default:
        mock_default_palette = [(1, 1, 1)] * 16
        mock_default.return_value = mock_default_palette

        controller.open_in_editor()

        # Verify editing controller received the default palette
        mock_editing_controller.load_image.assert_called()
        args = mock_editing_controller.load_image.call_args
        assert args[0][1] == mock_default_palette

        # Verify default palette WAS used
        mock_default.assert_called_once()


def test_open_in_editor_clears_previous_rom_sources(qtbot):
    """Verify that loading a new sprite clears previous ROM palette sources."""
    # Mock dependencies
    mock_editing_controller = MagicMock()
    mock_rom_extractor = MagicMock()
    mock_view = MagicMock()
    mock_workspace = MagicMock()
    mock_palette_panel = MagicMock()
    mock_view.workspace = mock_workspace
    mock_workspace.palette_panel = mock_palette_panel

    # Create controller with view
    controller = ROMWorkflowController(
        parent=None, editing_controller=mock_editing_controller, rom_extractor=mock_rom_extractor
    )
    # Use public setter instead of private attribute
    controller.set_view(mock_view)

    # Setup minimal state
    controller.current_tile_data = b"\x00" * 32
    controller.current_width = 8
    controller.current_height = 8
    controller.current_sprite_name = "test_sprite"
    controller.rom_path = "test.sfc"

    # Mock no game config (simpler test)
    mock_rom_extractor.rom_injector.read_rom_header.return_value = MagicMock()
    # Ensure palette extraction returns nothing to trigger fallback (simulating no config)
    mock_rom_extractor.get_palette_config_from_sprite_config.return_value = (None, None)

    # Execute
    with patch("ui.sprite_editor.core.palette_utils.get_default_snes_palette") as mock_default:
        mock_default.return_value = [(0, 0, 0)] * 16
        controller.open_in_editor()

        # Verify palette sources were cleared before loading
        # The controller calls self._view.clear_rom_palette_sources(), not palette_panel directly
        mock_view.clear_rom_palette_sources.assert_called_once()
