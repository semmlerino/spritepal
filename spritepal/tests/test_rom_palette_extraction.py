"""
Test ROM palette extraction functionality
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from core.rom_palette_extractor import ROMPaletteExtractor

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]

class TestROMPaletteExtraction:
    """Test ROM palette extraction"""

    def setup_method(self):
        """Set up test fixtures"""
        self.extractor = ROMPaletteExtractor()

    def create_test_rom_with_palettes(self, tmpdir):
        """Create a test ROM file with palette data"""
        rom_path = Path(tmpdir) / "test.sfc"

        # Create test ROM data
        rom_data = bytearray(0x300000)  # 3MB ROM

        # Add test palette data at offset 0x288000
        palette_offset = 0x288000

        # Create 16 palettes with distinct colors
        for pal_idx in range(16):
            for color_idx in range(16):
                # Create BGR555 color value
                # Use palette index to create distinct colors
                r = (pal_idx * 2) & 0x1F
                g = ((pal_idx + 5) * 2) & 0x1F
                b = ((pal_idx + 10) * 2) & 0x1F

                bgr555 = (b << 10) | (g << 5) | r

                # Write to ROM (little-endian)
                offset = palette_offset + (pal_idx * 32) + (color_idx * 2)
                rom_data[offset] = bgr555 & 0xFF
                rom_data[offset + 1] = (bgr555 >> 8) & 0xFF

        # Write ROM file
        with rom_path.open("wb") as f:
            f.write(rom_data)

        return str(rom_path), palette_offset

    def test_extract_single_palette(self):
        """Test extracting a single palette from ROM"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_path, palette_offset = self.create_test_rom_with_palettes(tmpdir)
            output_base = str(Path(tmpdir) / "test_sprite")

            # Extract palette 8
            files = self.extractor.extract_palettes_from_rom(
                rom_path, palette_offset, [8], output_base
            )

            assert len(files) == 1
            assert Path(files[0]).exists()
            assert files[0].endswith("_pal8.pal.json")

            # Load and verify palette
            with Path(files[0]).open() as f:
                palette_data = json.load(f)

            assert "colors" in palette_data
            assert len(palette_data["colors"]) == 16

            # Check first color (should be based on our formula)
            first_color = palette_data["colors"][0]
            assert isinstance(first_color, list)
            assert len(first_color) == 3

    def test_extract_multiple_palettes(self):
        """Test extracting multiple palettes from ROM"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_path, palette_offset = self.create_test_rom_with_palettes(tmpdir)
            output_base = str(Path(tmpdir) / "test_sprite")

            # Extract palettes 8-11 (typical Kirby palettes)
            files = self.extractor.extract_palettes_from_rom(
                rom_path, palette_offset, [8, 9, 10, 11], output_base
            )

            assert len(files) == 4

            # Verify all files exist and have correct names
            for idx, pal_file in enumerate(files):
                assert Path(pal_file).exists()
                assert f"_pal{8+idx}.pal.json" in pal_file

    def test_palette_bgr555_conversion(self):
        """Test BGR555 to RGB888 conversion"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create ROM with known palette values
            rom_path = Path(tmpdir) / "test.sfc"
            rom_data = bytearray(0x300000)

            # Set specific test colors at palette 0
            test_colors = [
                0x0000,  # Black (0, 0, 0)
                0x001F,  # Red (248, 0, 0)
                0x03E0,  # Green (0, 248, 0)
                0x7C00,  # Blue (0, 0, 248)
                0x7FFF,  # White (248, 248, 248)
            ]

            palette_offset = 0x100000
            for i, bgr555 in enumerate(test_colors):
                rom_data[palette_offset + i * 2] = bgr555 & 0xFF
                rom_data[palette_offset + i * 2 + 1] = (bgr555 >> 8) & 0xFF

            with rom_path.open("wb") as f:
                f.write(rom_data)

            # Extract palette
            output_base = str(Path(tmpdir) / "test")
            files = self.extractor.extract_palettes_from_rom(
                str(rom_path), palette_offset, [0], output_base
            )

            # Load and verify colors
            with Path(files[0]).open() as f:
                palette_data = json.load(f)

            colors = palette_data["colors"]

            # Check conversions
            # Note: SNES color conversion (value << 3) | (value >> 2) gives 255 for max value (31)
            assert colors[0] == [0, 0, 0]  # Black
            assert colors[1] == [255, 0, 0]  # Red (31 << 3 | 31 >> 2 = 255)
            assert colors[2] == [0, 255, 0]  # Green
            assert colors[3] == [0, 0, 255]  # Blue
            assert colors[4] == [255, 255, 255]  # White

    def test_get_palette_config_from_sprite(self):
        """Test getting palette configuration for a sprite"""
        # Mock game config
        game_config = {
            "palettes": {"offset": "0x288000", "size": 512},
            "sprites": {"kirby_normal": {"palette_indices": [8, 9, 10, 11]}},
        }

        offset, indices = self.extractor.get_palette_config_from_sprite_config(
            game_config, "kirby_normal"
        )

        assert offset == 0x288000
        assert indices == [8, 9, 10, 11]

    def test_extract_palette_range(self):
        """Test extracting a range of palettes"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_path, palette_offset = self.create_test_rom_with_palettes(tmpdir)

            # Extract palettes 8-11
            palettes = self.extractor.extract_palette_range(
                rom_path, palette_offset, 8, 11
            )

            assert len(palettes) == 4
            assert 8 in palettes
            assert 11 in palettes

            # Each palette should have 16 colors
            for idx in range(8, 12):
                assert len(palettes[idx]) == 16
                assert all(len(color) == 3 for color in palettes[idx])

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
