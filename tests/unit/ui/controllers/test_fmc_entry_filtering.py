"""Tests for FrameMappingController entry ID filtering.

Verifies that get_capture_result_for_game_frame respects the stored
selected_entry_ids when returning capture results.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.frame_mapping_project import FrameMappingProject, GameFrame
from tests.fixtures.frame_mapping_helpers import create_test_capture
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


class TestGetCaptureResultFiltering:
    """Tests for get_capture_result_for_game_frame entry ID filtering."""

    def test_returns_all_entries_when_no_selected_ids(self, tmp_path: Path, qtbot) -> None:
        """Without selected_entry_ids, returns all entries with correct IDs."""
        # Create capture file with 5 entries
        expected_ids = [0, 1, 2, 3, 4]
        capture_data = create_test_capture(expected_ids)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with project
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[],  # Empty = no filtering
            )
        )
        controller._project = project

        # Get capture result (returns tuple)
        result, _ = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 5

        # Verify the correct entries are returned (not just count)
        returned_ids = {e.id for e in result.entries}
        assert returned_ids == set(expected_ids), (
            f"Expected entries with IDs {set(expected_ids)}, but got {returned_ids}"
        )

    def test_filters_entries_by_selected_ids(self, tmp_path: Path, qtbot) -> None:
        """With selected_entry_ids, returns only matching entries."""
        # Create capture file with 5 entries (IDs 0-4)
        capture_data = create_test_capture([0, 1, 2, 3, 4])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with project - only select entries 1 and 3
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[1, 3],
            )
        )
        controller._project = project

        # Get capture result (returns tuple)
        result, _ = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 2
        assert {e.id for e in result.entries} == {1, 3}

    def test_filters_preserves_entry_order(self, tmp_path: Path, qtbot) -> None:
        """Filtered entries preserve their original order."""
        # Create capture file with entries in specific order
        capture_data = create_test_capture([10, 20, 30, 40, 50])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with project - select in different order than stored
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[40, 20, 10],  # Reversed subset
            )
        )
        controller._project = project

        # Get capture result - should preserve capture file order (returns tuple)
        result, _ = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 3
        # Order should match capture file, not selected_entry_ids order
        assert [e.id for e in result.entries] == [10, 20, 40]

    def test_returns_none_when_no_entries_match(self, tmp_path: Path, qtbot) -> None:
        """Falls back to unfiltered capture when no entries match selected IDs."""
        # Create capture file with entries
        capture_data = create_test_capture([0, 1, 2])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with non-matching IDs
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[99, 100],  # IDs not in capture
            )
        )
        controller._project = project

        # Get capture result - should fall back to unfiltered with all entries (returns tuple)
        with qtbot.waitSignal(controller.stale_entries_warning, timeout=1000):
            result, _ = controller.get_capture_result_for_game_frame("F001")

        # Should return unfiltered capture with all 3 entries
        assert result is not None
        assert len(result.entries) == 3
        assert result.visible_count == 3

    def test_filters_single_entry(self, tmp_path: Path, qtbot) -> None:
        """Can filter down to a single entry."""
        # Create capture file with 10 entries
        capture_data = create_test_capture(list(range(10)))
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with single selection
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[5],
            )
        )
        controller._project = project

        # Get capture result (returns tuple)
        result, _ = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 1
        assert result.entries[0].id == 5


class TestInjectMappingEntryFiltering:
    """Tests that inject_mapping filters entries by selected_entry_ids, not rom_offset.

    Bug: inject_mapping at line 690 filters by rom_offset which can match wrong entries
    when multiple frames share ROM offsets. Should filter by selected_entry_ids instead.
    """

    def test_inject_mapping_uses_selected_entry_ids_not_rom_offset(self, tmp_path: Path, qtbot) -> None:
        """Injection should filter by selected_entry_ids, not rom_offset.

        Scenario: Two entries with different IDs but SAME rom_offset (shared tile).
        Entry 10 at x=0, Entry 20 at x=100 (far apart to detect if both included).
        If filtering by rom_offset, both entries are included -> wider bounding box.
        If filtering by selected_entry_ids, only entry 10 -> smaller bounding box.
        """
        from unittest.mock import MagicMock, patch

        from PIL import Image

        from core.frame_mapping_project import AIFrame, FrameMapping
        from core.services.rom_verification_service import ROMVerificationResult
        from tests.infrastructure.injection_test_helpers import (
            InjectingMockROMInjector,
            make_solid_tile_hex,
        )

        shared_offset = 0x123456
        # Entry 10 at x=0, Entry 20 at x=100 (far apart)
        # Both have 8x8 size, so if only entry 10: bbox width=8
        # If both entries: bbox would span from 0 to 108 (width=108)
        solid_tile = make_solid_tile_hex(1)  # Palette index 1 = visible pixels
        capture_data = {
            "frame": 1,
            "obsel": {},
            "entries": [
                {
                    "id": 10,
                    "x": 0,
                    "y": 0,
                    "tile": 0,
                    "width": 8,
                    "height": 8,
                    "palette": 7,
                    "rom_offset": shared_offset,
                    "tiles": [
                        {
                            "tile_index": 0,
                            "vram_addr": 0x1000,
                            "pos_x": 0,
                            "pos_y": 0,
                            "data_hex": solid_tile,
                            "rom_offset": shared_offset,
                            "tile_index_in_block": 0,
                        }
                    ],
                },
                {
                    "id": 20,
                    "x": 100,  # Far from entry 10
                    "y": 0,
                    "tile": 1,
                    "width": 8,
                    "height": 8,
                    "palette": 7,
                    "rom_offset": shared_offset,  # Same ROM offset
                    "tiles": [
                        {
                            "tile_index": 0,
                            "vram_addr": 0x1020,
                            "pos_x": 0,
                            "pos_y": 0,
                            "data_hex": solid_tile,
                            "rom_offset": shared_offset,
                            "tile_index_in_block": 0,
                        }
                    ],
                },
            ],
            "palettes": {7: [[0, 0, 0]] + [[255, 255, 255]] * 15},
        }
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame image
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        ai_img.save(ai_frame_path)

        # Create project with game frame that only selected entry 10
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[shared_offset],
                selected_entry_ids=[10],  # Only entry 10, not entry 20
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

        # Mock ROMVerificationService to return identity mapping (no correction needed)
        mock_verification = ROMVerificationResult(
            corrections={shared_offset: shared_offset},
            matched_hal=1,
            matched_raw=0,
            not_found=0,
            total=1,
        )
        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification
        mock_verifier.apply_corrections.return_value = 0

        # Use capturing mock injector
        mock_injector = InjectingMockROMInjector(tile_count=1)

        controller = FrameMappingController()
        controller._project = project
        # Replace the orchestrator's internal ROM injector with our capturing mock
        controller._injection_orchestrator._rom_injector = mock_injector

        with (
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch(
                "core.services.injection_orchestrator.ROMVerificationService",
                return_value=mock_verifier,
            ),
        ):
            # Create fake ROM files
            rom_path = tmp_path / "test.sfc"
            rom_path.write_bytes(b"\x00" * 0x200000)
            (tmp_path / "out.sfc").write_bytes(b"\x00" * 0x200000)

            controller.inject_mapping("ai_frame.png", rom_path)

        # Verify an image was injected
        assert len(mock_injector.injected_images) == 1, "Expected one injection"

        # The key assertion: if only entry 10 was included (correct), the injected
        # image should be small (8x8 or similar). If both entries were included
        # (bug), the bounding box would span x=0 to x=108, making a much wider image.
        img = mock_injector.last_injected_image
        assert img is not None
        assert img.width <= 16, (
            f"Expected narrow image for single entry (width <= 16), "
            f"but got width={img.width}. Both entries may have been included "
            f"due to filtering by rom_offset instead of selected_entry_ids."
        )
