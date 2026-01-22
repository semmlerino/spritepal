"""Tests for entry ID fallback flag in frame mapping preview.

Verifies that preview returns a fallback flag when stored entry IDs
are stale, enabling the UI to show a warning to the user.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.frame_mapping_project import FrameMappingProject, GameFrame
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


class TestEntryFallbackFlag:
    """Tests for entry ID fallback flag in get_capture_result_for_game_frame."""

    def test_returns_false_when_entry_ids_match(self, tmp_path: Path, qtbot) -> None:
        """Returns used_fallback=False when stored entry IDs exist in capture.

        Scenario: Game frame has selected_entry_ids [1, 2] and capture has entries 1, 2.
        Expected: used_fallback is False (no fallback needed).
        """
        # Create capture with entries 1 and 2
        capture_data = create_test_capture(entry_ids=[1, 2])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create project with game frame storing those entry IDs
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[0x100000, 0x100100],
                selected_entry_ids=[1, 2],
            )
        )

        controller = FrameMappingController()
        controller._project = project

        result, used_fallback = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert used_fallback is False, "Should not use fallback when entry IDs match"
        assert len(result.entries) == 2

    def test_returns_true_when_entry_ids_stale(self, tmp_path: Path, qtbot) -> None:
        """Returns used_fallback=True when stored entry IDs don't exist in capture.

        Scenario: Game frame has selected_entry_ids [1, 2] but capture has entries 10, 20.
        Expected: used_fallback is True and falls back to rom_offset filtering.
        """
        # Create capture with DIFFERENT entry IDs (10, 20)
        rom_offsets = [0x100000, 0x100100]
        capture_data = create_test_capture(entry_ids=[10, 20], rom_offsets=rom_offsets)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create project with game frame storing OLD entry IDs (1, 2)
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=rom_offsets,  # Same ROM offsets
                selected_entry_ids=[1, 2],  # Stale entry IDs
            )
        )

        controller = FrameMappingController()
        controller._project = project

        result, used_fallback = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert used_fallback is True, "Should use fallback when entry IDs are stale"
        # Should still get entries via rom_offset fallback
        assert len(result.entries) == 2

    def test_emits_stale_warning_signal_on_fallback(self, tmp_path: Path, qtbot) -> None:
        """Emits stale_entries_warning signal when fallback is used.

        Scenario: Entry IDs are stale, triggering fallback.
        Expected: stale_entries_warning signal is emitted with frame_id.
        """
        # Create capture with different entry IDs than stored
        rom_offsets = [0x100000]
        capture_data = create_test_capture(entry_ids=[99], rom_offsets=rom_offsets)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F002",
                capture_path=capture_path,
                rom_offsets=rom_offsets,
                selected_entry_ids=[1],  # Stale
            )
        )

        controller = FrameMappingController()
        controller._project = project

        # Track signal emission
        signal_received: list[str] = []
        controller.stale_entries_warning.connect(lambda fid: signal_received.append(fid))

        controller.get_capture_result_for_game_frame("F002")

        assert len(signal_received) == 1
        assert signal_received[0] == "F002"

    def test_returns_false_when_no_selected_entry_ids(self, tmp_path: Path, qtbot) -> None:
        """Returns used_fallback=False when game frame has no stored selection.

        Scenario: Game frame has empty selected_entry_ids (no filtering applied).
        Expected: used_fallback is False, all entries returned.
        """
        capture_data = create_test_capture(entry_ids=[1, 2, 3])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[0x100000],
                selected_entry_ids=[],  # No selection stored
            )
        )

        controller = FrameMappingController()
        controller._project = project

        result, used_fallback = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert used_fallback is False
        # All entries should be returned when no selection filter
        assert len(result.entries) == 3

    def test_returns_none_for_missing_game_frame(self, qtbot) -> None:
        """Returns (None, False) for non-existent game frame ID."""
        project = FrameMappingProject(name="test")

        controller = FrameMappingController()
        controller._project = project

        result, used_fallback = controller.get_capture_result_for_game_frame("NONEXISTENT")

        assert result is None
        assert used_fallback is False

    def test_returns_none_when_no_project(self, qtbot) -> None:
        """Returns (None, False) when no project is loaded."""
        controller = FrameMappingController()
        # No project set

        result, used_fallback = controller.get_capture_result_for_game_frame("F001")

        assert result is None
        assert used_fallback is False
