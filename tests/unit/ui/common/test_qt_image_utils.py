"""Tests for Qt image conversion utilities.

NOTE: This test file exists for backward compatibility after consolidating
ui.common.qt_image_utils into core.services.image_utils.

The more comprehensive test suite is at tests/ui/components/test_image_utils.py
which covers error handling, edge cases, and mocked paths.
"""

from __future__ import annotations

import pytest
from PIL import Image
from PySide6.QtGui import QPixmap

from core.services.image_utils import pil_to_qpixmap


class TestPilToQpixmap:
    """Tests for pil_to_qpixmap function (consolidated from ui.common)."""

    def test_converts_rgba_image(self, qapp: None) -> None:
        """Convert a simple RGBA PIL image to QPixmap."""
        pil_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))

        result = pil_to_qpixmap(pil_img)

        assert result is not None
        assert isinstance(result, QPixmap)
        assert result.width() == 32
        assert result.height() == 32
        assert not result.isNull()

    def test_converts_rgb_image(self, qapp: None) -> None:
        """Convert an RGB PIL image to QPixmap."""
        pil_img = Image.new("RGB", (16, 24), (0, 255, 0))

        result = pil_to_qpixmap(pil_img)

        assert result is not None
        assert isinstance(result, QPixmap)
        assert result.width() == 16
        assert result.height() == 24
        assert not result.isNull()

    def test_preserves_transparency(self, qapp: None) -> None:
        """Verify transparency is preserved in conversion."""
        pil_img = Image.new("RGBA", (8, 8), (0, 0, 255, 128))

        result = pil_to_qpixmap(pil_img)

        assert result is not None
        # Convert back to QImage to verify alpha
        qimg = result.toImage()
        assert qimg.hasAlphaChannel()

    def test_handles_various_sizes(self, qapp: None) -> None:
        """Convert images of various sizes."""
        sizes = [(1, 1), (8, 8), (64, 32), (100, 200)]

        for width, height in sizes:
            pil_img = Image.new("RGBA", (width, height), (128, 128, 128, 255))
            result = pil_to_qpixmap(pil_img)

            assert result is not None
            assert result.width() == width
            assert result.height() == height
