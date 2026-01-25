"""Unit tests for AIFrame dataclass."""

from pathlib import Path

from core.frame_mapping_project import AIFrame


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
