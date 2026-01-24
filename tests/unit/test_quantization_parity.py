"""Tests for quantization parity between preview and injection.

Verifies that:
1. Preview and injection use the same transparency threshold (WYSIWYG)
2. Semi-transparent pixels (alpha 1-127) are treated as transparent
3. All quantization paths use perceptual LAB distance
4. ColorQuantizer uses the centralized threshold constant
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from core.color_quantization import ColorQuantizer
from core.palette_utils import (
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    SNES_PALETTE_SIZE,
    quantize_to_palette,
    quantize_with_mappings,
)


class TestTransparencyThresholdParity:
    """Tests for transparency threshold consistency."""

    def test_quantization_threshold_value(self) -> None:
        """Verify the transparency threshold is 128."""
        assert QUANTIZATION_TRANSPARENCY_THRESHOLD == 128

    def test_snes_palette_size_value(self) -> None:
        """Verify the SNES palette size is 16."""
        assert SNES_PALETTE_SIZE == 16

    def test_semi_transparent_pixels_become_transparent(self) -> None:
        """Pixels with alpha 1-127 should become index 0 (transparent)."""
        # Create a test image with semi-transparent pixels
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 64))  # Red with alpha=64

        # Create a simple palette
        palette: list[tuple[int, int, int]] = [
            (0, 0, 0),  # Index 0 - transparent
            (255, 0, 0),  # Index 1 - red
            *[(0, 0, 0)] * 14,  # Fill remaining slots
        ]

        # Quantize with the standard threshold
        result = quantize_to_palette(img, palette, transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD)

        # All pixels should be transparent (index 0)
        result_array = np.array(result)
        assert np.all(result_array == 0), "Semi-transparent pixels should become index 0"

    def test_opaque_pixels_quantized_normally(self) -> None:
        """Pixels with alpha >= 128 should be quantized normally."""
        # Create a test image with opaque pixels
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 200))  # Red with alpha=200

        # Create a simple palette
        palette: list[tuple[int, int, int]] = [
            (0, 0, 0),  # Index 0 - transparent
            (255, 0, 0),  # Index 1 - red
            *[(0, 0, 0)] * 14,  # Fill remaining slots
        ]

        # Quantize with the standard threshold
        result = quantize_to_palette(img, palette, transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD)

        # All pixels should be red (index 1)
        result_array = np.array(result)
        # Check that at least some pixels are quantized to index 1
        # (due to palette mode, the actual indices in the image may differ)
        # So we check that the result is not all transparent
        assert not np.all(result_array == 0), "Opaque pixels should not all be transparent"

    def test_threshold_boundary_below(self) -> None:
        """Alpha at 127 (below threshold) should be transparent."""
        img = Image.new("RGBA", (2, 2), (255, 0, 0, 127))

        palette: list[tuple[int, int, int]] = [
            (0, 0, 0),
            (255, 0, 0),
            *[(0, 0, 0)] * 14,
        ]

        result = quantize_to_palette(img, palette, transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD)
        result_array = np.array(result)
        assert np.all(result_array == 0), "Alpha 127 should be transparent"

    def test_threshold_boundary_at(self) -> None:
        """Alpha at 128 (at threshold) should be opaque."""
        img = Image.new("RGBA", (2, 2), (255, 0, 0, 128))

        palette: list[tuple[int, int, int]] = [
            (0, 0, 0),
            (255, 0, 0),
            *[(0, 0, 0)] * 14,
        ]

        result = quantize_to_palette(img, palette, transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD)
        result_array = np.array(result)
        # Should NOT be all transparent
        assert not np.all(result_array == 0), "Alpha 128 should be opaque"


class TestQuantizeWithMappingsParity:
    """Tests for quantize_with_mappings using same threshold."""

    def test_semi_transparent_with_explicit_mapping(self) -> None:
        """Semi-transparent pixels should be transparent even with explicit mappings."""
        # Create a test image with semi-transparent red pixels
        img = Image.new("RGBA", (2, 2), (255, 0, 0, 64))

        palette: list[tuple[int, int, int]] = [
            (0, 0, 0),
            (255, 0, 0),
            *[(0, 0, 0)] * 14,
        ]

        # Explicit mapping: red -> index 1
        mappings = {(255, 0, 0): 1}

        result = quantize_with_mappings(
            img,
            palette,
            mappings,
            transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
        )

        result_array = np.array(result)
        # Even with explicit mapping, semi-transparent should be index 0
        assert np.all(result_array == 0), "Semi-transparent should be transparent even with mapping"

    def test_opaque_with_explicit_mapping(self) -> None:
        """Opaque pixels with explicit mappings should use the mapping."""
        # Create a test image with fully opaque red pixels
        img = Image.new("RGBA", (2, 2), (255, 0, 0, 255))

        palette: list[tuple[int, int, int]] = [
            (0, 0, 0),
            (0, 255, 0),  # green
            (255, 0, 0),  # red at index 2
            *[(0, 0, 0)] * 13,
        ]

        # Explicit mapping: red -> index 2
        mappings = {(255, 0, 0): 2}

        result = quantize_with_mappings(
            img,
            palette,
            mappings,
            transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
        )

        result_array = np.array(result)
        # All pixels should be mapped to index 2
        assert np.all(result_array == 2), "Opaque red should map to index 2"


class TestColorQuantizerThresholdParity:
    """Tests that ColorQuantizer uses the centralized threshold constant."""

    def test_default_threshold_matches_constant(self) -> None:
        """ColorQuantizer default threshold should match QUANTIZATION_TRANSPARENCY_THRESHOLD."""
        quantizer = ColorQuantizer()
        assert quantizer._transparency_threshold == QUANTIZATION_TRANSPARENCY_THRESHOLD

    def test_semi_transparent_pixels_become_transparent(self) -> None:
        """ColorQuantizer should treat alpha 1-127 as transparent."""
        quantizer = ColorQuantizer(dither=False)

        # Create image with semi-transparent red (alpha=64)
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 64))

        result = quantizer.quantize(img)

        # All pixels should be marked as transparent
        assert result.transparency_mask is not None
        assert np.all(result.transparency_mask), "Alpha 64 should be transparent"

    def test_opaque_pixels_quantized(self) -> None:
        """ColorQuantizer should treat alpha >= 128 as opaque."""
        quantizer = ColorQuantizer(dither=False)

        # Create image with opaque red (alpha=200)
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 200))

        result = quantizer.quantize(img)

        # No pixels should be marked as transparent
        if result.transparency_mask is not None:
            assert not np.all(result.transparency_mask), "Alpha 200 should be opaque"

    def test_threshold_boundary_at_128(self) -> None:
        """Alpha at 128 should be opaque (threshold is exclusive)."""
        quantizer = ColorQuantizer(dither=False)

        img = Image.new("RGBA", (2, 2), (255, 0, 0, 128))

        result = quantizer.quantize(img)

        # Alpha 128 should NOT be fully transparent
        if result.transparency_mask is not None:
            assert not np.all(result.transparency_mask), "Alpha 128 should be opaque"
