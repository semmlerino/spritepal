"""Tests for frame mapping workflow fixes.

Covers:
- Step 4: Controller-routed compression updates
- Step 5: Canvas state preservation
- Step 6: Split brain fixes (compression/alignment apply to correct frame)

Note: Steps 1-3 are covered by other test files:
- Step 1 (double refresh): tests/ui/frame_mapping/views/test_mapping_panel_refresh_selection.py
- Step 2 (batch injection): tests/ui/integration/test_frame_mapping_batch_operations.py
- Step 3 (auto-save): tests/unit/ui/frame_mapping/test_auto_save_manager.py + tests/ui/frame_mapping/test_auto_save_manager.py
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from core.frame_mapping_project import GameFrame
from core.types import CompressionType
from tests.fixtures.frame_mapping_helpers import create_test_project
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.frame_operations_coordinator import FrameOperationsCoordinator
from ui.frame_mapping.palette_coordinator import PaletteCoordinator
from ui.frame_mapping.views.workbench_types import AlignmentState

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestControllerRoutedCompressionUpdates:
    """Step 4: Verify compression updates go through controller."""

    def test_update_game_frame_compression_updates_all_offsets(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Controller method should update compression for all ROM offsets."""
        controller = FrameMappingController()
        # Note: FrameMappingController is QObject, not QWidget

        # Create project with game frame
        project = create_test_project(tmp_path, num_frames=1)
        game_frame = GameFrame(
            id="test_game",
            rom_offsets=[0x1000, 0x2000, 0x3000],
            capture_path=None,
            palette_index=0,
            width=8,
            height=8,
            selected_entry_ids=[],
            compression_types={0x1000: CompressionType.RAW, 0x2000: CompressionType.RAW, 0x3000: CompressionType.RAW},
        )
        project.add_game_frame(game_frame)
        # Standard test setup pattern: use controller.project setter for test setup
        controller.project = project

        # Update compression type
        result = controller.update_game_frame_compression("test_game", CompressionType.HAL)

        assert result is True
        assert game_frame.compression_types[0x1000] == CompressionType.HAL
        assert game_frame.compression_types[0x2000] == CompressionType.HAL
        assert game_frame.compression_types[0x3000] == CompressionType.HAL

    def test_update_game_frame_compression_emits_signals(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Controller method should emit project_changed and save_requested."""
        controller = FrameMappingController()
        # Note: FrameMappingController is QObject, not QWidget

        # Create project with game frame
        project = create_test_project(tmp_path, num_frames=1)
        game_frame = GameFrame(
            id="test_game",
            rom_offsets=[0x1000],
            capture_path=None,
            palette_index=0,
            width=8,
            height=8,
            selected_entry_ids=[],
            compression_types={0x1000: CompressionType.RAW},
        )
        project.add_game_frame(game_frame)
        # Standard test setup pattern: use controller.project setter for test setup
        controller.project = project

        # Track emissions
        project_changed_emissions: list[None] = []
        save_requested_emissions: list[None] = []
        controller.project_changed.connect(lambda: project_changed_emissions.append(None))
        controller.save_requested.connect(lambda: save_requested_emissions.append(None))

        # Update compression
        controller.update_game_frame_compression("test_game", CompressionType.HAL)

        assert len(project_changed_emissions) == 1, "Should emit project_changed"
        assert len(save_requested_emissions) == 1, "Should emit save_requested"

    def test_update_game_frame_compression_invalid_frame_returns_false(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Controller method returns False for non-existent frame."""
        controller = FrameMappingController()
        # Note: FrameMappingController is QObject, not QWidget

        project = create_test_project(tmp_path, num_frames=1)
        # Standard test setup pattern: use controller.project setter for test setup
        controller.project = project

        result = controller.update_game_frame_compression("nonexistent", CompressionType.HAL)

        assert result is False


class TestCanvasStatePreservation:
    """Step 5: Verify canvas state is preserved during content updates."""

    def test_project_changed_preserves_canvas_on_content_update(
        self, qtbot: QtBot, tmp_path: Path, app_context: object
    ) -> None:
        """Canvas should not clear when project content changes (same project).

        Only clear on new/load project (identity change).

        Note: This test verifies the fix was applied by checking that the state
        manager tracks previous_project_id for canvas state preservation.
        """
        from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace

        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Verify previous_project_id is tracked in state manager after fix
        assert hasattr(workspace, "_state"), "Workspace should have state manager"
        assert hasattr(workspace._state, "previous_project_id"), (
            "State manager should track previous project ID for canvas state preservation"
        )


class TestSplitBrainFixes:
    """Step 6: Verify canvas/selection split brain fixes.

    The workspace tracks two distinct IDs:
    - selected_game_id: What user last clicked in the captures library
    - current_canvas_game_id: What the canvas is actually displaying

    These can differ when previewing captures. The fixes ensure:
    1. Compression changes apply to the displayed frame (canvas), not selected
    2. Blocked alignment edits show user feedback
    """

    def test_compression_type_applied_to_canvas_frame_not_selected(
        self, qtbot: QtBot, tmp_path: Path, app_context: object
    ) -> None:
        """Compression changes should apply to canvas frame, not selected frame.

        Scenario:
        1. AI frame mapped to capture_a (selected_game_id = capture_a)
        2. User clicks capture_b to preview (canvas shows capture_b)
        3. User changes compression type
        4. Compression should apply to capture_b (what canvas shows), not capture_a

        Bug: _on_compression_type_changed used _selected_game_id instead of
        _current_canvas_game_id, causing compression to apply to the wrong frame.
        """
        from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace

        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Create project with AI frame and two game frames
        project = create_test_project(tmp_path, num_frames=1)

        capture_a = GameFrame(
            id="capture_a",
            rom_offsets=[0x1000],
            capture_path=None,
            palette_index=0,
            width=8,
            height=8,
            selected_entry_ids=[],
            compression_types={0x1000: CompressionType.RAW},
        )
        capture_b = GameFrame(
            id="capture_b",
            rom_offsets=[0x2000],
            capture_path=None,
            palette_index=0,
            width=8,
            height=8,
            selected_entry_ids=[],
            compression_types={0x2000: "raw"},
        )
        project.add_game_frame(capture_a)
        project.add_game_frame(capture_b)
        # Standard test setup pattern: use controller.project setter for test setup
        workspace.controller.project = project

        # Create mapping: AI frame -> capture_a
        ai_frame_id = project.ai_frames[0].id
        project.create_mapping(ai_frame_id, "capture_a")

        # Simulate user workflow:
        # 1. Select AI frame (loads mapping with capture_a)
        workspace._on_ai_frame_selected(ai_frame_id)
        # 2. Click capture_b to preview (canvas now shows capture_b)
        workspace._on_game_frame_selected("capture_b")

        # Verify state is set up correctly (canvas shows capture_b, not capture_a)
        assert workspace._state.selected_game_id == "capture_b"
        assert workspace._state.current_canvas_game_id == "capture_b"

        # User changes compression type via canvas
        workspace._on_compression_type_changed(CompressionType.HAL)

        # Compression should be applied to capture_b (what canvas shows),
        # NOT capture_a (what the mapping points to)
        assert capture_b.compression_types[0x2000] == CompressionType.HAL, (
            "Compression should apply to canvas frame (capture_b), not mapped frame (capture_a)"
        )
        assert capture_a.compression_types[0x1000] == CompressionType.RAW, (
            "Mapped frame (capture_a) should remain unchanged"
        )

    def test_alignment_blocked_shows_user_feedback(self, qtbot: QtBot, tmp_path: Path, app_context: object) -> None:
        """When alignment edit is blocked, user should get status bar feedback.

        Scenario:
        1. AI frame mapped to capture_a
        2. User clicks capture_b to preview (canvas shows capture_b)
        3. User drags AI frame to adjust alignment
        4. Alignment edit should be blocked AND user should see a message

        Bug: Alignment was silently blocked with no user feedback, causing
        confusion when users tried to adjust alignment.
        """
        from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace

        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Create mock message service to track feedback
        mock_message_service = MagicMock()
        workspace.set_message_service(mock_message_service)

        # Create project with AI frame and two game frames
        project = create_test_project(tmp_path, num_frames=1)

        capture_a = GameFrame(
            id="capture_a",
            rom_offsets=[0x1000],
            capture_path=None,
            palette_index=0,
            width=8,
            height=8,
            selected_entry_ids=[],
            compression_types={0x1000: CompressionType.RAW},
        )
        capture_b = GameFrame(
            id="capture_b",
            rom_offsets=[0x2000],
            capture_path=None,
            palette_index=0,
            width=8,
            height=8,
            selected_entry_ids=[],
            compression_types={0x2000: "raw"},
        )
        project.add_game_frame(capture_a)
        project.add_game_frame(capture_b)
        # Standard test setup pattern: use controller.project setter for test setup
        workspace.controller.project = project

        # Create mapping: AI frame -> capture_a
        ai_frame_id = project.ai_frames[0].id
        project.create_mapping(ai_frame_id, "capture_a")

        # Simulate user workflow:
        # 1. Select AI frame (loads mapping with capture_a)
        workspace._on_ai_frame_selected(ai_frame_id)
        # 2. Click capture_b to preview (canvas now shows capture_b)
        workspace._on_game_frame_selected("capture_b")

        # Verify state (canvas shows different frame than mapping)
        assert workspace._state.current_canvas_game_id == "capture_b"
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        assert mapping is not None
        assert mapping.game_frame_id == "capture_a"

        # User tries to adjust alignment
        state = AlignmentState(
            offset_x=10, offset_y=20, flip_h=False, flip_v=False, scale=1.0, sharpen=0.0, resampling="lanczos"
        )
        workspace._on_alignment_changed(state)

        # Alignment should be blocked (no change to mapping)
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        assert mapping is not None
        assert mapping.offset_x == 0, "Alignment should NOT be applied"
        assert mapping.offset_y == 0, "Alignment should NOT be applied"

        # User should receive feedback about the blocked edit
        mock_message_service.show_message.assert_called()
        # Find the call with the warning message (may have other show_message calls)
        calls = mock_message_service.show_message.call_args_list
        warning_calls = [c for c in calls if "not saved" in c[0][0].lower() or "different" in c[0][0].lower()]
        assert len(warning_calls) >= 1, f"Expected a message explaining why alignment was blocked. Got calls: {calls}"


class TestRemoveMappingCanvasGuard:
    """Bug 3: Verify remove_mapping preserves canvas when removing non-selected frame."""

    def test_remove_mapping_non_selected_preserves_canvas(self) -> None:
        """Canvas should NOT be cleared when removing mapping for non-selected frame."""
        # Create coordinator
        coordinator = FrameOperationsCoordinator()

        # Set up dependencies
        mock_controller = MagicMock()
        mock_controller.remove_mapping = MagicMock()
        coordinator.set_controller(mock_controller)

        mock_state = MagicMock()
        mock_state.selected_ai_frame_id = "frame_A"
        coordinator.set_state(mock_state)

        mock_canvas = MagicMock()
        mock_captures = MagicMock()
        coordinator.set_panes(alignment_canvas=mock_canvas, captures_pane=mock_captures)

        # Call remove_mapping for a DIFFERENT frame than selected
        coordinator.handle_remove_mapping("frame_B")

        # Assert: Canvas should NOT be cleared (frame_B != frame_A)
        mock_canvas.clear_alignment.assert_not_called()

        # Assert: Removal still happens
        mock_controller.remove_mapping.assert_called_once_with("frame_B")


class TestIngameSavedFrameGuard:
    """Bug 6: Verify ingame_saved only updates canvas for selected frame."""

    def test_ingame_saved_only_updates_selected_frame_canvas(self) -> None:
        """Canvas should NOT be updated when ingame_saved for non-selected frame."""
        # Create coordinator
        coordinator = PaletteCoordinator()

        # Set up dependencies (controller + state required by _require_initialized)
        mock_controller = MagicMock()
        mock_controller.project = None
        coordinator.set_controller(mock_controller)

        mock_state = MagicMock()
        mock_state.selected_ai_frame_id = "frame_A"
        coordinator.set_state(mock_state)

        mock_ai_pane = MagicMock()
        mock_mapping_panel = MagicMock()
        mock_canvas = MagicMock()
        coordinator.set_panes(
            ai_frames_pane=mock_ai_pane,
            mapping_panel=mock_mapping_panel,
            alignment_canvas=mock_canvas,
        )

        # Call _handle_ingame_saved for a DIFFERENT frame than selected
        coordinator._handle_ingame_saved("frame_B", "/some/path.png")

        # Assert: Canvas should NOT be updated (frame_B != frame_A)
        mock_canvas.set_ingame_edited_path.assert_not_called()
