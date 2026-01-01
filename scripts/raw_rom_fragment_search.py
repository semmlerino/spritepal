#!/usr/bin/env python3
"""
Search for tile fragments in ROM to understand assembly pattern.
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
    parser = argparse.ArgumentParser(description="ROM fragment search")
    parser.add_argument("--rom", type=Path, required=True, help="ROM file")
    parser.add_argument("--capture", type=Path, required=True, help="Capture JSON")

    args = parser.parse_args()

    rom_data = args.rom.read_bytes()
    print(f"ROM size: {len(rom_data):,} bytes")

    with open(args.capture) as f:
        capture = json.load(f)

    # Get one interesting non-empty tile (Kirby's main sprite - sprite 5 tile 1)
    test_tiles = []
    for entry in capture.get("entries", []):
        for tile in entry.get("tiles", []):
            tile_hex = tile.get("data_hex", "")
            if len(tile_hex) == 64 and tile_hex != "00" * 32:
                test_tiles.append((entry.get("id"), tile.get("tile_index"), tile_hex))

    if not test_tiles:
        print("No non-empty tiles found")
        return 1

    # Take Kirby's main body tile (sprite 5, tile 1)
    sprite_id, tile_idx, tile_hex = test_tiles[5]  # Index 5 is sprite 5 tile 1
    tile_bytes = bytes.fromhex(tile_hex)

    print(f"\nAnalyzing Sprite {sprite_id} tile {tile_idx}")
    print(f"Full 32 bytes: {tile_hex}")
    print()

    # SNES 4bpp format: 32 bytes = 4 bitplanes interleaved
    # Rows 0-7: bytes 0-15 (planes 0,1 interleaved)
    # Rows 0-7: bytes 16-31 (planes 2,3 interleaved)

    print("Bitplane structure:")
    print("  Low bitplanes (bytes 0-15):", tile_hex[:32])
    print("  High bitplanes (bytes 16-31):", tile_hex[32:])
    print()

    # Search for fragments
    fragment_sizes = [16, 8, 4]
    print("Fragment search results:")

    for frag_size in fragment_sizes:
        print(f"\n{frag_size}-byte fragments:")
        for i in range(0, 32, frag_size):
            fragment = tile_bytes[i:i + frag_size]
            offsets = search_bytes_in_file(rom_data, fragment)
            status = f"FOUND at {len(offsets)} locations" if offsets else "NOT FOUND"
            print(f"  Bytes {i:2d}-{i+frag_size-1:2d}: {fragment.hex().upper():32s} → {status}")
            if offsets and len(offsets) <= 3:
                print(f"            Offsets: {', '.join(f'0x{o:06X}' for o in offsets)}")

    # Also check: are the low/high bitplane halves found separately?
    print("\n" + "=" * 60)
    print("Checking if bitplane halves exist separately:")
    low_planes = tile_bytes[:16]
    high_planes = tile_bytes[16:]

    low_offsets = search_bytes_in_file(rom_data, low_planes)
    high_offsets = search_bytes_in_file(rom_data, high_planes)

    print(f"  Low planes (0-15):  {len(low_offsets)} hits")
    print(f"  High planes (16-31): {len(high_offsets)} hits")

    # Check if they might be stored interleaved differently
    # Some games store all plane 0 bytes, then all plane 1 bytes, etc.
    print("\nChecking planar (non-interleaved) arrangement:")

    # Extract individual planes from interleaved format
    plane0 = bytes(tile_bytes[i * 2] for i in range(8))
    plane1 = bytes(tile_bytes[i * 2 + 1] for i in range(8))
    plane2 = bytes(tile_bytes[16 + i * 2] for i in range(8))
    plane3 = bytes(tile_bytes[16 + i * 2 + 1] for i in range(8))

    print(f"  Plane 0: {plane0.hex().upper()} → {len(search_bytes_in_file(rom_data, plane0))} hits")
    print(f"  Plane 1: {plane1.hex().upper()} → {len(search_bytes_in_file(rom_data, plane1))} hits")
    print(f"  Plane 2: {plane2.hex().upper()} → {len(search_bytes_in_file(rom_data, plane2))} hits")
    print(f"  Plane 3: {plane3.hex().upper()} → {len(search_bytes_in_file(rom_data, plane3))} hits")

    return 0


if __name__ == "__main__":
    sys.exit(main())
