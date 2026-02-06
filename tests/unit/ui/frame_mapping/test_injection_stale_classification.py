"""Tests for stale-failure classification using queue-time game frame ID."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.frame_mapping_project import AIFrame, GameFrame
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.injection_coordinator import InjectionCoordinator
from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager


class TestInjectionStaleClassification:
    """Tests that stale classification uses queue-time game frame ID."""

    @pytest.fixture
    def controller(self, tmp_path: Path) -> FrameMappingController:
        controller = FrameMappingController()
        controller.new_project("Test")
        return controller

    @pytest.fixture
    def state(self) -> WorkspaceStateManager:
        return WorkspaceStateManager()

    @pytest.fixture
    def coordinator(self, controller: FrameMappingController, state: WorkspaceStateManager) -> InjectionCoordinator:
        coordinator = InjectionCoordinator()
        coordinator.set_controller(controller)
        coordinator.set_state(state)
        return coordinator

    def test_stale_classification_uses_queue_time_game_frame(
        self,
        controller: FrameMappingController,
        state: WorkspaceStateManager,
        coordinator: InjectionCoordinator,
        tmp_path: Path,
    ) -> None:
        """After remap, stale classification should use queue-time game frame ID.

        Scenario:
        1. Map A→G1 (G1 is stale)
        2. Queue injection for A (captures game_frame_id=G1)
        3. Remap A→G2 (G2 is NOT stale)
        4. Injection completes - should classify as stale (G1), not non-stale (G2)
        """
        project = controller.project
        assert project is not None

        # Create AI frames (need 2 to keep batch active)
        for name in ("sprite_01.png", "sprite_02.png"):
            (tmp_path / name).write_bytes(b"PNG")
        ai_frames = [
            AIFrame(path=tmp_path / "sprite_01.png", index=0),
            AIFrame(path=tmp_path / "sprite_02.png", index=1),
        ]
        project.replace_ai_frames(ai_frames, tmp_path)

        # Create game frames
        game_frame_g1 = GameFrame(id="capture_G1", rom_offsets=[0x1000])
        game_frame_g2 = GameFrame(id="capture_G2", rom_offsets=[0x2000])
        project.add_game_frame(game_frame_g1)
        project.add_game_frame(game_frame_g2)

        # Step 1: Map sprite_01 → G1
        controller.create_mapping("sprite_01.png", "capture_G1")

        # Step 2: Simulate queue-time capture: set queue_time_game_frame_id to G1
        controller._last_queue_time_game_frame_id = "capture_G1"

        # Step 3: Remap sprite_01 → G2 (simulating what happens after injection queued)
        controller.remove_mapping("sprite_01.png")
        controller.create_mapping("sprite_01.png", "capture_G2")

        # Mark G1 as stale, G2 is NOT stale
        state.start_batch_injection(["sprite_01.png", "sprite_02.png"], Path("/tmp/test.sfc"))
        state.add_stale_game_frame_id("capture_G1")

        # Step 4: Handle injection completion
        coordinator.handle_async_injection_finished("sprite_01.png", False, "stale")

        # Should classify as stale using queue-time G1, not current mapping G2
        assert "sprite_01.png" in state.batch_injection_failed_stale
        assert "sprite_01.png" not in state.batch_injection_success
