"""Unit tests for FrameMappingProject class operations."""

from pathlib import Path

import pytest

from core.frame_mapping_project import AIFrame, FrameMappingProject, GameFrame, SheetPalette


class TestSheetPaletteVersionHash:
    """Tests for SheetPalette.version_hash cache invalidation property."""

    def test_version_hash_changes_when_color_modified(self) -> None:
        """version_hash changes when a color is modified."""
        colors = [(0, 0, 0)] * 16
        palette = SheetPalette(colors=colors.copy())
        original_hash = palette.version_hash

        # Modify a color
        palette.colors[5] = (255, 0, 0)
        new_hash = palette.version_hash

        assert new_hash != original_hash

    def test_version_hash_same_for_equal_palettes(self) -> None:
        """Two palettes with identical content have the same version_hash."""
        colors = [(i * 16, i * 16, i * 16) for i in range(16)]
        mappings = {(100, 100, 100): 5, (200, 200, 200): 10}

        palette1 = SheetPalette(colors=colors.copy(), color_mappings=mappings.copy())
        palette2 = SheetPalette(colors=colors.copy(), color_mappings=mappings.copy())

        assert palette1.version_hash == palette2.version_hash

    def test_version_hash_changes_when_mapping_added(self) -> None:
        """version_hash changes when a color mapping is added."""
        colors = [(0, 0, 0)] * 16
        palette = SheetPalette(colors=colors)
        original_hash = palette.version_hash

        # Add a color mapping
        palette.color_mappings[(128, 128, 128)] = 3
        new_hash = palette.version_hash

        assert new_hash != original_hash

    def test_version_hash_changes_when_mapping_removed(self) -> None:
        """version_hash changes when a color mapping is removed."""
        colors = [(0, 0, 0)] * 16
        mappings = {(100, 100, 100): 5}
        palette = SheetPalette(colors=colors, color_mappings=mappings)
        original_hash = palette.version_hash

        # Remove mapping
        del palette.color_mappings[(100, 100, 100)]
        new_hash = palette.version_hash

        assert new_hash != original_hash

    def test_version_hash_differs_for_different_mapping_values(self) -> None:
        """version_hash differs when mapping index changes."""
        colors = [(0, 0, 0)] * 16
        palette1 = SheetPalette(colors=colors.copy(), color_mappings={(100, 100, 100): 5})
        palette2 = SheetPalette(colors=colors.copy(), color_mappings={(100, 100, 100): 7})

        assert palette1.version_hash != palette2.version_hash

    def test_version_hash_stable_across_repeated_calls(self) -> None:
        """version_hash returns consistent value for unchanged palette."""
        colors = [(i, i, i) for i in range(16)]
        palette = SheetPalette(colors=colors, color_mappings={(50, 50, 50): 3})

        hash1 = palette.version_hash
        hash2 = palette.version_hash
        hash3 = palette.version_hash

        assert hash1 == hash2 == hash3


