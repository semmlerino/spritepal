"""Tests for LogWatcher ROM checksum parsing.

Verifies that the LogWatcher correctly parses ROM checksums from:
- Log lines (FILE OFFSET + ROM_CHECKSUM format)
- Persistent clicks JSON (rom_checksum field)

Also tests backward compatibility with legacy formats without checksums.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from core.mesen_integration.log_watcher import (
    CHECKSUM_PATTERN,
    OFFSET_PATTERN,
    CapturedOffset,
    LogWatcher,
)


class TestCapturedOffsetChecksum:
    """Test CapturedOffset dataclass checksum functionality."""

    def test_checksum_default_none(self) -> None:
        """Verify rom_checksum defaults to None for backward compatibility."""
        capture = CapturedOffset(
            offset=0x3C6EF1,
            frame=1500,
            timestamp=datetime.now(tz=UTC),
            raw_line="FILE OFFSET: 0x3C6EF1",
        )
        assert capture.rom_checksum is None

    def test_checksum_stored_correctly(self) -> None:
        """Verify rom_checksum is stored when provided."""
        capture = CapturedOffset(
            offset=0x3C6EF1,
            frame=1500,
            timestamp=datetime.now(tz=UTC),
            raw_line="FILE OFFSET: 0x3C6EF1",
            rom_checksum=0xA1B2,
        )
        assert capture.rom_checksum == 0xA1B2

    def test_checksum_hex_property_none(self) -> None:
        """Verify checksum_hex returns None when no checksum."""
        capture = CapturedOffset(
            offset=0x3C6EF1,
            frame=1500,
            timestamp=datetime.now(tz=UTC),
            raw_line="FILE OFFSET: 0x3C6EF1",
        )
        assert capture.checksum_hex is None

    def test_checksum_hex_property_formatted(self) -> None:
        """Verify checksum_hex returns formatted hex string."""
        capture = CapturedOffset(
            offset=0x3C6EF1,
            frame=1500,
            timestamp=datetime.now(tz=UTC),
            raw_line="FILE OFFSET: 0x3C6EF1",
            rom_checksum=0x00F1,  # Test leading zeros preserved
        )
        assert capture.checksum_hex == "0x00F1"

    def test_checksum_hex_four_digits(self) -> None:
        """Verify checksum_hex is always 4 hex digits."""
        capture = CapturedOffset(
            offset=0x3C6EF1,
            frame=1500,
            timestamp=datetime.now(tz=UTC),
            raw_line="FILE OFFSET: 0x3C6EF1",
            rom_checksum=0xFFFF,
        )
        assert capture.checksum_hex == "0xFFFF"


class TestChecksumPatternRegex:
    """Test CHECKSUM_PATTERN regex matching."""

    def test_matches_standard_format(self) -> None:
        """Verify pattern matches standard ROM_CHECKSUM format."""
        line = "ROM_CHECKSUM: 0xA1B2"
        match = CHECKSUM_PATTERN.search(line)
        assert match is not None
        assert match.group(1) == "A1B2"

    def test_matches_lowercase_hex(self) -> None:
        """Verify pattern matches lowercase hex."""
        line = "ROM_CHECKSUM: 0xa1b2"
        match = CHECKSUM_PATTERN.search(line)
        assert match is not None
        assert match.group(1) == "a1b2"

    def test_matches_with_surrounding_content(self) -> None:
        """Verify pattern matches when embedded in other content."""
        line = "FILE OFFSET: 0x3C6EF1\nROM_CHECKSUM: 0xDEAD\nframe=1500"
        match = CHECKSUM_PATTERN.search(line)
        assert match is not None
        assert match.group(1) == "DEAD"

    def test_no_match_without_prefix(self) -> None:
        """Verify pattern doesn't match bare hex values."""
        line = "0xA1B2"
        match = CHECKSUM_PATTERN.search(line)
        assert match is None

    def test_no_match_wrong_prefix(self) -> None:
        """Verify pattern doesn't match wrong prefix."""
        line = "CHECKSUM: 0xA1B2"  # Missing ROM_ prefix
        match = CHECKSUM_PATTERN.search(line)
        assert match is None


