"""Tests for AIFramesFacade batch operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.frame_mapping_project import AIFrame
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


@dataclass
class _MockCommand:
    """Mock command for testing."""

    description: str = "Test"
    execute_count: int = field(default=0, repr=False)
    undo_count: int = field(default=0, repr=False)

    def execute(self) -> None:
        self.execute_count += 1

    def undo(self) -> None:
        self.undo_count += 1


class TestRemoveBatchUndoStack:
    """Tests for batch AI frame removal and undo stack interaction."""

    def test_remove_batch_clears_undo_stack(self, controller: FrameMappingController, tmp_path: Path) -> None:
        """Batch removal should clear undo stack like single remove does."""
        project = controller.project
        assert project is not None

        # Create and add an AI frame
        (tmp_path / "sprite_01.png").write_bytes(b"PNG")
        ai_frame = AIFrame(path=tmp_path / "sprite_01.png", index=0)
        project.replace_ai_frames([ai_frame], tmp_path)

        # Push a command to undo stack
        controller._undo_stack.push(_MockCommand())
        assert controller._undo_stack.can_undo()

        # Batch remove the frame
        controller.remove_ai_frames(["sprite_01.png"])

        # Undo stack should be cleared
        assert not controller._undo_stack.can_undo()
