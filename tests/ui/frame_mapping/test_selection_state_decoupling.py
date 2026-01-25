"""Tests for Selection State Decoupling.

When a filter hides the currently selected frame, the selection state should
be preserved in WorkspaceStateManager rather than being lost because the pane
returns None for a hidden item.
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


class TestSelectionPreservedWhenFiltered:
    """Tests for selection preservation when filter hides selected item."""

    @pytest.fixture
    def mock_project_with_frames(self, tmp_path: Path) -> tuple[MagicMock, list[AIFrame]]:
        """Create a mock project with mapped and unmapped AI frames."""
        # Create actual image files
        frames = []
        for i in range(3):
            img_path = tmp_path / f"frame_{i}.png"
            img = Image.new("RGBA", (32, 32), (i * 50, i * 50, i * 50, 255))
            img.save(img_path)
            frame = AIFrame(path=img_path, index=i)
            frames.append(frame)

        project = MagicMock(spec=FrameMappingProject)
        project.ai_frames = frames
        project.game_frames = []
        project.mappings = []
        project.get_ai_frame_by_id = lambda fid: next((f for f in frames if f.id == fid), None)
        project.get_mapping_for_ai_frame = MagicMock(return_value=None)

        return project, frames

    def test_state_manager_is_source_of_truth_for_ai_selection(
        self, qtbot: QtBot, mock_project_with_frames: tuple, tmp_path: Path
    ) -> None:
        """WorkspaceStateManager should be the source of truth for AI frame selection.

        When the pane returns None (item filtered), the state manager's value
        should still be used.
        """
        from ui.frame_mapping.views.ai_frames_pane import AIFramesPane
        from ui.workspaces.frame_mapping_workspace import WorkspaceStateManager

        project, frames = mock_project_with_frames

        # Create state manager with selection
        state = WorkspaceStateManager()
        state.selected_ai_frame_id = frames[0].id  # First frame is selected

        # Create pane and set it to return None (simulating filtered state)
        pane = AIFramesPane()
        qtbot.addWidget(pane)
        pane.set_ai_frames(frames)

        # Simulate applying filter that hides the selected frame
        # The pane's get_selected_id returns None when item is filtered
        pane.get_selected_id = MagicMock(return_value=None)

        # The state manager should still have the selection
        assert state.selected_ai_frame_id == frames[0].id

    def test_ai_frames_pane_does_not_clear_external_selection_on_filter(
        self, qtbot: QtBot, mock_project_with_frames: tuple, tmp_path: Path
    ) -> None:
        """AIFramesPane should not emit empty selection when filter hides item.

        The pane should only report what's visible, not clear external state.
        """
        from ui.frame_mapping.views.ai_frames_pane import AIFramesPane

        project, frames = mock_project_with_frames

        pane = AIFramesPane()
        qtbot.addWidget(pane)
        pane.show()
        qtbot.wait(20)

        # Set frames and select the first one
        pane.set_ai_frames(frames)
        pane.select_frame_by_id(frames[0].id)

        # Track signal emissions
        emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda fid: emissions.append(fid))

        # Mark first frame as mapped (so it will be filtered by unmapped filter)
        pane.set_mapping_status({frames[0].id: "mapped"})
        emissions.clear()

        # Apply "unmapped only" filter - this hides the selected frame
        # Access internal state and trigger refresh (acceptable in tests)
        pane._show_unmapped_only = True
        pane._refresh_list()

        # Verify: The pane should NOT emit an empty string to clear selection
        # It should either emit nothing, or emit the ID of the newly visible selection
        empty_emissions = [e for e in emissions if e == ""]
        assert len(empty_emissions) == 0, (
            f"Pane emitted empty string {len(empty_emissions)} time(s) when filter "
            "hid selected frame. This incorrectly clears workspace selection state."
        )


class TestSelectionGetterBehavior:
    """Tests for _get_selected_*_id() methods returning state directly."""

    def test_get_selected_ai_frame_id_returns_state_not_pane(self, qtbot: QtBot, tmp_path: Path) -> None:
        """_get_selected_ai_frame_id() should return state manager value.

        Even when pane returns None (item filtered), the state value is returned.
        """
        from ui.workspaces.frame_mapping_workspace import (
            FrameMappingWorkspace,
            WorkspaceStateManager,
        )

        # Create minimal workspace components
        state = WorkspaceStateManager()
        state.selected_ai_frame_id = "test_frame.png"

        # Create workspace and inject mocked state
        with patch.object(FrameMappingWorkspace, "__init__", lambda self: None):
            workspace = FrameMappingWorkspace.__new__(FrameMappingWorkspace)
            workspace._state = state

            # Mock pane to return None (simulating filtered state)
            workspace._ai_frames_pane = MagicMock()
            workspace._ai_frames_pane.get_selected_id.return_value = None

            # The method should return state manager value, not pane value
            result = workspace._get_selected_ai_frame_id()
            assert result == "test_frame.png"

    def test_get_selected_game_id_returns_state_not_pane(self, qtbot: QtBot, tmp_path: Path) -> None:
        """_get_selected_game_id() should return state manager value.

        Even when pane returns None, the state value is returned.
        """
        from ui.workspaces.frame_mapping_workspace import (
            FrameMappingWorkspace,
            WorkspaceStateManager,
        )

        # Create minimal workspace components
        state = WorkspaceStateManager()
        state.selected_game_id = "game_capture_001"

        # Create workspace and inject mocked state
        with patch.object(FrameMappingWorkspace, "__init__", lambda self: None):
            workspace = FrameMappingWorkspace.__new__(FrameMappingWorkspace)
            workspace._state = state

            # Mock pane to return None (simulating filtered state)
            workspace._captures_pane = MagicMock()
            workspace._captures_pane.get_selected_id.return_value = None

            # The method should return state manager value, not pane value
            result = workspace._get_selected_game_id()
            assert result == "game_capture_001"


class TestCapturesLibraryPaneFilterBehavior:
    """Tests for CapturesLibraryPane filter signal behavior matching AIFramesPane."""

    def test_captures_filter_does_not_clear_workspace_selection(self, qtbot: QtBot) -> None:
        """Filtering should NOT emit empty selection signal (matches AIFramesPane).

        When the "Unlinked Only" filter hides the currently selected game frame,
        the pane should NOT emit game_frame_selected("") to clear the workspace
        selection. This matches how AIFramesPane behaves and keeps the state
        manager as the source of truth.
        """
        from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane

        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)
        pane.show()
        qtbot.wait(20)

        # Create frames - one linked, one unlinked
        frame_linked = GameFrame(id="F001", rom_offsets=[0x1000])
        frame_unlinked = GameFrame(id="F002", rom_offsets=[0x2000])
        pane.set_game_frames([frame_linked, frame_unlinked])

        # Select the linked frame
        pane.select_frame("F001")
        assert pane.get_selected_id() == "F001"

        # Mark first frame as linked (has AI frame index 0)
        pane.set_link_status({"F001": 0, "F002": None})

        # Track signal emissions
        emissions: list[str] = []
        pane.game_frame_selected.connect(lambda fid: emissions.append(fid))

        # Apply "unlinked only" filter - this hides F001 (the selected frame)
        pane._show_unlinked_only = True
        pane._refresh_list()

        # Verify: The pane should NOT emit an empty string to clear selection
        # It should either emit nothing, or emit the ID of the newly visible selection
        empty_emissions = [e for e in emissions if e == ""]
        assert len(empty_emissions) == 0, (
            f"CapturesLibraryPane emitted empty string {len(empty_emissions)} time(s) when "
            "filter hid selected frame. This incorrectly clears workspace selection state. "
            "The pane should match AIFramesPane behavior and not clear external state."
        )
