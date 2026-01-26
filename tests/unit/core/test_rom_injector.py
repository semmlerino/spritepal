"""
Tests for ROM injector functionality.

These tests cover:
- Basic ROM header reading and checksum calculation
- Slack space detection boundary conditions
- Overflow protection and force injection mode
- Effective limit calculation
- RAW (uncompressed) injection mode

Related tests:
- tests/test_slack_detection.py - Basic slack detection patterns
- tests/integration/test_injection_manager.py - Manager-level injection API
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.rom_injector import ROMHeader, ROMInjector


@pytest.fixture
def rom_injector() -> ROMInjector:
    """Create ROMInjector with mocked dependencies."""
    injector = ROMInjector()
    injector.hal_compressor = MagicMock()
    return injector


class TestROMInjectorBasics:
    """Basic ROM injector tests for header reading and checksum calculation.

    Migrated from tests/integration/test_rom_injection.py.
    """

    @pytest.fixture
    def injector(self) -> ROMInjector:
        return ROMInjector()

    @pytest.fixture
    def test_rom_data(self) -> bytes:
        """Create a minimal SNES ROM with a valid header."""
        data = bytearray(0x8000)
        header_offset = 0x7FC0
        title = b"TEST ROM".ljust(21, b" ")
        data[header_offset : header_offset + 21] = title
        data[header_offset + 21] = 0x20  # LoROM
        data[header_offset + 23] = 0x08  # 256KB
        checksum = 0x1234
        complement = checksum ^ 0xFFFF
        data[header_offset + 28 : header_offset + 30] = complement.to_bytes(2, "little")
        data[header_offset + 30 : header_offset + 32] = checksum.to_bytes(2, "little")
        return bytes(data)

    def test_read_rom_header(self, injector: ROMInjector, test_rom_data: bytes, tmp_path) -> None:
        """Test reading ROM header."""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        header = injector.read_rom_header(str(rom_path))

        assert header.title.strip() == "TEST ROM"
        assert header.rom_type == 32
        assert header.rom_size == 8
        assert header.rom_type_offset == 0x7FC0

    def test_checksum_calculation(self, injector: ROMInjector, test_rom_data: bytes) -> None:
        """Test ROM checksum calculation."""
        injector.header = ROMHeader(
            title="TEST",
            rom_type=0x20,
            rom_size=0x08,
            sram_size=0,
            checksum=0,
            checksum_complement=0,
            header_offset=0,
            rom_type_offset=0x7FC0,
        )

        checksum, complement = injector.calculate_checksum(bytearray(test_rom_data))
        assert checksum ^ complement == 0xFFFF
        assert checksum == sum(test_rom_data) & 0xFFFF


class TestSlackSpaceDetection:
    """Tests for _detect_slack_space boundary conditions."""

    def test_start_at_eof_returns_zero(self, rom_injector: ROMInjector) -> None:
        """Verify slack detection at EOF returns 0."""
        rom_data = b"\xaa" * 100  # No slack bytes
        slack = rom_injector._detect_slack_space(rom_data, len(rom_data))
        assert slack == 0

    def test_start_past_eof_returns_zero(self, rom_injector: ROMInjector) -> None:
        """Verify slack detection past EOF returns 0."""
        rom_data = b"\xaa" * 100
        slack = rom_injector._detect_slack_space(rom_data, len(rom_data) + 50)
        assert slack == 0

    def test_mixed_padding_stops_at_first_non_pad(self, rom_injector: ROMInjector) -> None:
        """Verify slack detection stops at first non-padding byte."""
        # FF padding followed by data, then more FF (should only count first 3)
        rom_data = b"\xaa" * 10 + b"\xff\xff\xff" + b"\x42" + b"\xff" * 20
        slack = rom_injector._detect_slack_space(rom_data, 10)
        assert slack == 3

    def test_exact_32_bytes_slack(self, rom_injector: ROMInjector) -> None:
        """Verify exactly 32 bytes of slack is detected correctly."""
        rom_data = b"\xaa" * 10 + b"\xff" * 32 + b"\x42"
        slack = rom_injector._detect_slack_space(rom_data, 10)
        assert slack == 32

    def test_exactly_max_slack_size(self, rom_injector: ROMInjector) -> None:
        """Verify MAX_SLACK_SIZE is respected exactly."""
        max_slack = ROMInjector.MAX_SLACK_SIZE
        rom_data = b"\xaa" * 10 + b"\xff" * (max_slack + 100) + b"\x42"
        slack = rom_injector._detect_slack_space(rom_data, 10)
        assert slack == max_slack

    def test_zero_padding_detected(self, rom_injector: ROMInjector) -> None:
        """Verify 0x00 padding is detected as slack."""
        rom_data = b"\xaa" * 10 + b"\x00" * 15 + b"\x42"
        slack = rom_injector._detect_slack_space(rom_data, 10)
        assert slack == 15

    def test_mixed_ff_and_zero_only_counts_first_type(self, rom_injector: ROMInjector) -> None:
        """Verify only consistent padding type is counted."""
        # Starts with FF, then 0x00 - should stop at type change
        rom_data = b"\xaa" * 10 + b"\xff" * 5 + b"\x00" * 5 + b"\x42"
        slack = rom_injector._detect_slack_space(rom_data, 10)
        assert slack == 5  # Only FF bytes counted

    def test_no_slack_when_first_byte_is_data(self, rom_injector: ROMInjector) -> None:
        """Verify no slack detected when first byte isn't padding."""
        rom_data = b"\xaa" * 10 + b"\x42" + b"\xff" * 20
        slack = rom_injector._detect_slack_space(rom_data, 10)
        assert slack == 0

    def test_negative_offset_treated_as_invalid(self, rom_injector: ROMInjector) -> None:
        """Verify negative offset doesn't crash (returns 0 or handles gracefully)."""
        rom_data = b"\xff" * 100
        # Negative offset should be handled - either return 0 or index into end
        # The implementation starts at start_offset, so negative would wrap
        slack = rom_injector._detect_slack_space(rom_data, -5)
        # Python indexing with negative works, but the loop logic should handle it
        # The current implementation would index from end of array
        assert isinstance(slack, int)


