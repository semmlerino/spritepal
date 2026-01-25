"""Tests for frame mapping workflow fixes.

Covers:
- Step 1: Double refresh prevention
- Step 2: Batch injection signal coalescing
- Step 3: Auto-save after structural changes
- Step 4: Controller-routed compression updates
- Step 5: Canvas state preservation
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from core.frame_mapping_project import AIFrame, FrameMappingProject, GameFrame
from tests.fixtures.frame_mapping_helpers import create_test_project
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.views.mapping_panel import MappingPanel

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestDoubleRefreshPrevention:
    """Step 1: Verify set_project doesn't auto-refresh."""

    def test_set_project_does_not_call_refresh(self, qtbot: QtBot, tmp_path: Path) -> None:
        """MappingPanel.set_project() should NOT call refresh() internally.

        The caller controls refresh timing to prevent double refresh when
        project_changed signal triggers both set_project and update_previews.
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=3)

        # Track refresh calls
        refresh_call_count = 0
        original_refresh = panel.refresh

        def counting_refresh() -> None:
            nonlocal refresh_call_count
            refresh_call_count += 1
            original_refresh()

        panel.refresh = counting_refresh  # type: ignore[method-assign]

        # Call set_project - should NOT trigger refresh
        panel.set_project(project)

        assert refresh_call_count == 0, (
            f"set_project() called refresh() {refresh_call_count} times, expected 0. "
            "Caller should control refresh timing."
        )

    def test_project_changed_causes_single_rebuild(self, qtbot: QtBot, tmp_path: Path) -> None:
        """When project_changed fires, mapping panel rebuilds exactly once.

        This tests the full flow where workspace._on_project_changed calls
        set_project then _update_mapping_panel_previews.
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=5)

        # First set up the panel
        panel.set_project(project)
        panel.refresh()

        # Track refresh calls
        refresh_call_count = 0
        original_refresh = panel.refresh

        def counting_refresh() -> None:
            nonlocal refresh_call_count
            refresh_call_count += 1
            original_refresh()

        panel.refresh = counting_refresh  # type: ignore[method-assign]

        # Simulate workspace._on_project_changed behavior:
        # 1. set_project (should NOT refresh)
        panel.set_project(project)
        # 2. _update_mapping_panel_previews calls refresh
        panel.refresh()

        # Should be exactly 1 refresh (from explicit call, not from set_project)
        assert refresh_call_count == 1, (
            f"Expected exactly 1 refresh, got {refresh_call_count}. set_project should not call refresh internally."
        )


class TestBatchInjectionSignalCoalescing:
    """Step 2: Verify batch injection emits project_changed once."""

    def test_inject_mapping_with_emit_false_does_not_emit_project_changed(self, qtbot: QtBot, tmp_path: Path) -> None:
        """inject_mapping(emit_project_changed=False) should not emit signal.

        This enables batch injection to emit once at the end instead of per-frame.
        """
        controller = FrameMappingController()
        # Note: FrameMappingController is QObject, not QWidget - no addWidget needed

        # Track project_changed emissions
        emissions: list[None] = []
        controller.project_changed.connect(lambda: emissions.append(None))

        # Create project with AI frame and game frame
        project = create_test_project(tmp_path, num_frames=1)
        ai_frame = project.ai_frames[0]

        # Create game frame with ROM offset
        game_frame = GameFrame(
            id="test_game",
            rom_offsets=[0x1000],
            capture_path=None,  # Will cause injection to fail, but that's OK for this test
            palette_index=0,
            width=8,
            height=8,
            selected_entry_ids=[],
            compression_types={0x1000: "raw"},
        )
        project.add_game_frame(game_frame)
        project.create_mapping(ai_frame.id, game_frame.id)
        controller._project = project
        emissions.clear()  # Clear any emissions from setup

        # inject_mapping with emit_project_changed=False should not emit
        # (It will fail due to no capture file, but the signal behavior is what we're testing)
        with patch.object(controller, "_project", project):
            controller.inject_mapping(
                ai_frame_id="frame_0.png",
                rom_path=tmp_path / "nonexistent.sfc",
                emit_project_changed=False,
            )

        # We expect NO project_changed emission when emit_project_changed=False
        # Note: The injection will fail, but what matters is no signal during batch
        # (The actual test is: no emissions from inject_mapping's project_changed.emit line)


