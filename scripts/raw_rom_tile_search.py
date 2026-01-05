#!/usr/bin/env python3
"""
Raw ROM tile search: Direct memmem search for VRAM tile bytes in ROM.

This bypasses HAL decompression entirely. If tiles are found:
  → DB build is the problem (alignment/format/filters)
If tiles are NOT found:
  → Tiles are assembled/generated at runtime
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def search_bytes_in_file(data: bytes, needle: bytes) -> list[int]:
    """Find all occurrences of needle in data, return offsets."""
    offsets = []
    start = 0
    while True:
        pos = data.find(needle, start)
        if pos == -1:
            break
        offsets.append(pos)
        start = pos + 1
    return offsets


def main() -> int:
    parser = argparse.ArgumentParser(description="Raw ROM tile search")
    parser.add_argument("--rom", type=Path, required=True, help="ROM file")
    parser.add_argument("--capture", type=Path, required=True, help="Capture JSON")
    parser.add_argument("--max-tiles", type=int, default=10, help="Max tiles to search")

    args = parser.parse_args()

    if not args.rom.exists():
        print(f"Error: ROM not found: {args.rom}", file=sys.stderr)
        return 1

    # Load ROM
    rom_data = args.rom.read_bytes()
    print(f"ROM size: {len(rom_data):,} bytes ({len(rom_data) / 1024 / 1024:.1f} MB)")

    # Load capture
    with open(args.capture) as f:
        capture = json.load(f)

    frame = capture.get("frame", 0)
    print(f"Capture frame: {frame}")
    print()

    # Extract non-empty tiles
    tiles_to_search: list[tuple[int, int, str]] = []  # (sprite_id, tile_idx, hex)

    for entry in capture.get("entries", []):
        sprite_id = entry.get("id", 0)
        for tile in entry.get("tiles", []):
            tile_hex = tile.get("data_hex", "")
            tile_idx = tile.get("tile_index", 0)

            if len(tile_hex) != 64:
                continue

            # Skip all-zero tiles
            if tile_hex == "00" * 32:
                continue

            tiles_to_search.append((sprite_id, tile_idx, tile_hex))

    print(f"Non-empty tiles in capture: {len(tiles_to_search)}")
    print(f"Searching first {min(args.max_tiles, len(tiles_to_search))} tiles...")
    print()

    found_count = 0
    not_found_count = 0

    for sprite_id, tile_idx, tile_hex in tiles_to_search[: args.max_tiles]:
        tile_bytes = bytes.fromhex(tile_hex)

        # Search in ROM
        offsets = search_bytes_in_file(rom_data, tile_bytes)

        if offsets:
            found_count += 1
            print(f"FOUND: Sprite {sprite_id} tile {tile_idx}")
            print(f"  Data: {tile_hex[:32]}...")
            print(f"  ROM offsets: {', '.join(f'0x{o:06X}' for o in offsets[:5])}")
            if len(offsets) > 5:
                print(f"  ... and {len(offsets) - 5} more")
        else:
            not_found_count += 1
            print(f"NOT FOUND: Sprite {sprite_id} tile {tile_idx}")
            print(f"  Data: {tile_hex[:32]}...")

    print()
    print("=" * 60)
    print(f"RESULTS: {found_count} found, {not_found_count} not found")
    print("=" * 60)

    if found_count > 0 and not_found_count == 0:
        print("CONCLUSION: All tiles exist verbatim in ROM!")
        print("  → DB build is the problem (alignment/format/filters)")
    elif found_count == 0:
        print("CONCLUSION: No tiles exist verbatim in ROM!")
        print("  → Tiles are assembled/generated at runtime")
    else:
        print("CONCLUSION: Mixed results - some tiles verbatim, some generated")
        print(f"  → {found_count}/{found_count + not_found_count} tiles exist in ROM")

    return 0


if __name__ == "__main__":
    sys.exit(main())
