"""Unit tests for SpriteProject serialization and persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest

from core.sprite_project import FORMAT_VERSION, SpriteProject, SpriteProjectError


@pytest.fixture
def sample_tile_data() -> bytes:
    """Create sample 4bpp tile data (2 tiles = 64 bytes)."""
    # Each tile is 32 bytes in 4bpp format
    return bytes(range(64))


@pytest.fixture
def sample_palette() -> list[tuple[int, int, int]]:
    """Create sample 16-color palette."""
    return [
        (0, 0, 0),  # Transparent/black
        (255, 0, 0),  # Red
        (0, 255, 0),  # Green
        (0, 0, 255),  # Blue
        (255, 255, 0),  # Yellow
        (255, 0, 255),  # Magenta
        (0, 255, 255),  # Cyan
        (255, 255, 255),  # White
        (128, 128, 128),  # Gray
        (192, 192, 192),  # Light gray
        (64, 64, 64),  # Dark gray
        (255, 128, 0),  # Orange
        (128, 0, 255),  # Purple
        (0, 128, 255),  # Light blue
        (255, 192, 203),  # Pink
        (139, 69, 19),  # Brown
    ]


@pytest.fixture
def sample_project(sample_tile_data: bytes, sample_palette: list[tuple[int, int, int]]) -> SpriteProject:
    """Create a sample SpriteProject with all fields populated."""
    return SpriteProject(
        name="test_sprite",
        width=16,
        height=8,
        tile_data=sample_tile_data,
        tile_count=2,
        preview_png=b"\x89PNG\r\n\x1a\n",  # PNG magic bytes (not valid but sufficient for test)
        palette_colors=sample_palette,
        palette_name="Test Palette",
        palette_index=5,
        original_rom_offset=0x3C6EF1,
        original_compressed_size=1024,
        header_bytes=b"\x00\x01\x02",
        compression_type="hal",
        rom_title="Test ROM",
        rom_checksum="0xABCD",
        created_at=datetime(2026, 1, 13, 10, 30, 0, tzinfo=UTC),
        last_modified=datetime(2026, 1, 13, 14, 45, 0, tzinfo=UTC),
        notes="Test notes",
    )


class TestSpriteProjectSerialization:
    """Tests for SpriteProject JSON serialization."""

    def test_to_json_produces_valid_json(self, sample_project: SpriteProject) -> None:
        """to_json() should produce parseable JSON."""
        json_str = sample_project.to_json()
        parsed = json.loads(json_str)
        assert parsed is not None
        assert "format_version" in parsed

    def test_to_dict_includes_format_version(self, sample_project: SpriteProject) -> None:
        """to_dict() should include format_version."""
        data = sample_project.to_dict()
        assert data["format_version"] == FORMAT_VERSION

    def test_to_dict_includes_sprite_section(self, sample_project: SpriteProject) -> None:
        """to_dict() should include sprite section with all fields."""
        data = sample_project.to_dict()
        sprite = data["sprite"]
        assert sprite["name"] == "test_sprite"
        assert sprite["width"] == 16
        assert sprite["height"] == 8
        assert sprite["tile_count"] == 2
        assert "tile_data_b64" in sprite
        assert "preview_png_b64" in sprite

    def test_to_dict_includes_palette_section(self, sample_project: SpriteProject) -> None:
        """to_dict() should include palette section."""
        data = sample_project.to_dict()
        palette = data["palette"]
        assert palette["name"] == "Test Palette"
        assert palette["index"] == 5
        assert len(palette["colors"]) == 16

    def test_to_dict_includes_injection_metadata(self, sample_project: SpriteProject) -> None:
        """to_dict() should include injection metadata."""
        data = sample_project.to_dict()
        injection = data["injection_metadata"]
        assert injection["original_rom_offset"] == 0x3C6EF1
        assert injection["original_rom_offset_hex"] == "0x3C6EF1"
        assert injection["original_compressed_size"] == 1024
        assert injection["compression_type"] == "hal"
        assert injection["rom_title"] == "Test ROM"
        assert injection["rom_checksum"] == "0xABCD"
        assert "header_bytes_b64" in injection

    def test_to_dict_includes_edit_metadata(self, sample_project: SpriteProject) -> None:
        """to_dict() should include edit metadata."""
        data = sample_project.to_dict()
        edit = data["edit_metadata"]
        assert edit["notes"] == "Test notes"
        assert "created_at" in edit
        assert "last_modified" in edit


class TestSpriteProjectDeserialization:
    """Tests for SpriteProject JSON deserialization."""

    def test_roundtrip_preserves_all_fields(self, sample_project: SpriteProject) -> None:
        """Serializing and deserializing should preserve all data."""
        json_str = sample_project.to_json()
        loaded = SpriteProject.from_json(json_str)

        assert loaded.name == sample_project.name
        assert loaded.width == sample_project.width
        assert loaded.height == sample_project.height
        assert loaded.tile_data == sample_project.tile_data
        assert loaded.tile_count == sample_project.tile_count
        assert loaded.preview_png == sample_project.preview_png
        assert loaded.palette_colors == sample_project.palette_colors
        assert loaded.palette_name == sample_project.palette_name
        assert loaded.palette_index == sample_project.palette_index
        assert loaded.original_rom_offset == sample_project.original_rom_offset
        assert loaded.original_compressed_size == sample_project.original_compressed_size
        assert loaded.header_bytes == sample_project.header_bytes
        assert loaded.compression_type == sample_project.compression_type
        assert loaded.rom_title == sample_project.rom_title
        assert loaded.rom_checksum == sample_project.rom_checksum
        assert loaded.notes == sample_project.notes

    def test_from_json_invalid_json_raises_error(self) -> None:
        """from_json() should raise SpriteProjectError for invalid JSON."""
        with pytest.raises(SpriteProjectError, match="Invalid JSON"):
            SpriteProject.from_json("not valid json {{{")

    def test_from_dict_missing_required_field_raises_error(self) -> None:
        """from_dict() should raise error for missing required fields."""
        data: dict[str, object] = {
            "format_version": "1.0",
            "sprite": {
                "name": "test",
                # Missing width, height, tile_data_b64, tile_count
            },
            "palette": {},
            "injection_metadata": {},
            "edit_metadata": {},
        }
        with pytest.raises(SpriteProjectError, match="Missing required field"):
            SpriteProject.from_dict(data)

    def test_from_dict_invalid_base64_raises_error(self) -> None:
        """from_dict() should raise error for invalid base64."""
        data: dict[str, object] = {
            "format_version": "1.0",
            "sprite": {
                "name": "test",
                "width": 16,
                "height": 8,
                "tile_data_b64": "!!!invalid base64!!!",
                "tile_count": 2,
            },
            "palette": {},
            "injection_metadata": {},
            "edit_metadata": {},
        }
        with pytest.raises(SpriteProjectError, match="Invalid tile_data_b64"):
            SpriteProject.from_dict(data)

    def test_from_dict_handles_missing_optional_fields(self, sample_tile_data: bytes) -> None:
        """from_dict() should handle missing optional fields gracefully."""
        import base64

        data: dict[str, object] = {
            "format_version": "1.0",
            "sprite": {
                "name": "minimal",
                "width": 16,
                "height": 8,
                "tile_data_b64": base64.b64encode(sample_tile_data).decode("ascii"),
                "tile_count": 2,
            },
            # Missing palette, injection_metadata, edit_metadata
        }
        project = SpriteProject.from_dict(data)
        assert project.name == "minimal"
        assert project.palette_colors == []
        assert project.original_rom_offset == 0
        assert project.notes == ""


class TestSpriteProjectFilePersistence:
    """Tests for SpriteProject file save/load."""

    def test_save_creates_file(self, sample_project: SpriteProject, tmp_path: Path) -> None:
        """save() should create a file at the specified path."""
        file_path = tmp_path / "test.spritepal"
        sample_project.save(file_path)
        assert file_path.exists()

    def test_save_file_contains_valid_json(self, sample_project: SpriteProject, tmp_path: Path) -> None:
        """Saved file should contain valid JSON."""
        file_path = tmp_path / "test.spritepal"
        sample_project.save(file_path)

        content = file_path.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert parsed["format_version"] == FORMAT_VERSION

    def test_load_restores_project(self, sample_project: SpriteProject, tmp_path: Path) -> None:
        """load() should restore a saved project."""
        file_path = tmp_path / "test.spritepal"
        sample_project.save(file_path)

        loaded = SpriteProject.load(file_path)
        assert loaded.name == sample_project.name
        assert loaded.tile_data == sample_project.tile_data

    def test_load_nonexistent_file_raises_error(self, tmp_path: Path) -> None:
        """load() should raise error for nonexistent file."""
        with pytest.raises(SpriteProjectError, match="File not found"):
            SpriteProject.load(tmp_path / "nonexistent.spritepal")

    def test_load_invalid_file_raises_error(self, tmp_path: Path) -> None:
        """load() should raise error for invalid file content."""
        file_path = tmp_path / "invalid.spritepal"
        file_path.write_text("not json at all", encoding="utf-8")

        with pytest.raises(SpriteProjectError):
            SpriteProject.load(file_path)

    def test_save_updates_last_modified(self, sample_project: SpriteProject, tmp_path: Path) -> None:
        """save() should update last_modified timestamp."""
        from datetime import datetime

        before_save = datetime.now(UTC)
        file_path = tmp_path / "test.spritepal"
        sample_project.save(file_path)
        # last_modified should be updated to approximately "now"
        assert sample_project.last_modified >= before_save


class TestSpriteProjectPreviewGeneration:
    """Tests for preview PNG generation."""

    def test_generate_preview_with_valid_data(self, sample_palette: list[tuple[int, int, int]]) -> None:
        """generate_preview_png() should produce PNG bytes."""
        # Create valid 4bpp tile data (2 tiles for 16x8 image)
        # Simple pattern: all pixels set to palette index 1
        tile_data = bytes([0xFF] * 32 + [0xFF] * 32)  # 2 tiles

        project = SpriteProject(
            name="preview_test",
            width=16,
            height=8,
            tile_data=tile_data,
            tile_count=2,
            palette_colors=sample_palette,
        )

        png_bytes = project.generate_preview_png()
        assert png_bytes.startswith(b"\x89PNG")

    def test_generate_preview_empty_tile_data_raises_error(self, sample_palette: list[tuple[int, int, int]]) -> None:
        """generate_preview_png() should raise error for empty tile data."""
        project = SpriteProject(
            name="empty_test",
            width=16,
            height=8,
            tile_data=b"",
            tile_count=0,
            palette_colors=sample_palette,
        )

        with pytest.raises(SpriteProjectError, match="missing tile data"):
            project.generate_preview_png()

    def test_generate_preview_no_palette_raises_error(self) -> None:
        """generate_preview_png() should raise error for missing palette."""
        project = SpriteProject(
            name="no_palette_test",
            width=16,
            height=8,
            tile_data=bytes(64),
            tile_count=2,
            palette_colors=[],
        )

        with pytest.raises(SpriteProjectError, match="missing tile data or palette"):
            project.generate_preview_png()

    def test_update_preview_sets_preview_png(self, sample_palette: list[tuple[int, int, int]]) -> None:
        """update_preview() should populate preview_png field."""
        tile_data = bytes([0] * 64)  # 2 tiles, all zeros

        project = SpriteProject(
            name="update_test",
            width=16,
            height=8,
            tile_data=tile_data,
            tile_count=2,
            palette_colors=sample_palette,
            preview_png=None,
        )

        project.update_preview()
        assert project.preview_png is not None
        assert project.preview_png.startswith(b"\x89PNG")
