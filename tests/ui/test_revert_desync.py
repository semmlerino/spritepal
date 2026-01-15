from unittest.mock import MagicMock, patch

import pytest

from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


def test_revert_to_original_forces_rom_reload():
    """
    Test that revert_to_original() triggers a fresh reload from ROM
    by calling set_offset(..., auto_open=True) instead of using
    possibly dirty internal cache.
    """
    # Setup
    mock_editing = MagicMock()
    mock_editing.has_unsaved_changes.return_value = False

    controller = ROMWorkflowController(None, mock_editing)
    controller.rom_path = "dummy.sfc"
    controller.current_offset = 0x1000
    controller.state = "edit"
    # Must have tile data to revert
    controller.current_tile_data = b"\x00" * 32

    # Action: Click "Revert to Original"
    with patch.object(controller, "set_offset") as mock_set_offset:
        controller.revert_to_original()

        # Verify fix: it calls set_offset with auto_open=True
        mock_set_offset.assert_called_once_with(0x1000, auto_open=True)

    # Verify undo history was cleared to avoid double prompt in set_offset
    assert mock_editing.undo_manager.clear.called
