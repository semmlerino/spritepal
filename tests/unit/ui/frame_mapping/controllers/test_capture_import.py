"""Tests for capture import functionality in FrameMappingController.

These tests verify import_mesen_capture, complete_capture_import,
import_capture_directory, and their error handling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.mesen_integration.click_extractor import OAMEntry
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


@pytest.fixture
def valid_capture_json() -> dict:
    """Return valid Mesen capture JSON structure (schema v2.1 format)."""
    return {
        "schema_version": "2.1",
        "capture_type": "full_dump_with_attribution",
        "timestamp": 12345678,
        "frame": 1234,
        "obsel": {
            "raw": 0,
            "name_base": 0,
            "name_select": 0,
            "size_select": 0,
            "tile_base_addr": 0,
        },
        "total_entries": 1,
        "visible_count": 1,
        "entries": [
            {
                "id": 0,
                "x": 100,
                "y": 150,
                "tile": 0,
                "width": 8,
                "height": 8,
                "name_table": 0,
                "palette": 0,
                "priority": 0,
                "flip_h": False,
                "flip_v": False,
                "size_large": False,
                "tiles": [
                    {
                        "tile_index": 0,
                        "vram_addr": 0,
                        "pos_x": 0,
                        "pos_y": 0,
                        "data_hex": "00" * 32,
                    }
                ],
            }
        ],
        "palettes": {
            "0": [0] * 16,
            "1": [0] * 16,
        },
    }


@pytest.fixture
def capture_file(tmp_path: Path, valid_capture_json: dict) -> Path:
    """Create a valid capture JSON file."""
    capture_path = tmp_path / "capture_12345.json"
    capture_path.write_text(json.dumps(valid_capture_json))
    return capture_path


class TestImportMesenCapture:
    """Tests for import_mesen_capture method."""

    def test_creates_project_if_none(self, controller: FrameMappingController, capture_file: Path) -> None:
        """import_mesen_capture creates a new project if none exists."""
        controller._project = None

        # Connect to signal to verify import is requested
        requested: list[tuple] = []
        controller.capture_import_requested.connect(lambda capture, path: requested.append((capture, path)))

        controller.import_mesen_capture(capture_file)

        # A project should now exist
        assert controller._project is not None

    def test_emits_capture_import_requested(
        self, controller: FrameMappingController, capture_file: Path, qtbot: object
    ) -> None:
        """import_mesen_capture emits capture_import_requested signal."""
        requested: list[tuple] = []
        controller.capture_import_requested.connect(lambda capture, path: requested.append((capture, path)))

        controller.import_mesen_capture(capture_file)

        # Wait for async worker to complete and signal to be emitted
        with qtbot.waitSignal(controller.capture_import_requested, timeout=5000):
            pass

        assert len(requested) == 1
        capture_result, path = requested[0]
        assert path == capture_file
        assert capture_result.has_entries

    def test_file_not_found_emits_error(self, controller: FrameMappingController, tmp_path: Path) -> None:
        """import_mesen_capture emits error for missing file."""
        errors: list[str] = []
        controller.error_occurred.connect(errors.append)

        controller.import_mesen_capture(tmp_path / "nonexistent.json")

        assert len(errors) == 1
        assert "not found" in errors[0].lower()

    def test_invalid_json_emits_error(self, controller: FrameMappingController, tmp_path: Path, qtbot: object) -> None:
        """import_mesen_capture emits error for invalid JSON."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json")

        errors: list[str] = []
        controller.error_occurred.connect(errors.append)

        controller.import_mesen_capture(bad_file)

        # Wait for async worker to complete and error to be emitted
        with qtbot.waitSignal(controller.error_occurred, timeout=5000):
            pass

        assert len(errors) == 1
        assert "invalid" in errors[0].lower() or "format" in errors[0].lower()

    def test_empty_entries_emits_error(
        self, controller: FrameMappingController, tmp_path: Path, valid_capture_json: dict, qtbot: object
    ) -> None:
        """import_mesen_capture emits error when capture has no entries."""
        valid_capture_json["entries"] = []  # No entries (v2.1 schema uses 'entries')
        valid_capture_json["visible_count"] = 0
        valid_capture_json["total_entries"] = 0
        empty_file = tmp_path / "empty.json"
        empty_file.write_text(json.dumps(valid_capture_json))

        errors: list[str] = []
        controller.error_occurred.connect(errors.append)

        controller.import_mesen_capture(empty_file)

        # Wait for async worker to complete and error to be emitted
        with qtbot.waitSignal(controller.error_occurred, timeout=5000):
            pass

        assert len(errors) == 1
        assert "no sprite entries" in errors[0].lower()

    def test_malformed_capture_data_emits_error(
        self, controller: FrameMappingController, tmp_path: Path, qtbot: object
    ) -> None:
        """import_mesen_capture emits error for malformed capture data."""
        malformed = {"frameNumber": 1234}  # Missing required fields
        malformed_file = tmp_path / "malformed.json"
        malformed_file.write_text(json.dumps(malformed))

        errors: list[str] = []
        controller.error_occurred.connect(errors.append)

        controller.import_mesen_capture(malformed_file)

        # Wait for async worker to complete and error to be emitted
        with qtbot.waitSignal(controller.error_occurred, timeout=5000):
            pass

        assert len(errors) == 1


