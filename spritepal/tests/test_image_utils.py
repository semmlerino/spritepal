"""Tests for image utility functions.

This file contains:
- TestPilToQPixmap: Real Qt tests for happy paths (requires display)
- TestPilToQPixmapMocked: Mocked Qt tests for error paths (headless)
- TestCreateCheckerboardPattern: Pure PIL tests (headless)
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.services.image_utils import create_checkerboard_pattern, pil_to_qpixmap

# Check if Qt is available without initializing
try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QPixmap

    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

# Module-level markers for tests that don't specify otherwise
pytestmark = [pytest.mark.no_manager_setup]


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


# =============================================================================
# Real Qt Tests - Happy Paths Only (require display)
# =============================================================================


@pytest.mark.gui
@pytest.mark.allows_registry_state  # Pure unit test, Qt import triggers registry
@pytest.mark.skipif(not QT_AVAILABLE, reason="Qt not available")
@pytest.mark.skipif(
    is_headless_environment(), reason="GUI tests skipped in headless environment"
)
class TestPilToQPixmap:
    """Test PIL to QPixmap conversion with real Qt.

    These tests validate actual QPixmap behavior and require a display.
    Error paths are tested in TestPilToQPixmapMocked below.
    """

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
        pil_image = Image.new("RGB", (100, 100), color="red")

        pixmap = pil_to_qpixmap(pil_image)

        assert pixmap is not None
        assert isinstance(pixmap, QPixmap)
        assert pixmap.width() == 100
        assert pixmap.height() == 100
        assert not pixmap.isNull()

    def test_rgba_image_conversion(self):
        """Test converting RGBA image with transparency"""
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

    def test_very_small_image(self):
        """Test converting 1x1 pixel image"""
        pil_image = Image.new("RGB", (1, 1), "blue")

        pixmap = pil_to_qpixmap(pil_image)

        assert pixmap is not None
        assert pixmap.width() == 1
        assert pixmap.height() == 1

    def test_large_image(self):
        """Test converting large image"""
        pil_image = Image.new("RGB", (2000, 2000), "green")

        pixmap = pil_to_qpixmap(pil_image)

        assert pixmap is not None
        assert pixmap.width() == 2000
        assert pixmap.height() == 2000


# =============================================================================
# Mocked Qt Tests - Error Paths (headless, CI-safe)
# =============================================================================


@pytest.mark.headless
class TestPilToQPixmapMocked:
    """Test pil_to_qpixmap function with mocked Qt dependencies.

    These tests run in headless environments and cover error handling paths
    that cannot be tested with real Qt.
    """

    def test_none_input(self):
        """Test handling of None input"""
        result = pil_to_qpixmap(None)
        assert result is None

    def test_falsy_image_input(self):
        """Test handling of image that evaluates to False"""
        mock_image = MagicMock()
        mock_image.__bool__.return_value = False

        result = pil_to_qpixmap(mock_image)
        assert result is None

    @patch("core.services.image_utils.QPixmap")
    def test_successful_conversion(self, mock_qpixmap_class):
        """Test successful PIL to QPixmap conversion"""
        pil_image = Image.new("RGB", (10, 10), "red")

        mock_pixmap = MagicMock()
        mock_pixmap.loadFromData.return_value = True
        mock_pixmap.size.return_value.width.return_value = 10
        mock_pixmap.size.return_value.height.return_value = 10
        mock_qpixmap_class.return_value = mock_pixmap

        result = pil_to_qpixmap(pil_image)

        assert result == mock_pixmap
        mock_pixmap.loadFromData.assert_called_once()

        # Verify PNG data was passed
        call_args = mock_pixmap.loadFromData.call_args[0][0]
        assert call_args.startswith(b"\x89PNG\r\n\x1a\n")

    @patch("core.services.image_utils.QPixmap")
    def test_buffer_too_small(self, mock_qpixmap_class, caplog):
        """Test handling when buffer is too small"""
        pil_image = Image.new("RGB", (10, 10), "red")

        original_save = pil_image.save

        def mock_save(fp, format=None, **params):
            if hasattr(fp, "write"):
                fp.write(b"tiny")
            else:
                original_save(fp, format, **params)

        pil_image.save = mock_save

        with caplog.at_level(logging.ERROR):
            result = pil_to_qpixmap(pil_image)

        assert result is None
        assert "Buffer data too small: 4 bytes" in caplog.text

    @patch("core.services.image_utils.QPixmap")
    def test_invalid_png_header(self, mock_qpixmap_class, caplog):
        """Test handling when buffer doesn't have PNG header"""
        pil_image = Image.new("RGB", (10, 10), "blue")

        def mock_save(fp, format=None, **params):
            if hasattr(fp, "write"):
                fp.write(b"NOT_A_PNG_HEADER_12345678")

        pil_image.save = mock_save

        with caplog.at_level(logging.ERROR):
            result = pil_to_qpixmap(pil_image)

        assert result is None
        assert "Buffer data doesn't start with PNG header" in caplog.text

    @patch("core.services.image_utils.QPixmap")
    def test_qpixmap_loadfromdata_failure(self, mock_qpixmap_class, caplog):
        """Test handling when QPixmap.loadFromData fails"""
        pil_image = Image.new("RGB", (10, 10), "blue")

        mock_pixmap = MagicMock()
        mock_pixmap.loadFromData.return_value = False
        mock_qpixmap_class.return_value = mock_pixmap

        with caplog.at_level(logging.ERROR):
            result = pil_to_qpixmap(pil_image)

        assert result is None
        assert "QPixmap.loadFromData() failed" in caplog.text

    def test_save_exception(self, caplog):
        """Test handling of exception during save"""
        pil_image = Image.new("RGB", (10, 10), "green")

        with patch.object(pil_image, "save", side_effect=Exception("Save failed!")):
            with caplog.at_level(logging.ERROR):
                result = pil_to_qpixmap(pil_image)

        assert result is None
        assert "Failed to convert PIL to QPixmap" in caplog.text
        assert "Save failed!" in caplog.text

    def test_attribute_error_handling(self, caplog):
        """Test handling when image lacks expected attributes"""

        class FakeImage:
            def __bool__(self):
                return True

            def save(self, buffer, format):
                raise AttributeError("'FakeImage' object has no attribute 'size'")

        fake_image = FakeImage()

        with caplog.at_level(logging.ERROR):
            result = pil_to_qpixmap(fake_image)

        assert result is None
        assert "Failed to convert PIL to QPixmap" in caplog.text
        assert "size=unknown, mode=unknown" in caplog.text

    @patch("core.services.image_utils.QPixmap")
    def test_different_image_modes(self, mock_qpixmap_class):
        """Test conversion of various PIL image modes"""
        mock_pixmap = MagicMock()
        mock_pixmap.loadFromData.return_value = True
        mock_pixmap.size.return_value.width.return_value = 5
        mock_pixmap.size.return_value.height.return_value = 5
        mock_qpixmap_class.return_value = mock_pixmap

        modes_to_test = ["RGB", "RGBA", "L", "P", "1"]

        for mode in modes_to_test:
            if mode == "1":
                color = 1
            elif mode == "L":
                color = 128
            elif mode == "P":
                color = 0
            elif mode == "RGBA":
                color = (255, 0, 0, 128)
            else:
                color = (255, 0, 0)

            pil_image = Image.new(mode, (5, 5), color)
            result = pil_to_qpixmap(pil_image)

            assert result is not None, f"Failed for mode {mode}"

    @patch("core.services.image_utils.QPixmap")
    def test_logging_debug_messages(self, mock_qpixmap_class, caplog):
        """Test debug logging during conversion"""
        pil_image = Image.new("RGBA", (20, 30))

        mock_pixmap = MagicMock()
        mock_pixmap.loadFromData.return_value = True
        mock_pixmap.size.return_value.width.return_value = 20
        mock_pixmap.size.return_value.height.return_value = 30
        mock_qpixmap_class.return_value = mock_pixmap

        with caplog.at_level(logging.DEBUG):
            result = pil_to_qpixmap(pil_image)

        assert result is not None
        assert "Converting PIL image: size=(20, 30), mode=RGBA" in caplog.text
        assert "PIL image saved to buffer:" in caplog.text
        assert "Loading" in caplog.text
        assert "bytes into QPixmap" in caplog.text
        assert "Successfully created QPixmap: 20x30" in caplog.text

    @patch("core.services.image_utils.QPixmap")
    def test_empty_buffer_after_save(self, mock_qpixmap_class):
        """Test handling when save produces empty buffer"""
        pil_image = Image.new("RGB", (10, 10), "yellow")

        def mock_save(fp, format=None, **params):
            if hasattr(fp, "write"):
                pass  # Don't write anything

        pil_image.save = mock_save

        result = pil_to_qpixmap(pil_image)

        assert result is None

    def test_io_error_during_save(self, caplog):
        """Test handling of IOError during save"""
        pil_image = Image.new("RGB", (10, 10))

        with patch("core.services.image_utils.io.BytesIO") as mock_bytesio:
            mock_buffer = MagicMock()
            mock_buffer.write.side_effect = OSError("Disk full")
            mock_bytesio.return_value = mock_buffer

            with caplog.at_level(logging.ERROR):
                result = pil_to_qpixmap(pil_image)

            assert result is None
            assert "Failed to convert PIL to QPixmap" in caplog.text


# =============================================================================
# Pure PIL Tests - Checkerboard Pattern (headless)
# =============================================================================


@pytest.mark.headless
class TestCreateCheckerboardPattern:
    """Test checkerboard pattern creation - pure PIL, no Qt dependency."""

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
