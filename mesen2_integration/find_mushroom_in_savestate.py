#!/usr/bin/env python3
"""
Find mushroom sprite data in Mesen2 savestates by comparing Before.mss and Sprite.mss
The mushroom should be present in Sprite.mss but not in Before.mss
"""

import zlib
from pathlib import Path


def extract_vram_from_savestate(savestate_path):
    """Extract VRAM data from a Mesen2 savestate"""
    with open(savestate_path, 'rb') as f:
        data = f.read()

    # Check for MSS header
    if data[:3] != b'MSS':
        print(f"Invalid savestate header in {savestate_path}")
        return None, None

    # Find the start of zlib data (starts with 0x78)
    zlib_start = None
    for i in range(4, min(100, len(data))):
        if data[i] == 0x78 and data[i+1] in [0x01, 0x5E, 0x9C, 0xDA]:  # Common zlib headers
            zlib_start = i
            print(f"Found zlib data at offset {i}")
            break

    if not zlib_start:
        print(f"Could not find zlib data in {savestate_path}")
        return None, None

    # Try different decompression methods
    decompressed = None

    # Method 1: Standard zlib from detected start
    try:
        decompressed = zlib.decompress(data[zlib_start:])
        print(f"Decompressed {savestate_path} with standard zlib: {len(decompressed)} bytes")
    except Exception as e:
        print(f"Standard zlib failed: {e}")

    # Method 2: Raw deflate from detected start
    if not decompressed:
        try:
            decompressed = zlib.decompress(data[zlib_start:], -zlib.MAX_WBITS)
            print(f"Decompressed {savestate_path} with raw deflate: {len(decompressed)} bytes")
        except Exception as e:
            print(f"Raw deflate failed: {e}")

    if not decompressed:
        print(f"Failed to decompress {savestate_path}")
        return None, None

    # VRAM is 64KB in SNES
    vram_size = 64 * 1024

    # Find VRAM in the savestate
    # Based on previous analysis, VRAM should be after CPU/PPU state
    # Let's search for it by looking at known offsets

    # Try to find VRAM data
    # In our target range $6A00-$6A80 (27136-27264 bytes into VRAM)

    # Common offsets where VRAM might be in the savestate
    possible_offsets = [
        0x1000,   # After header
        0x2000,   # After CPU state
        0x4000,   # After PPU state
        0x8000,   # After APU state
        0x10000,  # Common location
        0x20000,  # Another common location
    ]

    # We'll extract potential VRAM sections and look for patterns
    vram_sections = {}
    for offset in possible_offsets:
        if offset + vram_size <= len(decompressed):
            vram_sections[offset] = decompressed[offset:offset + vram_size]

    return decompressed, vram_sections

def compare_vram_regions(before_data, sprite_data, vram_offset=0x6A00, size=0x80):
    """Compare VRAM regions between two savestates at the mushroom sprite location"""
    differences = []

    for i in range(size):
        if before_data[vram_offset + i] != sprite_data[vram_offset + i]:
            differences.append((vram_offset + i, before_data[vram_offset + i], sprite_data[vram_offset + i]))

    return differences

def find_sprite_pattern(vram_data, start_offset=0x6A00, size=0x80):
    """Look for sprite patterns in VRAM data"""
    # SNES sprites use 4bpp format (32 bytes per 8x8 tile)
    # Look for non-zero data in our target range

    sprite_data = vram_data[start_offset:start_offset + size]

    # Check if there's significant data here
    non_zero_bytes = sum(1 for b in sprite_data if b != 0)

    if non_zero_bytes > 16:  # At least half a tile worth of data
        print(f"Found potential sprite data at VRAM ${start_offset:04X}:")
        print(f"  Non-zero bytes: {non_zero_bytes}/{size}")

        # Show first 32 bytes (one tile)
        print("  First tile data:")
        for i in range(0, min(32, len(sprite_data)), 16):
            hex_str = ' '.join(f'{b:02X}' for b in sprite_data[i:i+16])
            print(f"    {hex_str}")

        return True
    return False

def main():
    base_dir = Path('/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal')

    before_path = base_dir / 'Before.mss'
    base_dir / 'Entering.mss'
    sprite_path = base_dir / 'Sprite.mss'

    print("Analyzing savestates to find mushroom sprite data...")
    print("-" * 60)

    # Extract VRAM from each savestate
    print("\n1. Extracting VRAM from Before.mss...")
    before_data, _before_vram_sections = extract_vram_from_savestate(before_path)

    print("\n2. Extracting VRAM from Sprite.mss...")
    sprite_data, _sprite_vram_sections = extract_vram_from_savestate(sprite_path)

    if not before_data or not sprite_data:
        print("Failed to extract savestate data")
        return

    print("\n3. Comparing VRAM regions at $6A00...")

    # Try each possible VRAM offset
    for offset_name, offset_value in [
        ("Direct offset", 0x6A00),
        ("After PPU state", 0x10000 + 0x6A00),
        ("After APU state", 0x20000 + 0x6A00),
        ("Common location 1", 0x30000 + 0x6A00),
        ("Common location 2", 0x40000 + 0x6A00),
    ]:
        if offset_value + 0x80 <= len(sprite_data):
            print(f"\nChecking {offset_name} (offset ${offset_value:06X})...")

            # Get the data at this offset
            before_region = before_data[offset_value:offset_value + 0x80]
            sprite_region = sprite_data[offset_value:offset_value + 0x80]

            # Count differences
            differences = sum(1 for i in range(0x80) if before_region[i] != sprite_region[i])

            if differences > 0:
                print(f"  Found {differences} byte differences!")

                # Show the sprite data
                non_zero = sum(1 for b in sprite_region if b != 0)
                if non_zero > 16:
                    print(f"  Sprite.mss has {non_zero} non-zero bytes in this region")
                    print("  First 32 bytes of sprite data:")
                    for i in range(0, 32, 16):
                        hex_str = ' '.join(f'{b:02X}' for b in sprite_region[i:i+16])
                        print(f"    {hex_str}")

                    # Save the sprite data for analysis
                    output_path = base_dir / f'mushroom_sprite_candidate_{offset_value:06X}.bin'
                    with open(output_path, 'wb') as f:
                        f.write(bytes(sprite_region))
                    print(f"  Saved candidate sprite data to {output_path.name}")

    print("\n4. Searching for sprite patterns in entire savestate...")

    # Search for specific patterns that might indicate sprite data
    # Look for sequences of non-zero bytes that could be tiles
    for search_offset in range(0, min(len(sprite_data) - 0x80, 0x80000), 0x1000):
        region = sprite_data[search_offset:search_offset + 0x80]
        non_zero = sum(1 for b in region if b != 0)

        if non_zero > 32:  # At least one full tile
            # Check if this region is different between savestates
            if search_offset + 0x80 <= len(before_data):
                before_region = before_data[search_offset:search_offset + 0x80]
                if before_region != region:
                    differences = sum(1 for i in range(0x80) if before_region[i] != region[i])
                    if differences > 32:
                        print(f"\nFound significant difference at offset ${search_offset:06X}:")
                        print(f"  {differences} bytes differ, {non_zero} non-zero bytes in Sprite.mss")

if __name__ == '__main__':
    main()