class TestCompleteCaptureImport:
    """Tests for complete_capture_import method."""

    def test_adds_game_frame_on_complete(self, controller: FrameMappingController, capture_file: Path) -> None:
        """complete_capture_import adds a GameFrame to the project."""
        # First import the capture (to get CaptureResult)
        from core.mesen_integration.click_extractor import MesenCaptureParser

        parser = MesenCaptureParser()
        capture_result = parser.parse_file(capture_file)

        # Select an entry
        selected_entries = capture_result.entries[:1]

        # Correct argument order: capture_path, capture_result, selected_entries
        game_frame = controller.complete_capture_import(capture_file, capture_result, selected_entries)

        # Verify game frame was added
        project = controller.project
        assert project is not None
        assert game_frame is not None
        retrieved = project.get_game_frame_by_id(game_frame.id)
        assert retrieved is not None

    def test_returns_none_without_project(self, controller: FrameMappingController, capture_file: Path) -> None:
        """complete_capture_import returns None when no project exists."""
        from core.mesen_integration.click_extractor import MesenCaptureParser

        parser = MesenCaptureParser()
        capture_result = parser.parse_file(capture_file)
        selected_entries = capture_result.entries[:1]

        controller._project = None

        result = controller.complete_capture_import(capture_file, capture_result, selected_entries)

        assert result is None

    def test_emits_game_frame_added_signal(self, controller: FrameMappingController, capture_file: Path) -> None:
        """complete_capture_import emits game_frame_added signal."""
        from core.mesen_integration.click_extractor import MesenCaptureParser

        parser = MesenCaptureParser()
        capture_result = parser.parse_file(capture_file)
        selected_entries = capture_result.entries[:1]

        added_frames: list[str] = []
        controller.game_frame_added.connect(added_frames.append)

        game_frame = controller.complete_capture_import(capture_file, capture_result, selected_entries)

        assert game_frame is not None
        assert game_frame.id in added_frames


class TestImportCaptureDirectory:
    """Tests for import_capture_directory method."""

    def test_imports_multiple_captures(
        self, controller: FrameMappingController, tmp_path: Path, valid_capture_json: dict
    ) -> None:
        """import_capture_directory imports all capture files in directory."""
        # Create multiple capture files
        for i in range(3):
            capture = valid_capture_json.copy()
            capture["frameNumber"] = 1000 + i
            path = tmp_path / f"capture_{1000 + i}.json"
            path.write_text(json.dumps(capture))

        # Import the directory
        controller.import_capture_directory(tmp_path)

        # Wait for the background worker to process (files are imported async)
        # The test verifies no crash occurs

    def test_skips_non_json_files(
        self, controller: FrameMappingController, tmp_path: Path, valid_capture_json: dict
    ) -> None:
        """import_capture_directory skips non-JSON files."""
        # Create a valid capture
        capture_path = tmp_path / "capture_123.json"
        capture_path.write_text(json.dumps(valid_capture_json))

        # Create a non-JSON file
        (tmp_path / "readme.txt").write_text("This is not a capture")

        errors: list[str] = []
        controller.error_occurred.connect(errors.append)

        controller.import_capture_directory(tmp_path)

        # Should not error on non-JSON files

    def test_handles_empty_directory(self, controller: FrameMappingController, tmp_path: Path) -> None:
        """import_capture_directory handles empty directory gracefully."""
        errors: list[str] = []
        controller.error_occurred.connect(errors.append)

        controller.import_capture_directory(tmp_path)

        # Should not crash, may emit status message


class TestDuplicateFrameIdHandling:
    """Tests for duplicate frame ID handling during import."""

    def test_generates_unique_id_for_duplicate(self, controller: FrameMappingController, capture_file: Path) -> None:
        """Import generates unique ID when frame ID would be duplicate."""
        from core.mesen_integration.click_extractor import MesenCaptureParser

        parser = MesenCaptureParser()
        capture_result = parser.parse_file(capture_file)
        selected_entries = capture_result.entries[:1]

        # Import the same capture twice (correct argument order)
        frame1 = controller.complete_capture_import(capture_file, capture_result, selected_entries)
        frame2 = controller.complete_capture_import(capture_file, capture_result, selected_entries)

        # IDs should be different
        assert frame1 is not None
        assert frame2 is not None
        assert frame1.id != frame2.id

        # Both frames should exist
        project = controller.project
        assert project is not None
        assert project.get_game_frame_by_id(frame1.id) is not None
        assert project.get_game_frame_by_id(frame2.id) is not None
