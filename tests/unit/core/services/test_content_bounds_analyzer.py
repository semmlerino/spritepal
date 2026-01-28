"""Tests for ContentBoundsAnalyzer."""

from __future__ import annotations

import pytest
from PIL import Image

from core.services.content_bounds_analyzer import ContentBoundsAnalyzer, get_content_bbox


class TestComputeCentroid:
    """Tests for ContentBoundsAnalyzer.compute_centroid()."""

    def test_uniform_square_returns_center(self) -> None:
        """Uniform opaque square should have centroid at geometric center."""
        # 10x10 solid white square
        image = Image.new("RGBA", (10, 10), (255, 255, 255, 255))

        centroid_x, centroid_y = ContentBoundsAnalyzer.compute_centroid(image)

        # Center of 10x10 image is at (4.5, 4.5) - average of 0-9
        assert abs(centroid_x - 4.5) < 0.01
        assert abs(centroid_y - 4.5) < 0.01

    def test_l_shaped_sprite_centroid_toward_main_body(self) -> None:
        """L-shaped sprite should have centroid pulled toward the main body.

        Creates a sprite with:
        - Main body: 60x100 pixels (area = 6000)
        - Protrusion: 20x20 pixels (area = 400)

        The centroid should be closer to the body center than the bbox center.
        """
        # 80x100 canvas
        image = Image.new("RGBA", (80, 100), (0, 0, 0, 0))

        # Main body at x=20-80, y=0-100 (right 60 columns, full height)
        for x in range(20, 80):
            for y in range(100):
                image.putpixel((x, y), (255, 255, 255, 255))

        # Protrusion at x=0-20, y=80-100 (bottom-left corner)
        for x in range(20):
            for y in range(80, 100):
                image.putpixel((x, y), (255, 255, 255, 255))

        centroid_x, centroid_y = ContentBoundsAnalyzer.compute_centroid(image)

        # Bbox center would be at (40, 50)
        # Body center is at (50, 50)
        # Protrusion center is at (10, 90)
        # Centroid should be between bbox center and body center, pulled toward body
        # Expected: closer to 50 than to 40 for x

        # Verify centroid is pulled toward the main body (x > 40)
        assert centroid_x > 40, f"Expected centroid_x > 40, got {centroid_x}"
        # But not all the way to body center due to protrusion influence
        assert centroid_x < 50, f"Expected centroid_x < 50, got {centroid_x}"

    def test_empty_image_returns_image_center(self) -> None:
        """Fully transparent image should return geometric center."""
        image = Image.new("RGBA", (20, 30), (0, 0, 0, 0))

        centroid_x, centroid_y = ContentBoundsAnalyzer.compute_centroid(image)

        assert centroid_x == 10.0
        assert centroid_y == 15.0

    def test_single_pixel_returns_pixel_position(self) -> None:
        """Single opaque pixel should have centroid at that pixel."""
        image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        image.putpixel((3, 7), (255, 255, 255, 255))

        centroid_x, centroid_y = ContentBoundsAnalyzer.compute_centroid(image)

        assert centroid_x == 3.0
        assert centroid_y == 7.0

    def test_alpha_weighting(self) -> None:
        """Pixels with higher alpha should have more influence on centroid."""
        image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))

        # High alpha pixel at (2, 5) with alpha=255
        image.putpixel((2, 5), (255, 255, 255, 255))
        # Low alpha pixel at (8, 5) with alpha=51 (1/5 of 255)
        image.putpixel((8, 5), (255, 255, 255, 51))

        centroid_x, centroid_y = ContentBoundsAnalyzer.compute_centroid(image)

        # Centroid should be pulled toward the high-alpha pixel
        # With alpha 255 vs 51, the centroid should be at:
        # x = (2*255 + 8*51) / (255+51) = (510 + 408) / 306 = 918/306 ≈ 3.0
        assert centroid_y == 5.0  # y should be exactly 5
        assert centroid_x < 5.0, f"Expected centroid_x < 5.0, got {centroid_x}"
        assert centroid_x > 2.0, f"Expected centroid_x > 2.0, got {centroid_x}"

    def test_rgb_image_conversion(self) -> None:
        """RGB image should be converted to RGBA and treated as fully opaque."""
        # RGB image (no alpha channel)
        image = Image.new("RGB", (10, 10), (255, 255, 255))

        centroid_x, centroid_y = ContentBoundsAnalyzer.compute_centroid(image)

        # Should be treated as fully opaque, centroid at center
        assert abs(centroid_x - 4.5) < 0.01
        assert abs(centroid_y - 4.5) < 0.01


class TestGetContentBbox:
    """Tests for get_content_bbox() function."""

    def test_transparent_background_uses_alpha(self) -> None:
        """Image with transparent background should use alpha-based bbox."""
        # 100x100 canvas, transparent background
        image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        # Draw opaque content in center (30-70 x 30-70)
        for x in range(30, 70):
            for y in range(30, 70):
                image.putpixel((x, y), (255, 255, 255, 255))

        bbox = get_content_bbox(image)

        assert bbox == (30, 30, 70, 70)

    def test_solid_background_detects_content(self) -> None:
        """Image with solid background should detect actual content via color."""
        # 100x100 canvas with white background
        image = Image.new("RGB", (100, 100), (255, 255, 255))
        # Draw dark content in center (30-70 x 30-70)
        for x in range(30, 70):
            for y in range(30, 70):
                image.putpixel((x, y), (50, 50, 50))

        bbox = get_content_bbox(image)

        # Should detect the dark content, not return full bounds
        assert bbox[0] == 30  # left
        assert bbox[1] == 30  # top
        assert bbox[2] == 70  # right
        assert bbox[3] == 70  # bottom

    def test_empty_image_returns_full_bounds(self) -> None:
        """Fully transparent image should return full bounds."""
        image = Image.new("RGBA", (50, 60), (0, 0, 0, 0))

        bbox = get_content_bbox(image)

        # getbbox returns None for transparent, so we fall back to full bounds
        assert bbox == (0, 0, 50, 60)

    def test_uniform_color_returns_full_bounds(self) -> None:
        """Uniform solid color image should return full bounds."""
        image = Image.new("RGB", (50, 60), (128, 128, 128))

        bbox = get_content_bbox(image)

        # No distinguishable content, return full bounds
        assert bbox == (0, 0, 50, 60)
