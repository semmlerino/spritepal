"""Unit tests for core.frame_mapping_project module."""

from pathlib import Path

from core.frame_mapping_project import FrameMapping, GameFrame


class TestFrameMappingAlignment:
    """Tests for FrameMapping alignment fields."""

    def test_frame_mapping_alignment_fields_default(self) -> None:
        """FrameMapping has default alignment values."""
        mapping = FrameMapping(ai_frame_index=0, game_frame_id="F001")
        assert mapping.offset_x == 0
        assert mapping.offset_y == 0
        assert mapping.flip_h is False
        assert mapping.flip_v is False

    def test_frame_mapping_alignment_explicit_values(self) -> None:
        """FrameMapping accepts explicit alignment values."""
        mapping = FrameMapping(
            ai_frame_index=1,
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
            ai_frame_index=0,
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

    def test_frame_mapping_backward_compatibility(self) -> None:
        """Old project files without alignment fields load correctly."""
        old_data: dict[str, object] = {
            "ai_frame_index": 0,
            "game_frame_id": "F001",
            "status": "mapped",
            # No alignment fields - simulating old format
        }
        mapping = FrameMapping.from_dict(old_data)
        assert mapping.offset_x == 0
        assert mapping.offset_y == 0
        assert mapping.flip_h is False
        assert mapping.flip_v is False

    def test_frame_mapping_to_dict_includes_alignment(self) -> None:
        """to_dict() includes all alignment fields."""
        mapping = FrameMapping(
            ai_frame_index=2,
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
            "ai_frame_index": 0,
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
        mapping = FrameMapping(ai_frame_index=0, game_frame_id="F001")
        assert mapping.status == "mapped"

    def test_frame_mapping_status_roundtrip(self) -> None:
        """Status field survives serialization."""
        mapping = FrameMapping(ai_frame_index=1, game_frame_id="F002", status="injected")
        data = mapping.to_dict()
        restored = FrameMapping.from_dict(data)
        assert restored.status == "injected"

    def test_frame_mapping_missing_status_backward_compat(self) -> None:
        """Missing status defaults to 'mapped'."""
        old_data: dict[str, object] = {
            "ai_frame_index": 0,
            "game_frame_id": "F001",
            # No status field
        }
        mapping = FrameMapping.from_dict(old_data)
        assert mapping.status == "mapped"


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


class TestFrameMappingProjectAlignment:
    """Tests for FrameMappingProject alignment update functionality."""

    def test_update_mapping_alignment_success(self) -> None:
        """update_mapping_alignment updates existing mapping."""
        from core.frame_mapping_project import FrameMappingProject

        project = FrameMappingProject(name="test")
        project.create_mapping(ai_frame_index=0, game_frame_id="G001")

        result = project.update_mapping_alignment(
            ai_frame_index=0,
            offset_x=10,
            offset_y=-5,
            flip_h=True,
            flip_v=False,
        )

        assert result is True
        mapping = project.get_mapping_for_ai_frame(0)
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
            ai_frame_index=0,
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
        mapping = project.create_mapping(ai_frame_index=0, game_frame_id="G001")
        mapping.status = "edited"

        project.update_mapping_alignment(
            ai_frame_index=0,
            offset_x=5,
            offset_y=5,
            flip_h=False,
            flip_v=True,
        )

        mapping = project.get_mapping_for_ai_frame(0)
        assert mapping is not None
        assert mapping.game_frame_id == "G001"
        assert mapping.status == "edited"

    def test_alignment_persists_through_save_load(self, tmp_path: Path) -> None:
        """Alignment values survive save/load cycle."""
        from core.frame_mapping_project import FrameMappingProject

        # Create project with alignment
        project = FrameMappingProject(name="test")
        project.create_mapping(ai_frame_index=0, game_frame_id="G001")
        project.update_mapping_alignment(
            ai_frame_index=0,
            offset_x=15,
            offset_y=-10,
            flip_h=True,
            flip_v=True,
        )

        # Save
        save_path = tmp_path / "test.spritepal-mapping.json"
        project.save(save_path)

        # Load
        loaded = FrameMappingProject.load(save_path)

        mapping = loaded.get_mapping_for_ai_frame(0)
        assert mapping is not None
        assert mapping.offset_x == 15
        assert mapping.offset_y == -10
        assert mapping.flip_h is True
        assert mapping.flip_v is True
