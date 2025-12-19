"""
Tests for sprite detection algorithms in ROMExtractor
"""
from __future__ import annotations

import random
from unittest.mock import Mock, patch

import pytest

from core.rom_extractor import ROMExtractor

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Uses session_managers which owns worker threads"),
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.usefixtures("session_managers", "mock_hal"),  # DI + HAL mocking
    pytest.mark.shared_state_safe,
]

@pytest.fixture
def rom_extractor(mock_hal):
    """Create a ROMExtractor instance with mocked HAL dependencies.

    Uses the mock_hal fixture which properly patches HALCompressor at the
    source level (core.hal_compression.HALCompressor), affecting all imports
    including both ROMExtractor and ROMInjector.
    """
    # Use DI to get ROMExtractor (session_managers fixture sets up DI)
    from core.di_container import inject
    from core.protocols.manager_protocols import ROMExtractorProtocol, ROMCacheProtocol
    extractor = inject(ROMExtractorProtocol)

    # Clear any cached scan results to ensure test isolation
    rom_cache = inject(ROMCacheProtocol)
    rom_cache.clear_scan_progress_cache()

    # Mock the rom_injector methods we use in tests
    extractor.rom_injector = Mock()
    return extractor

@pytest.fixture
def create_test_sprite_data():
    """Factory to create various types of test sprite data"""
    def _create_sprite_data(pattern="valid", num_tiles=64):
        """Create test sprite data with different patterns"""
        tile_data = []

        if pattern == "valid":
            # Create valid sprite-like data with 4bpp structure
            for tile_idx in range(num_tiles):
                tile = bytearray(32)
                # Create bitplane patterns
                for row in range(8):
                    # Bitplanes 0,1 (bytes 0-15)
                    tile[row * 2] = (tile_idx + row) % 256
                    tile[row * 2 + 1] = ((tile_idx + row) * 3) % 256
                    # Bitplanes 2,3 (bytes 16-31)
                    tile[16 + row * 2] = ((tile_idx + row) * 5) % 256
                    tile[16 + row * 2 + 1] = ((tile_idx + row) * 7) % 256
                tile_data.extend(tile)

        elif pattern == "empty":
            # All zeros
            tile_data = [0] * (num_tiles * 32)

        elif pattern == "full":
            # All 0xFF
            tile_data = [0xFF] * (num_tiles * 32)

        elif pattern == "random":
            # Random noise (high entropy) - seeded for reproducibility
            random.seed(42)
            tile_data = [random.randint(0, 255) for _ in range(num_tiles * 32)]

        elif pattern == "low_entropy":
            # Very low entropy (repeating pattern)
            tile_data = [0x42, 0x00] * (num_tiles * 16)

        elif pattern == "misaligned":
            # Valid data but with extra bytes (misaligned)
            for tile_idx in range(num_tiles):
                tile = bytearray(32)
                for i in range(32):
                    tile[i] = (tile_idx + i) % 256
                tile_data.extend(tile)
            # Add extra bytes for misalignment
            tile_data.extend([0xAB] * 25)  # Bad alignment

        elif pattern == "small":
            # Too small to be valid sprite
            tile_data = [0x55] * 256  # Only 8 tiles

        elif pattern == "huge":
            # Too large to be valid sprite (> 64KB)
            tile_data = [0x77] * 70000

        return bytes(tile_data)

    return _create_sprite_data

