"""
Unit tests for tile_hash_database module.

Tests tile hashing, flip transforms, database lookups, and persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.mesen_integration.tile_hash_database import (
    BYTES_PER_TILE,
    ROMSpriteBlock,
    TileHashDatabase,
    TileMatch,
    build_and_save_database,
)

# =============================================================================
# TileMatch Tests
# =============================================================================


class TestTileMatch:
    """Tests for TileMatch dataclass."""

    def test_tile_byte_offset_zero(self) -> None:
        """Tile index 0 has byte offset 0."""
        match = TileMatch(rom_offset=0x1B0000, tile_index=0)
        assert match.tile_byte_offset == 0

    def test_tile_byte_offset_first_tile(self) -> None:
        """Tile index 1 has byte offset 32."""
        match = TileMatch(rom_offset=0x1B0000, tile_index=1)
        assert match.tile_byte_offset == BYTES_PER_TILE

    def test_tile_byte_offset_arbitrary(self) -> None:
        """Tile index N has byte offset N * 32."""
        match = TileMatch(rom_offset=0x1B0000, tile_index=10)
        assert match.tile_byte_offset == 10 * BYTES_PER_TILE

    def test_default_confidence(self) -> None:
        """Default confidence is 1.0."""
        match = TileMatch(rom_offset=0x1B0000, tile_index=0)
        assert match.confidence == 1.0

    def test_custom_confidence(self) -> None:
        """Confidence can be customized."""
        match = TileMatch(rom_offset=0x1B0000, tile_index=0, confidence=0.75)
        assert match.confidence == 0.75

    def test_description_default(self) -> None:
        """Default description is empty string."""
        match = TileMatch(rom_offset=0x1B0000, tile_index=0)
        assert match.description == ""

    def test_description_custom(self) -> None:
        """Description can be customized."""
        match = TileMatch(rom_offset=0x1B0000, tile_index=0, description="Kirby sprites")
        assert match.description == "Kirby sprites"


# =============================================================================
# ROMSpriteBlock Tests
# =============================================================================


class TestROMSpriteBlock:
    """Tests for ROMSpriteBlock dataclass."""

    def test_defaults(self) -> None:
        """Default values are set correctly."""
        block = ROMSpriteBlock(rom_offset=0x1B0000, description="Test")
        assert block.decompressed_size == 0
        assert block.tile_count == 0
        assert block.tile_hashes == []

    def test_tile_hashes_mutable(self) -> None:
        """tile_hashes list can be appended to."""
        block = ROMSpriteBlock(rom_offset=0x1B0000, description="Test")
        block.tile_hashes.append("abc123")
        assert block.tile_hashes == ["abc123"]

    def test_tile_hashes_isolated(self) -> None:
        """Each block has its own tile_hashes list."""
        block1 = ROMSpriteBlock(rom_offset=0x1B0000, description="Test1")
        block2 = ROMSpriteBlock(rom_offset=0x1C0000, description="Test2")
        block1.tile_hashes.append("abc123")
        assert block2.tile_hashes == []


# =============================================================================
# TileHashDatabase Static Methods Tests
# =============================================================================


class TestTileHashDatabaseStaticMethods:
    """Tests for TileHashDatabase static and class methods."""

    def test_hash_tile_basic(self) -> None:
        """_hash_tile returns MD5 hex digest."""
        tile_data = bytes(BYTES_PER_TILE)  # 32 zero bytes
        hash_result = TileHashDatabase._hash_tile(tile_data)
        assert isinstance(hash_result, str)
        assert len(hash_result) == 32  # MD5 hex digest length

    def test_hash_tile_deterministic(self) -> None:
        """Same data produces same hash."""
        tile_data = bytes(range(BYTES_PER_TILE))
        hash1 = TileHashDatabase._hash_tile(tile_data)
        hash2 = TileHashDatabase._hash_tile(tile_data)
        assert hash1 == hash2

    def test_hash_tile_different_data(self) -> None:
        """Different data produces different hash."""
        tile1 = bytes(BYTES_PER_TILE)
        tile2 = bytes([1] * BYTES_PER_TILE)
        hash1 = TileHashDatabase._hash_tile(tile1)
        hash2 = TileHashDatabase._hash_tile(tile2)
        assert hash1 != hash2

    def test_reverse_byte_zero(self) -> None:
        """Reversing 0x00 returns 0x00."""
        assert TileHashDatabase._reverse_byte(0x00) == 0x00

    def test_reverse_byte_ff(self) -> None:
        """Reversing 0xFF returns 0xFF."""
        assert TileHashDatabase._reverse_byte(0xFF) == 0xFF

    def test_reverse_byte_single_bit(self) -> None:
        """Reversing 0x80 returns 0x01."""
        assert TileHashDatabase._reverse_byte(0x80) == 0x01

    def test_reverse_byte_pattern(self) -> None:
        """Reversing 0xF0 returns 0x0F."""
        assert TileHashDatabase._reverse_byte(0xF0) == 0x0F

    def test_reverse_byte_asymmetric(self) -> None:
        """Reversing 0b10110100 (0xB4) returns 0b00101101 (0x2D)."""
        # 0xB4 = 1011 0100
        # Reversed = 0010 1101 = 0x2D
        assert TileHashDatabase._reverse_byte(0xB4) == 0x2D

    def test_reverse_byte_double_reverse(self) -> None:
        """Reversing twice returns original value."""
        for value in [0x00, 0xFF, 0xAA, 0x55, 0x12, 0x34]:
            assert TileHashDatabase._reverse_byte(TileHashDatabase._reverse_byte(value)) == value

    def test_flip_tile_no_flip(self) -> None:
        """No flip returns original data."""
        tile_data = bytes(range(BYTES_PER_TILE))
        result = TileHashDatabase._flip_tile(tile_data, flip_h=False, flip_v=False)
        assert result == tile_data

    def test_flip_tile_invalid_size(self) -> None:
        """Invalid tile size returns original data unchanged."""
        tile_data = bytes([1, 2, 3])
        result = TileHashDatabase._flip_tile(tile_data, flip_h=True, flip_v=False)
        assert result == tile_data

    def test_flip_tile_h_produces_different(self) -> None:
        """Horizontal flip produces different data (for non-symmetric tiles)."""
        # Create non-symmetric tile data
        tile_data = bytes(list(range(BYTES_PER_TILE)))
        result = TileHashDatabase._flip_tile(tile_data, flip_h=True, flip_v=False)
        assert result != tile_data

    def test_flip_tile_v_produces_different(self) -> None:
        """Vertical flip produces different data (for non-symmetric tiles)."""
        tile_data = bytes(list(range(BYTES_PER_TILE)))
        result = TileHashDatabase._flip_tile(tile_data, flip_h=False, flip_v=True)
        assert result != tile_data

    def test_flip_tile_hv_produces_different(self) -> None:
        """HV flip produces different data (for non-symmetric tiles)."""
        tile_data = bytes(list(range(BYTES_PER_TILE)))
        result = TileHashDatabase._flip_tile(tile_data, flip_h=True, flip_v=True)
        assert result != tile_data

    def test_flip_tile_double_h_flip(self) -> None:
        """Double horizontal flip returns original."""
        tile_data = bytes(list(range(BYTES_PER_TILE)))
        flipped_once = TileHashDatabase._flip_tile(tile_data, flip_h=True, flip_v=False)
        flipped_twice = TileHashDatabase._flip_tile(flipped_once, flip_h=True, flip_v=False)
        assert flipped_twice == tile_data

    def test_flip_tile_double_v_flip(self) -> None:
        """Double vertical flip returns original."""
        tile_data = bytes(list(range(BYTES_PER_TILE)))
        flipped_once = TileHashDatabase._flip_tile(tile_data, flip_h=False, flip_v=True)
        flipped_twice = TileHashDatabase._flip_tile(flipped_once, flip_h=False, flip_v=True)
        assert flipped_twice == tile_data

    def test_iter_flip_variants_count(self) -> None:
        """_iter_flip_variants returns 3 variants (H, V, HV)."""
        tile_data = bytes(BYTES_PER_TILE)
        variants = TileHashDatabase._iter_flip_variants(tile_data)
        assert len(variants) == 3

    def test_iter_flip_variants_all_different_for_asymmetric(self) -> None:
        """All variants are different for asymmetric data."""
        tile_data = bytes(range(BYTES_PER_TILE))
        variants = TileHashDatabase._iter_flip_variants(tile_data)
        # All should be different from original
        for variant in variants:
            assert variant != tile_data
        # All should be different from each other
        assert len(set(variants)) == 3

    def test_dedupe_matches_empty(self) -> None:
        """Deduping empty list returns empty list."""
        result = TileHashDatabase._dedupe_matches([])
        assert result == []

    def test_dedupe_matches_no_duplicates(self) -> None:
        """Deduping unique matches returns all matches."""
        matches = [
            TileMatch(rom_offset=0x1000, tile_index=0),
            TileMatch(rom_offset=0x1000, tile_index=1),
            TileMatch(rom_offset=0x2000, tile_index=0),
        ]
        result = TileHashDatabase._dedupe_matches(matches)
        assert len(result) == 3

    def test_dedupe_matches_with_duplicates(self) -> None:
        """Deduping removes duplicate (rom_offset, tile_index) pairs."""
        matches = [
            TileMatch(rom_offset=0x1000, tile_index=0, description="First"),
            TileMatch(rom_offset=0x1000, tile_index=0, description="Duplicate"),
            TileMatch(rom_offset=0x2000, tile_index=0),
        ]
        result = TileHashDatabase._dedupe_matches(matches)
        assert len(result) == 2
        # First occurrence should be kept
        assert result[0].description == "First"


# =============================================================================
# TileHashDatabase Lookup Tests (with mocked internal state)
# =============================================================================


class TestTileHashDatabaseLookup:
    """Tests for database lookup operations."""

    @pytest.fixture
    def mock_db(self, tmp_path: Path) -> TileHashDatabase:
        """Create a database with mocked internals (no ROM needed)."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))  # Minimal dummy file

        with patch.object(TileHashDatabase, "__init__", lambda self, path: None):
            db = object.__new__(TileHashDatabase)

        db.rom_path = dummy_rom
        db._hal = MagicMock()
        db._hash_to_match = {}
        db._blocks = []
        db._rom_header_offset = 0
        db._rom_checksum = None
        db._rom_title = None
        db._rom_size = 0
        return db

    @pytest.fixture
    def populated_db(self, mock_db: TileHashDatabase) -> TileHashDatabase:
        """Database with pre-populated data."""
        tile1 = bytes([0] * BYTES_PER_TILE)
        tile2 = bytes([1] * BYTES_PER_TILE)
        hash1 = TileHashDatabase._hash_tile(tile1)
        hash2 = TileHashDatabase._hash_tile(tile2)

        mock_db._hash_to_match = {
            hash1: [TileMatch(rom_offset=0x1B0000, tile_index=0, description="Kirby")],
            hash2: [
                TileMatch(rom_offset=0x1A0000, tile_index=5, description="Enemy"),
                TileMatch(rom_offset=0x1C0000, tile_index=10, description="BG"),
            ],
        }
        return mock_db

    def test_lookup_tile_found(self, populated_db: TileHashDatabase) -> None:
        """lookup_tile returns match when found."""
        tile_data = bytes([0] * BYTES_PER_TILE)
        match = populated_db.lookup_tile(tile_data)
        assert match is not None
        assert match.rom_offset == 0x1B0000
        assert match.tile_index == 0

    def test_lookup_tile_not_found(self, populated_db: TileHashDatabase) -> None:
        """lookup_tile returns None when not found."""
        tile_data = bytes([99] * BYTES_PER_TILE)
        match = populated_db.lookup_tile(tile_data)
        assert match is None

    def test_lookup_tile_invalid_size(self, populated_db: TileHashDatabase) -> None:
        """lookup_tile returns empty for invalid tile size."""
        tile_data = bytes([0] * 16)  # Wrong size
        matches = populated_db.lookup_tile_matches(tile_data)
        assert matches == []

    def test_lookup_tile_matches_multiple(self, populated_db: TileHashDatabase) -> None:
        """lookup_tile_matches returns all matches."""
        tile_data = bytes([1] * BYTES_PER_TILE)
        matches = populated_db.lookup_tile_matches(tile_data)
        assert len(matches) == 2
        offsets = {m.rom_offset for m in matches}
        assert offsets == {0x1A0000, 0x1C0000}

    def test_lookup_tile_with_flips(self, mock_db: TileHashDatabase) -> None:
        """lookup_tile with include_flips tries flip variants."""
        original = bytes(range(BYTES_PER_TILE))
        h_flip = TileHashDatabase._flip_tile(original, flip_h=True, flip_v=False)
        h_flip_hash = TileHashDatabase._hash_tile(h_flip)

        # Store the H-flipped version
        mock_db._hash_to_match = {
            h_flip_hash: [TileMatch(rom_offset=0x1B0000, tile_index=0)],
        }

        # Original shouldn't match without flips
        match = mock_db.lookup_tile(original, include_flips=False)
        assert match is None

        # Original should match with flips enabled
        match = mock_db.lookup_tile(original, include_flips=True)
        assert match is not None
        assert match.rom_offset == 0x1B0000

    def test_lookup_tiles_batch(self, populated_db: TileHashDatabase) -> None:
        """lookup_tiles processes multiple tiles."""
        tiles = [
            bytes([0] * BYTES_PER_TILE),
            bytes([1] * BYTES_PER_TILE),
            bytes([99] * BYTES_PER_TILE),  # Not found
        ]
        results = populated_db.lookup_tiles(tiles)
        assert len(results) == 3
        assert results[0] is not None
        assert results[1] is not None
        assert results[2] is None

    def test_lookup_tiles_matches_batch(self, populated_db: TileHashDatabase) -> None:
        """lookup_tiles_matches processes multiple tiles with all candidates."""
        tiles = [
            bytes([0] * BYTES_PER_TILE),
            bytes([1] * BYTES_PER_TILE),
        ]
        results = populated_db.lookup_tiles_matches(tiles)
        assert len(results) == 2
        assert len(results[0]) == 1  # One match
        assert len(results[1]) == 2  # Two matches

    def test_find_rom_offset_for_vram_tiles(self, populated_db: TileHashDatabase) -> None:
        """find_rom_offset_for_vram_tiles aggregates matches."""
        tiles = [
            bytes([0] * BYTES_PER_TILE),
            bytes([1] * BYTES_PER_TILE),
            bytes([1] * BYTES_PER_TILE),  # Same as tile2
        ]
        counts = populated_db.find_rom_offset_for_vram_tiles(tiles)
        # tile1 matches 0x1B0000 once
        # tile2 matches 0x1A0000 and 0x1C0000 twice each
        assert 0x1B0000 in counts
        assert counts[0x1B0000] == 1
        # Sorted by count descending
        first_key = next(iter(counts))
        assert counts[first_key] >= counts.get(0x1B0000, 0)

    def test_iter_all_matches(self, populated_db: TileHashDatabase) -> None:
        """iter_all_matches yields all hash->matches pairs."""
        all_matches = list(populated_db.iter_all_matches())
        assert len(all_matches) == 2
        hashes = [h for h, _ in all_matches]
        assert len(set(hashes)) == 2


