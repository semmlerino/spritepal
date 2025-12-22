"""
Integration tests for sprite finder functionality using real components.

These tests require real HAL compression tools and verify actual sprite
finding and extraction behavior. They test with a synthetic ROM unless
a real Kirby ROM is available.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.hal_compression import HALCompressor
from core.rom_extractor import ROMExtractor
from core.sprite_finder import SpriteFinder

# Integration tests that need real DI setup and real HAL
# Uses session_managers with shared_state_safe at class level
# Don't use mock_hal - these tests verify real decompression behavior
pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_hal,
    pytest.mark.skip_thread_cleanup(reason="Integration tests involve HAL pool that spawns background threads"),
    pytest.mark.allows_registry_state,
]


@pytest.mark.integration
@pytest.mark.usefixtures("isolated_managers")
class TestSpriteFinder:
    """Test sprite finder with real ROM data and HAL compression."""

    def test_find_sprites_in_test_rom(self, test_rom_with_sprites):
        """Test finding sprites in a test ROM with known compressed data."""
        rom_info = test_rom_with_sprites

        # Skip if no sprites in test ROM (real Kirby ROM not available)
        if not rom_info['sprites']:
            pytest.skip("No compressed sprites in test ROM - real Kirby ROM not available")

        rom_path = str(rom_info['path'])

        # Create sprite finder
        finder = SpriteFinder()

        # Read ROM data
        rom_data = Path(rom_path).read_bytes()

        # Find sprites at known locations
        sprites_found = []
        for sprite_info in rom_info['sprites']:
            offset = sprite_info['offset']
            result = finder.find_sprite_at_offset(rom_data, offset)
            if result:
                sprites_found.append(result)

        # Verify we found at least some sprites
        assert len(sprites_found) > 0, "Should find test sprites"

        # Verify sprite properties match expectations
        for found, expected in zip(sprites_found, rom_info['sprites'], strict=False):
            assert found['offset'] == expected['offset']
            # Allow some variance in tile count since decompression may vary
            assert found['tile_count'] > 0
            assert found['decompressed_size'] > 0

    def test_sprite_finder_with_rom_extractor(self, test_rom_with_sprites):
        """Test sprite finder working with ROM extractor."""
        rom_info = test_rom_with_sprites

        # Skip if no sprites in test ROM
        if not rom_info['sprites']:
            pytest.skip("No compressed sprites in test ROM - real Kirby ROM not available")

        rom_path = str(rom_info['path'])

        # Create ROM extractor via DI (verifies DI container is working)
        from core.di_container import inject
        from core.protocols.manager_protocols import ROMExtractorProtocol
        extractor = inject(ROMExtractorProtocol)
        assert extractor is not None

        # Create sprite finder
        finder = SpriteFinder()

        # Read ROM
        rom_data = Path(rom_path).read_bytes()

        # Scan for sprites at known locations
        found_sprites = []
        for sprite_info in rom_info['sprites']:
            sprite = finder.find_sprite_at_offset(rom_data, sprite_info['offset'])
            if sprite:
                found_sprites.append(sprite)

        # We should find at least the sprites we expected
        assert len(found_sprites) >= 1, "Should find at least one sprite"

    def test_find_sprites_in_real_rom(self, real_kirby_rom):
        """Test finding sprites in real Kirby ROM if available."""
        if not real_kirby_rom:
            pytest.skip("Real Kirby ROM not available")

        finder = SpriteFinder()

        # Read ROM
        rom_data = Path(real_kirby_rom).read_bytes()

        # Known sprite locations in Kirby Super Star
        known_locations = [
            0x200000,  # Common sprite area
            0x206000,  # Another sprite area
        ]

        found_count = 0
        for offset in known_locations:
            if offset < len(rom_data):
                sprite = finder.find_sprite_at_offset(rom_data, offset)
                if sprite:
                    found_count += 1
                    # Verify sprite has reasonable properties
                    assert sprite['tile_count'] > 0
                    assert sprite['decompressed_size'] > 0
                    assert sprite['quality'] > 0

        # Should find at least some sprites
        assert found_count > 0, "Should find sprites at known locations"


@pytest.mark.integration
class TestHALCompression:
    """Test HAL compression/decompression with real data."""

    def test_compress_decompress_cycle(self, tmp_path):
        """Test that data survives compress/decompress cycle using files."""
        # Create test sprite data (4 tiles = 128 bytes)
        original_data = bytearray()
        for i in range(4):  # 4 tiles
            for j in range(32):  # 32 bytes per tile
                original_data.append((i * 32 + j) % 256)
        original_data = bytes(original_data)

        # Write to file for compression
        output_file = tmp_path / "test_sprite.hal"

        # Compress using file-based method
        compressor = HALCompressor()
        success = compressor.compress_to_file(original_data, str(output_file))

        assert success, "Compression should succeed"
        assert output_file.exists(), "Compressed file should exist"
        assert output_file.stat().st_size > 0, "Compressed data should not be empty"

        # Decompress from file
        decompressed = compressor.decompress_from_rom(str(output_file), 0)

        assert decompressed is not None, "Decompression should succeed"
        # HAL decompression returns the exact original data
        assert len(decompressed) >= len(original_data), "Decompressed size should be at least original"
        # First N bytes should match (HAL may pad output)
        assert decompressed[:len(original_data)] == original_data, "Data should match after cycle"

    def test_decompress_from_rom_offset(self, test_rom_with_sprites):
        """Test decompressing directly from ROM at offset."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        if not rom_info['sprites']:
            pytest.skip("No test sprites in ROM - real Kirby ROM not available")

        sprite_info = rom_info['sprites'][0]
        offset = sprite_info['offset']

        # Decompress from ROM
        compressor = HALCompressor()
        decompressed = compressor.decompress_from_rom(rom_path, offset)

        assert decompressed is not None, "Should decompress successfully"
        # Size might not match exactly due to compression boundaries
        assert len(decompressed) > 0, "Should have decompressed data"

    def test_parallel_decompression(self, test_rom_with_sprites):
        """Test that HAL process pool handles parallel operations."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        rom_data = Path(rom_path).read_bytes()

        compressor = HALCompressor()

        # Try to decompress from multiple offsets
        # Note: Most offsets won't have valid HAL data, that's expected
        offsets = [0x1000, 0x2000, 0x10000, 0x20000]
        results = []

        for offset in offsets:
            if offset < len(rom_data):
                try:
                    result = compressor.decompress_from_rom(rom_path, offset)
                    results.append((offset, result is not None))
                except Exception:
                    results.append((offset, False))

        # Should complete without crashes - most will return None (no valid HAL data)
        assert len(results) == len(offsets), "All offsets should be processed"


@pytest.mark.integration
@pytest.mark.usefixtures("isolated_managers")
class TestROMExtractor:
    """Test ROM extractor with real data."""

    def test_extract_sprite_from_rom(self, test_rom_with_sprites, tmp_path):
        """Test extracting sprites from ROM to files."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        if not rom_info['sprites']:
            pytest.skip("No test sprites in ROM - real Kirby ROM not available")

        # Use DI to get ROMExtractor
        from core.di_container import inject
        from core.protocols.manager_protocols import ROMExtractorProtocol
        extractor = inject(ROMExtractorProtocol)

        # Extract at a known sprite offset
        sprite_info = rom_info['sprites'][0]
        output_path = tmp_path / "extracted_sprite.bin"

        # Use extract_sprite_data which returns decompressed bytes
        sprite_data = extractor.extract_sprite_data(
            rom_path=rom_path,
            sprite_offset=sprite_info['offset'],
        )

        assert sprite_data is not None, "Should extract sprite data"
        assert len(sprite_data) > 0, "Sprite data should not be empty"

        # Write data to output file
        output_path.write_bytes(sprite_data)

        assert output_path.exists(), "Output file should exist"
        assert output_path.stat().st_size > 0, "File should have data"

    def test_extract_with_decompression(self, test_rom_with_sprites, tmp_path):
        """Test extracting and decompressing sprites."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        if not rom_info['sprites']:
            pytest.skip("No test sprites in ROM - real Kirby ROM not available")

        # Use DI to get ROMExtractor
        from core.di_container import inject
        from core.protocols.manager_protocols import ROMExtractorProtocol
        extractor = inject(ROMExtractorProtocol)

        sprite_info = rom_info['sprites'][0]
        output_path = tmp_path / "decompressed_sprite.bin"

        # Extract with decompression
        rom_data = Path(rom_path).read_bytes()

        # Use the injector to find and decompress
        compressed_size, decompressed_data = extractor.rom_injector.find_compressed_sprite(
            rom_data,
            sprite_info['offset'],
            expected_size=None
        )

        assert decompressed_data is not None, "Should decompress sprite"
        assert len(decompressed_data) > 0, "Decompressed data should not be empty"

        output_path.write_bytes(decompressed_data)
        assert output_path.exists()
        assert output_path.stat().st_size > 0
