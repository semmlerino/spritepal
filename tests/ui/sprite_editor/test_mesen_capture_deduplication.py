"""Tests for Mesen capture deduplication with frame support.

REGRESSION: Captures at the same offset but different frames were being
deduplicated (lost), causing frame collisions.
"""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from core.mesen_integration.log_watcher import CapturedOffset
from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser


class TestCaptureDeduplicationByFrame:
    """Tests for frame-aware capture deduplication."""

    def test_add_mesen_capture_accepts_frame_parameter(self, qtbot) -> None:
        """add_mesen_capture should accept optional frame parameter.

        This is a prerequisite for frame-based deduplication.
        """
        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Should not raise when frame parameter is provided
        browser.add_mesen_capture("Test Sprite", 0x123456, frame=100)

        # Verify frame is stored in item data
        mesen_category = None
        for i in range(browser.tree.topLevelItemCount()):
            item = browser.tree.topLevelItem(i)
            if item.text(0) == "Mesen2 Captures":
                mesen_category = item
                break

        assert mesen_category is not None
        mesen_item = mesen_category.child(0)
        data = mesen_item.data(0, 256)  # Qt.ItemDataRole.UserRole
        assert data.get("frame") == 100

    def test_same_offset_different_frames_not_deduplicated(self, qtbot) -> None:
        """Captures with same offset but different frames should both be added.

        Bug: has_mesen_capture only checked offset, causing frame 100 and frame 200
        at the same offset to collide (second one lost).
        """
        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        offset = 0x3C7001
        frame1 = 100
        frame2 = 200

        # Add first capture
        browser.add_mesen_capture(f"0x{offset:06X} (F{frame1})", offset, frame=frame1)

        # Add second capture at same offset but different frame
        browser.add_mesen_capture(f"0x{offset:06X} (F{frame2})", offset, frame=frame2)

        # Both should exist in the browser
        mesen_category = None
        for i in range(browser.tree.topLevelItemCount()):
            item = browser.tree.topLevelItem(i)
            if item.text(0) == "Mesen2 Captures":
                mesen_category = item
                break

        assert mesen_category is not None
        assert mesen_category.childCount() == 2, (
            f"Expected 2 captures (different frames), but got {mesen_category.childCount()}"
        )

        # Verify both frames are stored correctly
        frames_found = set()
        for i in range(mesen_category.childCount()):
            item = mesen_category.child(i)
            data = item.data(0, 256)
            if data and data.get("frame"):
                frames_found.add(data["frame"])

        assert frames_found == {frame1, frame2}, f"Expected frames {frame1} and {frame2}, found {frames_found}"

    def test_same_offset_same_frame_deduplicated(self, qtbot) -> None:
        """Captures with same offset AND same frame should be deduplicated."""
        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        offset = 0x3C7001
        frame = 100

        # Add first capture
        browser.add_mesen_capture(f"0x{offset:06X} (F{frame})", offset, frame=frame)

        # Add duplicate (same offset and frame)
        browser.add_mesen_capture(f"0x{offset:06X} (F{frame})", offset, frame=frame)

        # Only one should exist
        mesen_category = None
        for i in range(browser.tree.topLevelItemCount()):
            item = browser.tree.topLevelItem(i)
            if item.text(0) == "Mesen2 Captures":
                mesen_category = item
                break

        assert mesen_category is not None
        assert mesen_category.childCount() == 1, "Duplicate capture should have been skipped"

    def test_has_mesen_capture_with_frame_parameter(self, qtbot) -> None:
        """has_mesen_capture should optionally filter by frame."""
        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        offset = 0x3C7001
        frame = 100

        browser.add_mesen_capture("Test", offset, frame=frame)

        # Without frame parameter, should match any frame at this offset
        assert browser.has_mesen_capture(offset) is True

        # With matching frame, should return True
        assert browser.has_mesen_capture(offset, frame=frame) is True

        # With different frame, should return False
        assert browser.has_mesen_capture(offset, frame=200) is False

    def test_offset_only_deduplication_backward_compatible(self, qtbot) -> None:
        """Offset-only deduplication should still work when frame is None.

        Backward compatibility: when no frame is provided, behavior should
        match the original (deduplicate by offset only).
        """
        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        offset = 0x3C7001

        # Add capture without frame
        browser.add_mesen_capture("First", offset)

        # Add another capture without frame (same offset)
        browser.add_mesen_capture("Second", offset)

        # Should be deduplicated (backward compatible behavior)
        mesen_category = None
        for i in range(browser.tree.topLevelItemCount()):
            item = browser.tree.topLevelItem(i)
            if item.text(0) == "Mesen2 Captures":
                mesen_category = item
                break

        assert mesen_category is not None
        assert mesen_category.childCount() == 1


class TestFramePropagationThroughController:
    """Tests for frame propagation from CapturedOffset to asset browser."""

    def test_add_capture_to_browser_passes_frame(self, qtbot, tmp_path, monkeypatch) -> None:
        """_add_capture_to_browser should pass frame to add_mesen_capture.

        Bug: Frame was not being propagated, causing same-offset different-frame
        captures to collide.
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        editing_controller = EditingController()
        controller = ROMWorkflowController(parent=None, editing_controller=editing_controller)
        view = ROMWorkflowPage()
        qtbot.addWidget(view)
        controller.set_view(view)

        # Set up ROM state
        dummy_rom = tmp_path / "test.sfc"
        dummy_rom.write_bytes(b"\x00" * 0x10000)
        controller.rom_path = str(dummy_rom)
        controller.rom_size = 0x10000
        controller._rom_checksum = 0xA1B2

        # Create two captures at same offset but different frames
        offset = 0x3C7001
        capture1 = CapturedOffset(
            offset=offset,
            frame=100,
            timestamp=datetime.now(tz=UTC),
            raw_line=f"FILE: 0x{offset:06X} Frame: 100",
            rom_checksum=0xA1B2,
        )
        capture2 = CapturedOffset(
            offset=offset,
            frame=200,
            timestamp=datetime.now(tz=UTC),
            raw_line=f"FILE: 0x{offset:06X} Frame: 200",
            rom_checksum=0xA1B2,
        )

        # Add both captures through the controller
        controller._add_capture_to_browser(capture1)
        controller._add_capture_to_browser(capture2)

        # Both should appear in the browser (not deduplicated due to different frames)
        browser = view._asset_browser
        mesen_category = browser._mesen_category
        assert mesen_category.childCount() == 2, (
            f"Expected 2 captures (different frames), but got {mesen_category.childCount()}"
        )

        # Verify frame data is stored correctly
        frames_found = set()
        for i in range(mesen_category.childCount()):
            item = mesen_category.child(i)
            data = item.data(0, 256)  # Qt.ItemDataRole.UserRole
            if data and data.get("frame") is not None:
                frames_found.add(data["frame"])

        assert frames_found == {100, 200}