# =============================================================================
# TileHashDatabase Statistics Tests
# =============================================================================


class TestTileHashDatabaseStatistics:
    """Tests for database statistics."""

    @pytest.fixture
    def db_with_stats(self, tmp_path: Path) -> TileHashDatabase:
        """Database with blocks for statistics testing."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        with patch.object(TileHashDatabase, "__init__", lambda self, path: None):
            db = object.__new__(TileHashDatabase)

        db.rom_path = dummy_rom
        db._hal = MagicMock()
        db._hash_to_match = {
            "hash1": [TileMatch(0x1000, 0)],
            "hash2": [TileMatch(0x1000, 1), TileMatch(0x2000, 0)],  # Collision
        }
        db._blocks = [
            ROMSpriteBlock(rom_offset=0x1000, description="Block1", tile_count=10, decompressed_size=320),
            ROMSpriteBlock(rom_offset=0x2000, description="Block2", tile_count=5, decompressed_size=160),
        ]
        db._rom_header_offset = 0
        db._rom_checksum = None
        db._rom_title = None
        db._rom_size = 0
        return db

    def test_get_statistics_structure(self, db_with_stats: TileHashDatabase) -> None:
        """get_statistics returns expected keys."""
        stats = db_with_stats.get_statistics()
        assert "total_blocks" in stats
        assert "total_unique_hashes" in stats
        assert "hashes_with_collisions" in stats
        assert "total_matches" in stats
        assert "total_tiles" in stats
        assert "blocks" in stats

    def test_get_statistics_values(self, db_with_stats: TileHashDatabase) -> None:
        """get_statistics returns correct values."""
        stats = db_with_stats.get_statistics()
        assert stats["total_blocks"] == 2
        assert stats["total_unique_hashes"] == 2
        assert stats["hashes_with_collisions"] == 1  # hash2 has 2 matches
        assert stats["total_matches"] == 3  # 1 + 2
        assert stats["total_tiles"] == 15  # 10 + 5

    def test_get_statistics_blocks_detail(self, db_with_stats: TileHashDatabase) -> None:
        """get_statistics includes block details."""
        stats = db_with_stats.get_statistics()
        blocks = stats["blocks"]
        assert isinstance(blocks, list)
        assert len(blocks) == 2
        assert blocks[0]["offset"] == "$001000"
        assert blocks[0]["description"] == "Block1"
        assert blocks[0]["tiles"] == 10


# =============================================================================
# TileHashDatabase Persistence Tests
# =============================================================================


class TestTileHashDatabasePersistence:
    """Tests for save/load database operations."""

    @pytest.fixture
    def db_for_save(self, tmp_path: Path) -> TileHashDatabase:
        """Database ready for save testing."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        with patch.object(TileHashDatabase, "__init__", lambda self, path: None):
            db = object.__new__(TileHashDatabase)

        db.rom_path = dummy_rom
        db._hal = MagicMock()
        db._rom_header_offset = 512
        db._rom_checksum = 0x1234
        db._rom_title = "TEST ROM"
        db._rom_size = 0x200
        db._blocks = [
            ROMSpriteBlock(
                rom_offset=0x1B0000,
                description="Test sprites",
                tile_count=2,
                tile_hashes=["abc123", "def456"],
            ),
        ]
        db._hash_to_match = {
            "abc123": [TileMatch(0x1B0000, 0, description="Test sprites")],
            "def456": [TileMatch(0x1B0000, 1, description="Test sprites")],
        }
        return db

    def test_save_database_creates_file(self, db_for_save: TileHashDatabase, tmp_path: Path) -> None:
        """save_database creates a JSON file."""
        output_path = tmp_path / "db.json"
        db_for_save.save_database(output_path)
        assert output_path.exists()

    def test_save_database_valid_json(self, db_for_save: TileHashDatabase, tmp_path: Path) -> None:
        """save_database creates valid JSON."""
        output_path = tmp_path / "db.json"
        db_for_save.save_database(output_path)
        data = json.loads(output_path.read_text())
        assert "blocks" in data
        assert "metadata" in data

    def test_save_database_metadata(self, db_for_save: TileHashDatabase, tmp_path: Path) -> None:
        """save_database includes ROM metadata."""
        output_path = tmp_path / "db.json"
        db_for_save.save_database(output_path)
        data = json.loads(output_path.read_text())
        metadata = data["metadata"]
        assert metadata["rom_title"] == "TEST ROM"
        assert metadata["rom_checksum"] == 0x1234
        assert metadata["rom_header_offset"] == 512

    def test_save_database_blocks(self, db_for_save: TileHashDatabase, tmp_path: Path) -> None:
        """save_database includes block data."""
        output_path = tmp_path / "db.json"
        db_for_save.save_database(output_path)
        data = json.loads(output_path.read_text())
        blocks = data["blocks"]
        assert len(blocks) == 1
        assert blocks[0]["rom_offset"] == 0x1B0000
        assert blocks[0]["hashes"] == ["abc123", "def456"]

    def test_load_database_restores_hashes(self, db_for_save: TileHashDatabase, tmp_path: Path) -> None:
        """load_database restores hash->match mappings."""
        output_path = tmp_path / "db.json"
        db_for_save.save_database(output_path)

        # Create new database and load
        new_db = object.__new__(TileHashDatabase)
        new_db.rom_path = db_for_save.rom_path
        new_db._hash_to_match = {}
        new_db._blocks = []
        new_db._rom_checksum = 0x1234
        new_db._rom_header_offset = 512

        new_db.load_database(output_path)

        assert "abc123" in new_db._hash_to_match
        assert "def456" in new_db._hash_to_match
        assert len(new_db._hash_to_match["abc123"]) == 1
        assert new_db._hash_to_match["abc123"][0].rom_offset == 0x1B0000

    def test_load_database_restores_blocks(self, db_for_save: TileHashDatabase, tmp_path: Path) -> None:
        """load_database restores block list."""
        output_path = tmp_path / "db.json"
        db_for_save.save_database(output_path)

        new_db = object.__new__(TileHashDatabase)
        new_db.rom_path = db_for_save.rom_path
        new_db._hash_to_match = {}
        new_db._blocks = []
        new_db._rom_checksum = 0x1234
        new_db._rom_header_offset = 512

        new_db.load_database(output_path)

        assert len(new_db._blocks) == 1
        assert new_db._blocks[0].rom_offset == 0x1B0000
        assert new_db._blocks[0].tile_count == 2

    def test_load_database_clears_existing(self, db_for_save: TileHashDatabase, tmp_path: Path) -> None:
        """load_database clears existing data before loading."""
        output_path = tmp_path / "db.json"
        db_for_save.save_database(output_path)

        new_db = object.__new__(TileHashDatabase)
        new_db.rom_path = db_for_save.rom_path
        new_db._hash_to_match = {"existing": [TileMatch(0, 0)]}
        new_db._blocks = [ROMSpriteBlock(0, "existing")]
        new_db._rom_checksum = 0x1234
        new_db._rom_header_offset = 512

        new_db.load_database(output_path)

        assert "existing" not in new_db._hash_to_match
        assert len(new_db._blocks) == 1


