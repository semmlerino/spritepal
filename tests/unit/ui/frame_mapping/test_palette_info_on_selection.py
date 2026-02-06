"""Tests for palette info updates on AI/game frame selection."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.frame_mapping_project import FrameMapping, GameFrame
from ui.frame_mapping.workspace_logic_helper import WorkspaceLogicHelper


class TestPaletteInfoOnSelection:
    """Test that palette widget info is updated when selecting frames."""

    @pytest.fixture
    def helper_with_mocks(self):
        """Create a WorkspaceLogicHelper with mocked dependencies."""
        helper = WorkspaceLogicHelper()

        # Mock controller
        controller = MagicMock()
        project = MagicMock()
        controller.project = project
        helper.set_controller(controller)

        # Mock state
        state = MagicMock()
        helper.set_state(state)
        helper._state.selected_ai_frame_id = None
        helper._state.selected_game_id = None
        helper._state.current_canvas_game_id = None

        # Mock panes
        helper.set_panes(MagicMock(), MagicMock(), MagicMock(), MagicMock())

        return helper, project

    def test_palette_info_updated_on_ai_frame_selection_with_mapping(self, helper_with_mocks):
        """Selecting an AI frame with a mapping should update palette info."""
        helper, project = helper_with_mocks

        # Set up mapping and game frame
        mapping = FrameMapping(
            ai_frame_id="ai_frame_001",
            game_frame_id="game_001",
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            scale=1.0,
            sharpen=0.0,
            resampling="nearest",
        )
        project.get_mapping_for_ai_frame.return_value = mapping

        game_frame = GameFrame(id="game_001", palette_index=5)
        project.get_game_frame_by_id.return_value = game_frame
        project.get_ai_frame_by_id.return_value = MagicMock()

        # Capture result with entries
        capture_result = MagicMock()
        entry1 = MagicMock()
        entry1.palette = 5
        entry2 = MagicMock()
        entry2.palette = 7
        capture_result.entries = [entry1, entry2]
        helper._controller.get_capture_result_for_game_frame.return_value = (capture_result, False)
        helper._controller.get_cached_game_frame_preview.return_value = MagicMock()

        helper.handle_ai_frame_selected("ai_frame_001")

        # Verify palette info was set
        helper._ai_frames_pane.set_capture_palette_info.assert_called_once_with({5, 7})
        helper._ai_frames_pane.set_current_frame_palette_index.assert_called_once_with(5)

    def test_palette_info_cleared_when_no_mapping(self, helper_with_mocks):
        """Selecting an AI frame without mapping should clear palette info."""
        helper, project = helper_with_mocks

        project.get_mapping_for_ai_frame.return_value = None
        project.get_ai_frame_by_id.return_value = MagicMock()

        helper.handle_ai_frame_selected("ai_frame_001")

        helper._ai_frames_pane.set_capture_palette_info.assert_called_once_with(None)
        helper._ai_frames_pane.set_current_frame_palette_index.assert_called_once_with(None)

    def test_palette_info_updated_on_game_frame_selection(self, helper_with_mocks):
        """Selecting a game frame should update palette info."""
        helper, project = helper_with_mocks
        helper._state.selected_ai_frame_id = "some_ai_frame"

        game_frame = GameFrame(id="game_001", palette_index=3)
        project.get_game_frame_by_id.return_value = game_frame

        capture_result = MagicMock()
        entry = MagicMock()
        entry.palette = 3
        capture_result.entries = [entry]
        helper._controller.get_capture_result_for_game_frame.return_value = (capture_result, False)
        helper._controller.get_cached_game_frame_preview.return_value = MagicMock()

        project.get_mapping_for_ai_frame.return_value = None

        helper.handle_game_frame_selected("game_001")

        helper._ai_frames_pane.set_capture_palette_info.assert_called_once_with({3})
        helper._ai_frames_pane.set_current_frame_palette_index.assert_called_once_with(3)
