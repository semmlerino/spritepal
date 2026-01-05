#!/usr/bin/env python3
"""
Direct tile matching: VRAM tiles → ROM offsets (bypasses staging correlation).

This is a simplified version that directly compares captured VRAM tile data
against decompressed ROM tiles, without needing staging buffer tracking.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.mesen_integration.rom_tile_matcher import ROMTileMatcher


def main() -> int:
    parser = argparse.ArgumentParser(description="Direct VRAM tile → ROM matching")
    parser.add_argument("--rom", type=Path, required=True, help="Path to ROM file")
    parser.add_argument("--capture", type=Path, nargs="+", required=True, help="Capture JSON files")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")

    args = parser.parse_args()

    if not args.rom.exists():
        print(f"Error: ROM not found: {args.rom}", file=sys.stderr)
        return 1

    # Initialize matcher
    print(f"Initializing matcher with ROM: {args.rom}", file=sys.stderr)
    matcher = ROMTileMatcher(rom_path=args.rom, apply_sa1_conversion=True)

    # Build database from known sprite offsets
    print("Building tile database from known offsets...", file=sys.stderr)
    total_db_tiles = matcher.build_database()
    print(f"Indexed {total_db_tiles} tiles", file=sys.stderr)

    # Load captures and match tiles
    results = []
    total_tiles = 0
    matched_tiles = 0

    for capture_path in args.capture:
        if not capture_path.exists():
            print(f"Warning: {capture_path} not found", file=sys.stderr)
            continue

        with open(capture_path) as f:
            capture = json.load(f)

        frame = capture.get("frame", 0)
        print(f"Processing capture frame {frame}...", file=sys.stderr)

        for entry in capture.get("entries", []):
            sprite_id = entry.get("id", 0)

            for tile in entry.get("tiles", []):
                total_tiles += 1
                tile_hex = tile.get("data_hex", "")

                if len(tile_hex) != 64:  # 32 bytes = 64 hex chars
                    continue

                tile_data = bytes.fromhex(tile_hex)
                matches = matcher.lookup_vram_tile(tile_data)

                if matches:
                    matched_tiles += 1
                    best = matches[0]
                    results.append(
                        {
                            "frame": frame,
                            "sprite_id": sprite_id,
                            "tile_index": tile.get("tile_index"),
                            "vram_addr": f"0x{tile.get('vram_addr', 0):04X}",
                            "rom_offset": f"0x{best.rom_offset:06X}",
                            "rom_tile_index": best.tile_index,
                            "rom_description": best.description,
                            "flip_variant": best.flip_variant,
                        }
                    )

    match_rate = (matched_tiles / total_tiles * 100) if total_tiles > 0 else 0
    print(f"Matched {matched_tiles}/{total_tiles} tiles ({match_rate:.1f}%)", file=sys.stderr)

    # Collect unique ROM offsets
    unique_offsets = set()
    for r in results:
        unique_offsets.add(r["rom_offset"])

    # Output
    if args.json:
        output_data = {
            "summary": {
                "total_tiles": total_tiles,
                "matched_tiles": matched_tiles,
                "match_rate": f"{match_rate:.1f}%",
                "unique_rom_offsets": len(unique_offsets),
            },
            "matches": results,
            "unique_offsets": sorted(unique_offsets),
        }
        output = json.dumps(output_data, indent=2)
    else:
        lines = [f"Direct Tile Matching: {matched_tiles}/{total_tiles} ({match_rate:.1f}%)"]
        lines.append(f"Unique ROM offsets: {len(unique_offsets)}")
        lines.append("")
        for r in results[:50]:
            lines.append(
                f"  Sprite {r['sprite_id']} tile {r['tile_index']}: "
                f"{r['vram_addr']} → {r['rom_offset']} ({r['flip_variant']})"
            )
        if len(results) > 50:
            lines.append(f"  ... and {len(results) - 50} more")
        output = "\n".join(lines)

    if args.output:
        args.output.write_text(output)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
