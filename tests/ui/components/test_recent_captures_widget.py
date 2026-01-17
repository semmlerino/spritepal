"""Tests for RecentCapturesWidget."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from core.mesen_integration.log_watcher import CapturedOffset
from ui.components.panels.recent_captures_widget import RecentCapturesWidget

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


pytestmark = pytest.mark.gui


@pytest.fixture
def widget(qtbot: QtBot) -> RecentCapturesWidget:
    """Create RecentCapturesWidget for testing."""
    w = RecentCapturesWidget()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def sample_capture() -> CapturedOffset:
    """Create a sample CapturedOffset with known FILE offset."""
    return CapturedOffset(
        offset=0x3C7001,  # FILE offset (original Mesen capture point)
        frame=100,
        timestamp=datetime.now(),
        raw_line="FILE: 0x3C7001 Frame: 100",
        rom_checksum=0xA1B2,
    )


class TestFileOffsetImmutability:
    """Test that FILE offset is preserved when ROM offset is updated."""

    def test_update_capture_offset_preserves_file_offset(
        self, widget: RecentCapturesWidget, sample_capture: CapturedOffset
    ) -> None:
        """FILE offset should remain unchanged after ROM offset alignment adjustment.

        Bug: update_capture_offset() was overwriting CapturedOffset.offset with
        the new ROM offset, destroying the original FILE offset identity.
        """
        # Arrange: Add capture with FILE offset 0x3C7001
        original_file_offset = sample_capture.offset
        widget.add_capture(sample_capture)

        # SMC header offset for ROM conversion
        smc_offset = 0x200
        widget.set_smc_offset(smc_offset)

        # Original ROM offset = FILE - SMC = 0x3C7001 - 0x200 = 0x3C6E01
        old_rom_offset = original_file_offset - smc_offset
        # After HAL alignment, ROM offset changes (e.g., to aligned boundary)
        new_rom_offset = 0x3C6EF0  # Adjusted ROM offset

        # Act: Update the ROM offset (simulates HAL alignment discovery)
        result = widget.update_capture_offset(old_rom_offset, new_rom_offset)

        # Assert: Update should succeed
        assert result is True, "update_capture_offset should return True when item found"

        # Assert: The underlying CapturedOffset.offset (FILE offset) should be UNCHANGED
        # This is the critical assertion - FILE offset is the original capture identity
        assert len(widget._captures) == 1
        updated_capture = widget._captures[0]
        assert updated_capture.offset == original_file_offset, (
            f"FILE offset should be preserved as {original_file_offset:#x}, "
            f"but was changed to {updated_capture.offset:#x}"
        )

        # Assert: Frame and other metadata should also be preserved
        assert updated_capture.frame == sample_capture.frame
        assert updated_capture.rom_checksum == sample_capture.rom_checksum

    def test_update_capture_offset_updates_item_data_rom_offset(
        self, widget: RecentCapturesWidget, sample_capture: CapturedOffset
    ) -> None:
        """Item data should store the updated ROM offset separately from FILE offset.

        The widget item data should have both:
        - rom_offset: The adjusted ROM offset (for display/sprite loading)
        - file_offset: The original FILE offset (preserved for identity)
        """
        # Arrange
        widget.add_capture(sample_capture)
        smc_offset = 0x200
        widget.set_smc_offset(smc_offset)

        old_rom_offset = sample_capture.offset - smc_offset
        new_rom_offset = 0x3C6EF0

        # Act
        widget.update_capture_offset(old_rom_offset, new_rom_offset)

        # Assert: Item data should have the new ROM offset
        item = widget._list_widget.item(0)
        item_data = item.data(0x0100)  # Qt.ItemDataRole.UserRole
        assert item_data["rom_offset"] == new_rom_offset

        # Assert: FILE offset should also be stored/preserved in item data
        assert item_data.get("file_offset") == sample_capture.offset


class TestUpdateOrAddCapture:
    """Tests for update_or_add_capture method (handles re-clicking same sprite)."""

    def test_update_or_add_capture_adds_new_capture(
        self, widget: RecentCapturesWidget, sample_capture: CapturedOffset
    ) -> None:
        """New capture should be added when no existing capture with same offset."""
        assert widget.get_capture_count() == 0

        widget.update_or_add_capture(sample_capture, request_thumbnail=False)

        assert widget.get_capture_count() == 1
        assert widget.has_capture_by_file_offset(sample_capture.offset)

    def test_update_or_add_capture_updates_existing(
        self, widget: RecentCapturesWidget, sample_capture: CapturedOffset
    ) -> None:
        """Existing capture should be updated (removed and re-added at top)."""
        # Add initial capture
        widget.add_capture(sample_capture, request_thumbnail=False)
        assert widget.get_capture_count() == 1

        # Create updated capture with same offset but different frame
        updated_capture = CapturedOffset(
            offset=sample_capture.offset,  # Same FILE offset
            frame=200,  # Different frame
            timestamp=datetime.now(),
            raw_line=f"FILE: {sample_capture.offset:#x} Frame: 200",
            rom_checksum=sample_capture.rom_checksum,
        )

        widget.update_or_add_capture(updated_capture, request_thumbnail=False)

        # Should still have only 1 capture (not duplicated)
        assert widget.get_capture_count() == 1
        # The capture at top should have the new frame
        assert widget._captures[0].frame == 200

    def test_update_or_add_capture_moves_to_top(self, widget: RecentCapturesWidget) -> None:
        """Updated capture should be moved to top of list."""
        # Add two captures
        capture1 = CapturedOffset(
            offset=0x3C7001,
            frame=100,
            timestamp=datetime.now(),
            raw_line="FILE: 0x3C7001 Frame: 100",
            rom_checksum=0xA1B2,
        )
        capture2 = CapturedOffset(
            offset=0x3C8000,
            frame=150,
            timestamp=datetime.now(),
            raw_line="FILE: 0x3C8000 Frame: 150",
            rom_checksum=0xA1B2,
        )
        widget.add_capture(capture1, request_thumbnail=False)  # At top
        widget.add_capture(capture2, request_thumbnail=False)  # New top

        # capture2 is at index 0, capture1 is at index 1
        assert widget._captures[0].offset == 0x3C8000
        assert widget._captures[1].offset == 0x3C7001

        # Update capture1 (re-click)
        updated_capture1 = CapturedOffset(
            offset=0x3C7001,  # Same as capture1
            frame=999,  # Different frame
            timestamp=datetime.now(),
            raw_line="FILE: 0x3C7001 Frame: 999",
            rom_checksum=0xA1B2,
        )
        widget.update_or_add_capture(updated_capture1, request_thumbnail=False)

        # Now updated_capture1 should be at top
        assert widget.get_capture_count() == 2
        assert widget._captures[0].offset == 0x3C7001
        assert widget._captures[0].frame == 999  # New frame
        assert widget._captures[1].offset == 0x3C8000

    def test_update_or_add_capture_emits_thumbnail_request(
        self, widget: RecentCapturesWidget, sample_capture: CapturedOffset, qtbot
    ) -> None:
        """Thumbnail should be requested when request_thumbnail=True."""
        with qtbot.waitSignal(widget.thumbnail_requested, timeout=1000) as blocker:
            widget.update_or_add_capture(sample_capture, request_thumbnail=True)

        # Signal should have been emitted with ROM offset (normalized)
        rom_offset = widget._normalize_offset(sample_capture.offset)
        assert blocker.args == [rom_offset]


class TestRefreshButton:
    """Tests for refresh button functionality."""

    def test_refresh_button_exists(self, widget: RecentCapturesWidget) -> None:
        """Widget should have a refresh button."""
        assert hasattr(widget, "_refresh_btn")
        assert widget._refresh_btn is not None

    def test_refresh_button_emits_signal(
        self, widget: RecentCapturesWidget, sample_capture: CapturedOffset, qtbot
    ) -> None:
        """Clicking refresh should emit refresh_requested signal."""
        # Add a capture first
        widget.add_capture(sample_capture, request_thumbnail=False)

        with qtbot.waitSignal(widget.refresh_requested, timeout=1000):
            widget._refresh_btn.click()

    def test_refresh_clears_thumbnails(
        self, widget: RecentCapturesWidget, sample_capture: CapturedOffset, qtbot
    ) -> None:
        """Refresh should clear thumbnails from items."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap

        # Add capture with a thumbnail
        widget.add_capture(sample_capture, request_thumbnail=False)
        item = widget._list_widget.item(0)
        data = item.data(Qt.ItemDataRole.UserRole)
        # Set a mock thumbnail
        data["thumbnail"] = QPixmap(32, 32)
        item.setData(Qt.ItemDataRole.UserRole, data)

        # Verify thumbnail is set
        data_before = widget._list_widget.item(0).data(Qt.ItemDataRole.UserRole)
        assert data_before["thumbnail"] is not None

        # Click refresh (use internal method to avoid signal timing)
        widget._clear_all_thumbnails()

        # Verify thumbnail is cleared
        data_after = widget._list_widget.item(0).data(Qt.ItemDataRole.UserRole)
        assert data_after["thumbnail"] is None

    def test_refresh_re_requests_thumbnails(
        self, widget: RecentCapturesWidget, sample_capture: CapturedOffset, qtbot
    ) -> None:
        """Refresh should re-request thumbnails for all captures."""
        # Add capture
        widget.add_capture(sample_capture, request_thumbnail=False)

        # Track thumbnail requests
        requests: list[int] = []
        widget.thumbnail_requested.connect(lambda offset: requests.append(offset))

        # Trigger refresh click
        widget._on_refresh_clicked()

        # Should have requested thumbnail for the capture
        assert len(requests) == 1
        rom_offset = widget._normalize_offset(sample_capture.offset)
        assert requests[0] == rom_offset
