"""
Maps captured VRAM tile data back to ROM offsets.

This is the key bridge between:
- Mesen 2 captures (VRAM tile data from visible sprites)
- ROM source offsets (where sprite graphics are stored compressed)

Usage:
    mapper = CaptureToROMMapper(rom_path)
    mapper.build_database()  # One-time setup

    # When processing a capture:
    results = mapper.map_capture(capture_result)
    for entry_id, rom_offset in results.items():
        print(f"OAM entry {entry_id} -> ROM ${rom_offset:06X}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.mesen_integration.click_extractor import CaptureResult, OAMEntry
from core.mesen_integration.tile_hash_database import TileHashDatabase, TileMatch
from utils.logging_config import get_logger

logger = get_logger(__name__)

LOW_INFO_UNIQUE_BYTES = 2
MIN_MATCHED_TILES = 4
MIN_SCORE = 2.0
AMBIGUITY_RATIO = 1.25
AMBIGUITY_GAP = 0.20


@dataclass
class MappedOAMEntry:
    """OAM entry with ROM offset mapping (tile_matches aligns with entry.tiles order)."""

    entry: OAMEntry
    rom_offset: int | None
    tile_matches: list[list[TileMatch]] = field(default_factory=list)
    match_count: int = 0
    scored_tiles: int = 0
    total_tiles: int = 0
    rom_offset_scores: dict[int, float] = field(default_factory=dict)
    best_score: float = 0.0
    ambiguous: bool = False
    ignored_low_info_tiles: int = 0

    @property
    def match_percentage(self) -> float:
        """Percentage of tiles that matched the database."""
        if self.total_tiles == 0:
            return 0.0
        return (self.match_count / self.total_tiles) * 100

    @property
    def scored_percentage(self) -> float:
        """Percentage of tiles that contributed to scoring."""
        if self.total_tiles == 0:
            return 0.0
        return (self.scored_tiles / self.total_tiles) * 100

    @property
    def is_confident(self) -> bool:
        """True if we have high confidence in the ROM offset."""
        if self.ambiguous:
            return False
        return self.scored_tiles >= MIN_MATCHED_TILES and self.best_score >= MIN_SCORE


@dataclass
class CaptureMapResult:
    """Result of mapping a complete capture to ROM offsets."""

    mapped_entries: list[MappedOAMEntry]
    rom_offset_summary: dict[int, int]  # rom_offset -> count of entries
    rom_offset_scores: dict[int, float] = field(default_factory=dict)
    matched_tiles: int = 0
    scored_tiles: int = 0
    total_tiles: int = 0
    ignored_low_info_tiles: int = 0
    ambiguous: bool = False
    ambiguity_note: str | None = None
    unmapped_count: int = 0

    @property
    def primary_rom_offset(self) -> int | None:
        """Most likely ROM offset in the capture (score-weighted if available)."""
        if self.rom_offset_scores:
            return max(self.rom_offset_scores.items(), key=lambda x: x[1])[0]
        if self.rom_offset_summary:
            return max(self.rom_offset_summary.items(), key=lambda x: x[1])[0]
        return None

    @property
    def primary_rom_offset_score(self) -> float:
        """Score for the primary ROM offset (0.0 if none)."""
        if not self.rom_offset_scores:
            return 0.0
        return max(self.rom_offset_scores.values())

    @property
    def is_confident(self) -> bool:
        """True if results meet minimum evidence thresholds and are not ambiguous."""
        if self.ambiguous:
            return False
        return self.scored_tiles >= MIN_MATCHED_TILES and self.primary_rom_offset_score >= MIN_SCORE

    def get_entries_for_offset(self, rom_offset: int) -> list[MappedOAMEntry]:
        """Get all OAM entries mapped to a specific ROM offset."""
        return [e for e in self.mapped_entries if e.rom_offset == rom_offset]


class CaptureToROMMapper:
    """
    Maps Mesen 2 capture data to ROM offsets.

    Uses the tile hash database to identify which ROM offset
    each captured OAM entry's tiles came from.
    """

    def __init__(
        self,
        rom_path: str | Path,
        database_path: str | Path | None = None,
        include_flips: bool = False,
    ):
        """
        Initialize mapper.

        Args:
            rom_path: Path to ROM file
            database_path: Optional path to pre-built tile hash database JSON
            include_flips: If True, hash lookups include H/V/HV variants
        """
        self.rom_path = Path(rom_path)
        self.database_path = Path(database_path) if database_path else None
        self._db: TileHashDatabase | None = None
        self.include_flips = include_flips

    def build_database(
        self,
        additional_offsets: list[tuple[int, str]] | None = None,
    ) -> int:
        """
        Build or load the tile hash database.

        Args:
            additional_offsets: Extra ROM offsets to index

        Returns:
            Number of tiles indexed
        """
        self._db = TileHashDatabase(self.rom_path)

        # Try to load existing database
        if self.database_path and self.database_path.exists():
            logger.info(f"Loading existing database from {self.database_path}")
            self._db.load_database(self.database_path)
            return sum(b.tile_count for b in self._db._blocks)

        # Build new database
        total = self._db.build_database(additional_offsets)

        # Save for future use
        if self.database_path:
            self._db.save_database(self.database_path)

        return total

    def map_capture(self, capture: CaptureResult) -> CaptureMapResult:
        """
        Map all OAM entries in a capture to their ROM offsets.

        Args:
            capture: Parsed capture result from Mesen 2

        Returns:
            CaptureMapResult with mappings for each OAM entry
        """
        if self._db is None:
            raise RuntimeError("Database not built. Call build_database() first.")

        mapped_entries: list[MappedOAMEntry] = []
        rom_offset_counts: dict[int, int] = {}
        rom_offset_scores: dict[int, float] = {}
        matched_tiles = 0
        scored_tiles = 0
        total_tiles = 0
        ignored_low_info_tiles = 0
        unmapped = 0

        for entry in capture.entries:
            mapped = self._map_entry(entry)
            mapped_entries.append(mapped)
            matched_tiles += mapped.match_count
            scored_tiles += mapped.scored_tiles
            total_tiles += mapped.total_tiles
            ignored_low_info_tiles += mapped.ignored_low_info_tiles

            if mapped.rom_offset is not None:
                rom_offset_counts[mapped.rom_offset] = (
                    rom_offset_counts.get(mapped.rom_offset, 0) + 1
                )
                for offset, score in mapped.rom_offset_scores.items():
                    rom_offset_scores[offset] = rom_offset_scores.get(offset, 0.0) + score
            else:
                unmapped += 1

        ambiguous, ambiguity_note = self._assess_ambiguity(rom_offset_scores)

        return CaptureMapResult(
            mapped_entries=mapped_entries,
            rom_offset_summary=dict(sorted(rom_offset_counts.items(), key=lambda x: -x[1])),
            rom_offset_scores=dict(sorted(rom_offset_scores.items(), key=lambda x: -x[1])),
            matched_tiles=matched_tiles,
            scored_tiles=scored_tiles,
            total_tiles=total_tiles,
            ignored_low_info_tiles=ignored_low_info_tiles,
            ambiguous=ambiguous,
            ambiguity_note=ambiguity_note,
            unmapped_count=unmapped,
        )

    def _map_entry(self, entry: OAMEntry) -> MappedOAMEntry:
        """Map a single OAM entry to its ROM offset."""
        if not entry.tiles:
            return MappedOAMEntry(
                entry=entry,
                rom_offset=None,
                total_tiles=0,
            )

        tile_matches: list[list[TileMatch]] = []
        offset_scores: dict[int, float] = {}
        matched_tiles = 0
        scored_tiles = 0
        ignored_low_info_tiles = 0

        for tile in entry.tiles:
            tile_bytes = tile.data_bytes
            matches = self._db.lookup_tile_matches(tile_bytes, include_flips=self.include_flips)  # type: ignore[union-attr]
            tile_matches.append(matches)
            if matches:
                matched_tiles += 1
                unique_offsets = {m.rom_offset for m in matches}
                weight = self._tile_weight(tile_bytes, len(unique_offsets))
                if weight <= 0:
                    ignored_low_info_tiles += 1
                    continue
                scored_tiles += 1
                for rom_offset in unique_offsets:
                    offset_scores[rom_offset] = offset_scores.get(rom_offset, 0.0) + weight

        # Determine winning ROM offset by weighted score
        best_offset: int | None = None
        best_score = 0.0
        ambiguous = False
        if offset_scores:
            sorted_scores = sorted(offset_scores.items(), key=lambda x: x[1], reverse=True)
            best_offset, best_score = sorted_scores[0]
            ambiguous, _ = self._assess_ambiguity(offset_scores)

        return MappedOAMEntry(
            entry=entry,
            rom_offset=best_offset,
            tile_matches=tile_matches,
            match_count=matched_tiles,
            scored_tiles=scored_tiles,
            total_tiles=len(entry.tiles),
            rom_offset_scores=offset_scores,
            best_score=best_score,
            ambiguous=ambiguous,
            ignored_low_info_tiles=ignored_low_info_tiles,
        )

    def map_single_tile(self, tile_data: bytes) -> TileMatch | None:
        """
        Look up a single tile in the database.

        Args:
            tile_data: 32 bytes of 4bpp tile data (lookup includes flipped variants)

        Returns:
            TileMatch if found, None otherwise
        """
        if self._db is None:
            raise RuntimeError("Database not built. Call build_database() first.")
        return self._db.lookup_tile(tile_data, include_flips=self.include_flips)

    def get_database_stats(self) -> dict[str, object]:
        """Get tile hash database statistics."""
        if self._db is None:
            return {"error": "Database not built"}
        return self._db.get_statistics()

    @staticmethod
    def _is_low_information(tile_bytes: bytes) -> bool:
        """Heuristic: tiles with very few unique bytes are low-information."""
        return len(set(tile_bytes)) <= LOW_INFO_UNIQUE_BYTES

    def _tile_weight(self, tile_bytes: bytes, candidate_count: int) -> float:
        """Weight a tile match by rarity (unique ROM offsets); drop low-information tiles."""
        if candidate_count <= 0:
            return 0.0
        if self._is_low_information(tile_bytes):
            return 0.0
        return 1.0 / candidate_count

    @staticmethod
    def _assess_ambiguity(scores: dict[int, float]) -> tuple[bool, str | None]:
        """Determine if the top score is meaningfully separated from runner-up."""
        if len(scores) < 2:
            return False, None
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_offset, best_score = sorted_scores[0]
        runner_offset, runner_score = sorted_scores[1]
        if best_score <= 0 or runner_score <= 0:
            return False, None
        ratio = best_score / runner_score if runner_score else float("inf")
        gap = (best_score - runner_score) / best_score if best_score else 0.0
        if ratio < AMBIGUITY_RATIO or gap < AMBIGUITY_GAP:
            note = (
                f"ambiguous: top=0x{best_offset:06X} score={best_score:.3f} "
                f"runner_up=0x{runner_offset:06X} score={runner_score:.3f}"
            )
            return True, note
        return False, None


def create_mapper_for_kirby(
    rom_path: str | Path,
    cache_dir: str | Path | None = None,
    include_flips: bool = False,
) -> CaptureToROMMapper:
    """
    Convenience function to create a mapper for Kirby Super Star.

    Args:
        rom_path: Path to Kirby Super Star ROM
        cache_dir: Optional directory for database cache

    Returns:
        Configured CaptureToROMMapper
    """
    db_path = None
    if cache_dir:
        db_path = Path(cache_dir) / "kirby_tile_database.json"

    mapper = CaptureToROMMapper(rom_path, db_path, include_flips=include_flips)
    mapper.build_database()
    return mapper
