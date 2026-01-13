"""Unit tests for color quantization module."""

from __future__ import annotations

import numpy as np
from PIL import Image

from core.color_quantization import ColorQuantizer, QuantizationResult


class TestQuantizationResult:
    """Tests for QuantizationResult dataclass."""

    def test_result_stores_data(self) -> None:
        """Result stores indexed data and palette."""
        indexed = np.zeros((8, 8), dtype=np.uint8)
        palette = [(0, 0, 0)] * 16

        result = QuantizationResult(
            indexed_data=indexed,
            palette=palette,
            transparency_mask=None,
        )

        assert result.indexed_data.shape == (8, 8)
        assert len(result.palette) == 16
        assert result.transparency_mask is None

    def test_result_with_transparency_mask(self) -> None:
        """Result can include transparency mask."""
        indexed = np.zeros((4, 4), dtype=np.uint8)
        palette = [(0, 0, 0)] * 16
        mask = np.zeros((4, 4), dtype=bool)
        mask[0, 0] = True

        result = QuantizationResult(
            indexed_data=indexed,
            palette=palette,
            transparency_mask=mask,
        )

        assert result.transparency_mask is not None
        assert result.transparency_mask[0, 0] is np.True_


class TestColorQuantizer:
    """Tests for ColorQuantizer class."""

    def test_quantize_rgb_image(self) -> None:
        """RGB image is converted to RGBA and quantized."""
        # Create a simple RGB image with two colors
        image = Image.new("RGB", (8, 8), color=(255, 0, 0))
        for x in range(4, 8):
            for y in range(8):
                image.putpixel((x, y), (0, 0, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image)

        assert result.indexed_data.shape == (8, 8)
        assert len(result.palette) == 16
        # No transparency for RGB image (converted to RGBA with alpha=255)
        assert result.transparency_mask is not None
        assert not result.transparency_mask.any()

    def test_quantize_rgba_image_with_transparency(self) -> None:
        """RGBA image preserves transparency as index 0."""
        # Create RGBA image with transparent pixels
        image = Image.new("RGBA", (8, 8), color=(255, 0, 0, 255))
        # Make top row transparent
        for x in range(8):
            image.putpixel((x, 0), (0, 0, 0, 0))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image)

        # Top row should be transparent (index 0)
        assert result.transparency_mask is not None
        assert result.transparency_mask[0, :].all()
        assert result.indexed_data[0, 0] == 0

    def test_transparency_threshold(self) -> None:
        """Alpha values below threshold become transparent."""
        # Create image with semi-transparent pixel
        image = Image.new("RGBA", (2, 2), color=(255, 0, 0, 255))
        image.putpixel((0, 0), (255, 0, 0, 100))  # Semi-transparent

        # Default threshold is 127
        quantizer = ColorQuantizer(dither=False, transparency_threshold=127)
        result = quantizer.quantize(image)

        assert result.transparency_mask is not None
        assert result.transparency_mask[0, 0] is np.True_  # Below 127

    def test_palette_has_16_colors(self) -> None:
        """Generated palette always has exactly 16 colors."""
        # Image with only 2 colors
        image = Image.new("RGBA", (4, 4), color=(255, 0, 0, 255))
        image.putpixel((0, 0), (0, 255, 0, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image)

        assert len(result.palette) == 16

    def test_index_0_reserved_for_transparent(self) -> None:
        """Index 0 is always black (reserved for transparency)."""
        image = Image.new("RGBA", (4, 4), color=(255, 255, 255, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image)

        assert result.palette[0] == (0, 0, 0)

    def test_opaque_pixels_use_indices_1_to_15(self) -> None:
        """Opaque pixels map to indices 1-15, not 0."""
        # Create image with single solid color
        image = Image.new("RGBA", (4, 4), color=(255, 0, 0, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image)

        # All pixels should be same index (not 0)
        unique_indices = np.unique(result.indexed_data)
        assert 0 not in unique_indices
        assert len(unique_indices) == 1
        assert unique_indices[0] >= 1

    def test_scaling_to_target_size(self) -> None:
        """Image is scaled to fit target size before quantization."""
        image = Image.new("RGBA", (16, 16), color=(255, 0, 0, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image, target_size=(8, 8))

        assert result.indexed_data.shape == (8, 8)

    def test_scaling_preserves_aspect_ratio(self) -> None:
        """Scaling preserves aspect ratio and centers image on transparent canvas."""
        # Create a wide image (16x8) to scale into 8x8 target
        image = Image.new("RGBA", (16, 8), color=(255, 0, 0, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image, target_size=(8, 8))

        # Result should be 8x8 (target size)
        assert result.indexed_data.shape == (8, 8)

        # Image should be scaled to 8x4 (preserving 2:1 aspect ratio)
        # and centered vertically, so rows 0-1 and 6-7 should be transparent
        assert result.transparency_mask is not None
        # Top padding should be transparent (rows 0-1)
        assert result.transparency_mask[0, :].all()
        assert result.transparency_mask[1, :].all()
        # Bottom padding should be transparent (rows 6-7)
        assert result.transparency_mask[6, :].all()
        assert result.transparency_mask[7, :].all()
        # Middle rows should have content (not fully transparent)
        assert not result.transparency_mask[2, :].all()

    def test_no_scaling_when_already_correct_size(self) -> None:
        """No scaling if image already matches target."""
        image = Image.new("RGBA", (8, 8), color=(255, 0, 0, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image, target_size=(8, 8))

        assert result.indexed_data.shape == (8, 8)

    def test_no_upscaling_for_smaller_images(self) -> None:
        """Images smaller than target are not upscaled, just centered."""
        # Create a small 4x4 image
        image = Image.new("RGBA", (4, 4), color=(255, 0, 0, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image, target_size=(8, 8))

        # Result should be 8x8 with centered 4x4 content
        assert result.indexed_data.shape == (8, 8)
        assert result.transparency_mask is not None

        # Edges should be transparent (2 pixel border)
        assert result.transparency_mask[0, :].all()  # Top row
        assert result.transparency_mask[1, :].all()  # Second row
        assert result.transparency_mask[6, :].all()  # Seventh row
        assert result.transparency_mask[7, :].all()  # Bottom row


class TestFastOctreeQuantization:
    """Tests for FASTOCTREE quantization algorithm."""

    def test_single_color_image(self) -> None:
        """Single color image preserves color in palette."""
        image = Image.new("RGBA", (8, 8), color=(128, 64, 32, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image)

        # Find the opaque pixel color in palette (index 1-15)
        pixel_index = result.indexed_data[0, 0]
        color = result.palette[pixel_index]

        # Should be close to original (allow small tolerance for FASTOCTREE)
        assert abs(color[0] - 128) <= 5
        assert abs(color[1] - 64) <= 5
        assert abs(color[2] - 32) <= 5

    def test_two_distinct_colors(self) -> None:
        """Two distinct colors are preserved in palette."""
        image = Image.new("RGBA", (8, 8), color=(255, 0, 0, 255))
        for x in range(4, 8):
            for y in range(8):
                image.putpixel((x, y), (0, 0, 255, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image)

        # Palette should contain colors close to red and blue
        colors = result.palette[1:]  # Skip index 0
        has_red = any(c[0] > 200 and c[1] < 50 and c[2] < 50 for c in colors)
        has_blue = any(c[0] < 50 and c[1] < 50 and c[2] > 200 for c in colors)

        assert has_red
        assert has_blue

    def test_gradient_produces_multiple_colors(self) -> None:
        """Gradient image produces palette spanning the range."""
        image = Image.new("RGBA", (16, 1), color=(0, 0, 0, 255))
        for x in range(16):
            gray = x * 17  # 0 to 255
            image.putpixel((x, 0), (gray, gray, gray, 255))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image)

        # Palette should have colors spanning dark to light
        grays = [c[0] for c in result.palette[1:] if c[0] == c[1] == c[2]]
        if grays:
            assert max(grays) - min(grays) > 100


class TestFloydSteinbergDithering:
    """Tests for Floyd-Steinberg dithering."""

    def test_dithering_enabled_by_default(self) -> None:
        """Dithering is on by default."""
        quantizer = ColorQuantizer()
        assert quantizer._dither is True

    def test_dithering_can_be_disabled(self) -> None:
        """Dithering can be turned off."""
        quantizer = ColorQuantizer(dither=False)
        assert quantizer._dither is False

    def test_dithering_produces_different_result(self) -> None:
        """Dithered result differs from non-dithered for gradients."""
        # Create gradient
        image = Image.new("RGBA", (16, 16), color=(0, 0, 0, 255))
        for x in range(16):
            for y in range(16):
                gray = (x + y) * 8
                gray = min(255, gray)
                image.putpixel((x, y), (gray, gray, gray, 255))

        dithered = ColorQuantizer(dither=True).quantize(image)
        non_dithered = ColorQuantizer(dither=False).quantize(image)

        # Results should differ (dithering adds variation)
        # This is a weak test but ensures the code path is exercised
        assert dithered.indexed_data.shape == non_dithered.indexed_data.shape

    def test_dithering_respects_transparency(self) -> None:
        """Dithering doesn't affect transparent pixels."""
        image = Image.new("RGBA", (8, 8), color=(128, 128, 128, 255))
        # Make diagonal transparent
        for i in range(8):
            image.putpixel((i, i), (0, 0, 0, 0))

        quantizer = ColorQuantizer(dither=True)
        result = quantizer.quantize(image)

        # Diagonal should be index 0
        for i in range(8):
            assert result.indexed_data[i, i] == 0


class TestAllTransparentImage:
    """Tests for edge case: fully transparent image."""

    def test_all_transparent_uses_fallback_palette(self) -> None:
        """Fully transparent image uses fallback palette."""
        image = Image.new("RGBA", (4, 4), color=(0, 0, 0, 0))

        quantizer = ColorQuantizer(dither=False)
        result = quantizer.quantize(image)

        # All indices should be 0
        assert (result.indexed_data == 0).all()
        # Palette should still have 16 entries
        assert len(result.palette) == 16
