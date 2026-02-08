#!/usr/bin/env python3
"""
Search ROM for mushroom sprite data by looking for patterns that match
what we see in VRAM at $6A00
"""

import os
import struct
from pathlib import Path


def search_rom_for_pattern(rom_path, pattern, max_results=10):
    """Search ROM for a specific byte pattern"""
    with open(rom_path, "rb") as f:
        rom_data = f.read()

    results = []
    pattern_bytes = bytes(pattern)

    # Search for the pattern
    offset = 0
    while offset < len(rom_data) - len(pattern):
        idx = rom_data.find(pattern_bytes, offset)
        if idx == -1:
            break
        results.append(idx)
        offset = idx + 1
        if len(results) >= max_results:
            break

    return results


def search_for_compressed_sprite(rom_path):
    """Search for HAL compressed sprite data that could decompress to mushroom"""
    with open(rom_path, "rb") as f:
        rom_data = f.read()

    # HAL compression signatures
    # Look for regions that might be compressed sprite data
    potential_sprites = []

    # Search for common sprite header patterns
    # HAL compressed data often starts with specific patterns
    for offset in range(0, len(rom_data) - 0x100, 4):
        # Check for potential compressed data markers
        if rom_data[offset] == 0xE3:  # Common HAL compression marker
            # Check if this could be a sprite
            size_bytes = rom_data[offset + 1 : offset + 3]
            size = struct.unpack("<H", size_bytes)[0]

            if 0x20 <= size <= 0x200:  # Reasonable sprite size
                potential_sprites.append((offset, size))

    return potential_sprites


def analyze_vram_region(rom_path, savestate_data):
    """Analyze what might have written to VRAM $6A00"""
    # The pattern we see: 87 7E repeated
    # This could be:
    # 1. A fill pattern (initialization)
    # 2. Compressed data that expands to this
    # 3. A placeholder before real sprite loads

    # Search for the exact pattern in ROM
    pattern = [0x87, 0x7E] * 32  # The repeating pattern we found
    results = search_rom_for_pattern(rom_path, pattern, max_results=5)

    if results:
        print(f"Found exact pattern at ROM offsets: {[f'${r:06X}' for r in results]}")
    else:
        print("Exact pattern not found in ROM")

    # Search for just the 87 7E pair
    small_pattern = [0x87, 0x7E, 0x87, 0x7E]
    results = search_rom_for_pattern(rom_path, small_pattern, max_results=20)

    if results:
        print(f"\nFound '87 7E 87 7E' pattern at {len(results)} locations")
        print(f"First few offsets: {[f'${r:06X}' for r in results[:5]]}")


def main():
    rom_path = os.environ.get(
        "SPRITEPAL_ROM_PATH", str(Path(__file__).resolve().parents[2] / "roms" / "Kirby Super Star (USA).sfc")
    )
    project_root = Path(__file__).resolve().parents[2]
    sprite_data_path = project_root / "mushroom_sprite_candidate_006A00.bin"

    print("Searching ROM for mushroom sprite data...")
    print("-" * 60)

    # Load the sprite data from savestate
    with open(sprite_data_path, "rb") as f:
        sprite_data = f.read()

    print(f"Sprite data from VRAM $6A00: {len(sprite_data)} bytes")
    print(f"First 32 bytes: {' '.join(f'{b:02X}' for b in sprite_data[:32])}")
    print()

    # Search ROM for patterns
    print("1. Searching for exact VRAM pattern in ROM...")
    analyze_vram_region(rom_path, sprite_data)

    print("\n2. Searching for potential HAL compressed sprites...")
    compressed = search_for_compressed_sprite(rom_path)
    print(f"Found {len(compressed)} potential compressed sprites")

    if compressed:
        print("\nChecking compressed sprites in mushroom area (0x300000-0x310000)...")
        mushroom_area = [c for c in compressed if 0x300000 <= c[0] <= 0x310000]

        for offset, size in mushroom_area[:10]:
            print(f"  Offset ${offset:06X}: {size} bytes")

    print("\n3. Searching for mushroom sprite based on known enemy sprite locations...")
    # Based on previous discoveries, enemy sprites are often in these ranges
    enemy_ranges = [
        (0x300000, 0x310000, "Main enemy sprite area"),
        (0x280000, 0x290000, "Character sprite area"),
        (0x270000, 0x280000, "UI/background area"),
    ]

    for start, end, description in enemy_ranges:
        print(f"\nSearching {description} (${start:06X}-${end:06X})...")

        # Look for non-zero, non-repeating data that could be sprites
        with open(rom_path, "rb") as f:
            f.seek(start)
            data = f.read(end - start)

        # Find regions with high entropy (likely graphics data)
        for offset in range(0, len(data) - 0x80, 0x80):
            chunk = data[offset : offset + 0x80]

            # Check if this looks like sprite data
            non_zero = sum(1 for b in chunk if b != 0)
            unique = len(set(chunk))

            if non_zero > 64 and unique > 16:  # Good entropy
                # Check if it starts with a potential header
                if chunk[0] in [0xE3, 0xE7, 0xF3, 0xF7]:  # Common HAL markers
                    rom_offset = start + offset
                    print(f"  Potential sprite at ${rom_offset:06X}: {non_zero} non-zero bytes, {unique} unique values")
                    print(f"    First 16 bytes: {' '.join(f'{b:02X}' for b in chunk[:16])}")


if __name__ == "__main__":
    main()
