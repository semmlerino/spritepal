"""Regression test for add_single_item duplication bug.

This test verifies that add_single_item does not duplicate frames in
project.ai_frames when the pane holds a shared reference to that list.

Bug description:
- AIFramesPane.set_ai_frames(project.ai_frames) creates a shared reference
- Calling add_single_item(frame) should only add UI item, not modify list
- Previously, add_single_item appended to self._ai_frames (shared reference)
- Since facade already called project.add_ai_frame(), this created a duplicate

Fix: Removed the self._ai_frames.append(frame) line from add_single_item()
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.frame_mapping_project import AIFrame, FrameMappingProject
from tests.fixtures.frame_mapping_helpers import MINIMAL_PNG_DATA
from ui.frame_mapping.views.ai_frames_pane import AIFramesPane


class TestAIFramesPaneAddSingleItemRegression:
    """Regression test for shared reference duplication bug."""

    @pytest.fixture
    def project_with_pane(self, qtbot, tmp_path):
        """Create a project and pane with shared ai_frames reference."""
        # Create project with initial frames
        ai_frames_dir = tmp_path / "ai_frames"
        ai_frames_dir.mkdir()

        initial_frame_path = ai_frames_dir / "frame_000.png"
        initial_frame_path.write_bytes(MINIMAL_PNG_DATA)

        project = FrameMappingProject(
            name="test_project",
            ai_frames_dir=ai_frames_dir,
            ai_frames=[AIFrame(path=initial_frame_path, index=0)],
            game_frames=[],
            mappings=[],
        )

        # Create pane and set shared reference
        pane = AIFramesPane()
        qtbot.addWidget(pane)
        pane.set_ai_frames(project.ai_frames)  # Shared reference!

        return project, pane, ai_frames_dir

    def test_add_single_item_no_duplicate(self, project_with_pane):
        """add_single_item should not duplicate frame in project.ai_frames.

        This is a regression test for the bug where:
        1. Pane holds shared reference to project.ai_frames
        2. add_single_item was appending to self._ai_frames (shared)
        3. Since facade already added frame via project.add_ai_frame(),
           the frame appeared twice in project.ai_frames
        """
        project, pane, ai_frames_dir = project_with_pane

        # Verify initial state
        assert len(project.ai_frames) == 1

        # Create a new frame and add it to the project (simulating facade behavior)
        new_frame_path = ai_frames_dir / "frame_001.png"
        new_frame_path.write_bytes(MINIMAL_PNG_DATA)
        new_frame = AIFrame(path=new_frame_path, index=1)
        project.add_ai_frame(new_frame)

        # Now call add_single_item (simulating UI update after facade operation)
        pane.add_single_item(new_frame)

        # BUG: Previously, project.ai_frames would have 3 entries:
        # [frame_000, frame_001, frame_001] (duplicate!)
        # FIX: Now it should have exactly 2 entries:
        assert len(project.ai_frames) == 2
        assert project.ai_frames[0].path.name == "frame_000.png"
        assert project.ai_frames[1].path.name == "frame_001.png"

    def test_add_single_item_updates_ui(self, project_with_pane):
        """add_single_item should still add the item to the UI list."""
        project, pane, ai_frames_dir = project_with_pane

        # Add frame to project first
        new_frame_path = ai_frames_dir / "frame_001.png"
        new_frame_path.write_bytes(MINIMAL_PNG_DATA)
        new_frame = AIFrame(path=new_frame_path, index=1)
        project.add_ai_frame(new_frame)

        # Verify initial UI state (1 item)
        assert pane._list.count() == 1

        # Call add_single_item
        pane.add_single_item(new_frame)

        # UI should now show 2 items
        assert pane._list.count() == 2

        # Verify the new item is displayed correctly
        item = pane._list.item(1)
        assert item is not None
        assert "frame_001" in item.text()
