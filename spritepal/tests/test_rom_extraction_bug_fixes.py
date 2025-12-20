"""
Tests for ROM extraction bug fixes.

Covers:
- ROMService path handling (no double .png extension)
- OptimizedROMExtractor offset validation
- OptimizedROMExtractor image rendering (not blank)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from core.optimized_rom_extractor import OptimizedROMExtractor
from core.services.rom_service import ROMService
from utils.constants import BYTES_PER_TILE

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.usefixtures("isolated_managers", "mock_hal"),
]


class TestROMServicePathHandling:
    """Test ROMService correctly handles output paths without double .png extension."""

    def test_extract_from_rom_no_double_png_extension(self, tmp_path: Path):
        """Verify extract_from_rom doesn't create .png.png files (bug fix)."""
        # Setup: Create a fake ROM file
        rom_path = tmp_path / "test.smc"
        rom_path.write_bytes(b"\x00" * 0x10000)

        output_base = str(tmp_path / "test_sprite")
        expected_png = tmp_path / "test_sprite.png"
        wrong_png = tmp_path / "test_sprite.png.png"

        # Create mock extractor that returns the correct path
        mock_extractor = Mock()
        # The extractor should return (output_path, extraction_info)
        mock_extractor.extract_sprite_from_rom.return_value = (
            str(expected_png),
            {"tile_count": 10, "compressed_size": 100},
        )

        # Create a test image at expected path for Image.open to work
        test_image = Image.new("L", (64, 64), 128)
        test_image.save(expected_png)

        # Create ROMService with mocked extractor
        service = ROMService()
        service._rom_extractor = mock_extractor

        # Execute
        with patch.object(service, "_validate_rom_file"):
            with patch.object(service, "_validate_offset"):
                result = service.extract_from_rom(
                    str(rom_path),
                    offset=0x1000,
                    output_base=output_base,
                    sprite_name="test_sprite",
                    cgram_path=None,
                )

        # Verify: extractor was called with base path (no .png)
        mock_extractor.extract_sprite_from_rom.assert_called_once()
        call_args = mock_extractor.extract_sprite_from_rom.call_args
        assert call_args[0][2] == output_base, "Should pass output_base without .png"
        assert call_args[0][3] == "test_sprite", "Should pass sprite_name"

        # Verify: result uses correct path
        assert str(expected_png) in result
        assert not wrong_png.exists(), "Should not create .png.png file"


class TestOptimizedROMExtractorValidation:
    """Test OptimizedROMExtractor offset validation."""

    def test_negative_offset_raises_value_error(self, tmp_path: Path):
        """Verify negative offset raises ValueError."""
        rom_path = tmp_path / "test.smc"
        rom_path.write_bytes(b"\x00" * 0x10000)

        extractor = OptimizedROMExtractor()

        with pytest.raises(ValueError, match="Invalid negative offset"):
            extractor.extract_sprite_data(str(rom_path), sprite_offset=-1)

    def test_offset_beyond_rom_size_raises_value_error(self, tmp_path: Path):
        """Verify offset beyond ROM size raises ValueError."""
        rom_path = tmp_path / "test.smc"
        rom_data = b"\x00" * 0x10000  # 64KB ROM
        rom_path.write_bytes(rom_data)

        extractor = OptimizedROMExtractor()

        # Offset at exactly ROM size should fail
        with pytest.raises(ValueError, match="exceeds ROM size"):
            extractor.extract_sprite_data(str(rom_path), sprite_offset=0x10000)

        # Offset beyond ROM size should fail
        with pytest.raises(ValueError, match="exceeds ROM size"):
            extractor.extract_sprite_data(str(rom_path), sprite_offset=0x20000)


class TestOptimizedROMExtractorImageRendering:
    """Test OptimizedROMExtractor renders actual images, not blank ones."""

    def test_extract_single_sprite_renders_pixels(self, tmp_path: Path):
        """Verify _extract_single_sprite produces non-blank images."""
        rom_path = tmp_path / "test.smc"
        rom_path.write_bytes(b"\x00" * 0x10000)

        extractor = OptimizedROMExtractor()

        # Create mock sprite data (at least MIN_SPRITE_TILES=16 worth)
        # 16 tiles = 512 bytes of non-zero data to ensure rendering happens
        tile_count = 16
        mock_sprite_data = bytes([i % 256 for i in range(tile_count * BYTES_PER_TILE)])

        # Mock the extract_sprite_data to return our test data
        with patch.object(extractor, "extract_sprite_data", return_value=mock_sprite_data):
            result = extractor._extract_single_sprite(str(rom_path), offset=0x1000)

        # Verify extraction succeeded
        assert result.success is True
        assert result.data == mock_sprite_data
        assert result.image is not None, "Should produce an image"

        # Verify image is not blank (has some non-transparent pixels)
        image = result.image
        pixels = list(image.getdata())

        # Count non-transparent pixels (alpha > 0)
        non_transparent = sum(1 for p in pixels if len(p) == 4 and p[3] > 0)
        assert non_transparent > 0, "Image should have non-transparent pixels (not blank)"