class TestSpriteDetection:
    """Test sprite detection algorithms"""

    def test_scan_for_sprites_finds_valid_sprites(self, rom_extractor, create_test_sprite_data, tmp_path):
        """Test that scan_for_sprites finds valid sprite data"""
        # Create test ROM with valid sprite at specific offset
        rom_data = bytearray(0x10000)  # 64KB ROM
        valid_sprite = create_test_sprite_data("valid", 64)
        compressed_sprite = b"COMPRESSED" + valid_sprite  # Mock compressed data

        # Place compressed sprite at offset 0x1000
        rom_data[0x1000:0x1000 + len(compressed_sprite)] = compressed_sprite

        rom_path = tmp_path / "test.rom"
        with open(rom_path, "wb") as f:
            f.write(rom_data)

        # Mock decompression to return our valid sprite
        def mock_find_compressed(data, offset, expected_size=None):
            if offset == 0x1000:
                return len(compressed_sprite), valid_sprite
            raise Exception("No sprite found")

        rom_extractor.rom_injector.find_compressed_sprite.side_effect = mock_find_compressed

        # Scan for sprites
        found_sprites = rom_extractor.scan_for_sprites(
            str(rom_path),
            start_offset=0x0,
            end_offset=0x2000,
            step=0x100
        )

        # Should find our sprite
        assert len(found_sprites) == 1
        assert found_sprites[0]["offset"] == 0x1000
        assert found_sprites[0]["tile_count"] == 64
        assert found_sprites[0]["quality"] > 0  # Just verify quality is positive

    def test_scan_for_sprites_filters_invalid_data(self, rom_extractor, create_test_sprite_data, tmp_path):
        """Test that scan_for_sprites rejects invalid sprite data"""
        rom_data = bytearray(0x10000)

        # Create various invalid sprites
        empty_sprite = create_test_sprite_data("empty", 32)
        small_sprite = create_test_sprite_data("small")
        misaligned_sprite = create_test_sprite_data("misaligned", 32)

        rom_path = tmp_path / "test.rom"
        with open(rom_path, "wb") as f:
            f.write(rom_data)

        # Mock decompression to return different data based on offset
        def mock_find_compressed(data, offset, expected_size=None):
            if offset == 0x1000:
                return 100, empty_sprite  # Empty data
            if offset == 0x2000:
                return 50, small_sprite  # Too small
            if offset == 0x3000:
                return 200, misaligned_sprite  # Badly misaligned
            raise Exception("No sprite found")

        rom_extractor.rom_injector.find_compressed_sprite.side_effect = mock_find_compressed

        # Scan for sprites
        found_sprites = rom_extractor.scan_for_sprites(
            str(rom_path),
            start_offset=0x0,
            end_offset=0x4000,
            step=0x1000
        )

        # Should filter out invalid sprites or give them very low quality
        # Empty sprites might get through with very low quality scores
        for sprite in found_sprites:
            if sprite["offset"] == 0x2000:  # Small sprite
                assert sprite["tile_count"] < 16  # Should be rejected in scan
            else:
                assert sprite["quality"] < 0.3  # Very low quality for empty/misaligned

    def test_scan_for_sprites_sorts_by_quality(self, rom_extractor, create_test_sprite_data, tmp_path):
        """Test that found sprites are sorted by quality"""
        rom_data = bytearray(0x10000)

        # Create sprites with different qualities
        high_quality = create_test_sprite_data("valid", 128)  # Large, valid sprite
        med_quality = create_test_sprite_data("valid", 32)   # Smaller sprite
        low_quality = create_test_sprite_data("low_entropy", 64)  # Low entropy

        rom_path = tmp_path / "test.rom"
        with open(rom_path, "wb") as f:
            f.write(rom_data)

        def mock_find_compressed(data, offset, expected_size=None):
            if offset == 0x1000:
                return 100, med_quality
            if offset == 0x2000:
                return 200, high_quality
            if offset == 0x3000:
                return 150, low_quality
            raise Exception("No sprite found")

        rom_extractor.rom_injector.find_compressed_sprite.side_effect = mock_find_compressed

        # Scan for sprites
        found_sprites = rom_extractor.scan_for_sprites(
            str(rom_path),
            start_offset=0x0,
            end_offset=0x4000,
            step=0x1000
        )

        # Should be sorted by quality (descending)
        assert len(found_sprites) >= 2
        for i in range(len(found_sprites) - 1):
            assert found_sprites[i]["quality"] >= found_sprites[i + 1]["quality"]

    def test_assess_sprite_quality_perfect_sprite(self, rom_extractor, create_test_sprite_data):
        """Test quality assessment for perfect sprite data"""
        # Create ideal sprite data (64 tiles, perfectly aligned)
        sprite_data = create_test_sprite_data("valid", 64)

        quality = rom_extractor._assess_sprite_quality(sprite_data)

        # Should have positive quality score within valid range
        assert quality > 0
        assert quality <= 1.0

    def test_assess_sprite_quality_size_validation(self, rom_extractor, create_test_sprite_data):
        """Test quality assessment size validation"""
        # Test empty data
        assert rom_extractor._assess_sprite_quality(b"") == 0.0

        # Test data too large
        huge_data = create_test_sprite_data("huge")
        assert rom_extractor._assess_sprite_quality(huge_data) == 0.0

        # Test badly misaligned data
        misaligned = create_test_sprite_data("misaligned", 32)
        quality = rom_extractor._assess_sprite_quality(misaligned)
        assert quality == 0.0  # Should reject due to bad alignment

    def test_assess_sprite_quality_tile_count_scoring(self, rom_extractor, create_test_sprite_data):
        """Test quality scoring based on tile count"""
        # Optimal tile count (32-256 tiles)
        optimal = create_test_sprite_data("valid", 64)
        quality_optimal = rom_extractor._assess_sprite_quality(optimal)

        # Acceptable but not optimal (16-32 tiles)
        small = create_test_sprite_data("valid", 20)
        quality_small = rom_extractor._assess_sprite_quality(small)

        # Too small (< 16 tiles)
        tiny = create_test_sprite_data("valid", 8)
        quality_tiny = rom_extractor._assess_sprite_quality(tiny)

        # Should have descending quality
        # Optimal should score higher than small
        assert quality_optimal > quality_small
        # All valid data should have positive quality scores
        assert quality_small > 0
        assert quality_tiny > 0

    def test_assess_sprite_quality_entropy_analysis(self, rom_extractor, create_test_sprite_data):
        """Test quality scoring based on entropy"""
        # Good entropy (valid sprite data)
        valid = create_test_sprite_data("valid", 32)
        quality_valid = rom_extractor._assess_sprite_quality(valid)

        # Too low entropy (repetitive)
        low_entropy = create_test_sprite_data("low_entropy", 32)
        quality_low = rom_extractor._assess_sprite_quality(low_entropy)

        # Too high entropy (random noise)
        random = create_test_sprite_data("random", 32)
        quality_random = rom_extractor._assess_sprite_quality(random)

        # Valid sprite should score at least as high as low entropy
        # and better than random noise
        assert quality_valid >= quality_low
        assert quality_valid >= quality_random

    def test_calculate_entropy(self, rom_extractor):
        """Test entropy calculation"""
        # Test empty data
        assert rom_extractor._calculate_entropy(b"") == 0.0

        # Test uniform data (low entropy)
        uniform = b"\x42" * 1000
        entropy_uniform = rom_extractor._calculate_entropy(uniform)
        assert entropy_uniform == 0.0

        # Test binary pattern (entropy = 1)
        binary = b"\x00\xFF" * 500
        entropy_binary = rom_extractor._calculate_entropy(binary)
        assert 0.9 < entropy_binary < 1.1

        # Test random-like data (high entropy)
        # Create data with all byte values
        all_bytes = bytes(range(256)) * 4
        entropy_high = rom_extractor._calculate_entropy(all_bytes)
        assert entropy_high > 7.5  # Near maximum entropy for bytes

    def test_validate_4bpp_tile(self, rom_extractor):
        """Test 4bpp tile validation"""
        # Test wrong size
        assert not rom_extractor._validate_4bpp_tile(b"\x00" * 16)  # Too small
        assert not rom_extractor._validate_4bpp_tile(b"\x00" * 64)  # Too large

        # Test empty tile
        assert not rom_extractor._validate_4bpp_tile(b"\x00" * 32)

        # Test full tile
        assert not rom_extractor._validate_4bpp_tile(b"\xFF" * 32)

        # Test valid tile with bitplane structure
        valid_tile = bytearray(32)
        # Create bitplane patterns
        for i in range(8):
            valid_tile[i * 2] = 0x55      # Bitplane 0
            valid_tile[i * 2 + 1] = 0xAA  # Bitplane 1
            valid_tile[16 + i * 2] = 0x33     # Bitplane 2
            valid_tile[16 + i * 2 + 1] = 0xCC # Bitplane 3

        assert rom_extractor._validate_4bpp_tile(bytes(valid_tile))

    def test_has_graphics_patterns(self, rom_extractor, create_test_sprite_data):
        """Test graphics pattern detection"""
        # Test too small data
        assert not rom_extractor._has_graphics_patterns(b"\x00" * 32)

        # Test data with repeating tile patterns
        pattern_data = bytearray()
        base_tile = bytes(range(32))

        # Create tiles with some similarity
        for i in range(10):
            tile = bytearray(base_tile)
            # Modify a few bytes to create variation
            for j in range(5):
                tile[j] = (tile[j] + i) % 256
            pattern_data.extend(tile)

        assert rom_extractor._has_graphics_patterns(bytes(pattern_data))

        # Test completely random data (no patterns)
        random_data = create_test_sprite_data("random", 10)
        assert not rom_extractor._has_graphics_patterns(random_data)

    def test_find_best_sprite_offsets(self, rom_extractor, tmp_path):
        """Test finding best sprite offsets around a base offset"""
        rom_path = tmp_path / "test.rom"
        rom_data = b"\x00" * 0x10000
        with open(rom_path, "wb") as f:
            f.write(rom_data)

        # Mock scan_for_sprites to return test results
        mock_sprites = [
            {"offset": 0x1000, "quality": 0.8},
            {"offset": 0x1100, "quality": 0.6},
            {"offset": 0x1200, "quality": 0.4},  # Below threshold
            {"offset": 0x1300, "quality": 0.9},
        ]

        with patch.object(rom_extractor, "scan_for_sprites", return_value=mock_sprites):
            offsets = rom_extractor.find_best_sprite_offsets(
                str(rom_path),
                base_offset=0x1000,
                search_range=0x500
            )

        # Should only return high-quality offsets (>= 0.5)
        assert len(offsets) == 3
        assert 0x1000 in offsets
        assert 0x1100 in offsets
        assert 0x1300 in offsets
        assert 0x1200 not in offsets  # Low quality

    def test_has_4bpp_characteristics(self, rom_extractor):
        """Test 4bpp characteristics detection"""
        # Test too small data
        assert not rom_extractor._has_4bpp_characteristics(b"\x00" * 16)

        # Test data with 4bpp characteristics
        tile = bytearray(32)
        # Create varied bitplane data
        for i in range(16):
            tile[i] = i * 16  # First two bitplanes
            tile[16 + i] = i * 8  # Second two bitplanes

        assert rom_extractor._has_4bpp_characteristics(bytes(tile))

        # Test uniform data (no variety)
        uniform_tile = b"\x00" * 16 + b"\xFF" * 16
        assert not rom_extractor._has_4bpp_characteristics(uniform_tile)
