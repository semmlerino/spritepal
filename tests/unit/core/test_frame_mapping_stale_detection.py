"""Tests for stale entry detection logic.

Tests the pure function `detect_stale_frame_ids` from `core.services.stale_entry_logic`.
"""

import json
from pathlib import Path

import pytest

from core.frame_mapping_project import GameFrame
from core.mesen_integration.click_extractor import MesenCaptureParser
from core.services.stale_entry_logic import (
    StaleCheckResult,
    check_frame_staleness,
    detect_stale_frame_ids,
)


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


def make_get_capture(tmp_path: Path):
    """Create a get_capture function using MesenCaptureParser."""
    parser = MesenCaptureParser()
    return lambda path: parser.parse_file(path)


class TestCheckFrameStaleness:
    """Test suite for check_frame_staleness() pure function."""

    def test_skip_no_selected_ids(self, tmp_path: Path) -> None:
        """ROM-only frames (no selected_entry_ids) should be skipped."""
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(create_minimal_capture([1])))

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=capture_path,
            selected_entry_ids=[],  # ROM-only workflow
        )

        result = check_frame_staleness(game_frame, make_get_capture(tmp_path))
        assert result is None  # Skipped, no result

    def test_skip_no_capture_path(self) -> None:
        """Game frame without capture path should be skipped."""
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=None,
            selected_entry_ids=[1],
        )

        result = check_frame_staleness(game_frame, lambda _: None)  # type: ignore
        assert result is None  # Skipped, no result

    def test_stale_when_file_missing(self, tmp_path: Path) -> None:
        """Missing capture file should be marked as stale."""
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=tmp_path / "nonexistent.json",
            selected_entry_ids=[1],
        )

        result = check_frame_staleness(game_frame, make_get_capture(tmp_path))
        assert result is not None
        assert result.frame_id == "F1234"
        assert result.is_stale is True
        assert result.reason == "file_not_found"

    def test_not_stale_when_all_ids_match(self, tmp_path: Path) -> None:
        """All entry IDs present should not be stale."""
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(create_minimal_capture([1, 2])))

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000, 0x80100],
            capture_path=capture_path,
            selected_entry_ids=[1, 2],
        )

        result = check_frame_staleness(game_frame, make_get_capture(tmp_path))
        assert result is not None
        assert result.frame_id == "F1234"
        assert result.is_stale is False
        assert result.reason is None

    def test_stale_when_ids_missing(self, tmp_path: Path) -> None:
        """Missing entry IDs should be marked as stale."""
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(create_minimal_capture([3, 4])))

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000, 0x80100],
            capture_path=capture_path,
            selected_entry_ids=[1, 2],  # Not in capture
        )

        result = check_frame_staleness(game_frame, make_get_capture(tmp_path))
        assert result is not None
        assert result.is_stale is True
        assert result.reason == "missing_ids"

    def test_stale_on_parse_error(self, tmp_path: Path) -> None:
        """Invalid JSON should be marked as stale."""
        capture_path = tmp_path / "corrupt.json"
        capture_path.write_text("{ invalid json }")

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=capture_path,
            selected_entry_ids=[1],
        )

        result = check_frame_staleness(game_frame, make_get_capture(tmp_path))
        assert result is not None
        assert result.is_stale is True
        assert result.reason == "parse_error"


