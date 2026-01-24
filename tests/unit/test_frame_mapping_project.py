"""Unit tests for core.frame_mapping_project module."""

from pathlib import Path

from core.frame_mapping_project import AIFrame, FrameMapping, GameFrame, SheetPalette


class TestFrameMappingAlignment:
    """Tests for FrameMapping alignment fields."""

    def test_frame_mapping_alignment_fields_default(self) -> None:
        """FrameMapping has default alignment values."""
        mapping = FrameMapping(ai_frame_id="frame_001.png", game_frame_id="F001")
        assert mapping.offset_x == 0
        assert mapping.offset_y == 0
        assert mapping.flip_h is False
        assert mapping.flip_v is False

    def test_frame_mapping_alignment_explicit_values(self) -> None:
        """FrameMapping accepts explicit alignment values."""
        mapping = FrameMapping(
            ai_frame_id="frame_002.png",
            game_frame_id="F002",
            offset_x=-5,
            offset_y=10,
            flip_h=True,
            flip_v=True,
        )
        assert mapping.offset_x == -5
        assert mapping.offset_y == 10
        assert mapping.flip_h is True
        assert mapping.flip_v is True

    def test_frame_mapping_alignment_roundtrip(self) -> None:
        """Alignment fields survive to_dict/from_dict cycle."""
        mapping = FrameMapping(
            ai_frame_id="frame_001.png",
            game_frame_id="F001",
            offset_x=-5,
            offset_y=10,
            flip_h=True,
            flip_v=False,
        )
        data = mapping.to_dict()
        restored = FrameMapping.from_dict(data)
        assert restored.offset_x == -5
        assert restored.offset_y == 10
        assert restored.flip_h is True
        assert restored.flip_v is False

    def test_frame_mapping_v1_migration(self) -> None:
        """V1 project files with ai_frame_index load via migration."""
        # Create AI frames for migration lookup
        ai_frames = [
            AIFrame(path=Path("/tmp/frame_001.png"), index=0),
            AIFrame(path=Path("/tmp/frame_002.png"), index=1),
        ]

        old_data: dict[str, object] = {
            "ai_frame_index": 0,  # V1 format
            "game_frame_id": "F001",
            "status": "mapped",
        }
        mapping = FrameMapping.from_dict(old_data, ai_frames=ai_frames)
        assert mapping.ai_frame_id == "frame_001.png"  # Migrated from index
        assert mapping.offset_x == 0
        assert mapping.offset_y == 0
        assert mapping.flip_h is False
        assert mapping.flip_v is False

    def test_frame_mapping_to_dict_includes_alignment(self) -> None:
        """to_dict() includes all alignment fields."""
        mapping = FrameMapping(
            ai_frame_id="frame_003.png",
            game_frame_id="F003",
            status="edited",
            offset_x=15,
            offset_y=-8,
            flip_h=False,
            flip_v=True,
        )
        data = mapping.to_dict()
        assert data["offset_x"] == 15
        assert data["offset_y"] == -8
        assert data["flip_h"] is False
        assert data["flip_v"] is True

    def test_frame_mapping_partial_alignment_backward_compat(self) -> None:
        """Handles case where only some alignment fields are present."""
        partial_data: dict[str, object] = {
            "ai_frame_id": "frame_001.png",
            "game_frame_id": "F001",
            "status": "mapped",
            "offset_x": 5,
            # Missing offset_y, flip_h, flip_v
        }
        mapping = FrameMapping.from_dict(partial_data)
        assert mapping.offset_x == 5
        assert mapping.offset_y == 0  # Default
        assert mapping.flip_h is False  # Default
        assert mapping.flip_v is False  # Default


