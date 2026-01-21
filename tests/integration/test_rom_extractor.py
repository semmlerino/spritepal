"""
Integration tests for ROM sprite extraction functionality.

Tests with real file operations and minimal mocking.
Merged from tests/unit/test_rom_extractor_logic.py during test suite refactoring.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from core.hal_compression import HALCompressionError
from utils.constants import BYTES_PER_TILE, TILE_HEIGHT, TILE_WIDTH

# Constants for test helpers
DEFAULT_TILES_PER_ROW = 16


def create_test_rom_with_header(
    title: str,
    checksum: int,
    rom_size: int = 64 * 1024,
    smc_header: bool = False,
) -> bytes:
    """Create test ROM with valid SNES header at 0x7FC0 (LoROM).

    Args:
        title: ROM title (max 21 chars)
        checksum: 16-bit checksum value
        rom_size: Total ROM size in bytes (default 64KB)
        smc_header: If True, prepend 512-byte SMC header

    Returns:
        ROM data bytes with valid header structure
    """
    # Create ROM data
    rom_data = bytearray(rom_size)

    # Add SNES header at 0x7FC0 (LoROM standard)
    header_offset = 0x7FC0
    title_bytes = title.encode("ascii")[:21].ljust(21, b" ")
    rom_data[header_offset : header_offset + 21] = title_bytes
    rom_data[header_offset + 21] = 0x20  # ROM type (LoROM)
    rom_data[header_offset + 22] = 0x09  # ROM size code
    rom_data[header_offset + 23] = 0x00  # SRAM size

    # Add checksum and complement (checksum ^ complement = 0xFFFF)
    complement = 0xFFFF ^ checksum
    rom_data[header_offset + 28 : header_offset + 30] = complement.to_bytes(2, "little")
    rom_data[header_offset + 30 : header_offset + 32] = checksum.to_bytes(2, "little")

    if smc_header:
        return bytes(512) + bytes(rom_data)
    return bytes(rom_data)


def verify_png_output(
    png_path: Path,
    *,
    expect_indexed: bool = True,
    expect_non_zero: bool = False,
    min_tiles: int = 1,
) -> int:
    """Verify PNG output meets expectations.

    Args:
        png_path: Path to PNG file
        expect_indexed: If True, verify PNG is indexed mode ("P")
        expect_non_zero: If True, verify not all pixels are zero
        min_tiles: Minimum expected tile count

    Returns:
        Number of tiles in the image

    Raises:
        AssertionError: If any validation fails
    """
    assert png_path.exists(), f"PNG not created: {png_path}"

    with Image.open(png_path) as img:
        if expect_indexed:
            assert img.mode == "P", f"Wrong mode: {img.mode}, expected P"

        # Calculate tiles from dimensions
        tiles_per_row = DEFAULT_TILES_PER_ROW
        expected_width = tiles_per_row * TILE_WIDTH

        assert img.width == expected_width, f"Wrong width: {img.width}, expected {expected_width}"
        assert img.height % TILE_HEIGHT == 0, f"Height {img.height} not multiple of {TILE_HEIGHT}"

        num_rows = img.height // TILE_HEIGHT
        total_tiles = num_rows * tiles_per_row

        assert total_tiles >= min_tiles, f"Too few tiles: {total_tiles}, expected >= {min_tiles}"

        if expect_non_zero:
            pixels = list(img.getdata())
            assert any(p > 0 for p in pixels), "All pixels are zero"

        return total_tiles


# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Uses app_context which owns worker threads"),
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.usefixtures("app_context", "mock_hal"),
]


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
        from unittest.mock import Mock

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

    def test_boundary_sprite_size(self, tmp_path):
        """Test edge case with minimum valid sprite size"""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

        # Test with exactly 1 tile (minimum valid sprite)
        tile_data = b"\x00" * BYTES_PER_TILE
        output_path = tmp_path / "single_tile.png"

        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == 1
        assert output_path.exists()
        with Image.open(output_path) as img:
            assert img.size == (16 * TILE_WIDTH, 1 * TILE_HEIGHT)


# Tests merged from tests/unit/test_rom_extractor_logic.py


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
    """Tests for main sprite extraction workflow.

    Uses real ROMExtractor components with mock HAL (for speed).
    Verifies complete extraction workflow including file I/O, PNG generation,
    and palette extraction by validating actual output files.
    """

    def test_extract_sprite_from_rom_basic_success(self, app_context, tmp_path):
        """Test successful sprite extraction with real components.

        Uses real ROM header parsing, file I/O, and PNG conversion.
        Only mocks the HAL decompression step (tested separately).
        """
        # Create real ROM with proper header
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(
            create_test_rom_with_header(
                title="TEST ROM",
                checksum=0x1234,
            )
        )
        output_base = tmp_path / "extracted_sprite"

        extractor = app_context.rom_extractor

        # Mock HAL decompression (returns 4 tiles of test data)
        test_sprite_data = b"\x00" * (4 * BYTES_PER_TILE)
        with patch.object(
            extractor.rom_injector,
            "find_compressed_sprite",
            return_value=(100, test_sprite_data, 0),
        ):
            output_path, extraction_info = extractor.extract_sprite_from_rom(
                str(rom_path), 0x8000, str(output_base), "test_sprite"
            )

        # Verify PNG output (real file I/O and conversion)
        assert output_path == f"{output_base}.png"
        verify_png_output(Path(output_path), min_tiles=1)

        # Verify metadata
        assert extraction_info["source_type"] == "rom"
        assert extraction_info["rom_source"] == "test.sfc"
        assert extraction_info["rom_offset"] == "0x8000"
        assert extraction_info["sprite_name"] == "test_sprite"
        assert extraction_info["tile_count"] == 4  # 4 tiles of test data
        assert extraction_info["rom_title"].strip() == "TEST ROM"
        assert extraction_info["rom_checksum"] == "0x1234"
        assert extraction_info["rom_palettes_used"] is False
        assert extraction_info["default_palettes_used"] is False
        assert extraction_info["palette_count"] == 0

    def test_extract_sprite_from_rom_with_rom_palettes(self, app_context, tmp_path):
        """Test sprite extraction with ROM palette extraction."""
        # Create ROM with Kirby header (known game)
        rom_path = tmp_path / "kirby.sfc"
        rom_path.write_bytes(
            create_test_rom_with_header(
                title="KIRBY SUPER STAR",
                checksum=0x5678,
            )
        )
        output_base = tmp_path / "sprite_with_palettes"

        extractor = app_context.rom_extractor

        # Mock sprite config to return game with palette configuration
        game_config = {
            "palette_offset": 0x10000,
            "sprites": {"test_sprite": {"palettes": [8, 9, 10]}},
        }

        # Create fake palette files that extraction would produce
        palette_files = []
        for i in [8, 9, 10]:
            pal_file = tmp_path / f"sprite_with_palettes_pal{i}.json"
            pal_file.write_text('{"colors": [0, 1, 2]}')
            palette_files.append(str(pal_file))

        # Mock HAL decompression (returns 8 tiles of test data)
        test_sprite_data = b"\x00" * (8 * BYTES_PER_TILE)

        with (
            patch.object(
                extractor.rom_injector,
                "find_compressed_sprite",
                return_value=(200, test_sprite_data, 0),
            ),
            patch.object(extractor.sprite_config_loader, "find_game_config") as mock_find_config,
            patch.object(
                extractor.rom_palette_extractor, "get_palette_config_from_sprite_config"
            ) as mock_get_palette_config,
            patch.object(extractor.rom_palette_extractor, "extract_palettes_from_rom") as mock_extract_palettes,
        ):
            mock_find_config.return_value = ("KIRBY SUPER STAR", game_config)
            mock_get_palette_config.return_value = (0x10000, [8, 9, 10])
            mock_extract_palettes.return_value = palette_files

            output_path, extraction_info = extractor.extract_sprite_from_rom(
                str(rom_path), 0x8000, str(output_base), "test_sprite"
            )

        # Verify PNG created (real file I/O and conversion)
        verify_png_output(Path(output_path), min_tiles=1)

        # Verify ROM palette extraction was called
        mock_get_palette_config.assert_called_once()
        mock_extract_palettes.assert_called_once()

        # Verify metadata shows ROM palettes were used
        assert extraction_info["rom_palettes_used"] is True
        assert extraction_info["default_palettes_used"] is False
        assert extraction_info["palette_count"] == 3

    def test_extract_sprite_from_rom_with_default_palettes(self, app_context, tmp_path):
        """Test sprite extraction with default palette fallback."""
        # Create ROM with unknown title (no sprite config)
        rom_path = tmp_path / "unknown.sfc"
        rom_path.write_bytes(
            create_test_rom_with_header(
                title="UNKNOWN GAME",
                checksum=0x9ABC,
            )
        )
        output_base = tmp_path / "sprite_with_defaults"

        extractor = app_context.rom_extractor

        # Create fake default palette files
        default_palette_files = [str(tmp_path / "default_pal.json")]
        Path(default_palette_files[0]).write_text('{"colors": [0, 1, 2]}')

        # Mock HAL decompression (returns 2 tiles of test data)
        test_sprite_data = b"\x00" * (2 * BYTES_PER_TILE)

        # Mock: no ROM palettes (game config returns None), but default palettes exist
        with (
            patch.object(
                extractor.rom_injector,
                "find_compressed_sprite",
                return_value=(50, test_sprite_data, 0),
            ),
            patch.object(extractor.sprite_config_loader, "find_game_config", return_value=(None, None)),
            patch.object(
                extractor.default_palette_loader, "has_default_palettes", return_value=True
            ) as mock_has_defaults,
            patch.object(
                extractor.default_palette_loader, "create_palette_files", return_value=default_palette_files
            ) as mock_create_defaults,
        ):
            output_path, extraction_info = extractor.extract_sprite_from_rom(
                str(rom_path), 0x8000, str(output_base), "kirby_normal"
            )

        # Verify PNG created (real file I/O and conversion)
        verify_png_output(Path(output_path), min_tiles=1)

        # Verify default palette creation was called
        mock_has_defaults.assert_called_once_with("kirby_normal")
        mock_create_defaults.assert_called_once()

        # Verify metadata shows default palettes used
        assert extraction_info["rom_palettes_used"] is False
        assert extraction_info["default_palettes_used"] is True
        assert extraction_info["palette_count"] == 1

    def test_extract_sprite_from_rom_no_sprite_name(self, app_context, tmp_path):
        """Test sprite extraction without sprite name (no palette extraction)."""
        # Create simple ROM
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(
            create_test_rom_with_header(
                title="TEST ROM",
                checksum=0xDEF0,
            )
        )
        output_base = tmp_path / "sprite_no_name"

        extractor = app_context.rom_extractor

        # Mock HAL decompression (returns 1 tile of test data)
        test_sprite_data = b"\x00" * BYTES_PER_TILE
        with patch.object(
            extractor.rom_injector,
            "find_compressed_sprite",
            return_value=(25, test_sprite_data, 0),
        ):
            output_path, extraction_info = extractor.extract_sprite_from_rom(
                str(rom_path),
                0x8000,
                str(output_base),
                "",  # No sprite_name
            )

        # Verify PNG created (real file I/O and conversion)
        verify_png_output(Path(output_path), min_tiles=1)

        # Verify no palette files created (check output directory)
        palette_files = list(tmp_path.glob("sprite_no_name_pal*.json"))
        assert len(palette_files) == 0, "No palette files should be created"

        # Verify metadata shows no palettes
        assert extraction_info["sprite_name"] == ""
        assert extraction_info["palette_count"] == 0
        assert extraction_info["rom_palettes_used"] is False
        assert extraction_info["default_palettes_used"] is False

    def test_extract_sprite_from_rom_hal_compression_error(self, app_context, tmp_path):
        """Test handling of HAL compression errors."""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(
            create_test_rom_with_header(
                title="TEST ROM",
                checksum=0x1234,
            )
        )
        output_base = tmp_path / "failed_sprite"

        extractor = app_context.rom_extractor

        # Mock HAL compression error (appropriate mock for error path testing)
        with patch.object(
            extractor.rom_injector,
            "find_compressed_sprite",
            side_effect=HALCompressionError("Failed to decompress sprite data"),
        ):
            with pytest.raises(Exception, match="Failed to decompress sprite") as exc_info:
                extractor.extract_sprite_from_rom(str(rom_path), 0x8000, str(output_base), "test_sprite")

            assert "Failed to decompress sprite" in str(exc_info.value)

    def test_extract_sprite_from_rom_generic_error(self, app_context, tmp_path):
        """Test handling of generic errors."""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(
            create_test_rom_with_header(
                title="TEST ROM",
                checksum=0x1234,
            )
        )
        output_base = tmp_path / "error_sprite"

        extractor = app_context.rom_extractor

        # Mock ROM header error (appropriate mock for error path testing)
        with patch.object(
            extractor.rom_injector,
            "read_rom_header",
            side_effect=Exception("Invalid ROM format"),
        ):
            with pytest.raises(Exception, match="Invalid ROM format"):
                extractor.extract_sprite_from_rom(str(rom_path), 0x8000, str(output_base), "test_sprite")
