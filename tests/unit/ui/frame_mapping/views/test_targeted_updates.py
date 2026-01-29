"""Tests for targeted single-item update methods in frame mapping panes.

These tests verify that the performance optimization methods only update
the specific items they should, without affecting other items.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import AIFrame, GameFrame
from ui.frame_mapping.views.ai_frames_pane import AIFramesPane
from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane


class TestAIFramesPaneTargetedUpdate:
    """Test AIFramesPane.update_single_item_status()."""

    @pytest.fixture
    def pane(self, qtbot):
        """Create AIFramesPane with test data."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        # Add test frames (id and name are computed from path)
        frames = [
            AIFrame(path=Path("/test/frame_01.png"), index=0),
            AIFrame(path=Path("/test/frame_02.png"), index=1),
            AIFrame(path=Path("/test/frame_03.png"), index=2),
        ]
        pane.set_ai_frames(frames)

        # Set initial statuses
        pane.set_mapping_status({"frame_01.png": "unmapped", "frame_02.png": "mapped", "frame_03.png": "injected"})

        return pane

    def test_update_single_item_only_updates_target(self, pane):
        """Only the specified frame's status should change."""
        # Update frame_02 to "edited"
        pane.update_single_item_status("frame_02.png", "edited")

        # Check that frame_02 changed
        item2 = pane._list.item(1)
        assert "●" in item2.text()  # Status indicator

        # Check that frame_01 and frame_03 are unchanged
        item1 = pane._list.item(0)
        item3 = pane._list.item(2)
        assert "○" in item1.text()  # Unmapped
        assert "●" in item3.text()  # Injected (still mapped indicator)

    def test_update_single_item_updates_internal_status(self, pane):
        """Internal status dict should be updated."""
        pane.update_single_item_status("frame_01.png", "mapped")

        assert pane._mapping_status["frame_01.png"] == "mapped"
        # Others unchanged
        assert pane._mapping_status["frame_02.png"] == "mapped"
        assert pane._mapping_status["frame_03.png"] == "injected"

    def test_update_nonexistent_frame_is_noop(self, pane):
        """Updating nonexistent frame should not crash."""
        original_statuses = dict(pane._mapping_status)

        pane.update_single_item_status("nonexistent.png", "mapped")

        # Internal status has the new key but UI unchanged
        assert pane._mapping_status["nonexistent.png"] == "mapped"
        # Original items unchanged
        assert pane._mapping_status["frame_01.png"] == original_statuses["frame_01.png"]


class TestCapturesLibraryPaneTargetedUpdate:
    """Test CapturesLibraryPane.update_single_item_link_status()."""

    @pytest.fixture
    def pane(self, qtbot):
        """Create CapturesLibraryPane with test data."""
        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)

        # Add test game frames
        frames = [
            GameFrame(id="capture_01", width=32, height=32),
            GameFrame(id="capture_02", width=32, height=32),
            GameFrame(id="capture_03", width=32, height=32),
        ]
        pane.set_game_frames(frames)

        # Set initial link statuses
        pane.set_link_status(
            {"capture_01": None, "capture_02": "frame_02.png", "capture_03": "frame_03.png"}  # Unlinked  # Linked
        )

        return pane

    def test_update_single_item_only_updates_target(self, pane):
        """Only the specified capture's link status should change."""
        # Link capture_01 to an AI frame
        pane.update_single_item_link_status("capture_01", "frame_01.png")

        # Check that capture_01 changed
        item1 = pane._list.item(0)
        assert "✓" in item1.text()

        # Check that capture_02 and capture_03 are unchanged
        item2 = pane._list.item(1)
        item3 = pane._list.item(2)
        assert "✓" in item2.text()  # Still linked
        assert "✓" in item3.text()  # Still linked

    def test_update_single_item_unlinks(self, pane):
        """Unlinking should remove the checkmark."""
        # Unlink capture_02
        pane.update_single_item_link_status("capture_02", None)

        item2 = pane._list.item(1)
        assert "✓" not in item2.text()

        # Internal status updated
        assert pane._link_status["capture_02"] is None

    def test_update_single_item_updates_internal_status(self, pane):
        """Internal link status dict should be updated."""
        pane.update_single_item_link_status("capture_01", "ai_frame.png")

        assert pane._link_status["capture_01"] == "ai_frame.png"
        # Others unchanged
        assert pane._link_status["capture_02"] == "frame_02.png"

    def test_update_nonexistent_frame_is_noop(self, pane):
        """Updating nonexistent capture should not crash."""
        original_statuses = dict(pane._link_status)

        pane.update_single_item_link_status("nonexistent", "ai_frame.png")

        # Internal status has new key
        assert pane._link_status["nonexistent"] == "ai_frame.png"
        # Original unchanged
        assert pane._link_status["capture_01"] == original_statuses["capture_01"]
