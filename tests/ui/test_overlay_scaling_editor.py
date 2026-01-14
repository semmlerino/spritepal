
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


class TestOverlayScalingEditor:
    @pytest.fixture
    def controller(self):
        # Setup real controllers with mocks for dependencies
        edit_ctrl = EditingController()
        # Initialize with 32x32 sprite (all index 0)
        edit_ctrl.load_image(np.zeros((32, 32), dtype=np.uint8), [(0,0,0)]*16)
        
        # Mock workflow controller
        workflow = ROMWorkflowController(None, edit_ctrl)
        workflow._view = MagicMock()
        workflow._view.workspace = MagicMock()
        workflow.current_width = 32
        workflow.current_height = 32
        return workflow

    def test_merge_overlay_with_scaling(self, controller):
        # Sprite: 32x32 (all index 0)
        # Overlay: 64x64 (all red)
        # Scale: 0.5 (should visually match 32x32)
        
        palette = [(0,0,0)] * 16
        palette[1] = (255, 0, 0)
        controller._editing_controller.set_palette(palette)
        
        overlay = QImage(64, 64, QImage.Format.Format_ARGB32)
        overlay.fill(QColor(255, 0, 0))
        
        position = QPoint(0, 0)
        scale = 0.5
        
        sprite_data = controller._editing_controller.get_image_data()
        merged = controller._merge_overlay_to_indexed(
            sprite_data,
            palette,
            overlay,
            position,
            scale
        )
        
        # Whole 32x32 sprite should now be red (index 1)
        assert merged.shape == (32, 32)
        assert np.all(merged == 1)

    def test_merge_overlay_with_scaling_and_offset(self, controller):
        # Sprite: 32x32
        # Overlay: 32x32
        # Scale: 0.5 (visual size 16x16)
        # Position: (8, 8)
        
        palette = [(0,0,0)] * 16
        palette[1] = (255, 0, 0)
        
        overlay = QImage(32, 32, QImage.Format.Format_ARGB32)
        overlay.fill(QColor(255, 0, 0))
        
        sprite_data = np.zeros((32, 32), dtype=np.uint8)
        merged = controller._merge_overlay_to_indexed(
            sprite_data,
            palette,
            overlay,
            QPoint(8, 8),
            0.5
        )
        
        # (8,8) to (23,23) should be red
        assert merged[8, 8] == 1
        assert merged[23, 23] == 1
        # (7,7) should be 0
        assert merged[7, 7] == 0
        # (24,24) should be 0
        assert merged[24, 24] == 0

    def test_auto_scale_on_import(self, controller, tmp_path):
        # Create a large overlay image
        img_path = tmp_path / "large.png"
        QImage(128, 128, QImage.Format.Format_ARGB32).save(str(img_path))
        
        # Mock QFileDialog
        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(img_path), "Images")):
            # Mock canvas
            canvas = MagicMock()
            controller._view.workspace.get_canvas.return_value = canvas
            
            controller.state = "edit"
            controller._on_overlay_import_requested()
            
            # Sprite is 32x32, Overlay is 128x128. Initial scale should be 32/128 = 0.25
            canvas.set_overlay_scale.assert_called_with(0.25)
            # Verify panel UI was updated
            controller._view.workspace.overlay_panel._scale_slider.setValue.assert_called_with(25)

if __name__ == "__main__":
    pytest.main([__file__])
