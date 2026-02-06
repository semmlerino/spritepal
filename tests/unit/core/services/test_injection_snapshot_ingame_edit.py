"""Tests for ingame_edited_path field in injection snapshots.

Verifies that the ingame_edited_path field is correctly captured from
FrameMapping objects, stored in MappingSnapshot, and properly reconstructed
during injection from snapshot.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
from core.services.injection_orchestrator import InjectionOrchestrator
from core.services.injection_results import InjectionRequest, InjectionResult
from core.services.injection_snapshot import AIFrameSnapshot, GameFrameSnapshot, InjectionSnapshot, MappingSnapshot


class TestMappingSnapshotIngameEditedPath:
    """Tests for MappingSnapshot.ingame_edited_path field."""

    def test_mapping_snapshot_with_ingame_edited_path(self) -> None:
        """MappingSnapshot includes ingame_edited_path when provided."""
        snapshot = MappingSnapshot(
            offset_x=10,
            offset_y=20,
            flip_h=False,
            flip_v=True,
            scale=0.5,
            sharpen=1.0,
            resampling="lanczos",
            ingame_edited_path="/some/path/edited.png",
        )

        assert snapshot.ingame_edited_path == "/some/path/edited.png"

    def test_mapping_snapshot_defaults_to_none(self) -> None:
        """MappingSnapshot defaults ingame_edited_path to None."""
        snapshot = MappingSnapshot(
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            scale=1.0,
            sharpen=0.0,
            resampling="lanczos",
        )

        assert snapshot.ingame_edited_path is None


class TestInjectionSnapshotFromProject:
    """Tests for InjectionSnapshot.from_project() capturing ingame_edited_path."""

    def test_captures_ingame_edited_path_when_set(self, tmp_path: Path) -> None:
        """from_project() captures ingame_edited_path from mapping."""
        # Create a real project
        project = FrameMappingProject(name="test", ai_frames_dir=tmp_path)

        # Add a game frame
        capture_path = tmp_path / "capture.json"
        capture_path.write_text('{"entries": []}')
        game_frame = GameFrame(
            id="F00001",
            capture_path=capture_path,
            rom_offsets=[0x1000],
            compression_types={0x1000: "lz4"},
            palette_index=0,
            selected_entry_ids=[],
            width=32,
            height=32,
        )
        project.add_game_frame(game_frame)

        # Add an AI frame
        ai_path = tmp_path / "ai_frame.png"
        # Create minimal valid PNG
        img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        img.save(ai_path)
        ai_frame = AIFrame(path=ai_path, index=0)
        project.add_ai_frame(ai_frame)

        # Create mapping and set ingame_edited_path
        project.create_mapping(ai_frame.id, game_frame.id)
        mapping = project.get_mapping_for_ai_frame(ai_frame.id)
        assert mapping is not None
        mapping.ingame_edited_path = "/tmp/edited_sprite.png"

        # Snapshot the project
        snapshot = InjectionSnapshot.from_project(project, ai_frame.id)

        assert snapshot is not None
        assert snapshot.mapping.ingame_edited_path == "/tmp/edited_sprite.png"

    def test_captures_none_when_not_set(self, tmp_path: Path) -> None:
        """from_project() captures None when ingame_edited_path is not set."""
        # Create a real project
        project = FrameMappingProject(name="test", ai_frames_dir=tmp_path)

        # Add a game frame
        capture_path = tmp_path / "capture.json"
        capture_path.write_text('{"entries": []}')
        game_frame = GameFrame(
            id="F00001",
            capture_path=capture_path,
            rom_offsets=[0x1000],
            compression_types={0x1000: "lz4"},
            palette_index=0,
            selected_entry_ids=[],
            width=32,
            height=32,
        )
        project.add_game_frame(game_frame)

        # Add an AI frame
        ai_path = tmp_path / "ai_frame.png"
        # Create minimal valid PNG
        img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        img.save(ai_path)
        ai_frame = AIFrame(path=ai_path, index=0)
        project.add_ai_frame(ai_frame)

        # Create mapping without setting ingame_edited_path
        project.create_mapping(ai_frame.id, game_frame.id)

        # Snapshot the project
        snapshot = InjectionSnapshot.from_project(project, ai_frame.id)

        assert snapshot is not None
        assert snapshot.mapping.ingame_edited_path is None


class TestExecuteFromSnapshotIngameEditedPath:
    """Tests for execute_from_snapshot passing ingame_edited_path to FrameMapping."""

    def test_reconstructs_frame_mapping_with_ingame_edited_path(self, tmp_path: Path) -> None:
        """execute_from_snapshot() passes ingame_edited_path to reconstructed FrameMapping."""
        # Create snapshot with ingame_edited_path
        mapping_snapshot = MappingSnapshot(
            offset_x=5,
            offset_y=10,
            flip_h=True,
            flip_v=False,
            scale=0.75,
            sharpen=0.5,
            resampling="lanczos",
            ingame_edited_path="/tmp/edited.png",
        )

        ai_path = tmp_path / "ai.png"
        img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        img.save(ai_path)
        ai_snapshot = AIFrameSnapshot(
            id="ai_1",
            path=ai_path,
            index=0,
        )

        capture_path = tmp_path / "capture.json"
        capture_path.write_text('{"entries": []}')
        game_snapshot = GameFrameSnapshot(
            id="F00001",
            rom_offsets=(0x1000,),
            capture_path=capture_path,
            palette_index=0,
            selected_entry_ids=(),
            compression_types={0x1000: "lz4"},
            width=32,
            height=32,
        )

        snapshot = InjectionSnapshot(
            mapping=mapping_snapshot,
            ai_frame=ai_snapshot,
            game_frame=game_snapshot,
            palette=None,
        )

        # Create a valid ROM file
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM" * 1024)  # Minimal ROM

        request = InjectionRequest(
            ai_frame_id="ai_1",
            rom_path=rom_path,
        )

        orchestrator = InjectionOrchestrator()

        # Patch _prepare_images to capture the mapping argument
        captured_mapping: FrameMapping | None = None

        def mock_prepare_images(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal captured_mapping
            # The mapping is the 3rd positional arg (after self and request)
            # or a kwarg named 'mapping'
            if len(args) >= 3:
                captured_mapping = args[2]
            else:
                captured_mapping = kwargs.get("mapping")
            # Return failure to short-circuit execution
            return InjectionResult.failure("Test short-circuit")

        with patch.object(orchestrator, "_prepare_images", side_effect=mock_prepare_images):
            _result = orchestrator.execute_from_snapshot(request, snapshot)

        # Verify the method was called and we captured the mapping
        assert captured_mapping is not None
        assert isinstance(captured_mapping, FrameMapping)
        assert captured_mapping.ingame_edited_path == "/tmp/edited.png"

        # Verify other mapping fields for completeness
        assert captured_mapping.offset_x == 5
        assert captured_mapping.offset_y == 10
        assert captured_mapping.flip_h is True
        assert captured_mapping.flip_v is False
        assert captured_mapping.scale == 0.75
        assert captured_mapping.sharpen == 0.5
        assert captured_mapping.resampling == "lanczos"

    def test_reconstructs_frame_mapping_with_none_ingame_edited_path(self, tmp_path: Path) -> None:
        """execute_from_snapshot() handles None ingame_edited_path correctly."""
        # Create snapshot without ingame_edited_path (defaults to None)
        mapping_snapshot = MappingSnapshot(
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            scale=1.0,
            sharpen=0.0,
            resampling="nearest",
        )

        ai_path = tmp_path / "ai.png"
        img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        img.save(ai_path)
        ai_snapshot = AIFrameSnapshot(
            id="ai_2",
            path=ai_path,
            index=0,
        )

        capture_path = tmp_path / "capture.json"
        capture_path.write_text('{"entries": []}')
        game_snapshot = GameFrameSnapshot(
            id="F00002",
            rom_offsets=(0x2000,),
            capture_path=capture_path,
            palette_index=0,
            selected_entry_ids=(),
            compression_types={0x2000: "none"},
            width=16,
            height=16,
        )

        snapshot = InjectionSnapshot(
            mapping=mapping_snapshot,
            ai_frame=ai_snapshot,
            game_frame=game_snapshot,
            palette=None,
        )

        # Create a valid ROM file
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM" * 1024)

        request = InjectionRequest(
            ai_frame_id="ai_2",
            rom_path=rom_path,
        )

        orchestrator = InjectionOrchestrator()

        # Patch _prepare_images to capture the mapping argument
        captured_mapping: FrameMapping | None = None

        def mock_prepare_images(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal captured_mapping
            if len(args) >= 3:
                captured_mapping = args[2]
            else:
                captured_mapping = kwargs.get("mapping")
            return InjectionResult.failure("Test short-circuit")

        with patch.object(orchestrator, "_prepare_images", side_effect=mock_prepare_images):
            _result = orchestrator.execute_from_snapshot(request, snapshot)

        # Verify ingame_edited_path is None
        assert captured_mapping is not None
        assert isinstance(captured_mapping, FrameMapping)
        assert captured_mapping.ingame_edited_path is None
