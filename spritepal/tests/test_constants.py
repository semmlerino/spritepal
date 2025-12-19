"""
Tests for constants module.

This file tests pure constants and utility functions that don't require
manager initialization. Marked with @pytest.mark.no_manager_setup for optimal performance.
"""

import pytest

# Mark this entire module for fast, pure unit tests
pytestmark = [
    pytest.mark.headless,
    pytest.mark.no_manager_setup,
]

from utils.constants import (
    BYTES_PER_TILE,
    CGRAM_PALETTE_SIZE,
    CGRAM_PATTERNS,
    COLORS_PER_PALETTE,
    DEFAULT_TILES_PER_ROW,
    METADATA_EXTENSION,
    OAM_PATTERNS,
    PALETTE_EXTENSION,
    PALETTE_INFO,
    SPRITE_EXTENSION,
    SPRITE_PALETTE_END,
    SPRITE_PALETTE_START,
    TILE_HEIGHT,
    TILE_WIDTH,
    VRAM_PATTERNS,
    VRAM_SPRITE_OFFSET,
    VRAM_SPRITE_SIZE,
)


@pytest.mark.no_manager_setup
class TestConstants:
    """Test constants are properly defined"""

    def test_memory_offsets(self):
        """Test SNES memory offset constants"""
        assert VRAM_SPRITE_OFFSET == 0xC000
        assert VRAM_SPRITE_SIZE == 0x4000
        assert VRAM_SPRITE_OFFSET + VRAM_SPRITE_SIZE <= 0x10000  # Within 64KB VRAM

    def test_sprite_format_constants(self):
        """Test sprite format constants"""
        assert BYTES_PER_TILE == 32  # 4bpp format
        assert TILE_WIDTH == 8
        assert TILE_HEIGHT == 8
        assert DEFAULT_TILES_PER_ROW == 16

        # Verify 4bpp format math
        pixels_per_tile = TILE_WIDTH * TILE_HEIGHT
        bits_per_pixel = 4
        expected_bytes = (pixels_per_tile * bits_per_pixel) // 8
        assert expected_bytes == BYTES_PER_TILE

    def test_palette_constants(self):
        """Test palette-related constants"""
        assert COLORS_PER_PALETTE == 16
        assert SPRITE_PALETTE_START == 8
        assert SPRITE_PALETTE_END == 16
        assert CGRAM_PALETTE_SIZE == 32

        # Verify palette size calculation
        assert CGRAM_PALETTE_SIZE == COLORS_PER_PALETTE * 2  # 2 bytes per color

        # Verify sprite palette range
        assert SPRITE_PALETTE_END - SPRITE_PALETTE_START == 8

    def test_file_extensions(self):
        """Test file extension constants"""
        assert PALETTE_EXTENSION == ".pal.json"
        assert METADATA_EXTENSION == ".metadata.json"
        assert SPRITE_EXTENSION == ".png"

        # All should start with dot
        assert all(
            ext.startswith(".")
            for ext in [PALETTE_EXTENSION, METADATA_EXTENSION, SPRITE_EXTENSION]
        )

    def test_palette_info(self):
        """Test palette information dictionary"""
        assert isinstance(PALETTE_INFO, dict)

        # Check all sprite palettes have info
        for pal_idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
            assert pal_idx in PALETTE_INFO
            name, desc = PALETTE_INFO[pal_idx]
            assert isinstance(name, str)
            assert isinstance(desc, str)
            assert len(name) > 0
            assert len(desc) > 0

        # Check specific known palettes
        assert PALETTE_INFO[8][0] == "Kirby (Pink)"
        assert PALETTE_INFO[12][0] == "UI/HUD"
        assert PALETTE_INFO[14][0] == "Boss/Enemy"

    def test_file_patterns(self):
        """Test dump file pattern lists"""
        assert isinstance(VRAM_PATTERNS, list)
        assert isinstance(CGRAM_PATTERNS, list)
        assert isinstance(OAM_PATTERNS, list)

        # Each should have multiple patterns
        assert len(VRAM_PATTERNS) >= 3
        assert len(CGRAM_PATTERNS) >= 3
        assert len(OAM_PATTERNS) >= 3

        # All patterns should contain wildcard
        all_patterns = VRAM_PATTERNS + CGRAM_PATTERNS + OAM_PATTERNS
        assert all("*" in pattern for pattern in all_patterns)

        # All should end with .dmp
        assert all(pattern.endswith((".dmp", "*.dmp")) for pattern in all_patterns)
