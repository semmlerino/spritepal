"""
Frame Mapping Batch Operations Tests.

Consolidated from:
- tests/ui/test_batch_injection_performance_repro.py

Tests for batch injection operations in the frame mapping workflow.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.frame_mapping_project import AIFrame, GameFrame
from core.services.injection_results import InjectionResult, TileInjectionResult
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController

# =============================================================================
# Batch Injection Tests
# Source: tests/ui/test_batch_injection_performance_repro.py
# =============================================================================


@pytest.fixture
def mock_controller(tmp_path):
    """Create a FrameMappingController with test frames and mappings.

    Source: tests/ui/test_batch_injection_performance_repro.py::mock_controller
    """
    controller = FrameMappingController()
    controller.new_project("Test Project")

    # Create 5 dummy frames
    frames = []
    game_frames = []

    for i in range(5):
        ai_path = tmp_path / f"frame_{i}.png"
        ai_path.touch()
        ai_frame = AIFrame(path=ai_path, index=i)
        frames.append(ai_frame)

        gf_id = f"gf_{i}"
        cap_path = tmp_path / f"cap_{i}.json"
        cap_path.touch()
        game_frame = GameFrame(id=gf_id, rom_offsets=[0x1000 + i], capture_path=cap_path)
        game_frames.append(game_frame)

    # Add frames to project first, then create mappings
    controller.project.ai_frames = frames
    controller.project.game_frames = game_frames
    controller.project._rebuild_indices()

    for i in range(5):
        controller.project.create_mapping(frames[i].id, f"gf_{i}")

    return controller


class TestBatchInjectionSignalStorm:
    """Tests for batch injection signal performance.

    Source: tests/ui/test_batch_injection_performance_repro.py
    """

    def test_batch_injection_signal_storm(self, mock_controller, tmp_path):
        """
        Reproduces the issue where inject_mapping emits project_changed for every single frame,
        causing massive UI thrashing during batch operations.

        This test verifies:
        1. Signal count matches injection count (documents current behavior)
        2. Injections actually succeeded (not just signals emitted)
        3. Mapping status is updated correctly after injection
        """
        # Create a successful injection result
        success_result = InjectionResult(
            success=True,
            tile_results=(
                TileInjectionResult(
                    rom_offset=0x1000,
                    tile_count=4,
                    compression_used="HAL",
                    success=True,
                    message="Injected 4 tiles at 0x1000",
                ),
            ),
            output_rom_path=tmp_path / "out.sfc",
            messages=("Injection successful",),
            new_mapping_status="injected",
        )

        # Mock the orchestrator's execute method to return success
        with patch.object(
            mock_controller._injection_orchestrator,
            "execute",
            return_value=success_result,
        ):
            # Track signal emissions
            signal_spy = MagicMock()
            mock_controller.project_changed.connect(signal_spy)

            # Ensure ROM path exists
            rom_path = tmp_path / "dummy.sfc"
            rom_path.touch()

            # Capture initial mapping statuses
            initial_statuses = {}
            for i in range(5):
                ai_frame_id = f"frame_{i}.png"
                mapping = mock_controller.project.get_mapping_for_ai_frame(ai_frame_id)
                assert mapping is not None, f"Mapping for {ai_frame_id} should exist"
                initial_statuses[ai_frame_id] = mapping.status

            # Simulate a batch injection loop (like in Workspace._on_inject_all)
            # In the current implementation, the workspace loops and calls inject_mapping
            # Note: ai_frame_id must be the string ID (filename), not an index
            for i in range(5):
                ai_frame_id = f"frame_{i}.png"
                mock_controller.inject_mapping(ai_frame_id, rom_path, output_path=tmp_path / "out.sfc")

            # Verification 1: Each inject_mapping call should emit project_changed.
            # This test documents that the current implementation emits per-injection
            # (5 calls = 5 signals). If batch optimization is added later to reduce
            # signal storms, this assertion should be updated accordingly.
            assert signal_spy.call_count == 5, (
                f"Expected 5 project_changed signals for 5 injections, got {signal_spy.call_count}"
            )

            # Verification 2: All mappings should now have "injected" status
            # This verifies that injections actually succeeded (not just signals emitted)
            for i in range(5):
                ai_frame_id = f"frame_{i}.png"
                mapping = mock_controller.project.get_mapping_for_ai_frame(ai_frame_id)
                assert mapping is not None, f"Mapping for {ai_frame_id} should still exist"
                assert mapping.status == "injected", (
                    f"Mapping for {ai_frame_id} should be marked 'injected' after "
                    f"successful injection, but was '{mapping.status}'"
                )


class TestBatchRemoval:
    """Tests for batch removal operations."""

    def test_batch_removal_updates_project_and_signals(self, mock_controller, tmp_path):
        """Test that removing multiple frames updates project state and emits correct signal."""
        # Setup spy for batch signal
        signal_spy = MagicMock()
        mock_controller.ai_frames_removed_batch.connect(signal_spy)

        # Select first 3 frames to remove
        frames_to_remove = [f"frame_{i}.png" for i in range(3)]

        # Verify initial state
        assert len(mock_controller.project.ai_frames) == 5
        assert len(mock_controller.project.mappings) == 5

        # Perform batch removal
        removed_ids = mock_controller.remove_ai_frames(frames_to_remove)

        # Verify return value
        assert len(removed_ids) == 3
        assert set(removed_ids) == set(frames_to_remove)

        # Verify project state updated
        assert len(mock_controller.project.ai_frames) == 2
        assert len(mock_controller.project.mappings) == 2

        # Verify remaining frames are correct
        remaining_ids = {f.id for f in mock_controller.project.ai_frames}
        assert remaining_ids == {"frame_3.png", "frame_4.png"}

        # Verify signal emitted once with list of IDs
        signal_spy.assert_called_once()
        args = signal_spy.call_args[0][0]
        assert set(args) == set(frames_to_remove)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
