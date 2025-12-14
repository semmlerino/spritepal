"""
Tests for ZoomablePreviewWidget and PreviewPanel
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.widget,
    pytest.mark.ci_safe,
]

from ui.zoomable_preview import PreviewPanel, ZoomablePreviewWidget


@pytest.mark.gui
class TestZoomablePreviewWidget:
    """Test ZoomablePreviewWidget functionality"""

    @pytest.fixture
    def widget(self, qtbot):
        """Create a ZoomablePreviewWidget instance"""
        widget = ZoomablePreviewWidget()
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def test_pixmap(self):
        """Create a test pixmap"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.white)
        return pixmap

    def test_init(self, widget):
        """Test widget initialization"""
        assert widget._pixmap is None
        assert widget._zoom == 1.0
        assert widget._pan_offset == QPointF(0, 0)
        assert widget._grid_visible is True
        assert widget._tile_count == 0
        assert widget._tiles_per_row == 0

    def test_set_preview(self, widget, test_pixmap):
        """Test setting preview pixmap"""
        widget.set_preview(test_pixmap, 10, 8)

        assert widget._pixmap == test_pixmap
        assert widget._tile_count == 10
        assert widget._tiles_per_row == 8
        assert widget._zoom == 1.0  # Should reset zoom
        assert widget._pan_offset == QPointF(0, 0)  # Should reset pan

    def test_update_pixmap(self, widget, test_pixmap):
        """Test updating pixmap without resetting view"""
        # Set initial state
        widget.set_preview(test_pixmap, 5, 4)
        widget._zoom = 2.0
        widget._pan_offset = QPointF(10, 20)

        # Create new pixmap
        new_pixmap = QPixmap(32, 32)
        new_pixmap.fill(Qt.GlobalColor.blue)

        # Update pixmap
        widget.update_pixmap(new_pixmap)

        # Check pixmap was updated but view preserved
        assert widget._pixmap == new_pixmap
        assert widget._zoom == 2.0  # Should preserve zoom
        assert widget._pan_offset == QPointF(10, 20)  # Should preserve pan

    def test_clear(self, widget, test_pixmap):
        """Test clearing preview"""
        widget.set_preview(test_pixmap, 5, 4)
        widget._zoom = 2.0
        widget._pan_offset = QPointF(10, 20)

        widget.clear()

        assert widget._pixmap is None
        assert widget._tile_count == 0
        assert widget._tiles_per_row == 0
        assert widget._zoom == 1.0
        assert widget._pan_offset == QPointF(0, 0)

    def test_reset_view(self, widget, test_pixmap):
        """Test resetting view"""
        widget.set_preview(test_pixmap)
        widget._zoom = 3.0
        widget._pan_offset = QPointF(50, 75)

        widget.reset_view()

        assert widget._zoom == 1.0
        assert widget._pan_offset == QPointF(0, 0)

    def test_zoom_to_fit(self, widget, test_pixmap):
        """Test zoom to fit functionality"""
        widget.set_preview(test_pixmap)
        widget.resize(256, 256)

        widget.zoom_to_fit()

        # Should calculate zoom to fit 64x64 pixmap in 256x256 widget
        expected_zoom = min(256 / 64, 256 / 64) * 0.9  # 90% of perfect fit
        assert abs(widget._zoom - expected_zoom) < 0.01

    def test_grid_toggle_keypress(self, widget, qtbot):
        """Test G key toggles grid visibility"""
        initial_grid = widget._grid_visible

        # Simulate G key press
        key_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_G, Qt.KeyboardModifier.NoModifier
        )
        widget.keyPressEvent(key_event)

        assert widget._grid_visible != initial_grid

    def test_get_tile_info(self, widget, test_pixmap):
        """Test getting tile information"""
        widget.set_preview(test_pixmap, 12, 6)

        tile_count, tiles_per_row = widget.get_tile_info()
        assert tile_count == 12
        assert tiles_per_row == 6

    def test_set_preview_from_file(self, widget, tmp_path):
        """Test loading preview from file"""
        # Create test image file
        test_image = Image.new("RGB", (32, 32), "red")
        test_file = tmp_path / "test.png"
        test_image.save(test_file)

        widget.set_preview_from_file(str(test_file))

        assert widget._pixmap is not None
        assert not widget._pixmap.isNull()