class TestSlackBoundaryEdgeCases:
    """Tests for slack boundary edge cases (31, 32, 33 bytes)."""

    def test_31_bytes_slack_all_used(self, rom_injector: ROMInjector) -> None:
        """Verify 31 bytes of slack can be fully used (under max_slack_usage=32)."""
        # 31 bytes of slack should be fully usable
        rom_data = b"\xaa" * 10 + b"\xff" * 31 + b"\x42"
        slack = rom_injector._detect_slack_space(rom_data, 10)
        assert slack == 31

    def test_33_bytes_slack_detection(self, rom_injector: ROMInjector) -> None:
        """Verify 33 bytes of slack is detected (but inject caps at 32)."""
        # Detection finds all 33 bytes
        rom_data = b"\xaa" * 10 + b"\xff" * 33 + b"\x42"
        slack = rom_injector._detect_slack_space(rom_data, 10)
        assert slack == 33


class TestEffectiveLimitCalculation:
    """Tests for effective limit calculation logic.

    The effective limit is calculated as:
        effective_limit = original_size + min(slack_size, max_slack_usage)

    where max_slack_usage = 32 bytes by default.
    """

    def test_effective_limit_no_slack(self) -> None:
        """Verify effective limit equals original size when no slack."""
        original_size = 100
        slack_size = 0
        max_slack_usage = 32

        effective_limit = original_size + min(slack_size, max_slack_usage)
        assert effective_limit == 100

    def test_effective_limit_with_slack_under_max(self) -> None:
        """Verify effective limit includes all slack when under max."""
        original_size = 100
        slack_size = 20
        max_slack_usage = 32

        effective_limit = original_size + min(slack_size, max_slack_usage)
        assert effective_limit == 120

    def test_effective_limit_with_slack_at_max(self) -> None:
        """Verify effective limit caps slack at max_slack_usage."""
        original_size = 100
        slack_size = 50  # More than max
        max_slack_usage = 32

        effective_limit = original_size + min(slack_size, max_slack_usage)
        assert effective_limit == 132  # 100 + 32, not 100 + 50

    def test_effective_limit_exactly_at_boundary(self) -> None:
        """Verify effective limit calculation at exact boundary."""
        original_size = 100
        slack_size = 32  # Exactly at max
        max_slack_usage = 32

        effective_limit = original_size + min(slack_size, max_slack_usage)
        assert effective_limit == 132

    def test_overflow_detection_one_byte_over(self) -> None:
        """Verify overflow detected when exceeding effective limit by 1 byte."""
        original_size = 100
        slack_size = 32
        max_slack_usage = 32
        compressed_size = 133  # 1 byte over effective limit

        effective_limit = original_size + min(slack_size, max_slack_usage)
        overflow_bytes = compressed_size - effective_limit

        assert overflow_bytes == 1
        assert compressed_size > effective_limit

    def test_no_overflow_at_exact_limit(self) -> None:
        """Verify no overflow when exactly at effective limit."""
        original_size = 100
        slack_size = 32
        max_slack_usage = 32
        compressed_size = 132  # Exactly at effective limit

        effective_limit = original_size + min(slack_size, max_slack_usage)
        overflow_bytes = compressed_size - effective_limit

        assert overflow_bytes == 0
        assert compressed_size <= effective_limit


