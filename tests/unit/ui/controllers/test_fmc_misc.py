"""Tests for miscellaneous FrameMappingController functionality.

Covers:
- AI frames loading and mapping pruning
- Batch transform operations
- Frame tag management
- Game frame compression updates
- Capture organization (display names)
- Null project handling
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
from core.types import CompressionType
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


class TestAIFramesLoadingPrunesMappings:
    """Tests for Bug #3: AI frames loading orphans mappings.

    When reloading AI frames, mappings that reference non-existent indices
    should be pruned to prevent orphaned references.
    """

    def test_load_ai_frames_prunes_orphaned_mappings(self, tmp_path: Path, qtbot) -> None:
        """Reloading AI frames with fewer frames prunes invalid mappings."""
        # Create initial AI frames directory with 5 frames
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()
        for i in range(5):
            (ai_dir / f"frame_{i:03d}.png").write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

        controller = FrameMappingController()
        controller.load_ai_frames_from_directory(ai_dir)

        # Create mappings for frames 0, 2, and 4 (using filenames as IDs)
        controller._project.game_frames.append(GameFrame(id="G1", rom_offsets=[0x1000]))
        controller._project.game_frames.append(GameFrame(id="G2", rom_offsets=[0x2000]))
        controller._project.game_frames.append(GameFrame(id="G3", rom_offsets=[0x3000]))
        controller._project.mappings.append(FrameMapping(ai_frame_id="frame_000.png", game_frame_id="G1"))
        controller._project.mappings.append(FrameMapping(ai_frame_id="frame_002.png", game_frame_id="G2"))
        controller._project.mappings.append(FrameMapping(ai_frame_id="frame_004.png", game_frame_id="G3"))
        controller._project._rebuild_indices()

        # Now reload with only 3 frames (filenames frame_000, frame_001, frame_002)
        ai_dir2 = tmp_path / "ai_frames2"
        ai_dir2.mkdir()
        for i in range(3):
            (ai_dir2 / f"frame_{i:03d}.png").write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

        controller.load_ai_frames_from_directory(ai_dir2)

        # Mapping to frame_004.png should be pruned (file no longer exists)
        # Mappings to frame_000.png and frame_002.png should remain
        assert len(controller._project.mappings) == 2
        ai_ids = {m.ai_frame_id for m in controller._project.mappings}
        assert ai_ids == {"frame_000.png", "frame_002.png"}

    def test_load_ai_frames_preserves_compatible_mappings(self, tmp_path: Path, qtbot) -> None:
        """Reloading AI frames with same or more frames preserves all mappings."""
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()
        for i in range(5):
            (ai_dir / f"frame_{i:03d}.png").write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

        controller = FrameMappingController()
        controller.load_ai_frames_from_directory(ai_dir)

        # Create mappings for frames 0 and 2 (using filenames as IDs)
        controller._project.game_frames.append(GameFrame(id="G1", rom_offsets=[0x1000]))
        controller._project.game_frames.append(GameFrame(id="G2", rom_offsets=[0x2000]))
        controller._project.mappings.append(FrameMapping(ai_frame_id="frame_000.png", game_frame_id="G1"))
        controller._project.mappings.append(FrameMapping(ai_frame_id="frame_002.png", game_frame_id="G2"))
        controller._project._rebuild_indices()

        # Reload same directory - all mappings should remain (filenames match)
        controller.load_ai_frames_from_directory(ai_dir)

        assert len(controller._project.mappings) == 2
        ai_ids = {m.ai_frame_id for m in controller._project.mappings}
        assert ai_ids == {"frame_000.png", "frame_002.png"}

    def test_game_frames_unchanged_after_ai_frames_reload(self, tmp_path: Path, qtbot) -> None:
        """Reloading AI frames should not affect game frames."""
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()
        for i in range(3):
            (ai_dir / f"frame_{i:03d}.png").write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

        controller = FrameMappingController()
        controller.load_ai_frames_from_directory(ai_dir)

        # Add game frames
        controller._project.game_frames.append(GameFrame(id="G1", rom_offsets=[0x1000]))
        controller._project.game_frames.append(GameFrame(id="G2", rom_offsets=[0x2000]))

        # Reload AI frames
        controller.load_ai_frames_from_directory(ai_dir)

        # Game frames should be unchanged
        assert len(controller._project.game_frames) == 2
        assert controller._project.game_frames[0].id == "G1"
        assert controller._project.game_frames[1].id == "G2"


class TestApplyTransformsToAllMappings:
    """Tests for apply_transforms_to_all_mappings batch operation (P0-4)."""

    def test_apply_transforms_updates_all_mappings(self, qtbot) -> None:
        """apply_transforms_to_all_mappings updates offset and scale for all mappings."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")

        # Add AI frames and game frames
        ai1 = AIFrame(path=Path("frame_001.png"), index=0)
        ai2 = AIFrame(path=Path("frame_002.png"), index=1)
        ai3 = AIFrame(path=Path("frame_003.png"), index=2)
        project.ai_frames = [ai1, ai2, ai3]
        project.game_frames = [
            GameFrame(id="G001"),
            GameFrame(id="G002"),
            GameFrame(id="G003"),
        ]
        project._rebuild_indices()

        # Create mappings
        project.create_mapping("frame_001.png", "G001")
        project.create_mapping("frame_002.png", "G002")
        project.create_mapping("frame_003.png", "G003")

        controller._project = project

        # Apply transforms to all mappings
        updated_count = controller.apply_transforms_to_all_mappings(offset_x=10, offset_y=-5, scale=0.8)

        assert updated_count == 3

        # All mappings should have new offset and scale
        for mapping in project.mappings:
            assert mapping.offset_x == 10
            assert mapping.offset_y == -5
            assert mapping.scale == 0.8
            assert mapping.status == "edited"

    def test_apply_transforms_excludes_specified_frame(self, qtbot) -> None:
        """apply_transforms_to_all_mappings respects exclude_ai_frame_id."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")

        ai1 = AIFrame(path=Path("frame_001.png"), index=0)
        ai2 = AIFrame(path=Path("frame_002.png"), index=1)
        project.ai_frames = [ai1, ai2]
        project.game_frames = [GameFrame(id="G001"), GameFrame(id="G002")]
        project._rebuild_indices()

        project.create_mapping("frame_001.png", "G001")
        project.create_mapping("frame_002.png", "G002")

        controller._project = project

        # Apply transforms excluding frame_001.png
        updated_count = controller.apply_transforms_to_all_mappings(
            offset_x=10, offset_y=-5, scale=0.8, exclude_ai_frame_id="frame_001.png"
        )

        assert updated_count == 1

        # Only frame_002.png should be updated
        m1 = project.get_mapping_for_ai_frame("frame_001.png")
        m2 = project.get_mapping_for_ai_frame("frame_002.png")
        assert m1 is not None
        assert m2 is not None
        assert m1.offset_x == 0  # Not updated
        assert m2.offset_x == 10  # Updated

    def test_apply_transforms_clamps_scale(self, qtbot) -> None:
        """apply_transforms_to_all_mappings clamps scale to 0.01-1.0."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")

        ai1 = AIFrame(path=Path("frame_001.png"), index=0)
        project.ai_frames = [ai1]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        project.create_mapping("frame_001.png", "G001")

        controller._project = project

        # Test scale below minimum (0.01)
        controller.apply_transforms_to_all_mappings(offset_x=0, offset_y=0, scale=0.005)
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.scale == 0.01  # Clamped

        # Test scale above maximum (1.0)
        controller.apply_transforms_to_all_mappings(offset_x=0, offset_y=0, scale=1.5)
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.scale == 1.0  # Clamped

    def test_apply_transforms_no_project_returns_zero(self, qtbot) -> None:
        """apply_transforms_to_all_mappings returns 0 when no project loaded."""
        controller = FrameMappingController()

        updated_count = controller.apply_transforms_to_all_mappings(offset_x=10, offset_y=-5, scale=0.8)

        assert updated_count == 0


