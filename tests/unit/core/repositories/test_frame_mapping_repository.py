"""Unit tests for FrameMappingRepository.

Tests atomic saves, version detection, migration, and backward/forward compatibility.
"""

import json
from pathlib import Path

import pytest

from core.frame_mapping_project import (
    CURRENT_VERSION,
    AIFrame,
    FrameMapping,
    FrameMappingProject,
    GameFrame,
    SheetPalette,
)
from core.repositories.frame_mapping_repository import FrameMappingRepository


class TestFrameMappingRepositorySaveLoad:
    """Tests for basic save/load functionality."""

    def test_save_creates_valid_json(self, tmp_path: Path) -> None:
        """Save creates a valid JSON file."""
        project = FrameMappingProject(name="test")
        save_path = tmp_path / "test.spritepal-mapping.json"

        FrameMappingRepository.save(project, save_path)

        # Should be valid JSON
        with open(save_path) as f:
            data = json.load(f)

        assert data["name"] == "test"
        assert data["version"] == CURRENT_VERSION

    def test_save_uses_current_format(self, tmp_path: Path) -> None:
        """Save uses current format version with ai_frame_id."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("sprite.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="sprite.png", game_frame_id="G001")

        save_path = tmp_path / "test.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        with open(save_path) as f:
            data = json.load(f)

        assert data["version"] == CURRENT_VERSION
        assert len(data["mappings"]) == 1
        assert data["mappings"][0]["ai_frame_id"] == "sprite.png"
        assert "ai_frame_index" not in data["mappings"][0]

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Project survives save/load cycle."""
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()
        ai_path = ai_dir / "frame_001.png"
        ai_path.touch()

        project = FrameMappingProject(name="Test Project", ai_frames_dir=ai_dir)
        project.ai_frames.append(AIFrame(path=ai_path, index=0, width=16, height=16))
        project.game_frames.append(GameFrame(id="G001", rom_offsets=[0x1000]))
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")

        save_path = tmp_path / "project.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        loaded = FrameMappingRepository.load(save_path)

        assert loaded.name == "Test Project"
        assert len(loaded.ai_frames) == 1
        assert len(loaded.game_frames) == 1
        assert len(loaded.mappings) == 1
        assert loaded.mappings[0].ai_frame_id == "frame_001.png"

    def test_load_nonexistent_file_raises_error(self, tmp_path: Path) -> None:
        """Loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            FrameMappingRepository.load(tmp_path / "nonexistent.json")

    def test_load_invalid_json_raises_error(self, tmp_path: Path) -> None:
        """Loading invalid JSON raises JSONDecodeError."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {")

        with pytest.raises(json.JSONDecodeError):
            FrameMappingRepository.load(bad_file)

    def test_save_with_sheet_palette(self, tmp_path: Path) -> None:
        """Sheet palette survives save/load."""
        colors = [(i, i, i) for i in range(16)]
        palette = SheetPalette(colors=colors)
        project = FrameMappingProject(name="test", sheet_palette=palette)

        save_path = tmp_path / "test.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        loaded = FrameMappingRepository.load(save_path)
        assert loaded.sheet_palette is not None
        assert len(loaded.sheet_palette.colors) == 16


class TestFrameMappingRepositoryAtomicSave:
    """Tests for atomic save functionality (temp file + rename)."""

    def test_save_creates_no_temp_file_on_success(self, tmp_path: Path) -> None:
        """Temp file is cleaned up after successful save."""
        project = FrameMappingProject(name="test")
        save_path = tmp_path / "test.spritepal-mapping.json"

        FrameMappingRepository.save(project, save_path)

        # Check for leftover .tmp files
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        """Save creates parent directories if they don't exist."""
        save_path = tmp_path / "subdir" / "nested" / "test.spritepal-mapping.json"
        project = FrameMappingProject(name="test")

        FrameMappingRepository.save(project, save_path)

        assert save_path.exists()
        assert save_path.parent.exists()


class TestFrameMappingRepositoryVersionDetection:
    """Tests for version detection and validation."""

    def test_detect_version_explicit(self, tmp_path: Path) -> None:
        """Detects version from JSON data."""
        data = {"version": 3, "name": "test"}
        assert FrameMappingRepository._detect_version(data) == 3

    def test_detect_version_defaults_to_1(self, tmp_path: Path) -> None:
        """Missing version defaults to 1 (legacy files)."""
        data = {"name": "test"}
        assert FrameMappingRepository._detect_version(data) == 1

    def test_load_rejects_unsupported_version(self, tmp_path: Path) -> None:
        """Load rejects project files with unsupported versions."""
        bad_data = {
            "version": 99,  # Unsupported
            "name": "test",
            "ai_frames": [],
            "game_frames": [],
            "mappings": [],
        }

        save_path = tmp_path / "bad.spritepal-mapping.json"
        with open(save_path, "w") as f:
            json.dump(bad_data, f)

        with pytest.raises(ValueError, match="Unsupported project version"):
            FrameMappingRepository.load(save_path)