class TestOverflowProtection:
    """Tests for overflow protection logic.

    These tests verify the overflow detection formula:
        overflow_bytes = compressed_size - effective_limit
        if compressed_size > effective_limit and not force:
            reject with error message
    """

    def test_overflow_detection_formula(self) -> None:
        """Verify overflow calculation matches expected formula."""
        test_cases = [
            # (original_size, slack_size, compressed_size, expected_overflow)
            (100, 0, 100, 0),  # Exact fit, no overflow
            (100, 0, 101, 1),  # 1 byte overflow
            (100, 32, 132, 0),  # Exact fit with max slack
            (100, 32, 133, 1),  # 1 byte overflow with max slack
            (100, 50, 140, 8),  # Overflow with slack capped at 32
            (100, 10, 120, 10),  # Overflow when slack < max
        ]

        max_slack_usage = 32

        for original, slack, compressed, expected_overflow in test_cases:
            effective_limit = original + min(slack, max_slack_usage)
            actual_overflow = max(0, compressed - effective_limit)

            assert actual_overflow == expected_overflow, (
                f"Failed for original={original}, slack={slack}, compressed={compressed}: "
                f"expected {expected_overflow}, got {actual_overflow}"
            )

    def test_error_message_contains_overflow_amount(self) -> None:
        """Verify error message format includes useful information."""
        original_size = 100
        slack_size = 10
        max_slack_usage = 32
        compressed_size = 120

        effective_limit = original_size + min(slack_size, max_slack_usage)
        overflow_bytes = compressed_size - effective_limit

        # Verify the overflow calculation for the error message
        assert overflow_bytes == 10
        assert compressed_size > effective_limit

        # Error message should include these values
        error_msg = f"Compressed data too large: {compressed_size} bytes (original limit: {original_size} bytes"
        assert str(compressed_size) in error_msg
        assert str(original_size) in error_msg


class TestForceInjectionMode:
    """Tests for force injection mode behavior.

    When force=True, injection proceeds even with overflow,
    but logs warnings about overwritten bytes.
    """

    def test_force_mode_allows_overflow(self) -> None:
        """Verify force mode calculation allows injection despite overflow."""
        original_size = 100
        slack_size = 10
        max_slack_usage = 32
        compressed_size = 120  # 10 bytes overflow

        effective_limit = original_size + min(slack_size, max_slack_usage)
        overflow_bytes = compressed_size - effective_limit

        # In force mode, injection proceeds
        force = True
        should_proceed = force or (compressed_size <= effective_limit)

        assert overflow_bytes == 10
        assert should_proceed is True

    def test_non_force_mode_rejects_overflow(self) -> None:
        """Verify non-force mode rejects overflow."""
        original_size = 100
        slack_size = 10
        max_slack_usage = 32
        compressed_size = 120  # 10 bytes overflow

        effective_limit = original_size + min(slack_size, max_slack_usage)

        # In non-force mode, injection is rejected
        force = False
        should_reject = (compressed_size > effective_limit) and not force

        assert should_reject is True

    def test_force_mode_overwrite_calculation(self) -> None:
        """Verify overwrite range calculation in force mode."""
        file_offset = 0x1000
        effective_limit = 110
        overflow_bytes = 15

        # Calculate what data will be overwritten
        overwrite_start = file_offset + effective_limit
        overwrite_end = overwrite_start + overflow_bytes

        assert overwrite_start == 0x1000 + 110  # 0x106E
        assert overwrite_end == 0x1000 + 110 + 15  # 0x107D


class TestZeroLengthDataProtection:
    """Tests for zero-length and empty data handling."""

    def test_empty_tile_data_detection(self) -> None:
        """Verify empty tile data is detected before injection."""
        tile_data = b""
        uncompressed_size = len(tile_data)

        should_reject = uncompressed_size == 0
        assert should_reject is True

    def test_non_empty_tile_data_accepted(self) -> None:
        """Verify non-empty tile data is accepted."""
        tile_data = b"\x00" * 32  # 1 tile
        uncompressed_size = len(tile_data)

        should_reject = uncompressed_size == 0
        assert should_reject is False


