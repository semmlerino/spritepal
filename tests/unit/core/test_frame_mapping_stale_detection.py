"""Tests for stale entry detection in FrameMappingProject."""

import json
from pathlib import Path

import pytest

from core.frame_mapping_project import FrameMappingProject, GameFrame


def create_minimal_capture(entry_ids: list[int]) -> dict:
    """Create minimal valid capture data with specified entry IDs."""
    return {
        "frame": 1234,
        "obsel": {},
        "entries": [
            {
                "id": entry_id,
                "x": 100,
                "y": 100,
                "tile": 0,
                "width": 8,
                "height": 8,
                "palette": 0,
                "rom_offset": 0x80000 + (entry_id * 0x100),
                "tiles": [
                    {
                        "tile_index": 0,
                        "vram_addr": 0x2000,
                        "pos_x": 0,
                        "pos_y": 0,
                        "data_hex": "00" * 32,
                    }
                ],
            }
            for entry_id in entry_ids
        ],
        "palettes": {},
    }


class TestDetectStaleEntries:
    """Test suite for FrameMappingProject.detect_stale_entries()."""

    def test_detect_stale_entries_empty_project(self) -> None:
        """Empty project should return empty dict."""
        project = FrameMappingProject(name="test")
        result = project.detect_stale_entries()
        assert result == {}

    def test_detect_stale_entries_no_selected_ids(self, tmp_path: Path) -> None:
        """ROM-only frames (no selected_entry_ids) should not appear in result."""
        # Create a minimal capture file
        capture_path = tmp_path / "capture.json"
        capture_data = create_minimal_capture([1])
        capture_path.write_text(json.dumps(capture_data))

        # Create game frame with ROM offsets but no selected_entry_ids
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=capture_path,
            selected_entry_ids=[],  # ROM-only workflow
        )

        project = FrameMappingProject(name="test", game_frames=[game_frame])
        result = project.detect_stale_entries()

        # Should not check frames without selected_entry_ids
        assert result == {}

    def test_detect_stale_entries_all_valid(self, tmp_path: Path) -> None:
        """All entry IDs match - should not be marked as stale."""
        # Create capture file with entry IDs 1, 2
        capture_path = tmp_path / "capture.json"
        capture_data = create_minimal_capture([1, 2])
        capture_path.write_text(json.dumps(capture_data))

        # Game frame selects entries 1 and 2
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000, 0x80100],
            capture_path=capture_path,
            selected_entry_ids=[1, 2],  # Both exist in capture
        )

        project = FrameMappingProject(name="test", game_frames=[game_frame])
        result = project.detect_stale_entries()

        # Should not be marked as stale (not in result dict)
        assert "F1234" not in result

    def test_detect_stale_entries_some_stale(self, tmp_path: Path) -> None:
        """Some IDs missing from current capture - should be marked as stale."""
        # Create capture file with entry IDs 3, 4 (different from what was selected)
        capture_path = tmp_path / "capture.json"
        capture_data = create_minimal_capture([3, 4])
        capture_path.write_text(json.dumps(capture_data))

        # Game frame selects entries 1 and 2 (not in current capture)
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000, 0x80100],
            capture_path=capture_path,
            selected_entry_ids=[1, 2],  # Not in capture - stale!
        )

        project = FrameMappingProject(name="test", game_frames=[game_frame])
        result = project.detect_stale_entries()

        # Should be marked as stale
        assert result == {"F1234": True}

    def test_detect_stale_entries_partial_match(self, tmp_path: Path) -> None:
        """Partial match (some IDs exist) should still be marked as stale."""
        # Create capture file with entry IDs 1, 3
        capture_path = tmp_path / "capture.json"
        capture_data = create_minimal_capture([1, 3])
        capture_path.write_text(json.dumps(capture_data))

        # Game frame selects entries 1 and 2 (2 is missing)
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000, 0x80100],
            capture_path=capture_path,
            selected_entry_ids=[1, 2],  # 2 is missing - stale!
        )

        project = FrameMappingProject(name="test", game_frames=[game_frame])
        result = project.detect_stale_entries()

        # Should be marked as stale (partial match is not enough)
        assert result == {"F1234": True}

    def test_detect_stale_entries_capture_file_missing(self, tmp_path: Path) -> None:
        """Missing capture file should be handled gracefully."""
        # Create game frame with capture path that doesn't exist
        capture_path = tmp_path / "nonexistent.json"
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=capture_path,
            selected_entry_ids=[1],
        )

        project = FrameMappingProject(name="test", game_frames=[game_frame])
        result = project.detect_stale_entries()

        # Should be marked as stale (file not found)
        assert result == {"F1234": True}

    def test_detect_stale_entries_multiple_frames_mixed(self, tmp_path: Path) -> None:
        """Multiple frames with mixed stale/valid status."""
        # Create two capture files
        capture1_path = tmp_path / "capture1.json"
        capture1_data = create_minimal_capture([1])
        capture1_path.write_text(json.dumps(capture1_data))

        capture2_path = tmp_path / "capture2.json"
        capture2_data = create_minimal_capture([99])  # Different ID
        capture2_path.write_text(json.dumps(capture2_data))

        # Frame 1: valid entries
        game_frame1 = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=capture1_path,
            selected_entry_ids=[1],  # Exists in capture1
        )

        # Frame 2: stale entries
        game_frame2 = GameFrame(
            id="F5678",
            rom_offsets=[0x90000],
            capture_path=capture2_path,
            selected_entry_ids=[2],  # Does NOT exist in capture2
        )

        # Frame 3: no selected_entry_ids (ROM-only)
        game_frame3 = GameFrame(
            id="F9999",
            rom_offsets=[0xA0000],
            capture_path=capture1_path,
            selected_entry_ids=[],  # Should be skipped
        )

        project = FrameMappingProject(name="test", game_frames=[game_frame1, game_frame2, game_frame3])
        result = project.detect_stale_entries()

        # Only F5678 should be marked as stale
        assert result == {"F5678": True}

    def test_detect_stale_entries_invalid_json(self, tmp_path: Path) -> None:
        """Invalid JSON in capture file should be handled gracefully."""
        # Create corrupt capture file
        capture_path = tmp_path / "corrupt.json"
        capture_path.write_text("{ invalid json }")

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=capture_path,
            selected_entry_ids=[1],
        )

        project = FrameMappingProject(name="test", game_frames=[game_frame])
        result = project.detect_stale_entries()

        # Should be marked as stale (parse error)
        assert result == {"F1234": True}

    def test_detect_stale_entries_no_capture_path(self) -> None:
        """Game frame without capture path should be skipped."""
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=None,  # No capture path
            selected_entry_ids=[1],
        )

        project = FrameMappingProject(name="test", game_frames=[game_frame])
        result = project.detect_stale_entries()

        # Should be skipped (no capture path to check)
        assert result == {}
