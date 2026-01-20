"""
Integration tests for ROM sprite extraction functionality.

Tests with real file operations and minimal mocking.
For unit tests with mocked dependencies, see tests/unit/test_rom_extractor_logic.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from utils.constants import BYTES_PER_TILE, TILE_HEIGHT, TILE_WIDTH

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Uses app_context which owns worker threads"),
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.usefixtures("app_context", "mock_hal"),
]


class TestROMExtractorIntegration:
    """Integration tests with real file operations"""

    def test_4bpp_conversion_integration(self, tmp_path):
        """Test 4bpp conversion with real data and file operations"""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

        # Create realistic 4bpp test data (2 tiles)
        tile_data = bytearray(2 * BYTES_PER_TILE)

        # First tile: create a simple gradient pattern
        for row in range(8):
            for plane in range(4):
                base_offset = plane * 16 if plane >= 2 else 0
                plane_offset = plane % 2
                tile_data[base_offset + row * 2 + plane_offset] = row * 16  # Gradient

        # Second tile: create a checkerboard pattern
        tile_offset = BYTES_PER_TILE
        for row in range(8):
            pattern = 0xAA if row % 2 == 0 else 0x55  # Alternating pattern
            tile_data[tile_offset + row * 2] = pattern  # Plane 0
            tile_data[tile_offset + row * 2 + 1] = ~pattern & 0xFF  # Plane 1
            tile_data[tile_offset + 16 + row * 2] = 0x00  # Plane 2
            tile_data[tile_offset + 16 + row * 2 + 1] = 0x00  # Plane 3

        output_path = tmp_path / "integration_test.png"
        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        # Verify output
        assert tile_count == 2
        assert output_path.exists()

        # Verify image properties
        with Image.open(output_path) as img:
            assert img.mode == "P"  # Palette mode
            assert img.size == (16 * TILE_WIDTH, 1 * TILE_HEIGHT)

            # Verify some pixels have non-zero values (pattern was applied)
            pixels = list(img.getdata())
            assert any(p > 0 for p in pixels)  # Should have non-black pixels

    def test_error_recovery_file_cleanup(self, tmp_path):
        """Test that failed extractions don't leave partial files"""
        from unittest.mock import Mock

        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

        # Mock dependencies to cause error after PNG creation starts
        extractor.rom_injector = Mock()
        extractor.rom_injector.read_rom_header.side_effect = Exception("Simulated error")

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"Mock ROM")
        output_base = tmp_path / "failed_extraction"
        expected_png = Path(f"{output_base}.png")

        with pytest.raises(Exception, match="Simulated error"):
            extractor.extract_sprite_from_rom(str(rom_path), 0x8000, str(output_base), "test_sprite")

        # Verify no partial files were left behind
        # (In this case, the error happens before PNG creation, so no cleanup needed)
        assert not expected_png.exists()

    def test_large_sprite_processing(self, tmp_path):
        """Test processing of large sprite data"""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

        # Create data for 64 tiles (realistic sprite size)
        num_tiles = 64
        tile_data = b"\x00" * (num_tiles * BYTES_PER_TILE)

        output_path = tmp_path / "large_sprite.png"
        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == num_tiles
        assert output_path.exists()

        # Verify large image dimensions
        with Image.open(output_path) as img:
            expected_width = 16 * TILE_WIDTH
            expected_height = 4 * TILE_HEIGHT  # ceil(64/16) = 4 rows
            assert img.size == (expected_width, expected_height)

    def test_boundary_conditions(self, tmp_path):
        """Test boundary conditions and edge cases"""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

        # Test with exactly 16 tiles (one full row)
        tile_data = b"\x00" * (16 * BYTES_PER_TILE)
        output_path = tmp_path / "full_row.png"

        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == 16
        with Image.open(output_path) as img:
            assert img.size == (16 * TILE_WIDTH, 1 * TILE_HEIGHT)

        # Test with 17 tiles (one tile into second row)
        tile_data = b"\x00" * (17 * BYTES_PER_TILE)
        output_path = tmp_path / "second_row.png"

        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == 17
        with Image.open(output_path) as img:
            assert img.size == (16 * TILE_WIDTH, 2 * TILE_HEIGHT)

    def test_boundary_sprite_size(self, tmp_path):
        """Test edge case with minimum valid sprite size"""
        from core.app_context import get_app_context

        extractor = get_app_context().rom_extractor

        # Test with exactly 1 tile (minimum valid sprite)
        tile_data = b"\x00" * BYTES_PER_TILE
        output_path = tmp_path / "single_tile.png"

        tile_count = extractor._convert_4bpp_to_png(tile_data, str(output_path))

        assert tile_count == 1
        assert output_path.exists()
        with Image.open(output_path) as img:
            assert img.size == (16 * TILE_WIDTH, 1 * TILE_HEIGHT)
