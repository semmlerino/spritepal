"""
Tests for sprite finder
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.sprite_finder import SpriteCandidate, SpriteFinder

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Sprite finder may create threads during initialization"),
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.usefixtures("mock_hal"),  # HAL mocking for compression
]

@pytest.fixture
def mock_rom_data():
    """Create mock ROM data"""
    # Create some data that looks like it could contain sprites
    data = bytearray(0x300000)  # 3MB ROM

    # Add some patterns at known offsets
    # Offset 0x100000: Add recognizable pattern
    for i in range(0x1000):
        data[0x100000 + i] = (i * 7) % 256

    # Offset 0x200000: Add different pattern
    for i in range(0x2000):
        data[0x200000 + i] = (i * 13) % 256

    return bytes(data)

@pytest.fixture
def temp_output_dir():
    """Create temporary output directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def mock_extractor():
    """Create mock ROM extractor"""
    extractor = Mock()

    # Mock the rom_injector
    rom_injector = Mock()
    extractor.rom_injector = rom_injector

    # Mock _convert_4bpp_to_png method
    extractor._convert_4bpp_to_png = Mock()

    return extractor

@pytest.fixture
def mock_validator():
    """Create mock visual validator"""
    validator = Mock()

    # Default validation responses
    validator.validate_tile_data.return_value = (True, 0.7)
    validator.validate_sprite_image.return_value = (True, 0.8, {
        "coherence": 0.75,
        "tile_diversity": 0.8,
        "edge_score": 0.7,
        "symmetry": 0.6,
        "empty_space": 0.85,
        "pattern_regularity": 0.7
    })

    return validator

class TestSpriteCandidate:
    """Test SpriteCandidate dataclass"""

    def test_sprite_candidate_creation(self, tmp_path):
        """Test creating a sprite candidate"""
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

        assert candidate.offset == 0x100000
        assert candidate.compressed_size == 1024
        assert candidate.decompressed_size == 2048
        assert candidate.tile_count == 64
        assert candidate.confidence == 0.85
        assert candidate.visual_metrics == {"coherence": 0.8}
        assert candidate.preview_path == preview_path

    def test_sprite_candidate_to_dict(self, tmp_path):
        """Test converting candidate to dictionary"""
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

        result = candidate.to_dict()

        assert result["offset"] == "0x100000"
        assert result["offset_int"] == 0x100000
        assert result["compressed_size"] == 1024
        assert result["decompressed_size"] == 2048
        assert result["tile_count"] == 64
        assert result["confidence"] == 0.857  # Rounded to 3 places
        assert result["visual_metrics"]["coherence"] == 0.823
        assert result["visual_metrics"]["edge_score"] == 0.712
        assert result["preview_path"] == preview_path

