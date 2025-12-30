#!/usr/bin/env python3
"""
Analyze sprite capture quality before expanding the tile database.

This script focuses on capture integrity:
- Unique-byte distribution (low-info tiles vs. high-entropy tiles)
- Odd-byte sanity (VRAM read correctness)
- Optional hash-hit/scoring stats when a database is provided
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mesen_integration import MesenCaptureParser
from core.mesen_integration.capture_to_rom_mapper import (
    LOW_INFO_UNIQUE_BYTES,
    CaptureToROMMapper,
)
from core.mesen_integration.tile_hash_database import TileHashDatabase
from utils.logging_config import setup_logging


def _bucket_unique_count(unique_count: int) -> str:
    if unique_count <= LOW_INFO_UNIQUE_BYTES:
        return f"0-{LOW_INFO_UNIQUE_BYTES}"
    if unique_count <= 4:
        return "3-4"
    if unique_count <= 7:
        return "5-7"
    if unique_count <= 15:
        return "8-15"
    return "16+"


def _parse_discovered_offsets(file_path: Path, min_score: float) -> list[tuple[int, str]]:
    offsets: list[tuple[int, str]] = []
    seen: set[int] = set()
    if not file_path.exists():
        return offsets

    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"0x([0-9A-Fa-f]+)\s*#?\s*(.*)", line)
        if not match:
            continue
        offset = int(match.group(1), 16)
        desc = match.group(2).strip() if match.group(2) else f"Offset 0x{offset:06X}"
        if offset in seen:
            continue
        score_match = re.search(r"score=(\d+\.\d+)", desc)
        if score_match and float(score_match.group(1)) < min_score:
            continue
        seen.add(offset)
        offsets.append((offset, desc))
    return offsets


def _build_mapper(
    rom_path: Path | None,
    database_path: Path | None,
    use_discovered: bool,
    min_score: float,
) -> CaptureToROMMapper | None:
    if not rom_path and not database_path:
        return None

    if database_path and database_path.exists():
        if not rom_path:
            print("WARNING: ROM path not provided; skipping ROM/header verification for database.")
        rom_hint = rom_path or database_path
        mapper = CaptureToROMMapper(rom_hint, database_path)
        mapper.build_database()
        return mapper

    if not rom_path:
        raise ValueError("ROM path is required when no database is provided.")

    mapper = CaptureToROMMapper(rom_path, database_path)

    additional_offsets = None
    if use_discovered:
        discovered_path = rom_path.parent.parent / "mesen2_integration" / "discovered_sprite_offsets.txt"
        discovered = _parse_discovered_offsets(discovered_path, min_score=min_score)
        known_offsets = {offset for offset, _ in TileHashDatabase.KNOWN_SPRITE_OFFSETS}
        additional_offsets = [(offset, desc) for offset, desc in discovered if offset not in known_offsets]
    mapper.build_database(additional_offsets=additional_offsets)
    return mapper


def _iter_capture_files(paths: list[Path]) -> list[Path]:
    if not paths:
        return [Path("mesen2_exchange") / "test_capture.json"]

    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*capture*.json")))
        else:
            files.append(path)
    return files


def _analyze_capture(path: Path, mapper: CaptureToROMMapper | None, top: int) -> None:
    parser = MesenCaptureParser()
    capture = parser.parse_file(path)

    total_tiles = 0
    low_info_tiles = 0
    odd_nonzero_tiles = 0
    unique_buckets: Counter[str] = Counter()
    tile_stats: list[tuple[int, int, int, int, str]] = []

    for entry in capture.entries:
        for tile in entry.tiles:
            tile_bytes = tile.data_bytes
            unique_count = len(set(tile_bytes))
            total_tiles += 1
            if unique_count <= LOW_INFO_UNIQUE_BYTES:
                low_info_tiles += 1
            if any(tile_bytes[i] != 0 for i in range(1, len(tile_bytes), 2)):
                odd_nonzero_tiles += 1
            unique_buckets[_bucket_unique_count(unique_count)] += 1
            tile_stats.append((unique_count, entry.id, tile.tile_index, tile.vram_addr, tile.data_hex))

    print(f"\nCapture: {path}")
    print(f"  Entries: {len(capture.entries)}")
    print(f"  Tiles: {total_tiles}")
    print(f"  Low-info tiles (<= {LOW_INFO_UNIQUE_BYTES} unique bytes): {low_info_tiles}")
    print(f"  Odd-byte nonzero tiles: {odd_nonzero_tiles}/{total_tiles}")

    if total_tiles:
        print("  Unique-byte distribution:")
        for bucket in ("0-2", "3-4", "5-7", "8-15", "16+"):
            if bucket in unique_buckets:
                print(f"    {bucket}: {unique_buckets[bucket]}")

    if tile_stats:
        tile_stats.sort(key=lambda t: (-t[0], t[1], t[2]))
        print(f"  Top {min(top, len(tile_stats))} tiles by unique bytes:")
        for unique_count, entry_id, tile_index, vram_addr, data_hex in tile_stats[:top]:
            print(
                f"    entry {entry_id:03d} tile {tile_index:03d} "
                f"vram=0x{vram_addr:04X} unique={unique_count:02d} "
                f"data={data_hex[:16]}..."
            )

    if mapper:
        result = mapper.map_capture(capture)
        primary = result.primary_rom_offset
        primary_str = f"0x{primary:06X}" if primary is not None else "none"
        print("  Mapper summary:")
        print(
            f"    Tiles with hash hits: {result.matched_tiles}/{result.total_tiles} "
            f"(scored: {result.scored_tiles}/{result.total_tiles})"
        )
        print(f"    Primary offset: {primary_str} (score {result.primary_rom_offset_score:.2f})")
        if result.ambiguous and result.ambiguity_note:
            print(f"    Ambiguous: {result.ambiguity_note}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze capture quality and entropy before DB expansion.")
    parser.add_argument("paths", nargs="*", help="Capture file(s) or directories")
    parser.add_argument("--rom", help="Path to ROM file (optional, enables mapping)")
    parser.add_argument("--database", help="Path to tile hash database JSON")
    parser.add_argument("--use-discovered", action="store_true", help="Include discovered offsets when building DB")
    parser.add_argument("--min-score", type=float, default=0.95, help="Min score for discovered offsets")
    parser.add_argument("--top", type=int, default=10, help="Number of top-entropy tiles to display")
    args = parser.parse_args()

    setup_logging(log_level="WARNING")

    rom_path = Path(args.rom) if args.rom else None
    database_path = Path(args.database) if args.database else None
    if database_path and not database_path.exists():
        print(f"WARNING: database not found at {database_path}; will rebuild if ROM is provided.")

    mapper = _build_mapper(rom_path, database_path, args.use_discovered, args.min_score)

    files = _iter_capture_files([Path(p) for p in args.paths])
    if not files:
        print("No captures found.")
        return 1

    for path in files:
        if not path.exists():
            print(f"WARNING: capture not found: {path}")
            continue
        _analyze_capture(path, mapper, args.top)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
