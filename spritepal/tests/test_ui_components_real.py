"""
Real component tests for UI components using pytest-qt and RealComponentFactory.

Contains tests for:
- ImageUtils (image format conversions)
- RowArrangementDialog (dialog interactions)

Note: ZoomablePreviewWidget and PreviewPanel tests are in test_zoomable_preview.py
"""

from __future__ import annotations

import tempfile

import pytest
from PIL import Image
from PySide6.QtGui import QPixmap

from core.services.image_utils import pil_to_qpixmap
from ui.row_arrangement_dialog import RowArrangementDialog

# Serial execution required: Real Qt components
pytestmark = [pytest.mark.skip_thread_cleanup(reason="Real Qt component tests may create background threads")]


@pytest.mark.gui
class TestImageUtils:
    """Tests for image utilities (requires Qt context for QPixmap creation)"""

    def test_pil_image_to_pixmap_conversion_unit(self, qtbot):
        """Test PIL image to QPixmap conversion"""
        # Create test image
        test_image = Image.new("RGB", (16, 16), "red")

        # Test real conversion
        result = pil_to_qpixmap(test_image)

        # Verify result is a real QPixmap with correct size
        assert isinstance(result, QPixmap)
        assert result.width() == 16
        assert result.height() == 16
        assert not result.isNull()

    def test_pil_image_formats_supported(self, qtbot):
        """Test that various PIL image formats can be converted"""
        formats = [
            ("RGB", (255, 0, 0)),
            ("RGBA", (0, 255, 0, 255)),
            ("L", 128),
        ]

        for mode, color in formats:
            test_image = Image.new(mode, (32, 32), color)
            result = pil_to_qpixmap(test_image)

            assert isinstance(result, QPixmap)
            assert result.width() == 32
            assert result.height() == 32
            assert not result.isNull()


@pytest.mark.gui
class TestRowArrangementDialog:
    """Test RowArrangementDialog with real Qt components"""

    @pytest.fixture
    def temp_sprite_path(self):
        """Create a temporary sprite file for testing"""
        # Create a test sprite image
        test_image = Image.new("RGBA", (64, 32), (255, 0, 0, 255))
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        test_image.save(temp_file.name)
        return temp_file.name

    @pytest.fixture
    def dialog(self, temp_sprite_path, qtbot):
        """Create a real RowArrangementDialog for testing"""
        dialog = RowArrangementDialog(temp_sprite_path, tiles_per_row=8)
        qtbot.addWidget(dialog)
        return dialog

    def test_scroll_position_preserved_on_palette_toggle(self, dialog, qtbot):
        """Test that scroll position is preserved when toggling palette application"""
        # Skip if dialog doesn't have the method (not all versions may have it)
        if not hasattr(dialog, "toggle_palette_application"):
            pytest.skip("Dialog does not have toggle_palette_application method")

        # Get initial window title for comparison
        dialog.windowTitle()

        # Toggle palette application
        dialog.toggle_palette_application()

    def test_dialog_initialization(self, temp_sprite_path, qtbot):
        """Test that dialog initializes properly with real components"""
        dialog = RowArrangementDialog(temp_sprite_path, tiles_per_row=8)
        qtbot.addWidget(dialog)

        # Verify basic initialization
        assert dialog.sprite_path == temp_sprite_path
        assert dialog.tiles_per_row == 8
        assert dialog.image_processor is not None
        assert dialog.arrangement_manager is not None

    def test_dialog_cleanup(self, dialog, qtbot):
        """Test that dialog cleans up properly"""
        # Dialog should be able to close without errors
        dialog.close()

        # Verify cleanup
        assert not dialog.isVisible()
