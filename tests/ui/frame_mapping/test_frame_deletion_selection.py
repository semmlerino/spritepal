"""Tests for AI frame deletion and selection state synchronization.

When an AI frame is deleted while selected, the selection state should be properly
cleared across all components (state manager, canvas, mapping panel).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, FrameMappingProject, GameFrame

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestAIFrameDeletionClearsSelection:
    """Tests that deleting the selected AI frame properly clears selection state."""

    @pytest.fixture
    def mock_project_with_frames(self, tmp_path: Path) -> tuple[FrameMappingProject, list[AIFrame]]:
        """Create a real project with AI frames for testing."""
        # Create actual image files
        frames = []
        for i in range(3):
            img_path = tmp_path / f"frame_{i}.png"
            img = Image.new("RGBA", (32, 32), (i * 50, i * 50, i * 50, 255))
            img.save(img_path)
            frame = AIFrame(path=img_path, index=i)
            frames.append(frame)

        project = FrameMappingProject(name="test_project")
        for frame in frames:
            project.add_ai_frame(frame)

        return project, frames

    def test_refresh_list_emits_signal_when_selection_cleared_by_deletion(
        self, qtbot: QtBot, mock_project_with_frames: tuple, tmp_path: Path
    ) -> None:
        """_refresh_list should emit ai_frame_selected("") when deleted frame was selected.

        When set_ai_frames is called after a frame deletion, if the previously selected
        frame no longer exists, the pane should emit ai_frame_selected("") to notify
        the workspace to clear its state.
        """
        from ui.frame_mapping.views.ai_frames_pane import AIFramesPane

        project, frames = mock_project_with_frames

        pane = AIFramesPane()
        qtbot.addWidget(pane)
        pane.show()
        qtbot.wait(20)

        # Set frames and select the first one
        pane.set_ai_frames(list(project.ai_frames))
        pane.select_frame_by_id(frames[0].id)
        assert pane.get_selected_id() == frames[0].id

        # Track signal emissions
        emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda fid: emissions.append(fid))

        # Simulate project with first frame removed (what happens after deletion)
        remaining_frames = [f for f in project.ai_frames if f.id != frames[0].id]

        # This should emit ai_frame_selected("") because the selected frame is gone
        pane.set_ai_frames(remaining_frames)

        # Verify: Should emit empty string to signal selection was cleared
        assert "" in emissions, (
            "When a frame list change removes the selected frame, "
            "_refresh_list should emit ai_frame_selected('') to notify workspace."
        )

    def test_state_manager_cleared_after_frame_deletion(
        self, qtbot: QtBot, mock_project_with_frames: tuple, tmp_path: Path
    ) -> None:
        """WorkspaceStateManager.selected_ai_frame_id should be None after deletion.

        After removing an AI frame that was selected, the state manager should
        have its selected_ai_frame_id set to None.
        """
        from ui.frame_mapping.views.ai_frames_pane import AIFramesPane
        from ui.frame_mapping.workspace_logic_helper import WorkspaceLogicHelper
        from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager

        project, frames = mock_project_with_frames
        frame_to_delete = frames[0]

        # Create state manager and set selection
        state = WorkspaceStateManager()
        state.selected_ai_frame_id = frame_to_delete.id

        # Create pane
        pane = AIFramesPane()
        qtbot.addWidget(pane)
        pane.set_ai_frames(list(project.ai_frames))
        pane.select_frame_by_id(frame_to_delete.id)

        # Create logic helper with mocked dependencies
        helper = WorkspaceLogicHelper()
        helper.set_state(state)

        # Mock canvas and other components
        canvas = MagicMock()
        mapping_panel = MagicMock()
        captures_pane = MagicMock()
        controller = MagicMock()
        controller.project = project

        helper.set_panes(pane, captures_pane, mapping_panel, canvas)
        helper.set_controller(controller)

        # Connect pane signal to logic helper
        pane.ai_frame_selected.connect(helper.handle_ai_frame_selected)

        # Remove frame from project and update pane
        project.remove_ai_frame(frame_to_delete.id)
        pane.set_ai_frames(list(project.ai_frames))

        # Verify state is cleared
        assert state.selected_ai_frame_id is None, (
            "After deleting the selected frame, state.selected_ai_frame_id should be None"
        )

    def test_canvas_cleared_after_frame_deletion(
        self, qtbot: QtBot, mock_project_with_frames: tuple, tmp_path: Path
    ) -> None:
        """Canvas should be cleared after deleting selected AI frame.

        When the selected AI frame is deleted, clear_alignment should be called
        on the canvas.
        """
        from ui.frame_mapping.views.ai_frames_pane import AIFramesPane
        from ui.frame_mapping.workspace_logic_helper import WorkspaceLogicHelper
        from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager

        project, frames = mock_project_with_frames
        frame_to_delete = frames[0]

        # Create state manager and set selection
        state = WorkspaceStateManager()
        state.selected_ai_frame_id = frame_to_delete.id

        # Create pane
        pane = AIFramesPane()
        qtbot.addWidget(pane)
        pane.set_ai_frames(list(project.ai_frames))
        pane.select_frame_by_id(frame_to_delete.id)

        # Create logic helper with mocked dependencies
        helper = WorkspaceLogicHelper()
        helper.set_state(state)

        # Mock canvas and other components
        canvas = MagicMock()
        mapping_panel = MagicMock()
        captures_pane = MagicMock()
        controller = MagicMock()
        controller.project = project

        helper.set_panes(pane, captures_pane, mapping_panel, canvas)
        helper.set_controller(controller)

        # Connect pane signal to logic helper
        pane.ai_frame_selected.connect(helper.handle_ai_frame_selected)

        # Remove frame from project and update pane
        project.remove_ai_frame(frame_to_delete.id)
        pane.set_ai_frames(list(project.ai_frames))

        # Verify canvas was cleared
        canvas.clear_alignment.assert_called()
        canvas.set_ai_frame.assert_called_with(None)


class TestDeletionDoesNotAffectUnrelatedSelection:
    """Tests that deleting non-selected frames doesn't affect selection."""

    @pytest.fixture
    def mock_project_with_frames(self, tmp_path: Path) -> tuple[FrameMappingProject, list[AIFrame]]:
        """Create a real project with AI frames for testing."""
        frames = []
        for i in range(3):
            img_path = tmp_path / f"frame_{i}.png"
            img = Image.new("RGBA", (32, 32), (i * 50, i * 50, i * 50, 255))
            img.save(img_path)
            frame = AIFrame(path=img_path, index=i)
            frames.append(frame)

        project = FrameMappingProject(name="test_project")
        for frame in frames:
            project.add_ai_frame(frame)

        return project, frames

    def test_deleting_unselected_frame_preserves_selection(
        self, qtbot: QtBot, mock_project_with_frames: tuple, tmp_path: Path
    ) -> None:
        """Selection should be preserved when deleting a different frame.

        When frame B is deleted while frame A is selected, frame A should
        remain selected.
        """
        from ui.frame_mapping.views.ai_frames_pane import AIFramesPane

        project, frames = mock_project_with_frames
        frame_to_keep_selected = frames[0]
        frame_to_delete = frames[1]

        pane = AIFramesPane()
        qtbot.addWidget(pane)
        pane.show()
        qtbot.wait(20)

        # Set frames and select the first one
        pane.set_ai_frames(list(project.ai_frames))
        pane.select_frame_by_id(frame_to_keep_selected.id)
        assert pane.get_selected_id() == frame_to_keep_selected.id

        # Track signal emissions
        emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda fid: emissions.append(fid))

        # Simulate project with second frame removed
        project.remove_ai_frame(frame_to_delete.id)
        pane.set_ai_frames(list(project.ai_frames))

        # Selection should be restored (re-emit the selected frame ID)
        assert frame_to_keep_selected.id in emissions, (
            "When deletion removes a different frame, selection should be restored "
            "and the selected frame's ID should be emitted."
        )

        # Empty string should NOT be emitted
        assert "" not in emissions, "Deleting an unselected frame should not emit empty selection signal."
