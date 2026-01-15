"""
Unit tests for core/tile_utils.py tile utilities.

This module tests:
- Tile validation functions (validate_4bpp_tile_structure, is_heuristic_graphics_tile)
- Tile alignment functions (align_tile_data, get_tile_alignment_info)
- Integration scenarios with real-world patterns
"""

from __future__ import annotations

import pytest

from core.tile_utils import (
    align_tile_data,
    decode_4bpp_tile,
    get_tile_alignment_info,
    is_heuristic_graphics_tile,
    validate_4bpp_tile_structure,
)
from utils.constants import BYTES_PER_TILE

# ============================================================================
# Tile Validation Tests (from test_rom_extractor.py)
# ============================================================================


class TestTileValidation:
    """Test tile validation functions (structural checks)."""

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


# ============================================================================
# Tile Alignment Tests (from test_tile_alignment.py)
# ============================================================================


class TestAlignTileData:
    """Tests for align_tile_data function."""

    def test_already_aligned_data_unchanged(self) -> None:
        """Data that's already tile-aligned should not be modified."""
        # 2 complete tiles (64 bytes)
        aligned_data = b"\x00" * 64
        result = align_tile_data(aligned_data)
        assert result == aligned_data
        assert len(result) == 64

    def test_single_header_byte_removed(self) -> None:
        """Single header byte should be stripped to align data."""
        # 1 header byte + 2 complete tiles
        unaligned_data = b"\x02" + (b"\x00" * 64)
        result = align_tile_data(unaligned_data)
        assert len(result) == 64
        assert result == b"\x00" * 64

    def test_multiple_header_bytes_removed(self) -> None:
        """Multiple header bytes should be stripped."""
        # 15 header bytes + 2 complete tiles
        header = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
        tile_data = b"\xaa" * 64
        unaligned_data = header + tile_data
        result = align_tile_data(unaligned_data)
        assert len(result) == 64
        assert result == tile_data

    def test_real_world_kirby_case(self) -> None:
        """Test with the actual Kirby Super Star scenario (1 header byte)."""
        # Simulate: 2209 bytes = 69 tiles * 32 + 1 header byte
        # After alignment: 2208 bytes = 69 tiles
        header = b"\x02"  # The actual header byte value observed
        tile_data = b"\x00\x0f\xc1\xff" + (b"\x00" * 28)  # First tile pattern
        remaining_tiles = b"\x00" * (68 * 32)  # 68 more tiles
        unaligned_data = header + tile_data + remaining_tiles

        result = align_tile_data(unaligned_data)

        assert len(result) == 69 * 32  # 2208 bytes
        assert len(result) % BYTES_PER_TILE == 0
        # First 4 bytes should now be the tile data, not the header
        assert result[:4] == b"\x00\x0f\xc1\xff"

    def test_empty_data_returns_empty(self) -> None:
        """Empty input should return empty output."""
        result = align_tile_data(b"")
        assert result == b""

    def test_data_too_small_after_alignment_returns_original(self) -> None:
        """If stripping header leaves less than one tile, return original."""
        # 30 bytes total - stripping 30 bytes leaves nothing useful
        small_data = b"\x00" * 30
        result = align_tile_data(small_data)
        # Should return original since we can't form a complete tile after stripping
        assert result == small_data

    def test_exact_one_tile_aligned(self) -> None:
        """Exactly 32 bytes (one tile) should be unchanged."""
        one_tile = b"\xff" * 32
        result = align_tile_data(one_tile)
        assert result == one_tile
        assert len(result) == 32

    def test_custom_bytes_per_tile(self) -> None:
        """Test with custom bytes_per_tile parameter."""
        # Use 16 bytes per tile (like 2bpp format)
        data = b"\x01" + (b"\x00" * 32)  # 1 header + 2 tiles of 16 bytes
        result = align_tile_data(data, bytes_per_tile=16)
        assert len(result) == 32
        assert len(result) % 16 == 0

    def test_preserves_tile_content(self) -> None:
        """Verify actual tile content is preserved after alignment."""
        # Create recognizable tile patterns
        tile1 = bytes(range(32))  # 0x00-0x1F
        tile2 = bytes(range(32, 64))  # 0x20-0x3F
        header = b"\xab\xcd"  # 2-byte header

        unaligned = header + tile1 + tile2
        result = align_tile_data(unaligned)

        # After removing 2-byte header, we should have 62 bytes
        # But 62 % 32 = 30, so we'd remove 30 bytes...
        # Actually, 2 header + 64 tile = 66 bytes total
        # 66 % 32 = 2, so we remove 2 bytes (the header)
        assert len(result) == 64
        assert result[:32] == tile1
        assert result[32:] == tile2


