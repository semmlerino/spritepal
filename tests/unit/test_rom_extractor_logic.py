"""
Unit tests for ROM sprite extraction logic.

Tests for ROMExtractor internal logic using mocked dependencies.
Extracted from test_rom_extractor.py during test suite reorganization.

For integration tests with real file operations and minimal mocking,
see tests/integration/test_rom_extractor.py.
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
    pytest.mark.unit,
    pytest.mark.usefixtures("app_context", "mock_hal"),
]


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
    """Integration tests for main sprite extraction workflow.

    Uses real ROMExtractor components with mock HAL (for speed).
    Verifies complete extraction workflow including file I/O, PNG generation,
    and palette extraction by validating actual output files.

    For pure unit tests with isolated logic, see other test classes.
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
        """Test sprite extraction with ROM palette extraction.

        Uses real ROM header parsing, file I/O, and PNG conversion.
        Mocks HAL decompression and palette extraction.
        """
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
        """Test sprite extraction with default palette fallback.

        Uses real ROM header parsing, file I/O, and PNG conversion.
        Mocks HAL decompression and palette lookup.
        """
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
        """Test sprite extraction without sprite name (no palette extraction).

        Uses real ROM header parsing, file I/O, and PNG conversion.
        Mocks only HAL decompression.
        """
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
