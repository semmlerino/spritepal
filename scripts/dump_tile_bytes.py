#!/usr/bin/env python3
"""Dump raw tile bytes for comparison with Mesen VRAM."""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.hal_compression import HALCompressor
from core.rom_validator import ROMValidator


def dump_tile_bytes(rom_path: str, file_offset: int, tile_indices: list[int] | None = None):
    """Dump raw tile bytes from HAL-decompressed data.

    Args:
        rom_path: Path to ROM file
        file_offset: FILE offset (including SMC header) for HAL decompression
        tile_indices: Which tiles to dump (0-indexed). None = first 4 tiles.
    """
    if tile_indices is None:
        tile_indices = [0, 1, 2, 3]

    print(f"\n{'=' * 70}")
    print(f"TILE BYTE DUMP - FILE offset 0x{file_offset:06X}")
    print(f"{'=' * 70}\n")

    # Get header info
    header, smc_offset = ROMValidator.validate_rom_header(rom_path)
    print(f"SMC Header: {smc_offset} bytes")
    print(f"ROM offset (headerless): 0x{file_offset - smc_offset:06X}")

    # HAL decompress
    hal = HALCompressor()
    decompressed = hal.decompress_from_rom(rom_path, file_offset)

    if not decompressed:
        print("ERROR: HAL decompression failed")
        return

    total_tiles = len(decompressed) // 32
    print(f"Decompressed: {len(decompressed)} bytes = {total_tiles} tiles")
    print()

    # Dump requested tiles
    for tile_idx in tile_indices:
        if tile_idx >= total_tiles:
            print(f"Tile {tile_idx}: OUT OF RANGE (only {total_tiles} tiles)")
            continue

        start = tile_idx * 32
        tile_bytes = decompressed[start : start + 32]

        print(f"Tile {tile_idx} (bytes {start}-{start + 31}):")
        print("  Bitplanes 0-1 (bytes 0-15):")
        print(f"    {tile_bytes[0:8].hex(' ').upper()}")
        print(f"    {tile_bytes[8:16].hex(' ').upper()}")
        print("  Bitplanes 2-3 (bytes 16-31):")
        print(f"    {tile_bytes[16:24].hex(' ').upper()}")
        print(f"    {tile_bytes[24:32].hex(' ').upper()}")
        print("  All 32 bytes (one line):")
        print(f"    {tile_bytes.hex(' ').upper()}")
        print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Dump tile bytes for Mesen comparison")
    parser.add_argument("rom_path", help="Path to ROM file")
    parser.add_argument("file_offset", help="FILE offset (hex, e.g., 0x25AD84)")
    parser.add_argument("--tiles", "-t", help="Comma-separated tile indices (default: 0,1,2,3)")

    args = parser.parse_args()

    file_offset = int(args.file_offset, 16) if args.file_offset.startswith("0x") else int(args.file_offset)

    tile_indices = None
    if args.tiles:
        tile_indices = [int(t.strip()) for t in args.tiles.split(",")]

    dump_tile_bytes(args.rom_path, file_offset, tile_indices)


if __name__ == "__main__":
    main()
