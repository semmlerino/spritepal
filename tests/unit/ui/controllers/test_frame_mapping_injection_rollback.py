"""Tests for frame mapping injection rollback mechanism.

Verifies that partial injection failures don't corrupt the ROM:
- Staging file is created before any writes
- On success: staging is atomically committed to target
- On failure: staging is deleted, original ROM unchanged
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
from core.services.rom_verification_service import ROMVerificationResult
from ui.frame_mapping.controllers.frame_mapping_controller import (
    FrameMappingController,
)


def create_test_capture(
    entry_ids: list[int],
    rom_offsets: list[int] | None = None,
) -> dict:
    """Create a minimal capture with entries having the given IDs."""
    entries = []
    if rom_offsets is None:
        rom_offsets = [0x100000 + i * 0x100 for i in range(len(entry_ids))]

    for i, entry_id in enumerate(entry_ids):
        rom_offset = rom_offsets[i] if i < len(rom_offsets) else 0x100000 + i * 0x100
        entries.append(
            {
                "id": entry_id,
                "x": 50 + i * 10,
                "y": 100,
                "tile": i,
                "width": 8,
                "height": 8,
                "palette": 7,
                "rom_offset": rom_offset,
                "tiles": [
                    {
                        "tile_index": 0,
                        "vram_addr": 0x1000 + i * 0x20,
                        "pos_x": 0,
                        "pos_y": 0,
                        "data_hex": "00" * 32,
                        "rom_offset": rom_offset,
                        "tile_index_in_block": 0,
                    }
                ],
            }
        )
    return {
        "frame": 1,
        "obsel": {},
        "entries": entries,
        "palettes": {7: [[0, 0, 0]] * 16},
    }


class TestInjectionRollback:
    """Tests for injection rollback mechanism preventing ROM corruption."""

    def test_partial_injection_failure_preserves_original_rom(self, tmp_path: Path, qtbot) -> None:
        """When injection fails mid-loop, original ROM is unchanged.

        Scenario: Inject to 3 ROM offsets, second offset fails.
        Expected: Original ROM bytes unchanged (staging was rolled back).
        """
        # Create capture with 3 different ROM offsets
        rom_offsets = [0x100000, 0x100100, 0x100200]
        capture_data = create_test_capture(
            entry_ids=[1, 2, 3],
            rom_offsets=rom_offsets,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame image
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (24, 8), (255, 0, 0, 255))
        ai_img.save(ai_frame_path)

        # Create ROM with known content
        original_content = b"\xaa" * 0x200000
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(original_content)

        # Create project
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=rom_offsets,
                selected_entry_ids=[1, 2, 3],
            )
        )
        project.mappings.append(
            FrameMapping(
                ai_frame_id="ai_frame.png",
                game_frame_id="F001",
                offset_x=0,
                offset_y=0,
            )
        )
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Track injection calls and fail on second offset
        injection_call_count = [0]

        def mock_inject(
            sprite_path,
            rom_path,
            output_path,
            sprite_offset,
            **kwargs,
        ):
            injection_call_count[0] += 1
            if sprite_offset == 0x100100:  # Fail on second offset
                return (False, "Simulated failure")
            return (True, "Success")

        # Mock verification to pass (we're testing injection rollback, not verification)
        mock_verification = ROMVerificationResult(
            total=3,
            matched_hal=0,
            matched_raw=3,
            not_found=0,
            corrections={},
        )

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
        mock_injector.inject_sprite_to_rom.side_effect = mock_inject
        controller._injection_orchestrator._rom_injector = mock_injector

        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification

        with patch(
            "core.services.injection_orchestrator.ROMVerificationService",
            return_value=mock_verifier,
        ):
            result = controller.inject_mapping("ai_frame.png", rom_path)

        # Injection should have failed
        assert result is False

        # At least one offset was attempted before failure
        assert injection_call_count[0] >= 1

        # Original ROM should be UNCHANGED (staging was rolled back)
        final_content = rom_path.read_bytes()
        assert final_content == original_content, (
            "Original ROM was modified despite injection failure. Staging rollback did not work correctly."
        )

    def test_partial_injection_cleans_staging_file(self, tmp_path: Path, qtbot) -> None:
        """Staging file is deleted after injection failure."""
        # Create minimal capture
        capture_data = create_test_capture([1], rom_offsets=[0x100000])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        ai_img.save(ai_frame_path)

        # Create ROM
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 0x200000)

        # Create project
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[0x100000],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(
            FrameMapping(
                ai_frame_id="ai_frame.png",
                game_frame_id="F001",
                offset_x=0,
                offset_y=0,
            )
        )
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Mock verification to pass
        mock_verification = ROMVerificationResult(
            total=1,
            matched_hal=0,
            matched_raw=1,
            not_found=0,
            corrections={},
        )

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
        mock_injector.inject_sprite_to_rom.return_value = (False, "Simulated failure")
        controller._injection_orchestrator._rom_injector = mock_injector

        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification

        with patch(
            "core.services.injection_orchestrator.ROMVerificationService",
            return_value=mock_verifier,
        ):
            controller.inject_mapping("ai_frame.png", rom_path)

        # No staging files should remain
        staging_files = list(tmp_path.glob("*.staging"))
        assert len(staging_files) == 0, f"Staging file(s) not cleaned up: {staging_files}"

    def test_successful_injection_commits_staging(self, tmp_path: Path, qtbot) -> None:
        """Successful injection commits staging and updates ROM."""
        # Create minimal capture
        capture_data = create_test_capture([1], rom_offsets=[0x100000])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        ai_img.save(ai_frame_path)

        # Create ROM with known content
        original_content = b"\xaa" * 0x200000
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(original_content)

        # Create project
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[0x100000],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(
            FrameMapping(
                ai_frame_id="ai_frame.png",
                game_frame_id="F001",
                offset_x=0,
                offset_y=0,
            )
        )
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Track which files are written to
        written_paths: list[str] = []

        def mock_inject(
            sprite_path,
            rom_path,
            output_path,
            sprite_offset,
            **kwargs,
        ):
            # Simulate writing to the output path
            written_paths.append(output_path)
            Path(output_path).write_bytes(b"\xbb" * 0x200000)
            return (True, "Success")

        # Mock verification to pass
        mock_verification = ROMVerificationResult(
            total=1,
            matched_hal=0,
            matched_raw=1,
            not_found=0,
            corrections={},
        )

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
        mock_injector.inject_sprite_to_rom.side_effect = mock_inject
        controller._injection_orchestrator._rom_injector = mock_injector

        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification

        with patch(
            "core.services.injection_orchestrator.ROMVerificationService",
            return_value=mock_verifier,
        ):
            result = controller.inject_mapping("ai_frame.png", rom_path)

        # Injection should succeed
        assert result is True

        # Writes should have gone to staging file (not the injection copy directly)
        assert len(written_paths) >= 1
        assert any(".staging" in p for p in written_paths), f"Expected writes to staging file, got: {written_paths}"

        # No staging files should remain after commit
        staging_files = list(tmp_path.glob("*.staging"))
        assert len(staging_files) == 0, f"Staging file(s) not cleaned up after commit: {staging_files}"

        # The injection output file should exist and contain the modified data
        injected_files = list(tmp_path.glob("*_injected_*.sfc"))
        assert len(injected_files) == 1
        assert injected_files[0].read_bytes() == b"\xbb" * 0x200000
