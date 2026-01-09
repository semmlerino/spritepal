"""
Factory for creating properly initialized ROMTileMatcher instances for testing.

Replaces the anti-pattern of `object.__new__` + manual attribute seeding.
Uses the production class with _skip_expensive_init to avoid HAL overhead
while ensuring all attributes are properly initialized.

Example usage:
    matcher = create_test_rom_tile_matcher(
        rom_path=tmp_path / "test.sfc",
        hash_to_locations={"abc123": [TileLocation(0x1B0000, 0)]},
        total_tiles=100,
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from core.mesen_integration.rom_tile_matcher import (
    ROMBlock,
    ROMTileMatcher,
    TileLocation,
)


def create_test_rom_tile_matcher(
    rom_path: Path,
    *,
    hash_to_locations: dict[str, list[TileLocation]] | None = None,
    blocks: list[ROMBlock] | None = None,
    total_tiles: int = 0,
    unique_hashes: int = 0,
    two_plane_tiles: int = 0,
    two_plane_indexed: bool = False,
    hal_two_plane_indexed: bool = False,
    header_offset: int = 0,
    apply_sa1_conversion: bool = True,
) -> ROMTileMatcher:
    """
    Create a ROMTileMatcher for testing with pre-seeded data.

    Uses the production class with _skip_expensive_init=True to avoid HAL overhead.
    All attributes are properly initialized through the real __init__, ensuring
    tests break if the constructor changes.

    Args:
        rom_path: Path to dummy ROM file (must exist)
        hash_to_locations: Pre-seeded hash mappings (default: empty dict)
        blocks: Pre-seeded block list (default: empty list)
        total_tiles: Total tile count for statistics
        unique_hashes: Unique hash count for statistics
        two_plane_tiles: Two-plane tile count
        two_plane_indexed: Whether two-plane index was built
        hal_two_plane_indexed: Whether HAL two-plane index was built
        header_offset: SMC header offset override
        apply_sa1_conversion: SA-1 conversion flag

    Returns:
        Properly initialized ROMTileMatcher ready for testing

    Example:
        def test_lookup(tmp_path):
            dummy_rom = tmp_path / "test.sfc"
            dummy_rom.write_bytes(bytes(0x200))

            matcher = create_test_rom_tile_matcher(
                rom_path=dummy_rom,
                hash_to_locations={
                    "abc123": [TileLocation(0x1B0000, 0, "Kirby")]
                },
                blocks=[ROMBlock(0x1B0000, "Kirby", 320, 10)],
            )

            # matcher is now fully initialized and usable
            assert matcher._total_tiles == 0  # default
    """
    # Create matcher with expensive operations skipped
    matcher = ROMTileMatcher(
        rom_path=rom_path,
        apply_sa1_conversion=apply_sa1_conversion,
        _skip_expensive_init=True,
    )

    # Override header offset
    matcher._header_offset = header_offset

    # Seed data if provided
    if hash_to_locations is not None:
        matcher._hash_to_locations = hash_to_locations
    if blocks is not None:
        matcher._blocks = blocks

    # Set statistics
    matcher._total_tiles = total_tiles
    matcher._unique_hashes = unique_hashes
    matcher._two_plane_tiles = two_plane_tiles
    matcher._two_plane_indexed = two_plane_indexed
    matcher._hal_two_plane_indexed = hal_two_plane_indexed

    # Provide mock HAL for methods that need it
    # This is the ONE place we use MagicMock - for the external HAL process
    matcher._hal = MagicMock()

    return matcher


def create_test_rom_tile_matcher_with_data(
    rom_path: Path,
    tile_data: dict[bytes, list[TileLocation]],
    *,
    blocks: list[ROMBlock] | None = None,
    apply_sa1_conversion: bool = True,
) -> ROMTileMatcher:
    """
    Create a ROMTileMatcher with pre-indexed tile data for lookup testing.

    This is a convenience wrapper that converts tile bytes to hashes.

    Args:
        rom_path: Path to dummy ROM file (must exist)
        tile_data: Mapping of tile bytes -> locations (will be hashed)
        blocks: Pre-seeded block list
        apply_sa1_conversion: SA-1 conversion flag

    Returns:
        Matcher with hash_to_locations populated from tile_data

    Example:
        tile_bytes = bytes(32)  # 32-byte tile
        matcher = create_test_rom_tile_matcher_with_data(
            rom_path=dummy_rom,
            tile_data={tile_bytes: [TileLocation(0x1B0000, 0)]},
        )
        # Now matcher.lookup_tile(tile_bytes) would work
    """
    import hashlib

    hash_to_locations: dict[str, list[TileLocation]] = {}
    for tile_bytes, locations in tile_data.items():
        tile_hash = hashlib.sha256(tile_bytes).hexdigest()[:16]
        hash_to_locations[tile_hash] = locations

    return create_test_rom_tile_matcher(
        rom_path=rom_path,
        hash_to_locations=hash_to_locations,
        blocks=blocks,
        total_tiles=sum(len(locs) for locs in hash_to_locations.values()),
        unique_hashes=len(hash_to_locations),
        apply_sa1_conversion=apply_sa1_conversion,
    )
