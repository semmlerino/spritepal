"""Tile sampling service for extracting and quantizing sprite tiles.

This service provides shared functionality for:
- Sampling regions from overlay images with transform support
- Quantizing pixels to SNES palettes
- Calculating touched/untouched tile status

Used by both ApplyOperation (for injection) and WorkbenchCanvas (for preview).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from PIL import Image

if TYPE_CHECKING:
    from PySide6.QtCore import QRect


@dataclass
class TileCoord:
    """Coordinates for an 8x8 tile within a sprite."""

    row: int
    col: int

    @override
    def __hash__(self) -> int:
        return hash((self.row, self.col))

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TileCoord):
            return NotImplemented
        return self.row == other.row and self.col == other.col


@dataclass
class TileSampleResult:
    """Result of sampling tiles from an overlay."""

    sampled_tiles: dict[TileCoord, Image.Image]
    touched_coords: set[TileCoord]
    untouched_coords: set[TileCoord]


class TileSamplingService:
    """Service for sampling and quantizing sprite tiles.

    This service extracts tile regions from overlay images and quantizes
    them to SNES palettes. It supports arbitrary transforms (scale, flip).

    Note: Rotation is intentionally not supported because SNES hardware
    does not support arbitrary rotation for OAM sprites. Rotated tiles
    would break 8x8 tile boundaries.
    """

    SCALE_MIN = 0.1
    SCALE_MAX = 10.0

    def __init__(
        self,
        palette: list[tuple[int, int, int]] | None = None,
        color_mappings: dict[tuple[int, int, int], int] | None = None,
    ) -> None:
        """Initialize the tile sampling service.

        Args:
            palette: Optional palette for quantization (16 RGB colors).
            color_mappings: Optional custom color mappings (RGB -> palette index).
                If provided, these mappings override the default nearest-color matching.
        """
        self._palette = palette
        self._color_mappings = color_mappings

    def set_palette(self, palette: list[tuple[int, int, int]] | None) -> None:
        """Set the palette for quantization."""
        self._palette = palette

    def set_color_mappings(self, color_mappings: dict[tuple[int, int, int], int] | None) -> None:
        """Set custom color mappings."""
        self._color_mappings = color_mappings

    @staticmethod
    def clamp_scale(scale: float) -> float:
        """Clamp scale to valid range."""
        return max(TileSamplingService.SCALE_MIN, min(TileSamplingService.SCALE_MAX, scale))

    def sample_tile_region(
        self,
        image: Image.Image,
        tile_x: int,
        tile_y: int,
        tile_width: int,
        tile_height: int,
        offset_x: int = 0,
        offset_y: int = 0,
        scale: float = 1.0,
        flip_h: bool = False,
        flip_v: bool = False,
    ) -> Image.Image | None:
        """Sample a tile-sized region from an image with transform.

        The transform is applied to the source image, then the tile region
        is extracted at the specified position.

        Args:
            image: Source RGBA image to sample from.
            tile_x: X position of tile on canvas (in canvas coordinates).
            tile_y: Y position of tile on canvas (in canvas coordinates).
            tile_width: Width of tile (typically 8).
            tile_height: Height of tile (typically 8).
            offset_x: X offset of overlay relative to canvas.
            offset_y: Y offset of overlay relative to canvas.
            scale: Scale factor for the overlay image.
            flip_h: Whether to flip the overlay horizontally.
            flip_v: Whether to flip the overlay vertically.

        Returns:
            Sampled tile region as RGBA image, or None if tile not covered.
        """
        scale = self.clamp_scale(scale)

        # Apply transforms to the source image
        transformed = image
        if flip_h:
            transformed = transformed.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if flip_v:
            transformed = transformed.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        if scale != 1.0:
            new_width = int(transformed.width * scale)
            new_height = int(transformed.height * scale)
            if new_width > 0 and new_height > 0:
                transformed = transformed.resize(
                    (new_width, new_height),
                    Image.Resampling.NEAREST,
                )
            else:
                return None

        # Calculate the region to sample from the transformed image
        # The tile is at (tile_x, tile_y) on the canvas
        # The overlay is at (offset_x, offset_y) on the canvas
        # So we need to sample from (tile_x - offset_x, tile_y - offset_y) on the overlay
        sample_x = tile_x - offset_x
        sample_y = tile_y - offset_y

        # Check if tile is within the transformed image bounds
        if (
            sample_x < 0
            or sample_y < 0
            or sample_x + tile_width > transformed.width
            or sample_y + tile_height > transformed.height
        ):
            return None

        # Extract the region
        region = transformed.crop((sample_x, sample_y, sample_x + tile_width, sample_y + tile_height))
        return region

    def check_tile_coverage(
        self,
        image_width: int,
        image_height: int,
        tile_x: int,
        tile_y: int,
        tile_width: int,
        tile_height: int,
        offset_x: int = 0,
        offset_y: int = 0,
        scale: float = 1.0,
    ) -> bool:
        """Check if a tile is fully covered by the transformed overlay.

        Args:
            image_width: Width of source image.
            image_height: Height of source image.
            tile_x: X position of tile on canvas.
            tile_y: Y position of tile on canvas.
            tile_width: Width of tile (typically 8).
            tile_height: Height of tile (typically 8).
            offset_x: X offset of overlay relative to canvas.
            offset_y: Y offset of overlay relative to canvas.
            scale: Scale factor for the overlay image.

        Returns:
            True if tile is fully covered by the overlay.
        """
        scale = self.clamp_scale(scale)

        # Calculate scaled dimensions
        scaled_width = int(image_width * scale)
        scaled_height = int(image_height * scale)

        # Calculate the region to sample from the transformed image
        sample_x = tile_x - offset_x
        sample_y = tile_y - offset_y

        # Check if tile is fully within the transformed image bounds
        return (
            sample_x >= 0
            and sample_y >= 0
            and sample_x + tile_width <= scaled_width
            and sample_y + tile_height <= scaled_height
        )

    def get_touched_tiles(
        self,
        tile_rects: list[QRect],
        image_width: int,
        image_height: int,
        offset_x: int = 0,
        offset_y: int = 0,
        scale: float = 1.0,
    ) -> tuple[set[int], set[int]]:
        """Determine which tiles are touched/untouched by the overlay.

        A tile is "touched" if it is fully covered by the transformed overlay.

        Args:
            tile_rects: List of QRect defining tile positions on canvas.
            image_width: Width of source overlay image.
            image_height: Height of source overlay image.
            offset_x: X offset of overlay relative to canvas.
            offset_y: Y offset of overlay relative to canvas.
            scale: Scale factor for the overlay image.

        Returns:
            Tuple of (touched_indices, untouched_indices) as sets of indices.
        """
        touched: set[int] = set()
        untouched: set[int] = set()

        for i, rect in enumerate(tile_rects):
            if self.check_tile_coverage(
                image_width,
                image_height,
                rect.x(),
                rect.y(),
                rect.width(),
                rect.height(),
                offset_x,
                offset_y,
                scale,
            ):
                touched.add(i)
            else:
                untouched.add(i)

        return touched, untouched

    def check_content_outside_tiles(
        self,
        content_bbox: tuple[int, int, int, int] | None,
        tile_union_rect: tuple[int, int, int, int],
        offset_x: int,
        offset_y: int,
        scale: float,
    ) -> tuple[bool, list[tuple[int, int, int, int]]]:
        """Check if AI frame content extends outside the tile area.

        This detects regions of the AI frame that will be clipped during
        injection because they extend beyond the game sprite's tile boundaries.

        Args:
            content_bbox: Non-transparent content bounding box from PIL.Image.getbbox()
                in format (left, top, right, bottom) in source image coordinates.
                None if image is fully transparent.
            tile_union_rect: Union bounding box of all game tiles in scene coordinates
                (min_x, min_y, max_x, max_y).
            offset_x: X offset of AI frame in scene coordinates.
            offset_y: Y offset of AI frame in scene coordinates.
            scale: Scale factor applied to AI frame.

        Returns:
            Tuple of (has_overflow, overflow_rects) where:
            - has_overflow: True if any content extends outside tiles
            - overflow_rects: List of (x, y, w, h) rectangles in scene coordinates
              showing the clipped regions (top, bottom, left, right strips)
        """
        if content_bbox is None:
            # Fully transparent image - no overflow
            return (False, [])

        scale = self.clamp_scale(scale)

        # Transform content bbox to scene coordinates
        src_left, src_top, src_right, src_bottom = content_bbox
        scene_left = int(src_left * scale) + offset_x
        scene_top = int(src_top * scale) + offset_y
        scene_right = int(src_right * scale) + offset_x
        scene_bottom = int(src_bottom * scale) + offset_y

        tile_min_x, tile_min_y, tile_max_x, tile_max_y = tile_union_rect

        # Check if content is fully inside tiles
        if (
            scene_left >= tile_min_x
            and scene_top >= tile_min_y
            and scene_right <= tile_max_x
            and scene_bottom <= tile_max_y
        ):
            return (False, [])

        # Calculate overflow regions (strips that extend past tile bounds)
        overflow_rects: list[tuple[int, int, int, int]] = []

        # Top overflow
        if scene_top < tile_min_y:
            clip_top = scene_top
            clip_bottom = min(scene_bottom, tile_min_y)
            if clip_bottom > clip_top:
                overflow_rects.append((scene_left, clip_top, scene_right - scene_left, clip_bottom - clip_top))

        # Bottom overflow
        if scene_bottom > tile_max_y:
            clip_top = max(scene_top, tile_max_y)
            clip_bottom = scene_bottom
            if clip_bottom > clip_top:
                overflow_rects.append((scene_left, clip_top, scene_right - scene_left, clip_bottom - clip_top))

        # Left overflow (only the part not covered by top/bottom)
        if scene_left < tile_min_x:
            clip_left = scene_left
            clip_right = min(scene_right, tile_min_x)
            clip_top = max(scene_top, tile_min_y)
            clip_bottom = min(scene_bottom, tile_max_y)
            if clip_right > clip_left and clip_bottom > clip_top:
                overflow_rects.append((clip_left, clip_top, clip_right - clip_left, clip_bottom - clip_top))

        # Right overflow (only the part not covered by top/bottom)
        if scene_right > tile_max_x:
            clip_left = max(scene_left, tile_max_x)
            clip_right = scene_right
            clip_top = max(scene_top, tile_min_y)
            clip_bottom = min(scene_bottom, tile_max_y)
            if clip_right > clip_left and clip_bottom > clip_top:
                overflow_rects.append((clip_left, clip_top, clip_right - clip_left, clip_bottom - clip_top))

        return (len(overflow_rects) > 0, overflow_rects)

    def quantize_to_palette(self, image: Image.Image) -> Image.Image | None:
        """Quantize an image to the configured palette.

        Args:
            image: RGBA image to quantize.

        Returns:
            Grayscale image with palette indices (values 0-15 * 16 for 4bpp),
            or None if no palette configured or on failure.
        """
        if self._palette is None:
            return None

        if image.mode != "RGBA":
            image = image.convert("RGBA")

        # Create output image (grayscale, values 0-15 * 16 for 4bpp)
        output = Image.new("L", image.size)
        pixels_out = output.load()
        pixels_in = image.load()

        if pixels_out is None or pixels_in is None:
            return None

        for y in range(image.height):
            for x in range(image.width):
                pixel = pixels_in[x, y]
                # PIL returns tuples for RGBA images
                if not isinstance(pixel, tuple) or len(pixel) != 4:
                    continue
                r, g, b, a = pixel

                # Transparent pixel -> index 0
                if a < 128:
                    pixels_out[x, y] = 0
                    continue

                rgb = (r, g, b)

                # Check custom color mappings first (user-specified overrides)
                if self._color_mappings is not None and rgb in self._color_mappings:
                    best_idx = self._color_mappings[rgb]
                    # Ensure opaque pixels never use index 0 (transparency)
                    if best_idx == 0:
                        best_idx = 1  # Fallback to index 1
                else:
                    # Find closest palette color, skipping index 0 (reserved for transparency)
                    # SNES sprites use index 0 as the transparent color, so opaque pixels
                    # must never be assigned to index 0, even if it's the closest match.
                    min_dist = float("inf")
                    best_idx = 1  # Default to index 1 (not 0 which is transparent)
                    for idx, (pr, pg, pb) in enumerate(self._palette):
                        if idx == 0:
                            continue  # Skip index 0 for opaque pixels
                        dist = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
                        if dist < min_dist:
                            min_dist = dist
                            best_idx = idx

                # Store as grayscale value (index * 16 for 4bpp SNES format)
                pixels_out[x, y] = best_idx * 16

        return output

    def sample_and_quantize(
        self,
        image: Image.Image,
        tile_x: int,
        tile_y: int,
        tile_width: int,
        tile_height: int,
        offset_x: int = 0,
        offset_y: int = 0,
        scale: float = 1.0,
        flip_h: bool = False,
        flip_v: bool = False,
    ) -> Image.Image | None:
        """Sample a tile region and quantize to palette.

        Convenience method combining sample_tile_region and quantize_to_palette.

        Args:
            image: Source RGBA image.
            tile_x: X position of tile on canvas.
            tile_y: Y position of tile on canvas.
            tile_width: Width of tile.
            tile_height: Height of tile.
            offset_x: X offset of overlay relative to canvas.
            offset_y: Y offset of overlay relative to canvas.
            scale: Scale factor.
            flip_h: Horizontal flip.
            flip_v: Vertical flip.

        Returns:
            Quantized tile image, or None if not covered or no palette.
        """
        region = self.sample_tile_region(
            image,
            tile_x,
            tile_y,
            tile_width,
            tile_height,
            offset_x,
            offset_y,
            scale,
            flip_h,
            flip_v,
        )
        if region is None:
            return None

        if self._palette is not None:
            return self.quantize_to_palette(region)

        # No palette - convert to grayscale
        return region.convert("L")


def calculate_auto_alignment(
    ai_image: Image.Image,
    game_bbox_x: int,
    game_bbox_y: int,
    game_bbox_width: int,
    game_bbox_height: int,
) -> tuple[int, int]:
    """Calculate auto-alignment offset to center AI frame over game frame.

    Uses bounding box alignment: calculates bounding boxes of both frames
    and centers them relative to each other.

    Args:
        ai_image: AI frame image (RGBA).
        game_bbox_x: X coordinate of game frame bounding box.
        game_bbox_y: Y coordinate of game frame bounding box.
        game_bbox_width: Width of game frame bounding box.
        game_bbox_height: Height of game frame bounding box.

    Returns:
        Tuple of (offset_x, offset_y) to apply to AI frame.
    """
    # Calculate AI frame bounding box (non-transparent pixels)
    ai_bbox = ai_image.getbbox()
    if ai_bbox is None:
        # No non-transparent pixels - center the whole image
        ai_bbox = (0, 0, ai_image.width, ai_image.height)

    ai_x, ai_y, ai_x2, ai_y2 = ai_bbox
    ai_width = ai_x2 - ai_x
    ai_height = ai_y2 - ai_y

    # Calculate centers
    ai_center_x = ai_x + ai_width // 2
    ai_center_y = ai_y + ai_height // 2

    game_center_x = game_bbox_x + game_bbox_width // 2
    game_center_y = game_bbox_y + game_bbox_height // 2

    # Calculate offset to align centers
    offset_x = game_center_x - ai_center_x
    offset_y = game_center_y - ai_center_y

    return offset_x, offset_y
