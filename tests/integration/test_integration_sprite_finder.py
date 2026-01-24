"""
Integration tests for sprite finder functionality using real components.

These tests require real HAL compression tools and verify actual sprite
finding and extraction behavior. They test with a synthetic ROM unless
a real Kirby ROM is available.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.rom_extractor import ROMExtractor
from core.sprite_finder import SpriteFinder

# Integration tests that need real DI setup and real HAL
# Uses session_managers with shared_state_safe at class level
# Don't use mock_hal - these tests verify real decompression behavior
pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_hal,
    pytest.mark.skip_thread_cleanup(reason="Integration tests involve HAL pool that spawns background threads"),
    pytest.mark.allows_registry_state(reason="Integration tests manage own lifecycle"),
]


@pytest.mark.integration
@pytest.mark.usefixtures("isolated_managers")
class TestSpriteFinder:
    """Test sprite finder with real ROM data and HAL compression."""

    def test_find_sprites_in_test_rom(self, test_rom_with_sprites):
        """Test finding sprites in a test ROM with known compressed data."""
        rom_info = test_rom_with_sprites

        # Skip if no sprites in test ROM (real Kirby ROM not available)
        if not rom_info["sprites"]:
            pytest.skip("No compressed sprites in test ROM - real Kirby ROM not available")

        rom_path = str(rom_info["path"])

        # Create sprite finder
        finder = SpriteFinder()

        # Read ROM data
        rom_data = Path(rom_path).read_bytes()

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
            # Allow some variance in tile count since decompression may vary
            assert found["tile_count"] > 0
            assert found["decompressed_size"] > 0

    def test_sprite_finder_with_rom_extractor(self, test_rom_with_sprites):
        """Test sprite finder working with ROM extractor."""
        rom_info = test_rom_with_sprites

        # Skip if no sprites in test ROM
        if not rom_info["sprites"]:
            pytest.skip("No compressed sprites in test ROM - real Kirby ROM not available")

        rom_path = str(rom_info["path"])

        # Create ROM extractor via app context (verifies app context is working)
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor
        assert extractor is not None

        # Create sprite finder
        finder = SpriteFinder()

        # Read ROM
        rom_data = Path(rom_path).read_bytes()

        # Scan for sprites at known locations
        found_sprites = []
        for sprite_info in rom_info["sprites"]:
            sprite = finder.find_sprite_at_offset(rom_data, sprite_info["offset"])
            if sprite:
                found_sprites.append(sprite)

        # We should find at least the sprites we expected
        assert len(found_sprites) >= 1, "Should find at least one sprite"

    def test_find_sprites_in_real_rom(self, real_kirby_rom):
        """Test finding sprites in real Kirby ROM if available."""
        if not real_kirby_rom:
            pytest.skip("Real Kirby ROM not available")

        finder = SpriteFinder()

        # Read ROM
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