class TestFrameMappingProjectOrganization:
    """Tests for FrameMappingProject frame organization methods (V4 features)."""

    def test_set_frame_display_name_success(self) -> None:
        """set_frame_display_name updates frame's display name."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project._rebuild_indices()

        result = project.set_frame_display_name("frame_001.png", "Walk Cycle 1")

        assert result is True
        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert frame.display_name == "Walk Cycle 1"

    def test_set_frame_display_name_clear(self) -> None:
        """set_frame_display_name can clear display name with None."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0, display_name="Old Name")]
        project._rebuild_indices()

        project.set_frame_display_name("frame_001.png", None)

        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert frame.display_name is None

    def test_set_frame_display_name_nonexistent(self) -> None:
        """set_frame_display_name returns False for nonexistent frame."""
        project = FrameMappingProject(name="test")

        result = project.set_frame_display_name("nonexistent.png", "Name")

        assert result is False

    def test_add_frame_tag_success(self) -> None:
        """add_frame_tag adds a tag to the frame."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project._rebuild_indices()

        result = project.add_frame_tag("frame_001.png", "keep")

        assert result is True
        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert "keep" in frame.tags

    def test_add_frame_tag_multiple(self) -> None:
        """add_frame_tag can add multiple tags."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project._rebuild_indices()

        project.add_frame_tag("frame_001.png", "keep")
        project.add_frame_tag("frame_001.png", "final")

        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert frame.tags == frozenset({"keep", "final"})

    def test_add_frame_tag_invalid(self) -> None:
        """add_frame_tag rejects invalid tags."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project._rebuild_indices()

        result = project.add_frame_tag("frame_001.png", "invalid_tag")

        assert result is False
        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert "invalid_tag" not in frame.tags

    def test_remove_frame_tag_success(self) -> None:
        """remove_frame_tag removes a tag from the frame."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep", "wip"}))]
        project._rebuild_indices()

        result = project.remove_frame_tag("frame_001.png", "keep")

        assert result is True
        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert frame.tags == frozenset({"wip"})

    def test_toggle_frame_tag_adds_when_missing(self) -> None:
        """toggle_frame_tag adds tag when not present."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project._rebuild_indices()

        project.toggle_frame_tag("frame_001.png", "keep")

        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert "keep" in frame.tags

    def test_toggle_frame_tag_removes_when_present(self) -> None:
        """toggle_frame_tag removes tag when already present."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep"}))]
        project._rebuild_indices()

        project.toggle_frame_tag("frame_001.png", "keep")

        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert "keep" not in frame.tags

    def test_get_frames_with_tag(self) -> None:
        """get_frames_with_tag returns matching frames."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep"})),
            AIFrame(path=Path("frame_002.png"), index=1, tags=frozenset({"discard"})),
            AIFrame(path=Path("frame_003.png"), index=2, tags=frozenset({"keep", "final"})),
        ]
        project._rebuild_indices()

        keep_frames = project.get_frames_with_tag("keep")

        assert len(keep_frames) == 2
        ids = {f.id for f in keep_frames}
        assert ids == {"frame_001.png", "frame_003.png"}

    def test_set_frame_tags_replaces_all(self) -> None:
        """set_frame_tags replaces all existing tags."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep", "wip"}))]
        project._rebuild_indices()

        project.set_frame_tags("frame_001.png", frozenset({"final", "review"}))

        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert frame.tags == frozenset({"final", "review"})

    def test_organization_persists_through_save_load(self, tmp_path: Path) -> None:
        """display_name and tags survive save/load cycle."""
        from core.repositories.frame_mapping_repository import FrameMappingRepository

        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(
                path=Path("frame_001.png"),
                index=0,
                display_name="Walk Cycle 1",
                tags=frozenset({"keep", "final"}),
            ),
            AIFrame(path=Path("frame_002.png"), index=1, tags=frozenset({"discard"})),
        ]
        project._rebuild_indices()

        save_path = tmp_path / "test.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        loaded = FrameMappingRepository.load(save_path)

        frame1 = loaded.get_ai_frame_by_id("frame_001.png")
        assert frame1 is not None
        assert frame1.display_name == "Walk Cycle 1"
        assert frame1.tags == frozenset({"keep", "final"})

        frame2 = loaded.get_ai_frame_by_id("frame_002.png")
        assert frame2 is not None
        assert frame2.display_name is None
        assert frame2.tags == frozenset({"discard"})


class TestFrameMappingProjectCaptureOrganization:
    """Tests for FrameMappingProject capture organization methods."""

    def test_set_capture_display_name_success(self) -> None:
        """set_capture_display_name updates game frame."""
        project = FrameMappingProject(name="test")
        project.game_frames = [GameFrame(id="F001")]

        result = project.set_capture_display_name("F001", "My Capture")
        assert result is True

        frame = project.get_game_frame_by_id("F001")
        assert frame is not None
        assert frame.display_name == "My Capture"

    def test_set_capture_display_name_clear(self) -> None:
        """set_capture_display_name can clear display name."""
        project = FrameMappingProject(name="test")
        project.game_frames = [GameFrame(id="F001", display_name="Old Name")]

        result = project.set_capture_display_name("F001", None)
        assert result is True

        frame = project.get_game_frame_by_id("F001")
        assert frame is not None
        assert frame.display_name is None

    def test_set_capture_display_name_nonexistent(self) -> None:
        """set_capture_display_name returns False for nonexistent frame."""
        project = FrameMappingProject(name="test")

        result = project.set_capture_display_name("NONEXISTENT", "Name")
        assert result is False

    def test_capture_organization_persists_through_save_load(self, tmp_path: Path) -> None:
        """Capture display names persist through save/load cycle."""
        from core.repositories.frame_mapping_repository import FrameMappingRepository

        project = FrameMappingProject(name="test")
        project.game_frames = [
            GameFrame(id="F001", display_name="Walk Cycle"),
            GameFrame(id="F002"),  # No display name
        ]

        save_path = tmp_path / "test.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        loaded = FrameMappingRepository.load(save_path)

        frame1 = loaded.get_game_frame_by_id("F001")
        assert frame1 is not None
        assert frame1.display_name == "Walk Cycle"
        assert frame1.name == "Walk Cycle"

        frame2 = loaded.get_game_frame_by_id("F002")
        assert frame2 is not None
        assert frame2.display_name is None
        assert frame2.name == "F002"