class TestDetectStaleFrameIds:
    """Test suite for detect_stale_frame_ids() pure function."""

    def test_empty_list_returns_empty(self) -> None:
        """Empty game frames list should return empty list."""
        result = detect_stale_frame_ids([], lambda _: None)  # type: ignore
        assert result == []

    def test_no_selected_ids_not_checked(self, tmp_path: Path) -> None:
        """ROM-only frames (no selected_entry_ids) should not appear in result."""
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(create_minimal_capture([1])))

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=capture_path,
            selected_entry_ids=[],  # ROM-only workflow
        )

        result = detect_stale_frame_ids([game_frame], make_get_capture(tmp_path))
        assert result == []

    def test_all_valid_not_in_result(self, tmp_path: Path) -> None:
        """All entry IDs match - should not be in stale list."""
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(create_minimal_capture([1, 2])))

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000, 0x80100],
            capture_path=capture_path,
            selected_entry_ids=[1, 2],
        )

        result = detect_stale_frame_ids([game_frame], make_get_capture(tmp_path))
        assert "F1234" not in result

    def test_some_stale_in_result(self, tmp_path: Path) -> None:
        """Some IDs missing should be in stale list."""
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(create_minimal_capture([3, 4])))

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000, 0x80100],
            capture_path=capture_path,
            selected_entry_ids=[1, 2],  # Not in capture
        )

        result = detect_stale_frame_ids([game_frame], make_get_capture(tmp_path))
        assert result == ["F1234"]

    def test_partial_match_is_stale(self, tmp_path: Path) -> None:
        """Partial match (some IDs exist) should still be stale."""
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(create_minimal_capture([1, 3])))

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000, 0x80100],
            capture_path=capture_path,
            selected_entry_ids=[1, 2],  # 2 is missing
        )

        result = detect_stale_frame_ids([game_frame], make_get_capture(tmp_path))
        assert result == ["F1234"]

    def test_missing_capture_file_is_stale(self, tmp_path: Path) -> None:
        """Missing capture file should be marked as stale."""
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=tmp_path / "nonexistent.json",
            selected_entry_ids=[1],
        )

        result = detect_stale_frame_ids([game_frame], make_get_capture(tmp_path))
        assert result == ["F1234"]

    def test_multiple_frames_mixed_status(self, tmp_path: Path) -> None:
        """Multiple frames with mixed stale/valid status."""
        # Create two capture files
        capture1_path = tmp_path / "capture1.json"
        capture1_path.write_text(json.dumps(create_minimal_capture([1])))

        capture2_path = tmp_path / "capture2.json"
        capture2_path.write_text(json.dumps(create_minimal_capture([99])))

        # Frame 1: valid entries
        game_frame1 = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=capture1_path,
            selected_entry_ids=[1],
        )

        # Frame 2: stale entries
        game_frame2 = GameFrame(
            id="F5678",
            rom_offsets=[0x90000],
            capture_path=capture2_path,
            selected_entry_ids=[2],  # Does NOT exist
        )

        # Frame 3: no selected_entry_ids (ROM-only)
        game_frame3 = GameFrame(
            id="F9999",
            rom_offsets=[0xA0000],
            capture_path=capture1_path,
            selected_entry_ids=[],  # Should be skipped
        )

        result = detect_stale_frame_ids(
            [game_frame1, game_frame2, game_frame3],
            make_get_capture(tmp_path),
        )
        assert result == ["F5678"]

    def test_invalid_json_is_stale(self, tmp_path: Path) -> None:
        """Invalid JSON in capture file should be marked as stale."""
        capture_path = tmp_path / "corrupt.json"
        capture_path.write_text("{ invalid json }")

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=capture_path,
            selected_entry_ids=[1],
        )

        result = detect_stale_frame_ids([game_frame], make_get_capture(tmp_path))
        assert result == ["F1234"]

    def test_no_capture_path_not_checked(self) -> None:
        """Game frame without capture path should be skipped."""
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            capture_path=None,
            selected_entry_ids=[1],
        )

        result = detect_stale_frame_ids([game_frame], lambda _: None)  # type: ignore
        assert result == []

    def test_stop_check_aborts_early(self, tmp_path: Path) -> None:
        """Stop check should abort processing."""
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(create_minimal_capture([99])))

        frames = [
            GameFrame(
                id=f"F{i}",
                rom_offsets=[0x80000],
                capture_path=capture_path,
                selected_entry_ids=[1],  # All would be stale
            )
            for i in range(10)
        ]

        # Stop after first check
        check_count = 0

        def stop_after_first() -> bool:
            nonlocal check_count
            check_count += 1
            return check_count > 1

        result = detect_stale_frame_ids(
            frames,
            make_get_capture(tmp_path),
            stop_check=stop_after_first,
        )
        # Should only have processed first frame before stop
        assert len(result) == 1
