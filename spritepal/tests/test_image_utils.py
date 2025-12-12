"""Tests for image utility functions"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from utils.image_utils import create_checkerboard_pattern, pil_to_qpixmap

# Check if Qt is available without initializing
try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QPixmap

    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.mock_only,
    pytest.mark.parallel_safe,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.no_manager_setup,  # Pure unit tests for image utility functions
]

def is_headless_environment():
    """Check if we're in a headless environment"""
    import os
    import sys

    return (
        not os.environ.get("DISPLAY")
        or os.environ.get("CI")
        or "microsoft" in os.uname().release.lower()
        or (sys.platform.startswith("linux") and not os.environ.get("DISPLAY"))
    )

@pytest.mark.gui
@pytest.mark.skipif(not QT_AVAILABLE, reason="Qt not available")
@pytest.mark.skipif(
    is_headless_environment(), reason="GUI tests skipped in headless environment"
)
class TestPilToQPixmap:
    """Test PIL to QPixmap conversion"""

    def setup_method(self):
        """Setup Qt application for testing"""
        if not QCoreApplication.instance():
            self.app = QCoreApplication([])
        else:
            self.app = QCoreApplication.instance()

    def teardown_method(self):
        """Clean up Qt application"""
        if hasattr(self, "app") and self.app:
            self.app.quit()

    def test_valid_image_conversion(self):
        """Test converting a valid PIL image to QPixmap"""
        # Create a simple test image
        pil_image = Image.new("RGB", (100, 100), color="red")

        # Convert to QPixmap
        pixmap = pil_to_qpixmap(pil_image)

        assert pixmap is not None
        assert isinstance(pixmap, QPixmap)
        assert pixmap.width() == 100
        assert pixmap.height() == 100
        assert not pixmap.isNull()

    def test_rgba_image_conversion(self):
        """Test converting RGBA image with transparency"""
        # Create RGBA image with transparency
        pil_image = Image.new("RGBA", (50, 50), (255, 0, 0, 128))

        pixmap = pil_to_qpixmap(pil_image)

        assert pixmap is not None
        assert pixmap.hasAlpha()
        assert pixmap.width() == 50
        assert pixmap.height() == 50

    def test_grayscale_image_conversion(self):
        """Test converting grayscale image"""
        pil_image = Image.new("L", (75, 75), 128)

        pixmap = pil_to_qpixmap(pil_image)

        assert pixmap is not None
        assert pixmap.width() == 75
        assert pixmap.height() == 75

    def test_none_input(self):
        """Test handling None input"""
        pixmap = pil_to_qpixmap(None)
        assert pixmap is None

    def test_empty_image(self):
        """Test handling image that evaluates to False"""
        # Create a mock that evaluates to False
        mock_image = MagicMock()
        mock_image.__bool__.return_value = False

        pixmap = pil_to_qpixmap(mock_image)
        assert pixmap is None

    def test_very_small_image(self):
        """Test converting 1x1 pixel image"""
        pil_image = Image.new("RGB", (1, 1), "blue")

        pixmap = pil_to_qpixmap(pil_image)

        assert pixmap is not None
        assert pixmap.width() == 1
        assert pixmap.height() == 1

    def test_large_image(self):
        """Test converting large image"""
        # Create a reasonably large image
        pil_image = Image.new("RGB", (2000, 2000), "green")

        pixmap = pil_to_qpixmap(pil_image)

        assert pixmap is not None
        assert pixmap.width() == 2000
        assert pixmap.height() == 2000

    def test_save_exception_handling(self, caplog):
        """Test handling of save exceptions"""
        # Create image that will fail to save
        mock_image = MagicMock(spec=Image.Image)
        mock_image.__bool__.return_value = True
        mock_image.save.side_effect = Exception("Save failed")

        with caplog.at_level(logging.ERROR):
            pixmap = pil_to_qpixmap(mock_image)

        assert pixmap is None
        assert "Failed to convert PIL to QPixmap: Save failed" in caplog.text

    def test_loadfromdata_failure(self, caplog):
        """Test handling when QPixmap.loadFromData fails"""
        pil_image = Image.new("RGB", (10, 10), "white")

        # Mock QPixmap to fail loading
        with patch("core.services.image_utils.QPixmap") as mock_qpixmap_class:
            mock_pixmap = MagicMock()
            mock_pixmap.loadFromData.return_value = False
            mock_qpixmap_class.return_value = mock_pixmap

            with caplog.at_level(logging.ERROR):
                result = pil_to_qpixmap(pil_image)

            assert result is None
            assert "Failed to load pixmap from buffer data" in caplog.text

    def test_different_image_modes(self):
        """Test conversion of various PIL image modes"""
        modes_to_test = [
            ("RGB", (255, 0, 0)),
            ("RGBA", (255, 0, 0, 255)),
            ("L", 128),
            ("P", 0),  # Palette mode
        ]

        for mode, color in modes_to_test:
            pil_image = Image.new(mode, (20, 20), color)
            pixmap = pil_to_qpixmap(pil_image)

            assert pixmap is not None, f"Failed to convert {mode} mode image"
            assert pixmap.width() == 20
            assert pixmap.height() == 20

