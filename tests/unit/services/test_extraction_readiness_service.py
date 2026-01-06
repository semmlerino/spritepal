"""Unit tests for extraction readiness service."""

from __future__ import annotations

import pytest

from core.services.extraction_readiness_service import (
    ExtractionMode,
    ReadinessResult,
    ROMExtractionMode,
    check_generic_readiness,
    check_rom_extraction_readiness,
    check_vram_readiness,
)


class TestReadinessResult:
    """Tests for ReadinessResult dataclass."""

    def test_success_creates_ready_result(self) -> None:
        """Success should create a ready result."""
        result = ReadinessResult.success()
        assert result.ready is True
        assert result.reasons == []

    def test_failure_creates_not_ready_result(self) -> None:
        """Failure should create a not-ready result with reasons."""
        result = ReadinessResult.failure("Reason 1", "Reason 2")
        assert result.ready is False
        assert result.reasons == ["Reason 1", "Reason 2"]

    def test_reason_text_joins_with_pipe(self) -> None:
        """reason_text should join reasons with ' | '."""
        result = ReadinessResult(ready=False, reasons=["A", "B", "C"])
        assert result.reason_text == "A | B | C"

    def test_reason_text_empty_for_success(self) -> None:
        """reason_text should be empty for success."""
        result = ReadinessResult.success()
        assert result.reason_text == ""


class TestCheckVramReadiness:
    """Tests for check_vram_readiness function."""

    def test_requires_vram(self) -> None:
        """Should require VRAM file."""
        result = check_vram_readiness(has_vram=False, has_cgram=True)
        assert result.ready is False
        assert "Load a VRAM file" in result.reasons

    def test_requires_cgram_in_full_color_mode(self) -> None:
        """Should require CGRAM in full color mode."""
        result = check_vram_readiness(
            has_vram=True,
            has_cgram=False,
            mode=ExtractionMode.FULL_COLOR,
        )
        assert result.ready is False
        assert "Load a CGRAM file (or use Grayscale mode)" in result.reasons

    def test_cgram_optional_in_grayscale_mode(self) -> None:
        """Should not require CGRAM in grayscale mode."""
        result = check_vram_readiness(
            has_vram=True,
            has_cgram=False,
            mode=ExtractionMode.GRAYSCALE,
        )
        assert result.ready is True

    def test_ready_with_all_files_full_color(self) -> None:
        """Should be ready with all files in full color mode."""
        result = check_vram_readiness(
            has_vram=True,
            has_cgram=True,
            mode=ExtractionMode.FULL_COLOR,
        )
        assert result.ready is True

    def test_ready_with_vram_only_grayscale(self) -> None:
        """Should be ready with only VRAM in grayscale mode."""
        result = check_vram_readiness(
            has_vram=True,
            has_cgram=False,
            mode=ExtractionMode.GRAYSCALE,
        )
        assert result.ready is True


class TestCheckRomExtractionReadiness:
    """Tests for check_rom_extraction_readiness function."""

    def test_requires_rom(self) -> None:
        """Should require ROM file."""
        result = check_rom_extraction_readiness(
            has_rom=False,
            has_sprite=True,
            has_output_name=True,
        )
        assert result.ready is False
        assert "Load a ROM file" in result.reasons

    def test_requires_sprite_in_preset_mode(self) -> None:
        """Should require sprite selection in preset mode."""
        result = check_rom_extraction_readiness(
            has_rom=True,
            has_sprite=False,
            has_output_name=True,
            mode=ROMExtractionMode.PRESET,
        )
        assert result.ready is False
        assert "Select a sprite preset" in result.reasons

    def test_sprite_optional_in_manual_mode(self) -> None:
        """Should not require sprite selection in manual mode."""
        result = check_rom_extraction_readiness(
            has_rom=True,
            has_sprite=False,
            has_output_name=True,
            mode=ROMExtractionMode.MANUAL,
        )
        assert result.ready is True

    def test_output_name_is_optional(self) -> None:
        """Output name is optional for readiness (can be set at extraction time)."""
        result = check_rom_extraction_readiness(
            has_rom=True,
            has_sprite=True,
            has_output_name=False,
        )
        # Output name is optional - readiness depends only on ROM and sprite
        assert result.ready is True

    def test_ready_with_all_requirements_preset(self) -> None:
        """Should be ready with all requirements in preset mode."""
        result = check_rom_extraction_readiness(
            has_rom=True,
            has_sprite=True,
            has_output_name=True,
            mode=ROMExtractionMode.PRESET,
        )
        assert result.ready is True

    def test_ready_with_all_requirements_manual(self) -> None:
        """Should be ready with all requirements in manual mode."""
        result = check_rom_extraction_readiness(
            has_rom=True,
            has_sprite=False,  # Not needed in manual mode
            has_output_name=True,
            mode=ROMExtractionMode.MANUAL,
        )
        assert result.ready is True

    def test_multiple_missing_requirements(self) -> None:
        """Should report all missing requirements (ROM and sprite in preset mode)."""
        result = check_rom_extraction_readiness(
            has_rom=False,
            has_sprite=False,
            has_output_name=False,
            mode=ROMExtractionMode.PRESET,
        )
        assert result.ready is False
        # Only ROM and sprite are required (output_name is optional)
        assert len(result.reasons) == 2


class TestCheckGenericReadiness:
    """Tests for check_generic_readiness function."""

    def test_all_met_is_ready(self) -> None:
        """Should be ready when all requirements are met."""
        result = check_generic_readiness(
            {
                "req1": (True, "Requirement 1 not met"),
                "req2": (True, "Requirement 2 not met"),
            }
        )
        assert result.ready is True

    def test_some_not_met_is_not_ready(self) -> None:
        """Should not be ready when some requirements are not met."""
        result = check_generic_readiness(
            {
                "req1": (True, "Requirement 1 not met"),
                "req2": (False, "Requirement 2 not met"),
            }
        )
        assert result.ready is False
        assert "Requirement 2 not met" in result.reasons

    def test_reports_all_unmet_requirements(self) -> None:
        """Should report all unmet requirements."""
        result = check_generic_readiness(
            {
                "req1": (False, "Missing 1"),
                "req2": (False, "Missing 2"),
                "req3": (True, "Not missing"),
            }
        )
        assert result.ready is False
        assert len(result.reasons) == 2
        assert "Missing 1" in result.reasons
        assert "Missing 2" in result.reasons

    def test_empty_requirements_is_ready(self) -> None:
        """Should be ready with no requirements."""
        result = check_generic_readiness({})
        assert result.ready is True
