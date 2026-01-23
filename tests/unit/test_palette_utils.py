"""Tests for core/palette_utils.py - SNES palette conversion and quantization."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from core.palette_utils import (
    quantize_to_palette,
    quantize_with_mappings,
    snes_palette_to_rgb,
)


class TestSnesPaletteToRgb:
    """Tests for snes_palette_to_rgb function."""

    def test_converts_bgr555_to_rgb(self) -> None:
        """SNES BGR555 format should convert correctly to RGB."""
        # SNES BGR555: 0bbbbbgggggrrrrr (15-bit)
        # Red = 0x001F (r=31, g=0, b=0) -> RGB (248, 0, 0)
        # Green = 0x03E0 (r=0, g=31, b=0) -> RGB (0, 248, 0)
        # Blue = 0x7C00 (r=0, g=0, b=31) -> RGB (0, 0, 248)
        snes_colors = [0x001F, 0x03E0, 0x7C00]
        result = snes_palette_to_rgb(snes_colors)

        assert result[0] == (248, 0, 0), "Red channel conversion"
        assert result[1] == (0, 248, 0), "Green channel conversion"
        assert result[2] == (0, 0, 248), "Blue channel conversion"

    def test_passes_through_rgb_triplets(self) -> None:
        """RGB triplets (list format) should pass through unchanged."""
        snes_colors: list[int | list[int]] = [[128, 64, 32], [255, 255, 255]]
        result = snes_palette_to_rgb(snes_colors)

        assert result[0] == (128, 64, 32)
        assert result[1] == (255, 255, 255)

    def test_handles_mixed_formats(self) -> None:
        """Should handle mixed BGR555 integers and RGB triplets."""
        # White in BGR555 = 0x7FFF
        snes_colors: list[int | list[int]] = [0x7FFF, [0, 0, 0]]
        result = snes_palette_to_rgb(snes_colors)

        assert result[0] == (248, 248, 248), "BGR555 white"
        assert result[1] == (0, 0, 0), "RGB black"

    def test_black_is_zero(self) -> None:
        """Black (0x0000) should convert to (0, 0, 0)."""
        result = snes_palette_to_rgb([0x0000])
        assert result[0] == (0, 0, 0)

    def test_handles_empty_palette(self) -> None:
        """Empty palette should return empty list."""
        result = snes_palette_to_rgb([])
        assert result == []


class TestQuantizeToPalette:
    """Tests for quantize_to_palette function."""

    def test_quantizes_solid_color_to_nearest_palette_entry(self) -> None:
        """Solid color image should map to nearest palette color."""
        # Create 8x8 solid red image
        img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

        # Palette with black, red, green, blue
        palette = [
            (0, 0, 0),  # 0: black
            (248, 0, 0),  # 1: red
            (0, 248, 0),  # 2: green
            (0, 0, 248),  # 3: blue
        ]
        # Pad to 16 colors
        palette.extend([(0, 0, 0)] * 12)

        result = quantize_to_palette(img, palette)

        # Should be indexed mode
        assert result.mode == "P"
        assert result.size == (8, 8)

        # All pixels should be index 1 (red)
        pixels = np.array(result)
        assert np.all(pixels == 1), "All pixels should map to red (index 1)"

    def test_transparent_pixels_map_to_index_zero(self) -> None:
        """Transparent pixels should always map to palette index 0."""
        # Create image with transparent pixels
        img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))

        palette = [(0, 0, 0)] + [(255, 255, 255)] * 15

        result = quantize_to_palette(img, palette)
        pixels = np.array(result)

        assert np.all(pixels == 0), "Transparent pixels should map to index 0"

    def test_mixed_transparency(self) -> None:
        """Image with both transparent and opaque pixels."""
        img = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        # Make top-left quadrant red (opaque)
        for y in range(2):
            for x in range(2):
                img.putpixel((x, y), (255, 0, 0, 255))

        palette = [
            (0, 0, 0),  # 0: transparent/black
            (248, 0, 0),  # 1: red
        ]
        palette.extend([(0, 0, 0)] * 14)

        result = quantize_to_palette(img, palette)
        pixels = np.array(result)

        # Top-left should be red (1), rest should be transparent (0)
        assert pixels[0, 0] == 1, "Top-left should be red"
        assert pixels[0, 1] == 1, "Top-left quadrant should be red"
        assert pixels[2, 2] == 0, "Bottom-right should be transparent"

    def test_nearest_color_matching(self) -> None:
        """Should find nearest color by Euclidean distance."""
        # Create image with a color between two palette colors
        # (128, 0, 0) is closer to (100, 0, 0) than to (200, 0, 0)
        img = Image.new("RGBA", (1, 1), (128, 0, 0, 255))

        palette = [
            (0, 0, 0),  # 0
            (100, 0, 0),  # 1: closer to (128, 0, 0)
            (200, 0, 0),  # 2: further from (128, 0, 0)
        ]
        palette.extend([(0, 0, 0)] * 13)

        result = quantize_to_palette(img, palette)
        pixels = np.array(result)

        # Distance to (100,0,0) = 28, distance to (200,0,0) = 72
        assert pixels[0, 0] == 1, "Should map to nearest color"

    def test_output_has_correct_palette(self) -> None:
        """Output image should have the specified palette embedded."""
        img = Image.new("RGBA", (8, 8), (255, 255, 255, 255))

        palette = [
            (10, 20, 30),
            (40, 50, 60),
            (70, 80, 90),
        ]
        palette.extend([(0, 0, 0)] * 13)

        result = quantize_to_palette(img, palette)

        # Get PIL palette
        pil_palette = result.getpalette()
        assert pil_palette is not None

        # Check first 3 colors
        assert pil_palette[0:3] == [10, 20, 30]
        assert pil_palette[3:6] == [40, 50, 60]
        assert pil_palette[6:9] == [70, 80, 90]

    def test_converts_rgb_input_to_rgba(self) -> None:
        """RGB input should be converted to RGBA internally."""
        img = Image.new("RGB", (8, 8), (255, 0, 0))

        palette = [(0, 0, 0), (248, 0, 0)]
        palette.extend([(0, 0, 0)] * 14)

        # Should not raise
        result = quantize_to_palette(img, palette)
        assert result.mode == "P"

    def test_tile_aligned_image(self) -> None:
        """8x8 tile-aligned images should work correctly."""
        # 16x16 image = 4 tiles
        img = Image.new("RGBA", (16, 16), (0, 255, 0, 255))

        palette = [(0, 0, 0), (0, 248, 0)]
        palette.extend([(0, 0, 0)] * 14)

        result = quantize_to_palette(img, palette)
        assert result.size == (16, 16)

        pixels = np.array(result)
        assert np.all(pixels == 1), "All green pixels should map to index 1"

    def test_opaque_pixel_never_quantized_to_index_0(self) -> None:
        """Opaque pixels should never map to index 0 (transparency index).

        Index 0 is reserved for transparency in SNES sprites. Even if an opaque
        pixel's color is closest to palette[0], it should map to the next-closest
        color (index 1+) to preserve visibility in-game.
        """
        # Create 2x2 image with opaque black pixel (closest to palette[0])
        img = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        img.putpixel((0, 0), (0, 0, 0, 255))  # Opaque black - closest to palette[0]
        img.putpixel((1, 0), (255, 0, 0, 255))  # Opaque red
        img.putpixel((0, 1), (0, 0, 0, 0))  # Fully transparent - should be index 0
        img.putpixel((1, 1), (0, 0, 0, 0))  # Fully transparent - should be index 0

        # Palette where index 0 is black (the transparency placeholder color)
        # Opaque black pixels should map to index 1 (dark gray), not index 0
        palette = [
            (0, 0, 0),  # 0: transparency placeholder (black)
            (17, 17, 17),  # 1: very dark gray (next closest to black)
            (255, 0, 0),  # 2: red
        ]
        palette.extend([(128, 128, 128)] * 13)  # Fill rest with gray

        result = quantize_to_palette(img, palette)
        pixels = list(result.getdata())

        # Pixel layout: (0,0), (1,0), (0,1), (1,1)
        assert pixels[0] != 0, "Opaque black pixel incorrectly mapped to index 0"
        assert pixels[0] == 1, "Opaque black should map to dark gray (index 1)"
        assert pixels[1] == 2, "Opaque red should map to red (index 2)"
        assert pixels[2] == 0, "Transparent pixel should map to index 0"
        assert pixels[3] == 0, "Transparent pixel should map to index 0"


class TestPaletteUtilsIntegration:
    """Integration tests combining both functions."""

    def test_full_snes_palette_workflow(self) -> None:
        """Test converting SNES palette and using it for quantization."""
        # Typical SNES sprite palette (16 colors)
        snes_palette: list[int | list[int]] = [
            0x0000,  # 0: Transparent (black)
            0x7FFF,  # 1: White
            0x001F,  # 2: Red
            0x03E0,  # 3: Green
            0x7C00,  # 4: Blue
            0x7C1F,  # 5: Magenta
            0x7FE0,  # 6: Cyan
            0x03FF,  # 7: Yellow
        ]
        # Pad to 16
        snes_palette.extend([0x0000] * 8)

        # Convert to RGB
        rgb_palette = snes_palette_to_rgb(snes_palette)
        assert len(rgb_palette) == 16

        # Create test image with cyan color (closest to palette index 6)
        img = Image.new("RGBA", (8, 8), (0, 255, 255, 255))

        # Quantize
        result = quantize_to_palette(img, rgb_palette)
        pixels = np.array(result)

        # Should map to cyan (index 6)
        assert pixels[0, 0] == 6, "Cyan should map to palette index 6"

    def test_transparency_preserved_through_workflow(self) -> None:
        """Transparency should be preserved through full workflow."""
        snes_palette: list[int | list[int]] = [0x0000, 0x7FFF]
        snes_palette.extend([0x0000] * 14)

        rgb_palette = snes_palette_to_rgb(snes_palette)

        # Image with alpha=0 should stay at index 0
        img = Image.new("RGBA", (4, 4), (255, 255, 255, 0))
        result = quantize_to_palette(img, rgb_palette)
        pixels = np.array(result)

        assert np.all(pixels == 0), "Transparent pixels should remain index 0"


class TestQuantizeWithMappings:
    """Tests for quantize_with_mappings function."""

    def test_opaque_pixel_never_quantized_to_index_0_with_mappings(self) -> None:
        """Opaque pixels should never map to index 0 in fallback nearest-color.

        Even with color mappings, the nearest-color fallback should exclude
        index 0 for opaque pixels.
        """
        # Create 2x2 image with opaque black pixel (closest to palette[0])
        img = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        img.putpixel((0, 0), (0, 0, 0, 255))  # Opaque black - closest to palette[0]
        img.putpixel((1, 0), (128, 0, 0, 255))  # Opaque dark red - not in mappings
        img.putpixel((0, 1), (0, 0, 0, 0))  # Transparent - should be index 0
        img.putpixel((1, 1), (255, 0, 0, 255))  # Opaque red - has explicit mapping

        # Palette where index 0 is black (transparency placeholder)
        palette = [
            (0, 0, 0),  # 0: transparency placeholder
            (17, 17, 17),  # 1: very dark gray
            (130, 0, 0),  # 2: dark red
            (255, 0, 0),  # 3: red (explicit mapping target)
        ]
        palette.extend([(128, 128, 128)] * 12)

        # Only map exact red (255, 0, 0) explicitly
        color_mappings: dict[tuple[int, int, int], int] = {
            (255, 0, 0): 3,  # Red -> index 3
        }

        result = quantize_with_mappings(img, palette, color_mappings)
        pixels = list(result.getdata())

        # Pixel layout: (0,0), (1,0), (0,1), (1,1)
        assert pixels[0] != 0, "Opaque black pixel incorrectly mapped to index 0"
        assert pixels[0] == 1, "Opaque black should map to dark gray (index 1)"
        assert pixels[1] == 2, "Opaque dark red should map to dark red (index 2)"
        assert pixels[2] == 0, "Transparent pixel should map to index 0"
        assert pixels[3] == 3, "Explicitly mapped red should be index 3"
