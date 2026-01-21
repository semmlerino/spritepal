"""Tests for FrameMappingController selected_entry_ids filtering.

Verifies that get_capture_result_for_game_frame respects the stored
selected_entry_ids when returning capture results.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.frame_mapping_project import FrameMappingProject, GameFrame
from ui.frame_mapping.controllers.frame_mapping_controller import (
    FrameMappingController,
)


def create_test_capture(entry_ids: list[int]) -> dict:
    """Create a minimal capture with entries having the given IDs."""
    entries = []
    for i, entry_id in enumerate(entry_ids):
        entries.append(
            {
                "id": entry_id,
                "x": 50 + i * 10,  # Small offset to stay within [-256, 255]
                "y": 100,
                "tile": i,
                "width": 8,  # Use 8x8 sprites to match single tile
                "height": 8,
                "palette": 7,
                "tiles": [
                    {
                        "tile_index": 0,
                        "vram_addr": 0x1000,
                        "pos_x": 0,
                        "pos_y": 0,
                        "data_hex": "00" * 32,
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


class TestGetCaptureResultFiltering:
    """Tests for get_capture_result_for_game_frame entry ID filtering."""

    def test_returns_all_entries_when_no_selected_ids(self, tmp_path: Path, qtbot) -> None:
        """Without selected_entry_ids, returns all entries."""
        # Create capture file with 5 entries
        capture_data = create_test_capture([0, 1, 2, 3, 4])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with project
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[],  # Empty = no filtering
            )
        )
        controller._project = project

        # Get capture result
        result = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 5

    def test_filters_entries_by_selected_ids(self, tmp_path: Path, qtbot) -> None:
        """With selected_entry_ids, returns only matching entries."""
        # Create capture file with 5 entries (IDs 0-4)
        capture_data = create_test_capture([0, 1, 2, 3, 4])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with project - only select entries 1 and 3
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[1, 3],
            )
        )
        controller._project = project

        # Get capture result
        result = controller.get_capture_result_for_game_frame("F001")

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
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[40, 20, 10],  # Reversed subset
            )
        )
        controller._project = project

        # Get capture result - should preserve capture file order
        result = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 3
        # Order should match capture file, not selected_entry_ids order
        assert [e.id for e in result.entries] == [10, 20, 40]

    def test_returns_none_when_no_entries_match(self, tmp_path: Path, qtbot) -> None:
        """Returns None when no entries match selected IDs."""
        # Create capture file with entries
        capture_data = create_test_capture([0, 1, 2])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with non-matching IDs
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[99, 100],  # IDs not in capture
            )
        )
        controller._project = project

        # Get capture result - should return None
        result = controller.get_capture_result_for_game_frame("F001")

        assert result is None

    def test_filters_single_entry(self, tmp_path: Path, qtbot) -> None:
        """Can filter down to a single entry."""
        # Create capture file with 10 entries
        capture_data = create_test_capture(list(range(10)))
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with single selection
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[5],
            )
        )
        controller._project = project

        # Get capture result
        result = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 1
        assert result.entries[0].id == 5
