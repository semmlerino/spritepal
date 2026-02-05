"""Tests for Bayer dithering in palette quantization."""

import numpy as np
import pytest
from PIL import Image

from core.palette_utils import (
    quantize_to_index_map,
    quantize_with_mappings,
)


class TestBayerDithering:
    """Tests for ordered Bayer dithering implementation."""

    @pytest.fixture
    def gradient_image(self) -> Image.Image:
        """Create a grayscale gradient image."""
        width, height = 100, 100
        img = Image.new("RGBA", (width, height))
        pixels = []
        for y in range(height):
            for x in range(width):
                val = int(255 * (x + y) / (width + height - 2))
                pixels.append((val, val, val, 255))
        img.putdata(pixels)
        return img

    @pytest.fixture
    def bw_palette(self) -> list[tuple[int, int, int]]:
        """Create a black and white palette (plus padding)."""
        # Index 0 = Transparent (ignored for opaque pixels)
        # Index 1 = Black
        # Index 2 = White
        # Rest = Black
        return [(0, 0, 0), (0, 0, 0), (255, 255, 255)] + [(0, 0, 0)] * 13

    def test_quantize_with_mappings_dithering(
        self, gradient_image: Image.Image, bw_palette: list[tuple[int, int, int]]
    ) -> None:
        """Test that quantize_with_mappings respects dithering settings."""
        # No dither
        img_no_dither = quantize_with_mappings(
            gradient_image,
            bw_palette,
            {},
            dither_mode="none",
            dither_strength=0.0,
        )

        # With dither
        img_dither = quantize_with_mappings(
            gradient_image,
            bw_palette,
            {},
            dither_mode="bayer",
            dither_strength=1.0,
        )

        data_no_dither = list(img_no_dither.getdata())
        data_dither = list(img_dither.getdata())

        # Should be different
        assert data_no_dither != data_dither, "Dithering should affect output"

        # Check that dithered image uses more than just simple thresholding
        # (visual check logic: index distribution should differ)
        indices_no_dither = np.array(img_no_dither)
        indices_dither = np.array(img_dither)

        assert not np.array_equal(indices_no_dither, indices_dither)

    def test_quantize_to_index_map_dithering(
        self, gradient_image: Image.Image, bw_palette: list[tuple[int, int, int]]
    ) -> None:
        """Test that quantize_to_index_map respects dithering settings."""
        # No dither
        idx_no_dither = quantize_to_index_map(
            gradient_image,
            bw_palette,
            {},
            dither_mode="none",
            dither_strength=0.0,
        )

        # With dither
        idx_dither = quantize_to_index_map(
            gradient_image,
            bw_palette,
            {},
            dither_mode="bayer",
            dither_strength=1.0,
        )

        # Should be different
        assert not np.array_equal(idx_no_dither, idx_dither), "Dithering should affect index map"

    def test_dithering_strength_scaling(
        self, gradient_image: Image.Image, bw_palette: list[tuple[int, int, int]]
    ) -> None:
        """Test that different dithering strengths produce different results."""
        idx_weak = quantize_to_index_map(
            gradient_image,
            bw_palette,
            {},
            dither_mode="bayer",
            dither_strength=0.1,
        )

        idx_strong = quantize_to_index_map(
            gradient_image,
            bw_palette,
            {},
            dither_mode="bayer",
            dither_strength=1.0,
        )

        assert not np.array_equal(idx_weak, idx_strong), "Strength should affect dithering"

    def test_dithering_mode_none_ignores_strength(
        self, gradient_image: Image.Image, bw_palette: list[tuple[int, int, int]]
    ) -> None:
        """Test that mode='none' ignores strength parameter."""
        idx_none = quantize_to_index_map(
            gradient_image,
            bw_palette,
            {},
            dither_mode="none",
            dither_strength=0.0,
        )

        idx_none_strong = quantize_to_index_map(
            gradient_image,
            bw_palette,
            {},
            dither_mode="none",
            dither_strength=1.0,
        )

        assert np.array_equal(idx_none, idx_none_strong), "Mode 'none' should ignore strength"
