#!/usr/bin/env python3
"""
Analyze SNES DMA staging patterns from mesen2_dma_probe.lua output.

This script processes SNES_DMA_VRAM log entries to understand how tile data
flows from staging buffers (primarily WRAM $7E:xxxx) to VRAM.

Usage:
    python scripts/analyze_snes_dma_staging.py mesen2_exchange/sa1_hypothesis_run_*/
    python scripts/analyze_snes_dma_staging.py mesen2_exchange/sa1_hypothesis_run_*/dma_probe_log.txt

Output:
    - Source bank histogram (WRAM vs ROM vs other)
    - Top staging buffer addresses
    - VRAM destination patterns
    - Frame distribution of DMA activity
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# SNES_DMA_VRAM: frame=100 run=123_a3f2 ch=1 dmap=0x01 src=0x3000 src_bank=0x00 size=0x0800 vmadd=0x6000
# Note: size can be 0x10000 (5 hex digits) when DAS register wraps (0x0000 = 65536 bytes)
SNES_DMA_VRAM_PATTERN = re.compile(
    r"SNES_DMA_VRAM: "
    r"frame=(?P<frame>\d+) "
    r"run=(?P<run_id>\S+) "
    r"ch=(?P<channel>\d) "
    r"dmap=0x(?P<dmap>[0-9A-Fa-f]{2}) "
    r"src=0x(?P<src>[0-9A-Fa-f]{4}) "
    r"src_bank=0x(?P<src_bank>[0-9A-Fa-f]{2}) "
    r"size=0x(?P<size>[0-9A-Fa-f]{4,5}) "
    r"vmadd=0x(?P<vmadd>[0-9A-Fa-f]{4})"
)

# Memory region classification
MEMORY_REGIONS = {
    "WRAM": lambda bank: bank == 0x7E,
    "WRAM_EXT": lambda bank: bank == 0x7F,
    "IRAM_RANGE": lambda bank: bank == 0x00,  # Could be I-RAM at $3000-$37FF
    "ROM_LOROM": lambda bank: 0x00 <= bank <= 0x3F or 0x80 <= bank <= 0xBF,
    "ROM_HIROM": lambda bank: 0x40 <= bank <= 0x7D or 0xC0 <= bank <= 0xFF,
}


@dataclass
class DMAEntry:
    """Parsed SNES_DMA_VRAM entry."""

    frame: int
    run_id: str
    channel: int
    dmap: int
    src: int  # 16-bit source address
    src_bank: int  # Source bank
    size: int
    vmadd: int  # VRAM word address

    @property
    def full_src_addr(self) -> int:
        """24-bit source address."""
        return (self.src_bank << 16) | self.src

    @property
    def vram_byte_start(self) -> int:
        """VRAM byte address (word * 2)."""
        return self.vmadd << 1

    @property
    def vram_byte_end(self) -> int:
        """VRAM end byte address."""
        return self.vram_byte_start + self.size


@dataclass
class VRAMRegion:
    """Analysis of a VRAM region (2KB bucket)."""

    region_start: int  # VRAM word address (start of 2KB region)
    update_count: int = 0  # How many DMA transfers to this region
    unique_frames: set[int] = field(default_factory=set)
    source_buffers: Counter[int] = field(default_factory=Counter)  # 24-bit src addr
    total_bytes: int = 0

    @property
    def region_end(self) -> int:
        """End of 2KB region (word address)."""
        return self.region_start + 0x400  # 0x400 words = 2KB

    @property
    def update_frequency(self) -> float:
        """Updates per unique frame."""
        return self.update_count / len(self.unique_frames) if self.unique_frames else 0

    @property
    def is_hot(self) -> bool:
        """Region is 'hot' if updated frequently (>1x per frame on average)."""
        return self.update_frequency > 1.0


@dataclass
class AnalysisResults:
    """Analysis results for SNES DMA staging patterns."""

    log_file: str
    total_entries: int = 0
    bank_counts: Counter[int] = field(default_factory=Counter)
    src_addr_counts: Counter[int] = field(default_factory=Counter)  # Full 24-bit addr
    vram_dest_counts: Counter[int] = field(default_factory=Counter)  # vmadd
    sizes: list[int] = field(default_factory=list)
    frames: list[int] = field(default_factory=list)
    entries: list[DMAEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # VRAM coverage map: vmadd -> list of (frame, src_addr)
    vram_to_staging: dict[int, list[tuple[int, int]]] = field(default_factory=lambda: defaultdict(list))

    # VRAM region analysis (2KB buckets)
    vram_regions: dict[int, VRAMRegion] = field(default_factory=dict)


def parse_dma_entry(line: str) -> DMAEntry | None:
    """Parse a SNES_DMA_VRAM log line."""
    match = SNES_DMA_VRAM_PATTERN.search(line)
    if not match:
        return None

    return DMAEntry(
        frame=int(match.group("frame")),
        run_id=match.group("run_id"),
        channel=int(match.group("channel")),
        dmap=int(match.group("dmap"), 16),
        src=int(match.group("src"), 16),
        src_bank=int(match.group("src_bank"), 16),
        size=int(match.group("size"), 16),
        vmadd=int(match.group("vmadd"), 16),
    )


def classify_bank(bank: int) -> str:
    """Classify a memory bank."""
    if bank == 0x7E:
        return "WRAM"
    elif bank == 0x7F:
        return "WRAM_EXT"
    elif bank == 0x00:
        return "LOW_BANK"  # Could be I-RAM at $3000-$37FF or other
    elif 0xC0 <= bank <= 0xFF:
        return "ROM_HI"
    elif 0x80 <= bank <= 0xBF:
        return "ROM_MID"
    else:
        return f"OTHER_0x{bank:02X}"


def get_vram_region(vmadd: int) -> int:
    """Get the 2KB region start for a VRAM word address."""
    return vmadd & 0xFC00  # Mask to 2KB boundary (0x400 words = 2KB)


def analyze_log(log_path: Path) -> AnalysisResults:
    """Analyze a dma_probe_log.txt file for SNES DMA staging patterns."""
    results = AnalysisResults(log_file=str(log_path))

    if not log_path.exists():
        results.errors.append(f"File not found: {log_path}")
        return results

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                entry = parse_dma_entry(line)
                if entry is None:
                    continue

                results.total_entries += 1
                results.bank_counts[entry.src_bank] += 1
                results.src_addr_counts[entry.full_src_addr] += 1
                results.vram_dest_counts[entry.vmadd] += 1
                results.sizes.append(entry.size)
                results.frames.append(entry.frame)
                results.entries.append(entry)

                # Build VRAM → staging mapping
                results.vram_to_staging[entry.vmadd].append((entry.frame, entry.full_src_addr))

                # Build VRAM region analysis
                region_start = get_vram_region(entry.vmadd)
                if region_start not in results.vram_regions:
                    results.vram_regions[region_start] = VRAMRegion(region_start=region_start)
                region = results.vram_regions[region_start]
                region.update_count += 1
                region.unique_frames.add(entry.frame)
                region.source_buffers[entry.full_src_addr] += 1
                region.total_bytes += entry.size

    except OSError as e:
        results.errors.append(f"Failed to read file: {e}")

    return results


def print_report(results: AnalysisResults, verbose: bool = False) -> None:
    """Print the analysis report."""
    print("=" * 70)
    print("SNES DMA STAGING ANALYSIS")
    print("=" * 70)
    print()

    if results.errors:
        for error in results.errors:
            print(f"ERROR: {error}")
        return

    print(f"Log file: {results.log_file}")
    print(f"Total SNES_DMA_VRAM entries: {results.total_entries}")
    print()

    if results.total_entries == 0:
        print("No SNES_DMA_VRAM entries found in log.")
        return

    # Bank distribution
    print("=" * 70)
    print("SOURCE BANK DISTRIBUTION:")
    print("-" * 70)
    total = results.total_entries
    bank_by_region: dict[str, int] = defaultdict(int)

    for bank, count in sorted(results.bank_counts.items(), key=lambda x: -x[1]):
        region = classify_bank(bank)
        bank_by_region[region] += count
        pct = (count / total * 100) if total > 0 else 0
        if verbose or count >= 10:
            print(f"  ${bank:02X} ({region:8s}): {count:7d} ({pct:5.1f}%)")

    print()
    print("By region:")
    for region, count in sorted(bank_by_region.items(), key=lambda x: -x[1]):
        pct = (count / total * 100) if total > 0 else 0
        bar = "#" * int(pct / 2)
        print(f"  {region:10s}: {count:7d} ({pct:5.1f}%) {bar}")
    print()

    # Top staging addresses
    print("=" * 70)
    print("TOP STAGING ADDRESSES (24-bit):")
    print("-" * 70)
    for addr, count in results.src_addr_counts.most_common(15):
        bank = (addr >> 16) & 0xFF
        offset = addr & 0xFFFF
        pct = (count / total * 100) if total > 0 else 0
        region = classify_bank(bank)
        print(f"  ${bank:02X}:{offset:04X} ({region:8s}): {count:7d} ({pct:5.1f}%)")
    print()

    # Top VRAM destinations
    print("=" * 70)
    print("TOP VRAM DESTINATIONS (word address):")
    print("-" * 70)
    for vmadd, count in results.vram_dest_counts.most_common(15):
        byte_addr = vmadd << 1
        pct = (count / total * 100) if total > 0 else 0
        print(f"  word ${vmadd:04X} (byte ${byte_addr:04X}): {count:7d} ({pct:5.1f}%)")
    print()

    # Size statistics
    if results.sizes:
        sizes_sorted = sorted(results.sizes)
        median = statistics.median(sizes_sorted)
        p90_idx = int(len(sizes_sorted) * 0.9)
        p90 = sizes_sorted[min(p90_idx, len(sizes_sorted) - 1)]
        min_size = min(sizes_sorted)
        max_size = max(sizes_sorted)

        print("=" * 70)
        print("TRANSFER SIZE STATISTICS:")
        print("-" * 70)
        print(f"  Min:    0x{min_size:04X} ({min_size:6d} bytes)")
        print(f"  Median: 0x{int(median):04X} ({int(median):6d} bytes)")
        print(f"  P90:    0x{p90:04X} ({p90:6d} bytes)")
        print(f"  Max:    0x{max_size:04X} ({max_size:6d} bytes)")
        print()

    # Frame distribution
    if results.frames:
        min_frame = min(results.frames)
        max_frame = max(results.frames)
        unique_frames = len(set(results.frames))
        avg_per_frame = total / unique_frames if unique_frames > 0 else 0

        print("=" * 70)
        print("FRAME DISTRIBUTION:")
        print("-" * 70)
        print(f"  Frame range: {min_frame} - {max_frame}")
        print(f"  Unique frames: {unique_frames}")
        print(f"  Avg DMA/frame: {avg_per_frame:.1f}")
        print()

    # VRAM region analysis
    if results.vram_regions:
        print("=" * 70)
        print("VRAM REGION ANALYSIS (2KB buckets):")
        print("-" * 70)

        # Sort regions by update count
        sorted_regions = sorted(
            results.vram_regions.values(),
            key=lambda r: r.update_count,
            reverse=True,
        )

        # Classify regions
        hot_regions = [r for r in sorted_regions if r.is_hot]
        stable_regions = [r for r in sorted_regions if not r.is_hot]

        print(f"Total VRAM regions touched: {len(sorted_regions)}")
        print(f"Hot regions (>1 update/frame): {len(hot_regions)}")
        print(f"Stable regions: {len(stable_regions)}")
        print()

        print("Region breakdown (top 10 by updates):")
        print(
            f"  {'Region':12s} {'Updates':>8s} {'Frames':>8s} {'Freq':>6s} {'Bytes':>10s} {'Type':>6s} {'Top Source'}"
        )
        print("-" * 70)

        for region in sorted_regions[:10]:
            byte_start = region.region_start << 1
            byte_end = region.region_end << 1
            region_str = f"${byte_start:04X}-${byte_end:04X}"
            freq_str = f"{region.update_frequency:.2f}"
            type_str = "HOT" if region.is_hot else "stable"

            # Get top source buffer
            if region.source_buffers:
                top_src, top_count = region.source_buffers.most_common(1)[0]
                src_bank = (top_src >> 16) & 0xFF
                src_off = top_src & 0xFFFF
                src_str = f"${src_bank:02X}:{src_off:04X} ({top_count})"
            else:
                src_str = "N/A"

            print(
                f"  {region_str:12s} {region.update_count:8d} "
                f"{len(region.unique_frames):8d} {freq_str:>6s} "
                f"{region.total_bytes:10d} {type_str:>6s} {src_str}"
            )
        print()

        # Source-to-region mapping (which staging buffers feed which regions)
        if hot_regions:
            print("Hot region → Source buffer mapping:")
            for region in hot_regions[:5]:
                byte_start = region.region_start << 1
                print(f"  VRAM ${byte_start:04X}:")
                for src_addr, count in region.source_buffers.most_common(3):
                    src_bank = (src_addr >> 16) & 0xFF
                    src_off = src_addr & 0xFFFF
                    pct = count / region.update_count * 100
                    print(f"    ← ${src_bank:02X}:{src_off:04X} ({count:5d}, {pct:.1f}%)")
            print()

    # WRAM staging analysis
    wram_entries = [e for e in results.entries if e.src_bank == 0x7E]
    if wram_entries:
        print("=" * 70)
        print("WRAM STAGING BUFFER ANALYSIS:")
        print("-" * 70)

        # Group by source offset in WRAM
        wram_offsets: Counter[int] = Counter()
        for e in wram_entries:
            wram_offsets[e.src] += 1

        print(f"Total WRAM-sourced DMA: {len(wram_entries)}")
        print(f"Unique WRAM offsets: {len(wram_offsets)}")
        print()
        print("Top WRAM staging offsets:")
        for offset, count in wram_offsets.most_common(10):
            pct = (count / len(wram_entries) * 100) if wram_entries else 0
            print(f"  $7E:{offset:04X}: {count:7d} ({pct:5.1f}%)")
        print()

    # Correlation summary
    print("=" * 70)
    print("CORRELATION POTENTIAL:")
    print("-" * 70)

    wram_pct = (results.bank_counts.get(0x7E, 0) / total * 100) if total > 0 else 0
    low_bank_pct = (results.bank_counts.get(0x00, 0) / total * 100) if total > 0 else 0

    if wram_pct > 90:
        print(f"  ✅ WRAM staging dominant ({wram_pct:.1f}%)")
        print("  Correlation approach: Track WRAM buffer writes from SA-1")
        print()
        print("  Primary staging buffer: $7E:F382 (if matching top address)")
        print("  Strategy: Monitor SA-1 writes to WRAM, correlate with")
        print("            SNES_DMA_VRAM events by buffer address")
    elif low_bank_pct > 50:
        print(f"  📊 Low bank staging ({low_bank_pct:.1f}%)")
        print("  Likely I-RAM ($00:3000-$37FF) staging")
        print("  Strategy: Monitor SA-1 CCDMA to I-RAM, then SNES DMA to VRAM")
    else:
        print("  ⚠️ Mixed staging patterns")
        print(f"    WRAM: {wram_pct:.1f}%")
        print(f"    Low bank: {low_bank_pct:.1f}%")
        print("  Strategy: Route per-event based on source bank")

    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze SNES DMA staging patterns from dma_probe_log.txt.")
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
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show all bank entries, not just top ones",
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

        # Build JSON output
        bank_counts_str = {f"0x{k:02X}": v for k, v in results.bank_counts.items()}
        top_sources = [{"addr": f"0x{a:06X}", "count": c} for a, c in results.src_addr_counts.most_common(20)]
        top_vram = [{"vmadd": f"0x{v:04X}", "count": c} for v, c in results.vram_dest_counts.most_common(20)]

        output = {
            "log_file": results.log_file,
            "total_entries": results.total_entries,
            "bank_counts": bank_counts_str,
            "top_source_addresses": top_sources,
            "top_vram_destinations": top_vram,
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
        print_report(results, verbose=args.verbose)

    return 0 if not results.errors else 1


if __name__ == "__main__":
    sys.exit(main())
