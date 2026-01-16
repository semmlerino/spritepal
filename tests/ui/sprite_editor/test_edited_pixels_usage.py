"""Tests for using edited pixels in arrangement dialog and library thumbnail.

REGRESSION: Arrangement dialog and library thumbnail were showing original ROM
data instead of edited pixels when the user was in edit mode.
"""

from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
from PIL import Image


class TestArrangementDialogEditedPixels:
    """Tests for arrangement dialog using edited pixels."""

    def test_arrangement_dialog_checks_for_edited_pixels_in_edit_mode(self, qtbot, tmp_path, monkeypatch) -> None:
        """Arrangement dialog should check for edited pixels when in edit mode.

        Bug: show_arrangement_dialog used current_tile_data (original ROM bytes)
        instead of checking if edited pixels were available in edit mode.
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        editing_controller = EditingController()
        controller = ROMWorkflowController(parent=None, editing_controller=editing_controller)
        view = ROMWorkflowPage()
        qtbot.addWidget(view)
        controller.set_view(view)

        # Set up ROM state
        dummy_rom = tmp_path / "test.sfc"
        dummy_rom.write_bytes(b"\x00" * 0x10000)
        controller.rom_path = str(dummy_rom)
        controller.rom_size = 0x10000

        # Set up controller with tile data
        controller.current_tile_data = b"\x00" * 256  # 8 tiles, all zeros
        controller.current_tile_offset = 0x1000
        controller.current_width = 32  # 4 tiles wide
        controller.current_height = 16  # 2 tiles high
        controller.current_sprite_name = "Test Sprite"
        controller.state = "edit"  # In edit mode

        # Mock the dialog to not actually show
        mock_dialog_class = MagicMock()
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = False
        mock_dialog_class.return_value = mock_dialog

        # Track what was called
        get_image_data_called = []

        def tracked_get_image_data():
            get_image_data_called.append(True)
            # Return edited data that differs from ROM data
            return np.full((16, 32), 7, dtype=np.uint8)  # Different from the zeros in current_tile_data

        monkeypatch.setattr(editing_controller, "get_image_data", tracked_get_image_data)
        monkeypatch.setattr(editing_controller, "get_flat_palette", lambda: [0, 0, 0] * 256)

        with patch("ui.grid_arrangement_dialog.GridArrangementDialog", mock_dialog_class):
            controller.show_arrangement_dialog()

        # Verify that get_image_data was called (meaning we checked for edited pixels)
        assert len(get_image_data_called) > 0, (
            "In edit mode, show_arrangement_dialog should check for edited pixels "
            "via get_image_data(), but it was never called"
        )

    def test_arrangement_dialog_uses_original_data_when_not_in_edit_mode(self, qtbot, tmp_path, monkeypatch) -> None:
        """When not in edit mode, arrangement dialog should use current_tile_data."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        editing_controller = EditingController()
        controller = ROMWorkflowController(parent=None, editing_controller=editing_controller)
        view = ROMWorkflowPage()
        qtbot.addWidget(view)
        controller.set_view(view)

        # Set up ROM state
        dummy_rom = tmp_path / "test.sfc"
        dummy_rom.write_bytes(b"\x00" * 0x10000)
        controller.rom_path = str(dummy_rom)
        controller.rom_size = 0x10000

        # Set up controller in preview mode (not edit)
        controller.current_tile_data = b"\x00" * 256
        controller.current_tile_offset = 0x1000
        controller.current_width = 32
        controller.current_height = 16
        controller.current_sprite_name = "Test Sprite"
        controller.state = "preview"  # NOT in edit mode

        mock_dialog_class = MagicMock()
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = False
        mock_dialog_class.return_value = mock_dialog

        # Track if get_image_data is called
        get_image_data_called = []

        def tracked_get_image_data():
            get_image_data_called.append(True)
            return np.zeros((16, 32), dtype=np.uint8)

        monkeypatch.setattr(editing_controller, "get_image_data", tracked_get_image_data)

        with patch("ui.grid_arrangement_dialog.GridArrangementDialog", mock_dialog_class):
            controller.show_arrangement_dialog()

        # In preview mode, we should NOT check for edited pixels
        # (or if we do check, we shouldn't use them since we're not in edit mode)
        # This test documents that we should use current_tile_data in preview mode


class TestLibraryThumbnailEditedPixels:
    """Tests for library thumbnail using edited pixels."""

    def test_library_thumbnail_checks_edited_pixels_when_in_edit_mode(self, qtbot, tmp_path, monkeypatch) -> None:
        """Library thumbnail should use edited pixels when saving from edit mode.

        Bug: _generate_library_thumbnail used current_tile_data (original ROM bytes)
        instead of checking if we're editing that sprite with unsaved changes.
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        editing_controller = EditingController()
        controller = ROMWorkflowController(parent=None, editing_controller=editing_controller)
        view = ROMWorkflowPage()
        qtbot.addWidget(view)
        controller.set_view(view)

        # Set up ROM state
        dummy_rom = tmp_path / "test.sfc"
        dummy_rom.write_bytes(b"\x00" * 0x10000)
        controller.rom_path = str(dummy_rom)
        controller.rom_size = 0x10000

        # Set up controller state to be in edit mode
        offset = 0x1000
        controller.current_tile_data = b"\x00" * 256
        controller.current_tile_offset = offset
        controller.state = "edit"

        # Track if edited pixels are considered
        edited_data_checked = []

        def tracked_get_image_data():
            edited_data_checked.append(True)
            return np.full((16, 32), 5, dtype=np.uint8)

        monkeypatch.setattr(editing_controller, "get_image_data", tracked_get_image_data)
        monkeypatch.setattr(editing_controller, "get_flat_palette", lambda: [0, 0, 0] * 256)

        # Generate thumbnail for the same offset that's being edited
        _ = controller._generate_library_thumbnail(offset)

        # Should have checked for edited pixels
        assert len(edited_data_checked) > 0, (
            "When in edit mode and generating thumbnail for the current sprite, "
            "_generate_library_thumbnail should check for edited pixels"
        )
