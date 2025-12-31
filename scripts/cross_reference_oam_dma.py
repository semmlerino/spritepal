#!/usr/bin/env python3
"""
Cross-reference OAM sprite captures with SNES DMA events.

Links sprite tiles (from capture JSON) to the DMA transfers that populated
their VRAM locations. This enables tracing: sprite → VRAM → staging buffer.

Usage:
    python scripts/cross_reference_oam_dma.py \\
        --capture mesen2_exchange/sprite_capture_*.json \\
        --dma-log mesen2_exchange/sa1_hypothesis_run_*/dma_probe_log.txt

    # For captures during a specific frame range
    python scripts/cross_reference_oam_dma.py \\
        --capture mesen2_exchange/sprite_capture_1767035910.json \\
        --dma-log mesen2_exchange/sa1_hypothesis_run_122025_1720/ \\
        --frame-window 50

Output:
    - Sprite tile to staging buffer mapping
    - Coverage statistics (how many tiles have DMA matches)
    - Staging buffer usage patterns per sprite type
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# SNES_DMA_VRAM pattern (from analyze_snes_dma_staging.py)
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


@dataclass
class DMAEvent:
    """Parsed SNES_DMA_VRAM event."""

    frame: int
    run_id: str
    channel: int
    dmap: int
    src: int  # 16-bit source address
    src_bank: int  # Source bank
    size: int  # Transfer size in bytes
    vmadd: int  # VRAM word address at start

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
        """VRAM end byte address (exclusive)."""
        return self.vram_byte_start + self.size

    def contains_vram_addr(self, vram_byte_addr: int) -> bool:
        """Check if this DMA covers the given VRAM byte address."""
        return self.vram_byte_start <= vram_byte_addr < self.vram_byte_end


@dataclass
class SpriteTile:
    """A tile from a sprite capture."""

    sprite_id: int
    tile_index: int
    vram_addr: int  # Byte address in VRAM
    data_hex: str
    pos_x: int
    pos_y: int


@dataclass
class SpriteCapture:
    """Parsed sprite capture."""

    file_path: str
    timestamp: int
    frame: int
    obsel_raw: int
    visible_count: int
    tiles: list[SpriteTile] = field(default_factory=list)


@dataclass
class TileMatch:
    """Match between a sprite tile and a DMA event."""

    tile: SpriteTile
    dma: DMAEvent
    offset_in_transfer: int  # Byte offset within the DMA transfer

    @property
    def staging_addr(self) -> int:
        """Staging buffer address that corresponds to this tile."""
        return self.dma.full_src_addr + self.offset_in_transfer


@dataclass
class CrossReferenceResults:
    """Results of cross-referencing OAM captures with DMA events."""

    captures: list[SpriteCapture] = field(default_factory=list)
    dma_events: list[DMAEvent] = field(default_factory=list)
    matches: list[TileMatch] = field(default_factory=list)
    unmatched_tiles: list[SpriteTile] = field(default_factory=list)

    # Statistics
    staging_buffer_usage: Counter[int] = field(default_factory=Counter)
    vram_region_usage: Counter[int] = field(default_factory=Counter)


def parse_dma_log(log_path: Path) -> list[DMAEvent]:
    """Parse SNES_DMA_VRAM events from a log file."""
    events: list[DMAEvent] = []

    if not log_path.exists():
        return events

    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            match = SNES_DMA_VRAM_PATTERN.search(line)
            if match:
                events.append(
                    DMAEvent(
                        frame=int(match.group("frame")),
                        run_id=match.group("run_id"),
                        channel=int(match.group("channel")),
                        dmap=int(match.group("dmap"), 16),
                        src=int(match.group("src"), 16),
                        src_bank=int(match.group("src_bank"), 16),
                        size=int(match.group("size"), 16),
                        vmadd=int(match.group("vmadd"), 16),
                    )
                )

    return events


def parse_sprite_capture(capture_path: Path) -> SpriteCapture | None:
    """Parse a sprite capture JSON file."""
    try:
        with open(capture_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to parse {capture_path}: {e}", file=sys.stderr)
        return None

    capture = SpriteCapture(
        file_path=str(capture_path),
        timestamp=data.get("timestamp", 0),
        frame=data.get("frame", 0),
        obsel_raw=data.get("obsel", {}).get("raw", 0),
        visible_count=data.get("visible_count", 0),
    )

    for entry in data.get("entries", []):
        sprite_id = entry.get("id", 0)
        for tile in entry.get("tiles", []):
            capture.tiles.append(
                SpriteTile(
                    sprite_id=sprite_id,
                    tile_index=tile.get("tile_index", 0),
                    vram_addr=tile.get("vram_addr", 0),
                    data_hex=tile.get("data_hex", ""),
                    pos_x=tile.get("pos_x", 0),
                    pos_y=tile.get("pos_y", 0),
                )
            )

    return capture


def find_dma_for_tile(
    tile: SpriteTile,
    dma_events: list[DMAEvent],
    capture_frame: int,
    frame_window: int = 100,
) -> DMAEvent | None:
    """
    Find the DMA event that most likely wrote this tile's VRAM data.

    Searches backwards from the capture frame within the window.
    Returns the most recent DMA that covers the tile's VRAM address.
    """
    candidates: list[DMAEvent] = []

    for dma in dma_events:
        # Check frame window (DMA must be before or at capture frame)
        if dma.frame > capture_frame:
            continue
        if capture_frame - dma.frame > frame_window:
            continue

        # Check if DMA covers this VRAM address
        if dma.contains_vram_addr(tile.vram_addr):
            candidates.append(dma)

    if not candidates:
        return None

    # Return the most recent (highest frame number)
    return max(candidates, key=lambda d: d.frame)


def cross_reference(
    captures: list[SpriteCapture],
    dma_events: list[DMAEvent],
    frame_window: int = 100,
) -> CrossReferenceResults:
    """Cross-reference sprite captures with DMA events."""
    results = CrossReferenceResults(captures=captures, dma_events=dma_events)

    # Build frame-indexed DMA lookup for efficiency
    dma_by_frame: dict[int, list[DMAEvent]] = defaultdict(list)
    for dma in dma_events:
        dma_by_frame[dma.frame].append(dma)

    for capture in captures:
        for tile in capture.tiles:
            # Skip tiles with no data (empty/transparent)
            if tile.data_hex == "0" * 64:
                continue

            dma = find_dma_for_tile(
                tile, dma_events, capture.frame, frame_window
            )

            if dma:
                offset = tile.vram_addr - dma.vram_byte_start
                match = TileMatch(tile=tile, dma=dma, offset_in_transfer=offset)
                results.matches.append(match)

                # Track statistics
                results.staging_buffer_usage[dma.full_src_addr] += 1
                results.vram_region_usage[tile.vram_addr & 0xF800] += 1
            else:
                results.unmatched_tiles.append(tile)

    return results


def print_report(results: CrossReferenceResults) -> None:
    """Print cross-reference report."""
    print("=" * 70)
    print("OAM ↔ DMA CROSS-REFERENCE REPORT")
    print("=" * 70)
    print()

    # Summary
    total_tiles = len(results.matches) + len(results.unmatched_tiles)
    matched = len(results.matches)
    coverage = (matched / total_tiles * 100) if total_tiles > 0 else 0

    print(f"Captures analyzed: {len(results.captures)}")
    print(f"DMA events available: {len(results.dma_events)}")
    print(f"Total tiles (non-empty): {total_tiles}")
    print(f"Tiles with DMA match: {matched} ({coverage:.1f}%)")
    print(f"Tiles without match: {len(results.unmatched_tiles)}")
    print()

    if not results.matches:
        print("No matches found. Possible causes:")
        print("  - Capture frame not in DMA log frame range")
        print("  - Frame window too narrow (try --frame-window 500)")
        print("  - DMA log from different run than capture")
        return

    # Staging buffer usage
    print("=" * 70)
    print("STAGING BUFFER USAGE (tiles sourced from each buffer):")
    print("-" * 70)

    for addr, count in results.staging_buffer_usage.most_common(10):
        bank = (addr >> 16) & 0xFF
        offset = addr & 0xFFFF
        pct = (count / matched * 100) if matched > 0 else 0
        print(f"  ${bank:02X}:{offset:04X}: {count:5d} tiles ({pct:.1f}%)")
    print()

    # VRAM region usage
    print("=" * 70)
    print("VRAM REGION USAGE (2KB buckets):")
    print("-" * 70)

    for region, count in results.vram_region_usage.most_common(10):
        byte_start = region
        byte_end = region + 0x800
        pct = (count / matched * 100) if matched > 0 else 0
        print(
            f"  ${byte_start:04X}-${byte_end:04X}: {count:5d} tiles ({pct:.1f}%)"
        )
    print()

    # Sample matches
    print("=" * 70)
    print("SAMPLE MATCHES (first 10):")
    print("-" * 70)
    print(
        f"  {'Sprite':>6s} {'Tile':>4s} {'VRAM Addr':>10s} "
        f"{'DMA Frame':>9s} {'Staging Addr':>14s}"
    )

    for match in results.matches[:10]:
        staging = match.staging_addr
        staging_bank = (staging >> 16) & 0xFF
        staging_off = staging & 0xFFFF
        print(
            f"  {match.tile.sprite_id:6d} {match.tile.tile_index:4d} "
            f"${match.tile.vram_addr:08X} "
            f"{match.dma.frame:9d} "
            f"${staging_bank:02X}:{staging_off:04X}"
        )
    print()

    # Unmatched tiles sample
    if results.unmatched_tiles:
        print("=" * 70)
        print(f"UNMATCHED TILES (first 10 of {len(results.unmatched_tiles)}):")
        print("-" * 70)

        for tile in results.unmatched_tiles[:10]:
            print(
                f"  Sprite {tile.sprite_id}, Tile {tile.tile_index}, "
                f"VRAM ${tile.vram_addr:04X}"
            )
        print()

    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-reference OAM sprite captures with SNES DMA events."
    )
    parser.add_argument(
        "--capture",
        type=Path,
        nargs="+",
        required=True,
        help="Sprite capture JSON file(s)",
    )
    parser.add_argument(
        "--dma-log",
        type=Path,
        required=True,
        help="DMA probe log file or directory",
    )
    parser.add_argument(
        "--frame-window",
        type=int,
        default=100,
        help="Max frames before capture to search for DMA (default: 100)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Find DMA log
    if args.dma_log.is_dir():
        dma_log_path = args.dma_log / "dma_probe_log.txt"
    else:
        dma_log_path = args.dma_log

    print(f"Loading DMA log from {dma_log_path}...", file=sys.stderr)
    dma_events = parse_dma_log(dma_log_path)
    print(f"Loaded {len(dma_events)} DMA events", file=sys.stderr)

    # Parse captures
    captures: list[SpriteCapture] = []
    for capture_path in args.capture:
        if capture_path.is_file():
            capture = parse_sprite_capture(capture_path)
            if capture:
                captures.append(capture)
        else:
            # Glob pattern
            for f in capture_path.parent.glob(capture_path.name):
                capture = parse_sprite_capture(f)
                if capture:
                    captures.append(capture)

    print(f"Loaded {len(captures)} captures", file=sys.stderr)

    if not captures:
        print("Error: No captures loaded", file=sys.stderr)
        return 1

    # Cross-reference
    results = cross_reference(captures, dma_events, args.frame_window)

    if args.json:
        output = {
            "captures": len(results.captures),
            "dma_events": len(results.dma_events),
            "matched_tiles": len(results.matches),
            "unmatched_tiles": len(results.unmatched_tiles),
            "staging_buffers": [
                {"addr": f"0x{a:06X}", "count": c}
                for a, c in results.staging_buffer_usage.most_common(20)
            ],
            "sample_matches": [
                {
                    "sprite_id": m.tile.sprite_id,
                    "tile_index": m.tile.tile_index,
                    "vram_addr": f"0x{m.tile.vram_addr:04X}",
                    "dma_frame": m.dma.frame,
                    "staging_addr": f"0x{m.staging_addr:06X}",
                }
                for m in results.matches[:50]
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print_report(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
