"""Tests for FrameMappingWorkspace selection state management.

Bug Fix 2: When an unmapped row is selected in the mapping drawer,
_selected_game_id must be cleared to prevent linking to a previously
selected capture.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from core.app_context import AppContext


def create_test_project_with_mapping(tmp_path: Path) -> FrameMappingProject:
    """Create a test project with mixed mapped/unmapped frames.

    Returns project with:
    - Frame 0: mapped to game_frame_a
    - Frame 1: unmapped
    - Frame 2: unmapped
    """
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

    # Create one game frame for mapping
    game_frame = GameFrame(
        id="game_frame_a",
        rom_offsets=[0x1000],
        capture_path=None,
        palette_index=0,
        width=8,
        height=8,
    )

    # Frame 0 is mapped to game_frame_a
    mapping = FrameMapping(
        ai_frame_id=ai_frames[0].id,  # Use ID-based mapping (stable)
        game_frame_id="game_frame_a",
        offset_x=0,
        offset_y=0,
        flip_h=False,
        flip_v=False,
        scale=1.0,
    )

    return FrameMappingProject(
        name="test_project",
        ai_frames_dir=ai_frames_dir,
        ai_frames=ai_frames,
        game_frames=[game_frame],
        mappings=[mapping],
    )


class TestUnmappedRowClearsGameSelection:
    """Tests for Fix 2: Unmapped row selection clears _selected_game_id."""

    def test_unmapped_row_clears_game_selection(self, app_context: AppContext, qtbot: QtBot, tmp_path: Path) -> None:
        """Selecting an unmapped row should clear _selected_game_id.

        Bug: When an unmapped row is selected in the mapping drawer,
        _selected_game_id is NOT cleared. This means "Map Selected" can
        link to a previously selected capture from a different row.

        Scenario:
        1. User selects mapped row 0 -> _selected_game_id = "game_frame_a"
        2. User selects unmapped row 1 -> _selected_game_id should be None
        3. Without fix: _selected_game_id is still "game_frame_a" (stale!)
        """
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Mock controller methods that access external resources
        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project_with_mapping(tmp_path)
        mock_controller.project = project
        mock_controller.get_game_frame_preview.return_value = None
        mock_controller.get_capture_result_for_game_frame.return_value = (None, False)

        workspace._controller = mock_controller
        workspace._logic.set_controller(mock_controller)  # Also update logic helper

        # Load the project into the workspace UI
        workspace._mapping_panel.set_project(project)
        workspace._ai_frames_pane.set_ai_frames(project.ai_frames)

        # Get AI frame IDs (method now uses ID-based signals)
        frame_0_id = project.ai_frames[0].id  # "frame_000.png"
        frame_1_id = project.ai_frames[1].id  # "frame_001.png"

        # Step 1: Select mapped row 0 -> should set _selected_game_id
        workspace._on_mapping_selected(frame_0_id)
        assert workspace._state.selected_game_id == "game_frame_a", (
            "Expected _selected_game_id to be 'game_frame_a' after selecting mapped row 0"
        )

        # Step 2: Select unmapped row 1 -> should CLEAR _selected_game_id
        workspace._on_mapping_selected(frame_1_id)
        assert workspace._state.selected_game_id is None, (
            "BUG: _selected_game_id should be None after selecting unmapped row, "
            f"but was {workspace._state.selected_game_id!r}. "
            "This allows 'Map Selected' to link to a stale capture."
        )

    def test_map_selected_requires_explicit_capture_after_unmapped_row(
        self, app_context: AppContext, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Map Selected should require explicit capture selection after unmapped row.

        This tests the user-facing behavior: after selecting an unmapped row,
        the user must select a capture before Map Selected will work.
        """
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        mock_controller = MagicMock(spec=FrameMappingController)
        project = create_test_project_with_mapping(tmp_path)
        mock_controller.project = project
        mock_controller.get_game_frame_preview.return_value = None
        mock_controller.get_capture_result_for_game_frame.return_value = (None, False)

        workspace._controller = mock_controller
        workspace._logic.set_controller(mock_controller)  # Also update logic helper

        workspace._mapping_panel.set_project(project)
        workspace._ai_frames_pane.set_ai_frames(project.ai_frames)

        # Get AI frame IDs (method now uses ID-based signals)
        frame_0_id = project.ai_frames[0].id  # "frame_000.png"
        frame_1_id = project.ai_frames[1].id  # "frame_001.png"

        # Select mapped row 0 to set _selected_game_id
        workspace._on_mapping_selected(frame_0_id)
        assert workspace._state.selected_game_id == "game_frame_a"

        # Select unmapped row 1
        workspace._on_mapping_selected(frame_1_id)

        # Map Selected should NOT be able to link (no game frame selected)
        # Verify by checking the state that _on_map_selected uses
        assert workspace._state.selected_game_id is None, (
            "BUG: _selected_game_id should be cleared after selecting unmapped row"
        )
