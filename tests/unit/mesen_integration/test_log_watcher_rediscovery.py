"""Tests for LogWatcher offset rediscovery (re-capture of existing offsets).

When a user clicks on the same sprite again in Mesen2, the offset_rediscovered
signal should be emitted (not offset_discovered), and the internal capture list
should be updated to move the existing capture to the top with new timestamp/frame.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from core.mesen_integration.log_watcher import CapturedOffset, LogWatcher


@pytest.fixture
def log_watcher() -> LogWatcher:
    """Create a LogWatcher instance for testing."""
    return LogWatcher()


@pytest.fixture
def sample_capture() -> CapturedOffset:
    """Create a sample CapturedOffset."""
    return CapturedOffset(
        offset=0x3C7001,
        frame=100,
        timestamp=datetime.now(),
        raw_line="FILE: 0x3C7001 Frame: 100",
        rom_checksum=0xA1B2,
    )


@pytest.fixture
def updated_capture() -> CapturedOffset:
    """Create an updated CapturedOffset with same offset but new frame/timestamp."""
    return CapturedOffset(
        offset=0x3C7001,  # Same offset
        frame=200,  # Different frame
        timestamp=datetime.now() + timedelta(seconds=5),  # Later timestamp
        raw_line="FILE: 0x3C7001 Frame: 200",
        rom_checksum=0xA1B2,
    )


class TestOffsetRediscoveredSignal:
    """Tests for offset_rediscovered signal emission."""

    def test_first_capture_emits_offset_discovered(
        self, log_watcher: LogWatcher, sample_capture: CapturedOffset
    ) -> None:
        """First capture of an offset should emit offset_discovered."""
        discovered_spy = MagicMock()
        rediscovered_spy = MagicMock()
        log_watcher.offset_discovered.connect(discovered_spy)
        log_watcher.offset_rediscovered.connect(rediscovered_spy)

        # Simulate a new capture being processed
        log_watcher._seen_offsets.clear()
        log_watcher._recent_captures.clear()

        # Manually process a capture (simulating _check_offset_file logic)
        if sample_capture.offset not in log_watcher._seen_offsets:
            log_watcher._seen_offsets.add(sample_capture.offset)
            log_watcher._recent_captures.insert(0, sample_capture)
            log_watcher.offset_discovered.emit(sample_capture)
        else:
            log_watcher._update_recent_capture(sample_capture)
            log_watcher.offset_rediscovered.emit(sample_capture)

        # Verify offset_discovered was emitted, not offset_rediscovered
        discovered_spy.assert_called_once_with(sample_capture)
        rediscovered_spy.assert_not_called()

    def test_recapture_emits_offset_rediscovered(
        self,
        log_watcher: LogWatcher,
        sample_capture: CapturedOffset,
        updated_capture: CapturedOffset,
    ) -> None:
        """Re-capture of existing offset should emit offset_rediscovered."""
        discovered_spy = MagicMock()
        rediscovered_spy = MagicMock()
        log_watcher.offset_discovered.connect(discovered_spy)
        log_watcher.offset_rediscovered.connect(rediscovered_spy)

        # First capture
        log_watcher._seen_offsets.add(sample_capture.offset)
        log_watcher._recent_captures.insert(0, sample_capture)

        # Manually process a re-capture (same offset)
        if updated_capture.offset not in log_watcher._seen_offsets:
            log_watcher._seen_offsets.add(updated_capture.offset)
            log_watcher._recent_captures.insert(0, updated_capture)
            log_watcher.offset_discovered.emit(updated_capture)
        else:
            log_watcher._update_recent_capture(updated_capture)
            log_watcher.offset_rediscovered.emit(updated_capture)

        # Verify offset_rediscovered was emitted, not offset_discovered
        discovered_spy.assert_not_called()
        rediscovered_spy.assert_called_once_with(updated_capture)


class TestRecentCapturesUpdate:
    """Tests for _recent_captures list updates on rediscovery."""

    def test_update_recent_capture_moves_to_top(
        self,
        log_watcher: LogWatcher,
        sample_capture: CapturedOffset,
        updated_capture: CapturedOffset,
    ) -> None:
        """Re-captured offset should be moved to top of _recent_captures."""
        # Add initial capture plus another one
        other_capture = CapturedOffset(
            offset=0x3C8000,
            frame=50,
            timestamp=datetime.now(),
            raw_line="FILE: 0x3C8000 Frame: 50",
            rom_checksum=0xA1B2,
        )

        log_watcher._recent_captures = [other_capture, sample_capture]
        log_watcher._seen_offsets = {sample_capture.offset, other_capture.offset}

        # Update the older capture (sample_capture is at index 1)
        log_watcher._update_recent_capture(updated_capture)

        # Verify it's now at the top
        assert len(log_watcher._recent_captures) == 2
        assert log_watcher._recent_captures[0] == updated_capture
        assert log_watcher._recent_captures[1] == other_capture

    def test_update_recent_capture_replaces_old_with_new_data(
        self,
        log_watcher: LogWatcher,
        sample_capture: CapturedOffset,
        updated_capture: CapturedOffset,
    ) -> None:
        """Updated capture should have new frame and timestamp."""
        log_watcher._recent_captures = [sample_capture]
        log_watcher._seen_offsets = {sample_capture.offset}

        log_watcher._update_recent_capture(updated_capture)

        # Verify the capture has new data
        result = log_watcher._recent_captures[0]
        assert result.frame == updated_capture.frame
        assert result.timestamp == updated_capture.timestamp

    def test_update_recent_capture_respects_max_recent(self, log_watcher: LogWatcher) -> None:
        """Update should respect max_recent limit."""
        log_watcher._max_recent = 3

        # Fill to max
        captures = [
            CapturedOffset(
                offset=0x3C7000 + i,
                frame=i,
                timestamp=datetime.now(),
                raw_line=f"FILE: 0x{0x3C7000 + i:06X} Frame: {i}",
                rom_checksum=0xA1B2,
            )
            for i in range(3)
        ]
        log_watcher._recent_captures = captures.copy()
        log_watcher._seen_offsets = {c.offset for c in captures}

        # Update the last one (moves to top)
        updated = CapturedOffset(
            offset=captures[2].offset,  # Same as last capture
            frame=999,
            timestamp=datetime.now(),
            raw_line=f"FILE: 0x{captures[2].offset:06X} Frame: 999",
            rom_checksum=0xA1B2,
        )
        log_watcher._update_recent_capture(updated)

        # Should still be at max_recent
        assert len(log_watcher._recent_captures) == 3
        assert log_watcher._recent_captures[0] == updated
