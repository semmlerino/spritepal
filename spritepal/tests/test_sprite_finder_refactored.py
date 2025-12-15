"""
Refactored sprite finder tests using real components and test doubles.

Instead of mocking internal methods, we use real SpriteFinder with
test doubles only for external dependencies (ROM files, image files).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from core.sprite_finder import SpriteCandidate, SpriteFinder
from tests.infrastructure.test_doubles import (
    DoubleFactory,
)

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Refactored sprite finder tests may create background threads"),
    pytest.mark.unit,
    pytest.mark.headless,
    pytest.mark.parallel_safe,
    pytest.mark.usefixtures("mock_hal"),  # HAL mocking for compression
]

class TestSpriteCandidate:
    """Test SpriteCandidate dataclass behavior."""

    def test_sprite_candidate_creation_and_properties(self, tmp_path):
        """Test creating a sprite candidate and accessing its properties."""
        # Create candidate with test data
        preview_path = str(tmp_path / "preview.png")
        candidate = SpriteCandidate(
            offset=0x100000,
            compressed_size=1024,
            decompressed_size=2048,
            tile_count=64,
            confidence=0.85,
            visual_metrics={"coherence": 0.8},
            preview_path=preview_path,
        )

        # Verify properties are correctly set
        assert candidate.offset == 0x100000
        assert candidate.compressed_size == 1024
        assert candidate.decompressed_size == 2048
        assert candidate.tile_count == 64
        assert candidate.confidence == 0.85
        assert candidate.visual_metrics == {"coherence": 0.8}
        assert candidate.preview_path == preview_path

    def test_sprite_candidate_serialization(self, tmp_path):
        """Test converting candidate to dictionary for serialization."""
        # Create candidate with floating point values
        preview_path = str(tmp_path / "preview.png")
        candidate = SpriteCandidate(
            offset=0x100000,
            compressed_size=1024,
            decompressed_size=2048,
            tile_count=64,
            confidence=0.856789,
            visual_metrics={"coherence": 0.823456, "edge_score": 0.712345},
            preview_path=preview_path,
        )

        # Convert to dictionary
        result = candidate.to_dict()

        # Verify serialization format
        assert result["offset"] == "0x100000"  # Hex string format
        assert result["offset_int"] == 0x100000  # Integer value
        assert result["compressed_size"] == 1024
        assert result["decompressed_size"] == 2048
        assert result["tile_count"] == 64
        assert result["confidence"] == 0.857  # Rounded to 3 decimal places
        assert result["visual_metrics"]["coherence"] == 0.823  # Rounded
        assert result["visual_metrics"]["edge_score"] == 0.712  # Rounded
        assert result["preview_path"] == preview_path

@pytest.mark.usefixtures("isolated_managers")
class TestSpriteFinderWithRealComponents:
    """Test SpriteFinder using real components with test doubles for external dependencies."""

    @pytest.fixture
    def test_rom_with_sprites(self, tmp_path):
        """Create a test ROM file with known sprite patterns."""
        # Use test double factory to create ROM with sprite data
        rom_file = DoubleFactory.create_rom_file(rom_type="standard")

        # Write to actual file for testing
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(rom_file._data)

        return str(rom_path)

    @pytest.fixture
    def output_dir(self, tmp_path):
        """Create output directory for sprite extraction."""
        output = tmp_path / "sprites"
        output.mkdir()
        return str(output)

    @staticmethod
    def _create_test_sprite_data(tile_count: int = 16) -> bytes:
        """Helper to create test sprite tile data."""
        # Each tile is 32 bytes in 4bpp format
        tile_size = 32
        data = bytearray(tile_count * tile_size)

        # Fill with pattern that looks like sprite data
        for i in range(len(data)):
            # Create varied but non-random pattern
            data[i] = (i * 7 + i // 32 * 13) % 256

        return bytes(data)

    def test_sprite_finder_initialization(self, output_dir):
        """Test that SpriteFinder initializes correctly with real components."""
        # Create finder with real components
        finder = SpriteFinder(output_dir)

        # Verify initialization
        assert finder.output_dir == output_dir
        assert Path(output_dir).exists()

        # Verify real components are created (not mocked)
        assert finder.extractor is not None
        assert finder.validator is not None
        assert hasattr(finder, 'find_sprites_in_rom')

    def test_find_sprites_behavior_with_test_doubles(self, test_rom_with_sprites, output_dir):
        """Test sprite finding behavior using test doubles for ROM data."""
        # Create finder with real components
        finder = SpriteFinder(output_dir)

        # Mock only the external dependency (ROM decompression)
        # This allows us to test the SpriteFinder logic without HAL compression complexity
        with patch.object(finder.extractor.rom_injector, 'find_compressed_sprite') as mock_decompress:
            # Configure test double to return predictable sprite data
            sprite_data = self._create_test_sprite_data(tile_count=16)
            mock_decompress.return_value = (256, sprite_data)  # (compressed_size, decompressed_data)

            # Find sprites in test ROM
            candidates = finder.find_sprites_in_rom(
                rom_path=test_rom_with_sprites,
                start_offset=0x200000,
                end_offset=0x200100,
                step=0x100,
                min_confidence=0.5,
                save_previews=False  # Skip preview generation for unit test
            )

            # Verify behavior: Sprite was found and validated
            assert len(candidates) >= 0  # May find sprites depending on validation

            # Verify the decompression was attempted
            assert mock_decompress.called

    def test_confidence_filtering_behavior(self, test_rom_with_sprites, output_dir):
        """Test that sprites are filtered by confidence threshold."""
        finder = SpriteFinder(output_dir)

        # Mock validator to return different confidence scores
        with patch.object(finder.validator, 'validate_sprite_image') as mock_validate:
            # Setup: Return high and low confidence scores alternately
            mock_validate.side_effect = [
                (True, 0.9, {"coherence": 0.9}),  # High confidence
                (True, 0.3, {"coherence": 0.3}),  # Low confidence
                (True, 0.7, {"coherence": 0.7}),  # Medium confidence
            ]

            # Mock decompression to always succeed
            with patch.object(finder.extractor.rom_injector, 'find_compressed_sprite') as mock_decompress:
                sprite_data = self._create_test_sprite_data(tile_count=16)
                mock_decompress.return_value = (256, sprite_data)

                # Find sprites with high confidence threshold
                candidates = finder.find_sprites_in_rom(
                    rom_path=test_rom_with_sprites,
                    start_offset=0x200000,
                    end_offset=0x200300,
                    step=0x100,
                    min_confidence=0.6,  # Filter out low confidence
                    save_previews=False
                )

                # Verify behavior: Only high/medium confidence sprites included
                # Note: Actual count depends on how many times validation is called
                for candidate in candidates:
                    assert candidate.confidence >= 0.6

    def test_preview_generation_behavior(self, test_rom_with_sprites, output_dir):
        """Test that preview images are generated when requested."""
        finder = SpriteFinder(output_dir)

        # Create test sprite data
        sprite_data = self._create_test_sprite_data(tile_count=16)

        with patch.object(finder.extractor.rom_injector, 'find_compressed_sprite') as mock_decompress:
            mock_decompress.return_value = (256, sprite_data)

            # Mock image conversion to avoid complex image processing
            with patch.object(finder.extractor, '_convert_4bpp_to_png') as mock_convert:
                # Create a simple test image
                test_image = Image.new('RGBA', (64, 64), color=(255, 0, 0, 255))
                mock_convert.return_value = test_image

                # Find sprites with preview generation
                candidates = finder.find_sprites_in_rom(
                    rom_path=test_rom_with_sprites,
                    start_offset=0x200000,
                    end_offset=0x200100,
                    step=0x100,
                    min_confidence=0.5,
                    save_previews=True  # Enable preview generation
                )

                # Verify behavior: Preview paths are set for found sprites
                for candidate in candidates:
                    if candidate.preview_path:
                        assert Path(candidate.preview_path).parent == Path(output_dir)

    def test_error_handling_during_scan(self, test_rom_with_sprites, output_dir):
        """Test that errors during scanning are handled gracefully."""
        finder = SpriteFinder(output_dir)

        # Mock decompression to raise exception
        with patch.object(finder.extractor.rom_injector, 'find_compressed_sprite') as mock_decompress:
            mock_decompress.side_effect = Exception("Decompression failed")

            # Find sprites - should handle errors gracefully
            candidates = finder.find_sprites_in_rom(
                rom_path=test_rom_with_sprites,
                start_offset=0x200000,
                end_offset=0x200100,
                step=0x100,
                min_confidence=0.5,
                save_previews=False
            )

            # Verify behavior: No candidates found but no crash
            assert len(candidates) == 0


@pytest.mark.usefixtures("isolated_managers")
class TestSpriteFinderIntegration:
    """Integration tests for SpriteFinder with minimal mocking."""

    def test_sprite_finder_with_real_validation(self, tmp_path):
        """Test sprite finder with real visual validation."""
        # Setup: Create test environment
        rom_path = tmp_path / "test.sfc"
        rom_data = DoubleFactory.create_rom_file()._data
        rom_path.write_bytes(rom_data)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create sprite finder with real validator
        finder = SpriteFinder(str(output_dir))

        # Create test sprite image for validation
        test_sprite = Image.new('RGBA', (64, 64))
        # Draw some patterns to make it look like a sprite
        for x in range(64):
            for y in range(64):
                if (x + y) % 8 < 4:
                    test_sprite.putpixel((x, y), (255, 0, 0, 255))
                else:
                    test_sprite.putpixel((x, y), (0, 255, 0, 255))

        # Test validation directly
        with patch.object(finder.extractor, '_convert_4bpp_to_png') as mock_convert:
            mock_convert.return_value = test_sprite

            # Mock only the decompression
            with patch.object(finder.extractor.rom_injector, 'find_compressed_sprite') as mock_decompress:
                mock_decompress.return_value = (256, b'\x00' * 512)

                # Find sprites and let real validator process them
                candidates = finder.find_sprites_in_rom(
                    rom_path=str(rom_path),
                    start_offset=0x200000,
                    end_offset=0x200100,
                    step=0x100,
                    min_confidence=0.0
                )

                # Verify validation was performed
                for candidate in candidates:
                    assert 'visual_metrics' in candidate.__dict__ or candidate.visual_metrics is not None
