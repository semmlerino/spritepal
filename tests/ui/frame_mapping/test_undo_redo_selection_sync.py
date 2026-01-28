"""Tests for undo/redo selection synchronization.

Regression tests for the bug where undo/redo failed to synchronize selection state,
blocking alignment edits after mapping restoration.
"""

from __future__ import annotations

from unittest.mock import MagicMock

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


class TestUndoRedoSelectionSync:
    """Test undo/redo synchronization of selection state."""

    def test_sync_canvas_alignment_after_undo_syncs_selected_game_id(self, helper: WorkspaceLogicHelper) -> None:
        """Sync canvas after undo/redo restores mapping and syncs selected_game_id.

        When user undoes a mapping deletion:
        1. Mapping is restored in the model
        2. sync_canvas_alignment_from_model() is called
        3. Canvas game frame should be updated
        4. selected_game_id cache should be updated  <-- THIS WAS MISSING
        5. CapturesLibraryPane should be selected  <-- THIS WAS MISSING

        This regression test ensures alignment edits are not blocked by the
        invariant check that requires selected_game_id == current_canvas_game_id.
        """
        # Setup: mapping exists with AI frame linked to game frame
        project = MagicMock()
        mapping = MagicMock()
        mapping.offset_x = 5
        mapping.offset_y = 10
        mapping.flip_h = False
        mapping.flip_v = False
        mapping.scale = 1.0
        mapping.sharpen = 0.0
        mapping.resampling = "lanczos"
        mapping.game_frame_id = "capture_1"

        game_frame = MagicMock()
        game_frame.id = "capture_1"

        project.get_mapping_for_ai_frame.return_value = mapping
        project.get_game_frame_by_id.return_value = game_frame

        helper._controller.project = project  # type: ignore[union-attr]
        helper._controller.get_game_frame_preview.return_value = MagicMock()  # type: ignore[union-attr]
        helper._controller.get_capture_result_for_game_frame.return_value = (None, False)  # type: ignore[union-attr]

        # AI frame is already selected
        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]

        # BEFORE undo: canvas shows nothing
        helper._state.current_canvas_game_id = None  # type: ignore[union-attr]
        helper._state.selected_game_id = None  # type: ignore[union-attr]
        helper._captures_pane = MagicMock()  # type: ignore[union-attr]

        # Call sync_canvas_alignment_from_model (happens after undo)
        helper.sync_canvas_alignment_from_model()

        # VERIFY: Canvas was updated with game frame
        helper._alignment_canvas.set_game_frame.assert_called_once()  # type: ignore[union-attr]

        # VERIFY: current_canvas_game_id was updated
        assert helper._state.current_canvas_game_id == "capture_1"  # type: ignore[union-attr]

        # VERIFY: selected_game_id WAS UPDATED (this was the bug)
        assert helper._state.selected_game_id == "capture_1"  # type: ignore[union-attr]

        # VERIFY: CapturesLibraryPane.select_frame was called (this was the bug)
        helper._captures_pane.select_frame.assert_called_once_with("capture_1")  # type: ignore[union-attr]

    def test_sync_canvas_alignment_respects_block_signals_on_select_frame(self, helper: WorkspaceLogicHelper) -> None:
        """Ensure select_frame is called even when captures_pane exists.

        Regression check: previously, if captures_pane existed but wasn't properly
        synced, alignment changes would be blocked by invariant violation.
        """
        project = MagicMock()
        mapping = MagicMock()
        mapping.game_frame_id = "capture_1"
        mapping.offset_x = 0
        mapping.offset_y = 0
        mapping.flip_h = False
        mapping.flip_v = False
        mapping.scale = 1.0
        mapping.sharpen = 0.0
        mapping.resampling = "lanczos"

        game_frame = MagicMock()

        project.get_mapping_for_ai_frame.return_value = mapping
        project.get_game_frame_by_id.return_value = game_frame

        helper._controller.project = project  # type: ignore[union-attr]
        helper._controller.get_game_frame_preview.return_value = MagicMock()  # type: ignore[union-attr]
        helper._controller.get_capture_result_for_game_frame.return_value = (None, False)  # type: ignore[union-attr]

        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]
        helper._state.current_canvas_game_id = "capture_2"  # Different capture  # type: ignore[union-attr]
        helper._captures_pane = MagicMock()  # type: ignore[union-attr]

        helper.sync_canvas_alignment_from_model()

        # Verify both state update AND pane selection happened
        assert helper._state.selected_game_id == "capture_1"  # type: ignore[union-attr]
        helper._captures_pane.select_frame.assert_called_once_with("capture_1")  # type: ignore[union-attr]

    def test_sync_canvas_alignment_when_no_captures_pane_still_updates_state(
        self, helper: WorkspaceLogicHelper
    ) -> None:
        """State is updated even if captures_pane is not available.

        Edge case: if captures_pane is None, we should still update the state cache.
        The alignment invariant check still passes because current_canvas_game_id
        matches selected_game_id.
        """
        project = MagicMock()
        mapping = MagicMock()
        mapping.game_frame_id = "capture_1"
        mapping.offset_x = 0
        mapping.offset_y = 0
        mapping.flip_h = False
        mapping.flip_v = False
        mapping.scale = 1.0
        mapping.sharpen = 0.0
        mapping.resampling = "lanczos"

        game_frame = MagicMock()

        project.get_mapping_for_ai_frame.return_value = mapping
        project.get_game_frame_by_id.return_value = game_frame

        helper._controller.project = project  # type: ignore[union-attr]
        helper._controller.get_game_frame_preview.return_value = MagicMock()  # type: ignore[union-attr]
        helper._controller.get_capture_result_for_game_frame.return_value = (None, False)  # type: ignore[union-attr]

        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]
        helper._state.current_canvas_game_id = None  # type: ignore[union-attr]
        helper._captures_pane = None  # type: ignore[union-attr]

        helper.sync_canvas_alignment_from_model()

        # State updated even without captures_pane
        assert helper._state.selected_game_id == "capture_1"  # type: ignore[union-attr]
        assert helper._state.current_canvas_game_id == "capture_1"  # type: ignore[union-attr]

    def test_sync_canvas_alignment_no_sync_when_canvas_unchanged(self, helper: WorkspaceLogicHelper) -> None:
        """Skip pane sync if canvas already shows correct game frame.

        Optimization: only sync pane when canvas changes. If canvas already
        displays the correct game frame, don't call select_frame.
        """
        project = MagicMock()
        mapping = MagicMock()
        mapping.game_frame_id = "capture_1"
        mapping.offset_x = 0
        mapping.offset_y = 0
        mapping.flip_h = False
        mapping.flip_v = False
        mapping.scale = 1.0
        mapping.sharpen = 0.0
        mapping.resampling = "lanczos"

        project.get_mapping_for_ai_frame.return_value = mapping

        helper._controller.project = project  # type: ignore[union-attr]

        helper._state.selected_ai_frame_id = "frame_001.png"  # type: ignore[union-attr]
        helper._state.current_canvas_game_id = "capture_1"  # Already correct  # type: ignore[union-attr]
        helper._captures_pane = MagicMock()  # type: ignore[union-attr]

        helper.sync_canvas_alignment_from_model()

        # Canvas update skipped (already showing correct frame)
        helper._alignment_canvas.set_game_frame.assert_not_called()  # type: ignore[union-attr]

        # But state cache should still be updated
        assert helper._state.selected_game_id == "capture_1"  # type: ignore[union-attr]
