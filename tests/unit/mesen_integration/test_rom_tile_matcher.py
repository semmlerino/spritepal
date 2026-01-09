"""
Unit tests for rom_tile_matcher module.

Tests tile matching logic, flip transforms, lookups, and persistence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.mesen_integration.rom_tile_matcher import (
    BYTES_PER_TILE,
    ROMBlock,
    ROMTileMatcher,
    TileLocation,
)
from tests.infrastructure.fake_rom_tile_matcher import create_test_rom_tile_matcher

# =============================================================================
# TileLocation Tests
# =============================================================================


class TestTileLocation:
    """Tests for TileLocation dataclass."""

    def test_tile_byte_offset_zero(self) -> None:
        """Tile index 0 has byte offset 0."""
        loc = TileLocation(rom_offset=0x1B0000, tile_index=0)
        assert loc.tile_byte_offset == 0

    def test_tile_byte_offset_first(self) -> None:
        """Tile index 1 has byte offset 32."""
        loc = TileLocation(rom_offset=0x1B0000, tile_index=1)
        assert loc.tile_byte_offset == BYTES_PER_TILE

    def test_tile_byte_offset_arbitrary(self) -> None:
        """Tile index N has byte offset N * 32."""
        loc = TileLocation(rom_offset=0x1B0000, tile_index=15)
        assert loc.tile_byte_offset == 15 * BYTES_PER_TILE

    def test_default_description(self) -> None:
        """Default description is empty string."""
        loc = TileLocation(rom_offset=0x1B0000, tile_index=0)
        assert loc.description == ""

    def test_default_flip_variant(self) -> None:
        """Default flip_variant is empty string."""
        loc = TileLocation(rom_offset=0x1B0000, tile_index=0)
        assert loc.flip_variant == ""

    def test_custom_flip_variant(self) -> None:
        """flip_variant can be set."""
        loc = TileLocation(rom_offset=0x1B0000, tile_index=0, flip_variant="HV")
        assert loc.flip_variant == "HV"


# =============================================================================
# ROMBlock Tests
# =============================================================================


class TestROMBlock:
    """Tests for ROMBlock dataclass."""

    def test_defaults(self) -> None:
        """Default values are set correctly."""
        block = ROMBlock(rom_offset=0x1B0000, description="Test")
        assert block.decompressed_size == 0
        assert block.tile_count == 0
        assert block.tile_hashes == []

    def test_tile_hashes_mutable(self) -> None:
        """tile_hashes list can be appended to."""
        block = ROMBlock(rom_offset=0x1B0000, description="Test")
        block.tile_hashes.append("abc123")
        assert block.tile_hashes == ["abc123"]


# =============================================================================
# ROMTileMatcher Static Methods Tests
# =============================================================================


class TestROMTileMatcherStaticMethods:
    """Tests for ROMTileMatcher static methods."""

    def test_hash_tile_basic(self) -> None:
        """_hash_tile returns 16-character SHA256 prefix."""
        tile_data = bytes(BYTES_PER_TILE)
        result = ROMTileMatcher._hash_tile(tile_data)
        assert isinstance(result, str)
        assert len(result) == 16

    def test_hash_tile_matches_sha256(self) -> None:
        """_hash_tile uses SHA256."""
        tile_data = bytes(range(BYTES_PER_TILE))
        result = ROMTileMatcher._hash_tile(tile_data)
        expected = hashlib.sha256(tile_data).hexdigest()[:16]
        assert result == expected

    def test_hash_tile_deterministic(self) -> None:
        """Same data produces same hash."""
        tile_data = bytes([0xAB] * BYTES_PER_TILE)
        hash1 = ROMTileMatcher._hash_tile(tile_data)
        hash2 = ROMTileMatcher._hash_tile(tile_data)
        assert hash1 == hash2

    def test_hash_tile_different_data(self) -> None:
        """Different data produces different hash."""
        tile1 = bytes(BYTES_PER_TILE)
        tile2 = bytes([1] * BYTES_PER_TILE)
        hash1 = ROMTileMatcher._hash_tile(tile1)
        hash2 = ROMTileMatcher._hash_tile(tile2)
        assert hash1 != hash2

    def test_flip_h_returns_32_bytes(self) -> None:
        """_flip_h returns 32 bytes."""
        tile_data = bytes(BYTES_PER_TILE)
        result = ROMTileMatcher._flip_h(tile_data)
        assert len(result) == BYTES_PER_TILE

    def test_flip_h_all_zeros(self) -> None:
        """Flipping all zeros returns all zeros."""
        tile_data = bytes(BYTES_PER_TILE)
        result = ROMTileMatcher._flip_h(tile_data)
        assert result == tile_data

    def test_flip_h_all_ff(self) -> None:
        """Flipping all 0xFF returns all 0xFF."""
        tile_data = bytes([0xFF] * BYTES_PER_TILE)
        result = ROMTileMatcher._flip_h(tile_data)
        assert result == tile_data

    def test_flip_h_reverses_bits(self) -> None:
        """_flip_h reverses bit order in each byte."""
        # 0x80 = 10000000 -> 00000001 = 0x01
        tile_data = bytes([0x80] + [0] * (BYTES_PER_TILE - 1))
        result = ROMTileMatcher._flip_h(tile_data)
        assert result[0] == 0x01

    def test_flip_h_double_flip(self) -> None:
        """Double horizontal flip returns original."""
        tile_data = bytes(range(BYTES_PER_TILE))
        flipped = ROMTileMatcher._flip_h(tile_data)
        restored = ROMTileMatcher._flip_h(flipped)
        assert restored == tile_data

    def test_flip_v_returns_32_bytes(self) -> None:
        """_flip_v returns 32 bytes."""
        tile_data = bytes(BYTES_PER_TILE)
        result = ROMTileMatcher._flip_v(tile_data)
        assert len(result) == BYTES_PER_TILE

    def test_flip_v_all_same(self) -> None:
        """Flipping uniform tile returns same tile."""
        tile_data = bytes([0x55] * BYTES_PER_TILE)
        result = ROMTileMatcher._flip_v(tile_data)
        assert result == tile_data

    def test_flip_v_reverses_rows(self) -> None:
        """_flip_v reverses row order."""
        # Create tile with distinct row 0 and row 7
        tile_data = bytearray(BYTES_PER_TILE)
        tile_data[0] = 0xAA  # Row 0, bitplane 0
        tile_data[14] = 0x55  # Row 7, bitplane 0
        tile_data = bytes(tile_data)

        result = ROMTileMatcher._flip_v(tile_data)
        # After V flip, row 0 should have row 7's data
        assert result[0] == 0x55
        # And row 7 should have row 0's data
        assert result[14] == 0xAA

    def test_flip_v_double_flip(self) -> None:
        """Double vertical flip returns original."""
        tile_data = bytes(range(BYTES_PER_TILE))
        flipped = ROMTileMatcher._flip_v(tile_data)
        restored = ROMTileMatcher._flip_v(flipped)
        assert restored == tile_data

    def test_iter_flips_yields_three(self, tmp_path: Path) -> None:
        """_iter_flips yields 3 variants."""
        tile_data = bytes(range(BYTES_PER_TILE))
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        matcher = create_test_rom_tile_matcher(rom_path=dummy_rom)
        variants = list(matcher._iter_flips(tile_data))
        assert len(variants) == 3

    def test_iter_flips_labels(self, tmp_path: Path) -> None:
        """_iter_flips yields correct flip type labels."""
        tile_data = bytes(range(BYTES_PER_TILE))
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        matcher = create_test_rom_tile_matcher(rom_path=dummy_rom)
        variants = list(matcher._iter_flips(tile_data))
        labels = [v[0] for v in variants]
        assert labels == ["H", "V", "HV"]


# =============================================================================
# ROMTileMatcher Lookup Tests
# =============================================================================


class TestROMTileMatcherLookup:
    """Tests for database lookup operations."""

    @pytest.fixture
    def mock_matcher(self, tmp_path: Path) -> ROMTileMatcher:
        """Create matcher with test infrastructure."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        return create_test_rom_tile_matcher(
            rom_path=dummy_rom,
            hash_to_locations={},
            blocks=[],
        )

    @pytest.fixture
    def populated_matcher(self, mock_matcher: ROMTileMatcher) -> ROMTileMatcher:
        """Matcher with pre-populated hash mappings."""
        tile1 = bytes([0] * BYTES_PER_TILE)
        tile2 = bytes([1] * BYTES_PER_TILE)
        hash1 = ROMTileMatcher._hash_tile(tile1)
        hash2 = ROMTileMatcher._hash_tile(tile2)

        mock_matcher._hash_to_locations = {
            hash1: [TileLocation(0x1B0000, 0, "Kirby")],
            hash2: [
                TileLocation(0x1A0000, 5, "Enemy"),
                TileLocation(0x1C0000, 10, "BG"),
            ],
        }
        mock_matcher._total_tiles = 2
        mock_matcher._unique_hashes = 2
        return mock_matcher

    def test_lookup_vram_tile_found(self, populated_matcher: ROMTileMatcher) -> None:
        """lookup_vram_tile returns location when found."""
        tile_data = bytes([0] * BYTES_PER_TILE)
        matches = populated_matcher.lookup_vram_tile(tile_data)
        assert len(matches) == 1
        assert matches[0].rom_offset == 0x1B0000
        assert matches[0].tile_index == 0

    def test_lookup_vram_tile_not_found(self, populated_matcher: ROMTileMatcher) -> None:
        """lookup_vram_tile returns empty list when not found."""
        tile_data = bytes([99] * BYTES_PER_TILE)
        matches = populated_matcher.lookup_vram_tile(tile_data)
        assert matches == []

    def test_lookup_vram_tile_invalid_size(self, populated_matcher: ROMTileMatcher) -> None:
        """lookup_vram_tile returns empty for invalid size."""
        tile_data = bytes([0] * 16)  # Wrong size
        matches = populated_matcher.lookup_vram_tile(tile_data)
        assert matches == []

    def test_lookup_vram_tile_multiple_matches(self, populated_matcher: ROMTileMatcher) -> None:
        """lookup_vram_tile returns all matches."""
        tile_data = bytes([1] * BYTES_PER_TILE)
        matches = populated_matcher.lookup_vram_tile(tile_data)
        assert len(matches) == 2
        offsets = {m.rom_offset for m in matches}
        assert offsets == {0x1A0000, 0x1C0000}

    def test_lookup_vram_tile_sorted(self, populated_matcher: ROMTileMatcher) -> None:
        """lookup_vram_tile returns matches sorted by ROM offset."""
        tile_data = bytes([1] * BYTES_PER_TILE)
        matches = populated_matcher.lookup_vram_tile(tile_data)
        assert matches[0].rom_offset < matches[1].rom_offset

    def test_lookup_vram_tile_max_matches(self, mock_matcher: ROMTileMatcher) -> None:
        """lookup_vram_tile respects max_matches parameter."""
        tile_data = bytes([0] * BYTES_PER_TILE)
        hash_ = ROMTileMatcher._hash_tile(tile_data)

        # Create many matches
        mock_matcher._hash_to_locations = {
            hash_: [TileLocation(i * 0x1000, 0) for i in range(20)],
        }

        matches = mock_matcher.lookup_vram_tile(tile_data, max_matches=5)
        assert len(matches) == 5

    def test_lookup_vram_tiles_batch(self, populated_matcher: ROMTileMatcher) -> None:
        """lookup_vram_tiles processes multiple tiles."""
        tiles = [
            bytes([0] * BYTES_PER_TILE),
            bytes([1] * BYTES_PER_TILE),
            bytes([99] * BYTES_PER_TILE),  # Not found
        ]
        results = populated_matcher.lookup_vram_tiles(tiles)
        assert 0 in results
        assert 1 in results
        assert 2 not in results

    def test_lookup_vram_tiles_results_structure(self, populated_matcher: ROMTileMatcher) -> None:
        """lookup_vram_tiles returns dict with tile indices as keys."""
        tiles = [bytes([0] * BYTES_PER_TILE)]
        results = populated_matcher.lookup_vram_tiles(tiles)
        assert isinstance(results, dict)
        assert list(results.keys()) == [0]
        assert isinstance(results[0], list)


