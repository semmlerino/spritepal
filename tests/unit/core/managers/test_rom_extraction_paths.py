"""
Tests for ROM extraction path handling.

Bug fix: Prevent extract_from_rom from creating .png.png files.
Split from tests/integration/test_rom_extraction_regression.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from utils.file_validator import FileValidator

pytestmark = [
    pytest.mark.usefixtures("mock_hal"),
    pytest.mark.skip_thread_cleanup(reason="Uses app_context which owns worker threads"),
    pytest.mark.headless,
]


class TestROMExtractionPathHandling:
    """Test CoreOperationsManager correctly handles output paths without double .png extension.

    Bug fix: Prevent extract_from_rom from creating .png.png files.
    """

    def test_extract_from_rom_no_double_png_extension(self, tmp_path: Path, app_context):
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

        # Get manager from context and mock the extractor
        manager = app_context.core_operations_manager
        original_extractor = manager._rom_extractor
        manager._rom_extractor = mock_extractor

        try:
            # Execute - patch FileValidator to skip validation (test is about path handling)
            with patch.object(FileValidator, "validate_rom_file_or_raise"):
                result = manager.extract_from_rom(
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

            # Verify: result uses correct path (returns list of file paths)
            assert str(expected_png) in result
            assert not wrong_png.exists(), "Should not create .png.png file"
        finally:
            manager._rom_extractor = original_extractor
