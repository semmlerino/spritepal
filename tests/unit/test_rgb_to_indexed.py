"""Tests for the RGB to indexed conversion service.

Tests cover:
1. convert_rgb_to_indexed - RGB(A) image to indexed palette format
2. convert_indexed_to_rgb - Indexed data back to RGBA image
3. convert_indexed_to_pil_indexed - Indexed data to PIL palette mode
4. find_closest_palette_index - Nearest color matching
5. analyze_color_usage - Color analysis for quantization
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from core.palette_utils import QUANTIZATION_TRANSPARENCY_THRESHOLD
from core.services.rgb_to_indexed import (
    analyze_color_usage,
    convert_indexed_to_pil_indexed,
    convert_indexed_to_rgb,
    convert_rgb_to_indexed,
    find_closest_palette_index,
    get_color_distance,
)


@dataclass
class MockSheetPalette:
    """Mock SheetPalette for testing."""

    colors: list[tuple[int, int, int]] = field(default_factory=list)
    color_mappings: dict[tuple[int, int, int], int] = field(default_factory=dict)


class TestConvertRgbToIndexed:
    """Tests for convert_rgb_to_indexed function."""

    def test_transparent_pixels_become_index_zero(self) -> None:
        """Transparent pixels (alpha < 128) should map to index 0."""
        # Create image with transparent pixels
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 64))

        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),  # Index 0 - reserved for transparent
                (255, 0, 0),  # Index 1 - red
                *[(0, 0, 0)] * 14,
            ]
        )

        result = convert_rgb_to_indexed(img, palette, transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD)

        assert result.shape == (4, 4)
        assert np.all(result == 0), "Transparent pixels should be index 0"

    def test_opaque_pixels_mapped_to_palette(self) -> None:
        """Opaque pixels should be mapped to nearest palette color."""
        # Create image with opaque red pixels
        img = Image.new("RGBA", (2, 2), (255, 0, 0, 255))

        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),  # Index 0 - transparent
                (255, 0, 0),  # Index 1 - red (exact match)
                *[(0, 0, 0)] * 14,
            ]
        )

        result = convert_rgb_to_indexed(img, palette)

        # All pixels should map to index 1 (red)
        assert np.all(result == 1), "Opaque red should map to palette index 1"

    def test_explicit_color_mappings_used(self) -> None:
        """Explicit color mappings should be used before nearest-color fallback."""
        # Create image with opaque green pixels
        img = Image.new("RGBA", (2, 2), (0, 255, 0, 255))

        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),  # Index 0
                (255, 0, 0),  # Index 1 - red (not matching)
                (0, 0, 255),  # Index 2 - blue (not matching)
                *[(0, 0, 0)] * 13,
            ],
            # Explicit mapping: green -> index 2
            color_mappings={(0, 255, 0): 2},
        )

        result = convert_rgb_to_indexed(img, palette)

        # All pixels should map to index 2 via explicit mapping
        assert np.all(result == 2), "Green should map to index 2 via explicit mapping"

    def test_nearest_color_fallback(self) -> None:
        """Colors without explicit mapping should use nearest-color matching."""
        # Create image with slightly different red
        img = Image.new("RGBA", (2, 2), (250, 10, 10, 255))  # Almost red

        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),  # Index 0
                (255, 0, 0),  # Index 1 - closest to (250, 10, 10)
                (0, 255, 0),  # Index 2 - green
                (0, 0, 255),  # Index 3 - blue
                *[(0, 0, 0)] * 12,
            ]
        )

        result = convert_rgb_to_indexed(img, palette)

        # Should map to red (index 1) as nearest color
        assert np.all(result == 1), "Near-red should map to red at index 1"

    def test_rgb_mode_converted_to_rgba(self) -> None:
        """RGB images should be converted to RGBA before processing."""
        # Create RGB image (no alpha)
        img = Image.new("RGB", (2, 2), (255, 0, 0))

        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),
                (255, 0, 0),
                *[(0, 0, 0)] * 14,
            ]
        )

        result = convert_rgb_to_indexed(img, palette)

        # Should work without error and map to red
        assert result.shape == (2, 2)
        assert np.all(result == 1)


class TestConvertIndexedToRgb:
    """Tests for convert_indexed_to_rgb function."""

    def test_index_zero_becomes_transparent(self) -> None:
        """Index 0 should become fully transparent."""
        indexed = np.array([[0, 0], [0, 0]], dtype=np.uint8)

        palette = MockSheetPalette(
            colors=[(255, 0, 0)] * 16  # All red, but index 0 is transparent
        )

        result = convert_indexed_to_rgb(indexed, palette)

        assert result.mode == "RGBA"
        pixels = np.array(result)
        # Index 0 should be transparent (alpha = 0)
        assert np.all(pixels[:, :, 3] == 0)

    def test_non_zero_indices_become_opaque_colors(self) -> None:
        """Non-zero indices should become opaque colors from palette."""
        indexed = np.array([[1, 2], [3, 4]], dtype=np.uint8)

        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),  # 0 - transparent
                (255, 0, 0),  # 1 - red
                (0, 255, 0),  # 2 - green
                (0, 0, 255),  # 3 - blue
                (255, 255, 0),  # 4 - yellow
                *[(0, 0, 0)] * 11,
            ]
        )

        result = convert_indexed_to_rgb(indexed, palette)
        pixels = np.array(result)

        # Check each pixel color
        assert tuple(pixels[0, 0]) == (255, 0, 0, 255)  # red
        assert tuple(pixels[0, 1]) == (0, 255, 0, 255)  # green
        assert tuple(pixels[1, 0]) == (0, 0, 255, 255)  # blue
        assert tuple(pixels[1, 1]) == (255, 255, 0, 255)  # yellow

    def test_out_of_range_index_becomes_transparent(self) -> None:
        """Indices >= palette size should become transparent."""
        indexed = np.array([[15, 16]], dtype=np.uint8)  # 16 is out of range

        palette = MockSheetPalette(colors=[(255, 0, 0)] * 16)

        result = convert_indexed_to_rgb(indexed, palette)
        pixels = np.array(result)

        # Index 15 should be valid (red, opaque)
        assert pixels[0, 0, 3] == 255
        # Index 16 should be transparent
        assert pixels[0, 1, 3] == 0


class TestConvertIndexedToPilIndexed:
    """Tests for convert_indexed_to_pil_indexed function."""

    def test_creates_palette_mode_image(self) -> None:
        """Should create a PIL image in palette mode."""
        indexed = np.array([[1, 2], [3, 4]], dtype=np.uint8)

        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),
                (255, 0, 0),
                (0, 255, 0),
                (0, 0, 255),
                (255, 255, 0),
                *[(0, 0, 0)] * 11,
            ]
        )

        result = convert_indexed_to_pil_indexed(indexed, palette)

        assert result.mode == "P"
        assert result.size == (2, 2)

    def test_palette_embedded_correctly(self) -> None:
        """Palette should be embedded in the image."""
        indexed = np.array([[1]], dtype=np.uint8)

        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),
                (255, 128, 64),  # Custom color at index 1
                *[(0, 0, 0)] * 14,
            ]
        )

        result = convert_indexed_to_pil_indexed(indexed, palette)
        embedded_palette = result.getpalette()

        assert embedded_palette is not None
        # Check index 1 color (R, G, B at positions 3, 4, 5)
        assert embedded_palette[3] == 255
        assert embedded_palette[4] == 128
        assert embedded_palette[5] == 64

    def test_transparency_info_set(self) -> None:
        """Index 0 should be marked as transparent."""
        indexed = np.array([[0, 1]], dtype=np.uint8)

        palette = MockSheetPalette(colors=[(0, 0, 0)] * 16)

        result = convert_indexed_to_pil_indexed(indexed, palette)

        assert result.info.get("transparency") == 0


class TestFindClosestPaletteIndex:
    """Tests for find_closest_palette_index function."""

    def test_exact_match_returns_correct_index(self) -> None:
        """Exact color match should return correct index."""
        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),
                (255, 0, 0),
                (0, 255, 0),
                *[(0, 0, 0)] * 13,
            ]
        )

        idx, dist = find_closest_palette_index((255, 0, 0), palette)

        assert idx == 1
        assert dist < 0.001  # Should be essentially zero

    def test_skip_transparent_avoids_index_zero(self) -> None:
        """With skip_transparent=True, should never return index 0."""
        palette = MockSheetPalette(
            colors=[
                (255, 0, 0),  # Index 0 - exact match but skip
                (128, 0, 0),  # Index 1 - close but not exact
                *[(0, 0, 0)] * 14,
            ]
        )

        idx, dist = find_closest_palette_index((255, 0, 0), palette, skip_transparent=True)

        assert idx != 0, "Should not return index 0 when skip_transparent=True"
        assert idx == 1

    def test_include_transparent(self) -> None:
        """With skip_transparent=False, can return index 0."""
        palette = MockSheetPalette(
            colors=[
                (255, 0, 0),  # Index 0 - exact match
                (0, 255, 0),  # Index 1 - different color
                *[(0, 0, 0)] * 14,
            ]
        )

        idx, dist = find_closest_palette_index((255, 0, 0), palette, skip_transparent=False)

        assert idx == 0  # Can return index 0
        assert dist < 0.001

    def test_perceptual_distance_used(self) -> None:
        """Should use perceptual (LAB) distance, not RGB Euclidean."""
        # This tests that perceptually similar colors are matched
        # In LAB space, colors that look similar are closer
        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),
                (200, 180, 170),  # Index 1 - warm beige
                (170, 200, 180),  # Index 2 - cool green-gray
                *[(0, 0, 0)] * 13,
            ]
        )

        # A warm skin tone should match warm beige better in LAB
        idx, _ = find_closest_palette_index((210, 185, 175), palette)

        # Should match the warmer color at index 1
        assert idx == 1


class TestGetColorDistance:
    """Tests for get_color_distance function."""

    def test_same_color_zero_distance(self) -> None:
        """Same color should have zero distance."""
        dist = get_color_distance((100, 150, 200), (100, 150, 200))
        assert dist < 0.001

    def test_different_colors_positive_distance(self) -> None:
        """Different colors should have positive distance."""
        dist = get_color_distance((0, 0, 0), (255, 255, 255))
        assert dist > 0

    def test_symmetric(self) -> None:
        """Distance should be symmetric."""
        dist1 = get_color_distance((100, 0, 0), (0, 100, 0))
        dist2 = get_color_distance((0, 100, 0), (100, 0, 0))
        assert abs(dist1 - dist2) < 0.001


class TestAnalyzeColorUsage:
    """Tests for analyze_color_usage function."""

    def test_exact_matches_found(self) -> None:
        """Colors with explicit mappings should be in exact_matches."""
        img = Image.new("RGBA", (2, 2), (255, 0, 0, 255))

        palette = MockSheetPalette(
            colors=[(0, 0, 0)] * 16,
            color_mappings={(255, 0, 0): 1},
        )

        result = analyze_color_usage(img, palette)

        assert (255, 0, 0) in result["exact_matches"]
        assert result["exact_count"] == 1

    def test_unmapped_colors_counted(self) -> None:
        """Colors without explicit mappings should be in nearest_matches."""
        img = Image.new("RGBA", (2, 2), (0, 255, 0, 255))

        palette = MockSheetPalette(
            colors=[(0, 0, 0), (255, 0, 0), *[(0, 0, 0)] * 14],
            color_mappings={},  # No explicit mappings
        )

        result = analyze_color_usage(img, palette)

        assert result["unmapped_count"] == 1
        assert "(0, 255, 0)" in result["nearest_matches"]

    def test_transparent_pixels_excluded(self) -> None:
        """Transparent pixels should not be counted."""
        # Create image where top half is opaque, bottom half is transparent
        img = Image.new("RGBA", (2, 2))
        pixels = img.load()
        assert pixels is not None
        pixels[0, 0] = (255, 0, 0, 255)  # Opaque red
        pixels[1, 0] = (255, 0, 0, 255)  # Opaque red
        pixels[0, 1] = (0, 255, 0, 64)  # Transparent green
        pixels[1, 1] = (0, 255, 0, 64)  # Transparent green

        palette = MockSheetPalette(
            colors=[(0, 0, 0)] * 16,
            color_mappings={(255, 0, 0): 1},
        )

        result = analyze_color_usage(img, palette, transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD)

        # Only red should be counted (green is transparent)
        assert result["exact_count"] == 1
        assert result["unmapped_count"] == 0

    def test_distance_stats_computed(self) -> None:
        """Distance statistics should be computed for nearest matches."""
        # Create image with multiple unmapped colors
        img = Image.new("RGBA", (4, 1))
        pixels = img.load()
        assert pixels is not None
        pixels[0, 0] = (0, 100, 0, 255)
        pixels[1, 0] = (0, 150, 0, 255)
        pixels[2, 0] = (0, 200, 0, 255)
        pixels[3, 0] = (0, 250, 0, 255)

        palette = MockSheetPalette(
            colors=[(0, 0, 0), (0, 255, 0), *[(0, 0, 0)] * 14],
        )

        result = analyze_color_usage(img, palette)

        stats = result["distance_stats"]
        assert "min" in stats
        assert "max" in stats
        assert "avg" in stats
        assert stats["min"] <= stats["avg"] <= stats["max"]


class TestLoadImagePreservingIndices:
    """Tests for load_image_preserving_indices function.

    BUG-1 FIX: Tests for preserving palette indices when loading indexed PNGs.
    """

    def test_indexed_png_returns_index_map(self, tmp_path) -> None:
        """Loading indexed PNG returns valid index map."""
        from core.services.rgb_to_indexed import load_image_preserving_indices

        # Create indexed PNG with specific indices
        indexed_data = np.array(
            [
                [0, 1, 2, 3],
                [4, 5, 6, 7],
                [8, 9, 10, 11],
                [12, 13, 14, 15],
            ],
            dtype=np.uint8,
        )
        palette_flat = [i * 16 for i in range(16)] * 3  # Grayscale palette
        palette_flat.extend([0] * (768 - len(palette_flat)))

        img = Image.fromarray(indexed_data, mode="P")
        img.putpalette(palette_flat)

        path = tmp_path / "indexed.png"
        img.save(path)

        # Load and verify
        index_map, rgba_img = load_image_preserving_indices(path)

        assert index_map is not None
        assert index_map.shape == (4, 4)
        np.testing.assert_array_equal(index_map, indexed_data)
        assert rgba_img.mode == "RGBA"

    def test_rgba_png_returns_none_index_map(self, tmp_path) -> None:
        """Loading non-indexed PNG returns None for index map."""
        from core.services.rgb_to_indexed import load_image_preserving_indices

        # Create RGBA image
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
        path = tmp_path / "rgba.png"
        img.save(path)

        # Load and verify
        index_map, rgba_img = load_image_preserving_indices(path)

        assert index_map is None
        assert rgba_img.mode == "RGBA"

    def test_rgb_png_returns_none_index_map(self, tmp_path) -> None:
        """Loading RGB PNG returns None for index map."""
        from core.services.rgb_to_indexed import load_image_preserving_indices

        # Create RGB image
        img = Image.new("RGB", (4, 4), (0, 255, 0))
        path = tmp_path / "rgb.png"
        img.save(path)

        # Load and verify
        index_map, rgba_img = load_image_preserving_indices(path)

        assert index_map is None
        assert rgba_img.mode == "RGBA"

    def test_preserved_indices_match_original(self, tmp_path) -> None:
        """Preserved indices exactly match original indexed PNG."""
        from core.services.rgb_to_indexed import load_image_preserving_indices

        # Create indexed PNG with duplicate colors at different indices
        # This is the scenario that causes BUG-1
        indexed_data = np.array(
            [
                [3, 3, 7, 7],  # Index 3 and 7 might have same color
                [3, 3, 7, 7],
            ],
            dtype=np.uint8,
        )
        # Set indices 3 and 7 to same color (red)
        palette_flat = [0] * 768
        palette_flat[3 * 3] = 255  # Index 3 = red
        palette_flat[7 * 3] = 255  # Index 7 = red (same color!)

        img = Image.fromarray(indexed_data, mode="P")
        img.putpalette(palette_flat)

        path = tmp_path / "duplicate_colors.png"
        img.save(path)

        # Load and verify indices are preserved (not remapped due to color match)
        index_map, _ = load_image_preserving_indices(path)

        assert index_map is not None
        # Indices should be preserved exactly, even though colors are the same
        np.testing.assert_array_equal(index_map, indexed_data)

    def test_indexed_png_palette_match_preserves_index_map(self, tmp_path) -> None:
        """Indexed PNG preserves index map when palette matches sheet palette."""
        from core.services.rgb_to_indexed import load_image_preserving_indices

        indexed_data = np.array([[0, 1], [2, 3]], dtype=np.uint8)
        colors = [
            (0, 0, 0),
            (10, 20, 30),
            (40, 50, 60),
            (70, 80, 90),
            *[(0, 0, 0)] * 12,
        ]

        palette_flat: list[int] = []
        for r, g, b in colors:
            palette_flat.extend([r, g, b])
        palette_flat.extend([0] * (768 - len(palette_flat)))

        img = Image.fromarray(indexed_data, mode="P")
        img.putpalette(palette_flat)

        path = tmp_path / "match.png"
        img.save(path)

        palette = MockSheetPalette(colors=colors)
        index_map, _ = load_image_preserving_indices(path, sheet_palette=palette)

        assert index_map is not None
        np.testing.assert_array_equal(index_map, indexed_data)

    def test_indexed_png_palette_mismatch_drops_index_map(self, tmp_path) -> None:
        """Indexed PNG returns None index map when palette mismatches sheet palette."""
        from core.services.rgb_to_indexed import load_image_preserving_indices

        indexed_data = np.array([[0, 1], [2, 3]], dtype=np.uint8)
        palette_flat = [
            0,
            0,
            0,
            10,
            20,
            30,
            40,
            50,
            60,
            70,
            80,
            90,
        ]
        palette_flat.extend([0] * (768 - len(palette_flat)))

        img = Image.fromarray(indexed_data, mode="P")
        img.putpalette(palette_flat)

        path = tmp_path / "mismatch.png"
        img.save(path)

        # Mismatched palette (second color differs)
        palette = MockSheetPalette(
            colors=[
                (0, 0, 0),
                (11, 22, 33),
                (40, 50, 60),
                (70, 80, 90),
                *[(0, 0, 0)] * 12,
            ]
        )

        index_map, _ = load_image_preserving_indices(path, sheet_palette=palette)
        assert index_map is None