class TestFrameMappingBasic:
    """Basic tests for FrameMapping without alignment focus."""

    def test_frame_mapping_status_default(self) -> None:
        """FrameMapping status defaults to 'mapped'."""
        mapping = FrameMapping(ai_frame_id="frame_001.png", game_frame_id="F001")
        assert mapping.status == "mapped"

    def test_frame_mapping_status_roundtrip(self) -> None:
        """Status field survives serialization."""
        mapping = FrameMapping(ai_frame_id="frame_002.png", game_frame_id="F002", status="injected")
        data = mapping.to_dict()
        restored = FrameMapping.from_dict(data)
        assert restored.status == "injected"

    def test_frame_mapping_missing_status_backward_compat(self) -> None:
        """Missing status defaults to 'mapped'."""
        old_data: dict[str, object] = {
            "ai_frame_id": "frame_001.png",
            "game_frame_id": "F001",
            # No status field
        }
        mapping = FrameMapping.from_dict(old_data)
        assert mapping.status == "mapped"


class TestAIFrame:
    """Tests for AIFrame dataclass."""

    def test_ai_frame_id_property(self) -> None:
        """AIFrame.id returns the filename."""
        frame = AIFrame(path=Path("/tmp/my_sprite/frame_001.png"), index=0)
        assert frame.id == "frame_001.png"

    def test_ai_frame_id_different_paths(self) -> None:
        """AIFrame.id works with various path formats."""
        frame1 = AIFrame(path=Path("frame.png"), index=0)
        assert frame1.id == "frame.png"

        frame2 = AIFrame(path=Path("/a/b/c/d/sprite.png"), index=1)
        assert frame2.id == "sprite.png"


class TestAIFrameOrganization:
    """Tests for AIFrame display_name and tags (V4 features)."""

    def test_display_name_defaults_to_none(self) -> None:
        """AIFrame display_name defaults to None."""
        frame = AIFrame(path=Path("frame_001.png"), index=0)
        assert frame.display_name is None

    def test_display_name_can_be_set(self) -> None:
        """AIFrame display_name can be explicitly set."""
        frame = AIFrame(path=Path("frame_001.png"), index=0, display_name="Walk Cycle 1")
        assert frame.display_name == "Walk Cycle 1"

    def test_tags_defaults_to_empty(self) -> None:
        """AIFrame tags defaults to empty frozenset."""
        frame = AIFrame(path=Path("frame_001.png"), index=0)
        assert frame.tags == frozenset()

    def test_tags_can_be_set(self) -> None:
        """AIFrame tags can be explicitly set."""
        frame = AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep", "final"}))
        assert frame.tags == frozenset({"keep", "final"})

    def test_name_property_returns_display_name_if_set(self) -> None:
        """AIFrame.name returns display_name when set."""
        frame = AIFrame(path=Path("frame_001.png"), index=0, display_name="My Custom Name")
        assert frame.name == "My Custom Name"

    def test_name_property_returns_filename_if_no_display_name(self) -> None:
        """AIFrame.name returns filename when display_name is None."""
        frame = AIFrame(path=Path("/tmp/sprites/frame_001.png"), index=0)
        assert frame.name == "frame_001.png"

    def test_display_name_roundtrip(self) -> None:
        """display_name survives to_dict/from_dict cycle."""
        frame = AIFrame(path=Path("frame_001.png"), index=0, display_name="Walk Cycle 1")
        data = frame.to_dict()
        restored = AIFrame.from_dict(data)
        assert restored.display_name == "Walk Cycle 1"

    def test_tags_roundtrip(self) -> None:
        """tags survives to_dict/from_dict cycle."""
        frame = AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep", "wip"}))
        data = frame.to_dict()
        restored = AIFrame.from_dict(data)
        assert restored.tags == frozenset({"keep", "wip"})

    def test_display_name_not_in_dict_when_none(self) -> None:
        """to_dict() omits display_name when None for compact output."""
        frame = AIFrame(path=Path("frame_001.png"), index=0)
        data = frame.to_dict()
        assert "display_name" not in data

    def test_tags_not_in_dict_when_empty(self) -> None:
        """to_dict() omits tags when empty for compact output."""
        frame = AIFrame(path=Path("frame_001.png"), index=0)
        data = frame.to_dict()
        assert "tags" not in data

    def test_display_name_in_dict_when_set(self) -> None:
        """to_dict() includes display_name when set."""
        frame = AIFrame(path=Path("frame_001.png"), index=0, display_name="Custom")
        data = frame.to_dict()
        assert data["display_name"] == "Custom"

    def test_tags_in_dict_when_set(self) -> None:
        """to_dict() includes tags as sorted list when set."""
        frame = AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"wip", "keep"}))
        data = frame.to_dict()
        assert data["tags"] == ["keep", "wip"]  # Sorted alphabetically

    def test_backward_compatibility_missing_display_name(self) -> None:
        """V3 files without display_name load with None."""
        old_data: dict[str, object] = {
            "path": "frame_001.png",
            "index": 0,
            "width": 32,
            "height": 32,
            # No display_name - simulating V3 format
        }
        frame = AIFrame.from_dict(old_data)
        assert frame.display_name is None

    def test_backward_compatibility_missing_tags(self) -> None:
        """V3 files without tags load with empty set."""
        old_data: dict[str, object] = {
            "path": "frame_001.png",
            "index": 0,
            "width": 32,
            "height": 32,
            # No tags - simulating V3 format
        }
        frame = AIFrame.from_dict(old_data)
        assert frame.tags == frozenset()

    def test_tags_filters_invalid_values(self) -> None:
        """from_dict() filters out invalid tag values."""
        data: dict[str, object] = {
            "path": "frame_001.png",
            "index": 0,
            "tags": ["keep", "invalid_tag", "wip", "another_bad"],
        }
        frame = AIFrame.from_dict(data)
        assert frame.tags == frozenset({"keep", "wip"})  # Only valid tags kept


