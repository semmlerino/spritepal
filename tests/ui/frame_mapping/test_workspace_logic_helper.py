"""Tests for WorkspaceLogicHelper.

Tests the business logic extracted from FrameMappingWorkspace.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.infrastructure.fake_panes import (
    FakeAIFramesPane,
    FakeCapturesPane,
    FakeMappingPanel,
    FakeWorkbenchCanvas,
)
from ui.frame_mapping.views.workbench_types import AlignmentState
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
    ai_pane = FakeAIFramesPane()
    captures_pane = FakeCapturesPane()
    mapping_panel = FakeMappingPanel()
    canvas = FakeWorkbenchCanvas()
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
        """update_map_button_state enables button when both frames selected and visible."""
        helper._state.selected_ai_frame_id = "frame.png"  # type: ignore[union-attr]
        helper._state.selected_game_id = "capture_1"  # type: ignore[union-attr]
        helper._ai_frames_pane._visible_items.add("frame.png")

        helper.update_map_button_state()

        assert helper._ai_frames_pane.map_button_enabled is True

    def test_update_map_button_state_disables_when_ai_not_selected(self, helper: WorkspaceLogicHelper) -> None:
        """update_map_button_state disables button when AI frame not selected."""
        helper._state.selected_ai_frame_id = None  # type: ignore[union-attr]
        helper._state.selected_game_id = "capture_1"  # type: ignore[union-attr]

        helper.update_map_button_state()

        assert helper._ai_frames_pane.map_button_enabled is False

    def test_update_map_button_state_disables_when_ai_frame_filtered(self, helper: WorkspaceLogicHelper) -> None:
        """update_map_button_state disables button when selected AI frame is hidden by filter."""
        helper._state.selected_ai_frame_id = "frame.png"  # type: ignore[union-attr]
        helper._state.selected_game_id = "capture_1"  # type: ignore[union-attr]
        # Frame exists in state but is not visible (filtered out)
        # Don't add to _visible_items, it's empty by default

        helper.update_map_button_state()

        assert helper._ai_frames_pane.map_button_enabled is False

    def test_update_map_button_state_enables_when_ai_frame_visible(self, helper: WorkspaceLogicHelper) -> None:
        """update_map_button_state enables button when selected AI frame is visible."""
        helper._state.selected_ai_frame_id = "frame.png"  # type: ignore[union-attr]
        helper._state.selected_game_id = "capture_1"  # type: ignore[union-attr]
        # Frame is visible (passes filters)
        helper._ai_frames_pane._visible_items.add("frame.png")

        helper.update_map_button_state()

        assert helper._ai_frames_pane.map_button_enabled is True


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

        assert helper._ai_frames_pane.mapping_status == {"frame_001.png": "injected"}

    def test_refresh_mapping_status_clears_when_no_project(self, helper: WorkspaceLogicHelper) -> None:
        """refresh_mapping_status clears status when no project."""
        helper._controller.project = None  # type: ignore[union-attr]

        helper.refresh_mapping_status()

        assert helper._ai_frames_pane.mapping_status == {}

    def test_refresh_game_frame_link_status_updates_pane(self, helper: WorkspaceLogicHelper) -> None:
        """refresh_game_frame_link_status updates captures pane."""
        project = MagicMock()
        game_frame = MagicMock()
        game_frame.id = "capture_1"
        project.game_frames = [game_frame]
        project.get_ai_frame_linked_to_game_frame.return_value = "frame_001.png"
        helper._controller.project = project  # type: ignore[union-attr]

        helper.refresh_game_frame_link_status()

        assert helper._captures_pane.link_status == {"capture_1": "frame_001.png"}


class TestSelectionHandlers:
    """Test Phase 2c: Selection handlers."""

    def test_handle_ai_frame_selected_clears_on_empty(self, helper: WorkspaceLogicHelper) -> None:
        """handle_ai_frame_selected clears state on empty frame_id."""
        project = MagicMock()
        helper._controller.project = project  # type: ignore[union-attr]

        helper.handle_ai_frame_selected("")

        assert helper._state.selected_ai_frame_id is None  # type: ignore[union-attr]
        assert helper._alignment_canvas.alignment_cleared is True
        assert helper._mapping_panel.selection_cleared is True

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
        assert helper._mapping_panel.selected_ai_id == "frame_001.png"
        assert helper._alignment_canvas.ai_frame is frame

    def test_handle_game_frame_selected_updates_state(self, helper: WorkspaceLogicHelper) -> None:
        """handle_game_frame_selected updates state."""
        project = MagicMock()
        project.get_game_frame_by_id.return_value = MagicMock()
        project.get_mapping_for_ai_frame.return_value = None
        helper._controller.project = project  # type: ignore[union-attr]
        helper._controller.get_cached_game_frame_preview.return_value = MagicMock()  # type: ignore[union-attr]
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
        assert helper._alignment_canvas.alignment_cleared is True


class TestLinkingLogic:
    """Test Phase 2d: Linking logic."""

    def test_attempt_link_creates_mapping(self, helper: WorkspaceLogicHelper) -> None:
        """attempt_link creates a mapping and triggers auto-align with scale."""
        project = MagicMock()
        ai_frame = MagicMock()
        ai_frame.path.name = "frame_001.png"
        ai_frame.path.exists.return_value = False
        ai_frame.index = 0
        game_frame = MagicMock()
        project.get_ai_frame_by_id.return_value = ai_frame
        project.get_game_frame_by_id.return_value = game_frame
        project.get_mapping_for_ai_frame.return_value = None
        helper._controller.project = project  # type: ignore[union-attr]
        helper._controller.get_existing_link_for_ai_frame.return_value = None  # type: ignore[union-attr]
        helper._controller.get_existing_link_for_game_frame.return_value = None  # type: ignore[union-attr]
        helper._controller.get_cached_game_frame_preview.return_value = None  # type: ignore[union-attr]
        helper._controller.get_capture_result_for_game_frame.return_value = (None, False)  # type: ignore[union-attr]

        helper.attempt_link("frame_001.png", "capture_1")

        helper._controller.create_mapping.assert_called_once_with(  # type: ignore[union-attr]
            "frame_001.png", "capture_1"
        )
        # Verify canvas was set up with game frame and auto-align triggered
        assert helper._alignment_canvas.game_frame is not None
        assert helper._alignment_canvas.auto_aligned is True
        assert helper._alignment_canvas.auto_align_with_scale is True

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


class TestMappingPanelRowUpdate:
    """Test Bug 2: Mapping panel row update when mapping is removed."""

    def test_update_single_mapping_panel_row_clears_on_no_mapping(self, helper: WorkspaceLogicHelper) -> None:
        """update_single_mapping_panel_row should clear row when mapping is None."""
        # Setup: Project where get_mapping_for_ai_frame returns None
        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = None
        helper._controller.project = project  # type: ignore[union-attr]

        # Call the method
        helper.update_single_mapping_panel_row("frame_A")

        # Assert: Should clear the row when mapping is None
        assert "frame_A" in helper._mapping_panel.cleared_rows


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
        helper._alignment_canvas.drag_start_alignment = None

        state = AlignmentState(
            offset_x=10, offset_y=20, flip_h=False, flip_v=True, scale=1.0, sharpen=0.0, resampling="lanczos"
        )
        result = helper.handle_alignment_changed(state)

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

        state = AlignmentState(
            offset_x=10, offset_y=20, flip_h=False, flip_v=True, scale=1.0, sharpen=0.0, resampling="lanczos"
        )
        result = helper.handle_alignment_changed(state)

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

        assert helper._alignment_canvas.alignment == (5, 10, True, False, 1.5, 0.0, "lanczos")
        assert helper._alignment_canvas.alignment_has_mapping is True

    def test_sync_canvas_alignment_from_model_clears_when_no_mapping(self, helper: WorkspaceLogicHelper) -> None:
        """sync_canvas_alignment_from_model clears alignment when no mapping."""
        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = None
        helper._controller.project = project  # type: ignore[union-attr]
        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]

        helper.sync_canvas_alignment_from_model()

        assert helper._alignment_canvas.alignment_cleared is True
