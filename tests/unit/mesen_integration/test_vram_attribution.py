"""Tests for VRAM attribution loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.mesen_integration.vram_attribution import (
    VRAMAttribution,
    VRAMAttributionMap,
    find_attribution_file,
    load_vram_attribution,
)


@pytest.fixture
def sample_attribution_json(tmp_path: Path) -> Path:
    """Create a sample attribution JSON file."""
    data = {
        "export_frame": 2800,
        "export_time": "2026-01-19 12:00:00",
        "entry_count": 3,
        "entries": [
            {"vram_word": 100, "vram_byte": 200, "idx": 0, "ptr": 9650003, "file_offset": 2712915, "frame": 2800},
            {"vram_word": 101, "vram_byte": 202, "idx": 0, "ptr": 9650003, "file_offset": 2712915, "frame": 2800},
            {"vram_word": 200, "vram_byte": 400, "idx": 5, "ptr": 9700000, "file_offset": 2800000, "frame": 2799},
        ],
    }
    path = tmp_path / "vram_attribution.json"
    path.write_text(json.dumps(data))
    return path


class TestVRAMAttributionMap:
    """Tests for VRAMAttributionMap."""

    def test_get_by_vram_addr_converts_byte_to_word(self, sample_attribution_json: Path) -> None:
        """get_by_vram_addr converts byte address to word for lookup."""
        attr_map = load_vram_attribution(sample_attribution_json)
        assert attr_map is not None

        # vram_word 100 should be found via byte address 200
        entry = attr_map.get_by_vram_addr(200)
        assert entry is not None
        assert entry.vram_word == 100
        assert entry.file_offset == 2712915

    def test_get_rom_offset_returns_file_offset(self, sample_attribution_json: Path) -> None:
        """get_rom_offset returns the file_offset for a VRAM address."""
        attr_map = load_vram_attribution(sample_attribution_json)
        assert attr_map is not None

        offset = attr_map.get_rom_offset(400)  # byte address for vram_word 200
        assert offset == 2800000

    def test_get_rom_offset_returns_none_for_missing(self, sample_attribution_json: Path) -> None:
        """get_rom_offset returns None for addresses not in map."""
        attr_map = load_vram_attribution(sample_attribution_json)
        assert attr_map is not None

        assert attr_map.get_rom_offset(99999) is None

    def test_get_unique_rom_offsets(self, sample_attribution_json: Path) -> None:
        """get_unique_rom_offsets returns set of all unique offsets."""
        attr_map = load_vram_attribution(sample_attribution_json)
        assert attr_map is not None

        offsets = attr_map.get_unique_rom_offsets()
        assert offsets == {2712915, 2800000}


class TestLoadVRAMAttribution:
    """Tests for load_vram_attribution function."""

    def test_load_from_file(self, sample_attribution_json: Path) -> None:
        """Successfully loads attribution from JSON file."""
        attr_map = load_vram_attribution(sample_attribution_json)

        assert attr_map is not None
        assert attr_map.export_frame == 2800
        assert attr_map.export_time == "2026-01-19 12:00:00"
        assert len(attr_map.entries) == 3

    def test_load_from_directory(self, sample_attribution_json: Path) -> None:
        """Loads vram_attribution.json from directory path."""
        attr_map = load_vram_attribution(sample_attribution_json.parent)

        assert attr_map is not None
        assert len(attr_map.entries) == 3

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """Returns None when file doesn't exist."""
        assert load_vram_attribution(tmp_path / "nonexistent.json") is None

    def test_returns_none_for_invalid_json(self, tmp_path: Path) -> None:
        """Returns None for invalid JSON."""
        bad_file = tmp_path / "vram_attribution.json"
        bad_file.write_text("not valid json {{{")

        assert load_vram_attribution(bad_file) is None


class TestFindAttributionFile:
    """Tests for find_attribution_file function."""

    def test_finds_in_same_directory(self, sample_attribution_json: Path) -> None:
        """Finds attribution file in same directory as capture."""
        capture_path = sample_attribution_json.parent / "capture.json"
        capture_path.touch()

        found = find_attribution_file(capture_path)
        assert found == sample_attribution_json

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """Returns None when attribution file doesn't exist."""
        capture_path = tmp_path / "capture.json"
        capture_path.touch()

        assert find_attribution_file(capture_path) is None