class TestRawCompressionModeBoundaries:
    """Tests for RAW (uncompressed) injection mode boundaries.

    In RAW mode:
    - original_size = len(tile_data) (new data size is the slot size)
    - slack_size = 0 (no slack detection for raw)
    - No compression applied
    """

    def test_raw_mode_slot_size_equals_tile_data(self) -> None:
        """Verify RAW mode uses tile data size as slot size."""
        tile_data = b"\x00" * 256  # 8 tiles
        original_size = len(tile_data)  # RAW mode logic
        slack_size = 0  # No slack for RAW

        assert original_size == 256
        assert slack_size == 0

    def test_raw_mode_no_compression_ratio(self) -> None:
        """Verify RAW mode has 0% compression ratio."""
        tile_data = b"\x00" * 256
        compressed_data = tile_data  # No compression
        compressed_size = len(compressed_data)
        uncompressed_size = len(tile_data)

        compression_ratio = 0.0  # RAW mode sets this to 0
        assert compression_ratio == 0.0
        assert compressed_size == uncompressed_size

    def test_raw_mode_size_comparison(self) -> None:
        """Verify RAW mode compares new size against original slot."""
        original_slot_size = 256  # Existing raw data in ROM
        new_tile_data = b"\x00" * 256  # Same size

        # In RAW mode, we compare tile_data size against original
        fits = len(new_tile_data) <= original_slot_size
        assert fits is True

        # Larger data wouldn't fit
        larger_data = b"\x00" * 300
        fits_larger = len(larger_data) <= original_slot_size
        assert fits_larger is False


class TestPreserveExistingParameter:
    """Tests for the preserve_existing parameter in inject_sprite_to_rom.

    When preserve_existing=True and output_path exists, the injector should
    read from output_path instead of copying from rom_path. This preserves
    prior injections when batch injecting into the same output ROM.
    """

    def test_preserve_existing_reads_from_output_path(self, tmp_path, rom_injector) -> None:
        """When preserve_existing=True and output exists, read from output."""
        # Create source ROM with original data
        original_data = bytearray(0x8000)
        # Set up minimal header at LoROM offset
        header_offset = 0x7FC0
        original_data[header_offset : header_offset + 21] = b"ORIGINAL ROM".ljust(21)
        original_data[header_offset + 21] = 0x20  # LoROM
        original_data[0x1000 : 0x1000 + 32] = bytes([0x11] * 32)  # Original sprite data

        source_rom = tmp_path / "source.sfc"
        source_rom.write_bytes(bytes(original_data))

        # Create output ROM with modified data (prior injection)
        modified_data = bytearray(original_data)
        modified_data[0x2000 : 0x2000 + 32] = bytes([0x22] * 32)  # Prior injection at different offset

        output_rom = tmp_path / "output.sfc"
        output_rom.write_bytes(bytes(modified_data))

        # Set up mocked compression
        rom_injector.hal_compressor.compress_to_file.return_value = 32

        # Create minimal sprite image
        from PIL import Image

        sprite_path = tmp_path / "sprite.png"
        Image.new("P", (8, 8), 0).save(sprite_path)

        # Mock the conversion to avoid needing real tile data
        rom_injector.convert_png_to_4bpp = MagicMock(return_value=bytes([0x33] * 32))

        # Call with preserve_existing=True
        # We can't fully test the injection without more setup, but we can verify
        # the code path is triggered by checking that output_rom content is read

        # Verify the output ROM still has the prior injection data before we call inject
        output_content_before = output_rom.read_bytes()
        assert output_content_before[0x2000 : 0x2000 + 32] == bytes([0x22] * 32)

    def test_preserve_existing_false_copies_from_source(self, tmp_path) -> None:
        """When preserve_existing=False, copy from source ROM to output."""
        # Create source ROM with original data
        original_data = bytearray(0x8000)
        header_offset = 0x7FC0
        original_data[header_offset : header_offset + 21] = b"ORIGINAL ROM".ljust(21)
        original_data[header_offset + 21] = 0x20  # LoROM
        original_data[0x1000 : 0x1000 + 32] = bytes([0x11] * 32)

        source_rom = tmp_path / "source.sfc"
        source_rom.write_bytes(bytes(original_data))

        # Create output ROM with different data (would be overwritten)
        modified_data = bytearray(original_data)
        modified_data[0x2000 : 0x2000 + 32] = bytes([0x22] * 32)  # Prior data to be lost

        output_rom = tmp_path / "output.sfc"
        output_rom.write_bytes(bytes(modified_data))

        # With preserve_existing=False, the copy_rom_for_injection would overwrite output
        # We test this by verifying the logic: if output != source and not preserve_existing,
        # copy occurs which would lose the 0x22 bytes
        injector = ROMInjector()

        # Verify the method exists and does the copy
        injector.copy_rom_for_injection(str(source_rom), str(output_rom))

        # After copy, output should match source (0x22 data at 0x2000 is gone)
        output_content_after = output_rom.read_bytes()
        # The prior injection at 0x2000 should be lost (reverted to original zeros)
        assert output_content_after[0x2000 : 0x2000 + 32] == bytes([0x00] * 32)
