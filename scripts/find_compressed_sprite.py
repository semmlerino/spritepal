#!/usr/bin/env python3
"""
Find HAL-compressed sprite offsets by searching decompressed data for VRAM signatures.

Usage:
    python find_compressed_sprite.py <vram_signature_hex> [--start OFFSET] [--end OFFSET]

Example:
    python find_compressed_sprite.py "DF CF F9 78 F9 78 FB 78"
    python find_compressed_sprite.py "DF CF F9 78" --start 0x010000 --end 0x030000
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hal_compression import HALCompressor


def parse_hex_signature(sig_str: str) -> bytes:
    """Parse hex string like 'DF CF F9 78' into bytes."""
    # Remove common separators and convert
    cleaned = sig_str.replace(" ", "").replace(",", "").replace("0x", "")
    return bytes.fromhex(cleaned)


def search_compressed_blocks(
    rom_path: str,
    signature: bytes,
    start_offset: int = 0x010000,
    end_offset: int = 0x050000,
    step: int = 0x100,
) -> list[tuple[int, int, int]]:
    """
    Search ROM for HAL-compressed blocks containing the signature.

    Returns list of (offset, match_position, decompressed_size) tuples.
    """
    rom_data = Path(rom_path).read_bytes()
    hal = HALCompressor()
    matches = []

    print(f"Searching {start_offset:#x} - {end_offset:#x} for signature: {signature.hex(' ')}")
    print(f"ROM size: {len(rom_data)} bytes")

    checked = 0
    for offset in range(start_offset, min(end_offset, len(rom_data)), step):
        checked += 1
        if checked % 100 == 0:
            print(f"  Checked {checked} offsets... ({offset:#x})", end="\r")

        try:
            decompressed = hal.decompress_from_rom(rom_path, offset)
            if decompressed and len(decompressed) >= len(signature):
                # Search for signature in decompressed data
                pos = decompressed.find(signature)
                if pos >= 0:
                    matches.append((offset, pos, len(decompressed)))
                    print(f"\n  FOUND at {offset:#06x}: signature at byte {pos} of {len(decompressed)} decompressed bytes")
        except Exception:
            pass  # Invalid compressed data, skip

    print(f"\nChecked {checked} offsets total")
    return matches


def main():
    parser = argparse.ArgumentParser(description="Find HAL-compressed sprite offsets")
    parser.add_argument("signature", help="VRAM signature as hex bytes (e.g., 'DF CF F9 78')")
    parser.add_argument("--rom", default="roms/Kirby Super Star (USA).sfc", help="ROM file path")
    parser.add_argument("--start", type=lambda x: int(x, 0), default=0x010000, help="Start offset (hex)")
    parser.add_argument("--end", type=lambda x: int(x, 0), default=0x050000, help="End offset (hex)")
    parser.add_argument("--step", type=lambda x: int(x, 0), default=0x10, help="Search step size")

    args = parser.parse_args()

    try:
        signature = parse_hex_signature(args.signature)
    except ValueError as e:
        print(f"Error parsing signature: {e}")
        sys.exit(1)

    print(f"Signature: {signature.hex(' ')} ({len(signature)} bytes)")

    if not Path(args.rom).exists():
        print(f"ROM not found: {args.rom}")
        sys.exit(1)

    matches = search_compressed_blocks(
        args.rom,
        signature,
        args.start,
        args.end,
        args.step,
    )

    if matches:
        print(f"\n=== FOUND {len(matches)} MATCHING OFFSETS ===")
        for offset, pos, size in sorted(matches):
            tile_num = pos // 32  # 32 bytes per 4bpp tile
            print(f"  {offset:#06x}: signature at tile {tile_num} (byte {pos}) of {size//32} tiles")
    else:
        print("\nNo matches found. Try:")
        print("  - Different search range (--start, --end)")
        print("  - Shorter signature (first 4 bytes)")
        print("  - Smaller step size (--step 0x1)")


if __name__ == "__main__":
    main()
