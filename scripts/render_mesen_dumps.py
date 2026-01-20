#!/usr/bin/env python3
"""
Render Mesen memory dumps to preview images.

Usage:
    python render_mesen_dumps.py mesen2_exchange/ output_dir/ [--palette 7]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def parse_obsel(obsel_path: Path) -> dict[str, int]:
    """Parse OBSEL text file."""
    result = {"raw": 0, "name_base": 0, "name_select": 0, "size_select": 0}
    with open(obsel_path) as f:
        for line in f:
            if ":" in line:
                key, val = line.strip().split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                val = val.strip()
                if val.startswith("0x"):
                    result[key] = int(val, 16)
                elif val.isdigit():
                    result[key] = int(val)
    return result


def parse_oam(oam_data: bytes) -> list[dict[str, int]]:
    """Parse OAM data into sprite entries."""
    entries = []
    # First 512 bytes: 4 bytes per sprite (128 sprites)
    for i in range(128):
        offset = i * 4
        x = oam_data[offset]
        y = oam_data[offset + 1]
        tile = oam_data[offset + 2]
        attr = oam_data[offset + 3]

        # High table (2 bits per sprite, packed)
        high_offset = 512 + (i // 4)
        high_byte = oam_data[high_offset] if high_offset < len(oam_data) else 0
        high_bits = (high_byte >> ((i % 4) * 2)) & 0x03

        x_high = high_bits & 0x01
        size_large = (high_bits >> 1) & 0x01

        # Full X coordinate (9 bits, signed)
        full_x = x | (x_high << 8)
        if full_x >= 256:
            full_x -= 512

        entries.append(
            {
                "id": i,
                "x": full_x,
                "y": y,
                "tile": tile,
                "palette": (attr >> 1) & 0x07,
                "priority": (attr >> 4) & 0x03,
                "flip_h": bool(attr & 0x40),
                "flip_v": bool(attr & 0x80),
                "size_large": bool(size_large),
            }
        )
    return entries


def parse_cgram(cgram_data: bytes) -> list[list[tuple[int, int, int]]]:
    """Parse CGRAM into 8 sprite palettes (16 colors each)."""
    palettes = []
    # Sprite palettes start at $100 (256 bytes into CGRAM)
    sprite_offset = 0x100

    for pal_idx in range(8):
        colors = []
        for col_idx in range(16):
            offset = sprite_offset + (pal_idx * 32) + (col_idx * 2)
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


def render_tile_4bpp(
    vram_data: bytes,
    tile_addr: int,
    palette: list[tuple[int, int, int]],
    flip_h: bool = False,
    flip_v: bool = False,
) -> Image.Image:
    """Render a single 8x8 4bpp tile."""
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))

    for row in range(8):
        y = 7 - row if flip_v else row
        # 4bpp: 2 bytes per row for low planes, 2 for high planes
        bp_offset = tile_addr + (row * 2)
        bp01_lo = vram_data[bp_offset] if bp_offset < len(vram_data) else 0
        bp01_hi = vram_data[bp_offset + 1] if bp_offset + 1 < len(vram_data) else 0
        bp23_lo = vram_data[bp_offset + 16] if bp_offset + 16 < len(vram_data) else 0
        bp23_hi = vram_data[bp_offset + 17] if bp_offset + 17 < len(vram_data) else 0

        for col in range(8):
            x = 7 - col if flip_h else col
            bit = 7 - col

            pixel = 0
            pixel |= ((bp01_lo >> bit) & 1) << 0
            pixel |= ((bp01_hi >> bit) & 1) << 1
            pixel |= ((bp23_lo >> bit) & 1) << 2
            pixel |= ((bp23_hi >> bit) & 1) << 3

            if pixel != 0:  # 0 is transparent
                color = palette[pixel] if pixel < len(palette) else (255, 0, 255)
                img.putpixel((x, y), (*color, 255))

    return img


def render_sprite(
    entry: dict[str, int],
    vram_data: bytes,
    palettes: list[list[tuple[int, int, int]]],
    obsel: dict[str, int],
) -> tuple[Image.Image, int, int, int, int]:
    """Render a sprite entry, return (image, x, y, width, height)."""
    size_select = obsel.get("size_select", 0)
    name_base = obsel.get("name_base", 0)

    # Determine sprite size based on OBSEL and size bit
    size_table = [
        [(8, 8), (16, 16)],  # size_select 0
        [(8, 8), (32, 32)],  # size_select 1
        [(8, 8), (64, 64)],  # size_select 2
        [(16, 16), (32, 32)],  # size_select 3
        [(16, 16), (64, 64)],  # size_select 4
        [(32, 32), (64, 64)],  # size_select 5
        [(16, 32), (32, 64)],  # size_select 6
        [(16, 32), (32, 32)],  # size_select 7
    ]

    size_idx = 1 if entry["size_large"] else 0
    sprite_w, sprite_h = size_table[size_select][size_idx]

    palette = palettes[entry["palette"]]
    tile_base = name_base * 0x2000  # VRAM word address * 2

    img = Image.new("RGBA", (sprite_w, sprite_h), (0, 0, 0, 0))

    tiles_x = sprite_w // 8
    tiles_y = sprite_h // 8

    for ty in range(tiles_y):
        for tx in range(tiles_x):
            # Calculate tile index
            tile_num = entry["tile"]
            tile_num += tx
            tile_num += ty * 16  # SNES: rows are 16 tiles apart

            tile_addr = tile_base + (tile_num * 32)  # 32 bytes per 4bpp tile

            tile_img = render_tile_4bpp(vram_data, tile_addr, palette, entry["flip_h"], entry["flip_v"])

            # Position within sprite
            px = (tiles_x - 1 - tx) * 8 if entry["flip_h"] else tx * 8
            py = (tiles_y - 1 - ty) * 8 if entry["flip_v"] else ty * 8

            img.paste(tile_img, (px, py), tile_img)

    return img, entry["x"], entry["y"], sprite_w, sprite_h


def render_frame(
    dump_dir: Path,
    frame_id: str,
    palette_filter: int | None = None,
) -> Image.Image | None:
    """Render sprites from a frame dump, optionally filtered by palette."""
    vram_path = dump_dir / f"dump_{frame_id}_VRAM.dmp"
    cgram_path = dump_dir / f"dump_{frame_id}_CGRAM.dmp"
    oam_path = dump_dir / f"dump_{frame_id}_OAM.dmp"
    obsel_path = dump_dir / f"dump_{frame_id}_OBSEL.txt"

    if not all(p.exists() for p in [vram_path, cgram_path, oam_path, obsel_path]):
        return None

    vram_data = vram_path.read_bytes()
    cgram_data = cgram_path.read_bytes()
    oam_data = oam_path.read_bytes()
    obsel = parse_obsel(obsel_path)

    entries = parse_oam(oam_data)
    palettes = parse_cgram(cgram_data)

    # Filter to visible sprites (on-screen, not at Y=240)
    visible = [e for e in entries if e["y"] < 224 and e["y"] != 240 and -64 < e["x"] < 256]

    # Filter by palette if specified
    if palette_filter is not None:
        visible = [e for e in visible if e["palette"] == palette_filter]

    if not visible:
        return None

    # Find bounding box considering sprite sizes
    size_select = obsel.get("size_select", 0)
    size_table = [
        [(8, 8), (16, 16)],
        [(8, 8), (32, 32)],
        [(8, 8), (64, 64)],
        [(16, 16), (32, 32)],
        [(16, 16), (64, 64)],
        [(32, 32), (64, 64)],
        [(16, 32), (32, 64)],
        [(16, 32), (32, 32)],
    ]

    def get_size(e: dict[str, int]) -> tuple[int, int]:
        idx = 1 if e["size_large"] else 0
        return size_table[size_select][idx]

    min_x = min(e["x"] for e in visible)
    min_y = min(e["y"] for e in visible)
    max_x = max(e["x"] + get_size(e)[0] for e in visible)
    max_y = max(e["y"] + get_size(e)[1] for e in visible)

    # Create canvas
    canvas = Image.new("RGBA", (max_x - min_x, max_y - min_y), (0, 0, 0, 0))

    # Render sprites (reverse order for correct layering)
    for entry in reversed(visible):
        sprite_img, sx, sy, sw, sh = render_sprite(entry, vram_data, palettes, obsel)
        canvas.paste(sprite_img, (sx - min_x, sy - min_y), sprite_img)

    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Mesen dumps to images")
    parser.add_argument("input_dir", help="Directory containing dump files")
    parser.add_argument("output_dir", help="Output directory for rendered images")
    parser.add_argument("--palette", type=int, help="Filter to specific palette index (0-7)")

    args = parser.parse_args()

    input_path = Path(args.input_dir)
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Find all frame dumps
    frame_ids = set()
    for f in input_path.glob("dump_F*_OBSEL.txt"):
        frame_id = f.stem.replace("dump_", "").replace("_OBSEL", "")
        frame_ids.add(frame_id)

    print(f"Found {len(frame_ids)} frame dumps")
    if args.palette is not None:
        print(f"Filtering to palette {args.palette}")

    for frame_id in sorted(frame_ids):
        print(f"Rendering {frame_id}...")
        img = render_frame(input_path, frame_id, args.palette)
        if img:
            suffix = f"_pal{args.palette}" if args.palette is not None else ""
            out_file = output_path / f"{frame_id}{suffix}.png"
            img.save(out_file)
            print(f"  Saved: {out_file} ({img.width}x{img.height})")
        else:
            print("  No visible sprites" + (f" with palette {args.palette}" if args.palette else ""))


if __name__ == "__main__":
    main()