class TestFrameMappingProjectOrganization:
    """Tests for FrameMappingProject frame organization methods (V4 features)."""

    def test_set_frame_display_name_success(self) -> None:
        """set_frame_display_name updates frame's display name."""
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0, display_name="Old Name")]
        project._rebuild_indices()

        project.set_frame_display_name("frame_001.png", None)

        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert frame.display_name is None

    def test_set_frame_display_name_nonexistent(self) -> None:
        """set_frame_display_name returns False for nonexistent frame."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")

        result = project.set_frame_display_name("nonexistent.png", "Name")

        assert result is False

    def test_add_frame_tag_success(self) -> None:
        """add_frame_tag adds a tag to the frame."""
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0)]
        project._rebuild_indices()

        project.toggle_frame_tag("frame_001.png", "keep")

        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert "keep" in frame.tags

    def test_toggle_frame_tag_removes_when_present(self) -> None:
        """toggle_frame_tag removes tag when already present."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep"}))]
        project._rebuild_indices()

        project.toggle_frame_tag("frame_001.png", "keep")

        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert "keep" not in frame.tags

    def test_get_frames_with_tag(self) -> None:
        """get_frames_with_tag returns matching frames."""
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        project.ai_frames = [AIFrame(path=Path("frame_001.png"), index=0, tags=frozenset({"keep", "wip"}))]
        project._rebuild_indices()

        project.set_frame_tags("frame_001.png", frozenset({"final", "review"}))

        frame = project.get_ai_frame_by_id("frame_001.png")
        assert frame is not None
        assert frame.tags == frozenset({"final", "review"})

    def test_organization_persists_through_save_load(self, tmp_path: Path) -> None:
        """display_name and tags survive save/load cycle."""
        from core.frame_mapping_project import FrameMappingProject
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


