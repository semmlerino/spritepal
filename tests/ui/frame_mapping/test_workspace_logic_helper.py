"""Tests for WorkspaceLogicHelper.

Tests the business logic extracted from FrameMappingWorkspace.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from ui.frame_mapping.workspace_logic_helper import WorkspaceLogicHelper


@pytest.fixture
def helper() -> WorkspaceLogicHelper:
    """Create a WorkspaceLogicHelper with mocked dependencies."""
    h = WorkspaceLogicHelper()

    # Mock controller
    controller = MagicMock()
    controller.project = None
    h.set_controller(controller)

    # Mock state
    state = MagicMock()
    state.selected_ai_frame_id = None
    state.selected_game_id = None
    state.current_canvas_game_id = None
    state.auto_advance_enabled = False
    h.set_state(state)

    # Mock panes
    ai_pane = MagicMock()
    captures_pane = MagicMock()
    mapping_panel = MagicMock()
    canvas = MagicMock()
    h.set_panes(ai_pane, captures_pane, mapping_panel, canvas)

    # Mock message service
    message_service = MagicMock()
    h.set_message_service(message_service)

    # Mock parent widget
    parent = MagicMock()
    h.set_parent_widget(parent)

    return h


class TestSelectionHelpers:
    """Test Phase 2a: Selection helpers."""

    def test_get_selected_ai_frame_id_returns_state_value(self, helper: WorkspaceLogicHelper) -> None:
        """get_selected_ai_frame_id returns value from state manager."""
        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]

        result = helper.get_selected_ai_frame_id()

        assert result == "frame_001.png"

    def test_get_selected_ai_frame_id_returns_none_when_no_state(self) -> None:
        """get_selected_ai_frame_id returns None when state not set."""
        helper = WorkspaceLogicHelper()

        result = helper.get_selected_ai_frame_id()

        assert result is None

    def test_get_selected_game_id_returns_state_value(self, helper: WorkspaceLogicHelper) -> None:
        """get_selected_game_id returns value from state manager."""
        helper._state.selected_game_id = "capture_123"  # type: ignore[union-attr]

        result = helper.get_selected_game_id()

        assert result == "capture_123"

    def test_update_map_button_state_enables_when_both_selected(self, helper: WorkspaceLogicHelper) -> None:
        """update_map_button_state enables button when both frames selected."""
        helper._state.selected_ai_frame_id = "frame.png"  # type: ignore[union-attr]
        helper._state.selected_game_id = "capture_1"  # type: ignore[union-attr]

        helper.update_map_button_state()

        helper._ai_frames_pane.set_map_button_enabled.assert_called_once_with(True)  # type: ignore[union-attr]

    def test_update_map_button_state_disables_when_ai_not_selected(self, helper: WorkspaceLogicHelper) -> None:
        """update_map_button_state disables button when AI frame not selected."""
        helper._state.selected_ai_frame_id = None  # type: ignore[union-attr]
        helper._state.selected_game_id = "capture_1"  # type: ignore[union-attr]

        helper.update_map_button_state()

        helper._ai_frames_pane.set_map_button_enabled.assert_called_once_with(False)  # type: ignore[union-attr]


class TestRefreshHelpers:
    """Test Phase 2b: Refresh helpers."""

    def test_refresh_mapping_status_updates_pane(self, helper: WorkspaceLogicHelper) -> None:
        """refresh_mapping_status updates AI frames pane with status map."""
        # Setup mock project
        project = MagicMock()
        ai_frame = MagicMock()
        ai_frame.id = "frame_001.png"
        project.ai_frames = [ai_frame]
        mapping = MagicMock()
        mapping.status = "injected"
        project.get_mapping_for_ai_frame.return_value = mapping
        helper._controller.project = project  # type: ignore[union-attr]

        helper.refresh_mapping_status()

        helper._ai_frames_pane.set_mapping_status.assert_called_once_with(  # type: ignore[union-attr]
            {"frame_001.png": "injected"}
        )

    def test_refresh_mapping_status_clears_when_no_project(self, helper: WorkspaceLogicHelper) -> None:
        """refresh_mapping_status clears status when no project."""
        helper._controller.project = None  # type: ignore[union-attr]

        helper.refresh_mapping_status()

        helper._ai_frames_pane.set_mapping_status.assert_called_once_with({})  # type: ignore[union-attr]

    def test_refresh_game_frame_link_status_updates_pane(self, helper: WorkspaceLogicHelper) -> None:
        """refresh_game_frame_link_status updates captures pane."""
        project = MagicMock()
        game_frame = MagicMock()
        game_frame.id = "capture_1"
        project.game_frames = [game_frame]
        project.get_ai_frame_linked_to_game_frame.return_value = "frame_001.png"
        helper._controller.project = project  # type: ignore[union-attr]

        helper.refresh_game_frame_link_status()

        helper._captures_pane.set_link_status.assert_called_once_with(  # type: ignore[union-attr]
            {"capture_1": "frame_001.png"}
        )


class TestSelectionHandlers:
    """Test Phase 2c: Selection handlers."""

    def test_handle_ai_frame_selected_clears_on_empty(self, helper: WorkspaceLogicHelper) -> None:
        """handle_ai_frame_selected clears state on empty frame_id."""
        project = MagicMock()
        helper._controller.project = project  # type: ignore[union-attr]

        helper.handle_ai_frame_selected("")

        assert helper._state.selected_ai_frame_id is None  # type: ignore[union-attr]
        helper._alignment_canvas.clear_alignment.assert_called_once()  # type: ignore[union-attr]
        helper._mapping_panel.clear_selection.assert_called_once()  # type: ignore[union-attr]

    def test_handle_ai_frame_selected_updates_state(self, helper: WorkspaceLogicHelper) -> None:
        """handle_ai_frame_selected updates state and syncs panes."""
        project = MagicMock()
        frame = MagicMock()
        frame.id = "frame_001.png"
        project.get_ai_frame_by_id.return_value = frame
        project.get_mapping_for_ai_frame.return_value = None
        helper._controller.project = project  # type: ignore[union-attr]

        helper.handle_ai_frame_selected("frame_001.png")

        assert helper._state.selected_ai_frame_id == "frame_001.png"  # type: ignore[union-attr]
        helper._mapping_panel.select_row_by_ai_id.assert_called_once_with("frame_001.png")  # type: ignore[union-attr]
        helper._alignment_canvas.set_ai_frame.assert_called_once_with(frame)  # type: ignore[union-attr]

    def test_handle_game_frame_selected_updates_state(self, helper: WorkspaceLogicHelper) -> None:
        """handle_game_frame_selected updates state."""
        project = MagicMock()
        project.get_game_frame_by_id.return_value = MagicMock()
        project.get_mapping_for_ai_frame.return_value = None
        helper._controller.project = project  # type: ignore[union-attr]
        helper._controller.get_game_frame_preview.return_value = MagicMock()  # type: ignore[union-attr]
        helper._controller.get_capture_result_for_game_frame.return_value = (None, False)  # type: ignore[union-attr]
        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]

        helper.handle_game_frame_selected("capture_1")

        assert helper._state.selected_game_id == "capture_1"  # type: ignore[union-attr]

    def test_handle_game_frame_selected_clears_on_empty(self, helper: WorkspaceLogicHelper) -> None:
        """handle_game_frame_selected clears state on empty frame_id."""
        project = MagicMock()
        helper._controller.project = project  # type: ignore[union-attr]

        helper.handle_game_frame_selected("")

        assert helper._state.selected_game_id is None  # type: ignore[union-attr]
        helper._alignment_canvas.clear_alignment.assert_called_once()  # type: ignore[union-attr]


class TestLinkingLogic:
    """Test Phase 2d: Linking logic."""

    def test_attempt_link_creates_mapping(self, helper: WorkspaceLogicHelper) -> None:
        """attempt_link creates a mapping via controller."""
        project = MagicMock()
        ai_frame = MagicMock()
        ai_frame.path.name = "frame_001.png"
        ai_frame.path.exists.return_value = False
        project.get_ai_frame_by_id.return_value = ai_frame
        project.get_mapping_for_ai_frame.return_value = None
        helper._controller.project = project  # type: ignore[union-attr]
        helper._controller.get_existing_link_for_ai_frame.return_value = None  # type: ignore[union-attr]
        helper._controller.get_existing_link_for_game_frame.return_value = None  # type: ignore[union-attr]

        helper.attempt_link("frame_001.png", "capture_1")

        helper._controller.create_mapping.assert_called_once_with(  # type: ignore[union-attr]
            "frame_001.png", "capture_1"
        )

    def test_attempt_link_same_pair_shows_message(self, helper: WorkspaceLogicHelper) -> None:
        """attempt_link shows message when linking same pair."""
        project = MagicMock()
        ai_frame = MagicMock()
        ai_frame.path.name = "frame_001.png"
        project.get_ai_frame_by_id.return_value = ai_frame
        helper._controller.project = project  # type: ignore[union-attr]
        helper._controller.get_existing_link_for_ai_frame.return_value = "capture_1"  # type: ignore[union-attr]

        helper.attempt_link("frame_001.png", "capture_1")

        helper._message_service.show_message.assert_called_once()  # type: ignore[union-attr]
        helper._controller.create_mapping.assert_not_called()  # type: ignore[union-attr]

    def test_find_next_unmapped_ai_frame_returns_next(self, helper: WorkspaceLogicHelper) -> None:
        """find_next_unmapped_ai_frame returns next unmapped frame."""
        project = MagicMock()
        frame1 = MagicMock()
        frame1.id = "frame_001.png"
        frame1.index = 0
        frame2 = MagicMock()
        frame2.id = "frame_002.png"
        frame2.index = 1
        project.ai_frames = [frame1, frame2]
        project.get_mapping_for_ai_frame.side_effect = lambda x: (MagicMock() if x == "frame_001.png" else None)
        helper._controller.project = project  # type: ignore[union-attr]

        result = helper.find_next_unmapped_ai_frame(0)

        assert result == "frame_002.png"

    def test_find_next_unmapped_ai_frame_returns_none_when_all_mapped(self, helper: WorkspaceLogicHelper) -> None:
        """find_next_unmapped_ai_frame returns None when all frames mapped."""
        project = MagicMock()
        frame1 = MagicMock()
        frame1.id = "frame_001.png"
        frame1.index = 0
        project.ai_frames = [frame1]
        project.get_mapping_for_ai_frame.return_value = MagicMock()
        helper._controller.project = project  # type: ignore[union-attr]

        result = helper.find_next_unmapped_ai_frame(0)

        assert result is None


class TestAlignmentCoordination:
    """Test Phase 2e: Alignment coordination."""

    def test_handle_alignment_changed_updates_controller(self, helper: WorkspaceLogicHelper) -> None:
        """handle_alignment_changed updates alignment via controller."""
        project = MagicMock()
        mapping = MagicMock()
        mapping.game_frame_id = "capture_1"
        project.get_mapping_for_ai_frame.return_value = mapping
        helper._controller.project = project  # type: ignore[union-attr]
        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]
        helper._state.current_canvas_game_id = "capture_1"  # type: ignore[union-attr]
        helper._alignment_canvas.get_drag_start_alignment.return_value = None  # type: ignore[union-attr]

        result = helper.handle_alignment_changed(10, 20, False, True, 1.0, 0.0, "lanczos")

        assert result is True
        helper._controller.update_mapping_alignment.assert_called_once()  # type: ignore[union-attr]

    def test_handle_alignment_changed_blocked_when_canvas_differs(self, helper: WorkspaceLogicHelper) -> None:
        """handle_alignment_changed blocked when canvas shows different capture."""
        project = MagicMock()
        mapping = MagicMock()
        mapping.game_frame_id = "capture_1"
        project.get_mapping_for_ai_frame.return_value = mapping
        helper._controller.project = project  # type: ignore[union-attr]
        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]
        helper._state.current_canvas_game_id = "capture_2"  # Different!  # type: ignore[union-attr]

        result = helper.handle_alignment_changed(10, 20, False, True, 1.0, 0.0, "lanczos")

        assert result is False
        helper._controller.update_mapping_alignment.assert_not_called()  # type: ignore[union-attr]
        helper._message_service.show_message.assert_called_once()  # type: ignore[union-attr]

    def test_sync_canvas_alignment_from_model_updates_canvas(self, helper: WorkspaceLogicHelper) -> None:
        """sync_canvas_alignment_from_model updates canvas with mapping values."""
        project = MagicMock()
        mapping = MagicMock()
        mapping.offset_x = 5
        mapping.offset_y = 10
        mapping.flip_h = True
        mapping.flip_v = False
        mapping.scale = 1.5
        mapping.sharpen = 0.0
        mapping.resampling = "lanczos"
        mapping.game_frame_id = "capture_1"
        project.get_mapping_for_ai_frame.return_value = mapping
        helper._controller.project = project  # type: ignore[union-attr]
        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]
        helper._state.current_canvas_game_id = "capture_1"  # type: ignore[union-attr]

        helper.sync_canvas_alignment_from_model()

        helper._alignment_canvas.set_alignment.assert_called_once_with(  # type: ignore[union-attr]
            5, 10, True, False, 1.5, 0.0, "lanczos", has_mapping=True
        )

    def test_sync_canvas_alignment_from_model_clears_when_no_mapping(self, helper: WorkspaceLogicHelper) -> None:
        """sync_canvas_alignment_from_model clears alignment when no mapping."""
        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = None
        helper._controller.project = project  # type: ignore[union-attr]
        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]

        helper.sync_canvas_alignment_from_model()

        helper._alignment_canvas.clear_alignment.assert_called_once()  # type: ignore[union-attr]