class TestRepositoryMigrations:
    """Tests for version migrations (v1 -> v2 -> v3 -> current)."""

    # V1 -> V2 migration: ai_frame_index -> ai_frame_id

    def test_load_v1_file_migrates_to_current(self, tmp_path: Path) -> None:
        """V1 project files load and migrate to current version."""
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()
        frame_path = ai_dir / "frame_001.png"
        frame_path.touch()

        # Create v1 format file
        v1_data = {
            "version": 1,
            "name": "V1 Project",
            "ai_frames_dir": "ai_frames",
            "ai_frames": [{"path": "ai_frames/frame_001.png", "index": 0, "width": 16, "height": 16}],
            "game_frames": [{"id": "G001", "rom_offsets": [0x1000]}],
            "mappings": [
                {
                    "ai_frame_index": 0,  # V1 format
                    "game_frame_id": "G001",
                    "status": "mapped",
                }
            ],
        }

        save_path = tmp_path / "v1.spritepal-mapping.json"
        with open(save_path, "w") as f:
            json.dump(v1_data, f)

        # Load and verify migration
        loaded = FrameMappingRepository.load(save_path)

        assert loaded.name == "V1 Project"
        assert len(loaded.mappings) == 1
        assert loaded.mappings[0].ai_frame_id == "frame_001.png"  # Migrated from index
        assert hasattr(loaded.mappings[0], "ai_frame_id")

    def test_v1_migration_handles_orphaned_indices(self, tmp_path: Path) -> None:
        """V1 migration handles mappings with invalid ai_frame_index."""
        # Create v1 file with invalid index (no corresponding AI frame)
        v1_data = {
            "version": 1,
            "name": "V1 Orphaned",
            "ai_frames": [],  # Empty
            "game_frames": [{"id": "G001", "rom_offsets": []}],
            "mappings": [
                {
                    "ai_frame_index": 0,  # No frame at index 0
                    "game_frame_id": "G001",
                }
            ],
        }

        save_path = tmp_path / "v1_orphaned.spritepal-mapping.json"
        with open(save_path, "w") as f:
            json.dump(v1_data, f)

        loaded = FrameMappingRepository.load(save_path)

        # Orphaned mapping should be pruned
        assert len(loaded.mappings) == 0

    # V2 -> V3 migration: adding sheet_palette

    def test_load_v2_file_adds_sheet_palette_field(self, tmp_path: Path) -> None:
        """V2 files load with sheet_palette=None."""
        v2_data = {
            "version": 2,
            "name": "V2 Project",
            "ai_frames": [],
            "game_frames": [],
            "mappings": [],
        }

        save_path = tmp_path / "v2.spritepal-mapping.json"
        with open(save_path, "w") as f:
            json.dump(v2_data, f)

        loaded = FrameMappingRepository.load(save_path)

        assert loaded.sheet_palette is None  # Default for v2

    # V3 -> V4 migration: adding display_name and tags

    def test_load_v3_file_adds_organization_fields(self, tmp_path: Path) -> None:
        """V3 files load with display_name=None and tags=[]."""
        ai_dir = tmp_path / "ai"
        ai_dir.mkdir()
        frame_path = ai_dir / "frame.png"
        frame_path.touch()

        v3_data = {
            "version": 3,
            "name": "V3 Project",
            "ai_frames_dir": "ai",
            "ai_frames": [{"path": "ai/frame.png", "index": 0, "width": 16, "height": 16}],
            "game_frames": [],
            "mappings": [],
            "sheet_palette": None,
        }

        save_path = tmp_path / "v3.spritepal-mapping.json"
        with open(save_path, "w") as f:
            json.dump(v3_data, f)

        loaded = FrameMappingRepository.load(save_path)

        assert len(loaded.ai_frames) == 1
        assert loaded.ai_frames[0].display_name is None  # Default for v3
        assert loaded.ai_frames[0].tags == frozenset()  # Default for v3


class TestFrameMappingRepositoryPathResolution:
    """Tests for relative/absolute path handling."""

    def test_save_uses_relative_paths(self, tmp_path: Path) -> None:
        """Save stores relative paths for portability."""
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()
        frame_path = ai_dir / "frame.png"
        frame_path.touch()

        project = FrameMappingProject(name="test", ai_frames_dir=ai_dir)
        project.ai_frames.append(AIFrame(path=frame_path, index=0))

        save_path = tmp_path / "project.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        with open(save_path) as f:
            data = json.load(f)

        assert data["ai_frames_dir"] == "ai_frames"
        assert data["ai_frames"][0]["path"] == "ai_frames/frame.png"

    def test_load_resolves_relative_paths_to_absolute(self, tmp_path: Path) -> None:
        """Load resolves relative paths relative to project file location."""
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()
        frame_path = ai_dir / "frame.png"
        frame_path.touch()

        data = {
            "version": CURRENT_VERSION,
            "name": "test",
            "ai_frames_dir": "ai_frames",
            "ai_frames": [{"path": "ai_frames/frame.png", "index": 0}],
            "game_frames": [],
            "mappings": [],
        }

        save_path = tmp_path / "project.spritepal-mapping.json"
        with open(save_path, "w") as f:
            json.dump(data, f)

        loaded = FrameMappingRepository.load(save_path)

        assert loaded.ai_frames_dir is not None
        assert loaded.ai_frames_dir.is_absolute()
        assert loaded.ai_frames_dir == ai_dir
        assert loaded.ai_frames[0].path.is_absolute()


