"""Quantization strategies for tile injection.

Encapsulates the 4 different quantization paths:
1. Index passthrough - preserve original palette indices
2. Palette mapping - use explicit color mappings
3. Standard quantization - k-means to target palette
4. Capture fallback - use capture's original palette
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, override

import numpy as np
from PIL import Image

from core.palette_utils import (
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    quantize_to_palette,
    quantize_with_mappings,
    snap_to_snes_color,
)
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette

logger = get_logger(__name__)


class QuantizationStrategy(ABC):
    """Base class for quantization strategies."""

    @abstractmethod
    def quantize(
        self,
        chunk_image: Image.Image,
        chunk_index_map: np.ndarray | None,
        sheet_palette: SheetPalette | None,
        capture_palette_rgb: list[tuple[int, int, int]] | None,
        rom_offset: int,
    ) -> Image.Image:
        """Quantize an RGBA chunk image to indexed palette.

        Args:
            chunk_image: RGBA image to quantize
            chunk_index_map: Optional preserved index map from AI frame
            sheet_palette: Optional sheet palette with colors/mappings
            capture_palette_rgb: Optional capture palette (RGB tuples)
            rom_offset: ROM offset for logging

        Returns:
            Quantized indexed image
        """
        ...


class IndexPassthroughStrategy(QuantizationStrategy):
    """Use preserved palette indices directly (no re-quantization).

    This strategy creates an indexed image directly from the index map,
    bypassing color-based quantization entirely. This preserves exact
    palette indices even when colors are duplicated.

    Requires:
    - chunk_index_map with no 255 markers (outside AI frame area)
    - sheet_palette with colors defined
    """

    @override
    def quantize(
        self,
        chunk_image: Image.Image,
        chunk_index_map: np.ndarray | None,
        sheet_palette: SheetPalette | None,
        capture_palette_rgb: list[tuple[int, int, int]] | None,
        rom_offset: int,
    ) -> Image.Image:
        if chunk_index_map is None or sheet_palette is None:
            raise ValueError("IndexPassthroughStrategy requires index map and sheet palette")

        logger.debug(
            "ROM offset 0x%X: Using index passthrough (preserving palette indices)",
            rom_offset,
        )

        # Build PIL palette from sheet colors
        palette_flat: list[int] = []
        for r, g, b in sheet_palette.colors:
            palette_flat.extend([r, g, b])
        # Pad to 256 colors (PIL requirement)
        palette_flat.extend([0] * (768 - len(palette_flat)))

        # Create indexed image directly from index map
        result = Image.fromarray(chunk_index_map, mode="P")
        result.putpalette(palette_flat)
        return result


class PaletteMappingStrategy(QuantizationStrategy):
    """Use color_mappings dict for explicit index assignment.

    When the user has defined explicit color-to-index mappings,
    use those instead of nearest-color matching.

    Requires:
    - sheet_palette with color_mappings defined
    """

    @override
    def quantize(
        self,
        chunk_image: Image.Image,
        chunk_index_map: np.ndarray | None,
        sheet_palette: SheetPalette | None,
        capture_palette_rgb: list[tuple[int, int, int]] | None,
        rom_offset: int,
    ) -> Image.Image:
        if sheet_palette is None or not sheet_palette.color_mappings:
            raise ValueError("PaletteMappingStrategy requires sheet palette with color_mappings")

        # Snap palette to SNES-valid colors (matches preview pipeline)
        palette_rgb = [snap_to_snes_color(c) for c in sheet_palette.colors]

        return quantize_with_mappings(
            chunk_image,
            palette_rgb,
            sheet_palette.color_mappings,
            transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
        )


class StandardQuantizationStrategy(QuantizationStrategy):
    """K-means quantization to target palette.

    Standard color-matching quantization using the sheet palette.
    Each pixel is assigned to the nearest palette color.

    Requires:
    - sheet_palette with colors defined
    """

    @override
    def quantize(
        self,
        chunk_image: Image.Image,
        chunk_index_map: np.ndarray | None,
        sheet_palette: SheetPalette | None,
        capture_palette_rgb: list[tuple[int, int, int]] | None,
        rom_offset: int,
    ) -> Image.Image:
        if sheet_palette is None:
            raise ValueError("StandardQuantizationStrategy requires sheet palette")

        # Snap palette to SNES-valid colors (matches preview pipeline)
        palette_rgb = [snap_to_snes_color(c) for c in sheet_palette.colors]

        return quantize_to_palette(
            chunk_image,
            palette_rgb,
            transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
        )


class CapturePaletteFallbackStrategy(QuantizationStrategy):
    """Fall back to capture's original palette.

    When no sheet palette is defined, use the palette from the
    original Mesen capture. This preserves the game's original colors.

    Requires:
    - capture_palette_rgb (from filtered capture)
    """

    @override
    def quantize(
        self,
        chunk_image: Image.Image,
        chunk_index_map: np.ndarray | None,
        sheet_palette: SheetPalette | None,
        capture_palette_rgb: list[tuple[int, int, int]] | None,
        rom_offset: int,
    ) -> Image.Image:
        if not capture_palette_rgb:
            logger.warning("No capture palette available, returning original image")
            return chunk_image

        return quantize_to_palette(
            chunk_image,
            capture_palette_rgb,
            transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
        )


def select_quantization_strategy(
    chunk_index_map: np.ndarray | None,
    sheet_palette: SheetPalette | None,
    capture_palette_rgb: list[tuple[int, int, int]] | None,
) -> QuantizationStrategy:
    """Select the appropriate quantization strategy based on available data.

    Priority order:
    1. Index passthrough (if index map valid and sheet palette exists)
    2. Palette mapping (if sheet palette has color_mappings)
    3. Standard quantization (if sheet palette exists)
    4. Capture palette fallback (last resort)

    Args:
        chunk_index_map: Optional preserved index map
        sheet_palette: Optional sheet palette
        capture_palette_rgb: Optional capture palette

    Returns:
        Appropriate QuantizationStrategy instance
    """
    # Check for index passthrough eligibility
    if chunk_index_map is not None and sheet_palette is not None:
        # Check if index map has valid data (no 255 markers = outside AI frame area)
        if not np.any(chunk_index_map == 255):
            return IndexPassthroughStrategy()

    # Check for palette mapping
    if sheet_palette is not None and sheet_palette.color_mappings:
        return PaletteMappingStrategy()

    # Check for standard quantization
    if sheet_palette is not None:
        return StandardQuantizationStrategy()

    # Fallback to capture palette
    return CapturePaletteFallbackStrategy()
