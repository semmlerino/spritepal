"""
Comprehensive tests for ROM scanning functionality.
Tests the scan_for_sprites method and related quality assessment features.
"""
from __future__ import annotations

import pytest

from core.rom_extractor import ROMExtractor
from tests.infrastructure.test_doubles import MockHALCompressor

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.usefixtures("session_managers", "mock_hal"),  # DI + HAL mocking
]

class CustomMockHALCompressor(MockHALCompressor):
    """Custom HAL compressor for ROM scanning tests with specific size control."""

    def __init__(self):
        super().__init__()
        self._sprite_responses = {}  # Map offset to (compressed_size, decompressed_data)

    def configure_sprite_response(self, offset: int, compressed_size: int, decompressed_data: bytes):
        """Configure specific response for a ROM offset."""
        self._sprite_responses[offset] = (compressed_size, decompressed_data)

    def decompress_from_rom(self, rom_path: str, offset: int, output_path: str | None = None) -> bytes:
        """Return configured sprite data or raise exception."""
        if offset in self._sprite_responses:
            _, decompressed_data = self._sprite_responses[offset]
            if output_path:
                from pathlib import Path
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(decompressed_data)
            return decompressed_data
        else:
            # Default behavior - raise exception for unknown offsets
            raise Exception("No sprite found")

class TestROMScanning:
    """Test ROM scanning functionality with comprehensive coverage"""

    @pytest.fixture
    def rom_extractor(self):
        """Create a ROM extractor instance"""
        return ROMExtractor()

    @pytest.fixture
    def mock_rom_file(self, tmp_path):
        """Create a mock ROM file for testing"""
        rom_path = tmp_path / "test_rom.sfc"
        # Create a 128KB ROM with some test data
        rom_data = bytearray(128 * 1024)

        # Add some compressed sprite-like data at known offsets
        # These should be detected by the scanner
        test_offsets = [0x8000, 0x10000, 0x18000]
        for i, offset in enumerate(test_offsets):
            # Add mock compressed data signature
            rom_data[offset:offset+4] = b"\x01\x02\x03\x04"  # Mock compressed header
            # Add some tile-like data that should decompress nicely
            for j in range(offset+4, offset+100):
                rom_data[j] = (i * 16 + j % 16) & 0xFF

        rom_path.write_bytes(rom_data)
        return str(rom_path)

    def test_scan_for_sprites_basic_functionality(self, rom_extractor, mock_rom_file):
        """Test basic sprite scanning functionality"""
        # Set up custom HAL compressor with specific responses
        mock_hal = CustomMockHALCompressor()

        # Configure responses for test offsets (16 tiles = 512 bytes)
        sprite_data = b"\x00" * 512
        mock_hal.configure_sprite_response(0x8000, 64, sprite_data)
        mock_hal.configure_sprite_response(0x10000, 64, sprite_data)
        mock_hal.configure_sprite_response(0x18000, 64, sprite_data)

        # Replace the HAL compressor
        rom_extractor.rom_injector.hal_compressor = mock_hal

        # Run the scan
        results = rom_extractor.scan_for_sprites(
            mock_rom_file,
            start_offset=0x8000,
            end_offset=0x20000,
            step=0x1000
        )

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

    def test_scan_for_sprites_end_offset_exceeds_rom(self, rom_extractor, mock_rom_file):
        """Test scanning when end offset exceeds ROM size"""
        # Set up HAL compressor that returns no sprites
        mock_hal = CustomMockHALCompressor()
        rom_extractor.rom_injector.hal_compressor = mock_hal

        # Try to scan beyond ROM size
        results = rom_extractor.scan_for_sprites(
            mock_rom_file,
            start_offset=0x10000,
            end_offset=0x100000,  # Way beyond 128KB ROM
            step=0x1000
        )

        # Should complete without error and return empty results
        assert isinstance(results, list)

    def test_scan_for_sprites_quality_filtering(self, rom_extractor, mock_rom_file):
        """Test that sprites are sorted by quality score"""
        from unittest.mock import patch

        # Set up custom HAL compressor with different sprite data
        mock_hal = CustomMockHALCompressor()
        mock_hal.configure_sprite_response(0x8000, 32, b"\x00" * 512)  # Good sprite
        mock_hal.configure_sprite_response(0x10000, 48, b"\x11" * 512)  # Better sprite
        mock_hal.configure_sprite_response(0x18000, 16, b"\x22" * 512)  # Different sprite

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
                mock_rom_file,
                start_offset=0x8000,
                end_offset=0x20000,
                step=0x1000
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
        mock_hal = CustomMockHALCompressor()
        mock_hal.configure_sprite_response(0x8000, 64, b"\x00" * 512)  # Perfect alignment (16 tiles)
        mock_hal.configure_sprite_response(0x10000, 68, b"\x11" * 520)  # Minor misalignment (16 tiles + 8 extra)
        mock_hal.configure_sprite_response(0x18000, 16, b"\x22" * 32)   # Too small (1 tile)

        rom_extractor.rom_injector.hal_compressor = mock_hal

        with patch.object(rom_extractor, "_assess_sprite_quality", return_value=80.0):
            results = rom_extractor.scan_for_sprites(
                mock_rom_file,
                start_offset=0x8000,
                end_offset=0x20000,
                step=0x1000
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
            step=0x1000  # Reasonable step size
        )

        # Should complete and return empty list (no sprites found)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_scan_for_sprites_exception_handling(self, rom_extractor):
        """Test scanning with invalid ROM file"""
        # Try to scan non-existent file
        results = rom_extractor.scan_for_sprites(
            "/nonexistent/rom.sfc",
            start_offset=0x8000,
            end_offset=0x10000,
            step=0x1000
        )

        # Should return empty list, not crash
        assert results == []

    def test_scan_for_sprites_empty_results(self, rom_extractor, mock_rom_file):
        """Test scanning when no valid sprites are found"""
        # Set up HAL compressor that always fails
        mock_hal = CustomMockHALCompressor()
        rom_extractor.rom_injector.hal_compressor = mock_hal

        results = rom_extractor.scan_for_sprites(
            mock_rom_file,
            start_offset=0x8000,
            end_offset=0x10000,
            step=0x1000
        )

        assert results == []

