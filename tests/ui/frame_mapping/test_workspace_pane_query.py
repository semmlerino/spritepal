"""Tests for FrameMappingWorkspace pane query methods.

Phase 3: State Duplication Elimination - panes are source of truth for selection.
Workspace provides helper methods that query panes, with cached state as fallback.
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


class TestPaneQueryMethods:
    """Tests for _get_selected_ai_frame_id and _get_selected_game_id helpers."""

    def test_get_selected_ai_frame_id_queries_pane_first(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """_get_selected_ai_frame_id should query AIFramesPane as source of truth."""
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

        # User selects a frame in the pane
        workspace._ai_frames_pane.select_frame_by_id("frame_001.png")

        # Query method should return pane selection
        assert workspace._get_selected_ai_frame_id() == "frame_001.png"

        # Even if cached state is stale, pane is authoritative
        workspace._state.selected_ai_frame_id = "frame_002.png"
        assert workspace._get_selected_ai_frame_id() == "frame_001.png"

    def test_get_selected_ai_frame_id_falls_back_to_cached_state(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """If pane has no selection, fall back to cached state."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        workspace._controller = mock_controller

        # Load project but don't select anything in pane
        workspace._ai_frames_pane.set_ai_frames(project.ai_frames)

        # Set cached state
        workspace._state.selected_ai_frame_id = "frame_002.png"

        # Query should fall back to cached state when pane has no selection
        assert workspace._get_selected_ai_frame_id() == "frame_002.png"

    def test_get_selected_game_id_queries_pane_first(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """_get_selected_game_id should query CapturesLibraryPane as source of truth."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        workspace._controller = mock_controller

        # Load project into UI
        workspace._captures_pane.set_game_frames(project.game_frames)

        # User selects a game frame in the pane
        workspace._captures_pane.select_frame("game_b")

        # Query method should return pane selection
        assert workspace._get_selected_game_id() == "game_b"

        # Even if cached state is stale, pane is authoritative
        workspace._state.selected_game_id = "game_a"
        assert workspace._get_selected_game_id() == "game_b"

    def test_get_selected_game_id_falls_back_to_cached_state(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """If pane has no selection, fall back to cached state."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        workspace._controller = mock_controller

        # Load project but don't select anything in pane
        workspace._captures_pane.set_game_frames(project.game_frames)

        # Set cached state
        workspace._state.selected_game_id = "game_a"

        # Query should fall back to cached state when pane has no selection
        assert workspace._get_selected_game_id() == "game_a"

    def test_pane_query_reflects_user_selection_immediately(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Pane query should reflect user selection changes immediately."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        workspace._controller = mock_controller

        # Load project
        workspace._ai_frames_pane.set_ai_frames(project.ai_frames)
        workspace._captures_pane.set_game_frames(project.game_frames)

        # User selects AI frame
        workspace._ai_frames_pane.select_frame_by_id("frame_000.png")
        assert workspace._get_selected_ai_frame_id() == "frame_000.png"

        # User changes selection
        workspace._ai_frames_pane.select_frame_by_id("frame_001.png")
        assert workspace._get_selected_ai_frame_id() == "frame_001.png"

        # User selects game frame
        workspace._captures_pane.select_frame("game_a")
        assert workspace._get_selected_game_id() == "game_a"

        # User changes selection
        workspace._captures_pane.select_frame("game_b")
        assert workspace._get_selected_game_id() == "game_b"

    def test_cached_state_still_updated_for_backward_compatibility(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Cached state should still be updated via signal handlers for backward compat."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project(tmp_path)
        mock_controller.project = project
        mock_controller.get_game_frame_preview.return_value = None
        mock_controller.get_capture_result_for_game_frame.return_value = (None, False)
        workspace._controller = mock_controller

        # Load project
        workspace._ai_frames_pane.set_ai_frames(project.ai_frames)
        workspace._mapping_panel.set_project(project)

        # Trigger signal handler that updates cached state
        workspace._on_ai_frame_selected("frame_001.png")

        # Cached state should be updated
        assert workspace._state.selected_ai_frame_id == "frame_001.png"

        # Pane query should match
        assert workspace._get_selected_ai_frame_id() == "frame_001.png"