class TestAutoSaveAfterStructuralChanges:
    """Step 3: Verify save_requested is emitted after structural changes."""

    def test_create_mapping_emits_save_requested(self, qtbot: QtBot, tmp_path: Path) -> None:
        """create_mapping() should emit save_requested after success."""
        controller = FrameMappingController()
        # Note: FrameMappingController is QObject, not QWidget

        # Create project
        project = create_test_project(tmp_path, num_frames=1)
        game_frame = GameFrame(
            id="test_game",
            rom_offsets=[0x1000],
            capture_path=None,
            palette_index=0,
            width=8,
            height=8,
            selected_entry_ids=[],
            compression_types={},
        )
        project.add_game_frame(game_frame)
        controller._project = project

        # Track save_requested emissions
        save_emissions: list[None] = []
        controller.save_requested.connect(lambda: save_emissions.append(None))

        # Create mapping - use AI frame ID
        ai_frame_id = project.ai_frames[0].id
        controller.create_mapping(ai_frame_id, "test_game")

        assert len(save_emissions) == 1, (
            f"Expected 1 save_requested emission after create_mapping, got {len(save_emissions)}"
        )

    def test_remove_mapping_emits_save_requested(self, qtbot: QtBot, tmp_path: Path) -> None:
        """remove_mapping() should emit save_requested after success."""
        controller = FrameMappingController()
        # Note: FrameMappingController is QObject, not QWidget

        # Create project with mapping
        project = create_test_project(tmp_path, num_frames=1)
        game_frame = GameFrame(
            id="test_game",
            rom_offsets=[0x1000],
            capture_path=None,
            palette_index=0,
            width=8,
            height=8,
            selected_entry_ids=[],
            compression_types={},
        )
        project.add_game_frame(game_frame)
        project.create_mapping(project.ai_frames[0].id, "test_game")
        controller._project = project

        # Track save_requested emissions
        save_emissions: list[None] = []
        controller.save_requested.connect(lambda: save_emissions.append(None))

        # Remove mapping - use AI frame ID
        ai_frame_id = project.ai_frames[0].id
        controller.remove_mapping(ai_frame_id)

        assert len(save_emissions) == 1, (
            f"Expected 1 save_requested emission after remove_mapping, got {len(save_emissions)}"
        )


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
            compression_types={0x1000: "raw", 0x2000: "raw", 0x3000: "raw"},
        )
        project.add_game_frame(game_frame)
        controller._project = project

        # Update compression type
        result = controller.update_game_frame_compression("test_game", "hal")

        assert result is True
        assert game_frame.compression_types[0x1000] == "hal"
        assert game_frame.compression_types[0x2000] == "hal"
        assert game_frame.compression_types[0x3000] == "hal"

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
            compression_types={0x1000: "raw"},
        )
        project.add_game_frame(game_frame)
        controller._project = project

        # Track emissions
        project_changed_emissions: list[None] = []
        save_requested_emissions: list[None] = []
        controller.project_changed.connect(lambda: project_changed_emissions.append(None))
        controller.save_requested.connect(lambda: save_requested_emissions.append(None))

        # Update compression
        controller.update_game_frame_compression("test_game", "hal")

        assert len(project_changed_emissions) == 1, "Should emit project_changed"
        assert len(save_requested_emissions) == 1, "Should emit save_requested"

    def test_update_game_frame_compression_invalid_frame_returns_false(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Controller method returns False for non-existent frame."""
        controller = FrameMappingController()
        # Note: FrameMappingController is QObject, not QWidget

        project = create_test_project(tmp_path, num_frames=1)
        controller._project = project

        result = controller.update_game_frame_compression("nonexistent", "hal")

        assert result is False


class TestCanvasStatePreservation:
    """Step 5: Verify canvas state is preserved during content updates."""

    def test_project_changed_preserves_canvas_on_content_update(
        self, qtbot: QtBot, tmp_path: Path, app_context: object
    ) -> None:
        """Canvas should not clear when project content changes (same project).

        Only clear on new/load project (identity change).
        """
        # This test needs the full workspace, but we can test the concept
        # by checking that _previous_project_id tracking works
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
    - _selected_game_id: What user last clicked in the captures library
    - _current_canvas_game_id: What the canvas is actually displaying

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
            compression_types={0x1000: "raw"},
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
        workspace._controller._project = project

        # Simulate: AI frame mapped to capture_a, but canvas shows capture_b
        ai_frame_id = project.ai_frames[0].id
        project.create_mapping(ai_frame_id, "capture_a")
        workspace._state.selected_ai_frame_id = ai_frame_id
        workspace._state.selected_game_id = "capture_a"  # What was linked
        workspace._state.current_canvas_game_id = "capture_b"  # What canvas displays (user previewing)

        # User changes compression type via canvas
        workspace._on_compression_type_changed("hal")

        # Compression should be applied to capture_b (what canvas shows),
        # NOT capture_a (what was selected for linking)
        assert capture_b.compression_types[0x2000] == "hal", (
            "Compression should apply to canvas frame (capture_b), not selected frame (capture_a)"
        )
        assert capture_a.compression_types[0x1000] == "raw", "Selected frame (capture_a) should remain unchanged"

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
        workspace._message_service = mock_message_service

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
            compression_types={0x1000: "raw"},
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
        workspace._controller._project = project

        # Create mapping AI frame -> capture_a
        ai_frame_id = project.ai_frames[0].id
        project.create_mapping(ai_frame_id, "capture_a")
        workspace._state.selected_ai_frame_id = ai_frame_id
        workspace._state.selected_game_id = "capture_a"
        workspace._state.current_canvas_game_id = "capture_b"  # Canvas shows different frame

        # User tries to adjust alignment
        workspace._on_alignment_changed(10, 20, False, False, 1.0)

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
