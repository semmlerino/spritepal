#!/usr/bin/env python3
"""
Summarize WRAM↔VRAM tile overlap across capture runs.

Example:
  python3 scripts/summarize_wram_overlaps.py mesen2_exchange/movie_probe_run10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mesen_integration import MesenCaptureParser
from core.mesen_integration.capture_to_rom_mapper import LOW_INFO_UNIQUE_BYTES
from core.mesen_integration.tile_hash_database import BYTES_PER_TILE
from utils.logging_config import setup_logging


@dataclass(frozen=True)
class WramDump:
    path: Path
    frame_id: int
    source_frame: int
    label: str
    start: int
    size: int


def _hash_tile(tile_data: bytes) -> str:
    return hashlib.md5(tile_data).hexdigest()


def _unique_count(tile_data: bytes) -> int:
    return len(set(tile_data))


def _iter_capture_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*capture*.json")))
        elif path.is_file():
            files.append(path)
    return files


def _parse_wram_dumps(directory: Path) -> dict[int, list[WramDump]]:
    pattern = re.compile(
        r"wram_dump_(\d+)_([^_]+)(?:_f(\d+))?_start_([0-9A-Fa-f]+)_size_([0-9A-Fa-f]+)\.bin$"
    )
    by_source_frame: dict[int, list[WramDump]] = {}
    for path in directory.glob("wram_dump_*.bin"):
        match = pattern.match(path.name)
        if not match:
            continue
        frame_id = int(match.group(1))
        label = match.group(2)
        source_frame = int(match.group(3)) if match.group(3) else frame_id
        start = int(match.group(4), 16)
        size = int(match.group(5), 16)
        dump = WramDump(path=path, frame_id=frame_id, source_frame=source_frame, label=label, start=start, size=size)
        by_source_frame.setdefault(source_frame, []).append(dump)
    return by_source_frame


def _load_capture_tiles(capture_path: Path) -> tuple[int, list[bytes], list[int]]:
    parser = MesenCaptureParser()
    capture = parser.parse_file(capture_path)
    vram_tiles: list[bytes] = []
    high_info_idx: list[int] = []
    for entry in capture.entries:
        for tile in entry.tiles:
            vram_tiles.append(tile.data_bytes)
    for idx, tile in enumerate(vram_tiles):
        if _unique_count(tile) > LOW_INFO_UNIQUE_BYTES:
            high_info_idx.append(idx)
    return capture.frame, vram_tiles, high_info_idx


def _load_wram_hashes(path: Path) -> tuple[set[str], int]:
    data = path.read_bytes()
    tile_count = len(data) // BYTES_PER_TILE
    hashes = set()
    for i in range(tile_count):
        tile = data[i * BYTES_PER_TILE : (i + 1) * BYTES_PER_TILE]
        hashes.add(_hash_tile(tile))
    return hashes, tile_count


def _format_ratio(value: int, total: int) -> str:
    if total == 0:
        return "0/0"
    return f"{value}/{total} ({value / total:.1%})"


def _summarize_capture(
    capture_path: Path,
    wram_candidates: list[WramDump],
    wram_cache: dict[Path, tuple[set[str], int]],
) -> dict[str, object]:
    frame, vram_tiles, high_info_idx = _load_capture_tiles(capture_path)
    vram_hashes = [_hash_tile(tile) for tile in vram_tiles]
    vram_hash_set = set(vram_hashes)
    best = None

    for dump in wram_candidates:
        if dump.path not in wram_cache:
            wram_cache[dump.path] = _load_wram_hashes(dump.path)
        wram_hash_set, wram_tile_count = wram_cache[dump.path]
        total_hits = sum(1 for h in vram_hashes if h in wram_hash_set)
        high_hits = sum(1 for idx in high_info_idx if vram_hashes[idx] in wram_hash_set)
        unique_overlap = len(vram_hash_set & wram_hash_set)
        summary = {
            "frame": frame,
            "capture": capture_path,
            "wram": dump.path,
            "label": dump.label,
            "source_frame": dump.source_frame,
            "start": dump.start,
            "size": dump.size,
            "vram_tiles": len(vram_tiles),
            "high_info_tiles": len(high_info_idx),
            "wram_tiles": wram_tile_count,
            "total_hits": total_hits,
            "high_hits": high_hits,
            "unique_overlap": unique_overlap,
        }
        if not best or high_hits > best["high_hits"]:
            best = summary

    if best is None:
        return {
            "frame": frame,
            "capture": capture_path,
            "wram": None,
            "label": None,
            "source_frame": None,
            "start": None,
            "size": None,
            "vram_tiles": len(vram_tiles),
            "high_info_tiles": len(high_info_idx),
            "wram_tiles": 0,
            "total_hits": 0,
            "high_hits": 0,
            "unique_overlap": 0,
        }
    return best


def _print_summary(summary: dict[str, object]) -> None:
    high_ratio = _format_ratio(int(summary["high_hits"]), int(summary["high_info_tiles"]))
    total_ratio = _format_ratio(int(summary["total_hits"]), int(summary["vram_tiles"]))
    wram_path = summary["wram"]
    wram_label = summary["label"] or "-"
    wram_start = summary["start"]
    wram_start_str = f"0x{wram_start:06X}" if isinstance(wram_start, int) else "-"
    wram_size = summary["size"]
    wram_size_str = f"0x{wram_size:05X}" if isinstance(wram_size, int) else "-"
    wram_name = wram_path.name if isinstance(wram_path, Path) else "none"
    print(
        f"frame={summary['frame']} high={high_ratio} total={total_ratio} "
        f"wram={wram_name} label={wram_label} start={wram_start_str} size={wram_size_str}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize WRAM↔VRAM overlap for capture runs.")
    parser.add_argument("paths", nargs="*", help="Run directories or capture files")
    parser.add_argument("--top", type=int, default=10, help="Show top N frames by high-info hits")
    parser.add_argument("--min-high-ratio", type=float, default=0.0, help="Filter by high-info hit ratio")
    parser.add_argument("--json-out", type=Path, help="Write JSON summary to file")
    parser.add_argument("--top-only", action="store_true", help="Only show top-ranked frames")
    args = parser.parse_args()

    setup_logging(log_level="WARNING")

    input_paths = [Path(p) for p in args.paths] if args.paths else [Path("mesen2_exchange")]
    capture_files = _iter_capture_files(input_paths)
    if not capture_files:
        print("No capture files found.")
        return 1

    summaries: list[dict[str, object]] = []
    wram_cache: dict[Path, tuple[set[str], int]] = {}
    wram_index_cache: dict[Path, dict[int, list[WramDump]]] = {}

    for capture_path in capture_files:
        wram_dir = capture_path.parent
        if wram_dir not in wram_index_cache:
            wram_index_cache[wram_dir] = _parse_wram_dumps(wram_dir)
        wram_by_source = wram_index_cache[wram_dir]

        try:
            frame, _, _ = _load_capture_tiles(capture_path)
        except json.JSONDecodeError as exc:
            print(f"Skipping {capture_path}: invalid JSON ({exc})")
            continue

        candidates = wram_by_source.get(frame, [])
        summary = _summarize_capture(capture_path, candidates, wram_cache)
        summaries.append(summary)

    if args.json_out:
        args.json_out.write_text(json.dumps(summaries, indent=2), encoding="utf-8")

    if not args.top_only:
        print("Per-capture summary:")
        for summary in summaries:
            _print_summary(summary)

    ranked = sorted(
        summaries,
        key=lambda s: (s["high_hits"], s["total_hits"]),
        reverse=True,
    )
    print("\nTop frames by high-info overlap:")
    shown = 0
    for summary in ranked:
        high_info = int(summary["high_info_tiles"])
        if high_info == 0:
            continue
        ratio = summary["high_hits"] / high_info if high_info else 0.0
        if ratio < args.min_high_ratio:
            continue
        _print_summary(summary)
        shown += 1
        if shown >= args.top:
            break
    if shown == 0:
        print("  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
