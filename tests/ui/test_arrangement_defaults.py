"""
Tests for arrangement dialog default values to prevent layout changes.
"""

from unittest.mock import MagicMock, patch

import pytest

from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


class TestArrangementDefaults:
    """Verify defaults for arrangement dialog preserve layout."""

    @pytest.fixture
    def controller(self):
        """Create a mocked ROMWorkflowController."""
        mock_editing = MagicMock()
        mock_editing.validationChanged.connect = MagicMock()
        mock_editing.paletteSourceSelected.connect = MagicMock()
        mock_editing.paletteChanged.connect = MagicMock()
        
        ctrl = ROMWorkflowController(None, mock_editing)
        ctrl._view = MagicMock()
        return ctrl

    def test_rom_workflow_tiles_per_row_calculation(self, controller):
        """
        Verify ROMWorkflowController passes correct tiles_per_row for wide sprites.
        Regression check: Should NOT be clamped to 16.
        """
        # Case 1: Standard sprite (128px = 16 tiles)
        controller.current_width = 128
        
        # We need to spy on GridArrangementDialog init
        with patch('ui.grid_arrangement_dialog.GridArrangementDialog') as MockDialog:
            # Mock image save
            with patch('PIL.Image.Image.save'):
                # Mock current_tile_data so it doesn't return early
                controller.current_tile_data = b'\x00' * 32
                
                controller.show_arrangement_dialog()
                
                # Check args passed to Dialog
                args, _ = MockDialog.call_args
                tiles_per_row = args[1]
                assert tiles_per_row == 16, f"Expected 16 tiles_per_row for 128px width, got {tiles_per_row}"

        # Case 2: Wide sprite (256px = 32 tiles)
        controller.current_width = 256
        with patch('ui.grid_arrangement_dialog.GridArrangementDialog') as MockDialog:
            with patch('PIL.Image.Image.save'):
                controller.current_tile_data = b'\x00' * 32
                controller.show_arrangement_dialog()
                
                args, _ = MockDialog.call_args
                tiles_per_row = args[1]
                assert tiles_per_row == 32, f"Expected 32 tiles_per_row for 256px width, got {tiles_per_row} (Was it clamped?)"

    def test_dialog_width_spin_default(self, qtbot):
        """
        Verify GridArrangementDialog defaults width_spin to full grid width.
        Regression check: Should NOT be clamped to 16.
        """
        # Create a mock processor that simulates a wide sprite
        mock_processor = MagicMock()
        mock_processor.grid_cols = 32
        mock_processor.grid_rows = 1
        mock_processor.tile_width = 8
        mock_processor.tile_height = 8
        
        # Patch the processor creation in the dialog (patch where it is used!)
        with patch('ui.grid_arrangement_dialog.GridImageProcessor', return_value=mock_processor):
            # Also need to mock process_sprite_sheet_as_grid to return something valid
            # Use a real image to prevent crashes in pil_to_qimage
            from PIL import Image
            real_img = Image.new("L", (256, 8))
            mock_processor.process_sprite_sheet_as_grid.return_value = (real_img, {})
            
            # Create dialog with wide tiles_per_row
            dialog = GridArrangementDialog("dummy.png", tiles_per_row=32)
            qtbot.addWidget(dialog)
            
            # Check default width_spin value
            assert dialog.width_spin.value() == 32, \
                f"Expected width_spin default 32, got {dialog.width_spin.value()} (Was it clamped?)"

