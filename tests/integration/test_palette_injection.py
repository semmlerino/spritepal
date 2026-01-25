"""
Integration tests for ROM palette injection functionality.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.rom_injector import ROMInjector
from core.rom_palette_injector import ROMPaletteInjector

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]


class TestPaletteInjectionIntegration:
    """Integration tests for palette injection."""

    @pytest.fixture
    def test_rom_with_palette(self, tmp_path):
        """Create a test ROM with a valid header and palette data."""
        rom_path = tmp_path / "test.sfc"

        # Create minimal SNES ROM with valid header
        data = bytearray(0x150000)  # ~1.3MB ROM

        # Set up LoROM header at 0x7FC0
        header_offset = 0x7FC0
        title = b"TEST ROM".ljust(21, b" ")
        data[header_offset : header_offset + 21] = title
        data[header_offset + 21] = 0x20  # LoROM
        data[header_offset + 23] = 0x0A  # 1MB ROM

        # Initial checksum (will be updated)
        checksum = 0x1234
        complement = checksum ^ 0xFFFF
        data[header_offset + 28 : header_offset + 30] = complement.to_bytes(2, "little")
        data[header_offset + 30 : header_offset + 32] = checksum.to_bytes(2, "little")

        # Add known palette data at offset 0x144037 (similar to King Dedede)
        palette_offset = 0x144037

        # Create a test palette with known colors
        for color_idx in range(16):
            # Create distinct BGR555 values
            r5 = color_idx * 2
            g5 = (color_idx * 2 + 5) & 0x1F
            b5 = (color_idx * 2 + 10) & 0x1F
            bgr555 = (b5 << 10) | (g5 << 5) | r5

            offset = palette_offset + (color_idx * 2)
            data[offset] = bgr555 & 0xFF
            data[offset + 1] = (bgr555 >> 8) & 0xFF

        rom_path.write_bytes(data)
        return str(rom_path), palette_offset

    def test_inject_palette_via_rom_injector(self, test_rom_with_palette, tmp_path):
        """Test injecting palette through ROMInjector."""
        rom_path, palette_offset = test_rom_with_palette
        output_path = str(tmp_path / "modified.sfc")

        injector = ROMInjector()

        # Create modified palette - make first color bright red
        colors = [(255, 0, 0)] + [(i * 16, i * 16, i * 16) for i in range(1, 16)]

        success, msg = injector.inject_palette_to_rom(
            rom_path,
            output_path,
            palette_offset,
            colors,
            ignore_checksum=True,  # Test ROM has placeholder checksum
        )

        assert success, f"Injection failed: {msg}"
        assert "Successfully injected" in msg
        assert Path(output_path).exists()

        # Verify the palette was injected correctly
        with Path(output_path).open("rb") as f:
            modified_data = f.read()

        # Check first color is bright red (BGR555 = 0x001F = 31)
        low_byte = modified_data[palette_offset]
        high_byte = modified_data[palette_offset + 1]
        bgr555 = (high_byte << 8) | low_byte

        r5 = bgr555 & 0x1F
        g5 = (bgr555 >> 5) & 0x1F
        b5 = (bgr555 >> 10) & 0x1F

        assert r5 == 31, f"Expected red = 31, got {r5}"
        assert g5 == 0, f"Expected green = 0, got {g5}"
        assert b5 == 0, f"Expected blue = 0, got {b5}"

    def test_offset_out_of_bounds(self, test_rom_with_palette, tmp_path):
        """Test that injection fails gracefully for out-of-bounds offset."""
        rom_path, _ = test_rom_with_palette
        output_path = str(tmp_path / "modified.sfc")

        injector = ROMPaletteInjector()
        colors = [(0, 0, 0)] * 16

        # Use an offset beyond ROM size
        success, msg = injector.inject_palette_to_rom(
            rom_path,
            output_path,
            0xFFFFFF,  # Way beyond ROM size
            colors,
            ignore_checksum=True,  # Test ROM has placeholder checksum
        )

        assert not success
        assert "overflow" in msg.lower() or "offset" in msg.lower()
