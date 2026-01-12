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
    pytest.mark.skip_thread_cleanup(reason="Uses app_context which owns worker threads"),
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.usefixtures("app_context", "mock_hal"),
]


class TestROMExtractorInit:
    """Test ROM extractor initialization"""

    def test_init_creates_components(self):
        """Test that initialization creates all required components"""
        # Use AppContext to get ROMExtractor (session_managers fixture sets up context)
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

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


class TestROMExtractorSpriteLocations:
    """Test sprite location discovery functionality"""

    @pytest.fixture
    def mock_extractor(self):
        """Create ROM extractor with mocked dependencies via AppContext."""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor
        extractor.rom_injector = Mock()
        return extractor

    def test_get_known_sprite_locations_kirby_rom(self, mock_extractor):
        """Test sprite location discovery for Kirby ROM"""
        # Mock ROM header for Kirby Super Star
        mock_header = Mock()
        mock_header.title = "KIRBY SUPER STAR"
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock sprite locations
        expected_locations = {"kirby_normal": Mock(), "waddle_dee": Mock()}
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
        """Create ROM extractor with mocked dependencies via AppContext."""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

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
        mock_header.header_offset = 0  # No SMC header
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock compressed sprite data
        # Returns (compressed_size, decompressed_data, slack_size)
        test_sprite_data = b"\x00" * (4 * BYTES_PER_TILE)  # 4 tiles
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (100, test_sprite_data, 0)

        # Mock sprite config loader to return empty dict (no sprite config found)
        mock_extractor.sprite_config_loader.get_game_sprites.return_value = {}
        mock_extractor.sprite_config_loader.find_game_config.return_value = (None, None)

        # Mock palette extraction (no palettes found)
        mock_extractor.sprite_config_loader.config_data = {"games": {}}
        mock_extractor.default_palette_loader.has_default_palettes.return_value = False
        mock_extractor.default_palette_loader.has_palettes_for_rom_title.return_value = False

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
        mock_header.header_offset = 0  # No SMC header
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock sprite data (compressed_size, decompressed_data, slack_size)
        test_sprite_data = b"\x00" * (8 * BYTES_PER_TILE)
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (200, test_sprite_data, 0)

        # Mock sprite config loader to return config for test_sprite
        mock_sprite_config = Mock()
        mock_sprite_config.estimated_size = None  # No specific size
        mock_extractor.sprite_config_loader.get_game_sprites.return_value = {"test_sprite": mock_sprite_config}

        # Mock game configuration
        mock_game_config = {"palette_offset": 0x10000, "sprites": {"test_sprite": {}}}
        mock_extractor.sprite_config_loader.config_data = {"games": {"KIRBY SUPER STAR": mock_game_config}}
        mock_extractor.sprite_config_loader.find_game_config.return_value = ("KIRBY SUPER STAR", mock_game_config)

        # Mock palette extraction
        mock_extractor.rom_palette_extractor.get_palette_config_from_sprite_config.return_value = (0x10000, [8, 9, 10])
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
        mock_header.header_offset = 0  # No SMC header
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock sprite data (compressed_size, decompressed_data, slack_size)
        test_sprite_data = b"\x00" * (2 * BYTES_PER_TILE)
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (50, test_sprite_data, 0)

        # Mock sprite config loader to return empty dict (no sprite config found)
        mock_extractor.sprite_config_loader.get_game_sprites.return_value = {}
        mock_extractor.sprite_config_loader.find_game_config.return_value = (None, None)

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
        mock_header.header_offset = 0  # No SMC header
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock sprite data (compressed_size, decompressed_data, slack_size)
        test_sprite_data = b"\x00" * BYTES_PER_TILE
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (25, test_sprite_data, 0)

        output_path, extraction_info = mock_extractor.extract_sprite_from_rom(
            str(rom_path),
            0x8000,
            str(output_base),  # No sprite_name
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
        mock_header.header_offset = 0  # No SMC header
        mock_extractor.rom_injector.read_rom_header.return_value = mock_header

        # Mock sprite config loader to return empty dict
        mock_extractor.sprite_config_loader.get_game_sprites.return_value = {}

        # Mock HAL compression error
        mock_extractor.rom_injector.find_compressed_sprite.side_effect = HALCompressionError(
            "Failed to decompress sprite data"
        )

        with pytest.raises(Exception, match="Failed to decompress sprite") as exc_info:
            mock_extractor.extract_sprite_from_rom(str(rom_path), 0x8000, str(output_base), "test_sprite")

        assert "Failed to decompress sprite" in str(exc_info.value)

    def test_extract_sprite_from_rom_generic_error(self, mock_extractor, tmp_path):
        """Test handling of generic errors"""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"Mock ROM data")
        output_base = tmp_path / "error_sprite"

        # Mock ROM header error
        mock_extractor.rom_injector.read_rom_header.side_effect = Exception("Invalid ROM format")

        with pytest.raises(Exception, match="Invalid ROM format"):
            mock_extractor.extract_sprite_from_rom(str(rom_path), 0x8000, str(output_base), "test_sprite")