class TestFrameMappingProjectAlignment:
    """Tests for FrameMappingProject alignment update functionality."""

    def test_update_mapping_alignment_success(self) -> None:
        """update_mapping_alignment updates existing mapping."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")

        result = project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=10,
            offset_y=-5,
            flip_h=True,
            flip_v=False,
        )

        assert result is True
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.offset_x == 10
        assert mapping.offset_y == -5
        assert mapping.flip_h is True
        assert mapping.flip_v is False

    def test_update_mapping_alignment_no_mapping(self) -> None:
        """update_mapping_alignment returns False when no mapping exists."""
        project = FrameMappingProject(name="test")

        result = project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=10,
            offset_y=-5,
            flip_h=True,
            flip_v=False,
        )

        assert result is False

    def test_update_mapping_alignment_preserves_other_fields(self) -> None:
        """update_mapping_alignment preserves other mapping fields."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        mapping = project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")
        mapping.status = "edited"

        project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=5,
            offset_y=5,
            flip_h=False,
            flip_v=True,
        )

        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.game_frame_id == "G001"
        assert mapping.status == "edited"

    def test_alignment_persists_through_save_load(self, tmp_path: Path) -> None:
        """Alignment values survive save/load cycle."""
        from core.repositories.frame_mapping_repository import FrameMappingRepository

        # Create project with AI frame and game frame
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("/tmp/frame_001.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()

        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")
        project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=15,
            offset_y=-10,
            flip_h=True,
            flip_v=True,
        )

        # Save
        save_path = tmp_path / "test.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        # Load
        loaded = FrameMappingRepository.load(save_path)

        mapping = loaded.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.offset_x == 15
        assert mapping.offset_y == -10
        assert mapping.flip_h is True
        assert mapping.flip_v is True


