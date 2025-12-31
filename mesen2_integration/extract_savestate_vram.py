#!/usr/bin/env python3
"""
Extract VRAM data from Mesen2 savestate to find mushroom sprite
"""

import zlib


def extract_vram_from_savestate(savestate_path: str):
    """Extract VRAM contents from Mesen2 .mss savestate"""

    with open(savestate_path, 'rb') as f:
        data = f.read()

    # Check header
    if data[:3] != b'MSS':
        print("Not a valid Mesen2 savestate")
        return None

    print(f"Savestate format: {data[:3].decode()}")
    print(f"Version: {data[3]}.{data[4]}")

    # Find zlib compressed data (starts at offset 0x25)
    compressed_start = 0x25
    compressed_data = data[compressed_start:]

    try:
        # Try different decompression methods
        decompressed = None

        # Method 1: Standard zlib
        try:
            decompressed = zlib.decompress(compressed_data)
            print("Decompression method: zlib")
        except Exception:
            pass

        # Method 2: Raw deflate (no header)
        if not decompressed:
            try:
                decompressed = zlib.decompress(compressed_data, -zlib.MAX_WBITS)
                print("Decompression method: raw deflate")
            except Exception:
                pass

        # Method 3: gzip
        if not decompressed:
            try:
                import gzip
                decompressed = gzip.decompress(compressed_data)
                print("Decompression method: gzip")
            except Exception:
                pass

        if not decompressed:
            print("All decompression methods failed")
            print("First 64 bytes of compressed data:")
            for i in range(0, min(64, len(compressed_data)), 16):
                hex_str = ' '.join(f'{b:02x}' for b in compressed_data[i:i+16])
                print(f"  {hex_str}")
            return None

        print(f"Decompressed size: {len(decompressed):,} bytes")

        # Save decompressed data for analysis
        output_path = "savestate_decompressed.bin"
        with open(output_path, 'wb') as f:
            f.write(decompressed)
        print(f"Saved decompressed data to {output_path}")

        # VRAM is typically 64KB (0x10000 bytes)
        # Need to find where it's stored in the savestate
        # Let's search for patterns or specific offsets

        # Try to find VRAM section
        # SNES VRAM is 64KB, look for a 64KB aligned section
        vram_size = 0x10000  # 64KB

        # Search for potential VRAM sections
        print("\nSearching for VRAM section (64KB blocks)...")
        for offset in range(0, len(decompressed) - vram_size, 0x1000):
            # Check if this could be VRAM
            # VRAM often has patterns of tile data
            section = decompressed[offset:offset + vram_size]

            # Check for the mushroom sprite area at VRAM $6A00
            vram_6a00_offset = 0x6A00
            if offset + vram_6a00_offset + 128 <= len(decompressed):
                mushroom_data = section[vram_6a00_offset:vram_6a00_offset + 128]

                # Check if this looks like tile data (non-zero, patterned)
                non_zero = sum(1 for b in mushroom_data if b != 0)
                if non_zero > 64:  # At least half non-zero
                    print(f"\nPotential VRAM found at offset 0x{offset:06X}")
                    print("Mushroom sprite area ($6A00-$6A80):")
                    print(f"  Non-zero bytes: {non_zero}/128")

                    # Show first 32 bytes of mushroom sprite
                    print("  First 32 bytes (one tile):")
                    for i in range(0, 32, 16):
                        hex_str = ' '.join(f'{b:02x}' for b in mushroom_data[i:i+16])
                        print(f"    {hex_str}")

                    # Save this potential mushroom sprite data
                    mushroom_file = f"potential_mushroom_{offset:06X}.bin"
                    with open(mushroom_file, 'wb') as f:
                        f.write(mushroom_data)
                    print(f"  Saved to {mushroom_file}")

        return decompressed

    except zlib.error as e:
        print(f"Failed to decompress: {e}")
        return None

def analyze_decompressed_data(data: bytes):
    """Analyze the structure of decompressed savestate data"""

    print("\n=== Savestate Structure Analysis ===")
    print(f"Total size: {len(data):,} bytes")

    # Look for recognizable patterns
    # SNES memory map markers
    markers = {
        b'SNES': "SNES marker",
        b'CPU\x00': "CPU state",
        b'PPU\x00': "PPU state",
        b'SPC\x00': "SPC state",
        b'VRAM': "VRAM marker",
        b'CGRAM': "CGRAM marker",
        b'OAM\x00': "OAM marker"
    }

    for marker, desc in markers.items():
        pos = data.find(marker)
        if pos != -1:
            print(f"Found {desc} at offset 0x{pos:06X}")

    # Look for the mushroom tile pattern we know exists
    # The mushroom is at VRAM $6A00 and we know it's a 16x16 sprite
    print("\nSearching for tile patterns at VRAM $6A00 offset...")

    # Try different possible VRAM start positions
    possible_vram_starts = []

    # Method 1: Look for 64KB blocks that could be VRAM
    for i in range(0, len(data) - 0x10000, 0x100):
        # Check if this 64KB block has the right characteristics
        block = data[i:i + 0x10000]

        # VRAM characteristics:
        # - Has tile data (repeating patterns)
        # - Not all zeros or all FF
        zeros = block.count(b'\x00')
        ffs = block.count(b'\xFF')

        if zeros < 0x8000 and ffs < 0x8000:  # Less than half zeros or FFs
            possible_vram_starts.append(i)

    print(f"Found {len(possible_vram_starts)} potential VRAM blocks")
    for start in possible_vram_starts[:5]:  # Check first 5
        print(f"  Potential VRAM at 0x{start:06X}")

if __name__ == "__main__":
    # Analyze the Sprite.mss savestate where mushroom is visible
    savestate = "Sprite.mss"
    print(f"=== Extracting VRAM from {savestate} ===\n")

    decompressed = extract_vram_from_savestate(savestate)

    if decompressed:
        analyze_decompressed_data(decompressed)
