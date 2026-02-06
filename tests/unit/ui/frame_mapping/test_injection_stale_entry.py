"""Tests for stale-entry batch accounting in InjectionCoordinator.

Tests that stale_game_frame_ids (a set of game frame IDs like {"capture_A", "capture_B"})
is correctly compared against game frame IDs looked up from mappings during batch injection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.frame_mapping_project import AIFrame, GameFrame
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.injection_coordinator import InjectionCoordinator
from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager


class TestInjectionStaleEntry:
    """Tests for stale-entry detection during batch injection."""

    @pytest.fixture
    def controller(self, tmp_path) -> FrameMappingController:
        """Create a controller with a new project."""
        controller = FrameMappingController()
        controller.new_project("Test")
        return controller

    @pytest.fixture
    def state(self) -> WorkspaceStateManager:
        """Create a state manager."""
        return WorkspaceStateManager()

    @pytest.fixture
    def coordinator(self, controller: FrameMappingController, state: WorkspaceStateManager) -> InjectionCoordinator:
        """Create an injection coordinator with dependencies."""
        coordinator = InjectionCoordinator()
        coordinator.set_controller(controller)
        coordinator.set_state(state)
        return coordinator

    def test_stale_entry_detected_for_matching_game_frame(
        self,
        controller: FrameMappingController,
        state: WorkspaceStateManager,
        coordinator: InjectionCoordinator,
        tmp_path: Path,
    ) -> None:
        """Add stale game frame ID "capture_A", mapping "sprite_01.png" -> "capture_A".

        Call handle_async_injection_finished("sprite_01.png", False, "stale").
        Verify batch_injection_failed_stale contains "sprite_01.png".
        """
        # Arrange - Create AI frames and game frame
        project = controller.project
        assert project is not None

        ai_frame = AIFrame(path=tmp_path / "sprite_01.png", index=0)
        (tmp_path / "sprite_01.png").write_bytes(b"PNG")
        ai_frame2 = AIFrame(path=tmp_path / "sprite_02.png", index=1)
        (tmp_path / "sprite_02.png").write_bytes(b"PNG")
        project.replace_ai_frames([ai_frame, ai_frame2], tmp_path)

        game_frame = GameFrame(id="capture_A", rom_offsets=[0x1000])
        project.add_game_frame(game_frame)
        controller.create_mapping("sprite_01.png", "capture_A")

        # Set up batch tracking with TWO frames (so batch doesn't complete and clear state)
        state.start_batch_injection(["sprite_01.png", "sprite_02.png"], Path("/tmp/test.sfc"))
        state.add_stale_game_frame_id("capture_A")

        # Simulate queue-time capture: set queue_time_game_frame_id to capture_A
        controller._last_queue_time_game_frame_id = "capture_A"

        # Act - Handle injection completion for first frame (success=False, stale entry detected)
        coordinator.handle_async_injection_finished("sprite_01.png", False, "stale entry")

        # Assert - Should be recorded as stale failure, not success
        # Batch is still active (sprite_02.png pending) so state hasn't been cleared
        assert "sprite_01.png" in state.batch_injection_failed_stale
        assert "sprite_01.png" not in state.batch_injection_success
        assert "sprite_01.png" not in state.batch_injection_pending
        assert "sprite_02.png" in state.batch_injection_pending  # Still pending

    def test_no_stale_entry_when_game_frame_differs(
        self,
        controller: FrameMappingController,
        state: WorkspaceStateManager,
        coordinator: InjectionCoordinator,
        tmp_path: Path,
    ) -> None:
        """Add stale game frame ID "capture_B", mapping "sprite_01.png" -> "capture_A".

        Call handler. Verify batch_injection_failed_stale is empty and batch_injection_success
        contains "sprite_01.png".
        """
        # Arrange - Create AI frames and game frames
        project = controller.project
        assert project is not None

        ai_frame = AIFrame(path=tmp_path / "sprite_01.png", index=0)
        (tmp_path / "sprite_01.png").write_bytes(b"PNG")
        ai_frame2 = AIFrame(path=tmp_path / "sprite_02.png", index=1)
        (tmp_path / "sprite_02.png").write_bytes(b"PNG")
        project.replace_ai_frames([ai_frame, ai_frame2], tmp_path)

        game_frame_a = GameFrame(id="capture_A", rom_offsets=[0x1000])
        game_frame_b = GameFrame(id="capture_B", rom_offsets=[0x2000])
        project.add_game_frame(game_frame_a)
        project.add_game_frame(game_frame_b)
        controller.create_mapping("sprite_01.png", "capture_A")

        # Set up batch tracking with TWO frames (so batch doesn't complete and clear state)
        state.start_batch_injection(["sprite_01.png", "sprite_02.png"], Path("/tmp/test.sfc"))
        state.add_stale_game_frame_id("capture_B")  # Different game frame

        # Simulate queue-time capture: set queue_time_game_frame_id to capture_A
        controller._last_queue_time_game_frame_id = "capture_A"

        # Act - Handle injection completion (success=True, no stale entry match)
        coordinator.handle_async_injection_finished("sprite_01.png", True, "ok")

        # Assert - Should be recorded as success, not stale failure
        # Batch is still active (sprite_02.png pending) so state hasn't been cleared
        assert "sprite_01.png" in state.batch_injection_success
        assert "sprite_01.png" not in state.batch_injection_failed_stale
        assert "sprite_01.png" not in state.batch_injection_pending
        assert "sprite_02.png" in state.batch_injection_pending  # Still pending

    def test_no_stale_entry_when_none(
        self,
        controller: FrameMappingController,
        state: WorkspaceStateManager,
        coordinator: InjectionCoordinator,
        tmp_path: Path,
    ) -> None:
        """stale_game_frame_ids empty. Call handler. Verify no stale entries recorded."""
        # Arrange - Create AI frames and game frame
        project = controller.project
        assert project is not None

        ai_frame = AIFrame(path=tmp_path / "sprite_01.png", index=0)
        (tmp_path / "sprite_01.png").write_bytes(b"PNG")
        ai_frame2 = AIFrame(path=tmp_path / "sprite_02.png", index=1)
        (tmp_path / "sprite_02.png").write_bytes(b"PNG")
        project.replace_ai_frames([ai_frame, ai_frame2], tmp_path)

        game_frame = GameFrame(id="capture_A", rom_offsets=[0x1000])
        project.add_game_frame(game_frame)
        controller.create_mapping("sprite_01.png", "capture_A")

        # Set up batch tracking with TWO frames (so batch doesn't complete and clear state)
        state.start_batch_injection(["sprite_01.png", "sprite_02.png"], Path("/tmp/test.sfc"))
        # stale_game_frame_ids is empty by default (cleared by start_batch_injection)

        # Simulate queue-time capture: set queue_time_game_frame_id to capture_A
        controller._last_queue_time_game_frame_id = "capture_A"

        # Act - Handle injection completion (success=True, no stale entry tracking)
        coordinator.handle_async_injection_finished("sprite_01.png", True, "ok")

        # Assert - Should be recorded as success, no stale failures
        # Batch is still active (sprite_02.png pending) so state hasn't been cleared
        assert "sprite_01.png" in state.batch_injection_success
        assert "sprite_01.png" not in state.batch_injection_failed_stale
        assert "sprite_01.png" not in state.batch_injection_pending
        assert "sprite_02.png" in state.batch_injection_pending  # Still pending

    def test_batch_injection_multiple_stale_game_frames(
        self,
        controller: FrameMappingController,
        state: WorkspaceStateManager,
        coordinator: InjectionCoordinator,
        tmp_path: Path,
    ) -> None:
        """Two AI frames mapped to different stale game frames should both be failed_stale.

        This tests the fix: previously only one game frame ID could be tracked,
        so the second frame's stale status would be misclassified.
        """
        project = controller.project
        assert project is not None

        # Create 3 AI frames (third keeps the batch alive so state isn't cleared)
        for name in ("sprite_01.png", "sprite_02.png", "sprite_03.png"):
            (tmp_path / name).write_bytes(b"PNG")
        ai_frames = [
            AIFrame(path=tmp_path / "sprite_01.png", index=0),
            AIFrame(path=tmp_path / "sprite_02.png", index=1),
            AIFrame(path=tmp_path / "sprite_03.png", index=2),
        ]
        project.replace_ai_frames(ai_frames, tmp_path)

        # Create game frames
        game_frame_a = GameFrame(id="capture_A", rom_offsets=[0x1000])
        game_frame_b = GameFrame(id="capture_B", rom_offsets=[0x2000])
        project.add_game_frame(game_frame_a)
        project.add_game_frame(game_frame_b)

        # Map each of first two AI frames to different game frames
        controller.create_mapping("sprite_01.png", "capture_A")
        controller.create_mapping("sprite_02.png", "capture_B")

        # Start batch tracking with all 3 frames (third keeps batch active)
        state.start_batch_injection(
            ["sprite_01.png", "sprite_02.png", "sprite_03.png"],
            Path("/tmp/test.sfc"),
        )

        # Both game frames are stale
        state.add_stale_game_frame_id("capture_A")
        state.add_stale_game_frame_id("capture_B")

        # Process both stale frames
        # Simulate queue-time capture for sprite_01: set queue_time_game_frame_id to capture_A
        controller._last_queue_time_game_frame_id = "capture_A"
        coordinator.handle_async_injection_finished("sprite_01.png", False, "stale entry")

        # Simulate queue-time capture for sprite_02: set queue_time_game_frame_id to capture_B
        controller._last_queue_time_game_frame_id = "capture_B"
        coordinator.handle_async_injection_finished("sprite_02.png", False, "stale entry")

        # Both should be classified as stale failures (batch still active due to sprite_03)
        assert "sprite_01.png" in state.batch_injection_failed_stale
        assert "sprite_02.png" in state.batch_injection_failed_stale
        assert len(state.batch_injection_success) == 0
        assert "sprite_03.png" in state.batch_injection_pending
