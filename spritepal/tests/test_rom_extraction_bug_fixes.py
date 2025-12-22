"""
Tests for ROM extraction bug fixes.

Covers:
- ROMService path handling (no double .png extension)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from core.services.rom_service import ROMService

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
