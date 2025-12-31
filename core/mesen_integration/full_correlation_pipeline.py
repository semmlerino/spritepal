"""
Full Correlation Pipeline: VRAM → Staging → ROM.

Combines timing correlation and ROM tile matching to trace
captured sprites back to their ROM offsets.

Pipeline stages:
    1. Load DMA log and sprite captures
    2. Correlate VRAM tiles → DMA events → staging buffers
    3. Match VRAM tile data → ROM offsets (via SA-1 conversion)
    4. Cross-validate: do correlated staging patterns match ROM regions?

Usage:
    from core.mesen_integration.full_correlation_pipeline import CorrelationPipeline

    pipeline = CorrelationPipeline(
        rom_path="roms/Kirby Super Star (USA).sfc",
        dma_log_path="mesen2_exchange/dma_probe_log.txt",
    )
    pipeline.load_captures("mesen2_exchange/sprite_capture_*.json")
    results = pipeline.run()

    for match in results.rom_matches:
        print(f"Sprite {match.sprite_id} → ROM ${match.rom_offset:06X}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from core.mesen_integration.rom_tile_matcher import ROMTileMatcher
from core.mesen_integration.timing_correlator import (
    CorrelationResults,
    TileCorrelation,
    TimingCorrelator,
)

logger = logging.getLogger(__name__)


@dataclass
class ROMMatch:
    """A sprite tile matched to a ROM location."""

    # From timing correlation
    sprite_id: int
    tile_index: int
    vram_addr: int
    staging_addr: int
    dma_frame: int

    # From ROM matching
    rom_offset: int
    rom_tile_index: int
    rom_description: str
    flip_variant: str = ""

    @property
    def full_rom_offset(self) -> int:
        """ROM offset including tile byte offset."""
        return self.rom_offset + (self.rom_tile_index * 32)


@dataclass
class PipelineResults:
    """Results from the full correlation pipeline."""

    # Timing correlation
    timing_results: CorrelationResults

    # ROM matching
    rom_matches: list[ROMMatch] = field(default_factory=list)
    unmatched_tiles: list[TileCorrelation] = field(default_factory=list)

    # Statistics
    rom_match_rate: float = 0.0
    staging_to_rom_mapping: dict[int, set[int]] = field(default_factory=dict)

    def get_summary(self) -> dict[str, object]:
        """Get summary statistics."""
        total_correlated = len(self.timing_results.correlations)
        matched = len(self.rom_matches)

        return {
            "captures": len(self.timing_results.captures),
            "dma_events": len(self.timing_results.dma_events),
            "tiles_correlated": total_correlated,
            "tiles_rom_matched": matched,
            "rom_match_rate": f"{self.rom_match_rate:.1f}%",
            "unique_rom_offsets": len({m.rom_offset for m in self.rom_matches}),
            "staging_buffers_mapped": len(self.staging_to_rom_mapping),
        }


class CorrelationPipeline:
    """
    Full correlation pipeline from VRAM capture to ROM offset.

    Combines TimingCorrelator (VRAM → staging) with ROMTileMatcher
    (tile data → ROM) to provide complete sprite tracing.
    """

    def __init__(
        self,
        rom_path: str | Path,
        dma_log_path: str | Path | None = None,
        frame_window: int = 100,
        apply_sa1_conversion: bool = True,
    ):
        """
        Initialize correlation pipeline.

        Args:
            rom_path: Path to ROM file
            dma_log_path: Path to DMA probe log
            frame_window: Max frames to search for DMA events
            apply_sa1_conversion: Apply SA-1 bitmap→SNES conversion
        """
        self.rom_path = Path(rom_path)

        # Initialize components
        self._timing = TimingCorrelator(frame_window=frame_window)
        self._matcher = ROMTileMatcher(
            rom_path=rom_path,
            apply_sa1_conversion=apply_sa1_conversion,
        )

        # Load DMA log if provided
        if dma_log_path:
            self.load_dma_log(dma_log_path)

        self._database_built = False

    def load_dma_log(self, log_path: str | Path) -> int:
        """Load DMA events from log file."""
        log_path = Path(log_path)
        if log_path.is_dir():
            log_path = log_path / "dma_probe_log.txt"

        count = self._timing.load_dma_log(log_path)
        logger.info(f"Loaded {count} DMA events from {log_path}")
        return count

    def load_capture(self, capture_path: str | Path) -> int:
        """Load a sprite capture file."""
        return self._timing.load_capture(capture_path)

    def load_captures(self, pattern: str | Path) -> int:
        """Load captures matching a glob pattern."""
        return self._timing.load_captures_glob(pattern)

    def build_database(
        self,
        additional_offsets: list[tuple[int, str]] | None = None,
        scan_rom: bool = False,
        scan_step: int = 0x400,
        scan_min_tiles: int = 8,
        build_two_plane: bool = False,
        two_plane_step: int = 16,
        progress_callback: object | None = None,
    ) -> int:
        """
        Build ROM tile database.

        Args:
            additional_offsets: Extra (offset, description) pairs to scan
            scan_rom: If True, scan entire ROM for HAL blocks (comprehensive but slow)
            scan_step: Step size for scanning (default: 1KB)
            scan_min_tiles: Minimum tiles per block (default: 8)
            build_two_plane: If True, also build two-plane index from raw ROM
            two_plane_step: Step size for two-plane scanning (default: 16 bytes)
            progress_callback: Optional callback(current, total)

        Must be called before run() or will be called automatically.
        """
        count = self._matcher.build_database(
            additional_offsets=additional_offsets,
            scan_rom=scan_rom,
            scan_step=scan_step,
            scan_min_tiles=scan_min_tiles,
            build_two_plane=build_two_plane,
            two_plane_step=two_plane_step,
            progress_callback=progress_callback,
        )
        self._database_built = True
        return count

    def run(self) -> PipelineResults:
        """
        Run the full correlation pipeline.

        Returns:
            PipelineResults with matches and statistics
        """
        # Build database if not done
        if not self._database_built:
            logger.info("Building ROM tile database...")
            self.build_database()

        # Stage 1: Timing correlation (VRAM → staging)
        logger.info("Running timing correlation...")
        timing_results = self._timing.correlate()
        logger.info(
            f"Timing correlation: {len(timing_results.correlations)} tiles "
            f"({timing_results.match_rate:.1f}% match rate)"
        )

        # Stage 2: ROM matching (tile data → ROM offset)
        logger.info("Matching tiles to ROM...")
        results = PipelineResults(timing_results=timing_results)

        for corr in timing_results.correlations:
            # Get tile data from capture
            tile_data = bytes.fromhex(corr.tile.data_hex)

            if len(tile_data) != 32:
                results.unmatched_tiles.append(corr)
                continue

            # Look up in ROM database
            rom_matches = self._matcher.lookup_vram_tile(tile_data)

            if rom_matches:
                # Use best match (first, sorted by ROM offset)
                best = rom_matches[0]
                results.rom_matches.append(
                    ROMMatch(
                        sprite_id=corr.tile.sprite_id,
                        tile_index=corr.tile.tile_index,
                        vram_addr=corr.tile.vram_addr,
                        staging_addr=corr.staging_addr,
                        dma_frame=corr.dma.frame,
                        rom_offset=best.rom_offset,
                        rom_tile_index=best.tile_index,
                        rom_description=best.description,
                        flip_variant=best.flip_variant,
                    )
                )

                # Track staging → ROM mapping
                results.staging_to_rom_mapping.setdefault(
                    corr.staging_addr, set()
                ).add(best.rom_offset)
            else:
                results.unmatched_tiles.append(corr)

        # Calculate statistics
        total = len(timing_results.correlations)
        matched = len(results.rom_matches)
        results.rom_match_rate = (matched / total * 100) if total > 0 else 0

        logger.info(
            f"ROM matching: {matched}/{total} tiles "
            f"({results.rom_match_rate:.1f}% match rate)"
        )

        return results

    def get_database_stats(self) -> dict[str, object]:
        """Get ROM database statistics."""
        return self._matcher.get_statistics()


def format_pipeline_report(results: PipelineResults) -> str:
    """Generate human-readable pipeline report."""
    lines: list[str] = []

    lines.append("=" * 70)
    lines.append("FULL CORRELATION PIPELINE REPORT")
    lines.append("=" * 70)
    lines.append("")

    # Summary
    summary = results.get_summary()
    lines.append("SUMMARY:")
    lines.append("-" * 70)
    for key, value in summary.items():
        lines.append(f"  {key}: {value}")
    lines.append("")

    # ROM offset distribution
    if results.rom_matches:
        lines.append("=" * 70)
        lines.append("ROM OFFSET DISTRIBUTION:")
        lines.append("-" * 70)

        from collections import Counter

        offset_counts = Counter(m.rom_offset for m in results.rom_matches)
        for offset, count in offset_counts.most_common(10):
            desc = next(
                (m.rom_description for m in results.rom_matches if m.rom_offset == offset),
                "",
            )
            lines.append(f"  ${offset:06X}: {count:4d} tiles ({desc})")
        lines.append("")

    # Staging → ROM mapping
    if results.staging_to_rom_mapping:
        lines.append("=" * 70)
        lines.append("STAGING BUFFER → ROM MAPPING:")
        lines.append("-" * 70)

        for staging, rom_offsets in sorted(results.staging_to_rom_mapping.items())[:10]:
            staging_bank = (staging >> 16) & 0xFF
            staging_off = staging & 0xFFFF
            rom_list = ", ".join(f"${o:06X}" for o in sorted(rom_offsets)[:3])
            if len(rom_offsets) > 3:
                rom_list += f" (+{len(rom_offsets) - 3} more)"
            lines.append(f"  ${staging_bank:02X}:{staging_off:04X} → {rom_list}")
        lines.append("")

    # Sample matches
    if results.rom_matches:
        lines.append("=" * 70)
        lines.append("SAMPLE MATCHES (first 10):")
        lines.append("-" * 70)
        lines.append(
            f"  {'Sprite':>6s} {'VRAM':>8s} {'Staging':>10s} "
            f"{'ROM':>8s} {'Description':<20s}"
        )

        for match in results.rom_matches[:10]:
            staging_bank = (match.staging_addr >> 16) & 0xFF
            staging_off = match.staging_addr & 0xFFFF
            lines.append(
                f"  {match.sprite_id:6d} "
                f"${match.vram_addr:06X} "
                f"${staging_bank:02X}:{staging_off:04X} "
                f"${match.rom_offset:06X} "
                f"{match.rom_description[:20]}"
            )
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)
