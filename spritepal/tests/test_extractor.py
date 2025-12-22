"""Tests for SpriteExtractor class"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Mark this entire module for core logic tests
pytestmark = [
    pytest.mark.headless,
    pytest.mark.allows_registry_state(reason="File extraction tests don't use managers"),
]

from core.extractor import SpriteExtractor


class TestSpriteExtractor:
    """Test the SpriteExtractor functionality"""

    @pytest.fixture
    def extractor(self):
        """Create a SpriteExtractor instance"""
        return SpriteExtractor()

    @pytest.fixture
    def sample_vram_data(self):
        """Create sample VRAM data for testing"""
        # Create minimal valid 4bpp tile data (32 bytes per tile)
        # This represents a simple 8x8 tile with a pattern
        tile_data = bytearray(32)
        # Set some bits to create a pattern
        tile_data[0] = 0xFF  # Row 0, plane 0
        tile_data[1] = 0x00  # Row 0, plane 1
        tile_data[16] = 0x00  # Row 0, plane 2
        tile_data[17] = 0xFF  # Row 0, plane 3

        # Create VRAM data with padding before and after
        vram_data = bytearray(0x10000)  # 64KB VRAM
        vram_data[0xC000:0xC020] = tile_data  # Place tile at sprite offset
        return bytes(vram_data)

    def test_init(self, extractor):
        """Test extractor initialization"""
        assert extractor.vram_data is None
        assert extractor.offset == 0xC000
        assert extractor.size == 0x4000
        assert extractor.tiles_per_row == 16

    def test_load_vram(self, extractor, sample_vram_data):
        """Test loading VRAM data from file"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            f.write(sample_vram_data)
            f.flush()

        try:
            extractor.load_vram(f.name)
            assert extractor.vram_data == sample_vram_data
        finally:
            Path(f.name).unlink()

    def test_decode_4bpp_tile(self, extractor):
        """Test 4bpp tile decoding"""
        # Create a simple tile with known pattern
        tile_data = bytearray(32)
        # Set first pixel of first row to color index 9 (binary 1001)
        tile_data[0] = 0x80  # Plane 0, bit 7 = 1
        tile_data[1] = 0x00  # Plane 1, bit 7 = 0
        tile_data[16] = 0x00  # Plane 2, bit 7 = 0
        tile_data[17] = 0x80  # Plane 3, bit 7 = 1

        pixels = extractor._decode_4bpp_tile(tile_data)

        assert len(pixels) == 8  # 8 rows
        assert len(pixels[0]) == 8  # 8 pixels per row
        assert pixels[0][0] == 9  # First pixel should be color 9
        assert pixels[0][1] == 0  # Second pixel should be color 0

    def test_extract_tiles(self, extractor, sample_vram_data):
        """Test tile extraction from VRAM"""
        extractor.vram_data = sample_vram_data

        tiles, num_tiles = extractor.extract_tiles()

        assert num_tiles >= 1
        assert len(tiles) == num_tiles
        assert len(tiles[0]) == 8  # 8 rows
        assert len(tiles[0][0]) == 8  # 8 pixels

    def test_extract_tiles_custom_offset(self, extractor, sample_vram_data):
        """Test extracting tiles from custom offset"""
        extractor.vram_data = sample_vram_data

        # Extract from different offset
        tiles, num_tiles = extractor.extract_tiles(offset=0x8000, size=64)

        assert num_tiles == 2  # 64 bytes = 2 tiles
        assert len(tiles) == 2

    def test_extract_tiles_boundary_check(self, extractor):
        """Test extraction doesn't read past VRAM boundary"""
        small_vram = bytearray(100)
        extractor.vram_data = bytes(small_vram)

        # Try to extract beyond available data
        tiles, num_tiles = extractor.extract_tiles(offset=50, size=100)

        # Should only extract what's available
        assert num_tiles == 1  # Only 50 bytes available = 1 tile

    @pytest.mark.parametrize(
        ("tiles_per_row", "expected_width"),
        [
            (16, 128),  # 16 tiles * 8 pixels
            (8, 64),  # 8 tiles * 8 pixels
            (32, 256),  # 32 tiles * 8 pixels
        ],
    )
    def test_create_grayscale_image_dimensions(
        self, extractor, tiles_per_row, expected_width
    ):
        """Test grayscale image creation with different layouts"""
        # Create some test tiles
        test_tiles = [[[0] * 8 for _ in range(8)] for _ in range(tiles_per_row * 2)]

        img = extractor.create_grayscale_image(test_tiles, tiles_per_row)

        assert img.width == expected_width
        assert img.height == 16  # 2 rows * 8 pixels

    def test_extract_sprites_grayscale(self, extractor, sample_vram_data):
        """Test the main extraction method"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as vram_file:
            vram_file.write(sample_vram_data)
            vram_file.flush()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as output_file:
            output_path = output_file.name

        try:
            img, num_tiles = extractor.extract_sprites_grayscale(
                vram_file.name, output_path
            )

            assert img is not None
            assert num_tiles >= 1
            assert Path(output_path).exists()
            assert Path(output_path).stat().st_size > 0
        finally:
            Path(vram_file.name).unlink()
            Path(output_path).unlink(missing_ok=True)
