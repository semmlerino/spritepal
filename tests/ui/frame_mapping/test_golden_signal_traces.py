"""Golden trace tests for undo command signal emissions.

These tests verify that undo commands emit the correct signals for UI synchronization.
They catch regressions where undo operations complete in the model but fail to notify
the UI, leaving it out of sync.

Regression targets:
- 246b9b35: Missing signal emissions in 7 undo commands
- cb38ae69: Selection sync broken after undo/redo
- ba10d4c0: Signal disconnect race conditions
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.frame_mapping_project import AIFrame, GameFrame
from tests.infrastructure.signal_trace_recorder import (
    SignalCollector,
    assert_signal_args,
    assert_signal_emitted,
    assert_trace_contains,
)
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


class TestCreateMappingUndoSignals:
    """Verify CreateMappingCommand.undo() emits correct signals."""

    def test_undo_emits_mapping_removed_when_no_prior_mapping(
        self, populated_controller: FrameMappingController
    ) -> None:
        """Undo of fresh mapping must emit mapping_removed.

        Regression for 246b9b35: Without this signal, AI frames pane shows
        the mapping as still linked after undo.
        """
        collector = SignalCollector()
        collector.connect_signals(populated_controller, ["mapping_created", "mapping_removed"])

        cmd = CreateMappingCommand(
            ctx=get_ctx(populated_controller),
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_A",
        )

        # Execute creates mapping
        cmd.execute()
        collector.clear()

        # Undo should emit mapping_removed
        cmd.undo()

        assert_signal_emitted(collector.trace, "mapping_removed", times=1)
        assert_signal_args(collector.trace, "mapping_removed", ("sprite_01.png", "capture_A"))

    def test_undo_emits_mapping_created_when_restoring_prior_mapping(
        self, populated_controller: FrameMappingController
    ) -> None:
        """Undo of remapping must emit mapping_created to restore prior link.

        When AI frame was already mapped to capture_A and we remap to capture_B,
        undo must emit mapping_created(ai_frame, capture_A) to restore the UI.
        """
        # Create initial mapping
        project = populated_controller.project
        assert project is not None
        project.create_mapping("sprite_01.png", "capture_A")

        collector = SignalCollector()
        collector.connect_signals(populated_controller, ["mapping_created", "mapping_removed"])

        # Command remaps to different game frame
        cmd = CreateMappingCommand(
            ctx=get_ctx(populated_controller),
            ai_frame_id="sprite_01.png",
            game_frame_id="capture_B",
            prev_ai_mapping_game_id="capture_A",  # Record prior state
        )

        cmd.execute()
        collector.clear()

        cmd.undo()

        # Should restore prior mapping via mapping_created
        assert_signal_emitted(collector.trace, "mapping_created", times=1)
        assert_signal_args(collector.trace, "mapping_created", ("sprite_01.png", "capture_A"))


class TestRemoveMappingUndoSignals:
    """Verify RemoveMappingCommand.undo() emits correct signals."""

    def test_undo_emits_mapping_created_and_alignment_updated(
        self, populated_controller: FrameMappingController
    ) -> None:
        """Undo of removal must emit both mapping_created and alignment_updated.

        Regression for cb38ae69: Without alignment_updated, the workbench canvas
        doesn't update to show the restored alignment offsets.
        """
        # Create mapping with alignment
        project = populated_controller.project
        assert project is not None
        project.create_mapping("sprite_01.png", "capture_A")
        alignment = AlignmentState(
            offset_x=5,
            offset_y=10,
            flip_h=False,
            flip_v=True,
            scale=0.75,
            sharpen=2.0,
            resampling="nearest",
        )
        populated_controller._alignment_service.apply_alignment_to_project(
            project, "sprite_01.png", alignment, set_edited=True
        )

        collector = SignalCollector()
        collector.connect_signals(populated_controller, ["mapping_created", "mapping_removed", "alignment_updated"])

        cmd = RemoveMappingCommand(
            ctx=get_ctx(populated_controller),
            ai_frame_id="sprite_01.png",
            removed_game_frame_id="capture_A",
            removed_alignment=alignment,
            removed_status="edited",
        )

        cmd.execute()
        collector.clear()

        cmd.undo()

        # Must emit BOTH signals for full UI sync
        assert_trace_contains(collector.trace, ["mapping_created", "alignment_updated"])
        assert_signal_args(collector.trace, "mapping_created", ("sprite_01.png", "capture_A"))
        assert_signal_args(collector.trace, "alignment_updated", ("sprite_01.png",))

    def test_undo_does_not_emit_when_no_prior_mapping(self, populated_controller: FrameMappingController) -> None:
        """Undo with no prior mapping to restore emits nothing.

        Edge case: if removed_game_frame_id is None, nothing to restore.
        """
        collector = SignalCollector()
        collector.connect_signals(populated_controller, ["mapping_created", "alignment_updated"])

        cmd = RemoveMappingCommand(
            ctx=get_ctx(populated_controller),
            ai_frame_id="sprite_01.png",
            removed_game_frame_id=None,  # Nothing was removed
        )

        cmd.undo()

        # No signals when nothing to restore
        assert collector.trace.count("mapping_created") == 0
        assert collector.trace.count("alignment_updated") == 0


class TestUpdateAlignmentUndoSignals:
    """Verify UpdateAlignmentCommand.undo() emits correct signals."""

    def test_undo_emits_alignment_updated(self, populated_controller: FrameMappingController) -> None:
        """Undo of alignment change must emit alignment_updated.

        Regression for 246b9b35: Without this signal, the workbench canvas
        shows stale alignment after undo.
        """
        # Create mapping
        project = populated_controller.project
        assert project is not None
        project.create_mapping("sprite_01.png", "capture_A")

        collector = SignalCollector()
        collector.connect_signals(populated_controller, ["alignment_updated"])

        old_alignment = AlignmentState(
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            scale=1.0,
            sharpen=0.0,
            resampling="lanczos",
        )
        new_alignment = AlignmentState(
            offset_x=10,
            offset_y=20,
            flip_h=True,
            flip_v=False,
            scale=0.5,
            sharpen=0.0,
            resampling="lanczos",
        )

        cmd = UpdateAlignmentCommand(
            ctx=get_ctx(populated_controller),
            ai_frame_id="sprite_01.png",
            new_alignment=new_alignment,
            old_alignment=old_alignment,
        )

        cmd.execute()
        collector.clear()

        cmd.undo()

        assert_signal_emitted(collector.trace, "alignment_updated", times=1)
        assert_signal_args(collector.trace, "alignment_updated", ("sprite_01.png",))

    def test_execute_does_not_emit_alignment_updated(self, populated_controller: FrameMappingController) -> None:
        """Execute does NOT emit alignment_updated (controller handles it).

        The command's execute() only updates the model. Signal emission
        happens in the controller's update_mapping_alignment() method.
        Commands use _no_history methods that don't emit.
        """
        project = populated_controller.project
        assert project is not None
        project.create_mapping("sprite_01.png", "capture_A")

        collector = SignalCollector()
        collector.connect_signals(populated_controller, ["alignment_updated"])

        old_alignment = AlignmentState(
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            scale=1.0,
            sharpen=0.0,
            resampling="lanczos",
        )
        new_alignment = AlignmentState(
            offset_x=10,
            offset_y=20,
            flip_h=True,
            flip_v=False,
            scale=0.5,
            sharpen=0.0,
            resampling="lanczos",
        )

        cmd = UpdateAlignmentCommand(
            ctx=get_ctx(populated_controller),
            ai_frame_id="sprite_01.png",
            new_alignment=new_alignment,
            old_alignment=old_alignment,
        )

        cmd.execute()

        # Execute uses _no_history which doesn't emit
        assert collector.trace.count("alignment_updated") == 0


class TestSignalCollectorIntegration:
    """Integration tests for the SignalCollector utility itself."""

    def test_collector_tracks_multiple_signals(self) -> None:
        """Collector can track multiple different signals."""
        mock = MagicMock()
        collector = SignalCollector()
        collector.connect_mock(mock, ["signal_a", "signal_b", "signal_c"])

        mock.signal_a.emit("arg1")
        mock.signal_b.emit("arg2", 123)
        mock.signal_a.emit("arg3")

        assert collector.trace.signal_names() == ["signal_a", "signal_b", "signal_a"]
        assert collector.trace.count("signal_a") == 2
        assert collector.trace.count("signal_b") == 1
        assert collector.trace.count("signal_c") == 0

    def test_collector_clear_resets_trace(self) -> None:
        """Clear removes all recorded events."""
        mock = MagicMock()
        collector = SignalCollector()
        collector.connect_mock(mock, ["test_signal"])

        mock.test_signal.emit()
        assert collector.trace.count("test_signal") == 1

        collector.clear()
        assert collector.trace.count("test_signal") == 0

    def test_assert_trace_contains_allows_extras(self) -> None:
        """assert_trace_contains finds subsequence, ignoring extras."""
        mock = MagicMock()
        collector = SignalCollector()
        collector.connect_mock(mock, ["a", "b", "c"])

        mock.a.emit()
        mock.b.emit()
        mock.c.emit()
        mock.a.emit()

        # Should pass: [a, c] is subsequence of [a, b, c, a]
        assert_trace_contains(collector.trace, ["a", "c"])

        # Should pass: exact match is also valid
        assert_trace_contains(collector.trace, ["a", "b", "c", "a"])

    def test_assert_trace_contains_fails_on_missing(self) -> None:
        """assert_trace_contains fails if signal not in trace."""
        mock = MagicMock()
        collector = SignalCollector()
        collector.connect_mock(mock, ["a", "b"])

        mock.a.emit()

        with pytest.raises(AssertionError, match="missing"):
            assert_trace_contains(collector.trace, ["a", "b"])