class TestROMExtractorIntegration:
    """Integration tests with real file operations"""

    def test_4bpp_conversion_integration(self, tmp_path):
        """Test 4bpp conversion with real data and file operations"""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

        # Create realistic 4bpp test data (2 tiles)
        tile_data = bytearray(2 * BYTES_PER_TILE)

        # First tile: create a simple gradient pattern
        for row in range(8):
            for plane in range(4):
                base_offset = plane * 16 if plane >= 2 else 0
                plane_offset = plane % 2
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
        with Image.open(output_path) as img:
            assert img.mode == "P"  # Palette mode
            assert img.size == (16 * TILE_WIDTH, 1 * TILE_HEIGHT)

            # Verify some pixels have non-zero values (pattern was applied)
            pixels = list(img.getdata())
            assert any(p > 0 for p in pixels)  # Should have non-black pixels

    def test_error_recovery_file_cleanup(self, tmp_path):
        """Test that failed extractions don't leave partial files"""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

        # Mock dependencies to cause error after PNG creation starts
        extractor.rom_injector = Mock()
        extractor.rom_injector.read_rom_header.side_effect = Exception("Simulated error")

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"Mock ROM")
        output_base = tmp_path / "failed_extraction"
        expected_png = Path(f"{output_base}.png")

        with pytest.raises(Exception, match="Simulated error"):
            extractor.extract_sprite_from_rom(str(rom_path), 0x8000, str(output_base), "test_sprite")

        # Verify no partial files were left behind
        # (In this case, the error happens before PNG creation, so no cleanup needed)
        assert not expected_png.exists()

    def test_large_sprite_processing(self, tmp_path):
        """Test processing of large sprite data"""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

        # Create data for 64 tiles (realistic sprite size)
        num_tiles = 64
        tile_data = b"\x00" * (num_tiles * BYTES_PER_TILE)

        output_path = tmp_path / "large_sprite.png"
        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == num_tiles
        assert output_path.exists()

        # Verify large image dimensions
        with Image.open(output_path) as img:
            expected_width = 16 * TILE_WIDTH
            expected_height = 4 * TILE_HEIGHT  # ceil(64/16) = 4 rows
            assert img.size == (expected_width, expected_height)

    def test_boundary_conditions(self, tmp_path):
        """Test boundary conditions and edge cases"""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

        # Test with exactly 16 tiles (one full row)
        tile_data = b"\x00" * (16 * BYTES_PER_TILE)
        output_path = tmp_path / "full_row.png"

        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == 16
        with Image.open(output_path) as img:
            assert img.size == (16 * TILE_WIDTH, 1 * TILE_HEIGHT)

        # Test with 17 tiles (one tile into second row)
        tile_data = b"\x00" * (17 * BYTES_PER_TILE)
        output_path = tmp_path / "second_row.png"

        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == 17
        with Image.open(output_path) as img:
            assert img.size == (16 * TILE_WIDTH, 2 * TILE_HEIGHT)


# =============================================================================
# Advanced Tests (consolidated from test_rom_extractor_advanced.py)
# =============================================================================


