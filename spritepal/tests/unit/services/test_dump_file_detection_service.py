"""Unit tests for dump file detection service."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from core.services.dump_file_detection_service import (
    DetectedFiles,
    auto_detect_all,
    detect_related_files,
    find_dumps_from_directories,
    get_base_name,
    scan_directory_for_dumps,
)


class TestGetBaseName:
    """Tests for get_base_name function."""

    def test_strips_vram_suffix(self) -> None:
        """Should strip _VRAM suffix."""
        assert get_base_name(Path("game_VRAM.dmp")) == "game"

    def test_strips_cgram_suffix(self) -> None:
        """Should strip _CGRAM suffix."""
        assert get_base_name(Path("game_CGRAM.dmp")) == "game"

    def test_strips_oam_suffix(self) -> None:
        """Should strip _OAM suffix."""
        assert get_base_name(Path("game_OAM.dmp")) == "game"

    def test_strips_snes_video_ram_suffix(self) -> None:
        """Should strip .SnesVideoRam suffix."""
        assert get_base_name(Path("savestate.SnesVideoRam.dmp")) == "savestate"

    def test_strips_snes_cg_ram_suffix(self) -> None:
        """Should strip .SnesCgRam suffix."""
        assert get_base_name(Path("savestate.SnesCgRam.dmp")) == "savestate"

    def test_strips_snes_sprite_ram_suffix(self) -> None:
        """Should strip .SnesSpriteRam suffix."""
        assert get_base_name(Path("savestate.SnesSpriteRam.dmp")) == "savestate"

    def test_preserves_name_without_suffix(self) -> None:
        """Should preserve name if no known suffix."""
        assert get_base_name(Path("something.dmp")) == "something"

    def test_only_strips_first_matching_suffix(self) -> None:
        """Should only strip the first matching suffix."""
        assert get_base_name(Path("game_VRAM_CGRAM.dmp")) == "game_VRAM"


class TestDetectedFiles:
    """Tests for DetectedFiles dataclass."""

    def test_has_any_with_vram(self) -> None:
        """Should return True if VRAM is set."""
        result = DetectedFiles(vram_path=Path("/test/vram.dmp"))
        assert result.has_any() is True

    def test_has_any_with_cgram(self) -> None:
        """Should return True if CGRAM is set."""
        result = DetectedFiles(cgram_path=Path("/test/cgram.dmp"))
        assert result.has_any() is True

    def test_has_any_with_oam(self) -> None:
        """Should return True if OAM is set."""
        result = DetectedFiles(oam_path=Path("/test/oam.dmp"))
        assert result.has_any() is True

    def test_has_any_empty(self) -> None:
        """Should return False if nothing is set."""
        result = DetectedFiles()
        assert result.has_any() is False

    def test_merge_prefers_existing(self) -> None:
        """Merge should prefer existing values over other values."""
        existing = DetectedFiles(vram_path=Path("/a/vram.dmp"))
        other = DetectedFiles(
            vram_path=Path("/b/vram.dmp"),
            cgram_path=Path("/b/cgram.dmp"),
        )
        merged = existing.merge(other)

        assert merged.vram_path == Path("/a/vram.dmp")  # Existing wins
        assert merged.cgram_path == Path("/b/cgram.dmp")  # Other fills gap

    def test_merge_fills_gaps(self) -> None:
        """Merge should fill gaps from other."""
        existing = DetectedFiles(vram_path=Path("/a/vram.dmp"))
        other = DetectedFiles(cgram_path=Path("/b/cgram.dmp"))
        merged = existing.merge(other)

        assert merged.vram_path == Path("/a/vram.dmp")
        assert merged.cgram_path == Path("/b/cgram.dmp")


class TestDetectRelatedFiles:
    """Tests for detect_related_files function."""

    def test_finds_cgram_from_vram(self, tmp_path: Path) -> None:
        """Should find CGRAM when given VRAM file."""
        vram = tmp_path / "game_VRAM.dmp"
        cgram = tmp_path / "game_CGRAM.dmp"
        vram.write_bytes(b"vram")
        cgram.write_bytes(b"cgram")

        result = detect_related_files(vram)
        assert result.cgram_path == cgram

    def test_finds_oam_from_vram(self, tmp_path: Path) -> None:
        """Should find OAM when given VRAM file."""
        vram = tmp_path / "game_VRAM.dmp"
        oam = tmp_path / "game_OAM.dmp"
        vram.write_bytes(b"vram")
        oam.write_bytes(b"oam")

        result = detect_related_files(vram)
        assert result.oam_path == oam

    def test_finds_snes_pattern_files(self, tmp_path: Path) -> None:
        """Should find files using SNES naming pattern."""
        vram = tmp_path / "save.SnesVideoRam.dmp"
        cgram = tmp_path / "save.SnesCgRam.dmp"
        vram.write_bytes(b"vram")
        cgram.write_bytes(b"cgram")

        result = detect_related_files(vram)
        assert result.cgram_path == cgram

    def test_skips_already_loaded(self, tmp_path: Path) -> None:
        """Should skip files that are already loaded."""
        vram = tmp_path / "game_VRAM.dmp"
        cgram = tmp_path / "game_CGRAM.dmp"
        vram.write_bytes(b"vram")
        cgram.write_bytes(b"cgram")

        existing = DetectedFiles(cgram_path=Path("/other/cgram.dmp"))
        result = detect_related_files(vram, existing=existing)

        # Should not overwrite existing CGRAM
        assert result.cgram_path is None

    def test_handles_missing_files(self, tmp_path: Path) -> None:
        """Should handle case where related files don't exist."""
        vram = tmp_path / "game_VRAM.dmp"
        vram.write_bytes(b"vram")

        result = detect_related_files(vram)
        assert result.cgram_path is None
        assert result.oam_path is None


