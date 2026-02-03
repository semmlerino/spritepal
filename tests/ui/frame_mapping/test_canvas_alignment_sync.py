"""Tests for canvas alignment synchronization with model.

Bug P1: When alignment is updated programmatically (not by user drag),
_on_alignment_updated only updates the mapping panel drawer. The canvas
still shows the old position.

Fix: _on_alignment_updated should also call _sync_canvas_alignment_from_model()
when the modified frame is currently selected.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
from tests.fixtures.frame_mapping_helpers import MINIMAL_PNG_DATA, create_test_capture
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from core.app_context import AppContext


def create_project_with_mapping(tmp_path: Path) -> tuple[FrameMappingProject, AIFrame, GameFrame]:
    """Create a project with one AI frame mapped to one game frame."""
    import json

    ai_frames_dir = tmp_path / "ai_frames"
    ai_frames_dir.mkdir(parents=True, exist_ok=True)
    captures_dir = tmp_path / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)

    # Create AI frame
    ai_path = ai_frames_dir / "frame_000.png"
    ai_path.write_bytes(MINIMAL_PNG_DATA)
    ai_frame = AIFrame(path=ai_path, index=0, width=64, height=64)

    # Create game frame with capture
    capture_path = captures_dir / "capture_001.json"
    capture_data = create_test_capture([1, 2, 3])
    capture_path.write_text(json.dumps(capture_data))
    game_frame = GameFrame(
        id="capture_001",
        capture_path=capture_path,
        rom_offsets=[0x100000],
        selected_entry_ids=[1, 2, 3],
    )

    # Create mapping with initial alignment
    mapping = FrameMapping(
        ai_frame_id=ai_frame.id,
        game_frame_id=game_frame.id,
        offset_x=10,
        offset_y=20,
        flip_h=False,
        flip_v=False,
        scale=1.0,
    )

    project = FrameMappingProject(
        name="test_project",
        ai_frames_dir=ai_frames_dir,
        ai_frames=[ai_frame],
        game_frames=[game_frame],
        mappings=[mapping],
    )

    return project, ai_frame, game_frame


class TestCanvasAlignmentSync:
    """Tests for canvas alignment synchronization with model state."""

    def test_programmatic_alignment_update_syncs_to_canvas(
        self,
        app_context: AppContext,
        qtbot: QtBot,
        tmp_path: Path,
        wait_for_signal_processed,
    ) -> None:
        """When alignment is updated programmatically, canvas should reflect new values.

        Bug: _on_alignment_updated only updated the mapping panel drawer. The canvas
        still showed the old position when the user was viewing the affected frame.

        Fix: When the modified frame is currently selected, also call
        _sync_canvas_alignment_from_model() to update the canvas.
        """
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        project, ai_frame, game_frame = create_project_with_mapping(tmp_path)

        # Set up the workspace with the project
        controller = workspace._controller
        controller._project = project
        controller.project_changed.emit()
        wait_for_signal_processed()

        # Select the AI frame (this should load the mapping into the canvas)
        workspace._ai_frames_pane.select_frame(ai_frame.index)
        workspace._on_ai_frame_selected(ai_frame.id)
        wait_for_signal_processed()

        # Verify initial canvas state
        canvas = workspace._alignment_canvas
        alignment = canvas.get_alignment()
        assert alignment.offset_x == 10, f"Initial X offset should be 10, got {alignment.offset_x}"
        assert alignment.offset_y == 20, f"Initial Y offset should be 20, got {alignment.offset_y}"

        # Now programmatically update the alignment (simulate controller update)
        # This is what happens when alignment is changed via API, not user drag
        mapping = project.get_mapping_for_ai_frame(ai_frame.id)
        assert mapping is not None
        mapping.offset_x = 999
        mapping.offset_y = 888

        # Emit the alignment_updated signal (this is what the controller does)
        controller.alignment_updated.emit(ai_frame.id)
        wait_for_signal_processed()

        # BUG: Canvas still shows old position (10, 20)
        # FIX: Canvas should now show new position (999, 888)
        new_alignment = canvas.get_alignment()
        assert new_alignment.offset_x == 999, (
            f"Canvas X offset should be 999 after programmatic update, got {new_alignment.offset_x}. "
            "Canvas was not synced when alignment_updated signal was emitted."
        )
        assert new_alignment.offset_y == 888, (
            f"Canvas Y offset should be 888 after programmatic update, got {new_alignment.offset_y}. "
            "Canvas was not synced when alignment_updated signal was emitted."
        )

    def test_alignment_update_for_unselected_frame_does_not_sync_canvas(
        self,
        app_context: AppContext,
        qtbot: QtBot,
        tmp_path: Path,
        wait_for_signal_processed,
    ) -> None:
        """When alignment is updated for a frame that is NOT selected, canvas should not change.

        This verifies we only sync when the modified frame matches the current selection.
        """
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Create project with TWO AI frames
        ai_frames_dir = tmp_path / "ai_frames"
        ai_frames_dir.mkdir(parents=True, exist_ok=True)

        ai_path_0 = ai_frames_dir / "frame_000.png"
        ai_path_0.write_bytes(MINIMAL_PNG_DATA)
        ai_frame_0 = AIFrame(path=ai_path_0, index=0, width=64, height=64)

        ai_path_1 = ai_frames_dir / "frame_001.png"
        ai_path_1.write_bytes(MINIMAL_PNG_DATA)
        ai_frame_1 = AIFrame(path=ai_path_1, index=1, width=64, height=64)

        # Create game frames and mappings
        import json

        captures_dir = tmp_path / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)

        capture_path_0 = captures_dir / "capture_000.json"
        capture_path_0.write_text(json.dumps(create_test_capture([1])))
        game_frame_0 = GameFrame(
            id="capture_000",
            capture_path=capture_path_0,
            rom_offsets=[0x100000],
            selected_entry_ids=[1],
        )

        capture_path_1 = captures_dir / "capture_001.json"
        capture_path_1.write_text(json.dumps(create_test_capture([2])))
        game_frame_1 = GameFrame(
            id="capture_001",
            capture_path=capture_path_1,
            rom_offsets=[0x100100],
            selected_entry_ids=[2],
        )

        mapping_0 = FrameMapping(
            ai_frame_id=ai_frame_0.id,
            game_frame_id=game_frame_0.id,
            offset_x=10,
            offset_y=10,
        )
        mapping_1 = FrameMapping(
            ai_frame_id=ai_frame_1.id,
            game_frame_id=game_frame_1.id,
            offset_x=20,
            offset_y=20,
        )

        project = FrameMappingProject(
            name="test_project",
            ai_frames_dir=ai_frames_dir,
            ai_frames=[ai_frame_0, ai_frame_1],
            game_frames=[game_frame_0, game_frame_1],
            mappings=[mapping_0, mapping_1],
        )

        controller = workspace._controller
        controller._project = project
        controller.project_changed.emit()
        wait_for_signal_processed()

        # Select frame 0
        workspace._ai_frames_pane.select_frame(0)
        workspace._on_ai_frame_selected(ai_frame_0.id)
        wait_for_signal_processed()

        canvas = workspace._alignment_canvas
        initial_alignment = canvas.get_alignment()
        assert initial_alignment.offset_x == 10, f"Initial X should be 10, got {initial_alignment.offset_x}"

        # Now update alignment for frame 1 (NOT the selected frame)
        mapping_1.offset_x = 999
        controller.alignment_updated.emit(ai_frame_1.id)
        wait_for_signal_processed()

        # Canvas should still show frame 0's alignment (unchanged)
        final_alignment = canvas.get_alignment()
        assert final_alignment.offset_x == 10, (
            f"Canvas X should still be 10 (frame 0's alignment), got {final_alignment.offset_x}. "
            "Canvas should not update for non-selected frame alignment changes."
        )
