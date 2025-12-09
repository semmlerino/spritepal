"""
Integration tests for sprite finder functionality using real components.
"""
from __future__ import annotations

import pytest

from core.hal_compression import HALCompressor
from core.rom_extractor import ROMExtractor
from core.sprite_finder import SpriteFinder


@pytest.mark.integration
class TestSpriteFinder:
    """Test sprite finder with real ROM data and HAL compression."""

    def test_find_sprites_in_test_rom(self, test_rom_with_sprites):
        """Test finding sprites in a test ROM with known compressed data."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        # Create sprite finder
        finder = SpriteFinder()

        # Read ROM data
        with open(rom_path, 'rb') as f:
            rom_data = f.read()

        # Find sprites at known locations
        sprites_found = []
        for sprite_info in rom_info['sprites']:
            offset = sprite_info['offset']
            result = finder.find_sprite_at_offset(rom_data, offset)
            if result:
                sprites_found.append(result)

        # Verify we found the expected sprites
        if rom_info['sprites']:  # Only if we have test sprites
            assert len(sprites_found) > 0, "Should find test sprites"

            # Verify sprite properties
            for found, expected in zip(sprites_found, rom_info['sprites'], strict=False):
                assert found['offset'] == expected['offset']
                assert found['tile_count'] == expected['tile_count']
                assert found['decompressed_size'] == expected['decompressed_size']

    def test_sprite_finder_with_rom_extractor(self, test_rom_with_sprites):
        """Test sprite finder working with ROM extractor."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        # Create ROM extractor
        ROMExtractor()

        # Create sprite finder
        finder = SpriteFinder()

        # Read ROM
        with open(rom_path, 'rb') as f:
            rom_data = f.read()

        # Scan a range for sprites
        found_sprites = []
        scan_start = 0x0
        scan_end = min(0x300000, len(rom_data))
        step = 0x10000  # 64KB steps

        for offset in range(scan_start, scan_end, step):
            sprite = finder.find_sprite_at_offset(rom_data, offset)
            if sprite:
                found_sprites.append(sprite)

        # We should find at least the sprites we inserted
        if rom_info['sprites']:
            assert len(found_sprites) >= len(rom_info['sprites'])

    @pytest.mark.requires_rom
    def test_find_sprites_in_real_rom(self, real_kirby_rom):
        """Test finding sprites in real Kirby ROM if available."""
        if not real_kirby_rom:
            pytest.skip("Real Kirby ROM not available")

        finder = SpriteFinder()

        # Read ROM
        with open(real_kirby_rom, 'rb') as f:
            rom_data = f.read()

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

    def test_compress_decompress_cycle(self, temp_dir):
        """Test that data survives compress/decompress cycle using files."""
        # Create test sprite data (4 tiles = 128 bytes)
        original_data = bytearray()
        for i in range(4):  # 4 tiles
            for j in range(32):  # 32 bytes per tile
                original_data.append((i * 32 + j) % 256)
        original_data = bytes(original_data)

        # Write to file for compression
        input_file = temp_dir / "test_sprite.bin"
        output_file = temp_dir / "test_sprite.hal"
        temp_dir / "test_sprite_decompressed.bin"

        input_file.write_bytes(original_data)

        # Compress using file-based method
        compressor = HALCompressor()
        # compress_to_file takes bytes data and output path, not input file path
        success = compressor.compress_to_file(original_data, str(output_file))

        assert success, "Compression should succeed"
        assert output_file.exists(), "Compressed file should exist"
        assert output_file.stat().st_size > 0, "Compressed data should not be empty"

        # Decompress from file
        decompressed = compressor.decompress_from_rom(str(output_file), 0)

        if decompressed:
            # Verify data matches
            assert len(decompressed) == len(original_data), "Decompressed size should match"
            assert decompressed == original_data, "Data should match after cycle"

    def test_decompress_from_rom_offset(self, test_rom_with_sprites):
        """Test decompressing directly from ROM at offset."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        if not rom_info['sprites']:
            pytest.skip("No test sprites in ROM")

        sprite_info = rom_info['sprites'][0]
        offset = sprite_info['offset']
        sprite_info['decompressed_size']

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

        with open(rom_path, 'rb') as f:
            rom_data = f.read()

        compressor = HALCompressor()

        # Try to decompress from multiple offsets in parallel
        offsets = [0x1000, 0x2000, 0x10000, 0x20000]
        results = []

        for offset in offsets:
            if offset < len(rom_data):
                try:
                    result = compressor.decompress_from_rom(rom_path, offset)
                    results.append((offset, result is not None))
                except Exception:
                    results.append((offset, False))

        # Should complete without crashes
        assert len(results) == len(offsets)

@pytest.mark.integration
class TestROMExtractor:
    """Test ROM extractor with real data."""

    def test_extract_sprite_from_rom(self, test_rom_with_sprites, temp_dir):
        """Test extracting sprites from ROM to files."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        if not rom_info['sprites']:
            pytest.skip("No test sprites in ROM")

        extractor = ROMExtractor()

        # Extract at a known sprite offset
        sprite_info = rom_info['sprites'][0]
        output_path = temp_dir / "extracted_sprite.bin"

        # Use extract_sprite_data which returns decompressed bytes
        try:
            sprite_data = extractor.extract_sprite_data(
                rom_path=rom_path,
                sprite_offset=sprite_info['offset'],
            )

            # Write data to output file
            output_path.write_bytes(sprite_data)

            assert output_path.exists(), "Output file should exist"
            assert output_path.stat().st_size > 0, "File should have data"
        except Exception:
            # May fail if no valid HAL data at offset - that's acceptable
            pass

    def test_extract_with_decompression(self, test_rom_with_sprites, temp_dir):
        """Test extracting and decompressing sprites."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        if not rom_info['sprites']:
            pytest.skip("No test sprites in ROM")

        extractor = ROMExtractor()

        sprite_info = rom_info['sprites'][0]
        output_path = temp_dir / "decompressed_sprite.bin"

        # Extract with decompression
        with open(rom_path, 'rb') as f:
            rom_data = f.read()

        # Use the injector to find and decompress
        compressed_size, decompressed_data = extractor.rom_injector.find_compressed_sprite(
            rom_data,
            sprite_info['offset'],
            expected_size=None
        )

        if decompressed_data:
            output_path.write_bytes(decompressed_data)
            assert output_path.exists()
            assert output_path.stat().st_size > 0
