#!/usr/bin/env python3
"""
Compare VRAM tile dump to extracted sprite files.

Usage:
    1. In Mesen2, run vram_tile_dump.lua and press F11
    2. Copy the hex bytes from console output
    3. Run: python scripts/compare_vram_to_extraction.py <hex_string> <bin_file>

Or visually compare the extracted PNGs to what you see in Sprite Viewer.
"""

import sys
from pathlib import Path


def hex_to_bytes(hex_string: str) -> bytes:
    """Convert space-separated hex string to bytes."""
    hex_clean = hex_string.replace(" ", "").replace("\n", "")
    return bytes.fromhex(hex_clean)


def find_pattern_in_file(pattern: bytes, filepath: Path) -> list[int]:
    """Find all occurrences of pattern in file."""
    with open(filepath, "rb") as f:
        data = f.read()

    offsets = []
    start = 0
    while True:
        pos = data.find(pattern, start)
        if pos == -1:
            break
        offsets.append(pos)
        start = pos + 1

    return offsets


def main():
    # Check extracted sprites
    extracted_dir = Path("extracted_sprites")

    if not extracted_dir.exists():
        print("No extracted_sprites directory found")
        return 1

    print("Extracted sprite folders:")
    print("=" * 50)

    for folder in sorted(extracted_dir.iterdir()):
        if folder.is_dir():
            bin_files = list(folder.glob("*.bin"))
            list(folder.glob("*.png"))
            json_files = list(folder.glob("*_metadata.json"))

            if bin_files:
                bin_file = bin_files[0]
                size = bin_file.stat().st_size
                print(f"\n{folder.name}/")
                print(f"  Size: {size} bytes ({size // 32} tiles)")

                # Show first 32 bytes (first tile)
                with open(bin_file, "rb") as f:
                    first_tile = f.read(32)
                hex_preview = " ".join(f"{b:02X}" for b in first_tile[:16])
                print(f"  First 16 bytes: {hex_preview}")

                if json_files:
                    import json

                    with open(json_files[0]) as f:
                        meta = json.load(f)
                    print(f"  ROM offset: {meta.get('rom_offset', 'unknown')}")

    print("\n" + "=" * 50)
    print("\nTo compare with VRAM:")
    print("1. Open the .png files and compare visually to Sprite Viewer")
    print("2. Or dump VRAM hex and search in .bin files")

    # If arguments provided, do comparison
    if len(sys.argv) >= 3:
        hex_pattern = sys.argv[1]
        target_file = Path(sys.argv[2])

        pattern = hex_to_bytes(hex_pattern)
        print(f"\nSearching for pattern ({len(pattern)} bytes) in {target_file}...")

        offsets = find_pattern_in_file(pattern, target_file)
        if offsets:
            print(f"FOUND at offsets: {[hex(o) for o in offsets]}")
        else:
            print("Pattern not found")

    return 0


if __name__ == "__main__":
    sys.exit(main())
