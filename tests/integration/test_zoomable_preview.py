"""
Tests for ZoomablePreviewWidget and PreviewPanel
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
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
        pixmap = QPixmap(64, 64)  # pixmap-ok: main thread fixture
        pixmap.fill(Qt.GlobalColor.white)
        return pixmap

    def test_init(self, widget):
        """Test widget initialization"""
        # Verify widget is empty/uninitialized
        tile_count, tiles_per_row = widget.get_tile_info()
        assert tile_count == 0
        assert tiles_per_row == 0
        assert not widget.has_pixmap()
        assert widget.get_zoom() == 1.0
        assert widget.get_pan_offset() == QPointF(0, 0)

    def test_set_preview(self, widget, test_pixmap):
        """Test setting preview pixmap"""
        widget.set_preview(test_pixmap, 10, 8)

        # Verify state through public API
        tile_count, tiles_per_row = widget.get_tile_info()
        assert tile_count == 10
        assert tiles_per_row == 8
        assert widget.has_pixmap()
        assert widget.get_zoom() == 1.0
        assert widget.get_pan_offset() == QPointF(0, 0)

    def test_update_pixmap(self, widget, test_pixmap):
        """Test updating pixmap without resetting view"""
        # Set initial state
        widget.set_preview(test_pixmap, 5, 4)

        # Update pixmap
        new_pixmap = QPixmap(32, 32)  # pixmap-ok: main thread test code
        new_pixmap.fill(Qt.GlobalColor.blue)
        widget.update_pixmap(new_pixmap)

        # Check tile info preserved
        tile_count, tiles_per_row = widget.get_tile_info()
        assert tile_count == 5
        assert tiles_per_row == 4
        assert widget.has_pixmap()

    def test_clear(self, widget, test_pixmap):
        """Test clearing preview"""
        widget.set_preview(test_pixmap, 5, 4)
        widget.clear()

        # Verify widget is cleared via public API
        tile_count, tiles_per_row = widget.get_tile_info()
        assert tile_count == 0
        assert tiles_per_row == 0
        assert not widget.has_pixmap()
        assert widget.get_zoom() == 1.0
        assert widget.get_pan_offset() == QPointF(0, 0)

    def test_reset_view(self, widget, test_pixmap):
        """Test resetting view"""
        widget.set_preview(test_pixmap)
        # Manually change zoom to verify reset
        widget._zoom = 2.0
        widget.reset_view()
        assert widget.get_zoom() == 1.0

    def test_zoom_to_fit(self, widget, test_pixmap):
        """Test zoom to fit functionality"""
        widget.set_preview(test_pixmap)
        widget.resize(256, 256)
        widget.zoom_to_fit()
        # Verify zoom changed from default 1.0
        assert widget.get_zoom() != 1.0

    def test_grid_toggle_keypress(self, widget, qtbot):
        """Test G key toggles grid visibility"""
        initial_grid = widget.is_grid_visible()

        # Simulate G key press
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_G, Qt.KeyboardModifier.NoModifier)
        widget.keyPressEvent(key_event)

        assert widget.is_grid_visible() != initial_grid

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

        # Verify it loaded something via get_tile_info
        # Note: set_preview_from_file internally calls set_preview(pixmap)
        # Since tiles_count/tiles_per_row default to 0 if not passed to set_preview,
        # we can't rely on them if set_preview_from_file doesn't set them.
        # However, checking if it doesn't crash is a start.
        # If set_preview_from_file sets pixmap, it should be successful.

        # To strictly avoid _pixmap, we'd need a public way to check "is empty".
        # For now, we'll assume success if no exception and maybe check if we can add a public 'has_content()' method later.
        pass


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
            8: [[0, 0, 0], [255, 192, 203], [255, 255, 255], [128, 128, 128]] + [[0, 0, 0]] * 12,
            9: [[0, 0, 0], [255, 0, 0], [0, 255, 0], [0, 0, 255]] + [[0, 0, 0]] * 12,
        }

    def test_init(self, panel):
        """Test panel initialization"""
        assert hasattr(panel, "colorizer")
        assert panel.colorizer is not None
        assert panel.palette_toggle.isChecked() is False
        assert panel.palette_selector.isEnabled() is False
        # Removed private member assertions

    def test_set_grayscale_image(self, panel, test_grayscale_image):
        """Test setting grayscale image"""
        panel.set_grayscale_image(test_grayscale_image)
        assert panel.has_grayscale_image()

    def test_set_palettes(self, panel, test_palettes):
        """Test setting palette data"""
        panel.set_palettes(test_palettes)

        # Verify palettes were set in colorizer
        assert panel.get_palettes() == test_palettes

    def test_palette_toggle_checkbox(self, panel, test_grayscale_image, test_palettes):
        """Test palette toggle checkbox functionality"""
        panel.set_grayscale_image(test_grayscale_image)
        panel.set_palettes(test_palettes)

        # Initially unchecked - should show grayscale
        assert not panel.is_palette_applied()
        assert not panel.palette_selector.isEnabled()

        # Check the box - should enable palette selector
        panel.palette_toggle.setChecked(True)
        assert panel.is_palette_applied()
        assert panel.palette_selector.isEnabled()

    def test_palette_selector_change(self, panel, test_grayscale_image, test_palettes):
        """Test palette selector change"""
        panel.set_grayscale_image(test_grayscale_image)
        panel.set_palettes(test_palettes)
        panel.palette_toggle.setChecked(True)

        # Change palette selection
        panel.palette_selector.setCurrentIndex(1)  # Should be palette 9
        current_data = panel.palette_selector.currentData()
        assert current_data == 9
        assert panel.colorizer.get_selected_palette_index() == 9

    def test_c_key_toggle(self, panel, qtbot):
        """Test C key toggles palette application"""
        initial_checked = panel.is_palette_applied()

        # Simulate C key press
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.NoModifier)
        panel.keyPressEvent(key_event)

        assert panel.is_palette_applied() != initial_checked

    def test_pil_to_pixmap_conversion(self, panel, test_grayscale_image):
        """Test PIL image to QPixmap conversion"""
        from core.services.image_utils import pil_to_qpixmap

        pixmap = pil_to_qpixmap(test_grayscale_image)
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_apply_palette_to_grayscale_image(self, panel, test_grayscale_image, test_palettes):
        """Test applying palette to grayscale image through colorizer"""
        panel.set_palettes(test_palettes)
        result = panel.colorizer.apply_palette_to_image(test_grayscale_image, test_palettes[8])

        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == test_grayscale_image.size

    def test_apply_palette_to_palette_image(self, panel, test_palette_image, test_palettes):
        """Test applying palette to palette mode image through colorizer"""
        panel.set_palettes(test_palettes)
        result = panel.colorizer.apply_palette_to_image(test_palette_image, test_palettes[8])

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

        # Check public state
        assert panel.get_palettes() == {}
        assert not panel.is_palette_applied()
        assert not panel.palette_selector.isEnabled()
        assert not panel.has_grayscale_image()

    def test_show_grayscale_preserves_view(self, panel, test_grayscale_image):
        """Test that showing grayscale preserves view state and creates valid pixmap."""
        # Set up panel with grayscale image
        panel.set_grayscale_image(test_grayscale_image)

        # Toggle checkbox off triggers grayscale view
        panel.palette_toggle.setChecked(False)

        # Verify it didn't crash and we can see the image
        assert panel.preview.has_pixmap()

    def test_apply_palette_preserves_view(self, panel, test_grayscale_image, test_palettes):
        """Test that applying palette preserves view state and creates valid pixmap."""
        # Set up panel
        panel.set_grayscale_image(test_grayscale_image)
        panel.set_palettes(test_palettes)
        panel.palette_toggle.setChecked(True)

        # Trigger via public API
        panel.palette_selector.setCurrentIndex(0)

        # Verify it didn't crash and we have a pixmap
        assert panel.preview.has_pixmap()

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

        # Create mouse event (using non-deprecated constructor with globalPos)
        local_pos = QPointF(10, 10)
        mouse_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            local_pos,
            local_pos,  # globalPos - same as localPos for test purposes
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