class TestROMExtractorScanMethods:
    """Test advanced ROM scanning and analysis methods"""

    @pytest.fixture(autouse=True)
    def seed_random(self):
        """Seed random for reproducible test data."""
        import random

        random.seed(42)

    @pytest.fixture
    def extractor(self):
        """Create ROM extractor with mocked dependencies via AppContext."""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor
        extractor.rom_injector = Mock()
        return extractor

    def test_scan_for_sprites_basic(self, extractor, tmp_path):
        """Test basic sprite scanning functionality"""
        rom_path = tmp_path / "test.rom"
        rom_data = b"\x00" * 0x10000  # 64KB ROM
        rom_path.write_bytes(rom_data)

        # Mock successful decompression at specific offsets
        # Returns (compressed_size, decompressed_data, slack_size)
        test_sprite_data = b"\x00" * (32 * BYTES_PER_TILE)  # 32 tiles
        extractor.rom_injector.find_compressed_sprite.side_effect = [
            (256, test_sprite_data, 0),  # First offset - valid
            Exception("No sprite"),  # Second offset - invalid
            (512, test_sprite_data, 0),  # Third offset - valid
        ]

        found_sprites = extractor.scan_for_sprites(str(rom_path), 0x1000, 0x1300, step=0x100)

        assert len(found_sprites) == 2
        assert found_sprites[0]["offset"] == 0x1000
        assert found_sprites[0]["tile_count"] == 32
        assert found_sprites[0]["compressed_size"] == 256
        assert found_sprites[1]["offset"] == 0x1200
        assert found_sprites[1]["compressed_size"] == 512

    def test_scan_for_sprites_end_offset_exceeds_rom(self, extractor, tmp_path):
        """Test scanning when end offset exceeds ROM size"""
        rom_path = tmp_path / "test.rom"
        rom_data = b"\x00" * 0x1000  # 4KB ROM
        rom_path.write_bytes(rom_data)

        # Mock no sprites found
        extractor.rom_injector.find_compressed_sprite.side_effect = Exception("No sprite")

        found_sprites = extractor.scan_for_sprites(
            str(rom_path),
            0x100,
            0x5000,
            step=0x100,  # End offset > ROM size
        )

        # Should adjust end offset and still work
        assert found_sprites == []

    def test_scan_for_sprites_quality_filtering(self, extractor, tmp_path):
        """Test sprite quality assessment during scanning"""
        rom_path = tmp_path / "test.rom"
        rom_data = b"\x00" * 0x10000
        rom_path.write_bytes(rom_data)

        # Create different quality sprite data
        good_sprite = self._create_realistic_sprite_data(64)  # 64 tiles
        bad_sprite = b"\x00" * 100  # Not aligned, too small

        # Returns (compressed_size, decompressed_data, slack_size)
        extractor.rom_injector.find_compressed_sprite.side_effect = [
            (256, good_sprite, 0),
            (50, bad_sprite, 0),  # Should be rejected
        ]

        found_sprites = extractor.scan_for_sprites(str(rom_path), 0x0, 0x200, step=0x100)

        # Only good sprite should be found
        assert len(found_sprites) == 1
        assert found_sprites[0]["tile_count"] == 64
        # Quality assessment is complex, just verify it's calculated
        assert "quality" in found_sprites[0]
        assert 0.0 <= found_sprites[0]["quality"] <= 1.0

    def test_scan_for_sprites_empty_rom(self, extractor, tmp_path):
        """Test scanning an empty ROM file"""
        rom_path = tmp_path / "empty.rom"
        rom_path.write_bytes(b"")

        found_sprites = extractor.scan_for_sprites(str(rom_path), 0, 0x1000)

        assert found_sprites == []

    def test_scan_for_sprites_exception_handling(self, extractor, tmp_path):
        """Test exception handling during scan"""
        rom_path = tmp_path / "test.rom"

        # Simulate file not found
        found_sprites = extractor.scan_for_sprites(str(rom_path), 0, 0x1000)

        assert found_sprites == []

    def _create_realistic_sprite_data(self, num_tiles):
        """Create realistic 4bpp sprite data for testing"""
        sprite_data = bytearray()

        for tile_idx in range(num_tiles):
            # Create varied tile patterns
            tile_type = tile_idx % 5
            tile_data = bytearray(BYTES_PER_TILE)

            if tile_type == 0:
                # Empty tile
                pass
            elif tile_type == 1:
                # Horizontal lines
                for row in range(8):
                    if row % 2 == 0:
                        tile_data[row * 2] = 0xFF
                        tile_data[row * 2 + 1] = 0xFF
                        tile_data[16 + row * 2] = 0xFF
            elif tile_type == 2:
                # Vertical lines
                for row in range(8):
                    tile_data[row * 2] = 0xAA
                    tile_data[row * 2 + 1] = 0xAA
                    tile_data[16 + row * 2] = 0x55
                    tile_data[16 + row * 2 + 1] = 0x55
            elif tile_type == 3:
                # Diagonal pattern
                for row in range(8):
                    tile_data[row * 2] = 1 << row
                    tile_data[16 + row * 2] = 1 << (7 - row)
            else:
                # Solid fill
                for i in range(16):
                    tile_data[i] = 0x88
                for i in range(16, 32):
                    tile_data[i] = 0x44

            sprite_data.extend(tile_data)

        return bytes(sprite_data)


