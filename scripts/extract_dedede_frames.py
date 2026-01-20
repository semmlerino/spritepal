#!/usr/bin/env python3
"""
Extract Dedede (palette 7) sprites from Mesen dumps for frame mapping.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

SIZE_TABLE = {
    0: (8, 8, 16, 16),
    1: (8, 8, 32, 32),
    2: (8, 8, 64, 64),
    3: (16, 16, 32, 32),
    4: (16, 16, 64, 64),
    5: (32, 32, 64, 64),
    6: (16, 32, 32, 64),
    7: (16, 32, 32, 32),
}


def parse_oam(oam_data: bytes, obsel: int) -> list[dict]:
    """Parse OAM dump into entries."""
    entries = []
    size_select = (obsel >> 5) & 0x07
    sizes = SIZE_TABLE.get(size_select, (8, 8, 16, 16))

    for i in range(128):
        base = i * 4
        x_low = oam_data[base]
        y = oam_data[base + 1]
        tile = oam_data[base + 2]
        attr = oam_data[base + 3]

        hi_byte_idx = 0x200 + (i // 4)
        hi_byte = oam_data[hi_byte_idx] if hi_byte_idx < len(oam_data) else 0
        hi_bit_pos = (i % 4) * 2
        x_bit9 = (hi_byte >> hi_bit_pos) & 1
        size_bit = (hi_byte >> (hi_bit_pos + 1)) & 1

        x = x_low + (x_bit9 * 256)
        if x >= 256:
            x -= 512

        palette = (attr >> 1) & 0x07
        flip_h = bool(attr & 0x40)
        flip_v = bool(attr & 0x80)
        size_large = bool(size_bit)

        width = sizes[2] if size_large else sizes[0]
        height = sizes[3] if size_large else sizes[1]

        entries.append({
            "id": i, "x": x, "y": y, "tile": tile,
            "palette": palette, "flip_h": flip_h, "flip_v": flip_v,
            "width": width, "height": height,
        })
    return entries


def parse_cgram(cgram_data: bytes) -> list[list[tuple[int, int, int]]]:
    """Parse CGRAM into 8 sprite palettes."""
    palettes = []
    for pal_idx in range(8):
        colors = []
        for col_idx in range(16):
            offset = 0x100 + (pal_idx * 32) + (col_idx * 2)
            if offset + 1 < len(cgram_data):
                bgr555 = cgram_data[offset] | (cgram_data[offset + 1] << 8)
                r = (bgr555 & 0x1F) << 3
                g = ((bgr555 >> 5) & 0x1F) << 3
                b = ((bgr555 >> 10) & 0x1F) << 3
                colors.append((r, g, b))
            else:
                colors.append((0, 0, 0))
        palettes.append(colors)
    return palettes


def render_tile_4bpp(vram: bytes, addr: int, palette: list, flip_h: bool, flip_v: bool) -> Image.Image:
    """Render a single 8x8 4bpp tile."""
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for row in range(8):
        y = 7 - row if flip_v else row
        bp_offset = addr + (row * 2)
        bp01_lo = vram[bp_offset] if bp_offset < len(vram) else 0
        bp01_hi = vram[bp_offset + 1] if bp_offset + 1 < len(vram) else 0
        bp23_lo = vram[bp_offset + 16] if bp_offset + 16 < len(vram) else 0
        bp23_hi = vram[bp_offset + 17] if bp_offset + 17 < len(vram) else 0

        for col in range(8):
            x = 7 - col if flip_h else col
            bit = 7 - col
            pixel = (((bp01_lo >> bit) & 1) |
                     (((bp01_hi >> bit) & 1) << 1) |
                     (((bp23_lo >> bit) & 1) << 2) |
                     (((bp23_hi >> bit) & 1) << 3))
            if pixel != 0:
                color = palette[pixel] if pixel < len(palette) else (255, 0, 255)
                img.putpixel((x, y), (*color, 255))
    return img


def render_sprite(entry: dict, vram: bytes, palette: list, name_base: int) -> Image.Image:
    """Render a single OAM sprite."""
    w, h = entry["width"], entry["height"]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tile_base = name_base * 0x2000

    tiles_x, tiles_y = w // 8, h // 8
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            tile_num = entry["tile"] + tx + (ty * 16)
            tile_addr = tile_base + (tile_num * 32)
            tile_img = render_tile_4bpp(vram, tile_addr, palette, entry["flip_h"], entry["flip_v"])
            px = (tiles_x - 1 - tx) * 8 if entry["flip_h"] else tx * 8
            py = (tiles_y - 1 - ty) * 8 if entry["flip_v"] else ty * 8
            img.paste(tile_img, (px, py), tile_img)
    return img


def extract_character(dump_dir: Path, target_palette: int, obsel: int = 0x63) -> Image.Image | None:
    """Extract sprites of a specific palette from dumps."""
    oam_files = list(dump_dir.glob("*OAM*.dmp"))
    vram_files = list(dump_dir.glob("*VRAM*.dmp"))
    cgram_files = list(dump_dir.glob("*CGRAM*.dmp"))

    if not (oam_files and vram_files and cgram_files):
        return None

    oam_data = oam_files[0].read_bytes()
    vram_data = vram_files[0].read_bytes()
    cgram_data = cgram_files[0].read_bytes()

    name_base = obsel & 0x07
    entries = parse_oam(oam_data, obsel)
    palettes = parse_cgram(cgram_data)

    # Filter to target palette and visible
    visible = [e for e in entries
               if e["palette"] == target_palette
               and e["y"] < 224 and e["y"] != 240
               and -64 < e["x"] < 300]

    if not visible:
        return None

    # Calculate bounding box
    min_x = min(e["x"] for e in visible)
    min_y = min(e["y"] for e in visible)
    max_x = max(e["x"] + e["width"] for e in visible)
    max_y = max(e["y"] + e["height"] for e in visible)

    canvas = Image.new("RGBA", (max_x - min_x, max_y - min_y), (0, 0, 0, 0))

    for entry in reversed(visible):
        sprite_img = render_sprite(entry, vram_data, palettes[entry["palette"]], name_base)
        canvas.paste(sprite_img, (entry["x"] - min_x, entry["y"] - min_y), sprite_img)

    return canvas


def main():
    parser = argparse.ArgumentParser(description="Extract character sprites by palette")
    parser.add_argument("input_dir", help="Directory with dump subdirectories or single dump dir")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("--palette", type=int, default=7, help="Target palette (default: 7 for Dedede)")
    parser.add_argument("--obsel", type=lambda x: int(x, 0), default=0x63, help="OBSEL value")
    args = parser.parse_args()

    input_path = Path(args.input_dir)
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Check if input is a single dump dir or contains subdirs
    if list(input_path.glob("*OAM*.dmp")):
        # Single dump directory
        dirs = [input_path]
    else:
        # Contains subdirectories
        dirs = [d for d in input_path.iterdir() if d.is_dir() and list(d.glob("*OAM*.dmp"))]

    print(f"Processing {len(dirs)} dump directories for palette {args.palette}")

    for dump_dir in sorted(dirs):
        frame_name = dump_dir.name
        img = extract_character(dump_dir, args.palette, args.obsel)
        if img:
            out_file = output_path / f"{frame_name}_pal{args.palette}.png"
            img.save(out_file)
            print(f"  {frame_name}: {img.width}x{img.height}")
        else:
            print(f"  {frame_name}: no sprites with palette {args.palette}")


if __name__ == "__main__":
    main()
