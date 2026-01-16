"""Tests for LogWatcher offset lookup methods.

Verifies that the LogWatcher correctly looks up captures by:
- FILE offset (raw Mesen output)
- ROM offset (with SMC header conversion)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.mesen_integration.log_watcher import CapturedOffset, LogWatcher


@pytest.fixture
def log_watcher() -> LogWatcher:
    """Create a LogWatcher instance for testing."""
    return LogWatcher()


@pytest.fixture
def sample_captures() -> list[CapturedOffset]:
    """Create sample captures with different FILE offsets."""
    return [
        CapturedOffset(
            offset=0x3C7001,  # FILE offset (with SMC header)
            frame=100,
            timestamp=datetime.now(tz=UTC),
            raw_line="FILE: 0x3C7001 Frame: 100",
            rom_checksum=0xA1B2,
        ),
        CapturedOffset(
            offset=0x3C6EF1,  # FILE offset (without SMC header)
            frame=200,
            timestamp=datetime.now(tz=UTC),
            raw_line="FILE: 0x3C6EF1 Frame: 200",
            rom_checksum=0xA1B2,
        ),
    ]


class TestFileOffsetLookup:
    """Test looking up captures by FILE offset."""

    def test_get_capture_by_file_offset_exact_match(
        self, log_watcher: LogWatcher, sample_captures: list[CapturedOffset]
    ) -> None:
        """get_capture_by_file_offset should find capture by exact FILE offset."""
        # Arrange: Add captures to the watcher
        log_watcher._recent_captures = list(sample_captures)

        # Act: Look up by FILE offset
        result = log_watcher.get_capture_by_file_offset(0x3C7001)

        # Assert
        assert result is not None
        assert result.offset == 0x3C7001
        assert result.frame == 100

    def test_get_capture_by_file_offset_not_found(
        self, log_watcher: LogWatcher, sample_captures: list[CapturedOffset]
    ) -> None:
        """get_capture_by_file_offset should return None for non-existent offset."""
        log_watcher._recent_captures = list(sample_captures)

        result = log_watcher.get_capture_by_file_offset(0x999999)

        assert result is None

    def test_get_capture_by_file_offset_empty_captures(self, log_watcher: LogWatcher) -> None:
        """get_capture_by_file_offset should return None when no captures."""
        result = log_watcher.get_capture_by_file_offset(0x3C7001)

        assert result is None


class TestRomOffsetLookup:
    """Test looking up captures by ROM offset (with header conversion)."""

    def test_get_capture_by_rom_offset_with_smc_header(
        self, log_watcher: LogWatcher, sample_captures: list[CapturedOffset]
    ) -> None:
        """get_capture_by_rom_offset should find capture by ROM offset when SMC header present.

        Bug: Callers pass ROM offset (FILE - SMC_OFFSET) but existing method
        searches by FILE offset, causing lookup failures.
        """
        # Arrange: Add capture with FILE offset 0x3C7001
        log_watcher._recent_captures = list(sample_captures)
        smc_header_offset = 0x200

        # ROM offset = FILE offset - SMC header = 0x3C7001 - 0x200 = 0x3C6E01
        rom_offset = 0x3C7001 - smc_header_offset

        # Act: Look up by ROM offset (should convert internally)
        result = log_watcher.get_capture_by_rom_offset(rom_offset, smc_header_offset)

        # Assert: Should find the capture with FILE offset 0x3C7001
        assert result is not None, (
            f"Should find capture by ROM offset 0x{rom_offset:06X} "
            f"(FILE offset 0x{0x3C7001:06X} with SMC header 0x{smc_header_offset:X})"
        )
        assert result.offset == 0x3C7001
        assert result.frame == 100

    def test_get_capture_by_rom_offset_without_header(
        self, log_watcher: LogWatcher, sample_captures: list[CapturedOffset]
    ) -> None:
        """get_capture_by_rom_offset should work with zero header offset."""
        log_watcher._recent_captures = list(sample_captures)

        # When no SMC header, ROM offset == FILE offset
        result = log_watcher.get_capture_by_rom_offset(0x3C6EF1, smc_header_offset=0)

        assert result is not None
        assert result.offset == 0x3C6EF1
        assert result.frame == 200

    def test_get_capture_by_rom_offset_not_found(
        self, log_watcher: LogWatcher, sample_captures: list[CapturedOffset]
    ) -> None:
        """get_capture_by_rom_offset should return None for non-existent offset."""
        log_watcher._recent_captures = list(sample_captures)

        result = log_watcher.get_capture_by_rom_offset(0x999999, smc_header_offset=0x200)

        assert result is None


class TestBackwardCompatibility:
    """Test that existing get_capture_by_offset still works."""

    def test_get_capture_by_offset_is_file_offset_lookup(
        self, log_watcher: LogWatcher, sample_captures: list[CapturedOffset]
    ) -> None:
        """Existing get_capture_by_offset should match get_capture_by_file_offset behavior.

        This ensures backward compatibility - existing callers should continue
        to work after the refactoring.
        """
        log_watcher._recent_captures = list(sample_captures)

        # Both methods should return the same result
        file_result = log_watcher.get_capture_by_file_offset(0x3C7001)
        compat_result = log_watcher.get_capture_by_offset(0x3C7001)

        assert file_result == compat_result
        assert file_result is not None
        assert file_result.offset == 0x3C7001
