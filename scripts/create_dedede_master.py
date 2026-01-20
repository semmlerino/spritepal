#!/usr/bin/env python3
"""Create master tile sheet from all Dedede sprite offsets."""

import sys

sys.path.insert(0, str(__file__).rsplit("/", 2)[0])  # Add project root
import hashlib
from pathlib import Path

from PIL import Image

from core.hal_compression import HALCompressor


def main():
    hal = HALCompressor()
    rom_path = "roms/Kirby Super Star (USA).sfc"
    output_dir = Path("output/dedede_sprites")

    palette_bgr555 = [
        0x07BF,
        0x7FFF,
        0x539F,
        0x32D8,
        0x03FF,
        0x02F7,
        0x0210,
        0x7F97,
        0x7E6C,
        0x7CC0,
        0x01FF,
        0x001F,
        0x0012,
        0x0008,
        0x18C6,
        0x0000,
    ]

    def bgr555_to_rgb(bgr):
        r5 = bgr & 0x1F
        g5 = (bgr >> 5) & 0x1F
        b5 = (bgr >> 10) & 0x1F
        return ((r5 << 3) | (r5 >> 2), (g5 << 3) | (g5 >> 2), (b5 << 3) | (b5 >> 2))

    palette_rgb = [bgr555_to_rgb(c) for c in palette_bgr555]

    all_offsets = [
        0x17060,
        0x17160,
        0x17170,
        0x172C0,
        0x17300,
        0x17310,
        0x17340,
        0x17350,
        0x17360,
        0x17370,
        0x17380,
        0x17390,
        0x173A0,
        0x173B0,
        0x173D0,
        0x173E0,
        0x173F0,
        0x17710,
        0x17730,
        0x176C0,
        0x176D0,
        0x17740,
        0x17760,
        0x17770,
        0x17780,
        0x17790,
        0x177A0,
        0x177B0,
        0x177D0,
    ]

    unique_tiles = {}
    for offset in all_offsets:
        data = hal.decompress_from_rom(rom_path, offset)
        if data:
            for i in range(0, len(data), 32):
                tile = data[i : i + 32]
                if len(tile) == 32 and any(b != 0 for b in tile):
                    h = hashlib.md5(tile).hexdigest()
                    if h not in unique_tiles:
                        unique_tiles[h] = tile

    print(f"Unique non-empty tiles: {len(unique_tiles)}")

    tiles_per_row = 32
    num_tiles = len(unique_tiles)
    rows = (num_tiles + tiles_per_row - 1) // tiles_per_row
    img = Image.new("RGBA", (tiles_per_row * 8, rows * 8), (48, 48, 48, 255))

    for tile_idx, (h, tile_data) in enumerate(unique_tiles.items()):
        tx = (tile_idx % tiles_per_row) * 8
        ty = (tile_idx // tiles_per_row) * 8

        for y in range(8):
            bp0, bp1 = tile_data[y * 2], tile_data[y * 2 + 1]
            bp2, bp3 = tile_data[16 + y * 2], tile_data[16 + y * 2 + 1]

            for x in range(8):
                bit = 7 - x
                idx = (
                    ((bp0 >> bit) & 1)
                    | (((bp1 >> bit) & 1) << 1)
                    | (((bp2 >> bit) & 1) << 2)
                    | (((bp3 >> bit) & 1) << 3)
                )

                if idx != 0:
                    r, g, b = palette_rgb[idx]
                    img.putpixel((tx + x, ty + y), (r, g, b, 255))

    master_path = output_dir / "DEDEDE_ALL_UNIQUE_TILES.png"
    img.save(master_path)
    print(f"Saved: {master_path} ({img.size[0]}x{img.size[1]})")
    print(f"  {num_tiles} tiles in {rows} rows x {tiles_per_row} columns")


if __name__ == "__main__":
    main()
