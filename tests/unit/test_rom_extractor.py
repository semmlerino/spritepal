"""
Unit tests for ROMExtractor logic.
Tests structural validation methods without requiring full app context or real ROMs.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from core.rom_extractor import ROMExtractor
from core.tile_utils import is_heuristic_graphics_tile, validate_4bpp_tile_structure
from utils.constants import BYTES_PER_TILE


@pytest.fixture
def mock_rom_cache():
    return Mock()


@pytest.fixture
def extractor(mock_rom_cache):
    """Create ROM extractor with mocked dependencies for unit testing."""
    return ROMExtractor(rom_cache=mock_rom_cache)


class TestROMExtractorValidationMethods:
    """Test tile and data validation methods (structural check only)."""

    def test_has_4bpp_characteristics_valid(self, extractor):
        """Test 4bpp characteristics check with valid data"""
        # Create valid 4bpp tile
        tile_data = bytearray(BYTES_PER_TILE)
        # Add variety to bitplanes
        for i in range(16):
            tile_data[i] = (i * 17) % 256
        for i in range(16, 32):
            tile_data[i] = (i * 13) % 256

        full_data = bytes(tile_data) * 10

        assert extractor._has_4bpp_characteristics(full_data) is True

    def test_has_4bpp_characteristics_too_small(self, extractor):
        """Test 4bpp characteristics check with insufficient data"""
        small_data = b"\x00" * 16  # Less than one tile
        assert extractor._has_4bpp_characteristics(small_data) is False

    def test_validate_4bpp_tile_valid(self):
        """Test tile validation with valid tile"""
        # Create a valid tile with good structure
        tile_data = bytearray(32)
        # Add variety to bitplanes
        for i in range(8):
            tile_data[i * 2] = 0xAA
            tile_data[i * 2 + 1] = 0x55
            tile_data[16 + i * 2] = 0xF0
            tile_data[16 + i * 2 + 1] = 0x0F

        assert validate_4bpp_tile_structure(bytes(tile_data)) is True

    def test_validate_4bpp_tile_wrong_size(self):
        """Test tile validation with wrong size"""
        wrong_size = b"\x00" * 16  # Too small
        assert validate_4bpp_tile_structure(wrong_size) is False

    def test_validate_4bpp_tile_no_correlation(self):
        """Test tile validation with no bitplane correlation"""
        tile_data = bytearray(32)
        # First bitplanes all zero, second all full (no correlation)
        for i in range(16):
            tile_data[i] = 0x00
        for i in range(16, 32):
            tile_data[i] = 0xFF

        assert validate_4bpp_tile_structure(bytes(tile_data)) is False