class TestLogWatcherParseLine:
    """Test LogWatcher._parse_line with checksum."""

    @pytest.fixture
    def log_watcher(self, tmp_path: Path) -> LogWatcher:
        """Create LogWatcher instance."""
        watcher = LogWatcher(parent=None)
        watcher._offset_file = tmp_path / "last_offset.txt"
        watcher._clicks_file = tmp_path / "recent_clicks.json"
        return watcher

    def test_parse_line_with_checksum(self, log_watcher: LogWatcher) -> None:
        """Verify parsing extracts ROM checksum when present."""
        line = "FILE OFFSET: 0x3C6EF1\nROM_CHECKSUM: 0xA1B2\nframe=1500"
        result = log_watcher._parse_line(line)
        assert result is not None
        assert result.offset == 0x3C6EF1
        assert result.frame == 1500
        assert result.rom_checksum == 0xA1B2

    def test_parse_line_without_checksum(self, log_watcher: LogWatcher) -> None:
        """Verify parsing works for legacy lines without checksum."""
        line = "FILE OFFSET: 0x3C6EF1\nframe=1500"
        result = log_watcher._parse_line(line)
        assert result is not None
        assert result.offset == 0x3C6EF1
        assert result.frame == 1500
        assert result.rom_checksum is None

    def test_parse_line_checksum_zero(self, log_watcher: LogWatcher) -> None:
        """Verify checksum value 0x0000 is parsed correctly (not as None)."""
        line = "FILE OFFSET: 0x3C6EF1\nROM_CHECKSUM: 0x0000\nframe=1500"
        result = log_watcher._parse_line(line)
        assert result is not None
        assert result.rom_checksum == 0x0000

    def test_parse_line_no_offset_returns_none(self, log_watcher: LogWatcher) -> None:
        """Verify lines without FILE OFFSET return None."""
        line = "ROM_CHECKSUM: 0xA1B2\nframe=1500"
        result = log_watcher._parse_line(line)
        assert result is None


class TestLogWatcherLoadPersistentClicks:
    """Test LogWatcher.load_persistent_clicks with checksum."""

    @pytest.fixture
    def log_watcher(self, tmp_path: Path) -> LogWatcher:
        """Create LogWatcher with temp output directory."""
        watcher = LogWatcher(parent=None)
        watcher._offset_file = tmp_path / "last_offset.txt"
        watcher._clicks_file = tmp_path / "recent_clicks.json"
        return watcher

    def test_load_json_with_checksum(self, log_watcher: LogWatcher, tmp_path: Path) -> None:
        """Verify JSON with rom_checksum field is parsed correctly."""
        clicks_data = [
            {"offset": 0x3C6EF1, "frame": 1500, "timestamp": 1704067200, "rom_checksum": 0xA1B2},
            {"offset": 0x100000, "frame": 2000, "timestamp": 1704067300, "rom_checksum": 0xDEAD},
        ]
        log_watcher._clicks_file.write_text(json.dumps(clicks_data))

        captures = log_watcher.load_persistent_clicks()
        assert len(captures) == 2
        assert captures[0].offset == 0x3C6EF1
        assert captures[0].rom_checksum == 0xA1B2
        assert captures[1].offset == 0x100000
        assert captures[1].rom_checksum == 0xDEAD

    def test_load_json_without_checksum(self, log_watcher: LogWatcher, tmp_path: Path) -> None:
        """Verify legacy JSON without rom_checksum is loaded correctly."""
        clicks_data = [
            {"offset": 0x3C6EF1, "frame": 1500, "timestamp": 1704067200},
            {"offset": 0x100000, "frame": 2000, "timestamp": 1704067300},
        ]
        log_watcher._clicks_file.write_text(json.dumps(clicks_data))

        captures = log_watcher.load_persistent_clicks()
        assert len(captures) == 2
        assert captures[0].offset == 0x3C6EF1
        assert captures[0].rom_checksum is None
        assert captures[1].offset == 0x100000
        assert captures[1].rom_checksum is None

    def test_load_json_mixed_checksum(self, log_watcher: LogWatcher, tmp_path: Path) -> None:
        """Verify JSON with mixed checksum presence is handled."""
        clicks_data = [
            {"offset": 0x3C6EF1, "frame": 1500, "timestamp": 1704067200, "rom_checksum": 0xA1B2},
            {"offset": 0x100000, "frame": 2000, "timestamp": 1704067300},  # No checksum
        ]
        log_watcher._clicks_file.write_text(json.dumps(clicks_data))

        captures = log_watcher.load_persistent_clicks()
        assert len(captures) == 2
        assert captures[0].rom_checksum == 0xA1B2
        assert captures[1].rom_checksum is None

    def test_load_json_checksum_zero(self, log_watcher: LogWatcher, tmp_path: Path) -> None:
        """Verify checksum value 0 is loaded correctly (not as None)."""
        clicks_data = [
            {"offset": 0x3C6EF1, "frame": 1500, "timestamp": 1704067200, "rom_checksum": 0},
        ]
        log_watcher._clicks_file.write_text(json.dumps(clicks_data))

        captures = log_watcher.load_persistent_clicks()
        assert len(captures) == 1
        assert captures[0].rom_checksum == 0
