"""
Unit tests for ROM palette injection functionality.
"""

from __future__ import annotations

import pytest

from core.rom_palette_injector import ROMPaletteInjector

pytestmark = [
    pytest.mark.headless,
    pytest.mark.unit,
]


class TestColorsToBytes:
    """Test palette color conversion to bytes."""

    def test_produces_32_bytes(self):
        """Test that 16 colors produce exactly 32 bytes."""
        colors = [(0, 0, 0)] * 16
        result = ROMPaletteInjector.colors_to_bgr555_bytes(colors)
        assert len(result) == 32

    def test_wrong_color_count_raises(self):
        """Test that wrong color count raises ValueError."""
        with pytest.raises(ValueError, match="Expected 16 colors"):
            ROMPaletteInjector.colors_to_bgr555_bytes([(0, 0, 0)] * 8)

        with pytest.raises(ValueError, match="Expected 16 colors"):
            ROMPaletteInjector.colors_to_bgr555_bytes([(0, 0, 0)] * 20)

    def test_little_endian_byte_order(self):
        """Test that BGR555 values are stored in little-endian order."""
        # Pure blue: bgr555 = 0x7C00 (31 << 10)
        colors = [(0, 0, 255)] + [(0, 0, 0)] * 15
        result = ROMPaletteInjector.colors_to_bgr555_bytes(colors)

        # Little-endian: low byte first
        assert result[0] == 0x00  # Low byte of 0x7C00
        assert result[1] == 0x7C  # High byte of 0x7C00

    def test_all_black_palette(self):
        """Test all black palette produces all zeros."""
        colors = [(0, 0, 0)] * 16
        result = ROMPaletteInjector.colors_to_bgr555_bytes(colors)
        assert result == bytes(32)

    def test_all_white_palette(self):
        """Test all white palette produces 0xFF7F pattern."""
        colors = [(255, 255, 255)] * 16
        result = ROMPaletteInjector.colors_to_bgr555_bytes(colors)

        # 0x7FFF in little-endian is 0xFF, 0x7F
        for i in range(0, 32, 2):
            assert result[i] == 0xFF
            assert result[i + 1] == 0x7F


class TestROMPaletteInjector:
    """Test ROMPaletteInjector class."""

    def test_initialization(self):
        """Test injector can be instantiated."""
        injector = ROMPaletteInjector()
        assert injector is not None

    def test_inject_wrong_color_count(self, tmp_path):
        """Test that injecting wrong color count fails."""
        injector = ROMPaletteInjector()

        # Create minimal test ROM
        rom_path = tmp_path / "test.sfc"
        rom_data = bytearray(0x10000)  # 64KB minimum
        rom_path.write_bytes(rom_data)

        output_path = tmp_path / "test_modified.sfc"
        colors = [(0, 0, 0)] * 8  # Wrong count

        success, msg = injector.inject_palette_to_rom(
            str(rom_path),
            str(output_path),
            0x1000,
            colors,
        )

        assert not success
        assert "Expected 16 colors" in msg