class TestROMExtractorQualityAssessment:
    """Test sprite quality assessment methods"""

    @pytest.fixture
    def extractor(self):
        """Create ROM extractor for testing via AppContext."""
        from core.app_context import get_app_context

        return get_app_context().rom_extractor

    def test_assess_sprite_quality_perfect_sprite(self, extractor):
        """Test quality assessment with perfect sprite data"""
        import random

        random.seed(42)
        # Create well-formed sprite data
        sprite_data = self._create_perfect_sprite_data(64)  # 64 tiles

        score = extractor._assess_sprite_quality(sprite_data)

        assert score > 0.7  # Should have high quality score
        assert score <= 1.0

    def test_assess_sprite_quality_empty_data(self, extractor):
        """Test quality assessment with empty data"""
        score = extractor._assess_sprite_quality(b"")
        assert score == 0.0

    def test_assess_sprite_quality_too_large(self, extractor):
        """Test quality assessment with data that's too large"""
        huge_data = b"\x00" * 100000  # > 64KB
        score = extractor._assess_sprite_quality(huge_data)
        assert score == 0.0

    def test_assess_sprite_quality_misaligned(self, extractor):
        """Test quality assessment with misaligned data"""
        # Create data with bad alignment (not multiple of 32)
        misaligned_data = b"\x00" * (BYTES_PER_TILE * 10 + 20)  # 20 extra bytes
        score = extractor._assess_sprite_quality(misaligned_data)
        assert score == 0.0  # Should reject badly misaligned data

    def test_assess_sprite_quality_low_entropy(self, extractor):
        """Test quality assessment with low entropy data"""
        # All zeros - very low entropy
        low_entropy_data = b"\x00" * (BYTES_PER_TILE * 32)
        score = extractor._assess_sprite_quality(low_entropy_data)
        assert score < 0.5  # Should have low score

    def test_assess_sprite_quality_high_entropy(self, extractor):
        """Test quality assessment with high entropy (random) data"""
        import random

        random.seed(42)
        random_data = bytes(random.randint(0, 255) for _ in range(BYTES_PER_TILE * 32))
        score = extractor._assess_sprite_quality(random_data)
        assert score < 0.7  # Random data should score lower

    def test_assess_sprite_quality_embedded_sprite(self, extractor):
        """Test quality assessment with embedded sprite data"""
        # Create data with sprite embedded at one of the checked offsets
        # The implementation checks offsets: 512, 1024, 2048, 4096
        padding = b"\xff" * 1024  # 1024 bytes of padding
        good_sprite = self._create_perfect_sprite_data(256)  # 256 tiles = 8192 bytes
        embedded_data = padding + good_sprite + (b"\xff" * 1024)

        score = extractor._assess_sprite_quality(embedded_data, check_embedded=True)

        # Just verify the function runs and returns a valid score
        assert 0.0 <= score <= 1.0

    def test_assess_sprite_quality_small_sprite(self, extractor):
        """Test quality assessment with small sprite (< 16 tiles)"""
        small_sprite = self._create_perfect_sprite_data(8)  # Only 8 tiles
        score = extractor._assess_sprite_quality(small_sprite)
        # Small sprites get penalized but may still score okay if well-formed
        assert 0.0 <= score <= 1.0
        # Just verify it's less than a larger sprite would score
        large_sprite = self._create_perfect_sprite_data(64)
        large_score = extractor._assess_sprite_quality(large_sprite)
        assert score < large_score  # Small sprite should score lower than large

    def _create_perfect_sprite_data(self, num_tiles):
        """Create perfect sprite data with good characteristics"""
        sprite_data = bytearray()

        for tile_idx in range(num_tiles):
            tile_data = bytearray(BYTES_PER_TILE)

            # Create varied but structured patterns
            pattern_type = tile_idx % 8

            if pattern_type == 0:
                # Empty tile (some empty tiles are normal)
                pass
            elif pattern_type == 1:
                # Solid color
                for i in range(16):
                    tile_data[i] = 0x88
                for i in range(16, 32):
                    tile_data[i] = 0x44
            elif pattern_type == 2:
                # Horizontal gradient
                for row in range(8):
                    val = row * 32
                    tile_data[row * 2] = val
                    tile_data[row * 2 + 1] = val // 2
                    tile_data[16 + row * 2] = val // 4
            elif pattern_type == 3:
                # Checkerboard
                for row in range(8):
                    tile_data[row * 2] = 0xAA if row % 2 == 0 else 0x55
                    tile_data[row * 2 + 1] = 0x55 if row % 2 == 0 else 0xAA
                    tile_data[16 + row * 2] = 0xF0 if row % 2 == 0 else 0x0F
            elif pattern_type == 4:
                # Diagonal lines
                for row in range(8):
                    tile_data[row * 2] = 1 << row
                    tile_data[row * 2 + 1] = 1 << (7 - row)
                    tile_data[16 + row * 2] = 0x80 >> row
            elif pattern_type == 5:
                # Cross pattern
                for row in range(8):
                    if row == 4:
                        tile_data[row * 2] = 0xFF
                        tile_data[16 + row * 2] = 0xFF
                    else:
                        tile_data[row * 2] = 0x10
                        tile_data[16 + row * 2] = 0x10
            elif pattern_type == 6:
                # Border
                for row in range(8):
                    if row in {0, 7}:
                        tile_data[row * 2] = 0xFF
                        tile_data[16 + row * 2] = 0xFF
                    else:
                        tile_data[row * 2] = 0x81
                        tile_data[16 + row * 2] = 0x81
            else:
                # Varied pattern
                for i in range(32):
                    tile_data[i] = (tile_idx * 7 + i * 3) % 128

            sprite_data.extend(tile_data)

        return bytes(sprite_data)