class TestGameFrame:
    """Basic tests for GameFrame dataclass."""

    def test_game_frame_minimal(self) -> None:
        """GameFrame can be created with minimal args."""
        frame = GameFrame(id="G001")
        assert frame.id == "G001"
        assert frame.rom_offsets == []
        assert frame.capture_path is None

    def test_game_frame_with_rom_offsets(self) -> None:
        """GameFrame preserves ROM offsets."""
        frame = GameFrame(id="G002", rom_offsets=[0x1B0000, 0x282000])
        assert frame.rom_offsets == [0x1B0000, 0x282000]

    def test_game_frame_selected_entry_ids_default(self) -> None:
        """GameFrame has empty selected_entry_ids by default."""
        frame = GameFrame(id="G001")
        assert frame.selected_entry_ids == []

    def test_game_frame_selected_entry_ids_explicit(self) -> None:
        """GameFrame accepts explicit selected_entry_ids."""
        frame = GameFrame(id="G001", selected_entry_ids=[1, 3, 5, 7])
        assert frame.selected_entry_ids == [1, 3, 5, 7]

    def test_game_frame_selected_entry_ids_roundtrip(self) -> None:
        """selected_entry_ids survives to_dict/from_dict cycle."""
        frame = GameFrame(
            id="G001",
            rom_offsets=[0x1B0000],
            capture_path=Path("/tmp/capture.json"),
            palette_index=7,
            width=32,
            height=48,
            selected_entry_ids=[2, 5, 8, 12],
        )
        data = frame.to_dict()
        restored = GameFrame.from_dict(data)
        assert restored.selected_entry_ids == [2, 5, 8, 12]

    def test_game_frame_backward_compatibility(self) -> None:
        """Old project files without selected_entry_ids load correctly."""
        old_data: dict[str, object] = {
            "id": "G001",
            "rom_offsets": [0x1B0000],
            "capture_path": "/tmp/capture.json",
            "palette_index": 7,
            "width": 32,
            "height": 48,
            # No selected_entry_ids - simulating old format
        }
        frame = GameFrame.from_dict(old_data)
        assert frame.selected_entry_ids == []  # Default to empty

    def test_game_frame_to_dict_includes_selected_entry_ids(self) -> None:
        """to_dict() includes selected_entry_ids field."""
        frame = GameFrame(
            id="G001",
            selected_entry_ids=[1, 2, 3],
        )
        data = frame.to_dict()
        assert data["selected_entry_ids"] == [1, 2, 3]

    def test_game_frame_compression_types_default(self) -> None:
        """GameFrame has empty compression_types by default."""
        frame = GameFrame(id="G001")
        assert frame.compression_types == {}

    def test_game_frame_compression_types_explicit(self) -> None:
        """GameFrame accepts explicit compression_types."""
        frame = GameFrame(
            id="G001",
            compression_types={0x35000: "raw", 0x36000: "hal"},
        )
        assert frame.compression_types == {0x35000: "raw", 0x36000: "hal"}

    def test_game_frame_compression_types_roundtrip(self) -> None:
        """compression_types survives to_dict/from_dict cycle with int keys."""
        frame = GameFrame(
            id="G001",
            rom_offsets=[0x35000, 0x36000],
            capture_path=Path("/tmp/capture.json"),
            compression_types={0x35000: "raw", 0x36000: "hal"},
        )
        data = frame.to_dict()
        # JSON serializes int keys as strings
        assert data["compression_types"] == {"217088": "raw", "221184": "hal"}

        restored = GameFrame.from_dict(data)
        # Keys should be converted back to ints
        assert restored.compression_types == {0x35000: "raw", 0x36000: "hal"}

    def test_game_frame_compression_types_backward_compatibility(self) -> None:
        """Old project files without compression_types load correctly."""
        old_data: dict[str, object] = {
            "id": "G001",
            "rom_offsets": [0x1B0000],
            "capture_path": "/tmp/capture.json",
            # No compression_types - simulating old format
        }
        frame = GameFrame.from_dict(old_data)
        assert frame.compression_types == {}  # Default to empty

    def test_game_frame_to_dict_includes_compression_types(self) -> None:
        """to_dict() includes compression_types field."""
        frame = GameFrame(
            id="G001",
            compression_types={0x50000: "raw"},
        )
        data = frame.to_dict()
        assert "compression_types" in data
        assert data["compression_types"] == {"327680": "raw"}


