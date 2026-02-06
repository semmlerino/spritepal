"""Tests for FrameMappingController undo/redo functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.frame_mapping_project import AIFrame, FrameMappingProject, GameFrame
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


class TestUndoRedoState:
    """Tests for undo/redo state management."""

    def test_new_project_clears_undo_history(self, qtbot: object, tmp_path: Path) -> None:
        """Creating a new project clears undo history."""
        controller = FrameMappingController()
        controller.new_project("First")

        # Setup: create frames and perform an undoable action
        project = controller.project
        assert project is not None

        # Create test PNG file and add AI frame
        (tmp_path / "sprite.png").write_bytes(b"PNG")
        ai_frame = AIFrame(path=tmp_path / "sprite.png", index=0)
        project.replace_ai_frames([ai_frame], tmp_path)

        # Add game frame
        game_frame = GameFrame(id="capture_A", rom_offsets=[0x1000])
        project.add_game_frame(game_frame)

        # Create mapping - this populates the undo stack
        controller.create_mapping("sprite.png", "capture_A")
        assert controller.can_undo(), "Undo stack should be populated after create_mapping"

        # Now create new project - should clear undo history
        controller.new_project("Second")

        assert not controller.can_undo(), "Undo stack should be cleared after new_project"
        assert not controller.can_redo()

    def test_initial_state_cannot_undo(self, controller: FrameMappingController) -> None:
        """Fresh controller has nothing to undo."""
        assert not controller.can_undo()
        assert not controller.can_redo()

    def test_undo_returns_none_when_empty(self, controller: FrameMappingController) -> None:
        """Undo on empty history returns None."""
        result = controller.undo()
        assert result is None

    def test_redo_returns_none_when_empty(self, controller: FrameMappingController) -> None:
        """Redo on empty redo stack returns None."""
        result = controller.redo()
        assert result is None


class TestCreateMappingUndo:
    """Tests for undoing create_mapping operations."""

    def test_create_mapping_can_be_undone(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Creating a mapping can be undone."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        # Create a mapping
        populated_controller.create_mapping("sprite_01.png", "capture_A")

        assert project.get_mapping_for_ai_frame("sprite_01.png") is not None
        assert populated_controller.can_undo()

        # Undo
        desc = populated_controller.undo()

        assert desc is not None
        assert project.get_mapping_for_ai_frame("sprite_01.png") is None

    def test_create_mapping_can_be_redone(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Undone mapping can be redone."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        populated_controller.create_mapping("sprite_01.png", "capture_A")
        populated_controller.undo()

        assert project.get_mapping_for_ai_frame("sprite_01.png") is None

        # Redo
        desc = populated_controller.redo()

        assert desc is not None
        assert project.get_mapping_for_ai_frame("sprite_01.png") is not None

    def test_undo_restores_previous_mapping(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Undoing a remapping restores the previous link."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        # Create first mapping
        populated_controller.create_mapping("sprite_01.png", "capture_A")

        # Remap to different capture
        populated_controller.create_mapping("sprite_01.png", "capture_B")

        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.game_frame_id == "capture_B"

        # Undo the remapping
        populated_controller.undo()

        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.game_frame_id == "capture_A"


class TestRemoveMappingUndo:
    """Tests for undoing remove_mapping operations."""

    def test_remove_mapping_can_be_undone(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Removing a mapping can be undone."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        populated_controller.create_mapping("sprite_01.png", "capture_A")
        populated_controller.clear_undo_history()  # Start fresh

        populated_controller.remove_mapping("sprite_01.png")

        assert project.get_mapping_for_ai_frame("sprite_01.png") is None

        # Undo
        populated_controller.undo()

        assert project.get_mapping_for_ai_frame("sprite_01.png") is not None

    def test_undo_remove_restores_alignment(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Undoing remove restores all alignment values including sharpen and resampling."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        populated_controller.create_mapping("sprite_01.png", "capture_A")
        # Set ALL 7 alignment properties
        populated_controller.update_mapping_alignment(
            "sprite_01.png", 10, 20, True, False, 0.5, sharpen=2.5, resampling="nearest"
        )
        populated_controller.clear_undo_history()

        populated_controller.remove_mapping("sprite_01.png")
        populated_controller.undo()

        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.offset_x == 10
        assert mapping.offset_y == 20
        assert mapping.flip_h is True
        assert mapping.flip_v is False
        assert mapping.scale == 0.5
        assert mapping.sharpen == 2.5
        assert mapping.resampling == "nearest"


class TestUpdateAlignmentUndo:
    """Tests for undoing alignment operations."""

    def test_alignment_change_can_be_undone(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Alignment changes can be undone."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        populated_controller.create_mapping("sprite_01.png", "capture_A")
        populated_controller.clear_undo_history()

        populated_controller.update_mapping_alignment("sprite_01.png", 10, 20, False, False, 1.0)

        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.offset_x == 10

        # Undo
        populated_controller.undo()

        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.offset_x == 0  # Default

    def test_auto_alignment_not_undoable(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Auto-alignment (set_edited=False) is not added to undo history."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        populated_controller.create_mapping("sprite_01.png", "capture_A")
        populated_controller.clear_undo_history()

        # Auto-centering during link creation
        populated_controller.update_mapping_alignment("sprite_01.png", 10, 20, False, False, 1.0, set_edited=False)

        # Should not be undoable
        assert not populated_controller.can_undo()


class TestRenameFrameUndo:
    """Tests for undoing rename operations."""

    def test_rename_frame_can_be_undone(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Renaming a frame can be undone."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        populated_controller.rename_frame("sprite_01.png", "Walking")

        frame = project.get_ai_frame_by_id("sprite_01.png")
        assert frame is not None
        assert frame.display_name == "Walking"

        # Undo
        populated_controller.undo()

        frame = project.get_ai_frame_by_id("sprite_01.png")
        assert frame is not None
        assert frame.display_name is None


class TestToggleTagUndo:
    """Tests for undoing tag toggle operations."""

    def test_toggle_tag_can_be_undone(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Toggling a tag can be undone."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        # Use a valid tag from FRAME_TAGS: {'final', 'review', 'keep', 'wip', 'discard'}
        populated_controller.toggle_frame_tag("sprite_01.png", "keep")

        frame = project.get_ai_frame_by_id("sprite_01.png")
        assert frame is not None
        assert "keep" in frame.tags

        # Undo
        populated_controller.undo()

        frame = project.get_ai_frame_by_id("sprite_01.png")
        assert frame is not None
        assert "keep" not in frame.tags


class TestRenameCaptureUndo:
    """Tests for undoing capture rename operations."""

    def test_rename_capture_can_be_undone(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Renaming a capture can be undone."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        populated_controller.rename_capture("capture_A", "Player Walk")

        frame = project.get_game_frame_by_id("capture_A")
        assert frame is not None
        assert frame.display_name == "Player Walk"

        # Undo
        populated_controller.undo()

        frame = project.get_game_frame_by_id("capture_A")
        assert frame is not None
        assert frame.display_name is None


class TestMultiStepUndo:
    """Tests for undoing multiple operations in sequence."""

    def test_multiple_operations_undo_in_order(
        self, populated_controller: FrameMappingController, qtbot: object
    ) -> None:
        """Multiple operations are undone in LIFO order."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        # Do three operations
        populated_controller.create_mapping("sprite_01.png", "capture_A")
        populated_controller.update_mapping_alignment("sprite_01.png", 10, 10, False, False, 1.0)
        populated_controller.rename_frame("sprite_01.png", "Walking")

        # Undo all three
        desc1 = populated_controller.undo()  # Undo rename
        assert desc1 is not None
        assert "Walking" in desc1 or "Rename" in desc1

        frame = project.get_ai_frame_by_id("sprite_01.png")
        assert frame is not None
        assert frame.display_name is None

        desc2 = populated_controller.undo()  # Undo alignment
        assert desc2 is not None

        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.offset_x == 0

        desc3 = populated_controller.undo()  # Undo create mapping
        assert desc3 is not None

        assert project.get_mapping_for_ai_frame("sprite_01.png") is None


