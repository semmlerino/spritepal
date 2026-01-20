#!/usr/bin/env python3
"""
Trace VRAM sprites back to ROM addresses using tile matching.

Usage:
    python trace_sprites_to_rom.py dump_dir/ rom_file.sfc --obsel 0x63 --palette 7
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from core.mesen_integration.rom_tile_matcher import ROMTileMatcher

# SNES sprite size table
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
    """Parse OAM dump."""
    entries = []
    size_select = (obsel >> 5) & 0x07
    sizes = SIZE_TABLE.get(size_select, (16, 16, 32, 32))

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

        name_table = attr & 0x01
        palette = (attr >> 1) & 0x07
        size_large = bool(size_bit)
        width = sizes[2] if size_large else sizes[0]
        height = sizes[3] if size_large else sizes[1]

        if y < 224 and y != 240 and -64 < x < 280:
            entries.append({
                "id": i, "x": x, "y": y, "tile": tile,
                "name_table": name_table, "palette": palette,
                "width": width, "height": height,
            })
    return entries


def get_tile_vram_addr(tile_idx: int, use_second_table: bool, obsel: int) -> int:
    """Calculate VRAM byte address for a tile."""
    name_base = obsel & 0x07
    name_sel = (obsel >> 3) & 0x03

    oam_base_addr = name_base << 13
    oam_addr_offset = (name_sel + 1) << 12

    word_addr = oam_base_addr + (tile_idx << 4)
    if use_second_table:
        word_addr += oam_addr_offset
    word_addr &= 0x7FFF

    return word_addr << 1


def extract_sprite_tiles(entry: dict, vram_data: bytes, obsel: int) -> list[tuple[int, bytes]]:
    """Extract all 8x8 tiles for a sprite entry. Returns [(vram_addr, tile_data), ...]"""
    tiles = []
    tiles_x = entry["width"] // 8
    tiles_y = entry["height"] // 8

    base_x = entry["tile"] & 0x0F
    base_y = (entry["tile"] >> 4) & 0x0F

    for ty in range(tiles_y):
        for tx in range(tiles_x):
            tile_x = (base_x + tx) & 0x0F
            tile_y = (base_y + ty) & 0x0F
            tile_idx = (tile_y << 4) | tile_x

            vram_addr = get_tile_vram_addr(tile_idx, entry["name_table"] == 1, obsel)

            if vram_addr + 32 <= len(vram_data):
                tile_data = vram_data[vram_addr : vram_addr + 32]
                tiles.append((vram_addr, tile_data))

    return tiles


def main():
    parser = argparse.ArgumentParser(description="Trace sprites to ROM addresses")
    parser.add_argument("dump_dir", help="Directory with VRAM/OAM dumps")
    parser.add_argument("rom_file", help="ROM file to search")
    parser.add_argument("--obsel", type=lambda x: int(x, 0), default=0x63)
    parser.add_argument("--palette", type=int, help="Filter to palette")
    parser.add_argument("--db", help="Tile database path (will create if missing)")
    args = parser.parse_args()

    dump_dir = Path(args.dump_dir)
    rom_path = Path(args.rom_file)

    # Load dumps
    oam_files = list(dump_dir.glob("*OAM*.dmp"))
    vram_files = list(dump_dir.glob("*VRAM*.dmp"))

    if not oam_files or not vram_files:
        print(f"ERROR: Missing OAM or VRAM dumps in {dump_dir}")
        return 1

    oam_data = oam_files[0].read_bytes()
    vram_data = vram_files[0].read_bytes()

    # Parse OAM
    entries = parse_oam(oam_data, args.obsel)
    if args.palette is not None:
        entries = [e for e in entries if e["palette"] == args.palette]

    print(f"Found {len(entries)} sprites" + (f" with palette {args.palette}" if args.palette else ""))

    # Build or load tile matcher
    db_path = args.db or "tile_database.json"

    if Path(db_path).exists():
        print(f"Loading tile database from {db_path}")
        matcher = ROMTileMatcher.load_database(db_path, str(rom_path))
    else:
        print(f"Initializing tile matcher with {rom_path}...")
        matcher = ROMTileMatcher(str(rom_path))
        print(f"Building tile database...")
        matcher.build_database()
        matcher.save_database(db_path)
        print(f"Saved database to {db_path}")

    # Load ROM for direct search fallback
    rom_data = rom_path.read_bytes()

    # Extract and match tiles for each sprite
    rom_offsets: dict[int, set[int]] = defaultdict(set)  # sprite_id -> ROM offsets

    for entry in entries:
        tiles = extract_sprite_tiles(entry, vram_data, args.obsel)
        print(f"\nSprite #{entry['id']}: ({entry['x']}, {entry['y']}) tile=0x{entry['tile']:02X} {entry['width']}x{entry['height']}")

        for vram_addr, tile_data in tiles:
            # Skip empty tiles
            if all(b == 0 for b in tile_data):
                print(f"  VRAM 0x{vram_addr:04X} -> EMPTY (transparent)")
                continue

            # Try HAL database first
            matches = matcher.lookup_vram_tile(tile_data)
            if matches:
                for match in matches[:3]:  # Show top 3 matches
                    rom_offset = match.rom_offset + match.tile_byte_offset
                    rom_offsets[entry["id"]].add(rom_offset)
                    print(f"  VRAM 0x{vram_addr:04X} -> ROM 0x{match.rom_offset:06X} + tile {match.tile_index} ({match.description})")
            else:
                # Fallback: direct ROM search for uncompressed tiles
                pos = rom_data.find(tile_data)
                if pos != -1:
                    rom_offsets[entry["id"]].add(pos)
                    print(f"  VRAM 0x{vram_addr:04X} -> ROM 0x{pos:06X} (uncompressed)")
                else:
                    print(f"  VRAM 0x{vram_addr:04X} -> NO MATCH")

    # Summary
    print("\n" + "=" * 50)
    print("ROM OFFSET SUMMARY:")
    for sprite_id, offsets in sorted(rom_offsets.items()):
        entry = next(e for e in entries if e["id"] == sprite_id)
        # Find the most common block (sprites often share a block)
        blocks = defaultdict(int)
        for off in offsets:
            block = off & ~0xFFF  # Round to 4KB blocks
            blocks[block] += 1
        if blocks:
            main_block = max(blocks.items(), key=lambda x: x[1])[0]
            print(f"  Sprite #{sprite_id} ({entry['width']}x{entry['height']}): main block 0x{main_block:06X}, {len(offsets)} tiles")


if __name__ == "__main__":
    main()
