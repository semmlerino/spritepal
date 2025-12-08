"""
Test sprite preview widget functionality

This is a real Qt widget test that requires a GUI environment and tests
actual widget rendering, pixmap handling, and Qt-specific behavior.

Uses shared class_managers fixture from core_fixtures.py instead of local setup.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from ui.widgets.sprite_preview_widget import SpritePreviewWidget

# Skip in headless environments - this tests real Qt widget functionality
pytestmark = [
    pytest.mark.skipif(
        "DISPLAY" not in os.environ,
        reason="Requires GUI environment - tests real Qt widget rendering"
    ),
    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.qt_integration,
    pytest.mark.gui,
    pytest.mark.integration,
    pytest.mark.qt_real,
    pytest.mark.requires_display,
    pytest.mark.rom_data,
]

# Note: Uses shared class_managers fixture - no local setup_managers needed


@pytest.mark.usefixtures("class_managers")
class TestSpritePreviewWidget:
    """Test the sprite preview widget.

    Uses shared class_managers fixture - no local setup_managers needed.
    """

    @pytest.fixture(scope="class")
    def qapp(self):
        """Create QApplication for testing"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    def test_widget_creation(self, qapp):
        """Test basic widget creation"""
        widget = SpritePreviewWidget("Test Preview")
        assert widget.title == "Test Preview"
        assert widget.sprite_pixmap is None
        assert len(widget.palettes) == 0

    def test_load_grayscale_sprite(self, qapp):
        """Test loading a grayscale sprite"""
        widget = SpritePreviewWidget()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test grayscale image
            img_path = os.path.join(tmpdir, "test_gray.png")
            img = Image.new("L", (16, 16), 128)
            img.save(img_path)

            # Load it
            widget.load_sprite_from_png(img_path, "kirby_normal")

            # Check state
            assert widget.sprite_pixmap is not None
            assert widget.info_label.text().startswith("Size: 16x16")
            assert widget.palette_combo.count() > 0  # Should have default palettes

    def test_load_indexed_sprite(self, qapp):
        """Test loading an indexed sprite"""
        widget = SpritePreviewWidget()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test indexed image
            img_path = os.path.join(tmpdir, "test_indexed.png")
            img = Image.new("P", (16, 16))
            # Set a simple palette
            palette = []
            for i in range(256):
                palette.extend([i, i, i])
            img.putpalette(palette)
            img.save(img_path)

            # Load it
            widget.load_sprite_from_png(img_path)

            # Check state
            assert widget.sprite_pixmap is not None
            assert widget.info_label.text().startswith("Size: 16x16")
            assert not widget.palette_combo.isEnabled()  # Disabled for indexed

    def test_clear_preview(self, qapp):
        """Test clearing the preview"""
        widget = SpritePreviewWidget()

        # Load something first
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, "test.png")
            img = Image.new("L", (16, 16))
            img.save(img_path)
            widget.load_sprite_from_png(img_path)

        # Clear it
        widget.clear()

        # Check cleared state
        assert widget.sprite_pixmap is None
        assert widget.sprite_data is None
        assert len(widget.palettes) == 0
        assert widget.info_label.text() == "No sprite loaded"

    def test_load_4bpp_sprite(self, qapp):
        """Test loading sprite from 4bpp data"""
        widget = SpritePreviewWidget()

        # Create test 4bpp data (single tile)
        tile_data = bytes([0] * 32)  # All black tile

        # Load it
        widget.load_sprite_from_4bpp(tile_data, 8, 8, "test_sprite")

        # Check state
        assert widget.sprite_pixmap is not None
        assert widget.info_label.text() == "Size: 8x8 | Tiles: 1"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
