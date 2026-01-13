"""Color quantization for converting RGB images to indexed 16-color format.

This module provides algorithms for reducing full-color images to the 16-color
palette format used by SNES sprites (4bpp).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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

    Supports median-cut quantization with optional Floyd-Steinberg dithering.
    Transparency is handled by reserving index 0 for transparent pixels.
    """

    def __init__(
        self,
        dither: bool = True,
        transparency_threshold: int = 127,
        algorithm: Literal["median_cut"] = "median_cut",
    ) -> None:
        """Initialize the quantizer.

        Args:
            dither: Whether to apply Floyd-Steinberg dithering
            transparency_threshold: Alpha values below this are transparent
            algorithm: Quantization algorithm to use
        """
        self._dither = dither
        self._transparency_threshold = transparency_threshold
        self._algorithm = algorithm

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

        # Scale if target size provided
        if target_size is not None and (image.width, image.height) != target_size:
            image = image.resize(target_size, Image.Resampling.LANCZOS)

        # Convert to numpy array
        pixels = np.array(image)

        # Separate alpha channel and create transparency mask
        alpha = pixels[:, :, 3]
        transparency_mask = alpha < self._transparency_threshold

        # Extract RGB channels
        rgb = pixels[:, :, :3].astype(np.float32)

        # Get opaque pixels for palette computation
        opaque_mask = ~transparency_mask
        opaque_pixels = rgb[opaque_mask]

        # Generate palette (15 colors for opaque, index 0 reserved for transparent)
        if len(opaque_pixels) > 0:
            palette_colors = self._median_cut(opaque_pixels, 15)
        else:
            # All transparent - use grayscale palette
            palette_colors = [(i * 17, i * 17, i * 17) for i in range(15)]

        # Index 0 is transparent (black)
        full_palette: list[tuple[int, int, int]] = [(0, 0, 0), *palette_colors]

        # Pad to exactly 16 colors if needed
        while len(full_palette) < 16:
            full_palette.append((0, 0, 0))

        # Apply dithering or direct mapping
        if self._dither and len(opaque_pixels) > 0:
            indexed = self._floyd_steinberg_dither(rgb, full_palette, transparency_mask)
        else:
            indexed = self._map_to_nearest(rgb, full_palette, transparency_mask)

        return QuantizationResult(
            indexed_data=indexed,
            palette=full_palette,
            transparency_mask=transparency_mask,
        )

    def _median_cut(
        self,
        pixels: NDArray[np.float32],
        n_colors: int,
    ) -> list[tuple[int, int, int]]:
        """Generate palette using median-cut algorithm.

        Args:
            pixels: Array of RGB pixels, shape (N, 3)
            n_colors: Number of colors to generate

        Returns:
            List of RGB tuples
        """
        if len(pixels) == 0:
            return []

        # Start with all pixels in one box
        boxes: list[NDArray[np.float32]] = [pixels]

        # Split boxes until we have enough colors
        while len(boxes) < n_colors:
            # Find box with largest range to split
            best_idx = 0
            best_range = 0.0

            for i, box in enumerate(boxes):
                if len(box) < 2:
                    continue
                # Find channel with largest range
                ranges = box.max(axis=0) - box.min(axis=0)
                max_range = float(ranges.max())
                if max_range > best_range:
                    best_range = max_range
                    best_idx = i

            if best_range == 0:
                break  # Can't split further

            # Split the best box
            box = boxes.pop(best_idx)
            ranges = box.max(axis=0) - box.min(axis=0)
            split_channel = int(np.argmax(ranges))

            # Sort by the split channel and divide at median
            sorted_pixels = box[box[:, split_channel].argsort()]
            mid = len(sorted_pixels) // 2

            boxes.append(sorted_pixels[:mid])
            boxes.append(sorted_pixels[mid:])

        # Compute average color for each box
        palette: list[tuple[int, int, int]] = []
        for box in boxes:
            if len(box) > 0:
                avg = box.mean(axis=0)
                palette.append(
                    (
                        int(np.clip(avg[0], 0, 255)),
                        int(np.clip(avg[1], 0, 255)),
                        int(np.clip(avg[2], 0, 255)),
                    )
                )

        return palette

    def _floyd_steinberg_dither(
        self,
        rgb: NDArray[np.float32],
        palette: list[tuple[int, int, int]],
        transparency_mask: NDArray[np.bool_],
    ) -> NDArray[np.uint8]:
        """Apply Floyd-Steinberg dithering.

        Args:
            rgb: RGB pixel array, shape (H, W, 3)
            palette: List of 16 RGB tuples
            transparency_mask: Boolean mask where True = transparent

        Returns:
            Indexed array, shape (H, W)
        """
        height, width = rgb.shape[:2]
        indexed = np.zeros((height, width), dtype=np.uint8)

        # Work on a copy to accumulate errors
        working = rgb.copy()

        # Convert palette to array for vectorized operations
        palette_array = np.array(palette[1:], dtype=np.float32)  # Skip index 0

        for y in range(height):
            for x in range(width):
                if transparency_mask[y, x]:
                    indexed[y, x] = 0
                    continue

                old_pixel = working[y, x]

                # Find nearest color (excluding index 0)
                idx = self._find_nearest_color(old_pixel, palette_array)
                indexed[y, x] = idx + 1  # +1 because we skipped index 0

                new_pixel = np.array(palette[idx + 1], dtype=np.float32)
                error = old_pixel - new_pixel

                # Distribute error to neighbors (Floyd-Steinberg pattern)
                if x + 1 < width and not transparency_mask[y, x + 1]:
                    working[y, x + 1] += error * (7 / 16)
                if y + 1 < height:
                    if x > 0 and not transparency_mask[y + 1, x - 1]:
                        working[y + 1, x - 1] += error * (3 / 16)
                    if not transparency_mask[y + 1, x]:
                        working[y + 1, x] += error * (5 / 16)
                    if x + 1 < width and not transparency_mask[y + 1, x + 1]:
                        working[y + 1, x + 1] += error * (1 / 16)

        return indexed

    def _map_to_nearest(
        self,
        rgb: NDArray[np.float32],
        palette: list[tuple[int, int, int]],
        transparency_mask: NDArray[np.bool_],
    ) -> NDArray[np.uint8]:
        """Map pixels to nearest palette color without dithering.

        Args:
            rgb: RGB pixel array, shape (H, W, 3)
            palette: List of 16 RGB tuples
            transparency_mask: Boolean mask where True = transparent

        Returns:
            Indexed array, shape (H, W)
        """
        height, width = rgb.shape[:2]
        indexed = np.zeros((height, width), dtype=np.uint8)

        # Convert palette to array (excluding index 0)
        palette_array = np.array(palette[1:], dtype=np.float32)

        for y in range(height):
            for x in range(width):
                if transparency_mask[y, x]:
                    indexed[y, x] = 0
                else:
                    idx = self._find_nearest_color(rgb[y, x], palette_array)
                    indexed[y, x] = idx + 1

        return indexed

    def _find_nearest_color(
        self,
        pixel: NDArray[np.float32],
        palette: NDArray[np.float32],
    ) -> int:
        """Find index of nearest palette color.

        Args:
            pixel: RGB values, shape (3,)
            palette: Palette colors, shape (N, 3)

        Returns:
            Index into palette
        """
        if len(palette) == 0:
            return 0
        distances = np.sum((palette - pixel) ** 2, axis=1)
        return int(np.argmin(distances))