class TestROMExtractorValidationMethods:
    """Test tile and data validation methods"""

    @pytest.fixture
    def extractor(self):
        """Create ROM extractor for testing via AppContext."""
        from core.app_context import get_app_context

        return get_app_context().rom_extractor

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

    def test_has_4bpp_characteristics_no_variety(self, extractor):
        """Test 4bpp characteristics check with no variety"""
        # All zeros - no bitplane variety
        uniform_data = b"\x00" * (BYTES_PER_TILE * 2)
        assert extractor._has_4bpp_characteristics(uniform_data) is False

    def test_calculate_entropy_empty(self, extractor):
        """Test entropy calculation with empty data"""
        entropy = extractor._calculate_entropy(b"")
        assert entropy == 0.0

    def test_calculate_entropy_uniform(self, extractor):
        """Test entropy calculation with uniform data"""
        uniform_data = b"\x42" * 1024  # All same byte
        entropy = extractor._calculate_entropy(uniform_data)
        assert entropy == 0.0  # No entropy in uniform data

    def test_calculate_entropy_random(self, extractor):
        """Test entropy calculation with high entropy data"""
        # Create data with all byte values equally distributed
        high_entropy_data = bytes(range(256)) * 4  # Each byte appears 4 times
        entropy = extractor._calculate_entropy(high_entropy_data)
        assert 7.9 < entropy < 8.1  # Should be close to 8 bits

    def test_calculate_entropy_moderate(self, extractor):
        """Test entropy calculation with moderate entropy"""
        # Create data with limited byte values
        moderate_data = b"\x00\x01\x02\x03" * 256
        entropy = extractor._calculate_entropy(moderate_data)
        assert 1.5 < entropy < 2.5  # Should be around 2 bits

    def test_validate_4bpp_tile_valid(self, extractor):
        """Test tile validation with valid tile"""
        # Create a valid tile with good structure
        tile_data = bytearray(32)
        # Add variety to bitplanes
        for i in range(8):
            tile_data[i * 2] = 0xAA
            tile_data[i * 2 + 1] = 0x55
            tile_data[16 + i * 2] = 0xF0
            tile_data[16 + i * 2 + 1] = 0x0F

        assert extractor._validate_4bpp_tile(bytes(tile_data)) is True

    def test_validate_4bpp_tile_wrong_size(self, extractor):
        """Test tile validation with wrong size"""
        wrong_size = b"\x00" * 16  # Too small
        assert extractor._validate_4bpp_tile(wrong_size) is False

    def test_validate_4bpp_tile_empty(self, extractor):
        """Test tile validation with empty tile"""
        empty_tile = b"\x00" * 32
        assert extractor._validate_4bpp_tile(empty_tile) is False

    def test_validate_4bpp_tile_full(self, extractor):
        """Test tile validation with full tile"""
        full_tile = b"\xff" * 32
        assert extractor._validate_4bpp_tile(full_tile) is False

    def test_validate_4bpp_tile_no_correlation(self, extractor):
        """Test tile validation with no bitplane correlation"""
        tile_data = bytearray(32)
        # First bitplanes all zero
        for i in range(16):
            tile_data[i] = 0x00
        # Second bitplanes all full (no correlation)
        for i in range(16, 32):
            tile_data[i] = 0xFF

        assert extractor._validate_4bpp_tile(bytes(tile_data)) is False

    def test_has_graphics_patterns_valid(self, extractor):
        """Test graphics pattern detection with valid sprite data"""
        import random

        random.seed(42)
        # Create tiles with some similarity (sharing some bytes)
        tile1 = bytearray(32)
        # First half similar, second half different
        for i in range(16):
            tile1[i] = 0xAA
        for i in range(16, 32):
            tile1[i] = i

        tile2 = bytearray(32)
        # Share some bytes with tile1 (about 12 bytes similar)
        for i in range(16):
            tile2[i] = 0xAA  # Same as tile1
        for i in range(16, 32):
            tile2[i] = i + 16  # Different from tile1

        tile3 = bytearray(32)
        # Another variation with partial similarity
        for i in range(8):
            tile3[i] = 0xAA  # Partially same
        for i in range(8, 32):
            tile3[i] = i * 2

        pattern_data = bytes(tile1 + tile2 + tile3 + tile1)

        assert extractor._has_graphics_patterns(pattern_data) is True

    def test_has_graphics_patterns_random(self, extractor):
        """Test graphics pattern detection with random data"""
        import random

        random.seed(42)
        random_data = bytes(random.randint(0, 255) for _ in range(256))
        assert extractor._has_graphics_patterns(random_data) is False

    def test_has_graphics_patterns_too_small(self, extractor):
        """Test graphics pattern detection with insufficient data"""
        small_data = b"\x00" * 32
        assert extractor._has_graphics_patterns(small_data) is False


# =============================================================================
# Comprehensive Scanning Tests (consolidated from test_rom_scanning_comprehensive.py)
# =============================================================================


class CustomMockHALCompressor:
    """Custom HAL compressor for ROM scanning tests with specific size control.

    Note: The ROMInjector.find_compressed_sprite() creates a window from the ROM
    and passes offset=0 to the HAL compressor. This mock identifies sprites by
    checking the window content's first bytes (the "signature" at the start of
    each configured offset's window).
    """

    def __init__(self):
        from tests.infrastructure.mock_hal import MockHALCompressor

        self._base = MockHALCompressor()
        self._sprite_responses: dict[bytes, tuple[int, bytes]] = {}  # signature -> (compressed_size, decompressed_data)
        self._default_response: tuple[int, bytes] | None = None

    def configure_sprite_response(self, signature: bytes, compressed_size: int, decompressed_data: bytes):
        """Configure response for data windows starting with given signature."""
        self._sprite_responses[signature] = (compressed_size, decompressed_data)

    def set_default_response(self, compressed_size: int, decompressed_data: bytes):
        """Set default response for any decompression request (used for simple tests)."""
        self._default_response = (compressed_size, decompressed_data)

    def decompress_from_rom(self, rom_path: str, offset: int, output_path: str | None = None) -> bytes:
        """Return configured sprite data or raise exception.

        Matches responses by reading the first bytes of the ROM window file
        and comparing to configured signatures.
        """
        # If we have a default response configured, always return it
        if self._default_response is not None:
            _, decompressed_data = self._default_response
            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(decompressed_data)
            return decompressed_data

        # Read signature from the temp ROM window file
        try:
            with Path(rom_path).open("rb") as f:
                file_signature = f.read(4)  # First 4 bytes as signature
        except OSError:
            raise Exception("No sprite found") from None

        # Check if signature matches any configured response
        if file_signature in self._sprite_responses:
            _, decompressed_data = self._sprite_responses[file_signature]
            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(decompressed_data)
            return decompressed_data

        # Default behavior - raise exception for unknown signatures
        raise Exception("No sprite found")


