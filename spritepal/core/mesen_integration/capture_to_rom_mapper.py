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


@dataclass
class MappedOAMEntry:
    """OAM entry with ROM offset mapping."""

    entry: OAMEntry
    rom_offset: int | None
    tile_matches: list[TileMatch] = field(default_factory=list)
    match_count: int = 0
    total_tiles: int = 0

    @property
    def match_percentage(self) -> float:
        """Percentage of tiles that matched the database."""
        if self.total_tiles == 0:
            return 0.0
        return (self.match_count / self.total_tiles) * 100

    @property
    def is_confident(self) -> bool:
        """True if we have high confidence in the ROM offset."""
        return self.match_percentage >= 50 and self.match_count >= 1


@dataclass
class CaptureMapResult:
    """Result of mapping a complete capture to ROM offsets."""

    mapped_entries: list[MappedOAMEntry]
    rom_offset_summary: dict[int, int]  # rom_offset -> count of entries
    unmapped_count: int = 0

    @property
    def primary_rom_offset(self) -> int | None:
        """Most common ROM offset in the capture."""
        if not self.rom_offset_summary:
            return None
        return max(self.rom_offset_summary.items(), key=lambda x: x[1])[0]

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
    ):
        """
        Initialize mapper.

        Args:
            rom_path: Path to ROM file
            database_path: Optional path to pre-built tile hash database JSON
        """
        self.rom_path = Path(rom_path)
        self.database_path = Path(database_path) if database_path else None
        self._db: TileHashDatabase | None = None

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
        unmapped = 0

        for entry in capture.entries:
            mapped = self._map_entry(entry)
            mapped_entries.append(mapped)

            if mapped.rom_offset:
                rom_offset_counts[mapped.rom_offset] = (
                    rom_offset_counts.get(mapped.rom_offset, 0) + 1
                )
            else:
                unmapped += 1

        return CaptureMapResult(
            mapped_entries=mapped_entries,
            rom_offset_summary=dict(sorted(rom_offset_counts.items(), key=lambda x: -x[1])),
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

        tile_matches: list[TileMatch] = []
        offset_votes: dict[int, int] = {}

        for tile in entry.tiles:
            tile_bytes = tile.data_bytes
            match = self._db.lookup_tile(tile_bytes)  # type: ignore[union-attr]

            if match:
                tile_matches.append(match)
                offset_votes[match.rom_offset] = offset_votes.get(match.rom_offset, 0) + 1

        # Determine winning ROM offset by vote count
        best_offset: int | None = None
        if offset_votes:
            best_offset = max(offset_votes.items(), key=lambda x: x[1])[0]

        return MappedOAMEntry(
            entry=entry,
            rom_offset=best_offset,
            tile_matches=tile_matches,
            match_count=len(tile_matches),
            total_tiles=len(entry.tiles),
        )

    def map_single_tile(self, tile_data: bytes) -> TileMatch | None:
        """
        Look up a single tile in the database.

        Args:
            tile_data: 32 bytes of 4bpp tile data

        Returns:
            TileMatch if found, None otherwise
        """
        if self._db is None:
            raise RuntimeError("Database not built. Call build_database() first.")
        return self._db.lookup_tile(tile_data)

    def get_database_stats(self) -> dict[str, object]:
        """Get tile hash database statistics."""
        if self._db is None:
            return {"error": "Database not built"}
        return self._db.get_statistics()


def create_mapper_for_kirby(
    rom_path: str | Path,
    cache_dir: str | Path | None = None,
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

    mapper = CaptureToROMMapper(rom_path, db_path)
    mapper.build_database()
    return mapper
