"""
Renderer for Mesen 2 sprite captures.

Takes parsed capture data and renders sprites using the captured tile data
and palettes from VRAM/CGRAM.
"""

from __future__ import annotations

from pathlib import Path

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
        """Convert SNES palettes to RGB."""
        for pal_idx, colors in self.capture.palettes.items():
            rgb_colors = [snes_color_to_rgb(c) for c in colors]
            self._rgb_palettes[pal_idx] = rgb_colors

    def render_entry(
        self,
        entry: OAMEntry,
        transparent_bg: bool = True,
    ) -> Image.Image:
        """
        Render a single OAM entry to an image.

        Args:
            entry: OAM entry to render
            transparent_bg: If True, use transparent background (RGBA)

        Returns:
            PIL Image of the sprite
        """
        width = entry.width
        height = entry.height

        if transparent_bg:
            img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        else:
            img = Image.new("RGB", (width, height), (0, 0, 0))

        # Get palette for this sprite
        palette = self._rgb_palettes.get(entry.palette)
        if palette is None:
            logger.warning(f"Palette {entry.palette} not found, using grayscale")
            palette = [(i * 17, i * 17, i * 17) for i in range(16)]

        # Render each tile
        for tile in entry.tiles:
            self._render_tile(
                img,
                tile,
                palette,
                entry.flip_h,
                entry.flip_v,
                entry.width,
                entry.height,
                transparent_bg,
            )

        return img

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
        """Render a single tile onto the image."""
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
                        img.putpixel((dest_x, dest_y), color + (255,))
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
                sprite_img = sprite_img.crop(
                    (crop_x, crop_y, sprite_img.width, sprite_img.height)
                )
                paste_x = max(0, paste_x)
                paste_y = max(0, paste_y)

            # Paste with alpha compositing
            if paste_x < width and paste_y < height:
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
