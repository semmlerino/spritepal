"""
Unit tests for image utils with mocked Qt dependencies.
These tests run in headless environments without requiring Qt GUI.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from utils.image_utils import pil_to_qpixmap

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.parallel_safe,
    pytest.mark.rom_data,
    pytest.mark.unit,
    pytest.mark.ci_safe,
    pytest.mark.no_manager_setup,  # Pure unit tests with mocked dependencies
]

class TestPilToQPixmapMocked:
    """Test pil_to_qpixmap function with mocked Qt dependencies"""

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
        # Create a small test image
        pil_image = Image.new("RGB", (10, 10), "red")

        # Mock QPixmap
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
        # Create a real PIL image
        pil_image = Image.new("RGB", (10, 10), "red")

        # Override save to write tiny data to buffer
        original_save = pil_image.save
        def mock_save(fp, format=None, **params):
            # Write tiny data to the buffer
            if hasattr(fp, "write"):
                fp.write(b"tiny")
            else:
                # If fp is a path, call original save
                original_save(fp, format, **params)

        pil_image.save = mock_save

        with caplog.at_level(logging.ERROR):
            result = pil_to_qpixmap(pil_image)

        assert result is None
        assert "Buffer data too small: 4 bytes" in caplog.text

    @patch("core.services.image_utils.QPixmap")
    def test_invalid_png_header(self, mock_qpixmap_class, caplog):
        """Test handling when buffer doesn't have PNG header"""
        # Create a real PIL image
        pil_image = Image.new("RGB", (10, 10), "blue")

        # Override save to write non-PNG data
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

        # Mock QPixmap to fail loading
        mock_pixmap = MagicMock()
        mock_pixmap.loadFromData.return_value = False
        mock_qpixmap_class.return_value = mock_pixmap

        with caplog.at_level(logging.ERROR):
            result = pil_to_qpixmap(pil_image)

        assert result is None
        assert "QPixmap.loadFromData() failed" in caplog.text

    def test_save_exception(self, caplog):
        """Test handling of exception during save"""
        # Create a real PIL image but patch save to raise exception
        pil_image = Image.new("RGB", (10, 10), "green")

        with patch.object(pil_image, "save", side_effect=Exception("Save failed!")):
            with caplog.at_level(logging.ERROR):
                result = pil_to_qpixmap(pil_image)

        assert result is None
        assert "Failed to convert PIL to QPixmap" in caplog.text
        assert "Save failed!" in caplog.text

    def test_attribute_error_handling(self, caplog):
        """Test handling when image lacks expected attributes"""
        # Create an object that's truthy but isn't a PIL Image
        class FakeImage:
            def __bool__(self):
                return True

            def save(self, buffer, format):
                # This will raise AttributeError when trying to access image properties
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
        # Mock successful QPixmap
        mock_pixmap = MagicMock()
        mock_pixmap.loadFromData.return_value = True
        mock_pixmap.size.return_value.width.return_value = 5
        mock_pixmap.size.return_value.height.return_value = 5
        mock_qpixmap_class.return_value = mock_pixmap

        modes_to_test = ["RGB", "RGBA", "L", "P", "1"]

        for mode in modes_to_test:
            # Create appropriate color for mode
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

        # Mock successful QPixmap
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
        # Create a real PIL image
        pil_image = Image.new("RGB", (10, 10), "yellow")

        # Override save to write nothing
        def mock_save(fp, format=None, **params):
            if hasattr(fp, "write"):
                pass  # Don't write anything

        pil_image.save = mock_save

        result = pil_to_qpixmap(pil_image)

        assert result is None

    def test_io_error_during_save(self, caplog):
        """Test handling of IOError during save"""
        pil_image = Image.new("RGB", (10, 10))

        # Mock BytesIO to raise IOError
        with patch("core.services.image_utils.io.BytesIO") as mock_bytesio:
            mock_buffer = MagicMock()
            mock_buffer.write.side_effect = OSError("Disk full")
            mock_bytesio.return_value = mock_buffer

            with caplog.at_level(logging.ERROR):
                result = pil_to_qpixmap(pil_image)

            assert result is None
            assert "Failed to convert PIL to QPixmap" in caplog.text

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
