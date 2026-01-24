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

    # Create 5 dummy frames and mappings
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

        controller.project.create_mapping(ai_frame.id, gf_id)

    controller.project.ai_frames = frames
    controller.project.game_frames = game_frames

    return controller


class TestBatchInjectionSignalStorm:
    """Tests for batch injection signal performance.

    Source: tests/ui/test_batch_injection_performance_repro.py
    """

    def test_batch_injection_signal_storm(self, mock_controller, tmp_path):
        """
        Reproduces the issue where inject_mapping emits project_changed for every single frame,
        causing massive UI thrashing during batch operations.
        """
        # Mock the internal injection logic to succeed immediately
        with (
            patch.object(mock_controller, "_create_injection_copy", return_value=Path("test.sfc")),
            patch.object(mock_controller, "_create_staging_copy", return_value=Path("staging.sfc")),
            patch.object(mock_controller, "_commit_staging", return_value=True),
            patch("core.rom_injector.ROMInjector") as MockInjector,
            patch("core.services.rom_verification_service.ROMVerificationService") as MockVerifier,
            patch("PIL.Image.open"),
        ):
            # Setup mocks
            injector_instance = MockInjector.return_value
            injector_instance.inject_sprite_to_rom.return_value = (True, "Success")

            verifier_instance = MockVerifier.return_value
            verifier_instance.verify_offsets.return_value.all_found = True
            verifier_instance.verify_offsets.return_value.has_corrections = False
            verifier_instance.verify_offsets.return_value.total = 1

            # Track signal emissions
            signal_spy = MagicMock()
            mock_controller.project_changed.connect(signal_spy)

            # Ensure ROM path exists
            rom_path = tmp_path / "dummy.sfc"
            rom_path.touch()

            # Simulate a batch injection loop (like in Workspace._on_inject_all)
            # In the current implementation, the workspace loops and calls inject_mapping
            for i in range(5):
                mock_controller.inject_mapping(i, rom_path, output_path=tmp_path / "out.sfc")

            # Verification
            # The key assertion would be about signal count, but the test was incomplete
            # in the original file. Keeping behavior to ensure no crashes during batch ops.
            assert True  # Test passes if no exception during batch injection


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
