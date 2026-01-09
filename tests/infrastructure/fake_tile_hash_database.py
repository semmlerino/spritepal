"""
Fake TileHashDatabase for fast, type-safe testing.

Implements the same interface as TileHashDatabase without:
- HALCompressor initialization
- ROM file I/O operations
- Database indexing overhead

Use this instead of MagicMock for CaptureToROMMapper tests.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from core.mesen_integration.tile_hash_database import TileMatch

if TYPE_CHECKING:
    pass


@dataclass
class FakeTileHashDatabase:
    """
    Type-safe fake for TileHashDatabase.

    Allows pre-seeding lookup results for deterministic testing.
    All methods match the real TileHashDatabase signatures.

    Example usage:
        fake_db = FakeTileHashDatabase()
        tile_bytes = bytes(32)
        fake_db.seed_lookup(tile_bytes, TileMatch(rom_offset=0x1B0000, tile_index=5))
        result = fake_db.lookup_tile(tile_bytes)
        assert result.rom_offset == 0x1B0000
    """

    rom_path: Path = field(default_factory=lambda: Path("/fake/rom.sfc"))

    # Pre-seeded lookup results keyed by tile hash
    _lookup_results: dict[str, TileMatch | None] = field(default_factory=dict)
    _lookup_matches_results: dict[str, list[TileMatch]] = field(default_factory=dict)

    # Call tracking for verification
    _lookup_calls: int = field(default=0, init=False)
    _lookup_matches_calls: int = field(default=0, init=False)
    _lookup_tiles_seen: list[bytes] = field(default_factory=list, init=False)

    def lookup_tile(
        self, tile_data: bytes, include_flips: bool = False
    ) -> TileMatch | None:
        """
        Return pre-seeded result for tile lookup.

        Args:
            tile_data: 32 bytes of 4bpp tile data
            include_flips: Also try H/V/HV flipped variants (ignored in fake)

        Returns:
            TileMatch if seeded, None otherwise
        """
        self._lookup_calls += 1
        self._lookup_tiles_seen.append(tile_data)
        tile_hash = self._hash_tile(tile_data)
        return self._lookup_results.get(tile_hash)

    def lookup_tile_matches(
        self, tile_data: bytes, include_flips: bool = False
    ) -> list[TileMatch]:
        """
        Return pre-seeded matches for tile lookup.

        Args:
            tile_data: 32 bytes of 4bpp tile data
            include_flips: Also try H/V/HV flipped variants (ignored in fake)

        Returns:
            List of TileMatch if seeded, empty list otherwise
        """
        self._lookup_matches_calls += 1
        self._lookup_tiles_seen.append(tile_data)
        tile_hash = self._hash_tile(tile_data)
        return self._lookup_matches_results.get(tile_hash, [])

    def lookup_tiles(
        self, tiles_data: list[bytes], include_flips: bool = False
    ) -> list[TileMatch | None]:
        """Look up multiple tiles, returning single best match for each."""
        return [self.lookup_tile(t, include_flips) for t in tiles_data]

    def lookup_tiles_matches(
        self, tiles_data: list[bytes], include_flips: bool = False
    ) -> list[list[TileMatch]]:
        """Look up multiple tiles, returning all matches for each."""
        return [self.lookup_tile_matches(t, include_flips) for t in tiles_data]

    def get_statistics(self) -> dict[str, object]:
        """Return fake statistics."""
        return {
            "total_blocks": 0,
            "total_unique_hashes": len(self._lookup_results)
            + len(self._lookup_matches_results),
            "hashes_with_collisions": 0,
            "total_matches": sum(len(m) for m in self._lookup_matches_results.values()),
            "total_tiles": 0,
            "blocks": [],
        }

    def _hash_tile(self, tile_data: bytes) -> str:
        """Generate hash for tile bytes (matches real implementation)."""
        return hashlib.sha256(tile_data).hexdigest()[:16]

    # ============ Test helper methods ============

    def seed_lookup(self, tile_data: bytes, result: TileMatch | None) -> None:
        """
        Pre-seed a single-match lookup result.

        Args:
            tile_data: The tile bytes that will trigger this result
            result: The TileMatch to return (or None for no match)
        """
        tile_hash = self._hash_tile(tile_data)
        self._lookup_results[tile_hash] = result

    def seed_lookup_matches(self, tile_data: bytes, results: list[TileMatch]) -> None:
        """
        Pre-seed a multi-match lookup result.

        Args:
            tile_data: The tile bytes that will trigger this result
            results: List of TileMatch candidates to return
        """
        tile_hash = self._hash_tile(tile_data)
        self._lookup_matches_results[tile_hash] = results

    def verify_called(
        self, lookup: int | None = None, matches: int | None = None
    ) -> None:
        """
        Assert expected call counts.

        Args:
            lookup: Expected number of lookup_tile calls (None to skip check)
            matches: Expected number of lookup_tile_matches calls (None to skip)

        Raises:
            AssertionError: If actual calls don't match expected
        """
        if lookup is not None:
            assert (
                self._lookup_calls == lookup
            ), f"Expected {lookup} lookup_tile calls, got {self._lookup_calls}"
        if matches is not None:
            assert (
                self._lookup_matches_calls == matches
            ), f"Expected {matches} lookup_tile_matches calls, got {self._lookup_matches_calls}"

    def reset_call_tracking(self) -> None:
        """Reset call counters and seen tiles for reuse in multiple tests."""
        self._lookup_calls = 0
        self._lookup_matches_calls = 0
        self._lookup_tiles_seen.clear()
