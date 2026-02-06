"""Tests for PaletteCoordinator save signal emission."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from core.frame_mapping_project import AIFrame
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.palette_coordinator import PaletteCoordinator
from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager


class TestPaletteEditorSaveSignals:
    """Tests for PaletteCoordinator save signal emission."""

    def test_palette_editor_save_emits_save_requested(
        self, controller: FrameMappingController, tmp_path: Path, qtbot: QtBot
    ) -> None:
        """Palette editor save should emit save_requested for autosave.

        BUG-3 Fix: When the palette editor saves, it should emit both
        project_changed (to mark project as modified) and save_requested
        (to trigger autosave immediately).
        """
        project = controller.project
        assert project is not None

        # Add an AI frame so _handle_palette_editor_save has a valid frame to work with
        (tmp_path / "sprite_01.png").write_bytes(b"PNG")
        ai_frame = AIFrame(path=tmp_path / "sprite_01.png", index=0)
        project.replace_ai_frames([ai_frame], tmp_path)

        # Set up palette coordinator with controller
        coordinator = PaletteCoordinator()
        coordinator.set_controller(controller)

        # PaletteCoordinator also needs a state manager
        state = WorkspaceStateManager()
        state.selected_ai_frame_id = "sprite_01.png"
        coordinator.set_state(state)

        # Spy on save_requested signal emission
        save_requested_spy: list[bool] = []
        controller.save_requested.connect(lambda: save_requested_spy.append(True))

        # Call the handler directly (simulating palette editor save)
        # The handler uses the frame ID and output path
        output_path = str(tmp_path / "sprite_01.png")
        coordinator._handle_palette_editor_save("sprite_01.png", None, output_path)

        # Verify save_requested signal was emitted
        assert len(save_requested_spy) > 0, "save_requested signal should have been emitted"
