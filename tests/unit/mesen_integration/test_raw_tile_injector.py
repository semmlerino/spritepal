"""Tests for RawTileInjector - atomic writes and skipped offset tracking."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from core.mesen_integration.raw_tile_injector import (
    RawTileInjectionResult,
    RawTileInjector,
    TileInjectionMapping,
)


@pytest.fixture
def sample_rom(tmp_path: Path) -> Path:
    """Create a minimal ROM file for testing."""
    rom_path = tmp_path / "test.sfc"
    # 1KB ROM with recognizable pattern
    rom_data = bytes(range(256)) * 4
    rom_path.write_bytes(rom_data)
    return rom_path


@pytest.fixture
def tile_data() -> bytes:
    """32-byte 4bpp tile data."""
    return bytes([0xAA] * 32)


class TestRawTileInjectorSuccess:
    """Tests for successful injection scenarios."""

    def test_inject_tiles_writes_to_output(self, tmp_path: Path, sample_rom: Path, tile_data: bytes) -> None:
        """Normal write should succeed and modify the output file."""
        output_path = tmp_path / "output.sfc"
        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=0x100, tile_data=tile_data),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=sample_rom,
            output_path=output_path,
            tile_mappings=mappings,
            create_backup=False,
        )

        assert result.success is True
        assert result.tiles_written == 1
        assert result.skipped_offsets == []
        assert output_path.exists()

        # Verify tile was written at correct offset
        output_data = output_path.read_bytes()
        assert output_data[0x100 : 0x100 + 32] == tile_data

    def test_inject_tiles_multiple_tiles(self, tmp_path: Path, sample_rom: Path, tile_data: bytes) -> None:
        """Multiple tiles should all be written."""
        output_path = tmp_path / "output.sfc"
        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=0x100, tile_data=tile_data),
            TileInjectionMapping(vram_word=0x200, rom_offset=0x200, tile_data=tile_data),
            TileInjectionMapping(vram_word=0x300, rom_offset=0x300, tile_data=tile_data),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=sample_rom,
            output_path=output_path,
            tile_mappings=mappings,
            create_backup=False,
        )

        assert result.success is True
        assert result.tiles_written == 3
        assert result.skipped_offsets == []

        output_data = output_path.read_bytes()
        for offset in [0x100, 0x200, 0x300]:
            assert output_data[offset : offset + 32] == tile_data


class TestRawTileInjectorSkippedOffsets:
    """Tests for invalid offset handling."""

    def test_inject_tiles_skips_negative_offset(self, tmp_path: Path, sample_rom: Path, tile_data: bytes) -> None:
        """Negative offsets should be skipped and tracked."""
        output_path = tmp_path / "output.sfc"
        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=-1, tile_data=tile_data),
            TileInjectionMapping(vram_word=0x200, rom_offset=0x100, tile_data=tile_data),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=sample_rom,
            output_path=output_path,
            tile_mappings=mappings,
            create_backup=False,
        )

        assert result.success is True
        assert result.tiles_written == 1
        assert result.skipped_offsets == [-1]
        assert "skipped 1" in result.message.lower()

    def test_inject_tiles_skips_offset_beyond_rom_size(
        self, tmp_path: Path, sample_rom: Path, tile_data: bytes
    ) -> None:
        """Offsets beyond ROM size should be skipped."""
        output_path = tmp_path / "output.sfc"
        rom_size = sample_rom.stat().st_size
        # Offset that would extend beyond ROM
        bad_offset = rom_size - 16  # Only 16 bytes left, need 32

        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=bad_offset, tile_data=tile_data),
            TileInjectionMapping(vram_word=0x200, rom_offset=0x100, tile_data=tile_data),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=sample_rom,
            output_path=output_path,
            tile_mappings=mappings,
            create_backup=False,
        )

        assert result.success is True
        assert result.tiles_written == 1
        assert bad_offset in result.skipped_offsets

    def test_inject_tiles_all_skipped_still_succeeds(self, tmp_path: Path, sample_rom: Path, tile_data: bytes) -> None:
        """If all tiles are skipped, success is still True (caller decides severity)."""
        output_path = tmp_path / "output.sfc"
        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=-1, tile_data=tile_data),
            TileInjectionMapping(vram_word=0x200, rom_offset=-2, tile_data=tile_data),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=sample_rom,
            output_path=output_path,
            tile_mappings=mappings,
            create_backup=False,
        )

        assert result.success is True
        assert result.tiles_written == 0
        assert len(result.skipped_offsets) == 2


class TestRawTileInjectorAtomicWrite:
    """Tests for atomic write behavior."""

    def test_inject_tiles_same_file_works(self, tmp_path: Path, sample_rom: Path, tile_data: bytes) -> None:
        """Injection with output_path == rom_path should work (in-place update)."""
        original_data = sample_rom.read_bytes()
        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=0x100, tile_data=tile_data),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=sample_rom,
            output_path=sample_rom,  # Same file
            tile_mappings=mappings,
            create_backup=False,
        )

        assert result.success is True
        assert result.tiles_written == 1

        # File should be modified
        new_data = sample_rom.read_bytes()
        assert new_data != original_data
        assert new_data[0x100 : 0x100 + 32] == tile_data

    def test_inject_tiles_atomic_on_write_error(self, tmp_path: Path, sample_rom: Path, tile_data: bytes) -> None:
        """If write fails, original output file should be unchanged."""
        output_path = tmp_path / "output.sfc"
        # Create existing output file
        existing_content = b"ORIGINAL_CONTENT" + bytes(1000)
        output_path.write_bytes(existing_content)

        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=0x100, tile_data=tile_data),
        ]

        injector = RawTileInjector()

        # Patch open to fail during write
        original_open = open

        def failing_open(path, mode="r", *args, **kwargs):
            path_str = str(path)
            if "r+b" in mode and ".tmp" in path_str:
                raise OSError("Simulated write failure")
            return original_open(path, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=failing_open):
            result = injector.inject_tiles(
                rom_path=sample_rom,
                output_path=output_path,
                tile_mappings=mappings,
                create_backup=False,
            )

        assert result.success is False
        assert "write error" in result.message.lower()

        # Original output should be unchanged
        assert output_path.read_bytes() == existing_content

    def test_inject_tiles_no_temp_file_left_on_success(
        self, tmp_path: Path, sample_rom: Path, tile_data: bytes
    ) -> None:
        """No temp files should remain after successful injection."""
        output_path = tmp_path / "output.sfc"
        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=0x100, tile_data=tile_data),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=sample_rom,
            output_path=output_path,
            tile_mappings=mappings,
            create_backup=False,
        )

        assert result.success is True

        # No temp files should exist
        temp_files = list(tmp_path.glob(".spritepal_inject_*"))
        assert temp_files == []

    def test_inject_tiles_no_temp_file_left_on_failure(
        self, tmp_path: Path, sample_rom: Path, tile_data: bytes
    ) -> None:
        """No temp files should remain after failed injection."""
        output_path = tmp_path / "output.sfc"
        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=0x100, tile_data=tile_data),
        ]

        injector = RawTileInjector()

        # Make the temp file path, simulate a failure
        with patch("os.replace", side_effect=OSError("Simulated replace failure")):
            result = injector.inject_tiles(
                rom_path=sample_rom,
                output_path=output_path,
                tile_mappings=mappings,
                create_backup=False,
            )

        assert result.success is False

        # No temp files should remain
        temp_files = list(tmp_path.glob(".spritepal_inject_*"))
        assert temp_files == []


class TestRawTileInjectorValidation:
    """Tests for input validation."""

    def test_inject_tiles_missing_data_fails(self, tmp_path: Path, sample_rom: Path) -> None:
        """Mappings with missing tile_data should cause immediate failure."""
        output_path = tmp_path / "output.sfc"
        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=0x100, tile_data=None),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=sample_rom,
            output_path=output_path,
            tile_mappings=mappings,
            create_backup=False,
        )

        assert result.success is False
        assert "missing data" in result.message.lower()
        assert result.tiles_written == 0
        assert not output_path.exists()

    def test_inject_tiles_rom_not_found_fails(self, tmp_path: Path, tile_data: bytes) -> None:
        """Non-existent ROM should cause immediate failure."""
        output_path = tmp_path / "output.sfc"
        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=0x100, tile_data=tile_data),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=tmp_path / "nonexistent.sfc",
            output_path=output_path,
            tile_mappings=mappings,
            create_backup=False,
        )

        assert result.success is False
        assert "not found" in result.message.lower()


class TestRawTileInjectorBackup:
    """Tests for backup creation."""

    def test_inject_tiles_creates_backup(self, tmp_path: Path, sample_rom: Path, tile_data: bytes) -> None:
        """Backup should be created when output exists and backup requested."""
        output_path = tmp_path / "output.sfc"
        # Create existing output
        original_output = b"EXISTING_OUTPUT" + bytes(1000)
        output_path.write_bytes(original_output)

        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=0x100, tile_data=tile_data),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=sample_rom,
            output_path=output_path,
            tile_mappings=mappings,
            create_backup=True,
        )

        assert result.success is True

        backup_path = output_path.with_suffix(".sfc.bak")
        assert backup_path.exists()
        assert backup_path.read_bytes() == original_output

    def test_inject_tiles_no_backup_when_output_missing(
        self, tmp_path: Path, sample_rom: Path, tile_data: bytes
    ) -> None:
        """No backup created if output file doesn't exist yet."""
        output_path = tmp_path / "output.sfc"
        mappings = [
            TileInjectionMapping(vram_word=0x100, rom_offset=0x100, tile_data=tile_data),
        ]

        injector = RawTileInjector()
        result = injector.inject_tiles(
            rom_path=sample_rom,
            output_path=output_path,
            tile_mappings=mappings,
            create_backup=True,
        )

        assert result.success is True

        backup_path = output_path.with_suffix(".sfc.bak")
        assert not backup_path.exists()


class TestRawTileInjectionResultDataclass:
    """Tests for the result dataclass."""

    def test_skipped_offsets_default_empty(self) -> None:
        """skipped_offsets should default to empty list."""
        result = RawTileInjectionResult(
            success=True,
            output_path="/tmp/test.sfc",
            tiles_written=5,
            message="OK",
        )
        assert result.skipped_offsets == []

    def test_skipped_offsets_mutable_default_isolation(self) -> None:
        """Each instance should have its own skipped_offsets list."""
        result1 = RawTileInjectionResult(success=True, output_path="/a", tiles_written=1, message="OK")
        result2 = RawTileInjectionResult(success=True, output_path="/b", tiles_written=2, message="OK")

        result1.skipped_offsets.append(0x100)

        assert result1.skipped_offsets == [0x100]
        assert result2.skipped_offsets == []
