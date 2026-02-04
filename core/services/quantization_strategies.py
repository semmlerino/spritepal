"""Quantization strategies for tile injection.

Encapsulates the 4 different quantization paths:
1. Palette mapping - use explicit color mappings
2. Index passthrough - preserve original palette indices (when no mappings)
3. Standard quantization - nearest color to target palette
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

    def __init__(
        self,
        *,
        alpha_threshold: int = QUANTIZATION_TRANSPARENCY_THRESHOLD,
        dither_mode: str = "none",
        dither_strength: float = 0.0,
    ) -> None:
        self._alpha_threshold = max(0, min(255, alpha_threshold))
        self._dither_mode = dither_mode if dither_mode in {"none", "bayer"} else "none"
        self._dither_strength = max(0.0, min(1.0, float(dither_strength)))

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

        # Build palette for PIL (flat list, padded to 256 colors)
        palette_flat: list[int] = []
        for r, g, b in palette_rgb:
            palette_flat.extend([r, g, b])
        palette_flat.extend([0] * (768 - len(palette_flat)))

        # Use index map where valid (not 255), fall back to quantization elsewhere
        # This implements "quantize full-res, scale indexed" for injection parity
        if chunk_index_map is not None and np.any(chunk_index_map != 255):
            # Baseline quantization for 255-marked regions (outside AI frame)
            baseline = quantize_with_mappings(
                chunk_image,
                palette_rgb,
                sheet_palette.color_mappings,
                transparency_threshold=self._alpha_threshold,
                dither_mode=self._dither_mode,
                dither_strength=self._dither_strength,
            )

            # Overlay pre-computed indices where valid
            pixels = np.array(baseline)
            mask = chunk_index_map != 255
            pixels[mask] = chunk_index_map[mask]

            # Rebuild indexed image
            result = Image.fromarray(pixels, mode="P")
            result.putpalette(palette_flat)
            return result

        # No index map - fall back to standard quantization
        return quantize_with_mappings(
            chunk_image,
            palette_rgb,
            sheet_palette.color_mappings,
            transparency_threshold=self._alpha_threshold,
            dither_mode=self._dither_mode,
            dither_strength=self._dither_strength,
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
            transparency_threshold=self._alpha_threshold,
            dither_mode=self._dither_mode,
            dither_strength=self._dither_strength,
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
            transparency_threshold=self._alpha_threshold,
            dither_mode=self._dither_mode,
            dither_strength=self._dither_strength,
        )


def select_quantization_strategy(
    chunk_index_map: np.ndarray | None,
    sheet_palette: SheetPalette | None,
    capture_palette_rgb: list[tuple[int, int, int]] | None,
    *,
    alpha_threshold: int = QUANTIZATION_TRANSPARENCY_THRESHOLD,
    dither_mode: str = "none",
    dither_strength: float = 0.0,
) -> QuantizationStrategy:
    """Select the appropriate quantization strategy based on available data.

    Priority order:
    1. Palette mapping (if sheet palette has color_mappings)
    2. Index passthrough (if index map valid and sheet palette exists, and no mappings)
    3. Standard quantization (if sheet palette exists)
    4. Capture palette fallback (last resort)

    Args:
        chunk_index_map: Optional preserved index map
        sheet_palette: Optional sheet palette
        capture_palette_rgb: Optional capture palette

    Returns:
        Appropriate QuantizationStrategy instance
    """
    # Check for palette mapping (explicit user mappings take precedence)
    if sheet_palette is not None and sheet_palette.color_mappings:
        return PaletteMappingStrategy(
            alpha_threshold=alpha_threshold,
            dither_mode=dither_mode,
            dither_strength=dither_strength,
        )

    # Check for index passthrough eligibility (only when no mappings)
    if chunk_index_map is not None and sheet_palette is not None:
        # Check if index map has valid data:
        # - No 255 markers (outside AI frame area)
        # - All indices within 4bpp range (0-15)
        max_index = int(np.max(chunk_index_map))
        has_outside_markers = np.any(chunk_index_map == 255)
        if not has_outside_markers and max_index <= 15:
            return IndexPassthroughStrategy(
                alpha_threshold=alpha_threshold,
                dither_mode=dither_mode,
                dither_strength=dither_strength,
            )
        elif max_index > 15:
            logger.debug(
                "Index passthrough skipped: max index %d exceeds 4bpp limit (0-15), "
                "falling back to color-based quantization",
                max_index,
            )

    # Check for standard quantization
    if sheet_palette is not None:
        return StandardQuantizationStrategy(
            alpha_threshold=alpha_threshold,
            dither_mode=dither_mode,
            dither_strength=dither_strength,
        )

    # Fallback to capture palette
    return CapturePaletteFallbackStrategy(
        alpha_threshold=alpha_threshold,
        dither_mode=dither_mode,
        dither_strength=dither_strength,
    )