# =============================================================================
# TileHashDatabase Initialization Tests
# =============================================================================


class TestTileHashDatabaseInit:
    """Tests for database initialization."""

    def test_init_nonexistent_rom(self, tmp_path: Path) -> None:
        """Initialization with non-existent ROM doesn't crash."""
        rom_path = tmp_path / "nonexistent.sfc"
        db = TileHashDatabase(rom_path)
        assert db.rom_path == rom_path
        assert db._rom_size == 0

    def test_init_empty_database(self, tmp_path: Path) -> None:
        """New database starts empty."""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(0x200))

        with patch.object(TileHashDatabase, "__init__", lambda self, path: None):
            db = object.__new__(TileHashDatabase)
        db.rom_path = rom_path
        db._hash_to_match = {}
        db._blocks = []

        assert len(db._hash_to_match) == 0
        assert len(db._blocks) == 0


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_bytes_per_tile_constant(self) -> None:
        """BYTES_PER_TILE is 32."""
        assert BYTES_PER_TILE == 32

    def test_flip_tile_all_zeros(self) -> None:
        """Flipping all-zero tile returns all-zero tile."""
        tile_data = bytes(BYTES_PER_TILE)
        result_h = TileHashDatabase._flip_tile(tile_data, flip_h=True, flip_v=False)
        result_v = TileHashDatabase._flip_tile(tile_data, flip_h=False, flip_v=True)
        result_hv = TileHashDatabase._flip_tile(tile_data, flip_h=True, flip_v=True)
        assert result_h == tile_data
        assert result_v == tile_data
        assert result_hv == tile_data

    def test_flip_tile_all_ff(self) -> None:
        """Flipping all-FF tile returns all-FF tile."""
        tile_data = bytes([0xFF] * BYTES_PER_TILE)
        result_h = TileHashDatabase._flip_tile(tile_data, flip_h=True, flip_v=False)
        result_v = TileHashDatabase._flip_tile(tile_data, flip_h=False, flip_v=True)
        result_hv = TileHashDatabase._flip_tile(tile_data, flip_h=True, flip_v=True)
        assert result_h == tile_data
        assert result_v == tile_data
        assert result_hv == tile_data

    def test_lookup_tile_empty_database(self, tmp_path: Path) -> None:
        """Lookup in empty database returns None."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        with patch.object(TileHashDatabase, "__init__", lambda self, path: None):
            db = object.__new__(TileHashDatabase)
        db.rom_path = dummy_rom
        db._hash_to_match = {}
        db._blocks = []

        tile_data = bytes(BYTES_PER_TILE)
        assert db.lookup_tile(tile_data) is None

    def test_find_rom_offset_empty_tiles(self, tmp_path: Path) -> None:
        """find_rom_offset_for_vram_tiles with empty list returns empty dict."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        with patch.object(TileHashDatabase, "__init__", lambda self, path: None):
            db = object.__new__(TileHashDatabase)
        db.rom_path = dummy_rom
        db._hash_to_match = {}
        db._blocks = []

        result = db.find_rom_offset_for_vram_tiles([])
        assert result == {}

    def test_dedupe_preserves_order(self) -> None:
        """_dedupe_matches preserves insertion order."""
        matches = [
            TileMatch(rom_offset=0x3000, tile_index=0),
            TileMatch(rom_offset=0x1000, tile_index=0),
            TileMatch(rom_offset=0x2000, tile_index=0),
        ]
        result = TileHashDatabase._dedupe_matches(matches)
        assert [m.rom_offset for m in result] == [0x3000, 0x1000, 0x2000]


# =============================================================================
# build_and_save_database Function Tests
# =============================================================================


class TestBuildAndSaveDatabase:
    """Tests for build_and_save_database convenience function."""

    def test_build_without_save(self, tmp_path: Path) -> None:
        """build_and_save_database without output_path doesn't save."""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(0x200))

        with patch.object(TileHashDatabase, "build_database", return_value=0):
            db = build_and_save_database(rom_path)

        assert isinstance(db, TileHashDatabase)
        # No JSON file should be created
        json_files = list(tmp_path.glob("*.json"))
        assert len(json_files) == 0

    def test_build_with_save(self, tmp_path: Path) -> None:
        """build_and_save_database with output_path saves database."""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(0x200))
        output_path = tmp_path / "db.json"

        with patch.object(TileHashDatabase, "build_database", return_value=0):
            with patch.object(TileHashDatabase, "save_database") as mock_save:
                db = build_and_save_database(rom_path, output_path)
                mock_save.assert_called_once_with(output_path)

        assert isinstance(db, TileHashDatabase)
