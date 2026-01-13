"""Color quantization for converting RGB images to indexed 16-color format.

This module provides algorithms for reducing full-color images to the 16-color
palette format used by SNES sprites (4bpp).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image


@dataclass
class QuantizationResult:
    """Result of color quantization.

    Attributes:
        indexed_data: 2D array (H, W) of palette indices 0-15
        palette: List of 16 RGB tuples
        transparency_mask: Optional boolean mask where True = transparent pixel
    """

    indexed_data: NDArray[np.uint8]
    palette: list[tuple[int, int, int]]
    transparency_mask: NDArray[np.bool_] | None = None


class ColorQuantizer:
    """Quantizes RGB/RGBA images to 16-color indexed format.

    Uses PIL's FASTOCTREE quantization for better color preservation in pixel art.
    Transparency is handled by reserving index 0 for transparent pixels.
    """

    def __init__(
        self,
        dither: bool = True,
        transparency_threshold: int = 127,
    ) -> None:
        """Initialize the quantizer.

        Args:
            dither: Whether to apply Floyd-Steinberg dithering
            transparency_threshold: Alpha values below this are transparent
        """
        self._dither = dither
        self._transparency_threshold = transparency_threshold

    def quantize(
        self,
        image: Image.Image,
        target_size: tuple[int, int] | None = None,
    ) -> QuantizationResult:
        """Quantize an image to 16 colors.

        Args:
            image: PIL Image in RGB or RGBA mode
            target_size: Optional (width, height) to scale image to

        Returns:
            QuantizationResult with indexed data, palette, and transparency mask
        """
        # Convert to RGBA if needed
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        # Scale uniformly to fit within target size, preserving aspect ratio
        if target_size is not None:
            target_w, target_h = target_size
            scale = min(target_w / image.width, target_h / image.height)

            if scale < 1.0:  # Only scale down, not up
                new_w = int(image.width * scale)
                new_h = int(image.height * scale)
                scaled = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            else:
                scaled = image

            # Create transparent canvas at target size
            canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))

            # Center the scaled image
            paste_x = (target_w - scaled.width) // 2
            paste_y = (target_h - scaled.height) // 2
            canvas.paste(scaled, (paste_x, paste_y))

            image = canvas

        # Convert to numpy array
        pixels = np.array(image)

        # Separate alpha channel and create transparency mask
        alpha = pixels[:, :, 3]
        transparency_mask = alpha < self._transparency_threshold

        # Check if there are any opaque pixels
        has_opaque = not transparency_mask.all()

        if has_opaque:
            # Create RGB image for quantization (transparent pixels get black)
            rgb_image = Image.new("RGB", image.size, (0, 0, 0))
            rgb_image.paste(image, mask=image.split()[3])

            # Use PIL's FASTOCTREE for better color preservation in pixel art
            dither_mode = Image.Dither.FLOYDSTEINBERG if self._dither else Image.Dither.NONE
            quantized = rgb_image.quantize(
                colors=15,  # Reserve index 0 for transparency
                method=Image.Quantize.FASTOCTREE,
                dither=dither_mode,
            )

            # Extract palette from quantized image
            pil_palette = quantized.getpalette()
            if pil_palette is None:
                palette_colors: list[tuple[int, int, int]] = [(0, 0, 0)] * 15
            else:
                palette_colors = [
                    (pil_palette[i * 3], pil_palette[i * 3 + 1], pil_palette[i * 3 + 2]) for i in range(15)
                ]

            # Convert indexed image to numpy, offset indices by 1 for transparency
            indexed = np.array(quantized, dtype=np.uint8)
            indexed = indexed + 1  # Shift all indices up by 1
            indexed[transparency_mask] = 0  # Set transparent pixels to index 0
        else:
            # All transparent - create empty indexed image
            indexed = np.zeros((image.height, image.width), dtype=np.uint8)
            palette_colors = [(0, 0, 0)] * 15

        # Build full palette with index 0 = transparent (black)
        full_palette: list[tuple[int, int, int]] = [(0, 0, 0), *palette_colors]

        # Pad to exactly 16 colors if needed
        while len(full_palette) < 16:
            full_palette.append((0, 0, 0))

        return QuantizationResult(
            indexed_data=indexed,
            palette=full_palette,
            transparency_mask=transparency_mask,
        )
