"""
Timing Correlator for Sprite-to-ROM Mapping.

Correlates sprite captures with DMA events to trace tile data back to staging
buffers and ultimately to ROM locations. Uses two-stage correlation:

Stage 1: VRAM tiles → SNES DMA events
    - Match OAM tile VRAM addresses to DMA transfers
    - Identify which staging buffer provided the tile data

Stage 2: Staging buffers → ROM (future)
    - Match staging buffer content to decompressed ROM data
    - Use SA-1 character conversion for format matching

Data Flow Being Traced:
    ROM → SA-1 CCDMA → WRAM staging → SNES DMA → VRAM → OAM reference

Usage:
    from core.mesen_integration.timing_correlator import TimingCorrelator

    correlator = TimingCorrelator()
    correlator.load_dma_log("mesen2_exchange/dma_probe_log.txt")
    correlator.load_capture("mesen2_exchange/sprite_capture_*.json")

    results = correlator.correlate()
    for match in results.matches:
        print(f"Tile {match.tile_index} from staging ${match.staging_addr:06X}")
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from core.mesen_integration.address_space_bridge import (
    BankRegisters,
    CanonicalAddress,
    CanonicalRange,
    normalize_dma_source,
)

# =============================================================================
# Log Parsing
# =============================================================================

# Pattern for SNES_DMA_VRAM log line
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

# Pattern for SA1_BANKS log line
SA1_BANKS_PATTERN = re.compile(
    r"SA1_BANKS.*?"
    r"cxb=0x(?P<cxb>[0-9A-Fa-f]{2})\s+"
    r"dxb=0x(?P<dxb>[0-9A-Fa-f]{2})\s+"
    r"exb=0x(?P<exb>[0-9A-Fa-f]{2})\s+"
    r"fxb=0x(?P<fxb>[0-9A-Fa-f]{2})\s+"
    r"bmaps=0x(?P<bmaps>[0-9A-Fa-f]{2})\s+"
    r"bmap=0x(?P<bmap>[0-9A-Fa-f]{2})"
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

    def canonical_source(self) -> CanonicalAddress:
        """Get canonical address of DMA source."""
        return normalize_dma_source(self.src, self.src_bank)

    def canonical_range(self) -> CanonicalRange:
        """Get canonical range of DMA source."""
        return CanonicalRange.from_dma(self.src, self.src_bank, self.size)


@dataclass
class SpriteTile:
    """A tile from a sprite capture."""

    sprite_id: int
    tile_index: int
    vram_addr: int  # Byte address in VRAM
    data_hex: str
    pos_x: int
    pos_y: int
    capture_frame: int

    @property
    def is_empty(self) -> bool:
        """Check if tile is all zeros (transparent)."""
        return self.data_hex == "0" * 64


@dataclass
class SpriteCapture:
    """Parsed sprite capture from JSON."""

    file_path: str
    timestamp: int
    frame: int
    obsel_raw: int
    visible_count: int
    tiles: list[SpriteTile] = field(default_factory=list)


@dataclass
class TileCorrelation:
    """Correlation between a sprite tile and a DMA event."""

    tile: SpriteTile
    dma: DMAEvent
    offset_in_transfer: int  # Byte offset within the DMA transfer

    @property
    def staging_addr(self) -> int:
        """Staging buffer address that corresponds to this tile."""
        return self.dma.full_src_addr + self.offset_in_transfer

    @property
    def frame_distance(self) -> int:
        """Frames between DMA and tile capture."""
        return self.tile.capture_frame - self.dma.frame

    def canonical_staging(self) -> CanonicalAddress:
        """Get canonical address of staging location for this tile."""
        src = normalize_dma_source(self.dma.src, self.dma.src_bank)
        return CanonicalAddress(src.region, src.offset + self.offset_in_transfer)


@dataclass
class CorrelationResults:
    """Results from timing correlation."""

    captures: list[SpriteCapture] = field(default_factory=list)
    dma_events: list[DMAEvent] = field(default_factory=list)
    correlations: list[TileCorrelation] = field(default_factory=list)
    unmatched_tiles: list[SpriteTile] = field(default_factory=list)
    bank_registers: BankRegisters = field(default_factory=BankRegisters)

    # Statistics
    staging_buffer_usage: Counter[int] = field(default_factory=Counter)
    vram_region_usage: Counter[int] = field(default_factory=Counter)

    @property
    def match_rate(self) -> float:
        """Percentage of tiles that matched a DMA event."""
        total = len(self.correlations) + len(self.unmatched_tiles)
        if total == 0:
            return 0.0
        return len(self.correlations) / total * 100

    def staging_summary(self) -> dict[str, int]:
        """Summary of staging buffer usage by region."""
        from collections import defaultdict

        summary: dict[str, int] = defaultdict(int)
        for corr in self.correlations:
            canonical = corr.canonical_staging()
            summary[canonical.region] += 1
        return dict(summary)


# =============================================================================
# Timing Correlator
# =============================================================================


class TimingCorrelator:
    """
    Correlates sprite captures with DMA events for ROM tracing.

    Two-stage correlation:
    1. Match VRAM tiles to SNES DMA events by address/frame
    2. Track staging buffer usage patterns
    """

    def __init__(self, frame_window: int = 100):
        """
        Initialize correlator.

        Args:
            frame_window: Max frames before capture to search for DMA events
        """
        self.frame_window = frame_window
        self.dma_events: list[DMAEvent] = []
        self.captures: list[SpriteCapture] = []
        self.bank_registers = BankRegisters()

    def load_dma_log(self, log_path: str | Path) -> int:
        """
        Load DMA events from probe log.

        Args:
            log_path: Path to dma_probe_log.txt

        Returns:
            Number of DMA events loaded
        """
        log_path = Path(log_path)
        if not log_path.exists():
            return 0

        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                # Parse bank registers (use last seen)
                bank_match = SA1_BANKS_PATTERN.search(line)
                if bank_match:
                    self.bank_registers = BankRegisters(
                        cxb=int(bank_match.group("cxb"), 16),
                        dxb=int(bank_match.group("dxb"), 16),
                        exb=int(bank_match.group("exb"), 16),
                        fxb=int(bank_match.group("fxb"), 16),
                        bmaps=int(bank_match.group("bmaps"), 16),
                        bmap=int(bank_match.group("bmap"), 16),
                    )

                # Parse DMA events
                dma_match = SNES_DMA_VRAM_PATTERN.search(line)
                if dma_match:
                    self.dma_events.append(
                        DMAEvent(
                            frame=int(dma_match.group("frame")),
                            run_id=dma_match.group("run_id"),
                            channel=int(dma_match.group("channel")),
                            dmap=int(dma_match.group("dmap"), 16),
                            src=int(dma_match.group("src"), 16),
                            src_bank=int(dma_match.group("src_bank"), 16),
                            size=int(dma_match.group("size"), 16),
                            vmadd=int(dma_match.group("vmadd"), 16),
                        )
                    )

        return len(self.dma_events)

    def load_capture(self, capture_path: str | Path) -> int:
        """
        Load sprite capture from JSON file.

        Args:
            capture_path: Path to sprite_capture_*.json

        Returns:
            Number of tiles loaded
        """
        capture_path = Path(capture_path)
        if not capture_path.exists():
            return 0

        try:
            with open(capture_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return 0

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
                        capture_frame=capture.frame,
                    )
                )

        self.captures.append(capture)
        return len(capture.tiles)

    def load_captures_glob(self, pattern: str | Path) -> int:
        """
        Load multiple captures matching a glob pattern.

        Args:
            pattern: Glob pattern like "mesen2_exchange/sprite_capture_*.json"

        Returns:
            Total number of tiles loaded
        """
        pattern = Path(pattern)
        total = 0
        for path in sorted(pattern.parent.glob(pattern.name)):
            total += self.load_capture(path)
        return total

    def find_dma_for_tile(self, tile: SpriteTile) -> DMAEvent | None:
        """
        Find the DMA event that most likely wrote this tile's VRAM data.

        Searches backwards from the capture frame within the window.
        Returns the most recent DMA that covers the tile's VRAM address.
        """
        candidates: list[DMAEvent] = []

        for dma in self.dma_events:
            # DMA must be before or at capture frame
            if dma.frame > tile.capture_frame:
                continue
            # Check frame window
            if tile.capture_frame - dma.frame > self.frame_window:
                continue
            # Check if DMA covers this VRAM address
            if dma.contains_vram_addr(tile.vram_addr):
                candidates.append(dma)

        if not candidates:
            return None

        # Return the most recent (highest frame number)
        return max(candidates, key=lambda d: d.frame)

    def correlate(self) -> CorrelationResults:
        """
        Perform correlation between captures and DMA events.

        Returns:
            CorrelationResults with matches and statistics
        """
        results = CorrelationResults(
            captures=self.captures,
            dma_events=self.dma_events,
            bank_registers=self.bank_registers,
        )

        for capture in self.captures:
            for tile in capture.tiles:
                # Skip empty tiles
                if tile.is_empty:
                    continue

                dma = self.find_dma_for_tile(tile)
                if dma:
                    offset = tile.vram_addr - dma.vram_byte_start
                    correlation = TileCorrelation(
                        tile=tile,
                        dma=dma,
                        offset_in_transfer=offset,
                    )
                    results.correlations.append(correlation)

                    # Track statistics
                    results.staging_buffer_usage[dma.full_src_addr] += 1
                    results.vram_region_usage[tile.vram_addr & 0xF800] += 1
                else:
                    results.unmatched_tiles.append(tile)

        return results

    def iter_staging_buffers(self) -> Iterator[tuple[int, list[TileCorrelation]]]:
        """
        Group correlations by staging buffer address.

        Yields:
            (staging_addr, list of correlations from that buffer)
        """
        from collections import defaultdict

        by_buffer: dict[int, list[TileCorrelation]] = defaultdict(list)

        results = self.correlate()
        for corr in results.correlations:
            by_buffer[corr.dma.full_src_addr].append(corr)

        for addr in sorted(by_buffer.keys()):
            yield addr, by_buffer[addr]


# =============================================================================
# Report Generation
# =============================================================================


def format_correlation_report(results: CorrelationResults) -> str:
    """Generate a human-readable correlation report string."""
    lines: list[str] = []

    lines.append("=" * 70)
    lines.append("TIMING CORRELATION REPORT")
    lines.append("=" * 70)
    lines.append("")

    # Summary
    total_tiles = len(results.correlations) + len(results.unmatched_tiles)
    matched = len(results.correlations)

    lines.append(f"Captures analyzed: {len(results.captures)}")
    lines.append(f"DMA events available: {len(results.dma_events)}")
    lines.append(f"Total tiles (non-empty): {total_tiles}")
    lines.append(f"Tiles correlated: {matched} ({results.match_rate:.1f}%)")
    lines.append(f"Tiles without match: {len(results.unmatched_tiles)}")
    lines.append("")

    if not results.correlations:
        lines.append("No correlations found. Possible causes:")
        lines.append("  - Capture frame not in DMA log frame range")
        lines.append("  - Frame window too narrow")
        lines.append("  - DMA log from different run than capture")
        return "\n".join(lines)

    # Staging summary by region
    staging_summary = results.staging_summary()
    lines.append("=" * 70)
    lines.append("STAGING BY REGION:")
    lines.append("-" * 70)
    for region, count in sorted(staging_summary.items(), key=lambda x: -x[1]):
        pct = count / matched * 100
        lines.append(f"  {region:10s}: {count:5d} tiles ({pct:.1f}%)")
    lines.append("")

    # Top staging buffers
    lines.append("=" * 70)
    lines.append("TOP STAGING BUFFERS:")
    lines.append("-" * 70)

    for addr, count in results.staging_buffer_usage.most_common(10):
        bank = (addr >> 16) & 0xFF
        offset = addr & 0xFFFF
        pct = count / matched * 100
        lines.append(f"  ${bank:02X}:{offset:04X}: {count:5d} tiles ({pct:.1f}%)")
    lines.append("")

    # Sample correlations
    lines.append("=" * 70)
    lines.append("SAMPLE CORRELATIONS (first 10):")
    lines.append("-" * 70)
    lines.append(
        f"  {'Sprite':>6s} {'Tile':>4s} {'VRAM Addr':>10s} "
        f"{'DMA Frame':>9s} {'Staging':>14s} {'Offset':>8s}"
    )

    for corr in results.correlations[:10]:
        staging = corr.staging_addr
        staging_bank = (staging >> 16) & 0xFF
        staging_off = staging & 0xFFFF
        lines.append(
            f"  {corr.tile.sprite_id:6d} {corr.tile.tile_index:4d} "
            f"${corr.tile.vram_addr:08X} "
            f"{corr.dma.frame:9d} "
            f"${staging_bank:02X}:{staging_off:04X} "
            f"+{corr.offset_in_transfer:5d}"
        )
    lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def generate_correlation_json(results: CorrelationResults) -> dict[str, object]:
    """Generate JSON-serializable correlation data."""
    return {
        "summary": {
            "captures": len(results.captures),
            "dma_events": len(results.dma_events),
            "matched_tiles": len(results.correlations),
            "unmatched_tiles": len(results.unmatched_tiles),
            "match_rate": results.match_rate,
        },
        "staging_by_region": results.staging_summary(),
        "top_staging_buffers": [
            {"addr": f"0x{addr:06X}", "count": count}
            for addr, count in results.staging_buffer_usage.most_common(20)
        ],
        "bank_registers": {
            "cxb": f"0x{results.bank_registers.cxb:02X}",
            "dxb": f"0x{results.bank_registers.dxb:02X}",
            "exb": f"0x{results.bank_registers.exb:02X}",
            "fxb": f"0x{results.bank_registers.fxb:02X}",
            "bmaps": f"0x{results.bank_registers.bmaps:02X}",
            "bmap": f"0x{results.bank_registers.bmap:02X}",
        },
        "correlations": [
            {
                "sprite_id": c.tile.sprite_id,
                "tile_index": c.tile.tile_index,
                "vram_addr": f"0x{c.tile.vram_addr:04X}",
                "dma_frame": c.dma.frame,
                "staging_addr": f"0x{c.staging_addr:06X}",
                "offset_in_transfer": c.offset_in_transfer,
            }
            for c in results.correlations[:100]  # Limit for size
        ],
    }
