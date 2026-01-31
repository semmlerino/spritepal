"""Tests for undo/redo error paths and edge cases.

These tests verify that undo/redo operations handle error conditions gracefully,
including when the project state has changed (frame deleted, project reloaded, etc.).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.frame_mapping_project import AIFrame, GameFrame
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.undo.command_context import CommandContext
from ui.frame_mapping.undo.commands import (
    CreateMappingCommand,
    RemoveMappingCommand,
    UpdateAlignmentCommand,
)
from ui.frame_mapping.views.workbench_types import AlignmentState


@pytest.fixture
def controller(qtbot: object) -> FrameMappingController:
    """Create a controller with a test project."""
    ctrl = FrameMappingController()
    ctrl.new_project("Test Project")
    return ctrl


@pytest.fixture
def populated_controller(controller: FrameMappingController, tmp_path: Path) -> FrameMappingController:
    """Create a controller with AI frames and game frames."""
    project = controller.project
    assert project is not None

    # Create test PNG files
    (tmp_path / "sprite_01.png").write_bytes(b"PNG")
    (tmp_path / "sprite_02.png").write_bytes(b"PNG")

    # Add AI frames
    ai_frame_1 = AIFrame(path=tmp_path / "sprite_01.png", index=0)
    ai_frame_2 = AIFrame(path=tmp_path / "sprite_02.png", index=1)
    project.replace_ai_frames([ai_frame_1, ai_frame_2], tmp_path)

    # Add game frames
    game_frame_1 = GameFrame(id="capture_A", rom_offsets=[0x1000])
    game_frame_2 = GameFrame(id="capture_B", rom_offsets=[0x2000])
    project.add_game_frame(game_frame_1)
    project.add_game_frame(game_frame_2)

    return controller


def get_ctx(controller: FrameMappingController) -> CommandContext:
    """Get command context from controller."""
    return controller._get_command_context()


class TestUndoWhenProjectIsNone:
    """Tests for undo operations when project is None."""

    def test_undo_returns_none_without_project(self, controller: FrameMappingController) -> None:
        """Undo returns None when there is no project."""
        # Clear the project
        controller._project = None

        result = controller.undo()
        assert result is None

    def test_redo_returns_none_without_project(self, controller: FrameMappingController) -> None:
        """Redo returns None when there is no project."""
        controller._project = None

        result = controller.redo()
        assert result is None

    def test_can_undo_false_without_project(self, controller: FrameMappingController) -> None:
        """can_undo returns False when there is no project."""
        controller._project = None

        assert controller.can_undo() is False

    def test_can_redo_false_without_project(self, controller: FrameMappingController) -> None:
        """can_redo returns False when there is no project."""
        controller._project = None

        assert controller.can_redo() is False


class TestUndoWhenFrameWasDeleted:
    """Tests for undo when referenced frames have been deleted."""

    def test_undo_create_mapping_when_ai_frame_deleted(self, populated_controller: FrameMappingController) -> None:
        """Undo create mapping gracefully handles deleted AI frame.

        When an AI frame is deleted after a mapping was created, undoing
        should not crash (the remove operation will be a no-op).
        """
        project = populated_controller.project
        assert project is not None

        # Create a mapping (this pushes to undo stack)
        populated_controller.create_mapping("sprite_01.png", "capture_A")
        assert populated_controller.can_undo()

        # Delete the AI frame
        populated_controller.remove_ai_frame("sprite_01.png")

        # Undo should not raise, even though the frame is gone
        result = populated_controller.undo()
        # The undo stack still returns the description
        assert result is not None

    def test_undo_create_mapping_when_game_frame_deleted(self, populated_controller: FrameMappingController) -> None:
        """Undo create mapping gracefully handles deleted game frame."""
        project = populated_controller.project
        assert project is not None

        # Create a mapping
        populated_controller.create_mapping("sprite_01.png", "capture_A")
        assert populated_controller.can_undo()

        # Delete the game frame
        populated_controller.remove_game_frame("capture_A")

        # Undo should not crash
        result = populated_controller.undo()
        assert result is not None

    def test_undo_alignment_when_mapping_deleted(self, populated_controller: FrameMappingController) -> None:
        """Undo alignment update gracefully handles deleted mapping."""
        project = populated_controller.project
        assert project is not None

        # Create mapping and update alignment
        populated_controller.create_mapping("sprite_01.png", "capture_A")
        populated_controller.update_mapping_alignment("sprite_01.png", 10, 20, False, False, 1.0)

        # Remove the mapping (but don't clear undo stack)
        populated_controller.remove_mapping("sprite_01.png")

        # Now undo the remove mapping (which restores it)
        populated_controller.undo()

        # And undo the alignment change - this should work
        result = populated_controller.undo()
        assert result is not None


class TestRedoAfterProjectReload:
    """Tests for redo after project reload or new project."""

    def test_redo_cleared_after_new_project(self, populated_controller: FrameMappingController) -> None:
        """Redo stack is cleared when a new project is created."""
        # Create mapping and undo it
        populated_controller.create_mapping("sprite_01.png", "capture_A")
        populated_controller.undo()
        assert populated_controller.can_redo()

        # Create new project
        populated_controller.new_project("New Project")

        # Redo should be cleared
        assert not populated_controller.can_redo()

    def test_undo_cleared_after_new_project(self, populated_controller: FrameMappingController) -> None:
        """Undo stack is cleared when a new project is created."""
        populated_controller.create_mapping("sprite_01.png", "capture_A")
        assert populated_controller.can_undo()

        populated_controller.new_project("New Project")

        assert not populated_controller.can_undo()

    def test_redo_stack_cleared_by_new_operation(self, populated_controller: FrameMappingController) -> None:
        """Redo stack is cleared when a new operation is performed after undo."""
        # Create two mappings
        populated_controller.create_mapping("sprite_01.png", "capture_A")
        populated_controller.create_mapping("sprite_02.png", "capture_B")

        # Undo the second mapping
        populated_controller.undo()
        assert populated_controller.can_redo()

        # Perform a new operation (this should clear redo stack)
        populated_controller.update_mapping_alignment("sprite_01.png", 5, 5, False, False, 1.0)

        # Redo should now be unavailable
        assert not populated_controller.can_redo()


class TestAlignmentServiceErrors:
    """Tests for alignment service error cases."""

    def test_returns_false_for_nonexistent_frame(self, populated_controller: FrameMappingController) -> None:
        """apply_alignment_to_project returns False for nonexistent frame."""
        project = populated_controller.project
        assert project is not None

        alignment = AlignmentState(
            offset_x=0, offset_y=0, flip_h=False, flip_v=False, scale=1.0, sharpen=0.0, resampling="lanczos"
        )
        result = populated_controller._alignment_service.apply_alignment_to_project(
            project, "nonexistent.png", alignment, set_edited=True
        )
        assert result is False


class TestCommandExecutionErrors:
    """Tests for command execution error handling.

    Note: These tests verify that commands operate correctly on the project
    snapshot captured at command creation time. Commands hold a reference
    to the project via CommandContext, so even if the controller's project
    changes, the command operates on its original project reference.
    """

    def test_execute_create_mapping_with_valid_context(self, populated_controller: FrameMappingController) -> None:
        """CreateMappingCommand.execute works with valid context."""
        ctx = get_ctx(populated_controller)
        cmd = CreateMappingCommand(
            ctx=ctx,
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_A",
        )

        # Execute should work
        cmd.execute()

        # Verify mapping was created
        assert ctx.project.get_mapping_for_ai_frame("sprite_01.png") is not None

    def test_undo_remove_mapping_restores_correctly(self, populated_controller: FrameMappingController) -> None:
        """RemoveMappingCommand.undo restores the mapping."""
        # Create a mapping first
        project = populated_controller.project
        assert project is not None
        project.create_mapping("sprite_01.png", "capture_A")

        ctx = get_ctx(populated_controller)
        cmd = RemoveMappingCommand(
            ctx=ctx,
            ai_frame_id="sprite_01.png",
            removed_game_frame_id="capture_A",
            removed_alignment=AlignmentState(
                offset_x=0, offset_y=0, flip_h=False, flip_v=False, scale=1.0, sharpen=0.0, resampling="lanczos"
            ),
        )

        cmd.execute()
        assert ctx.project.get_mapping_for_ai_frame("sprite_01.png") is None

        cmd.undo()
        assert ctx.project.get_mapping_for_ai_frame("sprite_01.png") is not None

    def test_undo_update_alignment_restores_correctly(self, populated_controller: FrameMappingController) -> None:
        """UpdateAlignmentCommand.undo restores original alignment."""
        # Create a mapping first
        project = populated_controller.project
        assert project is not None
        project.create_mapping("sprite_01.png", "capture_A")

        ctx = get_ctx(populated_controller)
        cmd = UpdateAlignmentCommand(
            ctx=ctx,
            ai_frame_id="sprite_01.png",
            new_alignment=AlignmentState(
                offset_x=10, offset_y=20, flip_h=True, flip_v=False, scale=0.5, sharpen=0.0, resampling="lanczos"
            ),
            old_alignment=AlignmentState(
                offset_x=0, offset_y=0, flip_h=False, flip_v=False, scale=1.0, sharpen=0.0, resampling="lanczos"
            ),
        )

        cmd.execute()
        mapping = ctx.project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.offset_x == 10

        cmd.undo()
        mapping = ctx.project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.offset_x == 0