class TestScanDirectoryForDumps:
    """Tests for scan_directory_for_dumps function."""

    def test_finds_vram_by_glob(self, tmp_path: Path) -> None:
        """Should find VRAM file using glob pattern."""
        vram = tmp_path / "someVRAMfile.dmp"
        vram.write_bytes(b"vram")

        result = scan_directory_for_dumps(tmp_path)
        assert result.vram_path == vram

    def test_finds_cgram_by_glob(self, tmp_path: Path) -> None:
        """Should find CGRAM file using glob pattern."""
        cgram = tmp_path / "someCGRAMfile.dmp"
        cgram.write_bytes(b"cgram")

        result = scan_directory_for_dumps(tmp_path)
        assert result.cgram_path == cgram

    def test_finds_snes_pattern_by_glob(self, tmp_path: Path) -> None:
        """Should find files using SNES glob pattern."""
        vram = tmp_path / "state.SnesVideoRam.dmp"
        vram.write_bytes(b"vram")

        result = scan_directory_for_dumps(tmp_path)
        # VideoRam matches glob pattern
        assert result.vram_path == vram

    def test_skips_already_loaded(self, tmp_path: Path) -> None:
        """Should skip files that are already loaded."""
        vram = tmp_path / "VRAM.dmp"
        vram.write_bytes(b"vram")

        existing = DetectedFiles(vram_path=Path("/other/vram.dmp"))
        result = scan_directory_for_dumps(tmp_path, existing=existing)

        assert result.vram_path is None

    def test_handles_nonexistent_directory(self) -> None:
        """Should handle nonexistent directory gracefully."""
        result = scan_directory_for_dumps(Path("/nonexistent/directory"))
        assert result.has_any() is False


class TestFindDumpsFromDirectories:
    """Tests for find_dumps_from_directories function."""

    def test_searches_directories_in_order(self, tmp_path: Path) -> None:
        """Should search directories in priority order."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        # Put file only in dir2
        vram = dir2 / "VRAM.dmp"
        vram.write_bytes(b"vram")

        result = find_dumps_from_directories([dir1, dir2])
        assert result.vram_path == vram

    def test_stops_at_first_match(self, tmp_path: Path) -> None:
        """Should stop searching once files are found."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        # Put files in both directories
        vram1 = dir1 / "VRAM.dmp"
        vram2 = dir2 / "VRAM.dmp"
        vram1.write_bytes(b"vram1")
        vram2.write_bytes(b"vram2")

        result = find_dumps_from_directories([dir1, dir2])
        # Should find first one
        assert result.vram_path == vram1

    def test_skips_nonexistent_directories(self, tmp_path: Path) -> None:
        """Should skip directories that don't exist."""
        valid_dir = tmp_path / "valid"
        valid_dir.mkdir()
        vram = valid_dir / "VRAM.dmp"
        vram.write_bytes(b"vram")

        result = find_dumps_from_directories(
            [
                Path("/nonexistent"),
                valid_dir,
            ]
        )
        assert result.vram_path == vram


class TestAutoDetectAll:
    """Tests for auto_detect_all function."""

    def test_uses_trigger_file_first(self, tmp_path: Path) -> None:
        """Should use trigger file for related detection first."""
        vram = tmp_path / "game_VRAM.dmp"
        cgram = tmp_path / "game_CGRAM.dmp"
        vram.write_bytes(b"vram")
        cgram.write_bytes(b"cgram")

        result = auto_detect_all(trigger_file=vram)
        assert result.cgram_path == cgram

    def test_falls_back_to_directory_scan(self, tmp_path: Path) -> None:
        """Should fall back to directory scanning if trigger has no matches."""
        other_dir = tmp_path / "other"
        other_dir.mkdir()

        trigger = tmp_path / "single.dmp"
        trigger.write_bytes(b"trigger")

        cgram = other_dir / "CGRAM.dmp"
        cgram.write_bytes(b"cgram")

        result = auto_detect_all(
            trigger_file=trigger,
            search_directories=[other_dir],
        )
        assert result.cgram_path == cgram

    def test_merges_both_strategies(self, tmp_path: Path) -> None:
        """Should merge results from both strategies."""
        other_dir = tmp_path / "other"
        other_dir.mkdir()

        # Related file from trigger
        vram = tmp_path / "game_VRAM.dmp"
        cgram = tmp_path / "game_CGRAM.dmp"
        vram.write_bytes(b"vram")
        cgram.write_bytes(b"cgram")

        # OAM from directory scan
        oam = other_dir / "OAM.dmp"
        oam.write_bytes(b"oam")

        result = auto_detect_all(
            trigger_file=vram,
            search_directories=[other_dir],
        )

        assert result.cgram_path == cgram  # From related
        assert result.oam_path == oam  # From scan
