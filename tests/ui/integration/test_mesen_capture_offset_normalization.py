"""Integration tests for Mesen capture offset normalization bugs.

Tests the complete signal flow from capture discovery through offset normalization
and alignment adjustments across multiple UI components.
"""

from datetime import UTC, datetime

import pytest
from PySide6.QtCore import Qt


class TestBug2CaptureOffsetAdjustment:
    """Bug #2: Capture offset adjustment signal mismatch when HAL alignment corrects offset."""

    def test_alignment_adjustment_updates_capture_list(self, qtbot):
        """Verify that alignment adjustments update the capture list display.

        Scenario:
        1. User clicks on Mesen capture at ROM offset 0x3C7071
        2. Preview worker compresses with HAL, discovers sprite at offset 0x3C7075 (adjusted)
        3. ROMWorkflowController emits capture_offset_adjusted(0x3C7071, 0x3C7075) with ROM offsets
        4. RecentCapturesWidget.update_capture_offset receives adjustment

        Expected:
        - Capture list searches by ROM offset (not FILE)
        - Item is found and updated
        - Display reflects new offset
        """
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        # Set SMC offset to 512 (like KSSU ROM)
        widget.set_smc_offset(512)

        # Add a capture
        file_offset = 0x3C7271
        rom_offset = 0x3C7071  # Normalized (FILE - SMC offset)

        capture = CapturedOffset(
            offset=file_offset,
            frame=None,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture, request_thumbnail=False)

        # Verify capture was added with correct offsets
        assert widget.get_capture_count() == 1
        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("file_offset") == file_offset
        assert item_data.get("rom_offset") == rom_offset

        # Simulate alignment adjustment: ROM offset increases by 4 bytes
        old_rom_offset = rom_offset
        new_rom_offset = rom_offset + 4  # 0x3C7075

        # Call update_capture_offset with ROM offsets (as emitted by controller)
        result = widget.update_capture_offset(old_rom_offset, new_rom_offset)

        # Verify update succeeded
        assert result is True, "update_capture_offset should find and update the capture"

        # Verify item was updated
        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("rom_offset") == new_rom_offset, (
            f"Updated ROM offset is {item_data.get('rom_offset'):06X}, "
            f"expected {new_rom_offset:06X}"
        )

        # FILE offset should remain unchanged
        assert item_data.get("file_offset") == file_offset


class TestBug3SMCOffsetStaleness:
    """Bug #3: Captures added before ROM load don't get re-normalized when SMC offset changes."""

    def test_captures_added_before_rom_load_get_renormalized(self, qtbot):
        """Verify that captures added before ROM load are re-normalized correctly.

        Scenario:
        1. Mesen discovers sprite at FILE offset 0x3C7271 (before ROM loads)
        2. RecentCapturesWidget adds capture with SMC offset 0
        3. Capture stores ROM offset as 0x3C7271 (FILE - 0 = FILE)
        4. User loads KSSU ROM, set_smc_offset(512) called
        5. Existing captures should be re-normalized

        Expected:
        - Capture ROM offset updates to 0x3C7071 (FILE - 512)
        - Thumbnails re-requested with corrected offset
        """
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        file_offset = 0x3C7271

        # Capture added before ROM load (SMC offset is 0)
        capture = CapturedOffset(
            offset=file_offset,
            frame=None,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture, request_thumbnail=False)

        # Verify initial state (no normalization with SMC offset 0)
        assert widget.get_capture_count() == 1
        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("rom_offset") == file_offset, (
            "With SMC offset 0, ROM offset should equal FILE offset"
        )
        assert item_data.get("file_offset") == file_offset

        # Now load SMC ROM and set SMC offset
        widget.set_smc_offset(512)

        # Verify capture was re-normalized
        expected_rom_offset = file_offset - 512  # 0x3C7071
        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("rom_offset") == expected_rom_offset, (
            f"After set_smc_offset, ROM offset is {item_data.get('rom_offset'):06X}, "
            f"expected {expected_rom_offset:06X}"
        )

        # FILE offset should remain unchanged
        assert item_data.get("file_offset") == file_offset

    def test_multiple_captures_added_before_rom_load(self, qtbot):
        """Verify that multiple captures are all re-normalized when SMC offset changes."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        # Add multiple captures before ROM load
        captures_data = [
            (0x3C7271, "FILE OFFSET: 0x3C7271"),
            (0x3C7300, "FILE OFFSET: 0x3C7300"),
            (0x400000, "FILE OFFSET: 0x400000"),
        ]

        for file_offset, line in captures_data:
            capture = CapturedOffset(
                offset=file_offset,
                frame=None,
                timestamp=datetime.now(UTC),
                raw_line=line,
            )
            widget.add_capture(capture, request_thumbnail=False)

        # Verify all captures added
        assert widget.get_capture_count() == len(captures_data)

        # Set SMC offset
        smc_offset = 512
        widget.set_smc_offset(smc_offset)

        # Verify all captures were re-normalized
        for i, (file_offset, _) in enumerate(captures_data):
            # Items are inserted at position 0, so reverse order
            item = widget._list_widget.item(len(captures_data) - 1 - i)
            item_data = item.data(Qt.ItemDataRole.UserRole)

            expected_rom_offset = file_offset - smc_offset if file_offset >= smc_offset else file_offset
            assert item_data.get("rom_offset") == expected_rom_offset, (
                f"Item {i}: ROM offset is {item_data.get('rom_offset'):06X}, "
                f"expected {expected_rom_offset:06X} (FILE 0x{file_offset:06X} - SMC {smc_offset})"
            )

            assert item_data.get("file_offset") == file_offset, (
                f"Item {i}: FILE offset should be unchanged"
            )


class TestOffsetNormalizationEdgeCases:
    """Edge cases for offset normalization."""

    def test_non_smc_rom_no_normalization(self, qtbot):
        """Verify that non-SMC ROMs don't normalize offsets."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        # SMC offset is 0 (no header)
        widget.set_smc_offset(0)

        file_offset = 0x100000
        capture = CapturedOffset(
            offset=file_offset,
            frame=None,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture, request_thumbnail=False)

        # With SMC offset 0, FILE and ROM offsets should be identical
        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("file_offset") == file_offset
        assert item_data.get("rom_offset") == file_offset

    def test_offset_below_smc_header_not_adjusted(self, qtbot):
        """Verify that offsets below SMC header size are not adjusted."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        widget.set_smc_offset(512)

        # This offset is smaller than SMC header size
        file_offset = 0x100  # Less than 512

        capture = CapturedOffset(
            offset=file_offset,
            frame=None,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture, request_thumbnail=False)

        # Should not be adjusted
        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("rom_offset") == file_offset, (
            "Offset below SMC header should not be adjusted"
        )

    def test_update_capture_offset_returns_false_for_missing_offset(self, qtbot):
        """Verify that update_capture_offset returns False when offset not found."""
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        # Try to update non-existent offset
        result = widget.update_capture_offset(0x123456, 0x123457)

        # Should return False since capture not found
        assert result is False
