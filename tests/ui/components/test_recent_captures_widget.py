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
