"""Unit tests for GameFrame dataclass."""

from pathlib import Path

from core.frame_mapping_project import GameFrame
from core.types import CompressionType


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
            compression_types={0x35000: CompressionType.RAW, 0x36000: CompressionType.HAL},
        )
        assert frame.compression_types == {0x35000: CompressionType.RAW, 0x36000: CompressionType.HAL}

    def test_game_frame_compression_types_roundtrip(self) -> None:
        """compression_types survives to_dict/from_dict cycle with int keys."""
        frame = GameFrame(
            id="G001",
            rom_offsets=[0x35000, 0x36000],
            capture_path=Path("/tmp/capture.json"),
            compression_types={0x35000: CompressionType.RAW, 0x36000: CompressionType.HAL},
        )
        data = frame.to_dict()
        # JSON serializes int keys as strings
        assert data["compression_types"] == {"217088": "raw", "221184": "hal"}

        restored = GameFrame.from_dict(data)
        # Keys should be converted back to ints
        assert restored.compression_types == {0x35000: CompressionType.RAW, 0x36000: CompressionType.HAL}

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
            compression_types={0x50000: CompressionType.RAW},
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
