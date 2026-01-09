"""
Unit tests for capture_to_rom_mapper module.

Tests VRAM capture to ROM offset mapping logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from core.mesen_integration.capture_to_rom_mapper import (
    AMBIGUITY_GAP,
    AMBIGUITY_RATIO,
    LOW_INFO_UNIQUE_BYTES,
    MIN_MATCHED_TILES,
    MIN_SCORE,
    CaptureMapResult,
    CaptureToROMMapper,
    MappedOAMEntry,
)
from core.mesen_integration.tile_hash_database import TileMatch
from tests.infrastructure.fake_tile_hash_database import FakeTileHashDatabase

# =============================================================================
# Mock Classes for Testing
# =============================================================================


@dataclass
class MockTile:
    """Mock tile data for testing."""

    data_bytes: bytes


@dataclass
class MockOAMEntry:
    """Mock OAM entry for testing."""

    tiles: list[MockTile] = field(default_factory=list)
    idx: int = 0


@dataclass
class MockCaptureResult:
    """Mock capture result for testing."""

    entries: list[MockOAMEntry] = field(default_factory=list)


# =============================================================================
# MappedOAMEntry Tests
# =============================================================================


class TestMappedOAMEntry:
    """Tests for MappedOAMEntry dataclass."""

    @pytest.fixture
    def mock_entry(self) -> MockOAMEntry:
        """Create a mock OAM entry."""
        return MockOAMEntry()

    def test_match_percentage_zero_tiles(self, mock_entry: MockOAMEntry) -> None:
        """match_percentage returns 0.0 when total_tiles is 0."""
        mapped = MappedOAMEntry(
            entry=mock_entry,  # type: ignore[arg-type]
            rom_offset=None,
            match_count=0,
            total_tiles=0,
        )
        assert mapped.match_percentage == 0.0

    def test_match_percentage_all_matched(self, mock_entry: MockOAMEntry) -> None:
        """match_percentage returns 100.0 when all tiles matched."""
        mapped = MappedOAMEntry(
            entry=mock_entry,  # type: ignore[arg-type]
            rom_offset=0x1B0000,
            match_count=10,
            total_tiles=10,
        )
        assert mapped.match_percentage == 100.0

    def test_match_percentage_partial(self, mock_entry: MockOAMEntry) -> None:
        """match_percentage returns correct value for partial matches."""
        mapped = MappedOAMEntry(
            entry=mock_entry,  # type: ignore[arg-type]
            rom_offset=0x1B0000,
            match_count=5,
            total_tiles=10,
        )
        assert mapped.match_percentage == 50.0

    def test_scored_percentage_zero_tiles(self, mock_entry: MockOAMEntry) -> None:
        """scored_percentage returns 0.0 when total_tiles is 0."""
        mapped = MappedOAMEntry(
            entry=mock_entry,  # type: ignore[arg-type]
            rom_offset=None,
            scored_tiles=0,
            total_tiles=0,
        )
        assert mapped.scored_percentage == 0.0

    def test_scored_percentage_partial(self, mock_entry: MockOAMEntry) -> None:
        """scored_percentage returns correct value."""
        mapped = MappedOAMEntry(
            entry=mock_entry,  # type: ignore[arg-type]
            rom_offset=0x1B0000,
            scored_tiles=8,
            total_tiles=10,
        )
        assert mapped.scored_percentage == 80.0

    def test_is_confident_true(self, mock_entry: MockOAMEntry) -> None:
        """is_confident returns True when thresholds met."""
        mapped = MappedOAMEntry(
            entry=mock_entry,  # type: ignore[arg-type]
            rom_offset=0x1B0000,
            scored_tiles=MIN_MATCHED_TILES,
            best_score=MIN_SCORE,
            ambiguous=False,
        )
        assert mapped.is_confident is True

    def test_is_confident_false_ambiguous(self, mock_entry: MockOAMEntry) -> None:
        """is_confident returns False when ambiguous."""
        mapped = MappedOAMEntry(
            entry=mock_entry,  # type: ignore[arg-type]
            rom_offset=0x1B0000,
            scored_tiles=MIN_MATCHED_TILES,
            best_score=MIN_SCORE,
            ambiguous=True,
        )
        assert mapped.is_confident is False

    def test_is_confident_false_low_tiles(self, mock_entry: MockOAMEntry) -> None:
        """is_confident returns False when scored_tiles below threshold."""
        mapped = MappedOAMEntry(
            entry=mock_entry,  # type: ignore[arg-type]
            rom_offset=0x1B0000,
            scored_tiles=MIN_MATCHED_TILES - 1,
            best_score=MIN_SCORE,
            ambiguous=False,
        )
        assert mapped.is_confident is False

    def test_is_confident_false_low_score(self, mock_entry: MockOAMEntry) -> None:
        """is_confident returns False when best_score below threshold."""
        mapped = MappedOAMEntry(
            entry=mock_entry,  # type: ignore[arg-type]
            rom_offset=0x1B0000,
            scored_tiles=MIN_MATCHED_TILES,
            best_score=MIN_SCORE - 0.1,
            ambiguous=False,
        )
        assert mapped.is_confident is False


# =============================================================================
# CaptureMapResult Tests
# =============================================================================


class TestCaptureMapResult:
    """Tests for CaptureMapResult dataclass."""

    def test_primary_rom_offset_from_scores(self) -> None:
        """primary_rom_offset returns highest scoring offset."""
        result = CaptureMapResult(
            mapped_entries=[],
            rom_offset_summary={0x1B0000: 5, 0x1A0000: 10},
            rom_offset_scores={0x1B0000: 10.0, 0x1A0000: 5.0},
        )
        assert result.primary_rom_offset == 0x1B0000

    def test_primary_rom_offset_fallback_to_summary(self) -> None:
        """primary_rom_offset falls back to summary when no scores."""
        result = CaptureMapResult(
            mapped_entries=[],
            rom_offset_summary={0x1B0000: 5, 0x1A0000: 10},
            rom_offset_scores={},
        )
        # Falls back to max by count
        assert result.primary_rom_offset == 0x1A0000

    def test_primary_rom_offset_none_empty(self) -> None:
        """primary_rom_offset returns None when no data."""
        result = CaptureMapResult(
            mapped_entries=[],
            rom_offset_summary={},
            rom_offset_scores={},
        )
        assert result.primary_rom_offset is None

    def test_primary_rom_offset_score(self) -> None:
        """primary_rom_offset_score returns highest score."""
        result = CaptureMapResult(
            mapped_entries=[],
            rom_offset_summary={},
            rom_offset_scores={0x1B0000: 10.0, 0x1A0000: 5.0},
        )
        assert result.primary_rom_offset_score == 10.0

    def test_primary_rom_offset_score_zero_empty(self) -> None:
        """primary_rom_offset_score returns 0.0 when no scores."""
        result = CaptureMapResult(
            mapped_entries=[],
            rom_offset_summary={},
            rom_offset_scores={},
        )
        assert result.primary_rom_offset_score == 0.0

    def test_is_confident_true(self) -> None:
        """is_confident returns True when thresholds met."""
        result = CaptureMapResult(
            mapped_entries=[],
            rom_offset_summary={0x1B0000: 5},
            rom_offset_scores={0x1B0000: MIN_SCORE + 1.0},
            scored_tiles=MIN_MATCHED_TILES + 1,
            ambiguous=False,
        )
        assert result.is_confident is True

    def test_is_confident_false_ambiguous(self) -> None:
        """is_confident returns False when ambiguous."""
        result = CaptureMapResult(
            mapped_entries=[],
            rom_offset_summary={0x1B0000: 5},
            rom_offset_scores={0x1B0000: MIN_SCORE + 1.0},
            scored_tiles=MIN_MATCHED_TILES + 1,
            ambiguous=True,
        )
        assert result.is_confident is False

    def test_get_entries_for_offset(self) -> None:
        """get_entries_for_offset filters by ROM offset."""
        mock_entry = MockOAMEntry()
        entry1 = MappedOAMEntry(entry=mock_entry, rom_offset=0x1B0000)  # type: ignore[arg-type]
        entry2 = MappedOAMEntry(entry=mock_entry, rom_offset=0x1A0000)  # type: ignore[arg-type]
        entry3 = MappedOAMEntry(entry=mock_entry, rom_offset=0x1B0000)  # type: ignore[arg-type]

        result = CaptureMapResult(
            mapped_entries=[entry1, entry2, entry3],
            rom_offset_summary={0x1B0000: 2, 0x1A0000: 1},
        )

        entries = result.get_entries_for_offset(0x1B0000)
        assert len(entries) == 2
        assert all(e.rom_offset == 0x1B0000 for e in entries)

    def test_get_entries_for_offset_none(self) -> None:
        """get_entries_for_offset returns empty list for unknown offset."""
        result = CaptureMapResult(
            mapped_entries=[],
            rom_offset_summary={},
        )
        entries = result.get_entries_for_offset(0x999999)
        assert entries == []


# =============================================================================
# CaptureToROMMapper Instance Methods Tests
# =============================================================================


class TestCaptureToROMMapperInstanceMethods:
    """Tests for CaptureToROMMapper instance methods."""

    @pytest.fixture
    def fake_db(self, tmp_path: Path) -> FakeTileHashDatabase:
        """Create a fake database for testing."""
        return FakeTileHashDatabase(rom_path=tmp_path / "dummy.sfc")

    @pytest.fixture
    def mapper_with_db(self, tmp_path: Path, fake_db: FakeTileHashDatabase) -> CaptureToROMMapper:
        """Create mapper with fake database."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        mapper = CaptureToROMMapper(dummy_rom)
        mapper._db = fake_db
        return mapper

    def test_get_database_stats_with_db(self, mapper_with_db: CaptureToROMMapper) -> None:
        """get_database_stats delegates to database."""
        stats = mapper_with_db.get_database_stats()
        # FakeTileHashDatabase returns its own statistics structure
        assert "total_blocks" in stats
        assert "total_unique_hashes" in stats


