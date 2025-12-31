#!/usr/bin/env python3
"""
Analyze CCDMA source types from mesen2_dma_probe.lua output.

Produces histogram of CCDMA source types (SS field) to determine
routing: direct path (SS=ROM) vs two-hop path (SS=BW-RAM/I-RAM).

Usage:
    python scripts/analyze_ccdma_sources.py mesen2_exchange/dma_probe_log.txt
    python scripts/analyze_ccdma_sources.py mesen2_exchange/movie_probe_run_*/

Output:
    CCDMA Source Type Histogram showing:
    - SS=0 (ROM): count and percentage
    - SS=1 (BW-RAM): count and percentage
    - SS=2 (I-RAM): count and percentage
    - Destination breakdown (I-RAM vs BW-RAM)
    - Typical transfer sizes (median, p90)
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Pattern to match CCDMA_START log lines (per Instrumentation Contract v1.1)
# CCDMA_START: frame=100 run=123_a3f2 dcnt=0xA0 cdma=0x03 ss=0 (ROM) dest_dev=0 (I-RAM) src=0x3C8000 dest=0x003000 size=0x0800
CCDMA_START_PATTERN = re.compile(
    r"CCDMA_START: "
    r"frame=(?P<frame>\d+) "
    r"run=(?P<run_id>\S+) "
    r"dcnt=0x(?P<dcnt>[0-9A-Fa-f]{2}) "
    r"cdma=0x(?P<cdma>[0-9A-Fa-f]{2}) "
    r"ss=(?P<ss>\d) "
    r"\((?P<ss_name>[^)]+)\) "
    r"dest_dev=(?P<dest_dev>\d) "
    r"\((?P<dest_name>[^)]+)\) "
    r"src=0x(?P<src>[0-9A-Fa-f]{6}) "
    r"dest=0x(?P<dest>[0-9A-Fa-f]{6}) "
    r"size=0x(?P<size>[0-9A-Fa-f]{4})"
)

SS_NAMES = {0: "ROM", 1: "BW-RAM", 2: "I-RAM", 3: "reserved"}
DEST_NAMES = {0: "I-RAM", 1: "BW-RAM"}


@dataclass
class CCDMAEntry:
    """Parsed CCDMA_START entry."""

    frame: int
    run_id: str
    dcnt: int
    cdma: int
    ss: int
    ss_name: str
    dest_dev: int
    dest_name: str
    src: int
    dest: int
    size: int


@dataclass
class AnalysisResults:
    """Analysis results for CCDMA source types."""

    log_file: str
    total_entries: int = 0
    ss_counts: Counter[int] = field(default_factory=Counter)
    dest_counts: Counter[int] = field(default_factory=Counter)
    sizes: list[int] = field(default_factory=list)
    entries: list[CCDMAEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_ccdma_entry(line: str) -> CCDMAEntry | None:
    """Parse a CCDMA_START log line."""
    match = CCDMA_START_PATTERN.search(line)
    if not match:
        return None

    return CCDMAEntry(
        frame=int(match.group("frame")),
        run_id=match.group("run_id"),
        dcnt=int(match.group("dcnt"), 16),
        cdma=int(match.group("cdma"), 16),
        ss=int(match.group("ss")),
        ss_name=match.group("ss_name"),
        dest_dev=int(match.group("dest_dev")),
        dest_name=match.group("dest_name"),
        src=int(match.group("src"), 16),
        dest=int(match.group("dest"), 16),
        size=int(match.group("size"), 16),
    )


def analyze_log(log_path: Path) -> AnalysisResults:
    """Analyze a dma_probe_log.txt file for CCDMA source types."""
    results = AnalysisResults(log_file=str(log_path))

    if not log_path.exists():
        results.errors.append(f"File not found: {log_path}")
        return results

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                entry = parse_ccdma_entry(line)
                if entry is None:
                    continue

                results.total_entries += 1
                results.ss_counts[entry.ss] += 1
                results.dest_counts[entry.dest_dev] += 1
                results.sizes.append(entry.size)
                results.entries.append(entry)

    except OSError as e:
        results.errors.append(f"Failed to read file: {e}")

    return results


def print_report(results: AnalysisResults) -> None:
    """Print the analysis report."""
    print("=" * 70)
    print("CCDMA SOURCE TYPE HISTOGRAM")
    print("=" * 70)
    print()

    if results.errors:
        for error in results.errors:
            print(f"ERROR: {error}")
        return

    print(f"Log file: {results.log_file}")
    print(f"Total CCDMA_START entries: {results.total_entries}")
    print()

    if results.total_entries == 0:
        print("No CCDMA_START entries found in log.")
        print()
        print("This could mean:")
        print("  - The log was captured before Phase 1 instrumentation")
        print("  - No SA-1 character conversion DMA occurred during capture")
        print("  - The ROM doesn't use SA-1 character conversion")
        return

    # Source type histogram
    print("SOURCE TYPE (SS) HISTOGRAM:")
    total = results.total_entries
    for ss in range(4):
        count = results.ss_counts.get(ss, 0)
        name = SS_NAMES.get(ss, "?")
        pct = (count / total * 100) if total > 0 else 0
        bar = "#" * int(pct / 2)
        print(f"  SS={ss} ({name:7s}): {count:6d} ({pct:5.1f}%) {bar}")
    print()

    # Destination histogram
    print("DESTINATION (D) HISTOGRAM:")
    for dest in range(2):
        count = results.dest_counts.get(dest, 0)
        name = DEST_NAMES.get(dest, "?")
        pct = (count / total * 100) if total > 0 else 0
        bar = "#" * int(pct / 2)
        print(f"  D={dest} ({name:7s}): {count:6d} ({pct:5.1f}%) {bar}")
    print()

    # Size statistics
    if results.sizes:
        sizes_sorted = sorted(results.sizes)
        median = statistics.median(sizes_sorted)
        p90_idx = int(len(sizes_sorted) * 0.9)
        p90 = sizes_sorted[p90_idx] if p90_idx < len(sizes_sorted) else sizes_sorted[-1]
        min_size = min(sizes_sorted)
        max_size = max(sizes_sorted)

        print("TRANSFER SIZE STATISTICS:")
        print(f"  Min:    0x{min_size:04X} ({min_size:6d} bytes)")
        print(f"  Median: 0x{int(median):04X} ({int(median):6d} bytes)")
        print(f"  P90:    0x{p90:04X} ({p90:6d} bytes)")
        print(f"  Max:    0x{max_size:04X} ({max_size:6d} bytes)")
        print()

    # Routing recommendation
    print("=" * 70)
    print("ROUTING RECOMMENDATION:")
    print()

    rom_count = results.ss_counts.get(0, 0)
    bwram_count = results.ss_counts.get(1, 0)
    iram_count = results.ss_counts.get(2, 0)
    staging_count = bwram_count + iram_count

    if total > 0:
        rom_pct = rom_count / total * 100
        staging_pct = staging_count / total * 100

        if rom_pct > 90:
            print(f"  DIRECT PATH DOMINANT: {rom_pct:.1f}% of transfers from ROM")
            print("  Proceed with Phase 2A (direct ROM → CCDMA → I-RAM → VRAM correlation)")
        elif staging_pct > 90:
            print(f"  STAGING PATH DOMINANT: {staging_pct:.1f}% of transfers from BW-RAM/I-RAM")
            print("  Proceed with Phase 2B (two-hop staging correlation)")
        else:
            print("  MIXED PATHS: Both direct and staging used")
            print(f"    Direct (ROM):      {rom_count:6d} ({rom_pct:.1f}%)")
            print(f"    Staging (BW/I-RAM): {staging_count:6d} ({staging_pct:.1f}%)")
            print()
            print("  Route events per-type using SS field:")
            print("    SS=0 → Phase 2A logic (direct)")
            print("    SS=1,2 → Phase 2B logic (staging)")

    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze CCDMA source types from dma_probe_log.txt output."
    )
    parser.add_argument(
        "target",
        type=Path,
        help="Log file or directory containing dma_probe_log.txt",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Find the log file
    if args.target.is_dir():
        log_path = args.target / "dma_probe_log.txt"
    else:
        log_path = args.target

    results = analyze_log(log_path)

    if args.json:
        import json

        output = {
            "log_file": results.log_file,
            "total_entries": results.total_entries,
            "ss_counts": dict(results.ss_counts),
            "dest_counts": dict(results.dest_counts),
            "size_stats": {},
            "errors": results.errors,
        }
        if results.sizes:
            sizes_sorted = sorted(results.sizes)
            output["size_stats"] = {
                "min": min(sizes_sorted),
                "median": int(statistics.median(sizes_sorted)),
                "p90": sizes_sorted[int(len(sizes_sorted) * 0.9)],
                "max": max(sizes_sorted),
            }
        print(json.dumps(output, indent=2))
    else:
        print_report(results)

    return 0 if not results.errors else 1


if __name__ == "__main__":
    sys.exit(main())