class TestFrameTagManagement:
    """Tests for frame tag management methods (P0-4)."""

    def test_add_frame_tag_adds_tag(self, qtbot) -> None:
        """add_frame_tag adds a tag to the AI frame."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project._rebuild_indices()
        controller._project = project

        result = controller.add_frame_tag("frame_001.png", "keep")

        assert result is True
        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert "keep" in frame.tags

    def test_remove_frame_tag_removes_tag(self, qtbot) -> None:
        """remove_frame_tag removes a tag from the AI frame."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep", "wip"}))]
        project._rebuild_indices()
        controller._project = project

        result = controller.remove_frame_tag("frame_001.png", "keep")

        assert result is True
        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert "keep" not in frame.tags
        assert "wip" in frame.tags

    def test_toggle_frame_tag_toggles_tag(self, qtbot) -> None:
        """toggle_frame_tag toggles tag on/off."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project._rebuild_indices()
        controller._project = project

        # Toggle on
        controller.toggle_frame_tag("frame_001.png", "keep")
        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert "keep" in frame.tags

        # Toggle off
        controller.toggle_frame_tag("frame_001.png", "keep")
        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert "keep" not in frame.tags

    def test_get_frames_with_tag_returns_matching_frames(self, qtbot) -> None:
        """get_frames_with_tag returns all frames with the tag."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep"})),
            AIFrame(path=Path("frame_002.png"), index=1, tags=frozenset({"discard"})),
            AIFrame(path=Path("frame_003.png"), index=2, tags=frozenset({"keep", "final"})),
        ]
        project._rebuild_indices()
        controller._project = project

        keep_frames = controller.get_frames_with_tag("keep")

        assert len(keep_frames) == 2
        ids = {f.id for f in keep_frames}
        assert ids == {"frame_001.png", "frame_003.png"}

    def test_set_frame_tags_replaces_all_tags(self, qtbot) -> None:
        """set_frame_tags replaces all existing tags."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep", "wip"}))]
        project._rebuild_indices()
        controller._project = project

        result = controller.set_frame_tags("frame_001.png", frozenset({"final", "review"}))

        assert result is True
        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert frame.tags == frozenset({"final", "review"})

    def test_get_available_tags_returns_valid_tags(self, qtbot) -> None:
        """get_available_tags returns the set of valid tag names."""
        tags = FrameMappingController.get_available_tags()

        assert "keep" in tags
        assert "discard" in tags
        assert "wip" in tags
        assert "final" in tags
        assert "review" in tags


class TestUpdateGameFrameCompression:
    """Tests for update_game_frame_compression method (P0-4)."""

    def test_update_compression_changes_type(self, qtbot) -> None:
        """update_game_frame_compression changes compression type for all offsets."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames = [
            GameFrame(
                id="G001",
                rom_offsets=[0x1000, 0x2000, 0x3000],
                compression_types={0x1000: CompressionType.RAW, 0x2000: CompressionType.RAW, 0x3000: CompressionType.RAW},
            )
        ]
        project._rebuild_indices()
        controller._project = project

        result = controller.update_game_frame_compression("G001", CompressionType.HAL)

        assert result is True
        frame = project.get_game_frame_by_id("G001")
        assert frame is not None
        assert frame.compression_types == {0x1000: CompressionType.HAL, 0x2000: CompressionType.HAL, 0x3000: CompressionType.HAL}

    def test_update_compression_nonexistent_frame_returns_false(self, qtbot) -> None:
        """update_game_frame_compression returns False for nonexistent frame."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        controller._project = project

        result = controller.update_game_frame_compression("NONEXISTENT", CompressionType.HAL)

        assert result is False


class TestCaptureOrganization:
    """Tests for capture (game frame) organization methods (P0-4)."""

    def test_rename_capture_sets_display_name(self, qtbot) -> None:
        """rename_capture sets the display name for a game frame."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        controller._project = project

        result = controller.rename_capture("G001", "My Capture")

        assert result is True
        frame = project.get_game_frame_by_id("G001")
        assert frame is not None
        assert frame.display_name == "My Capture"

    def test_rename_capture_clears_display_name_with_none(self, qtbot) -> None:
        """rename_capture clears display name when given None."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames = [GameFrame(id="G001", display_name="Old Name")]
        project._rebuild_indices()
        controller._project = project

        result = controller.rename_capture("G001", None)

        assert result is True
        frame = project.get_game_frame_by_id("G001")
        assert frame is not None
        assert frame.display_name is None

    def test_get_capture_display_name_returns_name(self, qtbot) -> None:
        """get_capture_display_name returns the display name."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames = [GameFrame(id="G001", display_name="My Capture")]
        project._rebuild_indices()
        controller._project = project

        name = controller.get_capture_display_name("G001")

        assert name == "My Capture"

    def test_get_capture_display_name_returns_none_when_not_set(self, qtbot) -> None:
        """get_capture_display_name returns None when not set."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        controller._project = project

        name = controller.get_capture_display_name("G001")

        assert name is None


class TestControllerNullProjectHandling:
    """Tests for controller methods with null project (P0-4)."""

    def test_tag_methods_return_false_without_project(self, qtbot) -> None:
        """Tag methods return False when no project is loaded."""
        controller = FrameMappingController()

        assert controller.add_frame_tag("frame.png", "keep") is False
        assert controller.remove_frame_tag("frame.png", "keep") is False
        assert controller.toggle_frame_tag("frame.png", "keep") is False
        assert controller.set_frame_tags("frame.png", frozenset({"keep"})) is False
        assert controller.get_frames_with_tag("keep") == []

    def test_compression_update_emits_error_without_project(self, qtbot) -> None:
        """update_game_frame_compression emits error without project."""
        controller = FrameMappingController()
        errors: list[str] = []
        controller.error_occurred.connect(errors.append)

        result = controller.update_game_frame_compression("G001", CompressionType.HAL)

        assert result is False
        assert len(errors) == 1
        assert "No project loaded" in errors[0]

    def test_capture_rename_returns_false_without_project(self, qtbot) -> None:
        """rename_capture returns False when no project is loaded."""
        controller = FrameMappingController()

        result = controller.rename_capture("G001", "New Name")

        assert result is False