class TestGetTileAlignmentInfo:
    """Tests for get_tile_alignment_info function."""

    def test_aligned_data_info(self) -> None:
        """Aligned data should report is_aligned=True."""
        data = b"\x00" * 64  # 2 complete tiles
        info = get_tile_alignment_info(data)

        assert info["size"] == 64
        assert info["tile_count"] == 2
        assert info["remainder"] == 0
        assert info["is_aligned"] is True
        assert info["header_bytes"] == 0

    def test_unaligned_data_info(self) -> None:
        """Unaligned data should report correct header bytes."""
        data = b"\x00" * 65  # 2 tiles + 1 extra byte
        info = get_tile_alignment_info(data)

        assert info["size"] == 65
        assert info["tile_count"] == 2
        assert info["remainder"] == 1
        assert info["is_aligned"] is False
        assert info["header_bytes"] == 1

    def test_empty_data_info(self) -> None:
        """Empty data should report zeros."""
        info = get_tile_alignment_info(b"")

        assert info["size"] == 0
        assert info["tile_count"] == 0
        assert info["remainder"] == 0
        assert info["is_aligned"] is True
        assert info["header_bytes"] == 0

    def test_kirby_scenario_info(self) -> None:
        """Test with real Kirby Super Star values."""
        # 2209 bytes = 69 * 32 + 1
        data = b"\x00" * 2209
        info = get_tile_alignment_info(data)

        assert info["size"] == 2209
        assert info["tile_count"] == 69
        assert info["remainder"] == 1
        assert info["is_aligned"] is False
        assert info["header_bytes"] == 1

    def test_custom_tile_size_info(self) -> None:
        """Test with custom bytes_per_tile."""
        data = b"\x00" * 50  # 3 tiles of 16 + 2 extra
        info = get_tile_alignment_info(data, bytes_per_tile=16)

        assert info["size"] == 50
        assert info["tile_count"] == 3
        assert info["remainder"] == 2
        assert info["is_aligned"] is False
        assert info["header_bytes"] == 2


# ============================================================================
# Alignment Integration Tests (from test_tile_alignment.py)
# ============================================================================


class TestAlignmentIntegration:
    """Integration tests for tile alignment with real-world patterns."""

    def test_align_then_decode_produces_valid_tiles(self) -> None:
        """Aligned data should be decodable as valid 4bpp tiles."""
        # Create a recognizable tile pattern (checkerboard)
        # In 4bpp, each pixel is 0-15, encoded in planar format
        tile_bytes = bytes(
            [
                # Bitplanes 0-1 (rows 0-7)
                0xAA,
                0x55,
                0xAA,
                0x55,
                0xAA,
                0x55,
                0xAA,
                0x55,
                0x55,
                0xAA,
                0x55,
                0xAA,
                0x55,
                0xAA,
                0x55,
                0xAA,
                # Bitplanes 2-3 (rows 0-7)
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
            ]
        )

        # Add a header byte
        unaligned = b"\x02" + tile_bytes

        # Align and decode
        aligned = align_tile_data(unaligned)
        pixels = decode_4bpp_tile(aligned)

        # Verify we got an 8x8 grid
        assert len(pixels) == 8
        assert all(len(row) == 8 for row in pixels)
        # Verify pixels are in valid range
        assert all(0 <= p <= 15 for row in pixels for p in row)

    def test_alignment_preserves_vram_match(self) -> None:
        """Verify alignment produces data that matches expected VRAM pattern."""
        # This simulates the actual bug we found: VRAM tile at offset 545
        # in a 2209-byte blob should match after alignment

        # Create a mock "decompressed" blob with 1 header byte
        header = b"\x02"

        # Create 69 tiles worth of data (2208 bytes)
        # Put a recognizable pattern at what will be tile 17 after alignment
        tiles_before = b"\x00" * (17 * 32)  # Tiles 0-16
        target_tile = b"\x00\x00\xff\xff\xbb\xc7\xfe\x01" + b"\x00" * 24  # Tile 17
        tiles_after = b"\x00" * (51 * 32)  # Tiles 18-68

        unaligned = header + tiles_before + target_tile + tiles_after
        assert len(unaligned) == 2209  # 1 + 2208

        # Align
        aligned = align_tile_data(unaligned)
        assert len(aligned) == 2208

        # Verify tile 17 is now at the correct position
        tile_17_start = 17 * 32
        tile_17_data = aligned[tile_17_start : tile_17_start + 32]
        assert tile_17_data[:8] == b"\x00\x00\xff\xff\xbb\xc7\xfe\x01"
