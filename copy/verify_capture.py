#!/usr/bin/env python3
"""
Quick verification: decode a single tile from capture and show it.
Useful for comparing against Mesen's VRAM viewer.

Usage:
    python verify_capture.py capture.json [--entry N] [--tile N]
"""

import argparse
import json
from pathlib import Path


def decode_4bpp_tile_to_text(data: bytes) -> str:
    """Decode 4bpp tile to ASCII art for visual comparison."""
    if len(data) < 32:
        data = data + b"\x00" * (32 - len(data))

    chars = " .:-=+*#@"  # 9 levels for 0-15 mapped to indices 0-8
    lines = []

    for y in range(8):
        bp0 = data[y * 2]
        bp1 = data[y * 2 + 1]
        bp2 = data[16 + y * 2]
        bp3 = data[16 + y * 2 + 1]

        row = ""
        for x in range(8):
            bit = 7 - x
            idx = ((bp0 >> bit) & 1) | (((bp1 >> bit) & 1) << 1) | (((bp2 >> bit) & 1) << 2) | (((bp3 >> bit) & 1) << 3)
            char_idx = min(idx // 2, len(chars) - 1)
            row += chars[char_idx] * 2
        lines.append(row)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Verify captured tile data")
    parser.add_argument("capture", help="Path to capture JSON file")
    parser.add_argument("--entry", "-e", type=int, default=0, help="OAM entry index (default: 0)")
    parser.add_argument("--tile", "-t", type=int, default=0, help="Tile index within entry (default: 0)")

    args = parser.parse_args()

    capture_path = Path(args.capture)
    data = json.loads(capture_path.read_text(encoding="utf-8"))

    entries = data.get("entries", [])
    if not entries:
        print("No entries in capture")
        return 1

    if args.entry >= len(entries):
        print(f"Entry {args.entry} out of range (max: {len(entries) - 1})")
        return 1

    entry = entries[args.entry]
    tiles = entry.get("tiles", [])

    if args.tile >= len(tiles):
        print(f"Tile {args.tile} out of range (max: {len(tiles) - 1})")
        return 1

    tile = tiles[args.tile]

    print("=" * 60)
    print("CAPTURE VERIFICATION")
    print("=" * 60)
    print(f"File: {capture_path.name}")
    print(f"Frame: {data.get('frame', '?')}")
    print()

    obsel = data.get("obsel", {})
    print(f"OBSEL: raw=0x{obsel.get('raw', 0):02X}")
    print(f"  name_base={obsel.get('name_base', 0)}, name_select={obsel.get('name_select', 0)}")
    print(f"  size_select={obsel.get('size_select', 0)}")
    print(f"  tile_base_addr=0x{obsel.get('tile_base_addr', 0):04X}")
    print()

    print(f"Entry {args.entry}:")
    print(f"  OAM ID: {entry.get('id', '?')}")
    print(f"  Position: ({entry.get('x', '?')}, {entry.get('y', '?')})")
    print(f"  Size: {entry.get('width', '?')}x{entry.get('height', '?')}")
    print(f"  Base tile: 0x{entry.get('tile', 0):02X} (decimal: {entry.get('tile', 0)})")
    print(f"  Name table: {entry.get('name_table', 0)}")
    print(f"  Palette: {entry.get('palette', '?')}")
    print(f"  Flips: H={entry.get('flip_h', False)}, V={entry.get('flip_v', False)}")
    print()

    print(f"Tile {args.tile}:")
    print(f"  tile_index: 0x{tile.get('tile_index', 0):02X} (decimal: {tile.get('tile_index', 0)})")
    print(f"  vram_addr: 0x{tile.get('vram_addr', 0):04X} (decimal: {tile.get('vram_addr', 0)})")
    print(f"  pos_x: {tile.get('pos_x', 0)}, pos_y: {tile.get('pos_y', 0)}")
    print()

    data_hex = tile.get("data_hex", "")
    print(f"  data_hex ({len(data_hex)} chars = {len(data_hex) // 2} bytes):")

    # Format hex in 16-byte rows for easy comparison with Mesen
    for i in range(0, len(data_hex), 32):
        chunk = data_hex[i : i + 32]
        spaced = " ".join(chunk[j : j + 2] for j in range(0, len(chunk), 2))
        print(f"    {spaced}")

    if data_hex and len(data_hex) == 64:
        print()
        print("  Visual (ASCII art):")
        tile_bytes = bytes.fromhex(data_hex)
        for line in decode_4bpp_tile_to_text(tile_bytes).split("\n"):
            print(f"    {line}")

    print()
    print("=" * 60)
    print("VERIFICATION STEPS:")
    print("=" * 60)
    print(f"1. In Mesen 2, open Debug → VRAM Viewer")
    print(f"2. Navigate to byte address 0x{tile.get('vram_addr', 0):04X}")
    print(f"3. Compare the 32 bytes shown with data_hex above")
    print(f"4. If they match: capture is correct")
    print(f"   If swapped pairs (AB CD → BA DC): byte order bug")
    print(f"   If completely different: OBSEL/addressing bug")

    return 0


if __name__ == "__main__":
    exit(main())