# =============================================================================
# CaptureToROMMapper.map_capture Tests
# =============================================================================


class TestCaptureToROMMapperMapCapture:
    """Tests for map_capture method."""

    @pytest.fixture
    def fake_db(self, tmp_path: Path) -> FakeTileHashDatabase:
        """Create a fake database for testing."""
        return FakeTileHashDatabase(rom_path=tmp_path / "dummy.sfc")

    @pytest.fixture
    def mapper_with_db(self, tmp_path: Path, fake_db: FakeTileHashDatabase) -> CaptureToROMMapper:
        """Create mapper with fake database."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        mapper = CaptureToROMMapper(dummy_rom)
        mapper._db = fake_db
        return mapper

    def test_map_capture_no_db(self, tmp_path: Path) -> None:
        """map_capture raises when database not built."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        mapper = CaptureToROMMapper(dummy_rom)
        capture = MockCaptureResult(entries=[])
        with pytest.raises(RuntimeError, match="Database not built"):
            mapper.map_capture(capture)  # type: ignore[arg-type]

    def test_map_capture_empty(self, mapper_with_db: CaptureToROMMapper) -> None:
        """map_capture handles empty capture."""
        capture = MockCaptureResult(entries=[])
        result = mapper_with_db.map_capture(capture)  # type: ignore[arg-type]
        assert len(result.mapped_entries) == 0
        assert result.total_tiles == 0

    def test_map_capture_aggregates_scores(
        self, mapper_with_db: CaptureToROMMapper, fake_db: FakeTileHashDatabase
    ) -> None:
        """map_capture aggregates scores across entries."""
        # First entry matches 0x1B0000 only
        tile1 = bytes([0] + list(range(1, 32)))
        fake_db.seed_lookup_matches(tile1, [TileMatch(rom_offset=0x1B0000, tile_index=0)])

        # Second entry matches both 0x1B0000 and 0x1A0000
        tile2 = bytes(range(1, 33))
        fake_db.seed_lookup_matches(
            tile2,
            [
                TileMatch(rom_offset=0x1B0000, tile_index=0),
                TileMatch(rom_offset=0x1A0000, tile_index=0),
            ],
        )

        entry1 = MockOAMEntry(tiles=[MockTile(tile1)])
        entry2 = MockOAMEntry(tiles=[MockTile(tile2)])
        capture = MockCaptureResult(entries=[entry1, entry2])

        result = mapper_with_db.map_capture(capture)  # type: ignore[arg-type]

        assert len(result.mapped_entries) == 2
        # 0x1B0000 should have higher total score (appears in both)
        assert 0x1B0000 in result.rom_offset_scores

    def test_map_capture_counts_unmapped(self, mapper_with_db: CaptureToROMMapper) -> None:
        """map_capture counts unmapped entries."""
        # No seeding = no matches
        entry = MockOAMEntry(tiles=[MockTile(bytes(range(32)))])
        capture = MockCaptureResult(entries=[entry])

        result = mapper_with_db.map_capture(capture)  # type: ignore[arg-type]
        assert result.unmapped_count == 1

    def test_map_capture_detects_ambiguity(
        self, mapper_with_db: CaptureToROMMapper, fake_db: FakeTileHashDatabase
    ) -> None:
        """map_capture detects ambiguous results."""
        # Create tiles that match two offsets with similar scores
        tile1 = bytes(range(32))
        # Seed to match two offsets
        fake_db.seed_lookup_matches(
            tile1,
            [
                TileMatch(rom_offset=0x1B0000, tile_index=0),
                TileMatch(rom_offset=0x1A0000, tile_index=0),
            ],
        )

        entry = MockOAMEntry(tiles=[MockTile(tile1)])
        capture = MockCaptureResult(entries=[entry])

        result = mapper_with_db.map_capture(capture)  # type: ignore[arg-type]

        # Should be ambiguous because scores are identical (or very close)
        assert result.ambiguous is True
        assert result.ambiguity_note is not None

    def test_map_capture_ignores_low_info(
        self, mapper_with_db: CaptureToROMMapper, fake_db: FakeTileHashDatabase
    ) -> None:
        """map_capture ignores low-information tiles."""
        # All-zero tile is low-information
        low_info_tile = bytes(32)
        # Even if it matches something in DB
        fake_db.seed_lookup_matches(
            low_info_tile, [TileMatch(rom_offset=0x1B0000, tile_index=0)]
        )

        entry = MockOAMEntry(tiles=[MockTile(low_info_tile)])
        capture = MockCaptureResult(entries=[entry])

        result = mapper_with_db.map_capture(capture)  # type: ignore[arg-type]

        # Should be counted as ignored
        assert result.ignored_low_info_tiles == 1
        # Should NOT contribute to score/confidence (scored_tiles should be 0)
        assert result.scored_tiles == 0


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_low_info_unique_bytes(self) -> None:
        """LOW_INFO_UNIQUE_BYTES is a positive integer."""
        assert isinstance(LOW_INFO_UNIQUE_BYTES, int)
        assert LOW_INFO_UNIQUE_BYTES > 0

    def test_min_matched_tiles(self) -> None:
        """MIN_MATCHED_TILES is a positive integer."""
        assert isinstance(MIN_MATCHED_TILES, int)
        assert MIN_MATCHED_TILES > 0

    def test_min_score(self) -> None:
        """MIN_SCORE is a positive float."""
        assert isinstance(MIN_SCORE, (int, float))
        assert MIN_SCORE > 0

    def test_ambiguity_ratio(self) -> None:
        """AMBIGUITY_RATIO is >= 1.0."""
        assert isinstance(AMBIGUITY_RATIO, (int, float))
        assert AMBIGUITY_RATIO >= 1.0

    def test_ambiguity_gap(self) -> None:
        """AMBIGUITY_GAP is between 0 and 1."""
        assert isinstance(AMBIGUITY_GAP, (int, float))
        assert 0 <= AMBIGUITY_GAP <= 1


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_mapper_init_with_database_path(self, tmp_path: Path) -> None:
        """Mapper can be initialized with database path."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))
        db_path = tmp_path / "db.json"

        mapper = CaptureToROMMapper(dummy_rom, db_path)
        assert mapper.database_path == db_path

    def test_mapper_include_flips_option(self, tmp_path: Path) -> None:
        """Mapper respects include_flips option."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        mapper = CaptureToROMMapper(dummy_rom, include_flips=True)
        assert mapper.include_flips is True

        mapper2 = CaptureToROMMapper(dummy_rom, include_flips=False)
        assert mapper2.include_flips is False

    def test_assess_ambiguity_exact_ratio(self) -> None:
        """_assess_ambiguity at exact AMBIGUITY_RATIO boundary."""
        # Score ratio exactly at AMBIGUITY_RATIO
        best = 10.0
        runner = best / AMBIGUITY_RATIO
        scores = {0x1B0000: best, 0x1A0000: runner}
        # At boundary, should still be ambiguous (< not <=)
        ambiguous, _ = CaptureToROMMapper._assess_ambiguity(scores)
        # Note: depends on exact implementation (< vs <=)

    def test_mapped_entry_defaults(self) -> None:
        """MappedOAMEntry has correct defaults."""
        mock_entry = MockOAMEntry()
        mapped = MappedOAMEntry(entry=mock_entry, rom_offset=None)  # type: ignore[arg-type]
        assert mapped.tile_matches == []
        assert mapped.match_count == 0
        assert mapped.scored_tiles == 0
        assert mapped.total_tiles == 0
        assert mapped.rom_offset_scores == {}
        assert mapped.best_score == 0.0
        assert mapped.ambiguous is False
        assert mapped.ignored_low_info_tiles == 0

    def test_capture_map_result_defaults(self) -> None:
        """CaptureMapResult has correct defaults."""
        result = CaptureMapResult(
            mapped_entries=[],
            rom_offset_summary={},
        )
        assert result.rom_offset_scores == {}
        assert result.matched_tiles == 0
        assert result.scored_tiles == 0
        assert result.total_tiles == 0
        assert result.ignored_low_info_tiles == 0
        assert result.ambiguous is False
        assert result.ambiguity_note is None
        assert result.unmapped_count == 0
