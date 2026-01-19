#!/usr/bin/env python3
"""
Reconstruct SNES sprite frame directly from Mesen memory dumps.

This bypasses the Lua capture entirely to test reconstruction logic.

Usage:
    python reconstruct_from_dumps.py /path/to/DededeDMP --output frame.png
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

SNES_WIDTH = 256
SNES_HEIGHT = 224

# SNES sprite size table: OBSEL size_select -> (small_w, small_h, large_w, large_h)
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


@dataclass
class OAMEntry:
    """Parsed OAM entry."""
    id: int
    x: int
    y: int
    tile: int
    name_table: int  # bit 0 of attr - second tile table select
    palette: int     # bits 1-3 of attr
    priority: int    # bits 4-5 of attr
    flip_h: bool
    flip_v: bool
    size_large: bool
    width: int = 0
    height: int = 0


def parse_oam_dump(oam_data: bytes, obsel: int) -> list[OAMEntry]:
    """Parse OAM dump into entries."""
    entries = []
    size_select = (obsel >> 5) & 0x07
    sizes = SIZE_TABLE.get(size_select, (8, 8, 16, 16))

    for i in range(128):
        # Main table: 4 bytes per entry
        base = i * 4
        x_low = oam_data[base]
        y = oam_data[base + 1]
        tile = oam_data[base + 2]
        attr = oam_data[base + 3]

        # High table: 2 bits per entry at offset 0x200 (512)
        hi_byte_idx = 0x200 + (i // 4)
        hi_byte = oam_data[hi_byte_idx] if hi_byte_idx < len(oam_data) else 0
        hi_bit_pos = (i % 4) * 2
        x_bit9 = (hi_byte >> hi_bit_pos) & 1
        size_bit = (hi_byte >> (hi_bit_pos + 1)) & 1

        # Full X (signed 9-bit)
        x = x_low + (x_bit9 * 256)
        if x >= 256:
            x -= 512

        # Parse attributes
        name_table = attr & 0x01
        palette = (attr >> 1) & 0x07
        priority = (attr >> 4) & 0x03
        flip_h = bool((attr >> 6) & 1)
        flip_v = bool((attr >> 7) & 1)
        size_large = size_bit == 1

        width, height = sizes[2:4] if size_large else sizes[0:2]

        entries.append(OAMEntry(
            id=i, x=x, y=y, tile=tile,
            name_table=name_table, palette=palette, priority=priority,
            flip_h=flip_h, flip_v=flip_v, size_large=size_large,
            width=width, height=height
        ))

    return entries


def parse_cgram_dump(cgram_data: bytes) -> dict[int, list[tuple[int, int, int]]]:
    """Parse CGRAM dump into sprite palettes (palettes 0-7 at $100-$1FF)."""
    palettes = {}

    for pal_idx in range(8):
        colors = []
        for col in range(16):
            addr = 0x100 + (pal_idx * 32) + (col * 2)
            if addr + 1 < len(cgram_data):
                lo = cgram_data[addr]
                hi = cgram_data[addr + 1]
                bgr555 = lo | (hi << 8)

                # BGR555 to RGB888 (bit replication: shift left 3)
                r = (bgr555 & 0x1F) << 3
                g = ((bgr555 >> 5) & 0x1F) << 3
                b = ((bgr555 >> 10) & 0x1F) << 3
                colors.append((r, g, b))
            else:
                colors.append((0, 0, 0))
        palettes[pal_idx] = colors

    return palettes


def decode_4bpp_tile(tile_data: bytes) -> list[list[int]]:
    """Decode 32-byte 4bpp planar tile to 8x8 pixel indices."""
    pixels = [[0] * 8 for _ in range(8)]

    for row in range(8):
        # Bitplanes 0,1 in first 16 bytes (2 bytes per row)
        bp0 = tile_data[row * 2]
        bp1 = tile_data[row * 2 + 1]
        # Bitplanes 2,3 in second 16 bytes
        bp2 = tile_data[16 + row * 2]
        bp3 = tile_data[16 + row * 2 + 1]

        for col in range(8):
            bit = 7 - col
            pixel = ((bp0 >> bit) & 1) | \
                    (((bp1 >> bit) & 1) << 1) | \
                    (((bp2 >> bit) & 1) << 2) | \
                    (((bp3 >> bit) & 1) << 3)
            pixels[row][col] = pixel

    return pixels


def get_tile_vram_addr(tile_idx: int, use_second_table: bool, obsel: int) -> int:
    """Calculate VRAM byte address for a tile index."""
    name_base = obsel & 0x07
    name_sel = (obsel >> 3) & 0x03

    oam_base_addr = name_base << 13  # word address
    oam_addr_offset = (name_sel + 1) << 12  # word address

    word_addr = oam_base_addr + (tile_idx << 4)
    if use_second_table:
        word_addr += oam_addr_offset
    word_addr &= 0x7FFF

    return word_addr << 1  # byte address


def render_sprite(entry: OAMEntry, vram: bytes, palettes: dict, obsel: int) -> Image.Image:
    """Render a single sprite to an RGBA image."""
    img = Image.new("RGBA", (entry.width, entry.height), (0, 0, 0, 0))

    tiles_x = entry.width // 8
    tiles_y = entry.height // 8
    palette = palettes.get(entry.palette, [(0, 0, 0)] * 16)

    # Base tile split into nibbles (SNES OBJ tile addressing)
    base_x = entry.tile & 0x0F
    base_y = (entry.tile >> 4) & 0x0F

    for ty in range(tiles_y):
        for tx in range(tiles_x):
            # SNES nibble wrapping (no carry between nibbles)
            tile_x = (base_x + tx) & 0x0F
            tile_y = (base_y + ty) & 0x0F
            tile_idx = (tile_y << 4) | tile_x

            vram_addr = get_tile_vram_addr(tile_idx, entry.name_table == 1, obsel)

            if vram_addr + 32 <= len(vram):
                tile_data = vram[vram_addr:vram_addr + 32]
                pixels = decode_4bpp_tile(tile_data)

                # Determine position with flip handling
                if entry.flip_h:
                    draw_x = entry.width - 8 - (tx * 8)
                else:
                    draw_x = tx * 8

                if entry.flip_v:
                    draw_y = entry.height - 8 - (ty * 8)
                else:
                    draw_y = ty * 8

                # Draw pixels
                for py in range(8):
                    for px in range(8):
                        # Apply per-pixel flip
                        src_px = (7 - px) if entry.flip_h else px
                        src_py = (7 - py) if entry.flip_v else py

                        color_idx = pixels[src_py][src_px]
                        if color_idx == 0:  # Transparent
                            continue

                        r, g, b = palette[color_idx]
                        img.putpixel((draw_x + px, draw_y + py), (r, g, b, 255))

    return img


def is_visible(entry: OAMEntry) -> bool:
    """Check if sprite is potentially visible."""
    # Y in overscan zone means off-screen
    if entry.y >= 224 and entry.y < 240:
        return False
    # X completely off left
    if entry.x <= -64:
        return False
    # X completely off right
    if entry.x >= 256:
        return False
    return True


def reconstruct_frame(
    oam_entries: list[OAMEntry],
    vram: bytes,
    palettes: dict,
    obsel: int,
    show_bounds: bool = False,
) -> Image.Image:
    """Reconstruct full frame from OAM, VRAM, and palettes."""
    canvas = Image.new("RGBA", (SNES_WIDTH, SNES_HEIGHT), (48, 48, 48, 255))

    # SNES: lower OAM index is on top -> draw high IDs first
    sorted_entries = sorted(oam_entries, key=lambda e: e.id, reverse=True)

    drawn = 0
    for entry in sorted_entries:
        if not is_visible(entry):
            continue

        sprite_img = render_sprite(entry, vram, palettes, obsel)

        x = entry.x
        y = entry.y & 0xFF  # OAM Y is 8-bit

        # Skip if entirely in non-visible area and doesn't wrap
        if y >= SNES_HEIGHT and (y + entry.height) <= 256:
            continue

        # Render positions (handle Y wrap at 256)
        positions = [(x, y)]
        if (y + entry.height) > 256:
            positions.append((x, y - 256))

        for px, py in positions:
            canvas.paste(sprite_img, (px, py), sprite_img)
            drawn += 1

            if show_bounds:
                from PIL import ImageDraw
                draw = ImageDraw.Draw(canvas)
                draw.rectangle(
                    [px, py, px + entry.width - 1, py + entry.height - 1],
                    outline=(255, 0, 255, 128),
                )

    print(f"Drew {drawn} sprite instances")
    return canvas


def main():
    parser = argparse.ArgumentParser(description="Reconstruct frame from Mesen dumps")
    parser.add_argument("dump_dir", help="Directory containing *_OAM.dmp, *_VRAM.dmp, *_CGRAM.dmp")
    parser.add_argument("--output", "-o", default="reconstructed_frame.png", help="Output PNG path")
    parser.add_argument("--obsel", type=lambda x: int(x, 0), default=0x62,
                        help="OBSEL value (default 0x62 = size_select=3, 16x16/32x32)")
    parser.add_argument("--bounds", action="store_true", help="Draw sprite bounds")

    args = parser.parse_args()
    dump_dir = Path(args.dump_dir)

    # Find dump files
    oam_file = list(dump_dir.glob("*OAM*.dmp")) or list(dump_dir.glob("*oam*.dmp"))
    vram_file = list(dump_dir.glob("*VRAM*.dmp")) or list(dump_dir.glob("*vram*.dmp"))
    cgram_file = list(dump_dir.glob("*CGRAM*.dmp")) or list(dump_dir.glob("*cgram*.dmp"))

    if not oam_file:
        print(f"ERROR: No OAM dump found in {dump_dir}")
        return 1
    if not vram_file:
        print(f"ERROR: No VRAM dump found in {dump_dir}")
        return 1
    if not cgram_file:
        print(f"ERROR: No CGRAM dump found in {dump_dir}")
        return 1

    oam_path = oam_file[0]
    vram_path = vram_file[0]
    cgram_path = cgram_file[0]

    print(f"OAM:   {oam_path.name} ({oam_path.stat().st_size} bytes)")
    print(f"VRAM:  {vram_path.name} ({vram_path.stat().st_size} bytes)")
    print(f"CGRAM: {cgram_path.name} ({cgram_path.stat().st_size} bytes)")
    print(f"OBSEL: 0x{args.obsel:02X} (size_select={(args.obsel >> 5) & 7})")

    # Load dumps
    oam_data = oam_path.read_bytes()
    vram_data = vram_path.read_bytes()
    cgram_data = cgram_path.read_bytes()

    # Parse
    entries = parse_oam_dump(oam_data, args.obsel)
    palettes = parse_cgram_dump(cgram_data)

    visible = [e for e in entries if is_visible(e)]
    print(f"Parsed {len(entries)} OAM entries, {len(visible)} potentially visible")

    # Show first few visible entries
    print("\nFirst 10 visible entries:")
    for e in visible[:10]:
        print(f"  #{e.id}: ({e.x}, {e.y}) tile=0x{e.tile:02X} pal={e.palette} "
              f"size={e.width}x{e.height} flip={e.flip_h},{e.flip_v}")

    # Reconstruct
    frame = reconstruct_frame(entries, vram_data, palettes, args.obsel, args.bounds)

    # Save
    output_path = Path(args.output)
    frame.save(output_path)
    print(f"\nSaved: {output_path}")

    return 0


if __name__ == "__main__":
    exit(main())