class TestSpriteFinder:
    """Test SpriteFinder class"""

    def test_init(self, temp_output_dir):
        """Test sprite finder initialization"""
        with patch("core.sprite_finder.ROMExtractor") as mock_ext_class, \
             patch("core.sprite_finder.SpriteVisualValidator") as mock_val_class:

            finder = SpriteFinder(temp_output_dir)

            assert finder.output_dir == temp_output_dir
            assert Path(temp_output_dir).exists()
            mock_ext_class.assert_called_once()
            mock_val_class.assert_called_once()


    def test_find_sprites_filters_by_confidence(self, temp_output_dir, mock_rom_data,
                                              mock_extractor, mock_validator):
        """Test that low confidence sprites are filtered out"""
        rom_path = str(Path(temp_output_dir) / "test.rom")
        with Path(rom_path).open("wb") as f:
            f.write(mock_rom_data)

        # Configure validator to return low confidence
        mock_validator.validate_sprite_image.return_value = (False, 0.3, {})

        sprite_data = b"\x01\x02" * 256  # 512 bytes
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (256, sprite_data)

        with patch("core.sprite_finder.ROMExtractor", return_value=mock_extractor), \
             patch("core.sprite_finder.SpriteVisualValidator", return_value=mock_validator):

            finder = SpriteFinder(temp_output_dir)
            candidates = finder.find_sprites_in_rom(
                rom_path,
                start_offset=0x100000,
                end_offset=0x100100,
                min_confidence=0.6
            )

            # Should find no candidates due to low confidence
            assert len(candidates) == 0

    def test_find_sprites_size_validation(self, temp_output_dir, mock_rom_data,
                                        mock_extractor, mock_validator):
        """Test that sprites with invalid sizes are rejected"""
        rom_path = str(Path(temp_output_dir) / "test.rom")
        with Path(rom_path).open("wb") as f:
            f.write(mock_rom_data)

        # Return sprite data that's too small (< 16 tiles)
        small_sprite = b"\x00" * 100  # Too small
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (50, small_sprite)

        with patch("core.sprite_finder.ROMExtractor", return_value=mock_extractor), \
             patch("core.sprite_finder.SpriteVisualValidator", return_value=mock_validator):

            finder = SpriteFinder(temp_output_dir)
            candidates = finder.find_sprites_in_rom(rom_path, start_offset=0, end_offset=0x100)

            assert len(candidates) == 0  # Rejected due to size

    def test_find_sprites_saves_previews(self, temp_output_dir, mock_rom_data,
                                       mock_extractor, mock_validator):
        """Test that preview images are saved when requested"""
        rom_path = str(Path(temp_output_dir) / "test.rom")
        with Path(rom_path).open("wb") as f:
            f.write(mock_rom_data)

        sprite_data = b"\x01" * 512
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (256, sprite_data)

        with patch("core.sprite_finder.ROMExtractor", return_value=mock_extractor), \
             patch("core.sprite_finder.SpriteVisualValidator", return_value=mock_validator), \
             patch("core.sprite_finder.Image") as mock_image:

            mock_img = Mock()
            mock_image.open.return_value = mock_img

            finder = SpriteFinder(temp_output_dir)
            candidates = finder.find_sprites_in_rom(
                rom_path,
                start_offset=0,
                end_offset=0x100,
                save_previews=True
            )

            if candidates:
                # Verify save was called
                mock_img.save.assert_called()
                assert candidates[0].preview_path is not None

    def test_find_sprites_max_candidates(self, temp_output_dir, mock_rom_data,
                                        mock_extractor, mock_validator):
        """Test max_candidates limit is respected"""
        rom_path = str(Path(temp_output_dir) / "test.rom")
        with Path(rom_path).open("wb") as f:
            f.write(mock_rom_data)

        # Always return valid sprite data
        sprite_data = b"\x01" * 512
        mock_extractor.rom_injector.find_compressed_sprite.return_value = (256, sprite_data)

        with patch("core.sprite_finder.ROMExtractor", return_value=mock_extractor), \
             patch("core.sprite_finder.SpriteVisualValidator", return_value=mock_validator), \
             patch("core.sprite_finder.Image"):

            finder = SpriteFinder(temp_output_dir)
            candidates = finder.find_sprites_in_rom(
                rom_path,
                start_offset=0,
                end_offset=0x10000,  # Large range
                step=0x100,
                max_candidates=3
            )

            # Should stop at max_candidates
            assert len(candidates) <= 3

    def test_convert_to_png(self, temp_output_dir, mock_extractor):
        """Test PNG conversion method"""
        with patch("core.sprite_finder.ROMExtractor", return_value=mock_extractor):
            finder = SpriteFinder(temp_output_dir)

            tile_data = b"\x00" * 512
            output_path = os.path.join(temp_output_dir, "test.png")

            finder._convert_to_png(tile_data, output_path)

            # Verify the extractor's method was called
            mock_extractor._convert_4bpp_to_png.assert_called_once_with(tile_data, output_path)

    def test_save_results_summary(self, temp_output_dir):
        """Test saving results summary"""
        with patch("core.sprite_finder.ROMExtractor"), \
             patch("core.sprite_finder.SpriteVisualValidator"):

            finder = SpriteFinder(temp_output_dir)

            # Create test candidates
            candidates = [
                SpriteCandidate(
                    offset=0x100000,
                    compressed_size=1024,
                    decompressed_size=2048,
                    tile_count=64,
                    confidence=0.85,
                    visual_metrics={"coherence": 0.8}
                ),
                SpriteCandidate(
                    offset=0x200000,
                    compressed_size=2048,
                    decompressed_size=4096,
                    tile_count=128,
                    confidence=0.75,
                    visual_metrics={"coherence": 0.7}
                )
            ]

            rom_path = "test.rom"
            finder._save_results_summary(rom_path, candidates)

            # Check JSON summary exists
            json_path = os.path.join(temp_output_dir, "sprite_search_results_test.rom.json")
            assert os.path.exists(json_path)

            with open(json_path) as f:
                summary = json.load(f)

            assert summary["rom_file"] == "test.rom"
            assert summary["total_candidates"] == 2
            assert len(summary["candidates"]) == 2
            assert summary["candidates"][0]["offset"] == "0x100000"

            # Check text report exists
            txt_path = os.path.join(temp_output_dir, "sprite_search_report_test.rom.txt")
            assert os.path.exists(txt_path)

    def test_quick_scan_known_areas(self, temp_output_dir, mock_rom_data):
        """Test quick scan of known sprite areas"""
        rom_path = str(Path(temp_output_dir) / "test.rom")
        with Path(rom_path).open("wb") as f:
            f.write(mock_rom_data)

        with patch("core.sprite_finder.ROMExtractor"), \
             patch("core.sprite_finder.SpriteVisualValidator"):

            finder = SpriteFinder(temp_output_dir)

            # Mock find_sprites_in_rom to return test data
            test_candidates = [
                SpriteCandidate(0x100000, 100, 200, 10, 0.8, {}),
                SpriteCandidate(0x180000, 150, 300, 15, 0.75, {})
            ]

            with patch.object(finder, "find_sprites_in_rom", return_value=test_candidates):
                candidates = finder.quick_scan_known_areas(rom_path)

                # Should have called find_sprites_in_rom
                finder.find_sprites_in_rom.assert_called()

                # Should return candidates
                assert len(candidates) >= 2

    def test_exception_handling(self, temp_output_dir, mock_rom_data,
                               mock_extractor, mock_validator):
        """Test that exceptions during scanning are handled gracefully"""
        rom_path = str(Path(temp_output_dir) / "test.rom")
        with Path(rom_path).open("wb") as f:
            f.write(mock_rom_data)

        # Make decompression always fail
        mock_extractor.rom_injector.find_compressed_sprite.side_effect = Exception("Decompress error")

        with patch("core.sprite_finder.ROMExtractor", return_value=mock_extractor), \
             patch("core.sprite_finder.SpriteVisualValidator", return_value=mock_validator):

            finder = SpriteFinder(temp_output_dir)

            # Should not crash, just return empty list
            candidates = finder.find_sprites_in_rom(
                rom_path,
                start_offset=0,
                end_offset=0x1000
            )

            assert candidates == []
