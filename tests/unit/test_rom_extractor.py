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

    def test_4bpp_characteristics_via_public_validation(self):
        """Test 4bpp characteristics check via public validation function.

        Uses validate_4bpp_tile_structure from tile_utils instead of
        calling private _has_4bpp_characteristics method.
        """
        # Create valid 4bpp tile with bitplane variety
        tile_data = bytearray(BYTES_PER_TILE)
        # Add variety to bitplanes (similar pattern to what _has_4bpp_characteristics expects)
        for i in range(8):
            tile_data[i * 2] = 0xAA
            tile_data[i * 2 + 1] = 0x55
            tile_data[16 + i * 2] = 0xF0
            tile_data[16 + i * 2 + 1] = 0x0F

        # Validate via public function
        assert validate_4bpp_tile_structure(bytes(tile_data)) is True

    def test_4bpp_characteristics_too_small(self):
        """Test 4bpp validation with insufficient data via public function."""
        small_data = b"\x00" * 16  # Less than one tile
        assert validate_4bpp_tile_structure(small_data) is False

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