# =============================================================================
# ROMTileMatcher Statistics Tests
# =============================================================================


class TestROMTileMatcherStatistics:
    """Tests for statistics methods."""

    @pytest.fixture
    def stats_matcher(self, tmp_path: Path) -> ROMTileMatcher:
        """Matcher with data for statistics testing."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        return create_test_rom_tile_matcher(
            rom_path=dummy_rom,
            blocks=[
                ROMBlock(0x1B0000, "Kirby", decompressed_size=320, tile_count=10),
                ROMBlock(0x1A0000, "Enemy", decompressed_size=160, tile_count=5),
            ],
            hash_to_locations={"hash1": [], "hash2": [], "hash3": []},
            total_tiles=15,
            unique_hashes=3,
            header_offset=512,
        )

    def test_get_statistics_keys(self, stats_matcher: ROMTileMatcher) -> None:
        """get_statistics returns expected keys."""
        stats = stats_matcher.get_statistics()
        expected_keys = [
            "rom_path",
            "sa1_conversion",
            "header_offset",
            "blocks_indexed",
            "total_tiles",
            "unique_hashes",
            "collision_rate",
            "two_plane_indexed",
            "two_plane_tiles",
        ]
        for key in expected_keys:
            assert key in stats

    def test_get_statistics_values(self, stats_matcher: ROMTileMatcher) -> None:
        """get_statistics returns correct values."""
        stats = stats_matcher.get_statistics()
        assert stats["header_offset"] == 512
        assert stats["sa1_conversion"] is True
        assert stats["blocks_indexed"] == 2
        assert stats["total_tiles"] == 15
        assert stats["unique_hashes"] == 3

    def test_get_statistics_collision_rate(self, stats_matcher: ROMTileMatcher) -> None:
        """get_statistics calculates collision rate."""
        stats = stats_matcher.get_statistics()
        # 15 tiles, 3 unique hashes -> collision_rate = 1 - 3/15 = 0.8
        assert stats["collision_rate"] == pytest.approx(1 - 3 / 15)

    def test_get_statistics_zero_tiles(self, tmp_path: Path) -> None:
        """get_statistics handles zero tiles without division error."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        matcher = create_test_rom_tile_matcher(
            rom_path=dummy_rom,
            blocks=[],
            hash_to_locations={},
            total_tiles=0,
            unique_hashes=0,
        )

        stats = matcher.get_statistics()
        assert stats["collision_rate"] == 0


