#!/usr/bin/env python3
"""
Test script for the sprite capture-to-ROM mapper.

This script:
1. Builds an expanded tile hash database from discovered sprite offsets
2. Tests the mapper with existing capture data
3. Reports database statistics and match results
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mesen_integration import (
    CaptureResult,
    MesenCaptureParser,
    TileHashDatabase,
    build_and_save_database,
)
from core.mesen_integration.capture_to_rom_mapper import CaptureToROMMapper


def parse_discovered_offsets(file_path: Path) -> list[tuple[int, str]]:
    """Parse discovered_sprite_offsets.txt file."""
    offsets: list[tuple[int, str]] = []
    seen: set[int] = set()

    if not file_path.exists():
        print(f"Warning: {file_path} not found")
        return offsets

    with open(file_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Parse lines like: "0x0CC100  # 58624 bytes, 1832 tiles, score=1.000"
            match = re.match(r"0x([0-9A-Fa-f]+)\s*#?\s*(.*)", line)
            if match:
                offset = int(match.group(1), 16)
                description = match.group(2).strip() if match.group(2) else f"Offset 0x{offset:06X}"

                # Skip duplicates
                if offset not in seen:
                    seen.add(offset)
                    offsets.append((offset, description))

    return offsets


def get_high_confidence_offsets(file_path: Path, min_score: float = 0.95) -> list[tuple[int, str]]:
    """Get offsets with confidence score >= min_score."""
    all_offsets = parse_discovered_offsets(file_path)

    # Filter by score if present in description
    high_conf: list[tuple[int, str]] = []
    for offset, desc in all_offsets:
        score_match = re.search(r"score=(\d+\.\d+)", desc)
        if score_match:
            score = float(score_match.group(1))
            if score >= min_score:
                high_conf.append((offset, desc))
        else:
            # No score = include it
            high_conf.append((offset, desc))

    return high_conf


def main():
    # Paths
    base_dir = Path(__file__).parent.parent
    rom_path = base_dir / "roms" / "Kirby Super Star (USA).sfc"
    capture_path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else base_dir / "mesen2_exchange" / "test_capture.json"
    )
    discovered_offsets_path = base_dir / "mesen2_integration" / "discovered_sprite_offsets.txt"
    database_output = base_dir / "mesen2_exchange" / "tile_hash_database.json"

    # Check ROM exists
    if not rom_path.exists():
        print(f"ERROR: ROM not found at {rom_path}")
        return 1

    print("=" * 60)
    print("SPRITE CAPTURE-TO-ROM MAPPER TEST")
    print("=" * 60)

    # Phase 1: Parse discovered offsets
    print("\n[1] Parsing discovered sprite offsets...")
    discovered = get_high_confidence_offsets(discovered_offsets_path, min_score=0.95)
    print(f"    Found {len(discovered)} high-confidence offsets (score >= 0.95)")

    # Show first few
    for offset, desc in discovered[:5]:
        print(f"    0x{offset:06X}: {desc[:50]}...")
    if len(discovered) > 5:
        print(f"    ... and {len(discovered) - 5} more")

    # Phase 2: Build expanded database
    print("\n[2] Building tile hash database...")
    mapper = CaptureToROMMapper(rom_path)

    # Combine default offsets with discovered ones
    all_offsets = list(TileHashDatabase.KNOWN_SPRITE_OFFSETS) + discovered

    # Remove duplicates while preserving order
    seen_offsets: set[int] = set()
    unique_offsets: list[tuple[int, str]] = []
    for offset, desc in all_offsets:
        if offset not in seen_offsets:
            seen_offsets.add(offset)
            unique_offsets.append((offset, desc))

    known_offsets = {offset for offset, _ in TileHashDatabase.KNOWN_SPRITE_OFFSETS}
    extra_offsets = [(offset, desc) for offset, desc in unique_offsets if offset not in known_offsets]
    print(f"    Total unique offsets to index: {len(unique_offsets)}")
    print(f"    Extra offsets beyond defaults: {len(extra_offsets)}")

    # Build database
    tile_count = mapper.build_database(additional_offsets=extra_offsets)
    print(f"    Indexed {tile_count} tiles")

    # Get stats
    stats = mapper.get_database_stats()
    print(f"    Total blocks: {stats.get('total_blocks', 0)}")
    print(f"    Unique hashes: {stats.get('total_unique_hashes', 0)}")
    print(f"    Total matches: {stats.get('total_matches', 0)}")
    print(f"    Hashes w/ collisions: {stats.get('hashes_with_collisions', 0)}")

    # Save database for future use
    if mapper._db:
        mapper._db.save_database(database_output)
        print(f"    Database saved to: {database_output}")

    # Phase 3: Test with capture file
    print("\n[3] Testing with capture file...")
    if not capture_path.exists():
        print(f"    WARNING: Capture file not found at {capture_path}")
        print("    Run the Lua script in Mesen 2 to generate a capture.")
        return 1

    # Parse capture
    parser = MesenCaptureParser()
    capture = parser.parse_file(capture_path)
    print(f"    Parsed capture: {len(capture.entries)} OAM entries")
    print(f"    Frame: {capture.frame}")

    # Check tile data format
    if capture.entries:
        first_entry = capture.entries[0]
        if first_entry.tiles:
            first_tile = first_entry.tiles[0]
            tile_hex = first_tile.data_hex
            print("\n    Sample tile data (first entry, first tile):")
            print(f"    {tile_hex[:64]}...")

            # Heuristic warning: sequential bytes often indicate bad reads or loop-index leakage.
            has_sequential_prefix = all(
                tile_hex[i * 2 : i * 2 + 2] == f"{i:02X}" for i in range(min(8, len(tile_hex) // 2))
            )
            if has_sequential_prefix:
                print("\n    ⚠️  WARNING: Capture data starts with sequential bytes.")
                print("       This often means a bad VRAM read or loop-index leakage.")
                print("       Verify VRAM word addressing and re-capture if needed.")

    # Map capture to ROM
    print("\n[4] Mapping capture to ROM offsets...")
    result = mapper.map_capture(capture)

    print(f"    Matched entries: {len(result.mapped_entries) - result.unmapped_count}/{len(result.mapped_entries)}")
    print(f"    Unmapped entries: {result.unmapped_count}")
    print(f"    Tiles with hash hits: {result.matched_tiles}/{result.total_tiles}")
    print(f"    Tiles contributing to scores: {result.scored_tiles}/{result.total_tiles}")
    if result.ignored_low_info_tiles:
        print(f"    Ignored low-info tiles: {result.ignored_low_info_tiles}")

    if result.rom_offset_summary:
        print("\n    ROM offset summary (entry votes):")
        for offset, count in list(result.rom_offset_summary.items())[:10]:
            print(f"      0x{offset:06X}: {count} entries")
    if result.rom_offset_scores:
        print("\n    ROM offset scores (weighted):")
        for offset, score in list(result.rom_offset_scores.items())[:10]:
            print(f"      0x{offset:06X}: {score:.2f}")
        print(f"    Primary offset score: {result.primary_rom_offset_score:.2f}")
        print(f"    Ambiguous: {result.ambiguous}")
        if result.ambiguity_note:
            print(f"    Note: {result.ambiguity_note}")
    else:
        print("\n    No scored matches found.")
        if result.matched_tiles:
            print("    Hash hits exist but contributed zero weight (likely low-info or collisions).")
        else:
            print("    No hash hits; verify VRAM capture integrity and DB coverage.")

    # Phase 4: Test individual tile lookup
    print("\n[5] Testing individual tile lookup...")
    # Create a known test pattern from ROM
    if mapper._db:
        test_matches = list(mapper._db.iter_all_matches())[:3]
        if test_matches:
            total_hashes = len(list(mapper._db.iter_all_matches()))
            print(f"    Database has {total_hashes} unique hashes")
            print("    Sample indexed tiles:")
            for tile_hash, matches in test_matches:
                sample = matches[0]
                print(
                    f"      Hash: {tile_hash[:16]}... -> ROM 0x{sample.rom_offset:06X} tile #{sample.tile_index}"
                )
                if len(matches) > 1:
                    print(f"        (+{len(matches) - 1} more candidates)")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

    if result.unmapped_count == len(result.mapped_entries):
        print("\nNext steps:")
        print("1. Run Mesen 2 with the fixed Lua script:")
        print("   mesen2_integration/lua_scripts/test_sprite_capture.lua")
        print("2. The script auto-captures at your TARGET_FRAME")
        print("3. Re-run this test with the capture file path")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
