"""
Integration tests for sprite finding with real HAL compression.

These tests require real HAL compression tools and verify actual sprite
finding and extraction behavior. They skip when no real Kirby ROM is available.

Migrated from tests/unit/test_sprite_finder.py::TestSpriteFinderRealHAL
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.sprite_finder import SpriteFinder

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_hal,
    pytest.mark.skip_thread_cleanup(reason="Integration tests involve HAL pool"),
    pytest.mark.allows_registry_state(reason="Integration tests manage own lifecycle"),
    pytest.mark.usefixtures("isolated_managers"),
    pytest.mark.headless,
]


@pytest.fixture(scope="module")
def real_kirby_rom():
    """Provide path to real Kirby ROM if available.

    Returns None if ROM not available. Tests using this MUST handle None case.
    Uses multiple candidate paths for robustness.
    """
    candidates = [
        # Environment variable (CI/CD can set this)
        Path(os.environ.get("SPRITEPAL_KIRBY_ROM", "")),
        # Relative to spritepal project root
        Path(__file__).parent.parent.parent.parent / "Kirby Super Star (USA).sfc",
        # Relative to spritepal/ (legacy location)
        Path(__file__).parent.parent.parent / "Kirby Super Star (USA).sfc",
    ]

    for path in candidates:
        if str(path) and path.exists() and path.is_file():
            return path.resolve()

    return None


class TestSpriteFinderRealHAL:
    """Test sprite finder with real ROM data and HAL compression.

    These tests require real HAL compression tools and verify actual sprite
    finding and extraction behavior. They skip when no real Kirby ROM is available.
    """

    def test_find_sprites_in_test_rom(self, real_kirby_rom, tmp_path):
        """Test finding sprites in a ROM with known compressed data."""
        if real_kirby_rom is None:
            pytest.skip("Real Kirby ROM not available")

        # Known sprite locations in Kirby Super Star (USA)
        rom_info = {
            "path": real_kirby_rom,
            "sprites": [
                {
                    "offset": 0x200000,
                    "compressed_size": 65464,
                    "decompressed_size": 7744,
                    "tile_count": 242,
                },
                {
                    "offset": 0x206000,
                    "compressed_size": 40888,
                    "decompressed_size": 832,
                    "tile_count": 26,
                },
            ],
        }

        finder = SpriteFinder()
        rom_data = Path(rom_info["path"]).read_bytes()

        # Find sprites at known locations
        sprites_found = []
        for sprite_info in rom_info["sprites"]:
            offset = sprite_info["offset"]
            result = finder.find_sprite_at_offset(rom_data, offset)
            if result:
                sprites_found.append(result)

        # Verify we found at least some sprites
        assert len(sprites_found) > 0, "Should find test sprites"

        # Verify sprite properties match expectations
        for found, expected in zip(sprites_found, rom_info["sprites"], strict=False):
            assert found["offset"] == expected["offset"]
            assert found["tile_count"] > 0
            assert found["decompressed_size"] > 0

    def test_sprite_finder_with_rom_extractor(self, real_kirby_rom, tmp_path):
        """Test sprite finder working with ROM extractor."""
        if real_kirby_rom is None:
            pytest.skip("Real Kirby ROM not available")

        from core.app_context import get_app_context

        # Verify app context is working
        extractor = get_app_context().rom_extractor
        assert extractor is not None

        finder = SpriteFinder()
        rom_data = Path(real_kirby_rom).read_bytes()

        # Known sprite location
        sprite = finder.find_sprite_at_offset(rom_data, 0x200000)
        assert sprite is not None, "Should find sprite at known location"

    def test_find_sprites_in_real_rom(self, real_kirby_rom):
        """Test finding sprites at known locations in real Kirby ROM."""
        if real_kirby_rom is None:
            pytest.skip("Real Kirby ROM not available")

        finder = SpriteFinder()
        rom_data = Path(real_kirby_rom).read_bytes()

        # Known sprite locations in Kirby Super Star
        known_locations = [
            0x200000,  # Common sprite area
            0x206000,  # Another sprite area
        ]

        found_count = 0
        for offset in known_locations:
            if offset < len(rom_data):
                sprite = finder.find_sprite_at_offset(rom_data, offset)
                if sprite:
                    found_count += 1
                    # Verify sprite has reasonable properties
                    assert sprite["tile_count"] > 0
                    assert sprite["decompressed_size"] > 0
                    assert sprite["quality"] > 0

        # Should find at least some sprites
        assert found_count > 0, "Should find sprites at known locations"
