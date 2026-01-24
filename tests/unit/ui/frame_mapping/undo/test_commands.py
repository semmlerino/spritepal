"""Tests for frame mapping undo commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
from ui.frame_mapping.undo.commands import (
    CreateMappingCommand,
    RemoveMappingCommand,
    RenameAIFrameCommand,
    RenameCaptureCommand,
    ToggleFrameTagCommand,
    UpdateAlignmentCommand,
)


@pytest.fixture
def mock_controller() -> MagicMock:
    """Create a mock controller for command testing."""
    controller = MagicMock()
    return controller


class TestCreateMappingCommand:
    """Tests for CreateMappingCommand."""

    def test_description(self, mock_controller: MagicMock) -> None:
        """Command has descriptive string."""
        cmd = CreateMappingCommand(
            controller=mock_controller,
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_A",
        )
        assert "sprite_01.png" in cmd.description
        assert "capture_A" in cmd.description

    def test_execute_creates_mapping(self, mock_controller: MagicMock) -> None:
        """Execute calls controller's internal create method."""
        cmd = CreateMappingCommand(
            controller=mock_controller,
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_A",
        )

        cmd.execute()

        mock_controller._create_mapping_no_history.assert_called_once_with("sprite_01.png", "capture_A")

    def test_undo_removes_mapping(self, mock_controller: MagicMock) -> None:
        """Undo removes the created mapping."""
        cmd = CreateMappingCommand(
            controller=mock_controller,
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_A",
        )

        cmd.undo()

        mock_controller._remove_mapping_no_history.assert_called_once_with("sprite_01.png")

    def test_undo_restores_previous_ai_mapping(self, mock_controller: MagicMock) -> None:
        """Undo restores previous AI frame mapping if it existed."""
        cmd = CreateMappingCommand(
            controller=mock_controller,
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_A",
            prev_ai_mapping_game_id="old_capture",
            prev_ai_mapping_alignment=(10, 20, True, False, 0.5),
        )

        cmd.undo()

        # Should remove new mapping and restore old
        mock_controller._remove_mapping_no_history.assert_called_with("sprite_01.png")
        mock_controller._create_mapping_no_history.assert_called_with("sprite_01.png", "old_capture")
        mock_controller._update_alignment_no_history.assert_called_with("sprite_01.png", 10, 20, True, False, 0.5)


class TestRemoveMappingCommand:
    """Tests for RemoveMappingCommand."""

    def test_description(self, mock_controller: MagicMock) -> None:
        """Command has descriptive string."""
        cmd = RemoveMappingCommand(
            controller=mock_controller,
            ai_frame_id="sprite_01.png",
        )
        assert "sprite_01.png" in cmd.description

    def test_execute_removes_mapping(self, mock_controller: MagicMock) -> None:
        """Execute calls controller's internal remove method."""
        cmd = RemoveMappingCommand(
            controller=mock_controller,
            ai_frame_id="sprite_01.png",
        )

        cmd.execute()

        mock_controller._remove_mapping_no_history.assert_called_once_with("sprite_01.png")

    def test_undo_restores_mapping(self, mock_controller: MagicMock) -> None:
        """Undo restores the removed mapping with alignment."""
        cmd = RemoveMappingCommand(
            controller=mock_controller,
            ai_frame_id="sprite_01.png",
            removed_game_frame_id="capture_A",
            removed_alignment=(5, 10, False, True, 0.75),
            removed_status="edited",
        )

        cmd.undo()

        mock_controller._create_mapping_no_history.assert_called_once_with("sprite_01.png", "capture_A")
        mock_controller._update_alignment_no_history.assert_called_once_with("sprite_01.png", 5, 10, False, True, 0.75)
        mock_controller._set_mapping_status_no_history.assert_called_once_with("sprite_01.png", "edited")


