#!/usr/bin/env python3
"""
Transform search: Try common tile transforms before concluding runtime generation.

Transforms tested:
1. Adjacent byte-pair swap (word endianness)
2. Bitmap-nibble encoding (both nibble orders)
3. Plane permutations (all 24 orderings)
4. H/V flips
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import permutations
from pathlib import Path


def byte_pair_swap(data: bytes) -> bytes:
    """Swap adjacent byte pairs: b0 b1 b2 b3 → b1 b0 b3 b2"""
    result = bytearray(len(data))
    for i in range(0, len(data) - 1, 2):
        result[i] = data[i + 1]
        result[i + 1] = data[i]
    return bytes(result)


def snes_4bpp_to_bitmap(tile_bytes: bytes) -> bytes:
    """Convert SNES 4bpp planar to bitmap nibbles (32 bytes)."""
    if len(tile_bytes) != 32:
        return b""

    pixels = [[0] * 8 for _ in range(8)]

    for row in range(8):
        bp0 = tile_bytes[row * 2]
        bp1 = tile_bytes[row * 2 + 1]
        bp2 = tile_bytes[16 + row * 2]
        bp3 = tile_bytes[16 + row * 2 + 1]

        for col in range(8):
            bit = 7 - col
            pixel = 0
            pixel |= (bp0 >> bit) & 1
            pixel |= ((bp1 >> bit) & 1) << 1
            pixel |= ((bp2 >> bit) & 1) << 2
            pixel |= ((bp3 >> bit) & 1) << 3
            pixels[row][col] = pixel

    # Pack as nibbles - high nibble first
    result = bytearray(32)
    for row in range(8):
        for col in range(0, 8, 2):
            byte_idx = row * 4 + col // 2
            result[byte_idx] = (pixels[row][col] << 4) | pixels[row][col + 1]

    return bytes(result)


def snes_4bpp_to_bitmap_swapped(tile_bytes: bytes) -> bytes:
    """Convert SNES 4bpp to bitmap, low nibble first."""
    if len(tile_bytes) != 32:
        return b""

    pixels = [[0] * 8 for _ in range(8)]

    for row in range(8):
        bp0 = tile_bytes[row * 2]
        bp1 = tile_bytes[row * 2 + 1]
        bp2 = tile_bytes[16 + row * 2]
        bp3 = tile_bytes[16 + row * 2 + 1]

        for col in range(8):
            bit = 7 - col
            pixel = 0
            pixel |= (bp0 >> bit) & 1
            pixel |= ((bp1 >> bit) & 1) << 1
            pixel |= ((bp2 >> bit) & 1) << 2
            pixel |= ((bp3 >> bit) & 1) << 3
            pixels[row][col] = pixel

    # Pack as nibbles - low nibble first
    result = bytearray(32)
    for row in range(8):
        for col in range(0, 8, 2):
            byte_idx = row * 4 + col // 2
            result[byte_idx] = pixels[row][col] | (pixels[row][col + 1] << 4)

    return bytes(result)


def extract_planes(tile_bytes: bytes) -> tuple[bytes, bytes, bytes, bytes]:
    """Extract 4 individual 8-byte planes from SNES 4bpp tile."""
    plane0 = bytes(tile_bytes[i * 2] for i in range(8))
    plane1 = bytes(tile_bytes[i * 2 + 1] for i in range(8))
    plane2 = bytes(tile_bytes[16 + i * 2] for i in range(8))
    plane3 = bytes(tile_bytes[16 + i * 2 + 1] for i in range(8))
    return plane0, plane1, plane2, plane3


def rebuild_from_planes(planes: tuple[bytes, ...]) -> bytes:
    """Rebuild 32-byte tile from 4 planes in given order."""
    p0, p1, p2, p3 = planes
    result = bytearray(32)
    for i in range(8):
        result[i * 2] = p0[i]
        result[i * 2 + 1] = p1[i]
        result[16 + i * 2] = p2[i]
        result[16 + i * 2 + 1] = p3[i]
    return bytes(result)


def flip_horizontal(tile_bytes: bytes) -> bytes:
    """Horizontal flip: bit-reverse each byte."""
    def reverse_bits(b: int) -> int:
        result = 0
        for i in range(8):
            if b & (1 << i):
                result |= 1 << (7 - i)
        return result

    return bytes(reverse_bits(b) for b in tile_bytes)


def flip_vertical(tile_bytes: bytes) -> bytes:
    """Vertical flip: reverse row order in each 16-byte half."""
    low = tile_bytes[:16]
    high = tile_bytes[16:]

    # Reverse 2-byte row pairs
    low_flipped = b"".join(low[i * 2 : i * 2 + 2] for i in range(7, -1, -1))
    high_flipped = b"".join(high[i * 2 : i * 2 + 2] for i in range(7, -1, -1))

    return low_flipped + high_flipped


def search_in_data(data: bytes, needle: bytes) -> list[int]:
    """Find all occurrences."""
    offsets = []
    start = 0
    while len(offsets) < 5:
        pos = data.find(needle, start)
        if pos == -1:
            break
        offsets.append(pos)
        start = pos + 1
    return offsets


def main() -> int:
    parser = argparse.ArgumentParser(description="Transform search for tiles")
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--max-tiles", type=int, default=5)

    args = parser.parse_args()

    rom_data = args.rom.read_bytes()
    print(f"ROM: {len(rom_data):,} bytes")

    with open(args.capture) as f:
        capture = json.load(f)

    # Collect non-empty tiles
    tiles: list[tuple[int, int, bytes]] = []
    for entry in capture.get("entries", []):
        sprite_id = entry.get("id")
        for tile in entry.get("tiles", []):
            tile_hex = tile.get("data_hex", "")
            if len(tile_hex) == 64 and tile_hex != "00" * 32:
                tiles.append((sprite_id, tile.get("tile_index"), bytes.fromhex(tile_hex)))

    print(f"Non-empty tiles: {len(tiles)}, testing first {min(args.max_tiles, len(tiles))}")
    print()

    for sprite_id, tile_idx, tile_bytes in tiles[: args.max_tiles]:
        print(f"{'=' * 70}")
        print(f"Sprite {sprite_id} tile {tile_idx}")
        print(f"Original: {tile_bytes.hex()[:40]}...")
        print()

        found_any = False

        # Transform 1: Byte-pair swap
        swapped = byte_pair_swap(tile_bytes)
        offsets = search_in_data(rom_data, swapped)
        if offsets:
            found_any = True
            print(f"  [FOUND] BYTE-PAIR SWAP at {', '.join(f'0x{o:06X}' for o in offsets)}")

        # Transform 2: Bitmap nibble encodings
        bitmap_high = snes_4bpp_to_bitmap(tile_bytes)
        offsets = search_in_data(rom_data, bitmap_high)
        if offsets:
            found_any = True
            print(f"  [FOUND] BITMAP (high-nibble first) at {', '.join(f'0x{o:06X}' for o in offsets)}")

        bitmap_low = snes_4bpp_to_bitmap_swapped(tile_bytes)
        offsets = search_in_data(rom_data, bitmap_low)
        if offsets:
            found_any = True
            print(f"  [FOUND] BITMAP (low-nibble first) at {', '.join(f'0x{o:06X}' for o in offsets)}")

        # Transform 3: H/V flips
        h_flip = flip_horizontal(tile_bytes)
        offsets = search_in_data(rom_data, h_flip)
        if offsets:
            found_any = True
            print(f"  [FOUND] H-FLIP at {', '.join(f'0x{o:06X}' for o in offsets)}")

        v_flip = flip_vertical(tile_bytes)
        offsets = search_in_data(rom_data, v_flip)
        if offsets:
            found_any = True
            print(f"  [FOUND] V-FLIP at {', '.join(f'0x{o:06X}' for o in offsets)}")

        hv_flip = flip_horizontal(flip_vertical(tile_bytes))
        offsets = search_in_data(rom_data, hv_flip)
        if offsets:
            found_any = True
            print(f"  [FOUND] HV-FLIP at {', '.join(f'0x{o:06X}' for o in offsets)}")

        # Transform 4: Plane permutations (all 24)
        planes = extract_planes(tile_bytes)
        plane_perms = list(permutations(range(4)))
        for perm in plane_perms:
            reordered = (planes[perm[0]], planes[perm[1]], planes[perm[2]], planes[perm[3]])
            rebuilt = rebuild_from_planes(reordered)
            if rebuilt == tile_bytes:
                continue  # Skip identity
            offsets = search_in_data(rom_data, rebuilt)
            if offsets:
                found_any = True
                print(
                    f"  [FOUND] PLANE PERM {perm} at {', '.join(f'0x{o:06X}' for o in offsets)}"
                )

        # Transform 5: Byte-pair swap on bitmap
        swapped_bitmap = byte_pair_swap(bitmap_high)
        offsets = search_in_data(rom_data, swapped_bitmap)
        if offsets:
            found_any = True
            print(
                f"  [FOUND] BITMAP+SWAP at {', '.join(f'0x{o:06X}' for o in offsets)}"
            )

        if not found_any:
            print("  [NOT FOUND] No transforms matched")

        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