class TestFrameMappingQuantizationOptions:
    """Tests for FrameMapping sharpen and resampling fields."""

    def test_frame_mapping_default_sharpen_resampling(self) -> None:
        """FrameMapping should have sensible defaults for new fields."""
        from core.frame_mapping_project import FrameMapping

        mapping = FrameMapping(ai_frame_id="test.png", game_frame_id="G001")

        assert mapping.sharpen == 0.0
        assert mapping.resampling == "lanczos"

    def test_frame_mapping_custom_sharpen_resampling(self) -> None:
        """FrameMapping should accept custom sharpen and resampling values."""
        from core.frame_mapping_project import FrameMapping

        mapping = FrameMapping(
            ai_frame_id="test.png",
            game_frame_id="G001",
            sharpen=2.5,
            resampling="nearest",
        )

        assert mapping.sharpen == 2.5
        assert mapping.resampling == "nearest"

    def test_frame_mapping_to_dict_includes_new_fields(self) -> None:
        """to_dict should include sharpen and resampling fields."""
        from core.frame_mapping_project import FrameMapping

        mapping = FrameMapping(
            ai_frame_id="test.png",
            game_frame_id="G001",
            sharpen=1.5,
            resampling="nearest",
        )

        data = mapping.to_dict()

        assert "sharpen" in data
        assert data["sharpen"] == 1.5
        assert "resampling" in data
        assert data["resampling"] == "nearest"

    def test_frame_mapping_from_dict_reads_new_fields(self) -> None:
        """from_dict should correctly deserialize sharpen and resampling."""
        from core.frame_mapping_project import FrameMapping

        data = {
            "ai_frame_id": "test.png",
            "game_frame_id": "G001",
            "sharpen": 3.0,
            "resampling": "nearest",
        }

        mapping = FrameMapping.from_dict(data)

        assert mapping.sharpen == 3.0
        assert mapping.resampling == "nearest"

    def test_frame_mapping_from_dict_defaults_for_old_projects(self) -> None:
        """from_dict should use defaults when fields are missing (backwards compatibility)."""
        from core.frame_mapping_project import FrameMapping

        # Simulate old project data without sharpen/resampling
        data = {
            "ai_frame_id": "test.png",
            "game_frame_id": "G001",
            "offset_x": 10,
            "offset_y": 5,
        }

        mapping = FrameMapping.from_dict(data)

        assert mapping.sharpen == 0.0
        assert mapping.resampling == "lanczos"
        # Verify other fields still work
        assert mapping.offset_x == 10
        assert mapping.offset_y == 5

    def test_update_mapping_alignment_with_sharpen_resampling(self) -> None:
        """update_mapping_alignment should update sharpen and resampling."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")

        result = project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            scale=0.5,
            sharpen=2.0,
            resampling="nearest",
        )

        assert result is True
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.sharpen == 2.0
        assert mapping.resampling == "nearest"

    def test_sharpen_resampling_persist_through_save_load(self, tmp_path: Path) -> None:
        """Sharpen and resampling values survive save/load cycle."""
        from core.repositories.frame_mapping_repository import FrameMappingRepository

        # Create project with AI frame and game frame
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("/tmp/frame_001.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()

        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")
        project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            scale=1.0,
            sharpen=2.5,
            resampling="nearest",
        )

        # Save
        save_path = tmp_path / "test.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        # Load
        loaded = FrameMappingRepository.load(save_path)

        mapping = loaded.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.sharpen == 2.5
        assert mapping.resampling == "nearest"

    def test_sharpen_clamped_to_valid_range(self) -> None:
        """update_mapping_alignment should clamp sharpen to 0.0-4.0."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")

        # Test negative clamps to 0
        project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            sharpen=-1.0,
        )
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.sharpen == 0.0

        # Test > 4.0 clamps to 4.0
        project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            sharpen=10.0,
        )
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping.sharpen == 4.0

    def test_resampling_validated(self) -> None:
        """update_mapping_alignment should validate resampling value."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")

        # Invalid resampling should default to lanczos
        project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            resampling="invalid_value",
        )
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.resampling == "lanczos"

    def test_scale_below_10_percent_persists(self) -> None:
        """Verify scale values below 10% are not clamped to 0.1.

        Bug fix: UI allows 0.01x-1.0x but model was clamping to 0.1x-1.0x,
        causing slider snap-back behavior when dragging below 10%.
        """
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")

        # Set scale to 5% (below the old 10% minimum)
        project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            scale=0.05,
        )
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.scale == 0.05  # Should be 5%, not clamped to 10%

    def test_scale_clamped_to_valid_range(self) -> None:
        """update_mapping_alignment should clamp scale to 0.01-1.0."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")

        # Test below minimum clamps to 0.01
        project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            scale=0.001,
        )
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.scale == 0.01

        # Test above maximum clamps to 1.0
        project.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=0,
            offset_y=0,
            flip_h=False,
            flip_v=False,
            scale=2.0,
        )
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.scale == 1.0


