"""Tests for Mesen capture offset synchronization across UI components.

When the preview worker discovers that a sprite is at an adjusted offset
(e.g., 0x293AEB -> 0x293AEF), both the Asset Browser AND the ROM Extraction
panel's Mesen captures list should update to show the corrected offset.
"""

from datetime import UTC, datetime

import pytest


class TestRecentCapturesWidgetOffsetUpdate:
    """Tests for RecentCapturesWidget.update_capture_offset method."""

    def test_update_capture_offset_updates_display_text(self, qtbot):
        """
        Bug: ROM Extraction panel shows offset 0x293AEB while Asset Browser
        shows 0x293AEF for the same Mesen capture.

        Scenario: User clicks on Mesen capture at 0x293AEB.
        Preview worker discovers sprite is actually at 0x293AEF (+4 bytes).
        Asset Browser updates to show 0x293AEF.
        ROM Extraction panel's capture list should ALSO update to 0x293AEF.

        Expected:
        - RecentCapturesWidget has update_capture_offset(old, new) method
        - Display text updates from "0x293AEB ..." to "0x293AEF ..."
        - Internal data also updates
        """
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        # Add a capture at the original offset
        original_offset = 0x293AEB
        new_offset = 0x293AEF
        capture = CapturedOffset(
            offset=original_offset,
            frame=1938,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x293AEB",
        )
        widget.add_capture(capture)

        # Verify initial state
        assert widget.get_capture_count() == 1
        assert widget.has_capture(original_offset)

        # Get the list item and verify display text contains original offset
        list_widget = widget._list_widget
        item = list_widget.item(0)
        assert item is not None
        original_text = item.text()
        # Use case-insensitive comparison for hex string
        assert f"{original_offset:06X}" in original_text.upper(), (
            f"Expected original offset in display text, got: {original_text}"
        )

        # This method should exist and update the offset
        assert hasattr(widget, "update_capture_offset"), "RecentCapturesWidget must have update_capture_offset method"

        # Update the offset
        success = widget.update_capture_offset(original_offset, new_offset)
        assert success, "update_capture_offset should return True when offset found"

        # Verify display text updated
        updated_text = item.text()
        # Use case-insensitive comparison for hex string
        assert f"{new_offset:06X}" in updated_text.upper(), f"Expected new offset in display text, got: {updated_text}"

        # Verify has_capture reflects new offset
        assert widget.has_capture(new_offset), "has_capture should find new offset"
        assert not widget.has_capture(original_offset), "has_capture should NOT find old offset after update"

    def test_update_capture_offset_preserves_other_info(self, qtbot):
        """Verify that offset update preserves timestamp and frame info."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        original_offset = 0x100000
        new_offset = 0x100004
        frame = 500
        capture = CapturedOffset(
            offset=original_offset,
            frame=frame,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x100000",
        )
        widget.add_capture(capture)

        list_widget = widget._list_widget
        item = list_widget.item(0)

        widget.update_capture_offset(original_offset, new_offset)

        updated_text = item.text()
        # Frame number should be preserved
        assert f"f{frame}" in updated_text.lower() or f"({frame})" in updated_text, (
            f"Frame number should be preserved in: {updated_text}"
        )

    def test_update_capture_offset_returns_false_when_not_found(self, qtbot):
        """Verify update_capture_offset returns False when offset not found."""
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        success = widget.update_capture_offset(0x999999, 0x999998)
        assert not success, "Should return False when offset not found"


class TestMesenCapturesSectionOffsetUpdate:
    """Tests for MesenCapturesSection.update_capture_offset wrapper method."""

    def test_mesen_captures_section_has_update_method(self, qtbot):
        """Verify MesenCapturesSection exposes update_capture_offset."""
        from ui.rom_extraction.widgets.mesen_captures_section import MesenCapturesSection

        widget = MesenCapturesSection()
        qtbot.addWidget(widget)

        assert hasattr(widget, "update_capture_offset"), "MesenCapturesSection must expose update_capture_offset method"
        assert callable(widget.update_capture_offset)

    def test_mesen_captures_section_delegates_to_widget(self, qtbot):
        """Verify MesenCapturesSection delegates update to RecentCapturesWidget."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.rom_extraction.widgets.mesen_captures_section import MesenCapturesSection

        widget = MesenCapturesSection()
        qtbot.addWidget(widget)

        original_offset = 0x200000
        new_offset = 0x200004
        capture = CapturedOffset(
            offset=original_offset,
            frame=1000,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x200000",
        )
        widget.add_capture(capture)

        # Update via section wrapper
        success = widget.update_capture_offset(original_offset, new_offset)
        assert success

        # Verify internal widget was updated
        assert widget.has_capture(new_offset)
        assert not widget.has_capture(original_offset)