class TestUpdateAlignmentCommand:
    """Tests for UpdateAlignmentCommand."""

    def test_description(self, mock_controller: MagicMock) -> None:
        """Command has descriptive string."""
        cmd = UpdateAlignmentCommand(
            controller=mock_controller,
            ai_frame_id="sprite_01.png",
            new_offset_x=10,
            new_offset_y=20,
            new_flip_h=True,
            new_flip_v=False,
            new_scale=0.5,
        )
        assert "sprite_01.png" in cmd.description

    def test_execute_updates_alignment(self, mock_controller: MagicMock) -> None:
        """Execute applies new alignment values."""
        cmd = UpdateAlignmentCommand(
            controller=mock_controller,
            ai_frame_id="sprite_01.png",
            new_offset_x=10,
            new_offset_y=20,
            new_flip_h=True,
            new_flip_v=False,
            new_scale=0.5,
        )

        cmd.execute()

        mock_controller._update_alignment_no_history.assert_called_once_with("sprite_01.png", 10, 20, True, False, 0.5)

    def test_undo_restores_old_alignment(self, mock_controller: MagicMock) -> None:
        """Undo restores previous alignment values."""
        cmd = UpdateAlignmentCommand(
            controller=mock_controller,
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

        cmd.undo()

        mock_controller._update_alignment_no_history.assert_called_once_with("sprite_01.png", 0, 0, False, False, 1.0)
        mock_controller._set_mapping_status_no_history.assert_called_once_with("sprite_01.png", "mapped")


class TestRenameAIFrameCommand:
    """Tests for RenameAIFrameCommand."""

    def test_description_with_new_name(self, mock_controller: MagicMock) -> None:
        """Description shows new name when setting."""
        cmd = RenameAIFrameCommand(
            controller=mock_controller,
            frame_id="sprite_01.png",
            new_name="Walking Left",
        )
        assert "Walking Left" in cmd.description

    def test_description_when_clearing(self, mock_controller: MagicMock) -> None:
        """Description indicates clearing when no new name."""
        cmd = RenameAIFrameCommand(
            controller=mock_controller,
            frame_id="sprite_01.png",
            new_name=None,
        )
        assert "Clear" in cmd.description or "clear" in cmd.description.lower()

    def test_execute_renames_frame(self, mock_controller: MagicMock) -> None:
        """Execute calls controller's internal rename method."""
        cmd = RenameAIFrameCommand(
            controller=mock_controller,
            frame_id="sprite_01.png",
            new_name="Walking Left",
        )

        cmd.execute()

        mock_controller._rename_frame_no_history.assert_called_once_with("sprite_01.png", "Walking Left")

    def test_undo_restores_old_name(self, mock_controller: MagicMock) -> None:
        """Undo restores previous name."""
        cmd = RenameAIFrameCommand(
            controller=mock_controller,
            frame_id="sprite_01.png",
            new_name="Walking Left",
            old_name="Idle",
        )

        cmd.undo()

        mock_controller._rename_frame_no_history.assert_called_once_with("sprite_01.png", "Idle")


class TestRenameCaptureCommand:
    """Tests for RenameCaptureCommand."""

    def test_execute_renames_capture(self, mock_controller: MagicMock) -> None:
        """Execute calls controller's internal rename method."""
        cmd = RenameCaptureCommand(
            controller=mock_controller,
            game_frame_id="capture_A",
            new_name="Running Animation",
        )

        cmd.execute()

        mock_controller._rename_capture_no_history.assert_called_once_with("capture_A", "Running Animation")

    def test_undo_restores_old_name(self, mock_controller: MagicMock) -> None:
        """Undo restores previous name."""
        cmd = RenameCaptureCommand(
            controller=mock_controller,
            game_frame_id="capture_A",
            new_name="Running Animation",
            old_name="Frame 1",
        )

        cmd.undo()

        mock_controller._rename_capture_no_history.assert_called_once_with("capture_A", "Frame 1")


class TestToggleFrameTagCommand:
    """Tests for ToggleFrameTagCommand."""

    def test_description_when_adding(self, mock_controller: MagicMock) -> None:
        """Description shows Add when tag was not present."""
        cmd = ToggleFrameTagCommand(
            controller=mock_controller,
            frame_id="sprite_01.png",
            tag="favorite",
            was_present=False,
        )
        assert "Add" in cmd.description

    def test_description_when_removing(self, mock_controller: MagicMock) -> None:
        """Description shows Remove when tag was present."""
        cmd = ToggleFrameTagCommand(
            controller=mock_controller,
            frame_id="sprite_01.png",
            tag="favorite",
            was_present=True,
        )
        assert "Remove" in cmd.description

    def test_execute_toggles_tag(self, mock_controller: MagicMock) -> None:
        """Execute calls controller's internal toggle method."""
        cmd = ToggleFrameTagCommand(
            controller=mock_controller,
            frame_id="sprite_01.png",
            tag="done",
        )

        cmd.execute()

        mock_controller._toggle_frame_tag_no_history.assert_called_once_with("sprite_01.png", "done")

    def test_undo_toggles_again(self, mock_controller: MagicMock) -> None:
        """Undo toggles tag again to reverse."""
        cmd = ToggleFrameTagCommand(
            controller=mock_controller,
            frame_id="sprite_01.png",
            tag="done",
        )

        cmd.undo()

        # Toggle is self-inverting
        mock_controller._toggle_frame_tag_no_history.assert_called_once_with("sprite_01.png", "done")