class TestRepositoryErrorHandling:
    """Tests for error handling, edge cases, and forward compatibility."""

    def test_load_missing_required_field_raises_error(self, tmp_path: Path) -> None:
        """Load raises KeyError if required field is missing."""
        bad_data = {
            "version": CURRENT_VERSION,
            # Missing "name" field
            "ai_frames": [],
        }

        save_path = tmp_path / "bad.json"
        with open(save_path, "w") as f:
            json.dump(bad_data, f)

        with pytest.raises(KeyError):
            FrameMappingRepository.load(save_path)

    def test_save_preserves_all_project_state(self, tmp_path: Path) -> None:
        """Save captures all project fields."""
        ai_dir = tmp_path / "ai"
        ai_dir.mkdir()
        frame_path = ai_dir / "frame.png"
        frame_path.touch()

        project = FrameMappingProject(name="Complete Test", ai_frames_dir=ai_dir)
        project.ai_frames.append(
            AIFrame(path=frame_path, index=0, width=32, height=32, display_name="Test Frame", tags=frozenset({"keep"}))
        )
        project.game_frames.append(
            GameFrame(
                id="G001",
                rom_offsets=[0x1000, 0x2000],
                palette_index=3,
                width=32,
                height=32,
                compression_types={0x1000: "hal"},
                display_name="Game Frame 1",
            )
        )
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="frame.png", game_frame_id="G001")
        project.update_mapping_alignment(
            ai_frame_id="frame.png", offset_x=5, offset_y=-3, flip_h=True, flip_v=False, scale=0.8
        )

        colors = [(i * 16, i * 16, i * 16) for i in range(16)]
        project.sheet_palette = SheetPalette(colors=colors, color_mappings={(255, 0, 0): 1})

        save_path = tmp_path / "complete.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        loaded = FrameMappingRepository.load(save_path)

        # Verify all state
        assert loaded.name == "Complete Test"
        assert len(loaded.ai_frames) == 1
        assert loaded.ai_frames[0].display_name == "Test Frame"
        assert "keep" in loaded.ai_frames[0].tags
        assert len(loaded.game_frames) == 1
        assert loaded.game_frames[0].display_name == "Game Frame 1"
        assert loaded.game_frames[0].rom_offsets == [0x1000, 0x2000]
        assert len(loaded.mappings) == 1
        assert loaded.mappings[0].offset_x == 5
        assert loaded.mappings[0].flip_h is True
        assert loaded.mappings[0].scale == 0.8
        assert loaded.sheet_palette is not None
        assert loaded.sheet_palette.color_mappings.get((255, 0, 0)) == 1

    def test_load_preserves_unknown_top_level_fields(self, tmp_path: Path) -> None:
        """Unknown top-level fields don't cause load to fail (forward compat)."""
        data = {
            "version": CURRENT_VERSION,
            "name": "test",
            "ai_frames": [],
            "game_frames": [],
            "mappings": [],
            "future_field": "some future value",  # Unknown field
        }

        save_path = tmp_path / "future.json"
        with open(save_path, "w") as f:
            json.dump(data, f)

        # Should not raise
        loaded = FrameMappingRepository.load(save_path)
        assert loaded.name == "test"

    def test_load_project_logs_stale_entries(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Loading a project with stale entries should log a warning."""
        # Create a capture file with entry IDs 3, 4
        capture_path = tmp_path / "capture.json"
        capture_data = {
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
                for entry_id in [3, 4]
            ],
            "palettes": {},
        }
        with open(capture_path, "w") as f:
            json.dump(capture_data, f)

        # Create a project with game frame referencing entry IDs 1, 2 (stale)
        project = FrameMappingProject(name="test")
        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000, 0x80100],
            capture_path=capture_path,
            selected_entry_ids=[1, 2],  # Not in current capture - stale!
        )
        project.game_frames.append(game_frame)

        # Save the project
        save_path = tmp_path / "test.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        # Modify the capture file to have different entry IDs (already done above)
        # This simulates re-recording the capture after the project was created

        # Load the project and check for warning
        import logging

        with caplog.at_level(logging.WARNING):
            loaded = FrameMappingRepository.load(save_path)

        # Should log a warning about stale entries
        assert any("stale game frames" in record.message.lower() for record in caplog.records)
        assert any("F1234" in record.message for record in caplog.records)

        # Project should still load successfully
        assert loaded.name == "test"
        assert len(loaded.game_frames) == 1