@pytest.mark.gui
class TestPreviewPanel:
    """Test PreviewPanel functionality"""

    @pytest.fixture
    def panel(self, qtbot):
        """Create a PreviewPanel instance"""
        panel = PreviewPanel()
        qtbot.addWidget(panel)
        return panel

    @pytest.fixture
    def test_grayscale_image(self):
        """Create test grayscale image"""
        return Image.new("L", (32, 32), 128)

    @pytest.fixture
    def test_palette_image(self):
        """Create test palette mode image"""
        image = Image.new("P", (32, 32), 0)
        # Set some pixels to different palette indices
        pixels = image.load()
        for y in range(32):
            for x in range(32):
                pixels[x, y] = (x + y) % 16
        return image

    @pytest.fixture
    def test_palettes(self):
        """Create test palette data"""
        return {
            8: [[0, 0, 0], [255, 192, 203], [255, 255, 255], [128, 128, 128]]
            + [[0, 0, 0]] * 12,
            9: [[0, 0, 0], [255, 0, 0], [0, 255, 0], [0, 0, 255]] + [[0, 0, 0]] * 12,
        }

    def test_init(self, panel):
        """Test panel initialization"""
        assert panel._grayscale_image is None
        assert panel._colorized_image is None
        assert hasattr(panel, "colorizer")
        assert panel.colorizer is not None
        assert panel.palette_toggle.isChecked() is False
        assert panel.palette_selector.isEnabled() is False

    def test_set_grayscale_image(self, panel, test_grayscale_image):
        """Test setting grayscale image"""
        panel.set_grayscale_image(test_grayscale_image)

        assert panel._grayscale_image == test_grayscale_image

    def test_set_palettes(self, panel, test_palettes):
        """Test setting palette data"""
        panel.set_palettes(test_palettes)

        # Verify palettes were set in colorizer
        assert panel.colorizer.get_palettes() == test_palettes

    def test_palette_toggle_checkbox(self, panel, test_grayscale_image, test_palettes):
        """Test palette toggle checkbox functionality"""
        panel.set_grayscale_image(test_grayscale_image)
        panel.set_palettes(test_palettes)

        # Initially unchecked - should show grayscale
        assert panel.palette_toggle.isChecked() is False
        assert panel.palette_selector.isEnabled() is False

        # Check the box - should enable palette selector
        panel.palette_toggle.setChecked(True)
        assert panel.palette_selector.isEnabled() is True

    def test_palette_selector_change(self, panel, test_grayscale_image, test_palettes):
        """Test palette selector change"""
        panel.set_grayscale_image(test_grayscale_image)
        panel.set_palettes(test_palettes)
        panel.palette_toggle.setChecked(True)

        # Change palette selection
        panel.palette_selector.setCurrentIndex(1)  # Should be palette 9
        current_data = panel.palette_selector.currentData()
        assert current_data == 9

    def test_c_key_toggle(self, panel, qtbot):
        """Test C key toggles palette application"""
        initial_checked = panel.palette_toggle.isChecked()

        # Simulate C key press
        key_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.NoModifier
        )
        panel.keyPressEvent(key_event)

        assert panel.palette_toggle.isChecked() != initial_checked

    def test_pil_to_pixmap_conversion(self, panel, test_grayscale_image):
        """Test PIL image to QPixmap conversion"""
        pixmap = panel._pil_to_pixmap(test_grayscale_image)

        assert pixmap is not None
        assert isinstance(pixmap, QPixmap)
        assert not pixmap.isNull()

    def test_apply_palette_to_grayscale_image(
        self, panel, test_grayscale_image, test_palettes
    ):
        """Test applying palette to grayscale image through colorizer"""
        panel.set_palettes(test_palettes)
        result = panel.colorizer.apply_palette_to_image(
            test_grayscale_image, test_palettes[8]
        )

        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == test_grayscale_image.size

    def test_apply_palette_to_palette_image(
        self, panel, test_palette_image, test_palettes
    ):
        """Test applying palette to palette mode image through colorizer"""
        panel.set_palettes(test_palettes)
        result = panel.colorizer.apply_palette_to_image(
            test_palette_image, test_palettes[8]
        )

        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == test_palette_image.size

    def test_transparency_handling(self, panel, test_palettes):
        """Test transparency for palette index 0"""
        # Create image with palette index 0
        test_image = Image.new("P", (4, 4), 0)

        panel.set_palettes(test_palettes)
        result = panel.colorizer.apply_palette_to_image(test_image, test_palettes[8])

        assert result is not None
        # Check that palette index 0 becomes transparent
        pixels = result.load()
        assert pixels[0, 0][3] == 0  # Alpha should be 0 (transparent)

    def test_clear_panel(self, panel, test_grayscale_image, test_palettes):
        """Test clearing panel state"""
        panel.set_grayscale_image(test_grayscale_image)
        panel.set_palettes(test_palettes)
        panel.palette_toggle.setChecked(True)

        panel.clear()

        assert panel._grayscale_image is None
        assert panel._colorized_image is None
        assert panel.colorizer.get_palettes() == {}
        assert panel.palette_toggle.isChecked() is False
        assert panel.palette_selector.isEnabled() is False

    @patch("ui.zoomable_preview.PreviewPanel._pil_to_pixmap")
    def test_show_grayscale_preserves_view(
        self, mock_pil_to_pixmap, panel, test_grayscale_image
    ):
        """Test that showing grayscale preserves view state"""
        # Mock the conversion
        mock_pixmap = Mock()
        mock_pil_to_pixmap.return_value = mock_pixmap

        # Set up panel
        panel.set_grayscale_image(test_grayscale_image)

        # Mock the preview widget's update_pixmap method
        panel.preview.update_pixmap = Mock()

        # Call _show_grayscale
        panel._show_grayscale()

        # Should call update_pixmap (not set_preview)
        panel.preview.update_pixmap.assert_called_once_with(mock_pixmap)

    @patch("ui.zoomable_preview.PreviewPanel._pil_to_pixmap")
    def test_apply_palette_preserves_view(
        self, mock_pil_to_pixmap, panel, test_grayscale_image, test_palettes
    ):
        """Test that applying palette preserves view state"""
        # Mock the conversion
        mock_pixmap = Mock()
        mock_pil_to_pixmap.return_value = mock_pixmap

        # Set up panel
        panel.set_grayscale_image(test_grayscale_image)
        panel.set_palettes(test_palettes)
        panel.palette_toggle.setChecked(True)

        # Mock the preview widget's update_pixmap method
        panel.preview.update_pixmap = Mock()

        # Call _apply_current_palette
        panel._apply_current_palette()

        # Should call update_pixmap (not set_preview)
        panel.preview.update_pixmap.assert_called_once_with(mock_pixmap)

    def test_error_handling_in_palette_application(self, panel):
        """Test error handling when palette application fails"""
        # Try to apply palette with invalid data
        result = panel.colorizer.apply_palette_to_image(None, None)
        assert result is None

        # Try with invalid palette
        test_image = Image.new("L", (4, 4), 0)
        result = panel.colorizer.apply_palette_to_image(test_image, [])
        assert result is None

    def test_mouse_press_sets_focus(self, panel, qtbot):
        """Test that mouse press sets focus for keyboard input"""
        # Mock the focus methods
        panel.setFocus = Mock()

        # Create mouse event
        mouse_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        # Call mouse press event
        panel.mousePressEvent(mouse_event)

        # Should set focus
        panel.setFocus.assert_called_once()

    def test_get_palettes_public_api(self, panel, test_palettes):
        """Test the public get_palettes API"""
        # Initially empty
        assert panel.get_palettes() == {}

        # Set palettes
        panel.set_palettes(test_palettes)

        # Should return the palettes
        assert panel.get_palettes() == test_palettes