class TestROMScanningComprehensive:
    """Test ROM scanning functionality with comprehensive coverage"""

    @pytest.fixture
    def rom_extractor(self):
        """Create a ROM extractor instance via AppContext."""
        from core.app_context import get_app_context

        return get_app_context().rom_extractor

    @pytest.fixture
    def mock_rom_file(self, tmp_path):
        """Create a mock ROM file for testing.

        Each sprite offset gets a unique 4-byte signature so the mock HAL
        can distinguish between different scan positions.

        IMPORTANT: Includes UUID at offset 0 to ensure unique content hash per test,
        preventing cache collisions between parallel tests.
        """
        import uuid

        rom_path = tmp_path / "test_rom.sfc"
        # Create a 128KB ROM with some test data
        rom_data = bytearray(128 * 1024)

        # Add unique identifier at start to prevent cache collisions
        # This ensures each test's ROM has a unique SHA-256 hash
        unique_id = uuid.uuid4().bytes
        rom_data[0:16] = unique_id

        # Add compressed sprite-like data at known offsets with UNIQUE signatures
        # These signatures are used by CustomMockHALCompressor to match responses
        test_offsets = [0x8000, 0x10000, 0x18000]
        signatures = [b"\x01\x01\x01\x01", b"\x02\x02\x02\x02", b"\x03\x03\x03\x03"]

        for i, (offset, sig) in enumerate(zip(test_offsets, signatures, strict=True)):
            # Add unique signature at start of each sprite location
            rom_data[offset : offset + 4] = sig
            # Add some tile-like data
            for j in range(offset + 4, offset + 100):
                rom_data[j] = (i * 16 + j % 16) & 0xFF

        rom_path.write_bytes(rom_data)
        return str(rom_path)

    def test_scan_for_sprites_basic_functionality(self, rom_extractor, mock_rom_file):
        """Test basic sprite scanning functionality"""
        # Set up custom HAL compressor with specific responses
        mock_hal = CustomMockHALCompressor()

        # Configure responses using signatures that match mock_rom_file
        # (16 tiles = 512 bytes)
        sprite_data = b"\x00" * 512
        mock_hal.configure_sprite_response(b"\x01\x01\x01\x01", 64, sprite_data)
        mock_hal.configure_sprite_response(b"\x02\x02\x02\x02", 64, sprite_data)
        mock_hal.configure_sprite_response(b"\x03\x03\x03\x03", 64, sprite_data)

        # Replace the HAL compressor
        rom_extractor.rom_injector.hal_compressor = mock_hal

        # Run the scan
        results = rom_extractor.scan_for_sprites(mock_rom_file, start_offset=0x8000, end_offset=0x20000, step=0x1000)

        # Verify results
        assert len(results) == 3
        assert all(sprite["tile_count"] == 16 for sprite in results)
        # Note: compressed_size comes from _estimate_compressed_size, not our mock
        # So we verify decompressed_size instead
        assert all(sprite["decompressed_size"] == 512 for sprite in results)

        # Check that offsets are correct
        found_offsets = [sprite["offset"] for sprite in results]
        assert 0x8000 in found_offsets
        assert 0x10000 in found_offsets
        assert 0x18000 in found_offsets

    def test_scan_for_sprites_end_offset_exceeds_rom_comprehensive(self, rom_extractor, mock_rom_file):
        """Test scanning when end offset exceeds ROM size"""
        # Set up HAL compressor that returns no sprites
        mock_hal = CustomMockHALCompressor()
        rom_extractor.rom_injector.hal_compressor = mock_hal

        # Try to scan beyond ROM size
        results = rom_extractor.scan_for_sprites(
            mock_rom_file,
            start_offset=0x10000,
            end_offset=0x100000,  # Way beyond 128KB ROM
            step=0x1000,
        )

        # Should complete without error and return empty results
        assert isinstance(results, list)

    def test_scan_for_sprites_quality_filtering_comprehensive(self, rom_extractor, mock_rom_file):
        """Test that sprites are sorted by quality score"""
        from unittest.mock import patch

        # Set up custom HAL compressor with different sprite data
        # Signatures match mock_rom_file: 0x8000=\x01..., 0x10000=\x02..., 0x18000=\x03...
        mock_hal = CustomMockHALCompressor()
        mock_hal.configure_sprite_response(b"\x01\x01\x01\x01", 32, b"\x00" * 512)  # Good sprite
        mock_hal.configure_sprite_response(b"\x02\x02\x02\x02", 48, b"\x11" * 512)  # Better sprite
        mock_hal.configure_sprite_response(b"\x03\x03\x03\x03", 16, b"\x22" * 512)  # Different sprite

        rom_extractor.rom_injector.hal_compressor = mock_hal

        # Mock quality assessment (still need this since it's on rom_extractor)
        with patch.object(rom_extractor, "_assess_sprite_quality") as mock_quality:

            def mock_assess_quality(sprite_data):
                if sprite_data == b"\x11" * 512:
                    return 95.0  # Highest quality
                if sprite_data == b"\x00" * 512:
                    return 85.0  # Medium quality
                if sprite_data == b"\x22" * 512:
                    return 75.0  # Lower quality
                return 0.0

            mock_quality.side_effect = mock_assess_quality

            results = rom_extractor.scan_for_sprites(
                mock_rom_file, start_offset=0x8000, end_offset=0x20000, step=0x1000
            )

            # Verify results are sorted by quality (highest first)
            assert len(results) == 3
            assert results[0]["quality"] == 95.0  # Best quality first
            assert results[1]["quality"] == 85.0
            assert results[2]["quality"] == 75.0

    def test_scan_for_sprites_alignment_validation(self, rom_extractor, mock_rom_file):
        """Test sprite alignment validation during scanning"""
        from unittest.mock import patch

        # Set up custom HAL compressor with different alignment scenarios
        # Signatures match mock_rom_file: 0x8000=\x01..., 0x10000=\x02..., 0x18000=\x03...
        mock_hal = CustomMockHALCompressor()
        mock_hal.configure_sprite_response(b"\x01\x01\x01\x01", 64, b"\x00" * 512)  # Perfect alignment (16 tiles)
        mock_hal.configure_sprite_response(
            b"\x02\x02\x02\x02", 68, b"\x11" * 520
        )  # Minor misalignment (16 tiles + 8 extra)
        mock_hal.configure_sprite_response(b"\x03\x03\x03\x03", 16, b"\x22" * 32)  # Too small (1 tile)

        rom_extractor.rom_injector.hal_compressor = mock_hal

        with patch.object(rom_extractor, "_assess_sprite_quality", return_value=80.0):
            results = rom_extractor.scan_for_sprites(
                mock_rom_file, start_offset=0x8000, end_offset=0x20000, step=0x1000
            )

            # Should only find 2 sprites (16+ tiles), not the 1-tile sprite
            assert len(results) == 2

            # Check alignment status
            perfect_sprite = next((s for s in results if s["offset"] == 0x8000), None)
            misaligned_sprite = next((s for s in results if s["offset"] == 0x10000), None)

            assert perfect_sprite is not None
            assert perfect_sprite["alignment"] == "perfect"
            assert perfect_sprite["tile_count"] == 16

            assert misaligned_sprite is not None
            assert misaligned_sprite["alignment"] == "8 extra bytes"
            assert misaligned_sprite["tile_count"] == 16

    def test_scan_for_sprites_large_range_completion(self, rom_extractor, mock_rom_file):
        """Test that scanning completes successfully over a large range"""
        # Set up HAL compressor that returns no sprites
        mock_hal = CustomMockHALCompressor()
        rom_extractor.rom_injector.hal_compressor = mock_hal

        # Run a scan that should complete without errors
        results = rom_extractor.scan_for_sprites(
            mock_rom_file,
            start_offset=0x0,
            end_offset=0x20000,  # Large range
            step=0x1000,  # Reasonable step size
        )

        # Should complete and return empty list (no sprites found)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_scan_for_sprites_exception_handling_comprehensive(self, rom_extractor):
        """Test scanning with invalid ROM file"""
        # Try to scan non-existent file
        results = rom_extractor.scan_for_sprites(
            "/nonexistent/rom.sfc", start_offset=0x8000, end_offset=0x10000, step=0x1000
        )

        # Should return empty list, not crash
        assert results == []

    def test_scan_for_sprites_empty_results(self, rom_extractor, mock_rom_file):
        """Test scanning when no valid sprites are found"""
        # Set up HAL compressor that always fails
        mock_hal = CustomMockHALCompressor()
        rom_extractor.rom_injector.hal_compressor = mock_hal

        results = rom_extractor.scan_for_sprites(mock_rom_file, start_offset=0x8000, end_offset=0x10000, step=0x1000)

        assert results == []


