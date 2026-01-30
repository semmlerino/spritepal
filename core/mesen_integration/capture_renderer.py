"""
Renderer for Mesen 2 sprite captures.

Takes parsed capture data and renders sprites using the captured tile data
and palettes from VRAM/CGRAM.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from core.mesen_integration.click_extractor import CaptureResult, OAMEntry, TileData
from utils.logging_config import get_logger

logger = get_logger(__name__)


def snes_color_to_rgb(color: int) -> tuple[int, int, int]:
    """
    Convert SNES 15-bit color to RGB.

    SNES format: 0bbbbbgggggrrrrr (little-endian)

    Args:
        color: 16-bit value containing 15-bit SNES color

    Returns:
        Tuple of (R, G, B) values 0-255
    """
    r = (color & 0x1F) << 3
    g = ((color >> 5) & 0x1F) << 3
    b = ((color >> 10) & 0x1F) << 3
    # Extend 5-bit to 8-bit properly
    r = r | (r >> 5)
    g = g | (g >> 5)
    b = b | (b >> 5)
    return (r, g, b)


def decode_4bpp_tile(tile_data: bytes) -> list[list[int]]:
    """
    Decode a 4bpp SNES tile to pixel indices.

    SNES 4bpp format: 32 bytes per 8x8 tile
    - Bytes 0-15: Bitplanes 0-1
    - Bytes 16-31: Bitplanes 2-3

    Args:
        tile_data: 32 bytes of tile data

    Returns:
        8x8 list of pixel indices (0-15)
    """
    if len(tile_data) != 32:
        logger.warning(f"Invalid tile data size: {len(tile_data)} (expected 32)")
        return [[0] * 8 for _ in range(8)]

    pixels: list[list[int]] = []

    for y in range(8):
        row: list[int] = []
        row_offset = y * 2

        bp0 = tile_data[row_offset]
        bp1 = tile_data[row_offset + 1]
        bp2 = tile_data[row_offset + 16]
        bp3 = tile_data[row_offset + 17]

        for x in range(8):
            bit = 7 - x
            pixel = (
                ((bp0 >> bit) & 1)
                | (((bp1 >> bit) & 1) << 1)
                | (((bp2 >> bit) & 1) << 2)
                | (((bp3 >> bit) & 1) << 3)
            )
            row.append(pixel)

        pixels.append(row)

    return pixels


def decode_4bpp_tile_vectorized(tile_data: bytes) -> np.ndarray:
    """
    Decode a 4bpp SNES tile to pixel indices using vectorized operations.

    SNES 4bpp format: 32 bytes per 8x8 tile
    - Bytes 0-15: Bitplanes 0-1
    - Bytes 16-31: Bitplanes 2-3

    Args:
        tile_data: 32 bytes of tile data

    Returns:
        8x8 numpy array of pixel indices (0-15), dtype uint8
    """
    if len(tile_data) != 32:
        logger.warning(f"Invalid tile data size: {len(tile_data)} (expected 32)")
        return np.zeros((8, 8), dtype=np.uint8)

    # Convert bytes to numpy array for vectorized bit manipulation
    data = np.frombuffer(tile_data, dtype=np.uint8)

    # Extract bitplanes - data is interleaved: bp0, bp1 for rows 0-7, then bp2, bp3
    bp0 = data[0:16:2]  # bytes 0, 2, 4, ..., 14 (8 values, one per row)
    bp1 = data[1:16:2]  # bytes 1, 3, 5, ..., 15
    bp2 = data[16:32:2]  # bytes 16, 18, 20, ..., 30
    bp3 = data[17:32:2]  # bytes 17, 19, 21, ..., 31

    # Create bit masks for columns 0-7 (bit 7 = col 0, bit 0 = col 7)
    bit_masks = np.array([128, 64, 32, 16, 8, 4, 2, 1], dtype=np.uint8)

    # Expand bitplanes to 8x8 by broadcasting: (8,) x (8,) -> (8, 8)
    # bp0[:, np.newaxis] is shape (8, 1), bit_masks is shape (8,)
    # Result is (8, 8) where each row is the bitplane value masked for each column
    plane0 = ((bp0[:, np.newaxis] & bit_masks) != 0).astype(np.uint8)
    plane1 = ((bp1[:, np.newaxis] & bit_masks) != 0).astype(np.uint8)
    plane2 = ((bp2[:, np.newaxis] & bit_masks) != 0).astype(np.uint8)
    plane3 = ((bp3[:, np.newaxis] & bit_masks) != 0).astype(np.uint8)

    # Combine bitplanes: pixel = bp0 | (bp1 << 1) | (bp2 << 2) | (bp3 << 3)
    pixels = plane0 | (plane1 << 1) | (plane2 << 2) | (plane3 << 3)

    return pixels


class CaptureRenderer:
    """Renderer for Mesen 2 sprite captures."""

    def __init__(self, capture: CaptureResult):
        """
        Initialize renderer with capture data.

        Args:
            capture: Parsed capture result
        """
        self.capture = capture
        self._rgb_palettes: dict[int, list[tuple[int, int, int]]] = {}
        self._convert_palettes()

    def _convert_palettes(self) -> None:
        """Convert palettes to RGB tuples.

        Handles both SNES BGR555 integers and pre-converted RGB triplets.
        """
        for pal_idx, colors in self.capture.palettes.items():
            rgb_colors: list[tuple[int, int, int]] = []
            for c in colors:
                if isinstance(c, int):
                    # SNES BGR555 format - needs conversion
                    rgb_colors.append(snes_color_to_rgb(c))
                else:
                    # Already RGB triplet (list[int]) - convert to tuple
                    rgb_colors.append((int(c[0]), int(c[1]), int(c[2])))
            self._rgb_palettes[pal_idx] = rgb_colors

    def render_entry(
        self,
        entry: OAMEntry,
        transparent_bg: bool = True,
    ) -> Image.Image:
        """
        Render a single OAM entry to an image using vectorized operations.

        Args:
            entry: OAM entry to render
            transparent_bg: If True, use transparent background (RGBA)

        Returns:
            PIL Image of the sprite
        """
        width = entry.width
        height = entry.height

        # Get palette for this sprite
        palette = self._rgb_palettes.get(entry.palette)
        if palette is None:
            logger.warning(f"Palette {entry.palette} not found, using grayscale")
            palette = [(i * 17, i * 17, i * 17) for i in range(16)]

        # Convert palette to numpy array for vectorized lookup
        if transparent_bg:
            # RGBA palette: index 0 is transparent
            palette_array = np.zeros((16, 4), dtype=np.uint8)
            for i, (r, g, b) in enumerate(palette):
                if i == 0:
                    palette_array[i] = [0, 0, 0, 0]  # Transparent
                else:
                    palette_array[i] = [r, g, b, 255]
            canvas = np.zeros((height, width, 4), dtype=np.uint8)
        else:
            palette_array = np.array(palette, dtype=np.uint8)
            canvas = np.zeros((height, width, 3), dtype=np.uint8)

        # Render each tile using vectorized operations
        for tile in entry.tiles:
            self._render_tile_vectorized(
                canvas,
                tile,
                palette_array,
                entry.flip_h,
                entry.flip_v,
                entry.width,
                entry.height,
                transparent_bg,
            )

        # Convert numpy array to PIL Image
        mode = "RGBA" if transparent_bg else "RGB"
        return Image.fromarray(canvas, mode=mode)

    def render_entry_indexed(
        self,
        entry: OAMEntry,
    ) -> Image.Image:
        """
        Render a single OAM entry as indexed grayscale using vectorized operations.

        This produces a grayscale image where pixel values represent
        palette indices (scaled to 0-255). This allows the arrangement
        dialog's colorizer to apply palettes on demand.

        Pixel mapping: palette index N -> gray value N * 17
        (0 -> 0, 1 -> 17, ..., 15 -> 255)

        Index 0 is transparent (alpha = 0), others are opaque.

        Args:
            entry: OAM entry to render

        Returns:
            RGBA grayscale image with indexed pixel values
        """
        width = entry.width
        height = entry.height

        # Create indexed palette: (gray, gray, gray, alpha)
        # Index 0 is transparent, others are opaque
        indexed_palette = np.zeros((16, 4), dtype=np.uint8)
        for i in range(16):
            gray = i * 17
            if i == 0:
                indexed_palette[i] = [0, 0, 0, 0]  # Transparent
            else:
                indexed_palette[i] = [gray, gray, gray, 255]

        canvas = np.zeros((height, width, 4), dtype=np.uint8)

        # Render each tile with indexed values using vectorized operations
        for tile in entry.tiles:
            self._render_tile_vectorized(
                canvas,
                tile,
                indexed_palette,
                entry.flip_h,
                entry.flip_v,
                entry.width,
                entry.height,
                transparent_bg=True,
            )

        return Image.fromarray(canvas, mode="RGBA")

    def _render_tile_vectorized(
        self,
        canvas: np.ndarray,
        tile: TileData,
        palette_array: np.ndarray,
        flip_h: bool,
        flip_v: bool,
        sprite_width: int,
        sprite_height: int,
        transparent_bg: bool,
    ) -> None:
        """Render a single tile onto the canvas using vectorized operations.

        Args:
            canvas: Numpy array (H, W, 3 or 4) to render onto
            tile: Tile data to render
            palette_array: Numpy array (16, 3 or 4) of RGB/RGBA colors
            flip_h: Horizontal flip flag
            flip_v: Vertical flip flag
            sprite_width: Total sprite width
            sprite_height: Total sprite height
            transparent_bg: Whether index 0 is transparent
        """
        # Decode tile data to 8x8 numpy array of indices
        pixels = decode_4bpp_tile_vectorized(tile.data_bytes)

        # Calculate tile position in sprite
        tile_x = tile.pos_x * 8
        tile_y = tile.pos_y * 8

        # Handle flipping at tile level
        if flip_h:
            tile_x = sprite_width - tile_x - 8
        if flip_v:
            tile_y = sprite_height - tile_y - 8

        # Apply pixel-level flipping using numpy slicing
        if flip_h:
            pixels = pixels[:, ::-1]
        if flip_v:
            pixels = pixels[::-1, :]

        # Calculate destination bounds with clipping
        dest_x_start = max(0, tile_x)
        dest_y_start = max(0, tile_y)
        dest_x_end = min(sprite_width, tile_x + 8)
        dest_y_end = min(sprite_height, tile_y + 8)

        # Calculate source bounds (handle negative tile positions)
        src_x_start = dest_x_start - tile_x
        src_y_start = dest_y_start - tile_y
        src_x_end = src_x_start + (dest_x_end - dest_x_start)
        src_y_end = src_y_start + (dest_y_end - dest_y_start)

        # Skip if no pixels to render
        if dest_x_start >= dest_x_end or dest_y_start >= dest_y_end:
            return

        # Get the pixel indices for this region
        pixel_region = pixels[src_y_start:src_y_end, src_x_start:src_x_end]

        # Apply palette lookup to get colors for all pixels at once
        colors = palette_array[pixel_region]

        if transparent_bg:
            # Only update non-transparent pixels (index != 0)
            # Create a mask for non-zero indices
            mask = pixel_region != 0
            # Expand mask to match color channels
            mask_3d = mask[:, :, np.newaxis]
            # Apply colors only where mask is True
            canvas_region = canvas[dest_y_start:dest_y_end, dest_x_start:dest_x_end]
            canvas[dest_y_start:dest_y_end, dest_x_start:dest_x_end] = np.where(
                mask_3d, colors, canvas_region
            )
        else:
            # Update all pixels
            canvas[dest_y_start:dest_y_end, dest_x_start:dest_x_end] = colors

    def _render_tile(
        self,
        img: Image.Image,
        tile: TileData,
        palette: list[tuple[int, int, int]],
        flip_h: bool,
        flip_v: bool,
        sprite_width: int,
        sprite_height: int,
        transparent_bg: bool,
    ) -> None:
        """Render a single tile onto the image (legacy per-pixel version)."""
        # Decode tile data
        pixels = decode_4bpp_tile(tile.data_bytes)

        # Calculate tile position in sprite
        tile_x = tile.pos_x * 8
        tile_y = tile.pos_y * 8

        # Handle flipping at tile level
        if flip_h:
            tile_x = sprite_width - tile_x - 8
        if flip_v:
            tile_y = sprite_height - tile_y - 8

        # Draw pixels
        for py in range(8):
            for px in range(8):
                # Handle pixel-level flipping
                src_x = (7 - px) if flip_h else px
                src_y = (7 - py) if flip_v else py

                pixel_idx = pixels[src_y][src_x]

                # Index 0 is transparent
                if pixel_idx == 0 and transparent_bg:
                    continue

                color = palette[pixel_idx]
                dest_x = tile_x + px
                dest_y = tile_y + py

                if 0 <= dest_x < sprite_width and 0 <= dest_y < sprite_height:
                    if transparent_bg:
                        img.putpixel((dest_x, dest_y), (*color, 255))
                    else:
                        img.putpixel((dest_x, dest_y), color)

    def render_all_entries(
        self,
        output_dir: str | Path,
        prefix: str = "sprite",
        transparent_bg: bool = True,
    ) -> list[Path]:
        """
        Render all OAM entries to individual files.

        Args:
            output_dir: Directory to save images
            prefix: Filename prefix
            transparent_bg: If True, use transparent background

        Returns:
            List of paths to saved images
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        saved_files: list[Path] = []

        for entry in self.capture.entries:
            img = self.render_entry(entry, transparent_bg)

            filename = f"{prefix}_{entry.id:03d}_x{entry.x}_y{entry.y}.png"
            filepath = output_path / filename
            img.save(filepath)
            saved_files.append(filepath)

        logger.info(f"Rendered {len(saved_files)} sprites to {output_path}")
        return saved_files

    def render_composite(
        self,
        width: int = 256,
        height: int = 224,
        transparent_bg: bool = True,
    ) -> Image.Image:
        """
        Render all sprites composited at their screen positions.

        Args:
            width: Canvas width (SNES screen width = 256)
            height: Canvas height (SNES screen height = 224)
            transparent_bg: If True, use transparent background

        Returns:
            PIL Image with all sprites at screen positions
        """
        if transparent_bg:
            canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        else:
            canvas = Image.new("RGB", (width, height), (0, 0, 0))

        # Sort by priority (lower priority drawn first = behind)
        sorted_entries = sorted(self.capture.entries, key=lambda e: e.priority)

        for entry in sorted_entries:
            sprite_img = self.render_entry(entry, transparent_bg=True)

            # Handle negative positions (sprite partially off-screen left/top)
            paste_x = entry.x
            paste_y = entry.y

            if paste_x < 0 or paste_y < 0:
                # Crop sprite for negative positions
                crop_x = max(0, -paste_x)
                crop_y = max(0, -paste_y)

                # Skip if sprite is entirely off-screen (crop would be invalid)
                if crop_x >= sprite_img.width or crop_y >= sprite_img.height:
                    continue

                sprite_img = sprite_img.crop(
                    (crop_x, crop_y, sprite_img.width, sprite_img.height)
                )
                paste_x = max(0, paste_x)
                paste_y = max(0, paste_y)

            # Paste with alpha compositing
            if paste_x < width and paste_y < height:
                canvas.paste(sprite_img, (paste_x, paste_y), sprite_img)

        return canvas

    def render_selection(
        self,
        transparent_bg: bool = True,
    ) -> Image.Image:
        """
        Render all sprites in the capture composited relative to their bounding box.

        Args:
            transparent_bg: If True, use transparent background (RGBA)

        Returns:
            PIL Image with all sprites composited relative to their bounding box
        """
        bbox = self.capture.bounding_box
        if bbox.width <= 0 or bbox.height <= 0:
            return Image.new("RGBA", (8, 8), (0, 0, 0, 0))

        if transparent_bg:
            canvas = Image.new("RGBA", (bbox.width, bbox.height), (0, 0, 0, 0))
        else:
            canvas = Image.new("RGB", (bbox.width, bbox.height), (0, 0, 0))

        # Sort by priority (lower priority drawn first = behind)
        sorted_entries = sorted(self.capture.entries, key=lambda e: e.priority)

        for entry in sorted_entries:
            sprite_img = self.render_entry(entry, transparent_bg=True)

            # Position relative to bbox origin
            paste_x = entry.x - bbox.x
            paste_y = entry.y - bbox.y

            # Since bbox is calculated from these entries, paste_x/y should be >= 0
            # and within canvas bounds.
            canvas.paste(sprite_img, (paste_x, paste_y), sprite_img)

        return canvas


def render_capture_to_files(
    json_path: str | Path,
    output_dir: str | Path,
    render_composite: bool = True,
    render_individual: bool = True,
) -> dict[str, Path | list[Path]]:
    """
    Convenience function to render a capture file to images.

    Args:
        json_path: Path to capture JSON file
        output_dir: Directory to save output
        render_composite: If True, render composite image
        render_individual: If True, render individual sprites

    Returns:
        Dict with 'composite' and 'sprites' paths
    """
    from core.mesen_integration.click_extractor import MesenCaptureParser

    parser = MesenCaptureParser()
    capture = parser.parse_file(json_path)

    renderer = CaptureRenderer(capture)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result: dict[str, Path | list[Path]] = {}

    if render_composite:
        composite = renderer.render_composite()
        composite_path = output_path / "composite.png"
        composite.save(composite_path)
        result["composite"] = composite_path
        logger.info(f"Saved composite to {composite_path}")

    if render_individual:
        sprite_files = renderer.render_all_entries(output_path / "sprites")
        result["sprites"] = sprite_files

    return result
