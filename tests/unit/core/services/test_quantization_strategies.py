"""Tests for quantization strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image

from core.services.quantization_strategies import (
    CapturePaletteFallbackStrategy,
    IndexPassthroughStrategy,
    PaletteMappingStrategy,
    StandardQuantizationStrategy,
    select_quantization_strategy,
)


@dataclass
class MockSheetPalette:
    """Minimal sheet palette for testing."""

    colors: list[tuple[int, int, int]]
    color_mappings: dict[tuple[int, int, int], int] | None = None


class TestIndexPassthroughStrategy:
    """Tests for index passthrough strategy."""

    def test_creates_indexed_image_from_index_map(self) -> None:
        """Should create P-mode image directly from index map."""
        strategy = IndexPassthroughStrategy()

        # 8x8 index map with values 0-3
        index_map = np.array([[i % 4 for i in range(8)] for _ in range(8)], dtype=np.uint8)

        palette = MockSheetPalette(colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)])

        chunk_image = Image.new("RGBA", (8, 8))

        result = strategy.quantize(
            chunk_image=chunk_image,
            chunk_index_map=index_map,
            sheet_palette=palette,
            capture_palette_rgb=None,
            rom_offset=0x100,
        )

        assert result.mode == "P"
        assert result.size == (8, 8)
        # First pixel should have index 0
        assert result.getpixel((0, 0)) == 0

    def test_raises_without_index_map(self) -> None:
        strategy = IndexPassthroughStrategy()
        palette = MockSheetPalette(colors=[(255, 0, 0)])

        with pytest.raises(ValueError, match="requires index map"):
            strategy.quantize(
                chunk_image=Image.new("RGBA", (8, 8)),
                chunk_index_map=None,
                sheet_palette=palette,
                capture_palette_rgb=None,
                rom_offset=0x100,
            )

    def test_raises_without_sheet_palette(self) -> None:
        strategy = IndexPassthroughStrategy()
        index_map = np.zeros((8, 8), dtype=np.uint8)

        with pytest.raises(ValueError, match="requires index map and sheet palette"):
            strategy.quantize(
                chunk_image=Image.new("RGBA", (8, 8)),
                chunk_index_map=index_map,
                sheet_palette=None,
                capture_palette_rgb=None,
                rom_offset=0x100,
            )


class TestPaletteMappingStrategy:
    """Tests for palette mapping strategy."""

    def test_uses_color_mappings(self) -> None:
        """Should use explicit color mappings for quantization."""
        strategy = PaletteMappingStrategy()

        # Create RGBA image with specific colors
        chunk_image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

        # Palette must have 16 colors for SNES
        colors = [(0, 0, 0), (248, 0, 0), (0, 248, 0)]
        colors.extend([(0, 0, 0)] * 13)
        palette = MockSheetPalette(
            colors=colors,
            color_mappings={(248, 0, 0): 1},  # Red maps to index 1
        )

        result = strategy.quantize(
            chunk_image=chunk_image,
            chunk_index_map=None,
            sheet_palette=palette,
            capture_palette_rgb=None,
            rom_offset=0x100,
        )

        assert result.mode == "P"

    def test_handles_empty_color_mappings(self) -> None:
        """Should handle empty color_mappings by falling back to perceptual matching."""
        strategy = PaletteMappingStrategy()
        colors = [(248, 0, 0)]
        colors.extend([(0, 0, 0)] * 15)
        palette = MockSheetPalette(colors=colors, color_mappings={})  # Empty dict

        result = strategy.quantize(
            chunk_image=Image.new("RGBA", (8, 8), (255, 0, 0, 255)),
            chunk_index_map=None,
            sheet_palette=palette,
            capture_palette_rgb=None,
            rom_offset=0x100,
        )

        assert result.mode == "P"  # Should succeed, not raise


class TestStandardQuantizationStrategy:
    """Tests for standard quantization strategy."""

    def test_quantizes_to_palette(self) -> None:
        """Should quantize using nearest color matching."""
        strategy = StandardQuantizationStrategy()

        # Create RGBA image
        chunk_image = Image.new("RGBA", (8, 8), (250, 5, 5, 255))  # Near red

        # Palette must have 16 colors for SNES
        colors = [(0, 0, 0), (248, 0, 0), (0, 248, 0)]  # Black, Red, Green
        colors.extend([(0, 0, 0)] * 13)
        palette = MockSheetPalette(colors=colors)

        result = strategy.quantize(
            chunk_image=chunk_image,
            chunk_index_map=None,
            sheet_palette=palette,
            capture_palette_rgb=None,
            rom_offset=0x100,
        )

        assert result.mode == "P"

    def test_raises_without_sheet_palette(self) -> None:
        strategy = StandardQuantizationStrategy()

        with pytest.raises(ValueError, match="requires sheet palette"):
            strategy.quantize(
                chunk_image=Image.new("RGBA", (8, 8)),
                chunk_index_map=None,
                sheet_palette=None,
                capture_palette_rgb=None,
                rom_offset=0x100,
            )


class TestCapturePaletteFallbackStrategy:
    """Tests for capture palette fallback strategy."""

    def test_uses_capture_palette(self) -> None:
        """Should quantize using capture's original palette."""
        strategy = CapturePaletteFallbackStrategy()

        chunk_image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        # Palette must have 16 colors for SNES
        capture_palette: list[tuple[int, int, int]] = [(0, 0, 0), (248, 0, 0), (0, 248, 0)]
        capture_palette.extend([(0, 0, 0)] * 13)

        result = strategy.quantize(
            chunk_image=chunk_image,
            chunk_index_map=None,
            sheet_palette=None,
            capture_palette_rgb=capture_palette,
            rom_offset=0x100,
        )

        assert result.mode == "P"

    def test_returns_original_without_capture_palette(self) -> None:
        """Should return original image if no capture palette."""
        strategy = CapturePaletteFallbackStrategy()

        chunk_image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

        result = strategy.quantize(
            chunk_image=chunk_image,
            chunk_index_map=None,
            sheet_palette=None,
            capture_palette_rgb=None,
            rom_offset=0x100,
        )

        # Returns original RGBA when no palette available
        assert result.mode == "RGBA"


