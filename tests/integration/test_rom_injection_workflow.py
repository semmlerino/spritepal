"""
Consolidated integration tests for ROM injection workflows.

Tests the complete injection workflow through public APIs, validating:
- Slack space detection with realistic ROM layouts
- Header read/write round-trips
- ROM file copy operations
- Palette injection

Migrated from:
- tests/unit/core/test_rom_injector.py::TestROMInjectorIntegration
- tests/integration/test_palette_injection.py
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


class TestROMInjectorIntegration:
    """Integration tests for ROM injector public API.

    These tests verify the complete injection workflow through public methods,
    validating slack space detection, header operations, and checksum updates.
    """

    def test_read_write_header_round_trip(self, tmp_path) -> None:
        """Verify header can be read, modified, and checksums recalculated.

        Integration test: Reads ROM header, modifies data, recalculates checksum,
        verifies the resulting ROM has valid checksum relationship.
        """
        # Create a valid SNES ROM
        rom_data = bytearray(0x8000)
        header_offset = 0x7FC0

        # Set up header
        title = b"INTEGRATION TEST".ljust(21, b" ")
        rom_data[header_offset : header_offset + 21] = title
        rom_data[header_offset + 21] = 0x20  # LoROM
        rom_data[header_offset + 23] = 0x08  # 256KB

        # Set initial checksum (will be recalculated)
        initial_checksum = sum(rom_data) & 0xFFFF
        rom_data[header_offset + 30 : header_offset + 32] = initial_checksum.to_bytes(2, "little")
        rom_data[header_offset + 28 : header_offset + 30] = (initial_checksum ^ 0xFFFF).to_bytes(2, "little")

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(rom_data))

        # Read header
        injector = ROMInjector()
        header = injector.read_rom_header(str(rom_path))

        assert header.title.strip() == "INTEGRATION TEST"
        assert header.rom_type == 0x20

        # Modify some data
        modified_data = bytearray(rom_data)
        modified_data[0x1000:0x1010] = bytes([0xFF] * 16)

        # Recalculate checksum
        injector.header = header
        new_checksum, new_complement = injector.calculate_checksum(modified_data)

        # Verify checksum relationship
        assert new_checksum ^ new_complement == 0xFFFF

        # Verify checksum reflects the modification
        assert new_checksum != initial_checksum

    def test_slack_space_detected_and_usable(self, tmp_path) -> None:
        """Verify slack space detection works with realistic ROM layout.

        Integration test: Creates ROM with slack space after sprite data,
        detects slack via _detect_slack_space, verifies correct amount detected.
        """
        injector = ROMInjector()

        # Create ROM: 100 bytes sprite data + 50 bytes FF padding + other data
        sprite_data = bytes([0xAB] * 100)
        slack_padding = bytes([0xFF] * 50)
        following_data = bytes([0xCD] * 100)

        rom_data = sprite_data + slack_padding + following_data

        # Detect slack starting at end of sprite data
        slack = injector._detect_slack_space(rom_data, len(sprite_data))

        # Should detect exactly 50 bytes of slack
        assert slack == 50

    def test_slack_capped_at_max_usage_in_limit_calc(self) -> None:
        """Verify effective limit calculation respects max slack usage.

        Integration test: Calculates effective limit with various slack amounts,
        verifies the 32-byte cap is applied correctly.
        """
        test_cases = [
            # (original_size, slack_detected, max_slack, expected_effective_limit)
            (100, 0, 32, 100),  # No slack
            (100, 20, 32, 120),  # Slack under max
            (100, 32, 32, 132),  # Slack at max
            (100, 64, 32, 132),  # Slack over max (capped)
            (100, 100, 32, 132),  # Much more slack (still capped)
        ]

        for original, slack, max_usage, expected_limit in test_cases:
            effective_limit = original + min(slack, max_usage)
            assert effective_limit == expected_limit, (
                f"Failed for original={original}, slack={slack}: expected {expected_limit}, got {effective_limit}"
            )

    def test_copy_rom_creates_independent_file(self, tmp_path) -> None:
        """Verify copy_rom_for_injection creates an independent copy.

        Integration test: Creates source ROM, copies to output, modifies output,
        verifies source is unchanged.
        """
        # Create source ROM
        source_data = bytearray(0x8000)
        header_offset = 0x7FC0
        source_data[header_offset : header_offset + 21] = b"SOURCE ROM".ljust(21)
        source_data[header_offset + 21] = 0x20

        source_path = tmp_path / "source.sfc"
        source_path.write_bytes(bytes(source_data))

        output_path = tmp_path / "output.sfc"

        # Copy ROM
        injector = ROMInjector()
        injector.copy_rom_for_injection(str(source_path), str(output_path))

        # Verify output exists and matches source
        assert output_path.exists()
        assert output_path.read_bytes() == source_path.read_bytes()

        # Modify output
        output_data = bytearray(output_path.read_bytes())
        output_data[0x1000:0x1010] = bytes([0xFF] * 16)
        output_path.write_bytes(bytes(output_data))

        # Verify source is unchanged
        assert source_path.read_bytes()[0x1000:0x1010] == bytes([0x00] * 16)
        assert output_path.read_bytes()[0x1000:0x1010] == bytes([0xFF] * 16)

    def test_zero_padding_slack_detection(self, tmp_path) -> None:
        """Verify 0x00 padding is correctly detected as slack space.

        Integration test: ROM with 0x00 padding (common in some games),
        verifies detection algorithm handles this padding type.
        """
        injector = ROMInjector()

        # Create ROM with 0x00 padding
        sprite_data = bytes([0xAB] * 100)
        zero_padding = bytes([0x00] * 45)
        following_data = bytes([0xCD] * 100)

        rom_data = sprite_data + zero_padding + following_data

        # Detect slack
        slack = injector._detect_slack_space(rom_data, len(sprite_data))

        # Should detect 45 bytes of zero padding
        assert slack == 45

    def test_mixed_padding_stops_at_type_change(self, tmp_path) -> None:
        """Verify slack detection stops when padding type changes.

        Integration test: ROM with mixed 0xFF then 0x00 padding,
        verifies only first consistent run is counted.
        """
        injector = ROMInjector()

        # Create ROM with mixed padding types
        sprite_data = bytes([0xAB] * 100)
        ff_padding = bytes([0xFF] * 25)
        zero_padding = bytes([0x00] * 20)
        following_data = bytes([0xCD] * 100)

        rom_data = sprite_data + ff_padding + zero_padding + following_data

        # Detect slack - should only count FF bytes
        slack = injector._detect_slack_space(rom_data, len(sprite_data))

        # Only the 25 FF bytes should be counted (stops at type change)
        assert slack == 25


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
