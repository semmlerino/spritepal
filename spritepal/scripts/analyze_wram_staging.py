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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mesen_integration import MesenCaptureParser
from core.mesen_integration.capture_to_rom_mapper import LOW_INFO_UNIQUE_BYTES
from core.mesen_integration.tile_hash_database import BYTES_PER_TILE


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare WRAM staging dumps to VRAM capture tiles and ROM DB hashes."
    )
    parser.add_argument("--capture", required=True, type=Path, help="Path to test_capture_*.json")
    parser.add_argument("--wram", required=True, type=Path, help="Path to wram_dump_*.bin")
    parser.add_argument("--database", type=Path, help="Path to tile_hash_database.json")
    parser.add_argument("--rom", type=Path, help="Path to ROM (for reporting only)")
    parser.add_argument("--wram-start", default="0x2000", help="WRAM start offset for reporting")
    parser.add_argument("--top", type=int, default=10, help="Top unmatched VRAM tiles to show")
    args = parser.parse_args()

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

    wram_start = args.wram_start
    if isinstance(wram_start, str):
        wram_start = wram_start.strip()
        if wram_start.lower().startswith("0x"):
            wram_start_value = int(wram_start, 16)
        else:
            wram_start_value = int(wram_start)
    else:
        wram_start_value = int(wram_start)

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
