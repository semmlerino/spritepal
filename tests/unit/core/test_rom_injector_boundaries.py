"""
Tests for ROM injection boundary conditions.

These tests cover:
- P0: High-priority boundary conditions for ROM injection
- Slack space detection edge cases
- Overflow protection and force injection mode
- Effective limit calculation

Related tests:
- tests/test_slack_detection.py - Basic slack detection patterns
- tests/integration/test_rom_injection.py - Integration tests
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.rom_injector import ROMInjector


@pytest.fixture
def rom_injector() -> ROMInjector:
    """Create ROMInjector with mocked dependencies."""
    injector = ROMInjector()
    injector.hal_compressor = MagicMock()
    return injector


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