class TestFrameMappingProjectStableIDs:
    """Tests for stable AI frame ID feature (Issue #1 fix)."""

    def test_mapping_uses_ai_frame_id(self) -> None:
        """Mappings use stable ai_frame_id, not position-dependent index."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("my_sprite.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="my_sprite.png", game_frame_id="G001")

        mapping = project.get_mapping_for_ai_frame("my_sprite.png")
        assert mapping is not None
        assert mapping.ai_frame_id == "my_sprite.png"

    def test_mapping_survives_frame_reorder(self, tmp_path: Path) -> None:
        """Mappings survive AI frame reload/reorder."""
        import json

        from core.repositories.frame_mapping_repository import FrameMappingRepository

        # Create project with AI frames in order A, B, C and a game frame
        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("/tmp/a.png"), index=0),
            AIFrame(path=Path("/tmp/b.png"), index=1),
            AIFrame(path=Path("/tmp/c.png"), index=2),
        ]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()

        # Create mapping for "b.png" at index 1
        project.create_mapping(ai_frame_id="b.png", game_frame_id="G001")

        # Save
        save_path = tmp_path / "test.spritepal-mapping.json"
        FrameMappingRepository.save(project, save_path)

        # Modify saved project to simulate different frame order on load
        # (Normally this would happen because files on disk got renamed/reordered)
        with open(save_path) as f:
            data = json.load(f)

        # Change AI frame order to C, A, B (index of "b.png" is now 2)
        data["ai_frames"] = [
            {"path": "/tmp/c.png", "index": 0, "width": 0, "height": 0},
            {"path": "/tmp/a.png", "index": 1, "width": 0, "height": 0},
            {"path": "/tmp/b.png", "index": 2, "width": 0, "height": 0},
        ]
        with open(save_path, "w") as f:
            json.dump(data, f)

        # Load
        loaded = FrameMappingRepository.load(save_path)

        # Mapping should still reference "b.png" by ID, not index
        mapping = loaded.get_mapping_for_ai_frame("b.png")
        assert mapping is not None
        assert mapping.ai_frame_id == "b.png"
        assert mapping.game_frame_id == "G001"

    def test_v1_project_migrates_to_v2(self, tmp_path: Path) -> None:
        """V1 projects with ai_frame_index are migrated to V2 on load."""
        import json

        from core.repositories.frame_mapping_repository import FrameMappingRepository

        # Create a V1 project file manually
        v1_data = {
            "version": 1,
            "name": "legacy_project",
            "ai_frames_dir": None,
            "ai_frames": [
                {"path": "/tmp/frame_001.png", "index": 0, "width": 32, "height": 32},
                {"path": "/tmp/frame_002.png", "index": 1, "width": 32, "height": 32},
            ],
            "game_frames": [
                {"id": "G001", "rom_offsets": [], "capture_path": None},
            ],
            "mappings": [
                {
                    "ai_frame_index": 1,  # V1 format - should migrate to ai_frame_id
                    "game_frame_id": "G001",
                    "status": "mapped",
                    "offset_x": 5,
                    "offset_y": -3,
                    "flip_h": True,
                    "flip_v": False,
                    "scale": 1.0,
                }
            ],
        }

        save_path = tmp_path / "legacy.spritepal-mapping.json"
        with open(save_path, "w") as f:
            json.dump(v1_data, f)

        # Load - should migrate
        project = FrameMappingRepository.load(save_path)

        # Mapping should now use ai_frame_id
        assert len(project.mappings) == 1
        mapping = project.mappings[0]
        assert mapping.ai_frame_id == "frame_002.png"  # Migrated from index 1
        assert mapping.offset_x == 5
        assert mapping.offset_y == -3
        assert mapping.flip_h is True


class TestFrameMappingProjectPerformance:
    """Tests for O(1) lookup optimization (Issue #5 fix)."""

    def test_mapping_lookup_is_fast(self) -> None:
        """Mapping lookup uses O(1) index - verified with timing."""
        import time

        project = FrameMappingProject(name="test")

        # Create many frames first
        num_items = 100
        for i in range(num_items):
            project.ai_frames.append(AIFrame(path=Path(f"frame_{i:04d}.png"), index=i))
            project.game_frames.append(GameFrame(id=f"G{i:04d}"))
        project._rebuild_indices()

        # Create many mappings
        for i in range(num_items):
            project.create_mapping(ai_frame_id=f"frame_{i:04d}.png", game_frame_id=f"G{i:04d}")

        # Basic correctness verification
        mapping = project.get_mapping_for_ai_frame("frame_0050.png")
        assert mapping is not None
        assert mapping.game_frame_id == "G0050"

        mapping = project.get_mapping_for_game_frame("G0099")
        assert mapping is not None
        assert mapping.ai_frame_id == "frame_0099.png"

        # Performance verification: O(1) should handle many lookups quickly
        # Time 1000 lookups - O(1) should be <10ms, O(n) with 100 items would be ~100ms+
        num_lookups = 1000
        start = time.perf_counter()
        for _ in range(num_lookups):
            project.get_mapping_for_ai_frame("frame_0050.png")
            project.get_mapping_for_game_frame("G0099")
        elapsed = time.perf_counter() - start

        # With O(1) lookup and 100 items, 2000 lookups (1000 iterations * 2 lookups)
        # should complete in <50ms even on slow machines.
        # O(n) linear scan would take much longer (100 items * 2000 calls = 200K operations).
        max_allowed_seconds = 0.05  # 50ms
        assert elapsed < max_allowed_seconds, (
            f"Lookup appears O(n): {elapsed * 1000:.1f}ms for {num_lookups * 2} lookups. "
            f"Expected O(1) to complete in <{max_allowed_seconds * 1000}ms"
        )


class TestRemoveGameFrame:
    """Tests for removing game frames from project."""

    def test_remove_game_frame_basic(self) -> None:
        """Remove a game frame from project."""
        project = FrameMappingProject(name="test")
        game_frame = GameFrame(id="G001", rom_offsets=[0x1000])
        project.game_frames.append(game_frame)

        assert len(project.game_frames) == 1
        assert project.get_game_frame_by_id("G001") is not None

        # Remove the game frame
        result = project.remove_game_frame("G001")

        assert result is True
        assert len(project.game_frames) == 0
        assert project.get_game_frame_by_id("G001") is None

    def test_remove_game_frame_nonexistent(self) -> None:
        """Remove nonexistent game frame returns False."""
        project = FrameMappingProject(name="test")

        result = project.remove_game_frame("NONEXISTENT")

        assert result is False

    def test_remove_game_frame_also_removes_mapping(self) -> None:
        """Removing a game frame also removes its mapping."""
        project = FrameMappingProject(name="test")
        ai_frame = AIFrame(path=Path("frame_001.png"), index=0)
        game_frame = GameFrame(id="G001", rom_offsets=[0x1000])
        project.ai_frames.append(ai_frame)
        project.game_frames.append(game_frame)
        project._rebuild_indices()
        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")

        assert project.get_mapping_for_game_frame("G001") is not None
        assert project.get_mapping_for_ai_frame("frame_001.png") is not None

        # Remove the game frame
        project.remove_game_frame("G001")

        # Mapping should also be gone
        assert project.get_mapping_for_game_frame("G001") is None
        assert project.get_mapping_for_ai_frame("frame_001.png") is None


class TestRemoveAIFrame:
    """Tests for removing AI frames from project."""

    def test_remove_ai_frame_basic(self) -> None:
        """Remove an AI frame from project."""
        project = FrameMappingProject(name="test")
        ai_frame = AIFrame(path=Path("frame_001.png"), index=0)
        project.ai_frames.append(ai_frame)
        project._invalidate_ai_frame_index()  # Rebuild index after direct append

        assert len(project.ai_frames) == 1
        assert project.get_ai_frame_by_id("frame_001.png") is not None

        # Remove the AI frame
        result = project.remove_ai_frame("frame_001.png")

        assert result is True
        assert len(project.ai_frames) == 0
        assert project.get_ai_frame_by_id("frame_001.png") is None

    def test_remove_ai_frame_nonexistent(self) -> None:
        """Remove nonexistent AI frame returns False."""
        project = FrameMappingProject(name="test")

        result = project.remove_ai_frame("NONEXISTENT")

        assert result is False

    def test_remove_ai_frame_also_removes_mapping(self) -> None:
        """Removing an AI frame also removes its mapping."""
        project = FrameMappingProject(name="test")
        ai_frame = AIFrame(path=Path("frame_001.png"), index=0)
        game_frame = GameFrame(id="G001", rom_offsets=[0x1000])
        project.ai_frames.append(ai_frame)
        project._invalidate_ai_frame_index()  # Rebuild index after direct append
        project.game_frames.append(game_frame)
        project.create_mapping(ai_frame_id="frame_001.png", game_frame_id="G001")

        assert project.get_mapping_for_game_frame("G001") is not None
        assert project.get_mapping_for_ai_frame("frame_001.png") is not None

        # Remove the AI frame
        project.remove_ai_frame("frame_001.png")

        # Mapping should also be gone
        assert project.get_mapping_for_game_frame("G001") is None
        assert project.get_mapping_for_ai_frame("frame_001.png") is None


class TestFacadeMethods:
    """Tests for encapsulation facade methods."""

    def test_replace_ai_frames_updates_list_and_index(self) -> None:
        """replace_ai_frames updates frames and rebuilds index."""
        project = FrameMappingProject(name="test")
        frames = [
            AIFrame(path=Path("frame_001.png"), index=0),
            AIFrame(path=Path("frame_002.png"), index=1),
        ]

        project.replace_ai_frames(frames)

        assert len(project.ai_frames) == 2
        assert project.get_ai_frame_by_id("frame_001.png") is not None
        assert project.get_ai_frame_by_id("frame_002.png") is not None

    def test_replace_ai_frames_sets_directory(self) -> None:
        """replace_ai_frames optionally sets ai_frames_dir."""
        project = FrameMappingProject(name="test")
        frames = [AIFrame(path=Path("/dir/frame.png"), index=0)]
        directory = Path("/some/dir")

        project.replace_ai_frames(frames, directory)

        assert project.ai_frames_dir == directory

    def test_replace_ai_frames_preserves_none_directory(self) -> None:
        """replace_ai_frames keeps existing directory if none provided."""
        project = FrameMappingProject(name="test", ai_frames_dir=Path("/existing"))
        frames = [AIFrame(path=Path("frame.png"), index=0)]

        project.replace_ai_frames(frames)

        assert project.ai_frames_dir == Path("/existing")

    def test_add_game_frame_appends_to_list(self) -> None:
        """add_game_frame adds a frame to game_frames list."""
        project = FrameMappingProject(name="test")
        frame = GameFrame(id="G001", rom_offsets=[0x1000])

        result = project.add_game_frame(frame)

        assert len(project.game_frames) == 1
        assert project.get_game_frame_by_id("G001") is not None
        assert result is frame  # Returns same frame for chaining

    def test_add_game_frame_returns_frame(self) -> None:
        """add_game_frame returns the added frame."""
        project = FrameMappingProject(name="test")
        frame = GameFrame(id="G002", rom_offsets=[0x2000])

        result = project.add_game_frame(frame)

        assert result is frame

    def test_filter_mappings_by_valid_ai_ids_removes_orphans(self) -> None:
        """filter_mappings_by_valid_ai_ids removes mappings with invalid AI IDs."""
        project = FrameMappingProject(name="test")
        # Create frames and mappings
        ai1 = AIFrame(path=Path("frame_001.png"), index=0)
        ai2 = AIFrame(path=Path("frame_002.png"), index=1)
        g1 = GameFrame(id="G001", rom_offsets=[0x1000])
        g2 = GameFrame(id="G002", rom_offsets=[0x2000])

        project.ai_frames = [ai1, ai2]
        project.game_frames = [g1, g2]
        project._rebuild_indices()
        project.create_mapping("frame_001.png", "G001")
        project.create_mapping("frame_002.png", "G002")

        assert len(project.mappings) == 2

        # Filter to only keep frame_001.png
        valid_ids = {"frame_001.png"}
        removed = project.filter_mappings_by_valid_ai_ids(valid_ids)

        assert removed == 1
        assert len(project.mappings) == 1
        assert project.get_mapping_for_ai_frame("frame_001.png") is not None
        assert project.get_mapping_for_ai_frame("frame_002.png") is None

    def test_filter_mappings_by_valid_ai_ids_returns_count(self) -> None:
        """filter_mappings_by_valid_ai_ids returns number of removed mappings."""
        project = FrameMappingProject(name="test")
        ai1 = AIFrame(path=Path("frame_001.png"), index=0)
        g1 = GameFrame(id="G001", rom_offsets=[0x1000])
        project.ai_frames = [ai1]
        project.game_frames = [g1]
        project._rebuild_indices()
        project.create_mapping("frame_001.png", "G001")

        # No orphans when all IDs valid
        removed = project.filter_mappings_by_valid_ai_ids({"frame_001.png"})
        assert removed == 0

        # Remove all when empty set
        removed = project.filter_mappings_by_valid_ai_ids(set())
        assert removed == 1
        assert len(project.mappings) == 0

    def test_filter_mappings_by_valid_ai_ids_updates_index(self) -> None:
        """filter_mappings_by_valid_ai_ids updates internal lookup index."""
        project = FrameMappingProject(name="test")
        ai1 = AIFrame(path=Path("frame_001.png"), index=0)
        g1 = GameFrame(id="G001", rom_offsets=[0x1000])
        project.ai_frames = [ai1]
        project.game_frames = [g1]
        project._rebuild_indices()
        project.create_mapping("frame_001.png", "G001")

        # Verify index is populated
        assert project.get_mapping_for_game_frame("G001") is not None

        # Filter removes mapping
        project.filter_mappings_by_valid_ai_ids(set())

        # Index should be updated (None lookup)
        assert project.get_mapping_for_game_frame("G001") is None


class TestCreateMappingValidation:
    """Tests for create_mapping input validation (P0-1 fix)."""

    def test_create_mapping_rejects_empty_ai_frame_id(self) -> None:
        """create_mapping raises ValueError for empty ai_frame_id."""
        project = FrameMappingProject(name="test")

        with pytest.raises(ValueError, match="ai_frame_id cannot be empty"):
            project.create_mapping("", "G001")

    def test_create_mapping_rejects_whitespace_ai_frame_id(self) -> None:
        """create_mapping raises ValueError for whitespace-only ai_frame_id."""
        project = FrameMappingProject(name="test")

        with pytest.raises(ValueError, match="ai_frame_id cannot be empty"):
            project.create_mapping("   ", "G001")

    def test_create_mapping_rejects_empty_game_frame_id(self) -> None:
        """create_mapping raises ValueError for empty game_frame_id."""
        project = FrameMappingProject(name="test")

        with pytest.raises(ValueError, match="game_frame_id cannot be empty"):
            project.create_mapping("frame_001.png", "")

    def test_create_mapping_rejects_whitespace_game_frame_id(self) -> None:
        """create_mapping raises ValueError for whitespace-only game_frame_id."""
        project = FrameMappingProject(name="test")

        with pytest.raises(ValueError, match="game_frame_id cannot be empty"):
            project.create_mapping("frame_001.png", "   ")

    def test_create_mapping_accepts_valid_ids(self) -> None:
        """create_mapping accepts valid non-empty IDs when frames exist."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project.game_frames = [GameFrame(id="G001")]
        project._rebuild_indices()

        mapping = project.create_mapping("frame_001.png", "G001")

        assert mapping.ai_frame_id == "frame_001.png"
        assert mapping.game_frame_id == "G001"

    def test_create_mapping_accepts_ids_with_special_chars(self) -> None:
        """create_mapping accepts IDs with special characters when frames exist."""
        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("sprite-001_v2.png"), index=0)]
        project.game_frames = [GameFrame(id="G_001-test")]
        project._rebuild_indices()

        mapping = project.create_mapping("sprite-001_v2.png", "G_001-test")

        assert mapping.ai_frame_id == "sprite-001_v2.png"
        assert mapping.game_frame_id == "G_001-test"

    def test_create_mapping_rejects_nonexistent_ai_frame(self) -> None:
        """create_mapping raises ValueError for AI frame ID not in project."""
        project = FrameMappingProject(name="test")
        # Add game frame but no AI frame
        project.game_frames.append(GameFrame(id="G001", rom_offsets=[0x1000]))
        project._rebuild_indices()

        with pytest.raises(ValueError, match="AI frame.*not found"):
            project.create_mapping("ghost.png", "G001")

    def test_create_mapping_rejects_nonexistent_game_frame(self) -> None:
        """create_mapping raises ValueError for game frame ID not in project."""
        project = FrameMappingProject(name="test")
        # Add AI frame but no game frame
        project.ai_frames.append(AIFrame(path=Path("frame_001.png"), index=0))
        project._rebuild_indices()

        with pytest.raises(ValueError, match="Game frame.*not found"):
            project.create_mapping("frame_001.png", "ghost_game")


class TestSheetPaletteTransparencyValidation:
    """Tests for BUG-1: Validate transparency at index 0."""

    def test_sheet_palette_from_dict_warns_on_non_transparent_index_0(self, caplog: pytest.LogCaptureFixture) -> None:
        """from_dict logs warning if index 0 is not (0,0,0)."""
        import logging

        data = {
            "colors": [
                [255, 0, 0],  # Index 0 should be transparent (black)
                *[[i, i, i] for i in range(1, 16)],
            ]
        }

        caplog.set_level(logging.WARNING)
        palette = SheetPalette.from_dict(data)

        # Should have logged a warning
        assert any("index 0 is (255, 0, 0), not (0,0,0)" in record.message for record in caplog.records), (
            "Expected warning about non-transparent index 0"
        )

        # Palette should still be created (we warn, not reject)
        assert palette.colors[0] == (255, 0, 0)

    def test_sheet_palette_from_dict_no_warning_for_transparent_index_0(self, caplog: pytest.LogCaptureFixture) -> None:
        """from_dict does not warn if index 0 is (0,0,0)."""
        import logging

        data = {
            "colors": [
                [0, 0, 0],  # Correct transparent index
                *[[i * 16, i * 16, i * 16] for i in range(1, 16)],
            ]
        }

        caplog.set_level(logging.WARNING)
        palette = SheetPalette.from_dict(data)

        # Should not have logged warning about index 0
        transparency_warnings = [r for r in caplog.records if "index 0" in r.message and "(0,0,0)" in r.message]
        assert len(transparency_warnings) == 0, "Unexpected transparency warning"

        assert palette.colors[0] == (0, 0, 0)

    def test_sheet_palette_from_dict_empty_pads_with_black(self) -> None:
        """from_dict pads empty palettes with black (0,0,0)."""
        data: dict[str, object] = {"colors": []}

        palette = SheetPalette.from_dict(data)

        assert len(palette.colors) == 16
        assert all(c == (0, 0, 0) for c in palette.colors)