# =============================================================================
# ROMTileMatcher Persistence Tests
# =============================================================================


class TestROMTileMatcherPersistence:
    """Tests for save/load database operations."""

    @pytest.fixture
    def matcher_for_save(self, tmp_path: Path) -> ROMTileMatcher:
        """Matcher ready for save testing."""
        dummy_rom = tmp_path / "test.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        return create_test_rom_tile_matcher(
            rom_path=dummy_rom,
            blocks=[
                ROMBlock(0x1B0000, "Test sprites", 320, 10),
            ],
            hash_to_locations={
                "abcd1234abcd1234": [
                    TileLocation(0x1B0000, 0, "Test sprites", ""),
                    TileLocation(0x1B0000, 0, "Test sprites", "H"),
                ],
                "efgh5678efgh5678": [TileLocation(0x1B0000, 1, "Test sprites", "")],
            },
            total_tiles=10,
            unique_hashes=2,
        )

    def test_save_database_creates_file(self, matcher_for_save: ROMTileMatcher, tmp_path: Path) -> None:
        """save_database creates JSON file."""
        output_path = tmp_path / "db.json"
        matcher_for_save.save_database(output_path)
        assert output_path.exists()

    def test_save_database_valid_json(self, matcher_for_save: ROMTileMatcher, tmp_path: Path) -> None:
        """save_database creates valid JSON."""
        output_path = tmp_path / "db.json"
        matcher_for_save.save_database(output_path)
        data = json.loads(output_path.read_text())
        assert "version" in data
        assert "blocks" in data
        assert "hash_to_locations" in data

    def test_save_database_blocks(self, matcher_for_save: ROMTileMatcher, tmp_path: Path) -> None:
        """save_database includes block data."""
        output_path = tmp_path / "db.json"
        matcher_for_save.save_database(output_path)
        data = json.loads(output_path.read_text())
        blocks = data["blocks"]
        assert len(blocks) == 1
        assert blocks[0]["rom_offset"] == 0x1B0000
        assert blocks[0]["tile_count"] == 10

    def test_save_database_locations(self, matcher_for_save: ROMTileMatcher, tmp_path: Path) -> None:
        """save_database includes hash->location mappings."""
        output_path = tmp_path / "db.json"
        matcher_for_save.save_database(output_path)
        data = json.loads(output_path.read_text())
        locs = data["hash_to_locations"]
        assert "abcd1234abcd1234" in locs
        assert len(locs["abcd1234abcd1234"]) == 2
        assert locs["abcd1234abcd1234"][0]["flip_variant"] == ""
        assert locs["abcd1234abcd1234"][1]["flip_variant"] == "H"

    def test_load_database_restores_structure(self, matcher_for_save: ROMTileMatcher, tmp_path: Path) -> None:
        """load_database restores matcher structure."""
        output_path = tmp_path / "db.json"
        matcher_for_save.save_database(output_path)

        loaded = ROMTileMatcher.load_database(output_path, matcher_for_save.rom_path)

        assert len(loaded._blocks) == 1
        assert loaded._blocks[0].rom_offset == 0x1B0000
        assert "abcd1234abcd1234" in loaded._hash_to_locations
        assert loaded._total_tiles == 10
        assert loaded._unique_hashes == 2

    def test_load_database_flip_variants(self, matcher_for_save: ROMTileMatcher, tmp_path: Path) -> None:
        """load_database restores flip variant information."""
        output_path = tmp_path / "db.json"
        matcher_for_save.save_database(output_path)

        loaded = ROMTileMatcher.load_database(output_path, matcher_for_save.rom_path)

        locations = loaded._hash_to_locations["abcd1234abcd1234"]
        flip_variants = [loc.flip_variant for loc in locations]
        assert "" in flip_variants
        assert "H" in flip_variants


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_bytes_per_tile_constant(self) -> None:
        """BYTES_PER_TILE is 32."""
        assert BYTES_PER_TILE == 32

    def test_flip_produces_different_for_asymmetric(self) -> None:
        """Flips produce different data for non-symmetric tiles."""
        tile_data = bytes(range(BYTES_PER_TILE))
        h_flip = ROMTileMatcher._flip_h(tile_data)
        v_flip = ROMTileMatcher._flip_v(tile_data)
        hv_flip = ROMTileMatcher._flip_h(ROMTileMatcher._flip_v(tile_data))

        assert h_flip != tile_data
        assert v_flip != tile_data
        assert hv_flip != tile_data
        assert h_flip != v_flip

    def test_flip_order_matters(self) -> None:
        """H(V(tile)) should equal V(H(tile)) for same result."""
        tile_data = bytes(range(BYTES_PER_TILE))
        hv1 = ROMTileMatcher._flip_h(ROMTileMatcher._flip_v(tile_data))
        hv2 = ROMTileMatcher._flip_v(ROMTileMatcher._flip_h(tile_data))
        assert hv1 == hv2

    def test_empty_database_lookup(self, tmp_path: Path) -> None:
        """Lookup in empty database returns empty list."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        matcher = create_test_rom_tile_matcher(
            rom_path=dummy_rom,
            hash_to_locations={},
        )

        tile_data = bytes(BYTES_PER_TILE)
        assert matcher.lookup_vram_tile(tile_data) == []

    def test_tile_location_equality(self) -> None:
        """TileLocation comparison works correctly."""
        loc1 = TileLocation(0x1B0000, 5, "Test")
        loc2 = TileLocation(0x1B0000, 5, "Test")
        loc3 = TileLocation(0x1B0000, 6, "Test")

        assert loc1 == loc2
        assert loc1 != loc3

    def test_known_sprite_offsets_structure(self) -> None:
        """KNOWN_SPRITE_OFFSETS is properly structured."""
        assert len(ROMTileMatcher.KNOWN_SPRITE_OFFSETS) > 0
        for offset, desc in ROMTileMatcher.KNOWN_SPRITE_OFFSETS:
            assert isinstance(offset, int)
            assert isinstance(desc, str)
            assert offset > 0

    def test_hash_collision_handling(self, tmp_path: Path) -> None:
        """Multiple locations can map to same hash."""
        dummy_rom = tmp_path / "dummy.sfc"
        dummy_rom.write_bytes(bytes(0x200))

        tile_data = bytes([0] * BYTES_PER_TILE)
        hash_ = ROMTileMatcher._hash_tile(tile_data)

        # Same hash maps to multiple locations
        matcher = create_test_rom_tile_matcher(
            rom_path=dummy_rom,
            hash_to_locations={
                hash_: [
                    TileLocation(0x1B0000, 0, "Block A"),
                    TileLocation(0x1C0000, 5, "Block B"),
                    TileLocation(0x1D0000, 10, "Block C"),
                ],
            },
        )

        matches = matcher.lookup_vram_tile(tile_data)
        assert len(matches) == 3
