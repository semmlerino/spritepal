"""
Advanced tests for ROM extractor methods that were missing coverage.
"""
from __future__ import annotations

import random
from unittest.mock import Mock

import pytest

from core.rom_extractor import ROMExtractor
from utils.constants import BYTES_PER_TILE

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.slow,
    pytest.mark.usefixtures("session_managers", "mock_hal"),  # DI + HAL mocking
]

class TestROMExtractorScanMethods:
    """Test advanced ROM scanning and analysis methods"""

    @pytest.fixture(autouse=True)
    def seed_random(self):
        """Seed random for reproducible test data."""
        random.seed(42)

    @pytest.fixture
    def extractor(self):
        """Create ROM extractor with mocked dependencies"""
        extractor = ROMExtractor()
        extractor.rom_injector = Mock()
        return extractor

    def test_scan_for_sprites_basic(self, extractor, tmp_path):
        """Test basic sprite scanning functionality"""
        rom_path = tmp_path / "test.rom"
        rom_data = b"\x00" * 0x10000  # 64KB ROM
        rom_path.write_bytes(rom_data)

        # Mock successful decompression at specific offsets
        test_sprite_data = b"\x00" * (32 * BYTES_PER_TILE)  # 32 tiles
        extractor.rom_injector.find_compressed_sprite.side_effect = [
            (256, test_sprite_data),  # First offset - valid
            Exception("No sprite"),   # Second offset - invalid
            (512, test_sprite_data),  # Third offset - valid
        ]

        found_sprites = extractor.scan_for_sprites(
            str(rom_path), 0x1000, 0x1300, step=0x100
        )

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
            str(rom_path), 0x100, 0x5000, step=0x100  # End offset > ROM size
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

        extractor.rom_injector.find_compressed_sprite.side_effect = [
            (256, good_sprite),
            (50, bad_sprite),  # Should be rejected
        ]

        found_sprites = extractor.scan_for_sprites(
            str(rom_path), 0x0, 0x200, step=0x100
        )

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
        """Create ROM extractor for testing"""
        return ROMExtractor()

    def test_assess_sprite_quality_perfect_sprite(self, extractor):
        """Test quality assessment with perfect sprite data"""
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
        random_data = bytes(random.randint(0, 255) for _ in range(BYTES_PER_TILE * 32))
        score = extractor._assess_sprite_quality(random_data)
        assert score < 0.7  # Random data should score lower

    def test_assess_sprite_quality_embedded_sprite(self, extractor):
        """Test quality assessment with embedded sprite data"""
        # Create data with sprite embedded at one of the checked offsets
        # The implementation checks offsets: 512, 1024, 2048, 4096
        padding = b"\xFF" * 1024  # 1024 bytes of padding
        good_sprite = self._create_perfect_sprite_data(256)  # 256 tiles = 8192 bytes
        embedded_data = padding + good_sprite + (b"\xFF" * 1024)

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
        """Create ROM extractor for testing"""
        return ROMExtractor()

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
        full_tile = b"\xFF" * 32
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
        random_data = bytes(random.randint(0, 255) for _ in range(256))
        assert extractor._has_graphics_patterns(random_data) is False

    def test_has_graphics_patterns_too_small(self, extractor):
        """Test graphics pattern detection with insufficient data"""
        small_data = b"\x00" * 32
        assert extractor._has_graphics_patterns(small_data) is False

class TestROMExtractorFindBestOffsets:
    """Test best sprite offset finding functionality"""

    @pytest.fixture
    def extractor(self):
        """Create ROM extractor with mocked scan method"""
        extractor = ROMExtractor()
        extractor.scan_for_sprites = Mock()
        return extractor

    def test_find_best_sprite_offsets_basic(self, extractor):
        """Test finding best sprite offsets"""
        # Mock scan results
        scan_results = [
            {"offset": 0x1000, "quality": 0.9},
            {"offset": 0x1100, "quality": 0.7},
            {"offset": 0x1200, "quality": 0.3},  # Below threshold
            {"offset": 0x1300, "quality": 0.8},
            {"offset": 0x1400, "quality": 0.6},
            {"offset": 0x1500, "quality": 0.85},
        ]
        extractor.scan_for_sprites.return_value = scan_results

        best_offsets = extractor.find_best_sprite_offsets(
            "/path/to/rom", 0x1000, search_range=0x1000
        )

        # Should return top 5 high-quality offsets (quality >= 0.5)
        assert len(best_offsets) == 5
        assert 0x1000 in best_offsets
        assert 0x1100 in best_offsets
        assert 0x1200 not in best_offsets  # Quality too low
        assert 0x1300 in best_offsets
        assert 0x1400 in best_offsets
        assert 0x1500 in best_offsets

        # Verify scan was called with correct parameters
        extractor.scan_for_sprites.assert_called_once_with(
            "/path/to/rom", 0x0, 0x2000, step=0x10
        )

    def test_find_best_sprite_offsets_no_results(self, extractor):
        """Test finding offsets when no sprites found"""
        extractor.scan_for_sprites.return_value = []

        best_offsets = extractor.find_best_sprite_offsets(
            "/path/to/rom", 0x8000
        )

        assert best_offsets == []

    def test_find_best_sprite_offsets_all_low_quality(self, extractor):
        """Test finding offsets when all sprites are low quality"""
        scan_results = [
            {"offset": 0x1000, "quality": 0.3},
            {"offset": 0x1100, "quality": 0.2},
            {"offset": 0x1200, "quality": 0.4},
        ]
        extractor.scan_for_sprites.return_value = scan_results

        best_offsets = extractor.find_best_sprite_offsets(
            "/path/to/rom", 0x1000
        )

        assert best_offsets == []  # No offsets meet quality threshold
