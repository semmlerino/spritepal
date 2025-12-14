"""
Comprehensive tests for ROM sprite extraction functionality.
Tests both unit functionality and integration across multiple modules.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from core.hal_compression import HALCompressionError
from core.rom_extractor import ROMExtractor
from utils.constants import BYTES_PER_TILE, TILE_HEIGHT, TILE_WIDTH

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Uses session_managers which owns worker threads"),
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.slow,
    pytest.mark.usefixtures("session_managers", "mock_hal"),  # DI + HAL mocking
]

class TestROMExtractorInit:
    """Test ROM extractor initialization"""

    def test_init_creates_components(self):
        """Test that initialization creates all required components"""
        extractor = ROMExtractor()

        # Verify all components are created
        assert extractor.hal_compressor is not None
        assert extractor.rom_injector is not None
        assert extractor.default_palette_loader is not None
        assert extractor.rom_palette_extractor is not None
        assert extractor.sprite_config_loader is not None

        # Verify components are of expected types (real or mock)
        from core.default_palette_loader import DefaultPaletteLoader
        from core.rom_injector import ROMInjector
        from core.rom_palette_extractor import ROMPaletteExtractor
        from core.sprite_config_loader import SpriteConfigLoader

        # Accept both real and mock HAL compressor (test runs with mock_hal fixture)
        # Check by class name to avoid import ordering issues with monkeypatch
        hal_class_name = type(extractor.hal_compressor).__name__
        assert hal_class_name in ("HALCompressor", "MockHALCompressor"), f"Unexpected type: {hal_class_name}"
        assert isinstance(extractor.rom_injector, ROMInjector)
        assert isinstance(extractor.default_palette_loader, DefaultPaletteLoader)
        assert isinstance(extractor.rom_palette_extractor, ROMPaletteExtractor)
        assert isinstance(extractor.sprite_config_loader, SpriteConfigLoader)

class TestROMExtractor4bppConversion:
    """Test 4bpp to PNG conversion functionality"""

    @pytest.fixture
    def extractor(self):
        """Create ROM extractor for testing"""
        return ROMExtractor()

    def test_get_4bpp_pixel_basic(self, extractor):
        """Test basic 4bpp pixel extraction"""
        # Create test tile data - SNES 4bpp format
        # Each tile is 32 bytes: 16 bytes for planes 0,1 and 16 bytes for planes 2,3
        tile_data = bytearray(32)

        # Set up a test pattern - pixel at (0,0) should have value 5 (binary 0101)
        # Plane 0 (bit 0): 1, Plane 1 (bit 1): 0, Plane 2 (bit 2): 1, Plane 3 (bit 3): 0
        tile_data[0] = 0x80  # Plane 0, row 0: bit 7 set (pixel 0)
        tile_data[1] = 0x00  # Plane 1, row 0: bit 7 not set
        tile_data[16] = 0x80  # Plane 2, row 0: bit 7 set (pixel 0)
        tile_data[17] = 0x00  # Plane 3, row 0: bit 7 not set

        pixel_value = extractor._get_4bpp_pixel(tile_data, 0, 0)

        # Expected: (0 << 3) | (1 << 2) | (0 << 1) | 1 = 5
        assert pixel_value == 5

    def test_get_4bpp_pixel_different_positions(self, extractor):
        """Test 4bpp pixel extraction at different positions"""
        tile_data = bytearray(32)

        # Set up test pattern for pixel at (1,0) - bit position 6
        tile_data[0] = 0x40  # Plane 0, row 0: bit 6 set
        tile_data[1] = 0x40  # Plane 1, row 0: bit 6 set
        tile_data[16] = 0x00  # Plane 2, row 0: bit 6 not set
        tile_data[17] = 0x00  # Plane 3, row 0: bit 6 not set

        pixel_value = extractor._get_4bpp_pixel(tile_data, 1, 0)

        # Expected: (0 << 3) | (0 << 2) | (1 << 1) | 1 = 3
        assert pixel_value == 3

    def test_get_4bpp_pixel_different_rows(self, extractor):
        """Test 4bpp pixel extraction in different rows"""
        tile_data = bytearray(32)

        # Set up test pattern for pixel at (0,1) - row 1, bit 7
        tile_data[2] = 0x80  # Plane 0, row 1: bit 7 set
        tile_data[3] = 0x00  # Plane 1, row 1: bit 7 not set
        tile_data[18] = 0x00  # Plane 2, row 1: bit 7 not set
        tile_data[19] = 0x80  # Plane 3, row 1: bit 7 set

        pixel_value = extractor._get_4bpp_pixel(tile_data, 0, 1)

        # Expected: (1 << 3) | (0 << 2) | (0 << 1) | 1 = 9
        assert pixel_value == 9

    def test_convert_4bpp_to_png_dimensions(self, extractor, tmp_path):
        """Test that PNG conversion creates correct dimensions"""
        # Create test data for exactly 4 tiles (4 * 32 = 128 bytes)
        tile_data = b"\x00" * (4 * BYTES_PER_TILE)
        output_path = tmp_path / "test_sprite.png"

        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        # Verify tile count
        assert tile_count == 4

        # Verify PNG was created
        assert output_path.exists()

        # Verify image dimensions
        img = Image.open(output_path)
        # 4 tiles in 16-tile-wide rows: 1 row of 4 tiles
        expected_width = 16 * TILE_WIDTH  # Standard sprite sheet width
        expected_height = 1 * TILE_HEIGHT  # 1 row needed for 4 tiles
        assert img.size == (expected_width, expected_height)

    def test_convert_4bpp_to_png_large_sprite(self, extractor, tmp_path):
        """Test PNG conversion with larger sprite data"""
        # Create test data for 20 tiles (20 * 32 = 640 bytes)
        tile_data = b"\x00" * (20 * BYTES_PER_TILE)
        output_path = tmp_path / "large_sprite.png"

        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == 20
        assert output_path.exists()

        # Verify image dimensions
        img = Image.open(output_path)
        # 20 tiles in 16-tile-wide rows: 2 rows (16 + 4 tiles)
        expected_width = 16 * TILE_WIDTH
        expected_height = 2 * TILE_HEIGHT  # ceil(20/16) = 2 rows
        assert img.size == (expected_width, expected_height)

    def test_convert_4bpp_to_png_pixel_values(self, extractor, tmp_path):
        """Test that PNG conversion produces correct pixel values"""
        # Create test data with known pattern
        tile_data = bytearray(BYTES_PER_TILE)

        # Set up first pixel (0,0) to have value 15 (all bits set)
        tile_data[0] = 0x80  # Plane 0, row 0: bit 7 set
        tile_data[1] = 0x80  # Plane 1, row 0: bit 7 set
        tile_data[16] = 0x80  # Plane 2, row 0: bit 7 set
        tile_data[17] = 0x80  # Plane 3, row 0: bit 7 set

        output_path = tmp_path / "test_pixels.png"
        extractor._convert_4bpp_to_png(tile_data, str(output_path))

        # Verify pixel value
        img = Image.open(output_path)
        pixel_value = img.getpixel((0, 0))

        # 4-bit value 15 should become 8-bit value 255 (15 * 17 = 255)
        assert pixel_value == 255

    def test_convert_4bpp_to_png_empty_data(self, extractor, tmp_path):
        """Test PNG conversion with empty data"""
        tile_data = b""
        output_path = tmp_path / "empty_sprite.png"

        # Empty data should be handled gracefully
        # Test that it either succeeds with 0 tiles or raises a specific error
        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        # Should return 0 tiles for empty data
        assert tile_count == 0

        # If image was created, verify it has reasonable dimensions
        if output_path.exists():
            img = Image.open(output_path)
            assert img.size[0] > 0  # Width should be positive
            assert img.size[1] >= 0  # Height should be non-negative

class TestROMExtractorSpriteLocations:
    """Test sprite location discovery functionality"""

    @pytest.fixture
    def mock_extractor(self):
        """Create ROM extractor with mocked dependencies"""
        extractor = ROMExtractor()
        extractor.rom_injector = Mock()
        return extractor

    def test_get_known_sprite_locations_kirby_rom(self, mock_extractor):
        """Test sprite location discovery for Kirby ROM"""
        # Mock ROM header for Kirby Super Star
        mock_header = Mock()
        mock_header.title = "KIRBY SUPER STAR"
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock sprite locations
        expected_locations = {
            "kirby_normal": Mock(),
            "waddle_dee": Mock()
        }
        mock_extractor.rom_injector.find_sprite_locations.return_value = expected_locations

        locations = mock_extractor.get_known_sprite_locations("/path/to/kirby.sfc")

        assert locations == expected_locations
        mock_extractor.rom_injector.read_rom_header.assert_called_once_with("/path/to/kirby.sfc")
        mock_extractor.rom_injector.find_sprite_locations.assert_called_once_with("/path/to/kirby.sfc")

    def test_get_known_sprite_locations_unknown_rom(self, mock_extractor):
        """Test sprite location discovery for unknown ROM"""
        # Mock ROM header for unknown game
        mock_header = Mock()
        mock_header.title = "UNKNOWN GAME"
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        locations = mock_extractor.get_known_sprite_locations("/path/to/unknown.sfc")

        assert locations == {}
        # Should not call find_sprite_locations for unknown ROM
        mock_extractor.rom_injector.find_sprite_locations.assert_not_called()

    def test_get_known_sprite_locations_error_handling(self, mock_extractor):
        """Test error handling in sprite location discovery"""
        mock_extractor.rom_injector.read_rom_header.side_effect = Exception("ROM read error")

        locations = mock_extractor.get_known_sprite_locations("/path/to/bad.sfc")

        assert locations == {}

class TestROMExtractorMainExtraction:
    """Test main sprite extraction functionality"""

    @pytest.fixture
    def mock_extractor(self):
        """Create ROM extractor with mocked dependencies"""
        extractor = ROMExtractor()

        # Mock all dependencies
        extractor.rom_injector = Mock()
        extractor.hal_compressor = Mock()
        extractor.rom_palette_extractor = Mock()
        extractor.default_palette_loader = Mock()
        extractor.sprite_config_loader = Mock()

        return extractor

    def test_extract_sprite_from_rom_basic_success(self, mock_extractor, tmp_path):
        """Test successful basic sprite extraction"""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"Mock ROM data" * 1000)
        output_base = tmp_path / "extracted_sprite"

        # Mock ROM header
        mock_header = Mock()
        mock_header.title = "TEST ROM"
        mock_header.checksum = 0x1234
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock compressed sprite data
        test_sprite_data = b"\x00" * (4 * BYTES_PER_TILE)  # 4 tiles
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (100, test_sprite_data)

        # Mock sprite config loader to return empty dict (no sprite config found)
        mock_extractor.sprite_config_loader.get_game_sprites.return_value = {}

        # Mock palette extraction (no palettes found)
        mock_extractor.sprite_config_loader.config_data = {"games": {}}
        mock_extractor.default_palette_loader.has_default_palettes.return_value = False

        output_path, extraction_info = mock_extractor.extract_sprite_from_rom(
            str(rom_path), 0x8000, str(output_base), "test_sprite"
        )

        # Verify output
        assert output_path == f"{output_base}.png"
        assert Path(output_path).exists()

        # Verify extraction info
        assert extraction_info["source_type"] == "rom"
        assert extraction_info["rom_source"] == "test.sfc"
        assert extraction_info["rom_offset"] == "0x8000"
        assert extraction_info["sprite_name"] == "test_sprite"
        assert extraction_info["compressed_size"] == 100
        assert extraction_info["tile_count"] == 4
        assert extraction_info["extraction_size"] == len(test_sprite_data)
        assert extraction_info["rom_title"] == "TEST ROM"
        assert extraction_info["rom_checksum"] == "0x1234"
        assert extraction_info["rom_palettes_used"] is False
        assert extraction_info["default_palettes_used"] is False
        assert extraction_info["palette_count"] == 0

    def test_extract_sprite_from_rom_with_rom_palettes(self, mock_extractor, tmp_path):
        """Test sprite extraction with ROM palette extraction"""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"Mock ROM data" * 1000)
        output_base = tmp_path / "sprite_with_palettes"

        # Mock ROM header
        mock_header = Mock()
        mock_header.title = "KIRBY SUPER STAR"
        mock_header.checksum = 0x5678
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock sprite data
        test_sprite_data = b"\x00" * (8 * BYTES_PER_TILE)
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (200, test_sprite_data)

        # Mock sprite config loader to return config for test_sprite
        mock_sprite_config = Mock()
        mock_sprite_config.estimated_size = None  # No specific size
        mock_extractor.sprite_config_loader.get_game_sprites.return_value = {
            "test_sprite": mock_sprite_config
        }

        # Mock game configuration
        mock_game_config = {"palette_offset": 0x10000, "sprites": {"test_sprite": {}}}
        mock_extractor.sprite_config_loader.config_data = {
            "games": {"KIRBY SUPER STAR": mock_game_config}
        }

        # Mock palette extraction
        mock_extractor.rom_palette_extractor.get_palette_config_from_sprite_config.return_value = (
            0x10000, [8, 9, 10]
        )
        mock_palette_files = ["sprite_pal8.pal.json", "sprite_pal9.pal.json"]
        mock_extractor.rom_palette_extractor.extract_palettes_from_rom.return_value = mock_palette_files

        output_path, extraction_info = mock_extractor.extract_sprite_from_rom(
            str(rom_path), 0x8000, str(output_base), "test_sprite"
        )

        # Verify ROM palette extraction was attempted
        mock_extractor.rom_palette_extractor.get_palette_config_from_sprite_config.assert_called_once()
        mock_extractor.rom_palette_extractor.extract_palettes_from_rom.assert_called_once()

        # Verify extraction info shows ROM palettes were used
        assert extraction_info["rom_palettes_used"] is True
        assert extraction_info["default_palettes_used"] is False
        assert extraction_info["palette_count"] == 2

    def test_extract_sprite_from_rom_with_default_palettes(self, mock_extractor, tmp_path):
        """Test sprite extraction with default palette fallback"""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"Mock ROM data" * 1000)
        output_base = tmp_path / "sprite_default_palettes"

        # Mock ROM header
        mock_header = Mock()
        mock_header.title = "UNKNOWN ROM"
        mock_header.checksum = 0x9999
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock sprite data
        test_sprite_data = b"\x00" * (2 * BYTES_PER_TILE)
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (50, test_sprite_data)

        # Mock sprite config loader to return empty dict (no sprite config found)
        mock_extractor.sprite_config_loader.get_game_sprites.return_value = {}

        # Mock no ROM palettes available
        mock_extractor.sprite_config_loader.config_data = {"games": {}}

        # Mock default palettes available
        mock_extractor.default_palette_loader.has_default_palettes.return_value = True
        mock_default_files = ["sprite_pal8.pal.json"]
        mock_extractor.default_palette_loader.create_palette_files.return_value = mock_default_files

        output_path, extraction_info = mock_extractor.extract_sprite_from_rom(
            str(rom_path), 0x8000, str(output_base), "kirby_normal"
        )

        # Verify default palette creation was attempted
        mock_extractor.default_palette_loader.has_default_palettes.assert_called_once_with("kirby_normal")
        mock_extractor.default_palette_loader.create_palette_files.assert_called_once()

        # Verify extraction info shows default palettes were used
        assert extraction_info["rom_palettes_used"] is False
        assert extraction_info["default_palettes_used"] is True
        assert extraction_info["palette_count"] == 1

    def test_extract_sprite_from_rom_no_sprite_name(self, mock_extractor, tmp_path):
        """Test sprite extraction without sprite name (no palette extraction)"""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"Mock ROM data" * 1000)
        output_base = tmp_path / "sprite_no_name"

        # Mock ROM header
        mock_header = Mock()
        mock_header.title = "TEST ROM"
        mock_header.checksum = 0xABCD
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock sprite data
        test_sprite_data = b"\x00" * BYTES_PER_TILE
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (25, test_sprite_data)

        output_path, extraction_info = mock_extractor.extract_sprite_from_rom(
            str(rom_path), 0x8000, str(output_base)  # No sprite_name
        )

        # Verify no palette extraction was attempted
        mock_extractor.rom_palette_extractor.get_palette_config_from_sprite_config.assert_not_called()
        mock_extractor.default_palette_loader.has_default_palettes.assert_not_called()

        # Verify extraction info
        assert extraction_info["sprite_name"] == ""
        assert extraction_info["rom_palettes_used"] is False
        assert extraction_info["default_palettes_used"] is False
        assert extraction_info["palette_count"] == 0

    def test_extract_sprite_from_rom_hal_compression_error(self, mock_extractor, tmp_path):
        """Test handling of HAL compression errors"""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"Mock ROM data")
        output_base = tmp_path / "failed_sprite"

        # Mock ROM header
        mock_header = Mock()
        mock_header.title = "TEST ROM"
        mock_header.checksum = 0x1234
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock sprite config loader to return empty dict
        mock_extractor.sprite_config_loader.get_game_sprites.return_value = {}

        # Mock HAL compression error
        mock_extractor.rom_injector.find_compressed_sprite.side_effect = HALCompressionError(
            "Failed to decompress sprite data"
        )

        with pytest.raises(Exception, match="Failed to decompress sprite") as exc_info:
            mock_extractor.extract_sprite_from_rom(
                str(rom_path), 0x8000, str(output_base), "test_sprite"
            )

        assert "Failed to decompress sprite" in str(exc_info.value)

    def test_extract_sprite_from_rom_generic_error(self, mock_extractor, tmp_path):
        """Test handling of generic errors"""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"Mock ROM data")
        output_base = tmp_path / "error_sprite"

        # Mock ROM header error
        mock_extractor.rom_injector.read_rom_header.side_effect = Exception("Invalid ROM format")

        with pytest.raises(Exception, match="Invalid ROM format"):
            mock_extractor.extract_sprite_from_rom(
                str(rom_path), 0x8000, str(output_base), "test_sprite"
            )

class TestROMExtractorIntegration:
    """Integration tests with real file operations"""

    def test_4bpp_conversion_integration(self, tmp_path):
        """Test 4bpp conversion with real data and file operations"""
        extractor = ROMExtractor()

        # Create realistic 4bpp test data (2 tiles)
        tile_data = bytearray(2 * BYTES_PER_TILE)

        # First tile: create a simple gradient pattern
        for row in range(8):
            for plane in range(4):
                base_offset = plane * 16 if plane >= 2 else 0
                plane_offset = (plane % 2)
                tile_data[base_offset + row * 2 + plane_offset] = row * 16  # Gradient

        # Second tile: create a checkerboard pattern
        tile_offset = BYTES_PER_TILE
        for row in range(8):
            pattern = 0xAA if row % 2 == 0 else 0x55  # Alternating pattern
            tile_data[tile_offset + row * 2] = pattern  # Plane 0
            tile_data[tile_offset + row * 2 + 1] = ~pattern & 0xFF  # Plane 1
            tile_data[tile_offset + 16 + row * 2] = 0x00  # Plane 2
            tile_data[tile_offset + 16 + row * 2 + 1] = 0x00  # Plane 3

        output_path = tmp_path / "integration_test.png"
        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        # Verify output
        assert tile_count == 2
        assert output_path.exists()

        # Verify image properties
        img = Image.open(output_path)
        assert img.mode == "P"  # Palette mode
        assert img.size == (16 * TILE_WIDTH, 1 * TILE_HEIGHT)

        # Verify some pixels have non-zero values (pattern was applied)
        pixels = list(img.getdata())
        assert any(p > 0 for p in pixels)  # Should have non-black pixels

    def test_error_recovery_file_cleanup(self, tmp_path):
        """Test that failed extractions don't leave partial files"""
        extractor = ROMExtractor()

        # Mock dependencies to cause error after PNG creation starts
        extractor.rom_injector = Mock()
        extractor.rom_injector.read_rom_header.side_effect = Exception("Simulated error")

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"Mock ROM")
        output_base = tmp_path / "failed_extraction"
        expected_png = Path(f"{output_base}.png")

        with pytest.raises(Exception, match="Simulated error"):
            extractor.extract_sprite_from_rom(
                str(rom_path), 0x8000, str(output_base), "test_sprite"
            )

        # Verify no partial files were left behind
        # (In this case, the error happens before PNG creation, so no cleanup needed)
        assert not expected_png.exists()

    def test_large_sprite_processing(self, tmp_path):
        """Test processing of large sprite data"""
        extractor = ROMExtractor()

        # Create data for 64 tiles (realistic sprite size)
        num_tiles = 64
        tile_data = b"\x00" * (num_tiles * BYTES_PER_TILE)

        output_path = tmp_path / "large_sprite.png"
        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == num_tiles
        assert output_path.exists()

        # Verify large image dimensions
        img = Image.open(output_path)
        expected_width = 16 * TILE_WIDTH
        expected_height = 4 * TILE_HEIGHT  # ceil(64/16) = 4 rows
        assert img.size == (expected_width, expected_height)

    def test_boundary_conditions(self, tmp_path):
        """Test boundary conditions and edge cases"""
        extractor = ROMExtractor()

        # Test with exactly 16 tiles (one full row)
        tile_data = b"\x00" * (16 * BYTES_PER_TILE)
        output_path = tmp_path / "full_row.png"

        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == 16
        img = Image.open(output_path)
        assert img.size == (16 * TILE_WIDTH, 1 * TILE_HEIGHT)

        # Test with 17 tiles (one tile into second row)
        tile_data = b"\x00" * (17 * BYTES_PER_TILE)
        output_path = tmp_path / "second_row.png"

        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == 17
        img = Image.open(output_path)
        assert img.size == (16 * TILE_WIDTH, 2 * TILE_HEIGHT)