class TestGameFrameOrganization:
    """Tests for GameFrame display_name and name property."""

    def test_display_name_defaults_to_none(self) -> None:
        """GameFrame has None display_name by default."""
        frame = GameFrame(id="F001")
        assert frame.display_name is None

    def test_display_name_can_be_set(self) -> None:
        """GameFrame accepts display_name at creation."""
        frame = GameFrame(id="F001", display_name="Walk Cycle 1")
        assert frame.display_name == "Walk Cycle 1"

    def test_name_property_returns_display_name_if_set(self) -> None:
        """name property returns display_name when set."""
        frame = GameFrame(id="F001", display_name="My Custom Name")
        assert frame.name == "My Custom Name"

    def test_name_property_returns_id_if_no_display_name(self) -> None:
        """name property returns id when display_name is None."""
        frame = GameFrame(id="F001")
        assert frame.name == "F001"

    def test_display_name_roundtrip(self) -> None:
        """display_name survives to_dict/from_dict cycle."""
        frame = GameFrame(id="F001", display_name="Dedede Attack")
        data = frame.to_dict()
        restored = GameFrame.from_dict(data)
        assert restored.display_name == "Dedede Attack"

    def test_display_name_not_in_dict_when_none(self) -> None:
        """to_dict() omits display_name when None (compact format)."""
        frame = GameFrame(id="F001")
        data = frame.to_dict()
        assert "display_name" not in data

    def test_display_name_in_dict_when_set(self) -> None:
        """to_dict() includes display_name when set."""
        frame = GameFrame(id="F001", display_name="Test Name")
        data = frame.to_dict()
        assert data["display_name"] == "Test Name"

    def test_backward_compatibility_missing_display_name(self) -> None:
        """Old project files without display_name load correctly."""
        old_data: dict[str, object] = {
            "id": "F001",
            "rom_offsets": [0x1B0000],
            # No display_name - simulating old format
        }
        frame = GameFrame.from_dict(old_data)
        assert frame.display_name is None
        assert frame.name == "F001"


