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

# Serial execution required: Real Qt components
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Real Qt component tests may create background threads"),
    pytest.mark.integration,
]


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
