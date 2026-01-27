"""Tests for core/palette_utils.py - SNES palette conversion and quantization."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from core.palette_utils import (
    JND_THRESHOLD_SQ,
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    SNES_PALETTE_SIZE,
    _stable_argmin,
    bgr555_to_rgb,
    extract_unique_colors,
    find_nearest_palette_index,
    quantize_colors_to_palette,
    quantize_to_palette,
    quantize_with_mappings,
    snap_to_snes_color,
    snes_palette_to_rgb,
)


class TestSnesPaletteToRgb:
    """Tests for snes_palette_to_rgb function."""

    def test_converts_bgr555_to_rgb_full_8bit_range(self) -> None:
        """BGR555 max value (31) should produce full 8-bit value (255), not 248.

        The correct 5-bit to 8-bit conversion is: (value << 3) | (value >> 2)
        This scales 31 (max 5-bit) to 255 (max 8-bit), not 248.
        Example: 31 << 3 = 248, 31 >> 2 = 7, 248 | 7 = 255

        Bug impact: Incomplete scaling produces muted colors (248 instead of 255).
        """
        # SNES BGR555: 0bbbbbgggggrrrrr (15-bit)
        # Max values in each channel should produce 255, not 248
        snes_colors = [0x001F, 0x03E0, 0x7C00, 0x7FFF]
        result = snes_palette_to_rgb(snes_colors)

        # Full red (r=31, g=0, b=0) -> RGB (255, 0, 0)
        assert result[0] == (255, 0, 0), f"Red channel: expected (255, 0, 0), got {result[0]}"
        # Full green (r=0, g=31, b=0) -> RGB (0, 255, 0)
        assert result[1] == (0, 255, 0), f"Green channel: expected (0, 255, 0), got {result[1]}"
        # Full blue (r=0, g=0, b=31) -> RGB (0, 0, 255)
        assert result[2] == (0, 0, 255), f"Blue channel: expected (0, 0, 255), got {result[2]}"
        # White (r=31, g=31, b=31) -> RGB (255, 255, 255)
        assert result[3] == (255, 255, 255), f"White: expected (255, 255, 255), got {result[3]}"

    def test_passes_through_rgb_triplets(self) -> None:
        """RGB triplets (list format) should pass through unchanged."""
        snes_colors: list[int | list[int]] = [[128, 64, 32], [255, 255, 255]]
        result = snes_palette_to_rgb(snes_colors)

        assert result[0] == (128, 64, 32)
        assert result[1] == (255, 255, 255)

    def test_handles_mixed_formats(self) -> None:
        """Should handle mixed BGR555 integers and RGB triplets."""
        # White in BGR555 = 0x7FFF (r=31, g=31, b=31 -> 255, 255, 255)
        snes_colors: list[int | list[int]] = [0x7FFF, [0, 0, 0]]
        result = snes_palette_to_rgb(snes_colors)

        assert result[0] == (255, 255, 255), "BGR555 white"
        assert result[1] == (0, 0, 0), "RGB black"

    def test_black_is_zero(self) -> None:
        """Black (0x0000) should convert to (0, 0, 0)."""
        result = snes_palette_to_rgb([0x0000])
        assert result[0] == (0, 0, 0)

    def test_handles_empty_palette(self) -> None:
        """Empty palette should return empty list."""
        result = snes_palette_to_rgb([])
        assert result == []


class TestBgr555ToRgb:
    """Tests for bgr555_to_rgb utility function."""

    def test_full_values_scale_to_255(self) -> None:
        """Max 5-bit values (31) should scale to max 8-bit (255)."""
        assert bgr555_to_rgb(0x001F) == (255, 0, 0)  # Full red
        assert bgr555_to_rgb(0x03E0) == (0, 255, 0)  # Full green
        assert bgr555_to_rgb(0x7C00) == (0, 0, 255)  # Full blue
        assert bgr555_to_rgb(0x7FFF) == (255, 255, 255)  # Full white

    def test_zero_values(self) -> None:
        """Zero values should stay zero."""
        assert bgr555_to_rgb(0x0000) == (0, 0, 0)

    def test_mid_values(self) -> None:
        """Mid-range 5-bit values (16) should scale correctly.

        16 << 3 = 128, 16 >> 2 = 4, 128 | 4 = 132
        """
        # r=16, g=0, b=0 -> 0x0010
        assert bgr555_to_rgb(0x0010) == (132, 0, 0)
        # r=0, g=16, b=0 -> 0x0200
        assert bgr555_to_rgb(0x0200) == (0, 132, 0)
        # r=0, g=0, b=16 -> 0x4000
        assert bgr555_to_rgb(0x4000) == (0, 0, 132)

    def test_low_values(self) -> None:
        """Low 5-bit value (1) should scale correctly.

        1 << 3 = 8, 1 >> 2 = 0, 8 | 0 = 8
        """
        assert bgr555_to_rgb(0x0001) == (8, 0, 0)


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


class TestBgr555RoundtripConversion:
    """Tests for BGR555 roundtrip conversion (RGB -> BGR555 -> RGB)."""

    def test_roundtrip_conversion(self) -> None:
        """Test that extraction and injection are approximately inverse operations.

        Note: Due to 8-bit to 5-bit quantization, exact roundtrip is not possible.
        The tolerance is +-7 (since 255/31 ≈ 8.2, values can vary by up to 7).
        """
        from core.rom_palette_injector import ROMPaletteInjector

        # Create test colors
        test_colors = [
            (0, 0, 0),
            (255, 255, 255),
            (128, 128, 128),
            (200, 100, 50),
        ]

        for r, g, b in test_colors:
            # Convert to BGR555
            bgr555 = ROMPaletteInjector.rgb888_to_bgr555(r, g, b)

            # Extract back using bgr555_to_rgb
            r8, g8, b8 = bgr555_to_rgb(bgr555)

            # Check within tolerance (quantization can cause +-7 difference)
            assert abs(r - r8) <= 7, f"Red mismatch: {r} -> {r8}"
            assert abs(g - g8) <= 7, f"Green mismatch: {g} -> {g8}"
            assert abs(b - b8) <= 7, f"Blue mismatch: {b} -> {b8}"

    def test_clamping_overflow(self) -> None:
        """Test that values > 255 are clamped in RGB to BGR555 conversion."""
        from core.rom_palette_injector import ROMPaletteInjector

        result = ROMPaletteInjector.rgb888_to_bgr555(300, 400, 500)
        # All should be clamped to 255, which gives r5=31, g5=31, b5=31
        assert result == 0x7FFF

    def test_clamping_underflow(self) -> None:
        """Test that values < 0 are clamped in RGB to BGR555 conversion."""
        from core.rom_palette_injector import ROMPaletteInjector

        result = ROMPaletteInjector.rgb888_to_bgr555(-10, -20, -30)
        # All should be clamped to 0
        assert result == 0x0000


class TestSnapToSnesColor:
    """Tests for snap_to_snes_color function."""

    def test_exact_snes_color_unchanged(self) -> None:
        """Colors that are already SNES-valid should be unchanged."""
        # Values produced by (c5 << 3) | (c5 >> 2) are the ONLY valid SNES values
        assert snap_to_snes_color((255, 255, 255)) == (255, 255, 255)  # 31 -> 255
        assert snap_to_snes_color((0, 0, 0)) == (0, 0, 0)  # 0 -> 0
        assert snap_to_snes_color((8, 8, 8)) == (8, 8, 8)  # 1 -> 8
        assert snap_to_snes_color((132, 132, 132)) == (132, 132, 132)  # 16 -> 132
        # Note: 248 is NOT a valid SNES-expanded value (31 expands to 255, not 248)

    def test_snaps_to_nearest_snes_value(self) -> None:
        """Colors should snap to nearest SNES-valid value."""
        # 248 is NOT a valid SNES-expanded value; round(248/8)=31 -> expands to 255
        assert snap_to_snes_color((248, 248, 248)) == (255, 255, 255)
        # 4 rounds to 5-bit 0 (banker's rounding: round(0.5)=0), expands to 0
        assert snap_to_snes_color((4, 4, 4)) == (0, 0, 0)
        # 5 rounds to 5-bit 1 (round(0.625)=1), expands to 8
        assert snap_to_snes_color((5, 5, 5)) == (8, 8, 8)
        # 127 rounds to 5-bit 16 (round(15.875)=16), expands to 132
        assert snap_to_snes_color((127, 127, 127)) == (132, 132, 132)

    def test_round_trip_consistency(self) -> None:
        """Snapped values should round-trip through BGR555 correctly."""
        from core.rom_palette_injector import ROMPaletteInjector

        for val in [0, 50, 100, 150, 200, 255]:
            snapped = snap_to_snes_color((val, val, val))
            # Convert to BGR555 and back
            bgr = ROMPaletteInjector.rgb888_to_bgr555(snapped[0], snapped[1], snapped[2])
            recovered = bgr555_to_rgb(bgr)
            assert recovered == snapped, f"Round-trip failed for {val}: {snapped} -> {bgr} -> {recovered}"


class TestFindNearestPaletteIndex:
    """Tests for find_nearest_palette_index function."""

    def test_finds_exact_match(self) -> None:
        """Exact color match should return correct index."""
        palette = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]
        assert find_nearest_palette_index((255, 0, 0), palette) == 1
        assert find_nearest_palette_index((0, 255, 0), palette) == 2
        assert find_nearest_palette_index((0, 0, 255), palette) == 3

    def test_skips_index_zero_by_default(self) -> None:
        """Should skip index 0 when skip_zero=True."""
        palette = [(255, 0, 0), (0, 0, 0)]  # Index 0 is closest match
        # But we skip it, so result should be index 1
        result = find_nearest_palette_index((255, 0, 0), palette, skip_zero=True)
        assert result == 1

    def test_includes_index_zero_when_requested(self) -> None:
        """Should include index 0 when skip_zero=False."""
        palette = [(255, 0, 0), (0, 0, 0)]
        result = find_nearest_palette_index((255, 0, 0), palette, skip_zero=False)
        assert result == 0


class TestExtractUniqueColors:
    """Tests for extract_unique_colors function."""

    def test_extracts_solid_color(self) -> None:
        """Single color image should have one color."""
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
        result = extract_unique_colors(img)
        assert len(result) == 1
        assert (255, 0, 0) in result
        assert result[(255, 0, 0)] == 16  # 4x4 = 16 pixels

    def test_ignores_transparent_by_default(self) -> None:
        """Transparent pixels should be ignored by default."""
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 0))
        result = extract_unique_colors(img)
        assert len(result) == 0

    def test_ignores_semi_transparent(self) -> None:
        """Semi-transparent pixels (alpha < 128) should be ignored."""
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 64))
        result = extract_unique_colors(img, alpha_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD)
        assert len(result) == 0

    def test_includes_opaque(self) -> None:
        """Opaque pixels (alpha >= 128) should be included."""
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 128))
        result = extract_unique_colors(img, alpha_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD)
        assert len(result) == 1
        assert (255, 0, 0) in result


class TestQuantizeColorsToPalette:
    """Tests for quantize_colors_to_palette function."""

    def test_returns_16_colors(self) -> None:
        """Should return exactly 16 colors."""
        colors = {(255, 0, 0): 100, (0, 255, 0): 50}
        result = quantize_colors_to_palette(colors)
        assert len(result) == SNES_PALETTE_SIZE

    def test_index_zero_is_black(self) -> None:
        """Index 0 should always be black (transparency)."""
        colors = {(255, 0, 0): 100}
        result = quantize_colors_to_palette(colors)
        assert result[0] == (0, 0, 0)

    def test_snaps_to_snes_by_default(self) -> None:
        """Colors should be snapped to SNES-valid values that round-trip correctly."""
        colors = {(255, 127, 63): 100}
        result = quantize_colors_to_palette(colors, snap_to_snes=True)
        # All colors should round-trip correctly through 5-bit conversion
        # Valid SNES values satisfy: c8 == (c5 << 3) | (c5 >> 2) where c5 = c8 >> 3
        for r, g, b in result:
            for c, name in [(r, "Red"), (g, "Green"), (b, "Blue")]:
                c5 = c >> 3
                expected = (c5 << 3) | (c5 >> 2)
                assert c == expected, f"{name} {c} is not a valid SNES-expanded value"

    def test_empty_colors_returns_black_palette(self) -> None:
        """Empty color dict should return all-black palette."""
        result = quantize_colors_to_palette({})
        assert len(result) == SNES_PALETTE_SIZE
        assert all(c == (0, 0, 0) for c in result)


class TestStableArgmin:
    """Tests for _stable_argmin helper - stable tie-breaking in quantization."""

    def test_picks_lowest_index_among_ties(self) -> None:
        """When distances are within JND threshold, picks lowest index."""
        # Create distance array where indices 1 and 2 are nearly equal
        # Shape: (1, 1, 16) - single pixel
        distances = np.full((1, 1, 16), 1000.0, dtype=np.float64)
        distances[0, 0, 0] = np.inf  # Index 0 excluded (transparency)
        distances[0, 0, 1] = 10.0  # Minimum
        distances[0, 0, 2] = 10.0 + JND_THRESHOLD_SQ - 0.1  # Within JND of minimum

        result = _stable_argmin(distances)
        assert result[0, 0] == 1, "Should pick lowest index (1) among near-ties"

    def test_clear_winner_not_affected(self) -> None:
        """Clear winner with large distance gap is unaffected by threshold."""
        distances = np.full((1, 1, 16), 1000.0, dtype=np.float64)
        distances[0, 0, 0] = np.inf
        distances[0, 0, 3] = 5.0  # Clear winner
        distances[0, 0, 1] = 50.0  # Far from minimum
        distances[0, 0, 2] = 100.0

        result = _stable_argmin(distances)
        assert result[0, 0] == 3, "Clear winner should still be selected"

    def test_two_pixels_with_reversed_tie_order_get_same_index(self) -> None:
        """Two pixels with tie-scenario reversed should both pick same index."""
        # Pixel A: index 1 slightly closer, index 2 slightly further
        # Pixel B: index 2 slightly closer, index 1 slightly further
        # Both should map to index 1 (lowest among ties)
        distances = np.full((2, 1, 16), 1000.0, dtype=np.float64)
        distances[:, :, 0] = np.inf

        # Pixel A: dist[1]=10.0, dist[2]=10.1 (within JND)
        distances[0, 0, 1] = 10.0
        distances[0, 0, 2] = 10.1

        # Pixel B: dist[1]=10.1, dist[2]=10.0 (reversed, still within JND)
        distances[1, 0, 1] = 10.1
        distances[1, 0, 2] = 10.0

        result = _stable_argmin(distances)
        assert result[0, 0] == result[1, 0], "Symmetric pixels should map to same index"
        assert result[0, 0] == 1, "Both should pick lowest index among ties"

    def test_custom_jnd_threshold(self) -> None:
        """Custom jnd_sq parameter should override default threshold."""
        distances = np.full((1, 1, 16), 1000.0, dtype=np.float64)
        distances[0, 0, 0] = np.inf
        distances[0, 0, 1] = 10.0
        distances[0, 0, 2] = 12.0  # 2.0 apart

        # With default JND (~5.29), these are ties -> pick 1
        result_default = _stable_argmin(distances)
        assert result_default[0, 0] == 1

        # With tight threshold (1.0), these are NOT ties -> pick 1 (still minimum)
        result_tight = _stable_argmin(distances, jnd_sq=1.0)
        assert result_tight[0, 0] == 1


class TestQuantizationSymmetry:
    """Tests verifying symmetric images stay symmetric after quantization."""

    def test_near_identical_colors_map_to_same_index(self) -> None:
        """Pixels differing by 1-2 RGB should map to same palette index."""
        # Create 2x1 image with nearly-identical colors (simulates AI generation noise)
        img = Image.new("RGBA", (2, 1))
        img.putpixel((0, 0), (100, 100, 100, 255))  # Base gray
        img.putpixel((1, 0), (101, 100, 100, 255))  # Off by 1 in red

        # Palette with two grays that could both match
        palette = [
            (0, 0, 0),  # 0: transparency
            (98, 98, 98),  # 1: darker gray
            (102, 102, 102),  # 2: lighter gray
        ]
        palette.extend([(128, 128, 128)] * 13)

        result = quantize_to_palette(img, palette)
        pixels = list(result.getdata())

        # Both pixels should map to same index despite RGB difference
        assert pixels[0] == pixels[1], f"Near-identical pixels mapped to different indices: {pixels[0]} vs {pixels[1]}"

    def test_mirrored_image_stays_symmetric(self) -> None:
        """Horizontal mirror of image should produce same quantized result."""
        # Create asymmetric test image
        img = Image.new("RGBA", (4, 2), (0, 0, 0, 0))
        # Fill with gradient that varies slightly
        for x in range(4):
            for y in range(2):
                # Small variations in color to trigger tie scenarios
                r = 100 + x + y
                g = 100 + x
                b = 100
                img.putpixel((x, y), (r, g, b, 255))

        # Palette with colors that could cause ties
        palette = [
            (0, 0, 0),  # 0
            (99, 99, 99),  # 1
            (103, 103, 103),  # 2
            (107, 107, 107),  # 3
        ]
        palette.extend([(128, 128, 128)] * 12)

        # Quantize original and mirrored
        result_orig = quantize_to_palette(img, palette)
        result_mirror = quantize_to_palette(img.transpose(Image.FLIP_LEFT_RIGHT), palette)

        # Mirror the result back
        result_mirror_back = result_mirror.transpose(Image.FLIP_LEFT_RIGHT)

        # Compare pixel data
        pixels_orig = list(result_orig.getdata())
        pixels_mirror = list(result_mirror_back.getdata())

        assert pixels_orig == pixels_mirror, "Mirrored image should quantize symmetrically"

    def test_symmetric_eyes_stay_symmetric(self) -> None:
        """Simulated symmetric eye pattern should remain symmetric after quantization.

        This is the core bug scenario: symmetric visual features (like eyes)
        become asymmetric when near-identical pixels map to different colors.
        """
        # Create 8x4 image simulating two symmetric "eyes"
        # Each eye is a 2x2 block with nearly-identical "pupil" color
        img = Image.new("RGBA", (8, 4), (200, 200, 200, 255))  # Light gray background

        # Left eye pupil (2x2 at position 1,1)
        # Simulate AI-generation noise: slight RGB variations
        img.putpixel((1, 1), (30, 30, 32, 255))
        img.putpixel((2, 1), (31, 30, 30, 255))
        img.putpixel((1, 2), (30, 31, 30, 255))
        img.putpixel((2, 2), (30, 30, 31, 255))

        # Right eye pupil (2x2 at position 5,1) - mirror of left
        # Same colors but in mirror positions
        img.putpixel((6, 1), (30, 30, 32, 255))
        img.putpixel((5, 1), (31, 30, 30, 255))
        img.putpixel((6, 2), (30, 31, 30, 255))
        img.putpixel((5, 2), (30, 30, 31, 255))

        # Palette with colors that could cause tie scenarios for dark grays
        palette = [
            (0, 0, 0),  # 0: transparency
            (24, 24, 24),  # 1: very dark gray
            (32, 32, 32),  # 2: dark gray
            (200, 200, 200),  # 3: light gray (background)
        ]
        palette.extend([(128, 128, 128)] * 12)

        result = quantize_to_palette(img, palette)
        pixels = np.array(result)

        # Extract eye regions
        left_eye = pixels[1:3, 1:3]
        right_eye = pixels[1:3, 5:7]

        # Right eye should be horizontal mirror of left eye
        right_eye_mirrored = np.fliplr(right_eye)

        assert np.array_equal(left_eye, right_eye_mirrored), (
            f"Eyes should be symmetric!\nLeft eye:\n{left_eye}\nRight eye (mirrored):\n{right_eye_mirrored}"
        )
