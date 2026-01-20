#!/usr/bin/env python3
"""Reconstruct Sprite from ROM Map - Renders sprite from mapped ROM addresses.

Takes a sprite ROM map JSON and CGRAM dump, extracts tiles from ROM,
and renders them as a composite image.

Usage:
    python reconstruct_sprite.py <rom_map.json> <rom_file> [options]

Examples:
    # Reconstruct Dedede F71 with palette from dump
    python reconstruct_sprite.py DededeDMP/dedede_f71_map.json roms/Kirby.sfc \
        --cgram DededeDMP/Dedede_F71_CGRAM.dmp --palette 7

    # Reconstruct with custom output
    python reconstruct_sprite.py DededeDMP/dedede_f71_map.json roms/Kirby.sfc \
        --cgram DededeDMP/Dedede_F71_CGRAM.dmp -o dedede_reconstructed.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image


def parse_cgram_palette(cgram_data: bytes, palette_index: int) -> list[tuple[int, int, int, int]]:
    """Extract RGB palette from CGRAM dump.

    Args:
        cgram_data: 512-byte CGRAM dump
        palette_index: Sprite palette 0-7

    Returns:
        List of 16 RGBA tuples
    """
    # Sprite palettes are in upper 256 bytes ($100-$1FF)
    # Each palette is 32 bytes (16 colors × 2 bytes)
    offset = 0x100 + (palette_index * 32)
    palette_data = cgram_data[offset : offset + 32]

    colors: list[tuple[int, int, int, int]] = []
    for i in range(0, 32, 2):
        bgr555 = palette_data[i] | (palette_data[i + 1] << 8)

        # Convert BGR555 to RGB888
        r = (bgr555 & 0x1F) << 3
        g = ((bgr555 >> 5) & 0x1F) << 3
        b = ((bgr555 >> 10) & 0x1F) << 3

        # First color is transparent
        alpha = 0 if i == 0 else 255
        colors.append((r, g, b, alpha))

    return colors


def decode_4bpp_tile(tile_data: bytes) -> list[list[int]]:
    """Decode 32-byte 4bpp SNES tile to 8x8 pixel indices.

    SNES 4bpp format: 8 rows, each row is 4 bytes
    - Bytes 0-1: Bitplanes 0-1
    - Bytes 16-17: Bitplanes 2-3
    """
    pixels: list[list[int]] = []

    for row in range(8):
        row_pixels: list[int] = []
        # Bitplanes 0-1 at offset row*2
        bp0 = tile_data[row * 2]
        bp1 = tile_data[row * 2 + 1]
        # Bitplanes 2-3 at offset 16 + row*2
        bp2 = tile_data[16 + row * 2]
        bp3 = tile_data[16 + row * 2 + 1]

        for col in range(8):
            bit = 7 - col
            pixel = (
                ((bp0 >> bit) & 1) | (((bp1 >> bit) & 1) << 1) | (((bp2 >> bit) & 1) << 2) | (((bp3 >> bit) & 1) << 3)
            )
            row_pixels.append(pixel)

        pixels.append(row_pixels)

    return pixels


def render_tile(tile_data: bytes, palette: list[tuple[int, int, int, int]]) -> Image.Image:
    """Render a single 8x8 tile as PIL Image."""
    pixels = decode_4bpp_tile(tile_data)
    img = Image.new("RGBA", (8, 8))

    for y, row in enumerate(pixels):
        for x, pixel_idx in enumerate(row):
            color = palette[pixel_idx] if pixel_idx < len(palette) else (255, 0, 255, 255)
            img.putpixel((x, y), color)

    return img


def load_oam_for_layout(oam_path: Path, palette_filter: int) -> list[dict]:
    """Load OAM and extract sprite layout info.

    Returns list of dicts with x, y, tile, h_flip, v_flip for each sprite.
    """
    oam_data = oam_path.read_bytes()
    low_table = oam_data[:512]
    high_table = oam_data[512:544]

    sprites = []
    for i in range(128):
        offset = i * 4
        x_low = low_table[offset]
        y = low_table[offset + 1]
        tile = low_table[offset + 2]
        attr = low_table[offset + 3]

        # High table
        high_byte = high_table[i // 4]
        high_bits = (high_byte >> ((i % 4) * 2)) & 0x03
        x_high = high_bits & 0x01
        size_large = bool(high_bits & 0x02)

        # Combine X
        x = x_low | (x_high << 8)
        if x >= 256:
            x -= 512

        palette = (attr >> 1) & 0x07
        h_flip = bool(attr & 0x40)
        v_flip = bool(attr & 0x80)

        # Filter by palette and visibility
        if palette == palette_filter and 0 <= y < 224 and -16 <= x < 256:
            sprites.append(
                {
                    "index": i,
                    "x": x,
                    "y": y,
                    "tile": tile,
                    "h_flip": h_flip,
                    "v_flip": v_flip,
                    "size_large": size_large,
                }
            )

    return sprites


def get_16x16_subtiles(base_tile: int) -> list[tuple[int, int, int]]:
    """Get 4 subtile positions for 16x16 sprite.

    Returns: list of (tile_idx, dx, dy) for each 8x8 subtile
    """
    return [
        (base_tile, 0, 0),
        (base_tile + 1, 8, 0),
        (base_tile + 16, 0, 8),
        (base_tile + 17, 8, 8),
    ]


def reconstruct_from_map(
    rom_map_path: Path,
    rom_path: Path,
    cgram_path: Path | None,
    oam_path: Path | None,
    palette_index: int,
    output_path: Path | None,
    scale: int = 4,
) -> Image.Image:
    """Reconstruct sprite from ROM map.

    Args:
        rom_map_path: Path to JSON ROM map
        rom_path: Path to ROM file
        cgram_path: Path to CGRAM dump (for palette)
        oam_path: Path to OAM dump (for layout)
        palette_index: Sprite palette 0-7
        output_path: Output PNG path
        scale: Output scale factor

    Returns:
        Reconstructed PIL Image
    """
    # Load ROM map
    with open(rom_map_path) as f:
        rom_map = json.load(f)

    # Load ROM
    rom_data = rom_path.read_bytes()

    # Load palette
    if cgram_path and cgram_path.exists():
        cgram_data = cgram_path.read_bytes()
        palette = parse_cgram_palette(cgram_data, palette_index)
        print(f"Loaded palette {palette_index} from {cgram_path.name}")
    else:
        # Default grayscale palette
        palette = [(i * 17, i * 17, i * 17, 255 if i > 0 else 0) for i in range(16)]
        print("Using grayscale palette (no CGRAM provided)")

    # Build VRAM word -> ROM offset lookup
    vram_to_rom: dict[int, int] = {}
    for mapping in rom_map.get("mappings", []):
        vram_word = mapping["vram_word"]
        rom_offset = mapping["rom_offset"]
        vram_to_rom[vram_word] = rom_offset

    print(f"Loaded {len(vram_to_rom)} tile mappings from {rom_map_path.name}")

    # Get layout from OAM if available
    if oam_path and oam_path.exists():
        oam_sprites = load_oam_for_layout(oam_path, palette_index)
        print(f"Found {len(oam_sprites)} sprites with palette {palette_index} in OAM")

        if not oam_sprites:
            print("Warning: No sprites found with specified palette")
            return Image.new("RGBA", (64, 64), (0, 0, 0, 0))

        # Calculate bounding box
        min_x = min(s["x"] for s in oam_sprites)
        min_y = min(s["y"] for s in oam_sprites)
        max_x = max(s["x"] + (16 if s["size_large"] else 8) for s in oam_sprites)
        max_y = max(s["y"] + (16 if s["size_large"] else 8) for s in oam_sprites)

        width = max_x - min_x
        height = max_y - min_y

        print(f"Sprite bounds: ({min_x}, {min_y}) to ({max_x}, {max_y}) = {width}x{height}")

        # Create composite image
        composite = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        # OBSEL base (0x63 = VRAM $6000)
        vram_base = rom_map.get("vram_base", 0x6000)

        tiles_rendered = 0
        for sprite in oam_sprites:
            base_tile = sprite["tile"]
            sx = sprite["x"] - min_x
            sy = sprite["y"] - min_y

            if sprite["size_large"]:
                subtiles = get_16x16_subtiles(base_tile)
            else:
                subtiles = [(base_tile, 0, 0)]

            for tile_idx, dx, dy in subtiles:
                # Calculate VRAM word address
                vram_word = vram_base + tile_idx * 16

                if vram_word not in vram_to_rom:
                    continue

                rom_offset = vram_to_rom[vram_word]
                tile_data = rom_data[rom_offset : rom_offset + 32]

                if len(tile_data) < 32:
                    continue

                tile_img = render_tile(tile_data, palette)

                # Apply flips
                if sprite["h_flip"]:
                    tile_img = tile_img.transpose(Image.FLIP_LEFT_RIGHT)
                    # Adjust dx for flipped tile
                    if sprite["size_large"]:
                        dx = 8 - dx if dx == 0 else 0
                if sprite["v_flip"]:
                    tile_img = tile_img.transpose(Image.FLIP_TOP_BOTTOM)
                    if sprite["size_large"]:
                        dy = 8 - dy if dy == 0 else 0

                # Paste tile
                paste_x = sx + dx
                paste_y = sy + dy
                composite.alpha_composite(tile_img, (paste_x, paste_y))
                tiles_rendered += 1

        print(f"Rendered {tiles_rendered} tiles")

    else:
        # No OAM - just render tiles in a grid
        print("No OAM provided - rendering tiles in grid layout")

        num_tiles = len(vram_to_rom)
        grid_cols = 8
        grid_rows = (num_tiles + grid_cols - 1) // grid_cols

        width = grid_cols * 8
        height = grid_rows * 8
        composite = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        for i, (vram_word, rom_offset) in enumerate(sorted(vram_to_rom.items())):
            tile_data = rom_data[rom_offset : rom_offset + 32]
            if len(tile_data) < 32:
                continue

            tile_img = render_tile(tile_data, palette)

            grid_x = (i % grid_cols) * 8
            grid_y = (i // grid_cols) * 8
            composite.paste(tile_img, (grid_x, grid_y))

        print(f"Rendered {num_tiles} tiles in {grid_cols}x{grid_rows} grid")

    # Scale up
    if scale > 1:
        composite = composite.resize(
            (composite.width * scale, composite.height * scale),
            Image.NEAREST,
        )

    # Save
    if output_path:
        composite.save(output_path)
        print(f"Saved to {output_path}")

    return composite


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconstruct sprite from ROM map",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("rom_map", type=Path, help="Path to ROM map JSON")
    parser.add_argument("rom", type=Path, help="Path to ROM file")
    parser.add_argument("--cgram", type=Path, help="Path to CGRAM dump for palette")
    parser.add_argument("--oam", type=Path, help="Path to OAM dump for layout")
    parser.add_argument("-p", "--palette", type=int, default=7, help="Palette index (default: 7)")
    parser.add_argument("-o", "--output", type=Path, help="Output PNG path")
    parser.add_argument("-s", "--scale", type=int, default=4, help="Scale factor (default: 4)")

    args = parser.parse_args()

    # Validate inputs
    if not args.rom_map.exists():
        print(f"Error: ROM map not found: {args.rom_map}")
        return 1
    if not args.rom.exists():
        print(f"Error: ROM not found: {args.rom}")
        return 1

    # Auto-detect CGRAM/OAM from map directory if not specified
    map_dir = args.rom_map.parent
    if not args.cgram:
        cgram_candidates = list(map_dir.glob("*CGRAM*.dmp")) + list(map_dir.glob("*cgram*.dmp"))
        if cgram_candidates:
            args.cgram = cgram_candidates[0]
    if not args.oam:
        oam_candidates = list(map_dir.glob("*OAM*.dmp")) + list(map_dir.glob("*oam*.dmp"))
        if oam_candidates:
            args.oam = oam_candidates[0]

    # Default output path
    if not args.output:
        args.output = args.rom_map.with_suffix(".png")

    # Reconstruct
    reconstruct_from_map(
        rom_map_path=args.rom_map,
        rom_path=args.rom,
        cgram_path=args.cgram,
        oam_path=args.oam,
        palette_index=args.palette,
        output_path=args.output,
        scale=args.scale,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