class TestSignalEmission:
    """Tests for signal emission during undo/redo."""

    def test_undo_emits_project_changed(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Undo emits project_changed signal."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        populated_controller.create_mapping("sprite_01.png", "capture_A")

        with qtbot.waitSignal(populated_controller.project_changed, timeout=1000):
            populated_controller.undo()

    def test_redo_emits_project_changed(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Redo emits project_changed signal."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        populated_controller.create_mapping("sprite_01.png", "capture_A")
        populated_controller.undo()

        with qtbot.waitSignal(populated_controller.project_changed, timeout=1000):
            populated_controller.redo()

    def test_can_undo_changed_signal(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """can_undo_changed signal is emitted."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)

        with qtbot.waitSignal(populated_controller.can_undo_changed, timeout=1000) as blocker:
            populated_controller.create_mapping("sprite_01.png", "capture_A")

        assert blocker.args == [True]


class TestReorderAIFrameUndo:
    """Tests for undoing AI frame reorder operations."""

    def test_reorder_is_undoable(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Reordering an AI frame can be undone."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        # Initial order: sprite_01.png (index 0), sprite_02.png (index 1)
        assert [f.id for f in project.ai_frames] == ["sprite_01.png", "sprite_02.png"]

        # Move sprite_01.png to index 1
        populated_controller.reorder_ai_frame("sprite_01.png", 1)

        # Order should be sprite_02.png, sprite_01.png
        assert [f.id for f in project.ai_frames] == ["sprite_02.png", "sprite_01.png"]
        assert populated_controller.can_undo()

        # Undo
        desc = populated_controller.undo()

        # Order should be restored
        assert desc is not None
        assert [f.id for f in project.ai_frames] == ["sprite_01.png", "sprite_02.png"]

    def test_reorder_is_redoable(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Undone reorder can be redone."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        populated_controller.reorder_ai_frame("sprite_01.png", 1)
        populated_controller.undo()

        assert [f.id for f in project.ai_frames] == ["sprite_01.png", "sprite_02.png"]

        # Redo
        desc = populated_controller.redo()

        assert desc is not None
        assert [f.id for f in project.ai_frames] == ["sprite_02.png", "sprite_01.png"]

    def test_reorder_same_position_not_undoable(
        self, populated_controller: FrameMappingController, qtbot: object
    ) -> None:
        """Moving to same position doesn't add to undo history."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)
        project = populated_controller.project
        assert project is not None

        populated_controller.clear_undo_history()

        # Move to same position (no-op)
        result = populated_controller.reorder_ai_frame("sprite_01.png", 0)

        assert result is False
        assert not populated_controller.can_undo()

    def test_reorder_emits_signal(self, populated_controller: FrameMappingController, qtbot: object) -> None:
        """Reordering emits ai_frame_moved signal."""
        from pytestqt.qtbot import QtBot

        assert isinstance(qtbot, QtBot)

        with qtbot.waitSignal(populated_controller.ai_frame_moved, timeout=1000):
            populated_controller.reorder_ai_frame("sprite_01.png", 1)
