#!/usr/bin/env python3
"""
Discover all valid HAL-compressed graphics offsets in ROM.

Scans the ROM comprehensively to find all valid HAL blocks,
providing complete offset coverage for ROM tile matching.

Usage:
    python scripts/discover_rom_offsets.py --rom "roms/Kirby Super Star (USA).sfc"
    python scripts/discover_rom_offsets.py --rom "roms/Kirby Super Star (USA).sfc" --json > offsets.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.hal_compression import HALCompressor
from core.mesen_integration.gfx_pointer_table import (
    GFX_POINTER_TABLE_OFFSET,
    GFXPointerTableParser,
)
from utils.rom_utils import detect_smc_offset_from_size


def scan_rom_for_hal_blocks(
    rom_path: Path,
    start: int = 0x000000,
    end: int | None = None,
    step: int = 0x100,
    min_tiles: int = 1,
    progress: bool = True,
) -> list[tuple[int, int, str]]:
    """
    Scan ROM for valid HAL-compressed blocks.

    Returns:
        List of (rom_offset, tile_count, description) tuples
    """
    hal = HALCompressor()
    rom_data = rom_path.read_bytes()
    header_offset = detect_smc_offset_from_size(len(rom_data))

    if end is None:
        end = len(rom_data) - header_offset

    results: list[tuple[int, int, str]] = []
    total_steps = (end - start) // step

    for i, offset in enumerate(range(start, end, step)):
        if progress and i % 100 == 0:
            pct = i / total_steps * 100 if total_steps > 0 else 0
            print(f"\rScanning: {pct:.1f}% (${offset:06X})...", end="", file=sys.stderr)

        file_offset = offset + header_offset
        try:
            data = hal.decompress_from_rom(str(rom_path), file_offset)
            if len(data) >= 32 * min_tiles:
                tile_count = len(data) // 32
                bank = (offset >> 16) & 0xFF
                addr = offset & 0xFFFF
                desc = f"Bank ${bank:02X} @ ${addr:04X} ({tile_count} tiles)"
                results.append((offset, tile_count, desc))
        except Exception:
            pass

    if progress:
        print(f"\rScanning complete: {len(results)} blocks found.      ", file=sys.stderr)

    return results


def get_pointer_table_offsets(rom_path: Path) -> list[tuple[int, int, str]]:
    """Get offsets from the GFX pointer table."""
    parser = GFXPointerTableParser(rom_path)
    table = parser.parse_pointer_table(GFX_POINTER_TABLE_OFFSET, max_entries=512)

    hal = HALCompressor()
    header_offset = detect_smc_offset_from_size(rom_path.stat().st_size)

    results: list[tuple[int, int, str]] = []

    for entry in table.entries:
        if not entry.is_valid:
            continue

        try:
            file_offset = entry.rom_offset + header_offset
            data = hal.decompress_from_rom(str(rom_path), file_offset)
            if len(data) >= 32:
                tile_count = len(data) // 32
                desc = f"GFX table entry #{entry.index} ({tile_count} tiles)"
                results.append((entry.rom_offset, tile_count, desc))
        except Exception:
            pass

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover HAL-compressed graphics offsets in ROM")
    parser.add_argument(
        "--rom",
        type=Path,
        required=True,
        help="Path to ROM file",
    )
    parser.add_argument(
        "--start",
        type=lambda x: int(x, 16) if x.startswith("0x") else int(x),
        default=0x000000,
        help="Start offset (default: 0x000000)",
    )
    parser.add_argument(
        "--end",
        type=lambda x: int(x, 16) if x.startswith("0x") else int(x),
        default=None,
        help="End offset (default: ROM size)",
    )
    parser.add_argument(
        "--step",
        type=lambda x: int(x, 16) if x.startswith("0x") else int(x),
        default=0x100,
        help="Scan step size (default: 0x100)",
    )
    parser.add_argument(
        "--min-tiles",
        type=int,
        default=4,
        help="Minimum tiles to consider valid (default: 4)",
    )
    parser.add_argument(
        "--pointer-table-only",
        action="store_true",
        help="Only scan GFX pointer table entries",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    if not args.rom.exists():
        print(f"Error: ROM not found: {args.rom}", file=sys.stderr)
        return 1

    all_offsets: list[tuple[int, int, str]] = []

    # Get pointer table entries
    print("Scanning GFX pointer table...", file=sys.stderr)
    ptr_offsets = get_pointer_table_offsets(args.rom)
    print(f"Found {len(ptr_offsets)} valid pointer table entries", file=sys.stderr)
    all_offsets.extend(ptr_offsets)

    # Scan ROM (unless pointer-table-only)
    if not args.pointer_table_only:
        print(f"\nScanning ROM ${args.start:06X}-${args.end or 'END':06X}...", file=sys.stderr)
        scan_offsets = scan_rom_for_hal_blocks(
            args.rom,
            start=args.start,
            end=args.end,
            step=args.step,
            min_tiles=args.min_tiles,
        )

        # Deduplicate
        existing = {o[0] for o in all_offsets}
        for offset, tiles, desc in scan_offsets:
            if offset not in existing:
                all_offsets.append((offset, tiles, desc))
                existing.add(offset)

    # Sort by offset
    all_offsets.sort(key=lambda x: x[0])

    # Output
    if args.json:
        output = {
            "rom": str(args.rom),
            "offsets": [{"rom_offset": f"0x{o:06X}", "tiles": t, "description": d} for o, t, d in all_offsets],
            "total_tiles": sum(t for _, t, _ in all_offsets),
            "total_blocks": len(all_offsets),
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print(f"DISCOVERED HAL BLOCKS: {len(all_offsets)}")
        print(f"{'=' * 60}")

        total_tiles = 0
        for offset, tiles, desc in all_offsets:
            print(f"  ${offset:06X}: {tiles:5d} tiles - {desc}")
            total_tiles += tiles

        print(f"\nTotal: {total_tiles} tiles from {len(all_offsets)} blocks")

    return 0


if __name__ == "__main__":
    sys.exit(main())
