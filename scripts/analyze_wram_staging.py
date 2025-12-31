#!/usr/bin/env python3
"""
Compare WRAM staging dumps against VRAM captures and the ROM tile DB.

Usage:
  python3 scripts/analyze_wram_staging.py --capture path/to/test_capture_104.json \
      --wram path/to/wram_dump_104_start_002000_size_8000.bin \
      --database mesen2_exchange/tile_hash_database.json \
      --rom roms/Kirby\\ Super\\ Star\\ \\(U\\)\\ \\[!\\].smc
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mesen_integration import MesenCaptureParser
from core.mesen_integration.capture_to_rom_mapper import LOW_INFO_UNIQUE_BYTES
from core.mesen_integration.tile_hash_database import BYTES_PER_TILE
from utils.logging_config import setup_logging


def _hash_tile(tile_data: bytes) -> str:
    return hashlib.md5(tile_data).hexdigest()


def _unique_count(tile_data: bytes) -> int:
    return len(set(tile_data))


def _iter_tiles_from_bytes(blob: bytes) -> list[bytes]:
    if len(blob) < BYTES_PER_TILE:
        return []
    tile_count = len(blob) // BYTES_PER_TILE
    return [blob[i * BYTES_PER_TILE : (i + 1) * BYTES_PER_TILE] for i in range(tile_count)]


def _load_db_hashes(db_path: Path) -> set[str]:
    data = json.loads(db_path.read_text(encoding="utf-8"))
    hashes: set[str] = set()
    for block in data.get("blocks", []):
        for tile_hash in block.get("hashes", []):
            hashes.add(tile_hash)
    return hashes


def _format_ratio(value: int, total: int) -> str:
    if total == 0:
        return "0/0"
    return f"{value}/{total} ({value / total:.1%})"


def _parse_wram_start(text: str | None, wram_path: Path) -> int:
    if text:
        value = text.strip()
        if value.lower().startswith("0x"):
            return int(value, 16)
        return int(value)
    match = re.search(r"start_([0-9A-Fa-f]+)", wram_path.name)
    if match:
        return int(match.group(1), 16)
    return 0


def best_alignment_overlap(wram: bytes, vram_tiles: list[bytes]) -> tuple[int, int]:
    def h32(b: bytes) -> str:
        return hashlib.md5(b).hexdigest()

    vhash = [h32(t) for t in vram_tiles]
    high = [i for i, t in enumerate(vram_tiles) if _unique_count(t) > LOW_INFO_UNIQUE_BYTES]

    best_offset = 0
    best_hits = -1
    for offset in range(BYTES_PER_TILE):
        blob = wram[offset:]
        tile_count = len(blob) // BYTES_PER_TILE
        wset = {h32(blob[i * BYTES_PER_TILE : (i + 1) * BYTES_PER_TILE]) for i in range(tile_count)}
        hits = sum(1 for i in high if vhash[i] in wset)
        if hits > best_hits:
            best_hits = hits
            best_offset = offset
    return best_offset, max(best_hits, 0)


def find_high_info_tiles_anywhere(
    wram: bytes, vram_tiles: list[bytes], wram_base: int, find_all: bool = False
) -> list[tuple[int, int, int]]:
    matches: list[tuple[int, int, int]] = []
    for idx, tile in enumerate(vram_tiles):
        unique_count = _unique_count(tile)
        if unique_count <= LOW_INFO_UNIQUE_BYTES:
            continue
        if not find_all:
            pos = wram.find(tile)
            if pos != -1:
                matches.append((idx, unique_count, wram_base + pos))
            continue
        start = 0
        while True:
            pos = wram.find(tile, start)
            if pos == -1:
                break
            matches.append((idx, unique_count, wram_base + pos))
            start = pos + 1
    return matches


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare WRAM staging dumps to VRAM capture tiles and ROM DB hashes."
    )
    parser.add_argument("--capture", required=True, type=Path, help="Path to test_capture_*.json")
    parser.add_argument("--wram", required=True, type=Path, help="Path to wram_dump_*.bin")
    parser.add_argument("--database", type=Path, help="Path to tile_hash_database.json")
    parser.add_argument("--rom", type=Path, help="Path to ROM (for reporting only)")
    parser.add_argument("--wram-start", help="WRAM start offset for reporting (default: parse filename)")
    parser.add_argument("--top", type=int, default=10, help="Top unmatched VRAM tiles to show")
    parser.add_argument("--max-substring", type=int, default=10, help="Max substring matches to print")
    parser.add_argument(
        "--emit-range",
        action="store_true",
        help="Print a suggested WRAM watch range based on substring matches",
    )
    parser.add_argument(
        "--range-pad",
        type=lambda value: int(value, 0),
        default=0,
        help="Pad bytes around suggested WRAM range (default: 0)",
    )
    parser.add_argument(
        "--range-align",
        action="store_true",
        help="Align suggested WRAM range to 32-byte boundaries",
    )
    args = parser.parse_args()

    setup_logging(log_level="WARNING")

    capture_path = args.capture
    wram_path = args.wram
    db_path = args.database

    if not capture_path.exists():
        raise SystemExit(f"Capture not found: {capture_path}")
    if not wram_path.exists():
        raise SystemExit(f"WRAM dump not found: {wram_path}")
    if db_path and not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    parser_instance = MesenCaptureParser()
    capture = parser_instance.parse_file(capture_path)
    vram_tiles: list[bytes] = []
    vram_tile_meta: list[tuple[int, object]] = []
    for entry_idx, entry in enumerate(capture.entries):
        for tile in entry.tiles:
            vram_tiles.append(tile.data_bytes)
            vram_tile_meta.append((entry_idx, tile))

    wram_data = wram_path.read_bytes()
    if len(wram_data) % BYTES_PER_TILE != 0:
        remainder = len(wram_data) % BYTES_PER_TILE
        print(f"WARNING: WRAM dump size not aligned ({len(wram_data)} bytes, remainder {remainder})")
    wram_tiles = _iter_tiles_from_bytes(wram_data)

    wram_start_value = _parse_wram_start(args.wram_start, wram_path)

    vram_hashes = [_hash_tile(tile) for tile in vram_tiles]
    wram_hashes = [_hash_tile(tile) for tile in wram_tiles]
    vram_hash_set = set(vram_hashes)
    wram_hash_set = set(wram_hashes)

    db_hashes: set[str] | None = None
    if db_path:
        db_hashes = _load_db_hashes(db_path)

    vram_low_info = [
        idx for idx, tile in enumerate(vram_tiles) if _unique_count(tile) <= LOW_INFO_UNIQUE_BYTES
    ]
    vram_high_info = [idx for idx in range(len(vram_tiles)) if idx not in set(vram_low_info)]

    vram_hits_in_wram = sum(1 for h in vram_hashes if h in wram_hash_set)
    vram_high_hits_in_wram = sum(1 for idx in vram_high_info if vram_hashes[idx] in wram_hash_set)
    vram_unique_overlap = len(vram_hash_set & wram_hash_set)

    print(f"Capture: {capture_path}")
    print(f"WRAM dump: {wram_path}")
    if args.rom:
        print(f"ROM: {args.rom}")
    if db_path:
        print(f"DB: {db_path}")
    print()
    print(f"VRAM tiles: {len(vram_tiles)} (low-info {len(vram_low_info)}, high-info {len(vram_high_info)})")
    print(f"WRAM tiles: {len(wram_tiles)}")
    print(
        "VRAM tiles present in WRAM: "
        f"{_format_ratio(vram_hits_in_wram, len(vram_tiles))} "
        f"(high-info {_format_ratio(vram_high_hits_in_wram, len(vram_high_info))})"
    )
    print(f"Unique hash overlap (VRAM vs WRAM): {vram_unique_overlap}")

    if db_hashes is not None:
        vram_hits_in_db = sum(1 for h in vram_hashes if h in db_hashes)
        wram_hits_in_db = sum(1 for h in wram_hashes if h in db_hashes)
        vram_high_hits_in_db = sum(1 for idx in vram_high_info if vram_hashes[idx] in db_hashes)
        print(
            "VRAM tiles present in DB: "
            f"{_format_ratio(vram_hits_in_db, len(vram_tiles))} "
            f"(high-info {_format_ratio(vram_high_hits_in_db, len(vram_high_info))})"
        )
        print(f"WRAM tiles present in DB: {_format_ratio(wram_hits_in_db, len(wram_tiles))}")

    best_offset, best_hits = best_alignment_overlap(wram_data, vram_tiles)
    print(f"Best 32-byte alignment offset: {best_offset} (high-info hits {best_hits})")

    substring_matches = find_high_info_tiles_anywhere(wram_data, vram_tiles, wram_start_value)
    if substring_matches:
        print(f"High-info VRAM tiles found as substring in WRAM: {len(substring_matches)}")
        for tile_idx, unique_count, addr in substring_matches[: args.max_substring]:
            entry_idx, tile = vram_tile_meta[tile_idx]
            print(
                f"  entry {entry_idx:03d} tile {tile.tile_index} vram=0x{tile.vram_addr:04X} "
                f"wram=0x{addr:06X} unique={unique_count}"
            )
    else:
        print("High-info VRAM tiles found as substring in WRAM: 0")

    if args.emit_range:
        range_matches = find_high_info_tiles_anywhere(
            wram_data, vram_tiles, wram_start_value, find_all=True
        )
        if range_matches:
            min_addr = min(addr for _, _, addr in range_matches)
            max_addr = max(addr for _, _, addr in range_matches) + BYTES_PER_TILE - 1
            if args.range_pad:
                min_addr = max(0, min_addr - args.range_pad)
                max_addr = max_addr + args.range_pad
            if args.range_align:
                min_addr = (min_addr // BYTES_PER_TILE) * BYTES_PER_TILE
                max_addr = ((max_addr + BYTES_PER_TILE) // BYTES_PER_TILE) * BYTES_PER_TILE - 1
            size = max_addr - min_addr + 1
            print(
                "Suggested WRAM watch range: "
                f"start=0x{min_addr:06X} end=0x{max_addr:06X} size=0x{size:05X}"
            )
            print(f"WRAM_WATCH_START=0x{min_addr:06X} WRAM_WATCH_END=0x{max_addr:06X}")
        else:
            print("Suggested WRAM watch range: none (no substring matches)")

    unmatched = []
    for idx, tile in enumerate(vram_tiles):
        unique_count = _unique_count(tile)
        if unique_count <= LOW_INFO_UNIQUE_BYTES:
            continue
        tile_hash = vram_hashes[idx]
        in_wram = tile_hash in wram_hash_set
        in_db = db_hashes is not None and tile_hash in db_hashes
        if in_wram or in_db:
            continue
        unmatched.append((unique_count, idx, tile[:16].hex()))

    if unmatched:
        unmatched.sort(reverse=True)
        print()
        print(f"Top {min(args.top, len(unmatched))} high-info VRAM tiles not in WRAM/DB:")
        for unique_count, idx, prefix in unmatched[: args.top]:
            entry_idx, tile = vram_tile_meta[idx]
            vram_addr = f"0x{tile.vram_addr:04X}"
            tile_index = f"{tile.tile_index}"
            entry_index = f"{entry_idx:03d}"
            wram_offset = wram_start_value + (idx * BYTES_PER_TILE)
            print(
                f"  entry {entry_index} tile {tile_index} vram={vram_addr} "
                f"wram~0x{wram_offset:04X} unique={unique_count} data={prefix}..."
            )

    if not wram_tiles:
        print("WARNING: WRAM dump produced zero tiles; check WRAM_DUMP_SIZE and dump path.")


if __name__ == "__main__":
    main()