class TestROMSpriteQualityAssessment:
    """Test ROM sprite quality assessment functionality"""

    @pytest.fixture
    def rom_extractor(self):
        """Create a ROM extractor instance"""
        return ROMExtractor()

    def test_assess_sprite_quality_perfect_sprite(self, rom_extractor):
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

    def test_assess_sprite_quality_empty_data(self, rom_extractor):
        """Test quality assessment for empty sprite data"""
        sprite_data = b"\x00" * 512  # All zeros

        quality = rom_extractor._assess_sprite_quality(sprite_data)

        # Empty data should have low quality
        assert isinstance(quality, float)
        assert 0.0 <= quality <= 1.0
        assert quality < 0.5  # Should be low quality

    def test_assess_sprite_quality_random_data(self, rom_extractor):
        """Test quality assessment for random-looking data"""
        import random
        random.seed(42)  # Reproducible random
        sprite_data = bytes([random.randint(0, 255) for _ in range(512)])

        quality = rom_extractor._assess_sprite_quality(sprite_data)

        # Random data should have moderate quality (high entropy but no patterns)
        assert isinstance(quality, float)
        assert 0.0 <= quality <= 1.0

    def test_assess_sprite_quality_small_data(self, rom_extractor):
        """Test quality assessment for very small sprite data"""
        sprite_data = b"\x01\x02\x03\x04" * 8  # 32 bytes (1 tile)

        quality = rom_extractor._assess_sprite_quality(sprite_data)

        # Small data should still return valid quality score
        assert isinstance(quality, float)
        assert 0.0 <= quality <= 1.0

    def test_assess_sprite_quality_with_embedded_check(self, rom_extractor):
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
        """Create a ROM extractor instance"""
        return ROMExtractor()

    @pytest.fixture
    def temp_rom_with_header(self, tmp_path):
        """Create a ROM with SNES header for testing"""
        rom_path = tmp_path / "test_rom_with_header.sfc"
        rom_data = bytearray(64 * 1024)  # 64KB ROM

        # Add SNES ROM header at 0x7FC0
        header_offset = 0x7FC0
        rom_data[header_offset:header_offset+21] = b"TEST ROM TITLE      "  # 21 chars
        rom_data[header_offset+21] = 0x20  # ROM type
        rom_data[header_offset+22] = 0x09  # ROM size (512KB)
        rom_data[header_offset+23] = 0x00  # SRAM size

        # Add checksum (simplified)
        rom_data[header_offset+28:header_offset+30] = b"\x34\x12"  # Checksum
        rom_data[header_offset+30:header_offset+32] = b"\xCB\xED"  # Complement

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
        rom_data[header_offset:header_offset+21] = b"KIRBY SUPER STAR    "  # 21 chars
        rom_data[header_offset+21] = 0x20  # ROM type
        rom_data[header_offset+22] = 0x09  # ROM size (512KB)
        rom_data[header_offset+23] = 0x00  # SRAM size

        # Add checksum (simplified)
        rom_data[header_offset+28:header_offset+30] = b"\x34\x12"  # Checksum
        rom_data[header_offset+30:header_offset+32] = b"\xCB\xED"  # Complement

        rom_path.write_bytes(rom_data)

        # Mock the rom injector's find_sprite_locations method
        # Note: This is still using patch because find_sprite_locations is not HAL-related
        with patch.object(rom_extractor.rom_injector, "find_sprite_locations") as mock_find_locations:
            mock_locations = {
                "kirby_normal": SpritePointer(offset=0x8000, bank=0x10, address=0x0000),
                "kirby_flying": SpritePointer(offset=0x9000, bank=0x12, address=0x1000)
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