class TestCreateCheckerboardPattern:
    """Test checkerboard pattern creation"""

    def test_default_checkerboard(self):
        """Test creating checkerboard with default parameters"""
        img = create_checkerboard_pattern(64, 64)

        assert isinstance(img, Image.Image)
        assert img.size == (64, 64)
        assert img.mode == "RGB"

        # Check corner pixels for pattern
        assert img.getpixel((0, 0)) == (200, 200, 200)  # First tile
        assert img.getpixel((8, 0)) == (255, 255, 255)  # Second tile
        assert img.getpixel((0, 8)) == (255, 255, 255)  # Second row first tile
        assert img.getpixel((8, 8)) == (200, 200, 200)  # Second row second tile

    def test_custom_colors(self):
        """Test checkerboard with custom colors"""
        color1 = (100, 100, 100)
        color2 = (50, 50, 50)

        img = create_checkerboard_pattern(
            32, 32, tile_size=8, color1=color1, color2=color2
        )

        assert img.getpixel((0, 0)) == color1
        assert img.getpixel((8, 0)) == color2

    def test_custom_tile_size(self):
        """Test checkerboard with custom tile size"""
        img = create_checkerboard_pattern(100, 100, tile_size=25)

        # Check pattern with 25x25 tiles
        assert img.getpixel((0, 0)) == (200, 200, 200)
        assert img.getpixel((25, 0)) == (255, 255, 255)
        assert img.getpixel((50, 0)) == (200, 200, 200)
        assert img.getpixel((0, 25)) == (255, 255, 255)

    def test_non_divisible_dimensions(self):
        """Test checkerboard when dimensions aren't divisible by tile size"""
        img = create_checkerboard_pattern(33, 33, tile_size=10)

        assert img.size == (33, 33)
        # Check that edge pixels are filled correctly
        assert img.getpixel((32, 32)) in [(200, 200, 200), (255, 255, 255)]

    def test_single_tile_size(self):
        """Test checkerboard with 1x1 tile size"""
        img = create_checkerboard_pattern(4, 4, tile_size=1)

        # Should alternate every pixel
        assert img.getpixel((0, 0)) == (200, 200, 200)
        assert img.getpixel((1, 0)) == (255, 255, 255)
        assert img.getpixel((0, 1)) == (255, 255, 255)
        assert img.getpixel((1, 1)) == (200, 200, 200)

    def test_large_tile_size(self):
        """Test checkerboard with tile size larger than image"""
        img = create_checkerboard_pattern(10, 10, tile_size=20)

        # Entire image should be one color
        for y in range(10):
            for x in range(10):
                assert img.getpixel((x, y)) == (200, 200, 200)

    def test_rectangular_image(self):
        """Test checkerboard with non-square dimensions"""
        img = create_checkerboard_pattern(80, 40, tile_size=10)

        assert img.size == (80, 40)
        # Verify pattern works with rectangular dimensions
        assert img.getpixel((0, 0)) == (200, 200, 200)
        assert img.getpixel((10, 0)) == (255, 255, 255)
        assert img.getpixel((0, 10)) == (255, 255, 255)

    def test_very_small_image(self):
        """Test checkerboard with very small dimensions"""
        img = create_checkerboard_pattern(2, 2, tile_size=1)

        assert img.size == (2, 2)
        assert img.getpixel((0, 0)) == (200, 200, 200)
        assert img.getpixel((1, 0)) == (255, 255, 255)
        assert img.getpixel((0, 1)) == (255, 255, 255)
        assert img.getpixel((1, 1)) == (200, 200, 200)

    def test_pattern_consistency(self):
        """Test that checkerboard pattern is consistent"""
        img = create_checkerboard_pattern(100, 100, tile_size=10)

        # Check multiple points to ensure pattern consistency
        for y in range(0, 100, 10):
            for x in range(0, 100, 10):
                tile_x = x // 10
                tile_y = y // 10
                expected_color = (
                    (200, 200, 200) if (tile_x + tile_y) % 2 == 0 else (255, 255, 255)
                )
                assert img.getpixel((x, y)) == expected_color

    def test_edge_pixels(self):
        """Test that edge pixels are correctly filled"""
        # Test with dimensions that don't divide evenly
        img = create_checkerboard_pattern(35, 27, tile_size=8)

        # Check rightmost column
        for y in range(27):
            pixel = img.getpixel((34, y))
            assert pixel in [(200, 200, 200), (255, 255, 255)]

        # Check bottom row
        for x in range(35):
            pixel = img.getpixel((x, 26))
            assert pixel in [(200, 200, 200), (255, 255, 255)]

    def test_memory_efficiency(self):
        """Test that function works with large images"""
        # Create a reasonably large checkerboard
        img = create_checkerboard_pattern(1000, 1000, tile_size=50)

        assert img.size == (1000, 1000)
        # Spot check a few tiles
        assert img.getpixel((0, 0)) == (200, 200, 200)
        assert img.getpixel((50, 0)) == (255, 255, 255)
        assert img.getpixel((100, 0)) == (200, 200, 200)
