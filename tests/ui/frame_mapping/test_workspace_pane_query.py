"""Tests for FrameMappingWorkspace selection state management.

Selection state is managed by WorkspaceStateManager, not panes. This ensures
selection is preserved even when filters hide items in the pane UI.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from core.frame_mapping_project import AIFrame, FrameMappingProject, GameFrame
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from core.app_context import AppContext


def create_test_project(tmp_path: Path) -> FrameMappingProject:
    """Create a minimal test project with AI and game frames."""
    ai_frames_dir = tmp_path / "ai_frames"
    ai_frames_dir.mkdir()

    # Create dummy AI frame image files
    ai_frames: list[AIFrame] = []
    for i in range(3):
        frame_path = ai_frames_dir / f"frame_{i:03d}.png"
        frame_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        ai_frames.append(AIFrame(path=frame_path, index=i, width=1, height=1))

    # Create game frames
    game_frames = [
        GameFrame(id="game_a", rom_offsets=[0x1000], width=8, height=8),
        GameFrame(id="game_b", rom_offsets=[0x2000], width=8, height=8),
    ]

    return FrameMappingProject(
        name="test_project",
        ai_frames_dir=ai_frames_dir,
        ai_frames=ai_frames,
        game_frames=game_frames,
        mappings=[],
    )


class TestStateManagerAsSourceOfTruth:
    """Tests verifying state manager is source of truth for selection."""

    def test_get_selected_ai_frame_id_returns_state_manager_value(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """_get_selected_ai_frame_id should return state manager value directly."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        mock_controller.get_game_frame_preview.return_value = None
        mock_controller.get_capture_result_for_game_frame.return_value = (None, False)
        workspace._controller = mock_controller

        # Load project into UI
        workspace._ai_frames_pane.set_ai_frames(project.ai_frames)

        # Set state manager directly
        workspace._state.selected_ai_frame_id = "frame_001.png"

        # Query method should return state manager value
        assert workspace._get_selected_ai_frame_id() == "frame_001.png"

        # Even if pane has different selection, state manager is authoritative
        workspace._ai_frames_pane.select_frame_by_id("frame_002.png")
        assert workspace._get_selected_ai_frame_id() == "frame_001.png"

    def test_get_selected_ai_frame_id_returns_none_when_no_state(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """If state manager has no selection, return None."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        workspace._controller = mock_controller

        # Load project but don't set state
        workspace._ai_frames_pane.set_ai_frames(project.ai_frames)

        # Query should return None (no state set)
        assert workspace._get_selected_ai_frame_id() is None

    def test_get_selected_game_id_returns_state_manager_value(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """_get_selected_game_id should return state manager value directly."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        workspace._controller = mock_controller

        # Load project into UI
        workspace._captures_pane.set_game_frames(project.game_frames)

        # Set state manager directly
        workspace._state.selected_game_id = "game_b"

        # Query method should return state manager value
        assert workspace._get_selected_game_id() == "game_b"

        # Even if pane has different selection, state manager is authoritative
        workspace._captures_pane.select_frame("game_a")
        assert workspace._get_selected_game_id() == "game_b"

    def test_get_selected_game_id_returns_none_when_no_state(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """If state manager has no selection, return None."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        workspace._controller = mock_controller

        # Load project but don't set state
        workspace._captures_pane.set_game_frames(project.game_frames)

        # Query should return None (no state set)
        assert workspace._get_selected_game_id() is None

    def test_signal_handler_updates_state_manager(self, app_context: AppContext, qtbot: QtBot, tmp_path: Path) -> None:
        """Signal handlers should update state manager when selection changes."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        mock_controller.get_game_frame_preview.return_value = None
        mock_controller.get_capture_result_for_game_frame.return_value = (None, False)
        workspace._controller = mock_controller
        workspace._logic.set_controller(mock_controller)  # Also update logic helper

        # Load project
        workspace._ai_frames_pane.set_ai_frames(project.ai_frames)
        workspace._mapping_panel.set_project(project)

        # Trigger signal handler that updates state manager
        workspace._on_ai_frame_selected("frame_001.png")

        # State manager should be updated
        assert workspace._state.selected_ai_frame_id == "frame_001.png"

        # Query method should reflect updated state
        assert workspace._get_selected_ai_frame_id() == "frame_001.png"

    def test_selection_preserved_when_filter_hides_item(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Selection should be preserved in state manager even when filter hides item."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        mock_controller.get_game_frame_preview.return_value = None
        mock_controller.get_capture_result_for_game_frame.return_value = (None, False)
        workspace._controller = mock_controller
        workspace._logic.set_controller(mock_controller)  # Also update logic helper

        # Load project
        workspace._ai_frames_pane.set_ai_frames(project.ai_frames)

        # Select a frame via signal handler (simulating user click)
        workspace._on_ai_frame_selected("frame_001.png")
        assert workspace._get_selected_ai_frame_id() == "frame_001.png"

        # Simulate filter hiding the selected item by clearing pane selection
        # but keeping state manager intact
        workspace._ai_frames_pane._list.clearSelection()

        # State manager should still have the selection
        assert workspace._state.selected_ai_frame_id == "frame_001.png"
        assert workspace._get_selected_ai_frame_id() == "frame_001.png"
