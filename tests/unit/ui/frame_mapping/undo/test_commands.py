"""Tests for frame mapping undo commands.

These tests verify that command objects correctly execute and undo operations
by verifying the resulting project state (not mock calls).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.frame_mapping_project import AIFrame, GameFrame
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.undo.commands import (
    CreateMappingCommand,
    RemoveMappingCommand,
    RenameAIFrameCommand,
    RenameCaptureCommand,
    ToggleFrameTagCommand,
    UpdateAlignmentCommand,
)


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

    # Add AI frames using the proper API (id is derived from path.name)
    ai_frame_1 = AIFrame(path=tmp_path / "sprite_01.png", index=0)
    ai_frame_2 = AIFrame(path=tmp_path / "sprite_02.png", index=1)
    project.replace_ai_frames([ai_frame_1, ai_frame_2], tmp_path)

    # Add game frames using the proper API
    game_frame_1 = GameFrame(id="capture_A", rom_offsets=[0x1000])
    game_frame_2 = GameFrame(id="capture_B", rom_offsets=[0x2000])
    project.add_game_frame(game_frame_1)
    project.add_game_frame(game_frame_2)

    return controller


class TestCreateMappingCommand:
    """Tests for CreateMappingCommand."""

    def test_description(self, populated_controller: FrameMappingController) -> None:
        """Command has descriptive string."""
        cmd = CreateMappingCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_A",
        )
        assert "sprite_01.png" in cmd.description
        assert "capture_A" in cmd.description

    def test_execute_creates_mapping(self, populated_controller: FrameMappingController) -> None:
        """Execute creates the mapping in the project."""
        project = populated_controller.project
        assert project is not None

        cmd = CreateMappingCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_A",
        )

        # No mapping initially
        assert project.get_mapping_for_ai_frame("sprite_01.png") is None

        cmd.execute()

        # Mapping now exists
        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.game_frame_id == "capture_A"

    def test_undo_removes_mapping(self, populated_controller: FrameMappingController) -> None:
        """Undo removes the created mapping."""
        project = populated_controller.project
        assert project is not None

        cmd = CreateMappingCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_A",
        )

        cmd.execute()
        assert project.get_mapping_for_ai_frame("sprite_01.png") is not None

        cmd.undo()

        # Mapping removed
        assert project.get_mapping_for_ai_frame("sprite_01.png") is None

    def test_undo_restores_previous_ai_mapping(self, populated_controller: FrameMappingController) -> None:
        """Undo restores previous AI frame mapping if it existed."""
        project = populated_controller.project
        assert project is not None

        # Create initial mapping with all 7 alignment properties
        populated_controller._create_mapping_no_history("sprite_01.png", "capture_A")
        populated_controller._update_alignment_no_history(
            "sprite_01.png", 10, 20, True, False, 0.5, sharpen=1.5, resampling="nearest"
        )

        # Command to remap to different game frame (capture all 7 properties)
        cmd = CreateMappingCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_B",
            prev_ai_mapping_game_id="capture_A",
            prev_ai_mapping_alignment=(10, 20, True, False, 0.5, 1.5, "nearest"),
        )

        cmd.execute()
        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.game_frame_id == "capture_B"

        cmd.undo()

        # Original mapping restored with all alignment properties
        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.game_frame_id == "capture_A"
        assert mapping.offset_x == 10
        assert mapping.offset_y == 20
        assert mapping.flip_h is True
        assert mapping.flip_v is False
        assert mapping.scale == 0.5
        assert mapping.sharpen == 1.5
        assert mapping.resampling == "nearest"


class TestRemoveMappingCommand:
    """Tests for RemoveMappingCommand."""

    def test_description(self, populated_controller: FrameMappingController) -> None:
        """Command has descriptive string."""
        cmd = RemoveMappingCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
        )
        assert "sprite_01.png" in cmd.description

    def test_execute_removes_mapping(self, populated_controller: FrameMappingController) -> None:
        """Execute removes the mapping from the project."""
        project = populated_controller.project
        assert project is not None

        # Create a mapping first
        populated_controller._create_mapping_no_history("sprite_01.png", "capture_A")
        assert project.get_mapping_for_ai_frame("sprite_01.png") is not None

        cmd = RemoveMappingCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
        )

        cmd.execute()

        # Mapping removed
        assert project.get_mapping_for_ai_frame("sprite_01.png") is None

    def test_undo_restores_mapping(self, populated_controller: FrameMappingController) -> None:
        """Undo restores the removed mapping with all alignment properties."""
        project = populated_controller.project
        assert project is not None

        # Create and configure a mapping with all 7 alignment properties
        populated_controller._create_mapping_no_history("sprite_01.png", "capture_A")
        populated_controller._update_alignment_no_history(
            "sprite_01.png", 5, 10, False, True, 0.75, sharpen=2.0, resampling="nearest"
        )

        cmd = RemoveMappingCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
            removed_game_frame_id="capture_A",
            removed_alignment=(5, 10, False, True, 0.75, 2.0, "nearest"),
            removed_status="edited",
        )

        cmd.execute()
        assert project.get_mapping_for_ai_frame("sprite_01.png") is None

        cmd.undo()

        # Mapping restored with all alignment properties
        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.game_frame_id == "capture_A"
        assert mapping.offset_x == 5
        assert mapping.offset_y == 10
        assert mapping.flip_h is False
        assert mapping.flip_v is True
        assert mapping.scale == 0.75
        assert mapping.sharpen == 2.0
        assert mapping.resampling == "nearest"


class TestUpdateAlignmentCommand:
    """Tests for UpdateAlignmentCommand."""

    def test_description(self, populated_controller: FrameMappingController) -> None:
        """Command has descriptive string."""
        cmd = UpdateAlignmentCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
            new_offset_x=10,
            new_offset_y=20,
            new_flip_h=True,
            new_flip_v=False,
            new_scale=0.5,
        )
        assert "sprite_01.png" in cmd.description

    def test_execute_updates_alignment(self, populated_controller: FrameMappingController) -> None:
        """Execute applies new alignment values."""
        project = populated_controller.project
        assert project is not None

        # Create a mapping first
        populated_controller._create_mapping_no_history("sprite_01.png", "capture_A")

        cmd = UpdateAlignmentCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
            new_offset_x=10,
            new_offset_y=20,
            new_flip_h=True,
            new_flip_v=False,
            new_scale=0.5,
        )

        cmd.execute()

        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.offset_x == 10
        assert mapping.offset_y == 20
        assert mapping.flip_h is True
        assert mapping.flip_v is False
        assert mapping.scale == 0.5

    def test_undo_restores_old_alignment(self, populated_controller: FrameMappingController) -> None:
        """Undo restores previous alignment values."""
        project = populated_controller.project
        assert project is not None

        # Create a mapping first
        populated_controller._create_mapping_no_history("sprite_01.png", "capture_A")

        cmd = UpdateAlignmentCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
            new_offset_x=10,
            new_offset_y=20,
            new_flip_h=True,
            new_flip_v=False,
            new_scale=0.5,
            old_offset_x=0,
            old_offset_y=0,
            old_flip_h=False,
            old_flip_v=False,
            old_scale=1.0,
            old_status="mapped",
        )

        cmd.execute()
        cmd.undo()

        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.offset_x == 0
        assert mapping.offset_y == 0
        assert mapping.flip_h is False
        assert mapping.flip_v is False
        assert mapping.scale == 1.0

    def test_undo_restores_sharpen_and_resampling(self, populated_controller: FrameMappingController) -> None:
        """Undo restores sharpen and resampling values.

        Regression test: sharpen and resampling must be preserved across undo/redo
        to avoid losing image quality settings when alignment is adjusted.
        """
        project = populated_controller.project
        assert project is not None

        # Create a mapping with specific sharpen/resampling values
        populated_controller._create_mapping_no_history("sprite_01.png", "capture_A")
        populated_controller._update_alignment_no_history(
            "sprite_01.png", 0, 0, False, False, 1.0, sharpen=2.5, resampling="nearest"
        )

        # Verify initial state
        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.sharpen == 2.5
        assert mapping.resampling == "nearest"

        # Create command that changes sharpen and resampling
        cmd = UpdateAlignmentCommand(
            controller=populated_controller,
            ai_frame_id="sprite_01.png",
            new_offset_x=10,
            new_offset_y=10,
            new_flip_h=False,
            new_flip_v=False,
            new_scale=1.0,
            new_sharpen=0.0,  # Changed
            new_resampling="lanczos",  # Changed
            old_offset_x=0,
            old_offset_y=0,
            old_flip_h=False,
            old_flip_v=False,
            old_scale=1.0,
            old_sharpen=2.5,  # Original value
            old_resampling="nearest",  # Original value
            old_status="edited",
        )

        cmd.execute()

        # Verify new values applied
        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.sharpen == 0.0
        assert mapping.resampling == "lanczos"

        cmd.undo()

        # Verify original sharpen/resampling restored
        mapping = project.get_mapping_for_ai_frame("sprite_01.png")
        assert mapping is not None
        assert mapping.sharpen == 2.5, "Sharpen should be restored after undo"
        assert mapping.resampling == "nearest", "Resampling should be restored after undo"


class TestRenameAIFrameCommand:
    """Tests for RenameAIFrameCommand."""

    def test_description_with_new_name(self, populated_controller: FrameMappingController) -> None:
        """Description shows new name when setting."""
        cmd = RenameAIFrameCommand(
            controller=populated_controller,
            frame_id="sprite_01.png",
            new_name="Walking Left",
        )
        assert "Walking Left" in cmd.description

    def test_description_when_clearing(self, populated_controller: FrameMappingController) -> None:
        """Description indicates clearing when no new name."""
        cmd = RenameAIFrameCommand(
            controller=populated_controller,
            frame_id="sprite_01.png",
            new_name=None,
        )
        assert "Clear" in cmd.description or "clear" in cmd.description.lower()

    def test_execute_renames_frame(self, populated_controller: FrameMappingController) -> None:
        """Execute sets the display name on the frame."""
        project = populated_controller.project
        assert project is not None

        cmd = RenameAIFrameCommand(
            controller=populated_controller,
            frame_id="sprite_01.png",
            new_name="Walking Left",
        )

        cmd.execute()

        frame = project.get_ai_frame_by_id("sprite_01.png")
        assert frame is not None
        assert frame.display_name == "Walking Left"

    def test_undo_restores_old_name(self, populated_controller: FrameMappingController) -> None:
        """Undo restores previous name."""
        project = populated_controller.project
        assert project is not None

        # Set initial name
        populated_controller._rename_frame_no_history("sprite_01.png", "Idle")

        cmd = RenameAIFrameCommand(
            controller=populated_controller,
            frame_id="sprite_01.png",
            new_name="Walking Left",
            old_name="Idle",
        )

        cmd.execute()
        cmd.undo()

        frame = project.get_ai_frame_by_id("sprite_01.png")
        assert frame is not None
        assert frame.display_name == "Idle"


class TestRenameCaptureCommand:
    """Tests for RenameCaptureCommand."""

    def test_execute_renames_capture(self, populated_controller: FrameMappingController) -> None:
        """Execute sets the display name on the game frame."""
        project = populated_controller.project
        assert project is not None

        cmd = RenameCaptureCommand(
            controller=populated_controller,
            game_frame_id="capture_A",
            new_name="Running Animation",
        )

        cmd.execute()

        frame = project.get_game_frame_by_id("capture_A")
        assert frame is not None
        assert frame.display_name == "Running Animation"

    def test_undo_restores_old_name(self, populated_controller: FrameMappingController) -> None:
        """Undo restores previous name."""
        project = populated_controller.project
        assert project is not None

        # Set initial name
        populated_controller._rename_capture_no_history("capture_A", "Frame 1")

        cmd = RenameCaptureCommand(
            controller=populated_controller,
            game_frame_id="capture_A",
            new_name="Running Animation",
            old_name="Frame 1",
        )

        cmd.execute()
        cmd.undo()

        frame = project.get_game_frame_by_id("capture_A")
        assert frame is not None
        assert frame.display_name == "Frame 1"


class TestToggleFrameTagCommand:
    """Tests for ToggleFrameTagCommand."""

    def test_description_when_adding(self, populated_controller: FrameMappingController) -> None:
        """Description shows Add when tag was not present."""
        cmd = ToggleFrameTagCommand(
            controller=populated_controller,
            frame_id="sprite_01.png",
            tag="keep",
            was_present=False,
        )
        assert "Add" in cmd.description

    def test_description_when_removing(self, populated_controller: FrameMappingController) -> None:
        """Description shows Remove when tag was present."""
        cmd = ToggleFrameTagCommand(
            controller=populated_controller,
            frame_id="sprite_01.png",
            tag="keep",
            was_present=True,
        )
        assert "Remove" in cmd.description

    def test_execute_toggles_tag_on(self, populated_controller: FrameMappingController) -> None:
        """Execute adds the tag when not present."""
        project = populated_controller.project
        assert project is not None

        frame = project.get_ai_frame_by_id("sprite_01.png")
        assert frame is not None
        assert "keep" not in frame.tags

        cmd = ToggleFrameTagCommand(
            controller=populated_controller,
            frame_id="sprite_01.png",
            tag="keep",
        )

        cmd.execute()

        frame = project.get_ai_frame_by_id("sprite_01.png")
        assert frame is not None
        assert "keep" in frame.tags

    def test_undo_toggles_tag_off(self, populated_controller: FrameMappingController) -> None:
        """Undo removes the tag (toggle is self-inverting)."""
        project = populated_controller.project
        assert project is not None

        cmd = ToggleFrameTagCommand(
            controller=populated_controller,
            frame_id="sprite_01.png",
            tag="keep",
        )

        cmd.execute()  # Adds tag
        cmd.undo()  # Removes tag

        frame = project.get_ai_frame_by_id("sprite_01.png")
        assert frame is not None
        assert "keep" not in frame.tags