class TestROMSpriteQualityAssessmentComprehensive:
    """Test ROM sprite quality assessment functionality"""

    @pytest.fixture
    def rom_extractor(self):
        """Create a ROM extractor instance via AppContext."""
        from core.app_context import get_app_context

        return get_app_context().rom_extractor

    def test_assess_sprite_quality_perfect_sprite_comprehensive(self, rom_extractor):
        """Test quality assessment for a perfect sprite"""
        # Create sprite data that should score highly
        # 16 tiles (512 bytes) with good variety and patterns
        sprite_data = bytearray(512)
        for i in range(512):
            sprite_data[i] = (i // 32) % 16  # Different values per tile

        quality = rom_extractor._assess_sprite_quality(bytes(sprite_data))

        # Quality should be a float between 0.0 and 1.0
        assert isinstance(quality, float)
        assert 0.0 <= quality <= 1.0
        # Good sprite should have decent quality
        assert quality > 0.5

    def test_assess_sprite_quality_empty_data_comprehensive(self, rom_extractor):
        """Test quality assessment for empty sprite data"""
        sprite_data = b"\x00" * 512  # All zeros

        quality = rom_extractor._assess_sprite_quality(sprite_data)

        # Empty data should have low quality
        assert isinstance(quality, float)
        assert 0.0 <= quality <= 1.0
        assert quality < 0.5  # Should be low quality

    def test_assess_sprite_quality_random_data_comprehensive(self, rom_extractor):
        """Test quality assessment for random-looking data"""
        import random

        random.seed(42)  # Reproducible random
        sprite_data = bytes([random.randint(0, 255) for _ in range(512)])

        quality = rom_extractor._assess_sprite_quality(sprite_data)

        # Random data should have moderate quality (high entropy but no patterns)
        assert isinstance(quality, float)
        assert 0.0 <= quality <= 1.0

    def test_assess_sprite_quality_small_data_comprehensive(self, rom_extractor):
        """Test quality assessment for very small sprite data"""
        sprite_data = b"\x01\x02\x03\x04" * 8  # 32 bytes (1 tile)

        quality = rom_extractor._assess_sprite_quality(sprite_data)

        # Small data should still return valid quality score
        assert isinstance(quality, float)
        assert 0.0 <= quality <= 1.0

    def test_assess_sprite_quality_with_embedded_check_comprehensive(self, rom_extractor):
        """Test quality assessment with embedded sprite detection"""
        # Create data that looks like it has an embedded sprite pattern
        sprite_data = b"\x00" * 256 + b"\x01\x02\x03\x04" * 64  # Pattern in second half

        quality_with_embedded = rom_extractor._assess_sprite_quality(sprite_data, check_embedded=True)
        quality_without_embedded = rom_extractor._assess_sprite_quality(sprite_data, check_embedded=False)

        # Both should return valid scores
        assert isinstance(quality_with_embedded, float)
        assert isinstance(quality_without_embedded, float)
        assert 0.0 <= quality_with_embedded <= 1.0
        assert 0.0 <= quality_without_embedded <= 1.0


class TestROMExtractorAdvancedFeatures:
    """Test advanced ROM extractor features for better coverage"""

    @pytest.fixture
    def rom_extractor(self):
        """Create a ROM extractor instance via AppContext."""
        from core.app_context import get_app_context

        return get_app_context().rom_extractor

    @pytest.fixture
    def temp_rom_with_header(self, tmp_path):
        """Create a ROM with SNES header for testing"""
        rom_path = tmp_path / "test_rom_with_header.sfc"
        rom_data = bytearray(64 * 1024)  # 64KB ROM

        # Add SNES ROM header at 0x7FC0
        header_offset = 0x7FC0
        rom_data[header_offset : header_offset + 21] = b"TEST ROM TITLE      "  # 21 chars
        rom_data[header_offset + 21] = 0x20  # ROM type
        rom_data[header_offset + 22] = 0x09  # ROM size (512KB)
        rom_data[header_offset + 23] = 0x00  # SRAM size

        # Add checksum (simplified)
        rom_data[header_offset + 28 : header_offset + 30] = b"\x34\x12"  # Checksum
        rom_data[header_offset + 30 : header_offset + 32] = b"\xcb\xed"  # Complement

        rom_path.write_bytes(rom_data)
        return str(rom_path)

    def test_get_known_sprite_locations_with_kirby_rom(self, rom_extractor, tmp_path):
        """Test getting known sprite locations for a Kirby ROM"""
        from unittest.mock import patch

        from core.rom_injector import SpritePointer

        # Create a ROM with KIRBY in the title
        rom_path = tmp_path / "kirby_test.sfc"
        rom_data = bytearray(64 * 1024)  # 64KB ROM

        # Add SNES ROM header with KIRBY title at 0x7FC0
        header_offset = 0x7FC0
        rom_data[header_offset : header_offset + 21] = b"KIRBY SUPER STAR    "  # 21 chars
        rom_data[header_offset + 21] = 0x20  # ROM type
        rom_data[header_offset + 22] = 0x09  # ROM size (512KB)
        rom_data[header_offset + 23] = 0x00  # SRAM size

        # Add checksum (simplified)
        rom_data[header_offset + 28 : header_offset + 30] = b"\x34\x12"  # Checksum
        rom_data[header_offset + 30 : header_offset + 32] = b"\xcb\xed"  # Complement

        rom_path.write_bytes(rom_data)

        # Mock the rom injector's find_sprite_locations method
        # Note: This is still using patch because find_sprite_locations is not HAL-related
        with patch.object(rom_extractor.rom_injector, "find_sprite_locations") as mock_find_locations:
            mock_locations = {
                "kirby_normal": SpritePointer(offset=0x8000, bank=0x10, address=0x0000),
                "kirby_flying": SpritePointer(offset=0x9000, bank=0x12, address=0x1000),
            }
            mock_find_locations.return_value = mock_locations

            locations = rom_extractor.get_known_sprite_locations(str(rom_path))

            # Should return the mocked sprite locations
            assert isinstance(locations, dict)
            assert len(locations) == 2
            assert "kirby_normal" in locations
            assert "kirby_flying" in locations
            assert locations["kirby_normal"].offset == 0x8000
            assert locations["kirby_flying"].offset == 0x9000

    def test_get_known_sprite_locations_unknown_rom(self, rom_extractor, temp_rom_with_header):
        """Test getting known sprite locations for unknown ROM"""
        # The temp_rom_with_header doesn't have "KIRBY" in title, so should return empty
        locations = rom_extractor.get_known_sprite_locations(temp_rom_with_header)

        # Should return empty dict for unknown ROM
        assert isinstance(locations, dict)
        assert len(locations) == 0

    def test_get_known_sprite_locations_file_error(self, rom_extractor):
        """Test getting known sprite locations with file error"""
        locations = rom_extractor.get_known_sprite_locations("/nonexistent/rom.sfc")

        # Should return empty dict on file error
        assert isinstance(locations, dict)
        assert len(locations) == 0
