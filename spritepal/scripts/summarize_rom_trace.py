#!/usr/bin/env python3
"""
Summarize PRG-ROM reads from rom_trace_log.txt and rank top read ranges per burst.

Example:
  python3 scripts/summarize_rom_trace.py mesen2_exchange/movie_probe_run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logging_config import setup_logging

ARM_RE = re.compile(
    r"ROM trace armed: frame=(\d+)\s+label=([^\s]+)(?:\s+prg_size=([^\s]+)\s+prg_end=([^\s]+))?"
)
READ_RE = re.compile(r"ROM read \(([^)]+)\): frame=(\d+)\s+addr=0x([0-9A-Fa-f]+)")
COMPLETE_RE = re.compile(r"ROM trace (?:complete|expired|frame limit reached)\b")


@dataclass
class RomTraceBurst:
    index: int
    frame: int | None
    label: str | None
    start_line: int
    reads: list[int] = field(default_factory=list)
    first_read: int | None = None
    prg_size: int | None = None
    prg_end: int | None = None

    def add_read(self, addr: int) -> None:
        if self.first_read is None:
            self.first_read = addr
        self.reads.append(addr)

    def stats(self) -> dict[str, object]:
        if not self.reads:
            return {
                "reads": 0,
                "unique_reads": 0,
                "min_addr": None,
                "max_addr": None,
            }
        return {
            "reads": len(self.reads),
            "unique_reads": len(set(self.reads)),
            "min_addr": min(self.reads),
            "max_addr": max(self.reads),
        }

    def top_buckets(self, bucket_size: int, top_n: int) -> list[dict[str, int]]:
        if bucket_size <= 0 or not self.reads:
            return []
        buckets: dict[int, dict[str, int]] = {}
        for addr in self.reads:
            base = addr - (addr % bucket_size)
            entry = buckets.get(base)
            if entry is None:
                entry = {
                    "start": base,
                    "end": base + bucket_size - 1,
                    "count": 0,
                    "min": addr,
                    "max": addr,
                    "first": addr,
                    "addresses": set(),
                }
                buckets[base] = entry
            entry["count"] += 1
            entry["min"] = min(entry["min"], addr)
            entry["max"] = max(entry["max"], addr)
            entry["addresses"].add(addr)
        for entry in buckets.values():
            run_start, run_end, run_len = _longest_contiguous_run(entry["addresses"])
            entry["run_start"] = run_start
            entry["run_end"] = run_end
            entry["run_len_unique"] = run_len
            entry.pop("addresses", None)
        ranked = sorted(buckets.values(), key=lambda item: (-item["count"], item["start"]))
        return ranked[:top_n]


def _iter_trace_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("rom_trace_log.txt")))
        elif path.is_file():
            files.append(path)
    return files


def _parse_trace(path: Path) -> list[RomTraceBurst]:
    bursts: list[RomTraceBurst] = []
    current: RomTraceBurst | None = None
    index = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            arm_match = ARM_RE.search(line)
            if arm_match:
                if current is not None:
                    bursts.append(current)
                index += 1
                prg_size = None
                prg_end = None
                if arm_match.group(3):
                    try:
                        prg_size = int(arm_match.group(3), 16)
                    except ValueError:
                        prg_size = None
                if arm_match.group(4):
                    try:
                        prg_end = int(arm_match.group(4), 16)
                    except ValueError:
                        prg_end = None
                current = RomTraceBurst(
                    index=index,
                    frame=int(arm_match.group(1)),
                    label=arm_match.group(2),
                    start_line=line_no,
                    prg_size=prg_size,
                    prg_end=prg_end,
                )
                continue

            read_match = READ_RE.search(line)
            if read_match:
                if current is None:
                    index += 1
                    current = RomTraceBurst(index=index, frame=None, label=read_match.group(1), start_line=line_no)
                addr = int(read_match.group(3), 16)
                current.add_read(addr)
                continue

            if current and COMPLETE_RE.search(line):
                bursts.append(current)
                current = None

    if current is not None:
        bursts.append(current)
    return bursts


def _format_addr(addr: int | None) -> str:
    if addr is None:
        return "-"
    return f"0x{addr:06X}"


def _longest_contiguous_run(addresses: list[int] | set[int]) -> tuple[int | None, int | None, int]:
    if not addresses:
        return None, None, 0
    ordered = sorted(set(addresses))
    best_start = ordered[0]
    best_end = ordered[0]
    best_len = 1
    run_start = ordered[0]
    run_end = ordered[0]
    run_len = 1
    for addr in ordered[1:]:
        if addr == run_end + 1:
            run_end = addr
            run_len += 1
        else:
            if run_len > best_len:
                best_start = run_start
                best_end = run_end
                best_len = run_len
            run_start = addr
            run_end = addr
            run_len = 1
    if run_len > best_len:
        best_start = run_start
        best_end = run_end
        best_len = run_len
    return best_start, best_end, best_len


def _print_burst(burst: RomTraceBurst, bucket_size: int, top_n: int) -> None:
    stats = burst.stats()
    reads = stats["reads"]
    unique_reads = stats["unique_reads"]
    min_addr = _format_addr(stats["min_addr"])
    max_addr = _format_addr(stats["max_addr"])
    first_addr = _format_addr(burst.first_read)
    frame = burst.frame if burst.frame is not None else "-"
    label = burst.label or "-"
    prg_text = ""
    if burst.prg_size is not None or burst.prg_end is not None:
        prg_size = _format_addr(burst.prg_size)
        prg_end = _format_addr(burst.prg_end)
        prg_text = f" prg_size={prg_size} prg_end={prg_end}"
    print(
        f"burst {burst.index}: frame={frame} label={label} reads={reads} "
        f"unique={unique_reads} range={min_addr}-{max_addr} first={first_addr}{prg_text}"
    )
    for bucket in burst.top_buckets(bucket_size, top_n):
        run_start = _format_addr(bucket.get("run_start"))
        run_end = _format_addr(bucket.get("run_end"))
        run_len = bucket.get("run_len_unique", 0)
        print(
            f"  0x{bucket['start']:06X}-0x{bucket['end']:06X}: {bucket['count']} "
            f"(first=0x{bucket['first']:06X}, min=0x{bucket['min']:06X}, max=0x{bucket['max']:06X}, "
            f"run={run_start}-{run_end}, unique_len={run_len})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize rom_trace_log.txt into top ROM read ranges.")
    parser.add_argument("paths", nargs="*", help="Run directories or rom_trace_log.txt files")
    parser.add_argument("--bucket-size", default="0x1000", help="Bucket size in bytes (hex ok); for ranking only")
    parser.add_argument("--top", type=int, default=5, help="Top N buckets per burst")
    parser.add_argument("--min-reads", type=int, default=1, help="Skip bursts with fewer reads")
    parser.add_argument("--json-out", type=Path, help="Write summary JSON to file")
    args = parser.parse_args()

    setup_logging(log_level="WARNING")

    try:
        bucket_size = int(str(args.bucket_size), 0)
    except ValueError:
        print(f"Invalid --bucket-size: {args.bucket_size}")
        return 1

    input_paths = [Path(p) for p in args.paths] if args.paths else [Path("mesen2_exchange")]
    trace_files = _iter_trace_files(input_paths)
    if not trace_files:
        print("No rom_trace_log.txt files found.")
        return 1

    json_summary: list[dict[str, object]] = []

    for trace_path in trace_files:
        bursts = _parse_trace(trace_path)
        print(f"\n{trace_path} ({len(bursts)} bursts)")
        for burst in bursts:
            if len(burst.reads) < args.min_reads:
                continue
            _print_burst(burst, bucket_size, args.top)
        for burst in bursts:
            stats = burst.stats()
            json_summary.append(
                {
                    "trace_file": str(trace_path),
                    "burst_index": burst.index,
                    "frame": burst.frame,
                    "label": burst.label,
                    "reads": stats["reads"],
                    "unique_reads": stats["unique_reads"],
                    "min_addr": stats["min_addr"],
                    "max_addr": stats["max_addr"],
                    "first_read": burst.first_read,
                    "prg_size": burst.prg_size,
                    "prg_end": burst.prg_end,
                    "top_buckets": [
                        {
                            "start": bucket["start"],
                            "end": bucket["end"],
                            "count": bucket["count"],
                            "first_read": bucket["first"],
                            "min_addr": bucket["min"],
                            "max_addr": bucket["max"],
                            "run_start": bucket.get("run_start"),
                            "run_end": bucket.get("run_end"),
                            "run_len_unique": bucket.get("run_len_unique"),
                        }
                        for bucket in burst.top_buckets(bucket_size, args.top)
                    ],
                }
            )

    if args.json_out:
        args.json_out.write_text(json.dumps(json_summary, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