class TestFrameMappingProjectCaptureOrganization:
    """Tests for FrameMappingProject capture organization methods."""

    def test_set_capture_display_name_success(self) -> None:
        """set_capture_display_name updates game frame."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        project.game_frames = [GameFrame(id="F001")]

        result = project.set_capture_display_name("F001", "My Capture")
        assert result is True

        frame = project.get_game_frame_by_id("F001")
        assert frame is not None
        assert frame.display_name == "My Capture"

    def test_set_capture_display_name_clear(self) -> None:
        """set_capture_display_name can clear display name."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        project.game_frames = [GameFrame(id="F001", display_name="Old Name")]

        result = project.set_capture_display_name("F001", None)
        assert result is True

        frame = project.get_game_frame_by_id("F001")
        assert frame is not None
        assert frame.display_name is None

    def test_set_capture_display_name_nonexistent(self) -> None:
        """set_capture_display_name returns False for nonexistent frame."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")

        result = project.set_capture_display_name("NONEXISTENT", "Name")
        assert result is False

    def test_capture_organization_persists_through_save_load(self, tmp_path: Path) -> None:
        """Capture display names persist through save/load cycle."""
        from core.frame_mapping_project import FrameMappingProject
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
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
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
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
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
        from core.frame_mapping_project import FrameMappingProject
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


class TestFrameMappingProjectStableIDs:
    """Tests for stable AI frame ID feature (Issue #1 fix)."""

    def test_mapping_uses_ai_frame_id(self) -> None:
        """Mappings use stable ai_frame_id, not position-dependent index."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        project.create_mapping(ai_frame_id="my_sprite.png", game_frame_id="G001")

        mapping = project.get_mapping_for_ai_frame("my_sprite.png")
        assert mapping is not None
        assert mapping.ai_frame_id == "my_sprite.png"

    def test_mapping_survives_frame_reorder(self, tmp_path: Path) -> None:
        """Mappings survive AI frame reload/reorder."""
        from core.frame_mapping_project import FrameMappingProject
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
        import json

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

        from core.frame_mapping_project import FrameMappingProject
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


class TestFrameMappingProjectAtomicSave:
    """Tests for atomic save functionality (Issue #3 fix).

    Note: These tests moved to test_frame_mapping_repository.py.
    Keeping this class for backward compatibility marker.
    """

    pass


class TestFrameMappingProjectVersionValidation:
    """Tests for version validation (Issue #4 fix).

    Note: These tests moved to test_frame_mapping_repository.py.
    Keeping this class for backward compatibility marker.
    """

    pass


class TestFrameMappingProjectPerformance:
    """Tests for O(1) lookup optimization (Issue #5 fix)."""

    def test_mapping_lookup_is_fast(self) -> None:
        """Mapping lookup uses O(1) index."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")

        # Create many mappings
        for i in range(100):
            project.create_mapping(ai_frame_id=f"frame_{i:04d}.png", game_frame_id=f"G{i:04d}")

        # Lookups should use the index (O(1) not O(n))
        mapping = project.get_mapping_for_ai_frame("frame_0050.png")
        assert mapping is not None
        assert mapping.game_frame_id == "G0050"

        mapping = project.get_mapping_for_game_frame("G0099")
        assert mapping is not None
        assert mapping.ai_frame_id == "frame_0099.png"


class TestRemoveGameFrame:
    """Tests for removing game frames from project."""

    def test_remove_game_frame_basic(self) -> None:
        """Remove a game frame from project."""
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")

        result = project.remove_game_frame("NONEXISTENT")

        assert result is False

    def test_remove_game_frame_also_removes_mapping(self) -> None:
        """Removing a game frame also removes its mapping."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        ai_frame = AIFrame(path=Path("frame_001.png"), index=0)
        game_frame = GameFrame(id="G001", rom_offsets=[0x1000])
        project.ai_frames.append(ai_frame)
        project.game_frames.append(game_frame)
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
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")

        result = project.remove_ai_frame("NONEXISTENT")

        assert result is False

    def test_remove_ai_frame_also_removes_mapping(self) -> None:
        """Removing an AI frame also removes its mapping."""
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

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
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        frames = [AIFrame(path=Path("/dir/frame.png"), index=0)]
        directory = Path("/some/dir")

        project.replace_ai_frames(frames, directory)

        assert project.ai_frames_dir == directory

    def test_replace_ai_frames_preserves_none_directory(self) -> None:
        """replace_ai_frames keeps existing directory if none provided."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test", ai_frames_dir=Path("/existing"))
        frames = [AIFrame(path=Path("frame.png"), index=0)]

        project.replace_ai_frames(frames)

        assert project.ai_frames_dir == Path("/existing")

    def test_add_game_frame_appends_to_list(self) -> None:
        """add_game_frame adds a frame to game_frames list."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        frame = GameFrame(id="G001", rom_offsets=[0x1000])

        result = project.add_game_frame(frame)

        assert len(project.game_frames) == 1
        assert project.get_game_frame_by_id("G001") is not None
        assert result is frame  # Returns same frame for chaining

    def test_add_game_frame_returns_frame(self) -> None:
        """add_game_frame returns the added frame."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        frame = GameFrame(id="G002", rom_offsets=[0x2000])

        result = project.add_game_frame(frame)

        assert result is frame

    def test_filter_mappings_by_valid_ai_ids_removes_orphans(self) -> None:
        """filter_mappings_by_valid_ai_ids removes mappings with invalid AI IDs."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        # Create frames and mappings
        ai1 = AIFrame(path=Path("frame_001.png"), index=0)
        ai2 = AIFrame(path=Path("frame_002.png"), index=1)
        g1 = GameFrame(id="G001", rom_offsets=[0x1000])
        g2 = GameFrame(id="G002", rom_offsets=[0x2000])

        project.ai_frames = [ai1, ai2]
        project.game_frames = [g1, g2]
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
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        ai1 = AIFrame(path=Path("frame_001.png"), index=0)
        g1 = GameFrame(id="G001", rom_offsets=[0x1000])
        project.ai_frames = [ai1]
        project.game_frames = [g1]
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
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        ai1 = AIFrame(path=Path("frame_001.png"), index=0)
        g1 = GameFrame(id="G001", rom_offsets=[0x1000])
        project.ai_frames = [ai1]
        project.game_frames = [g1]
        project.create_mapping("frame_001.png", "G001")

        # Verify index is populated
        assert project.get_mapping_for_game_frame("G001") is not None

        # Filter removes mapping
        project.filter_mappings_by_valid_ai_ids(set())

        # Index should be updated (None lookup)
        assert project.get_mapping_for_game_frame("G001") is None


class TestSheetPaletteValidation:
    """Tests for SheetPalette validation in from_dict()."""

    def test_sheet_palette_clamps_rgb_bounds(self, caplog: object) -> None:
        """RGB values outside 0-255 should be clamped."""
        import logging

        # Cast caplog to proper type for type checker
        from _pytest.logging import LogCaptureFixture

        log = caplog if isinstance(caplog, LogCaptureFixture) else None

        # Create palette data with out-of-bounds RGB values
        data: dict[str, object] = {
            "colors": [
                [0, 0, 0],  # Valid - index 0 (transparent)
                [300, -10, 256],  # All out of bounds - should clamp to (255, 0, 255)
                [128, 128, 128],  # Valid
                *[[0, 0, 0]] * 13,  # Fill remaining
            ],
            "color_mappings": {},
        }

        if log:
            with caplog.at_level(logging.WARNING):
                palette = SheetPalette.from_dict(data)

            # Should have logged a warning about clamping
            assert any("RGB value clamped" in record.message for record in log.records)
        else:
            palette = SheetPalette.from_dict(data)

        # Verify RGB values are clamped
        assert palette.colors[0] == (0, 0, 0)
        assert palette.colors[1] == (255, 0, 255)  # Clamped from (300, -10, 256)
        assert palette.colors[2] == (128, 128, 128)

    def test_sheet_palette_clamps_mapping_indices(self, caplog: object) -> None:
        """Mapping indices outside 0-15 should be clamped."""
        import logging

        # Cast caplog to proper type for type checker
        from _pytest.logging import LogCaptureFixture

        log = caplog if isinstance(caplog, LogCaptureFixture) else None

        # Create palette data with out-of-bounds mapping indices
        data: dict[str, object] = {
            "colors": [[i * 16, i * 16, i * 16] for i in range(16)],
            "color_mappings": {
                "255,0,0": 20,  # Out of bounds - should clamp to 15
                "0,255,0": -5,  # Out of bounds - should clamp to 0
                "0,0,255": 8,  # Valid - should remain 8
            },
        }

        if log:
            with caplog.at_level(logging.WARNING):
                palette = SheetPalette.from_dict(data)

            # Should have logged warnings about clamping
            assert any("Mapping index clamped" in record.message for record in log.records)
        else:
            palette = SheetPalette.from_dict(data)

        # Verify mapping indices are clamped
        assert palette.color_mappings[(255, 0, 0)] == 15  # Clamped from 20
        assert palette.color_mappings[(0, 255, 0)] == 0  # Clamped from -5
        assert palette.color_mappings[(0, 0, 255)] == 8  # Valid

    def test_sheet_palette_valid_data_no_clamping(self) -> None:
        """Valid data should not be modified."""
        data: dict[str, object] = {
            "colors": [[i * 16, i * 16, i * 16] for i in range(16)],
            "color_mappings": {
                "255,0,0": 1,
                "0,255,0": 5,
                "0,0,255": 15,
            },
        }

        palette = SheetPalette.from_dict(data)

        # All values should match input
        for i in range(16):
            expected = (i * 16, i * 16, i * 16)
            assert palette.colors[i] == expected

        assert palette.color_mappings[(255, 0, 0)] == 1
        assert palette.color_mappings[(0, 255, 0)] == 5
        assert palette.color_mappings[(0, 0, 255)] == 15

    def test_sheet_palette_pads_missing_colors(self) -> None:
        """Palettes with fewer than 16 colors should be padded with black."""
        data: dict[str, object] = {
            "colors": [
                [255, 0, 0],  # Only one color
            ],
            "color_mappings": {},
        }

        palette = SheetPalette.from_dict(data)

        # Should have 16 colors
        assert len(palette.colors) == 16
        assert palette.colors[0] == (255, 0, 0)
        # Rest should be black
        for i in range(1, 16):
            assert palette.colors[i] == (0, 0, 0)
