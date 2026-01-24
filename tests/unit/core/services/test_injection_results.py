"""Tests for InjectionResult and related dataclasses."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.services.injection_results import (
    InjectionRequest,
    InjectionResult,
    TileInjectionResult,
)


class TestInjectionRequest:
    """Tests for InjectionRequest dataclass."""

    def test_required_fields(self, tmp_path: Path) -> None:
        """Required fields must be provided."""
        request = InjectionRequest(
            ai_frame_index=5,
            rom_path=tmp_path / "game.sfc",
        )
        assert request.ai_frame_index == 5
        assert request.rom_path == tmp_path / "game.sfc"

    def test_default_values(self, tmp_path: Path) -> None:
        """Default values are applied."""
        request = InjectionRequest(
            ai_frame_index=0,
            rom_path=tmp_path / "game.sfc",
        )
        assert request.output_path is None
        assert request.create_backup is True
        assert request.force_raw is False
        assert request.allow_fallback is False
        assert request.preserve_sprite is False
        assert request.emit_project_changed is True

    def test_frozen(self, tmp_path: Path) -> None:
        """Request is immutable."""
        request = InjectionRequest(
            ai_frame_index=0,
            rom_path=tmp_path / "game.sfc",
        )
        with pytest.raises(AttributeError):
            request.ai_frame_index = 10  # type: ignore[misc]


class TestTileInjectionResult:
    """Tests for TileInjectionResult dataclass."""

    def test_success_result(self) -> None:
        """Success result with all fields."""
        result = TileInjectionResult(
            rom_offset=0x10000,
            tile_count=8,
            compression_used="HAL",
            success=True,
            message="Offset 0x10000: Success (8 tiles, HAL)",
        )
        assert result.rom_offset == 0x10000
        assert result.tile_count == 8
        assert result.compression_used == "HAL"
        assert result.success is True

    def test_failure_result(self) -> None:
        """Failure result with message."""
        result = TileInjectionResult(
            rom_offset=0x20000,
            tile_count=4,
            compression_used="RAW",
            success=False,
            message="Offset 0x20000: Failed (data too large)",
        )
        assert result.success is False
        assert "Failed" in result.message


class TestInjectionResult:
    """Tests for InjectionResult dataclass."""

    def test_success_result(self, tmp_path: Path) -> None:
        """Success result with all fields."""
        tile_results = (
            TileInjectionResult(0x10000, 4, "HAL", True, "OK"),
            TileInjectionResult(0x20000, 8, "RAW", True, "OK"),
        )
        result = InjectionResult(
            success=True,
            tile_results=tile_results,
            output_rom_path=tmp_path / "output.sfc",
            messages=("Msg 1", "Msg 2"),
            new_mapping_status="injected",
        )
        assert result.success is True
        assert len(result.tile_results) == 2
        assert result.output_rom_path is not None
        assert result.new_mapping_status == "injected"
        assert result.error is None

    def test_failure_factory(self) -> None:
        """failure() creates failure result."""
        result = InjectionResult.failure("Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.tile_results == ()
        assert result.output_rom_path is None

    def test_stale_entries_factory(self) -> None:
        """stale_entries() creates stale entries result."""
        result = InjectionResult.stale_entries("frame_123", "Entries are stale")
        assert result.success is False
        assert result.error == "Entries are stale"
        assert result.needs_fallback_confirmation is True
        assert result.stale_frame_id == "frame_123"

    def test_default_values(self) -> None:
        """Default values for optional fields."""
        result = InjectionResult(success=True)
        assert result.tile_results == ()
        assert result.output_rom_path is None
        assert result.messages == ()
        assert result.error is None
        assert result.new_mapping_status is None
        assert result.needs_fallback_confirmation is False
        assert result.stale_frame_id is None