class TestSelectQuantizationStrategy:
    """Tests for strategy selection function."""

    def test_selects_index_passthrough_when_valid(self) -> None:
        """Should select index passthrough when index map is valid."""
        index_map = np.zeros((8, 8), dtype=np.uint8)  # No 255 markers
        colors = [(248, 0, 0)]
        colors.extend([(0, 0, 0)] * 15)
        palette = MockSheetPalette(colors=colors)

        strategy = select_quantization_strategy(index_map, palette, None)

        assert isinstance(strategy, IndexPassthroughStrategy)

    def test_skips_passthrough_when_index_map_has_255(self) -> None:
        """Should not use passthrough when index map has 255 markers."""
        index_map = np.zeros((8, 8), dtype=np.uint8)
        index_map[0, 0] = 255  # Outside AI frame marker

        colors = [(248, 0, 0)]
        colors.extend([(0, 0, 0)] * 15)
        palette = MockSheetPalette(colors=colors)

        strategy = select_quantization_strategy(index_map, palette, None)

        # Should fall through to palette mapping (handles empty mappings via perceptual fallback)
        assert isinstance(strategy, PaletteMappingStrategy)

    def test_skips_passthrough_when_indices_exceed_4bpp(self) -> None:
        """Should not use passthrough when indices exceed 4bpp limit (>15)."""
        index_map = np.zeros((8, 8), dtype=np.uint8)
        index_map[0, 0] = 97  # Index exceeds 4bpp limit

        colors = [(248, 0, 0)]
        colors.extend([(0, 0, 0)] * 15)
        palette = MockSheetPalette(colors=colors)

        strategy = select_quantization_strategy(index_map, palette, None)

        # Should fall through to palette mapping (handles empty mappings via perceptual fallback)
        assert isinstance(strategy, PaletteMappingStrategy)

    def test_selects_palette_mapping_when_has_mappings(self) -> None:
        """Should select palette mapping when color_mappings exists."""
        index_map = np.full((8, 8), 255, dtype=np.uint8)  # Invalid index map

        colors = [(248, 0, 0)]
        colors.extend([(0, 0, 0)] * 15)
        palette = MockSheetPalette(colors=colors, color_mappings={(248, 0, 0): 0})

        strategy = select_quantization_strategy(index_map, palette, None)

        assert isinstance(strategy, PaletteMappingStrategy)

    def test_selects_palette_mapping_when_sheet_palette_only(self) -> None:
        """Should select palette mapping with just sheet palette (perceptual fallback)."""
        colors = [(248, 0, 0)]
        colors.extend([(0, 0, 0)] * 15)
        palette = MockSheetPalette(colors=colors)

        strategy = select_quantization_strategy(None, palette, None)

        # PaletteMappingStrategy handles empty mappings via perceptual fallback
        assert isinstance(strategy, PaletteMappingStrategy)

    def test_selects_capture_fallback_when_no_sheet_palette(self) -> None:
        """Should select capture fallback when no sheet palette."""
        capture_palette: list[tuple[int, int, int]] = [(248, 0, 0)]
        capture_palette.extend([(0, 0, 0)] * 15)

        strategy = select_quantization_strategy(None, None, capture_palette)

        assert isinstance(strategy, CapturePaletteFallbackStrategy)

    def test_priority_passthrough_over_mapping(self) -> None:
        """Index passthrough takes priority when index map is valid 4bpp."""
        index_map = np.zeros((8, 8), dtype=np.uint8)  # Valid 4bpp indices

        colors = [(248, 0, 0)]
        colors.extend([(0, 0, 0)] * 15)
        palette = MockSheetPalette(colors=colors, color_mappings={(248, 0, 0): 0})

        strategy = select_quantization_strategy(index_map, palette, None)

        # Valid index map wins - preserves exact indices from indexed PNG
        assert isinstance(strategy, IndexPassthroughStrategy)
