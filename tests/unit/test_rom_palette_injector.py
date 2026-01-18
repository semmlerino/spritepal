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


class TestBGR555Conversion:
    """Test BGR555 color conversion methods."""

    def test_black_conversion(self):
        """Test black (0, 0, 0) converts to 0x0000."""
        result = ROMPaletteInjector.rgb888_to_bgr555(0, 0, 0)
        assert result == 0x0000

    def test_white_conversion(self):
        """Test white (255, 255, 255) converts to 0x7FFF."""
        result = ROMPaletteInjector.rgb888_to_bgr555(255, 255, 255)
        assert result == 0x7FFF  # (31 << 10) | (31 << 5) | 31

    def test_pure_red_conversion(self):
        """Test pure red (255, 0, 0) converts correctly."""
        result = ROMPaletteInjector.rgb888_to_bgr555(255, 0, 0)
        # r5 = 31, g5 = 0, b5 = 0 -> (0 << 10) | (0 << 5) | 31 = 31
        assert result == 31

    def test_pure_green_conversion(self):
        """Test pure green (0, 255, 0) converts correctly."""
        result = ROMPaletteInjector.rgb888_to_bgr555(0, 255, 0)
        # r5 = 0, g5 = 31, b5 = 0 -> (0 << 10) | (31 << 5) | 0 = 992
        assert result == 992

    def test_pure_blue_conversion(self):
        """Test pure blue (0, 0, 255) converts correctly."""
        result = ROMPaletteInjector.rgb888_to_bgr555(0, 0, 255)
        # r5 = 0, g5 = 0, b5 = 31 -> (31 << 10) | (0 << 5) | 0 = 31744
        assert result == 31744

    def test_roundtrip_conversion(self):
        """Test that extraction and injection are approximately inverse operations.

        Note: Due to 8-bit to 5-bit quantization, exact roundtrip is not possible.
        The tolerance is +-7 (since 255/31 ≈ 8.2, values can vary by up to 7).
        """
        # Create test colors
        test_colors = [
            (0, 0, 0),
            (255, 255, 255),
            (128, 128, 128),
            (200, 100, 50),
        ]

        for r, g, b in test_colors:
            # Convert to BGR555
            bgr555 = ROMPaletteInjector.rgb888_to_bgr555(r, g, b)

            # Extract back (simulate extraction)
            r5 = bgr555 & 0x1F
            g5 = (bgr555 >> 5) & 0x1F
            b5 = (bgr555 >> 10) & 0x1F

            r8 = (r5 << 3) | (r5 >> 2)
            g8 = (g5 << 3) | (g5 >> 2)
            b8 = (b5 << 3) | (b5 >> 2)

            # Check within tolerance (quantization can cause +-7 difference)
            assert abs(r - r8) <= 7, f"Red mismatch: {r} -> {r8}"
            assert abs(g - g8) <= 7, f"Green mismatch: {g} -> {g8}"
            assert abs(b - b8) <= 7, f"Blue mismatch: {b} -> {b8}"

    def test_clamping_overflow(self):
        """Test that values > 255 are clamped."""
        result = ROMPaletteInjector.rgb888_to_bgr555(300, 400, 500)
        # All should be clamped to 255, which gives r5=31, g5=31, b5=31
        assert result == 0x7FFF

    def test_clamping_underflow(self):
        """Test that values < 0 are clamped."""
        result = ROMPaletteInjector.rgb888_to_bgr555(-10, -20, -30)
        # All should be clamped to 0
        assert result == 0x0000


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
