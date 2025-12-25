"""
Extraction readiness validation functions.

Provides mode-aware validation for determining when extraction can proceed.
Used by both ExtractionPanel (VRAM dumps) and ROMExtractionPanel (ROM extraction).

This module uses pure functions instead of a stateless service class.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class ExtractionMode(Enum):
    """Extraction mode for VRAM dump extraction."""

    FULL_COLOR = auto()
    GRAYSCALE = auto()


class ROMExtractionMode(Enum):
    """Extraction mode for ROM sprite extraction."""

    PRESET = auto()
    MANUAL = auto()


@dataclass
class ReadinessResult:
    """Result of a readiness check.

    Attributes:
        ready: Whether extraction can proceed
        reasons: List of reasons why not ready (empty if ready)
    """

    ready: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def reason_text(self) -> str:
        """Get reasons as a single string separated by ' | '."""
        return " | ".join(self.reasons)

    @classmethod
    def success(cls) -> ReadinessResult:
        """Create a successful result."""
        return cls(ready=True, reasons=[])

    @classmethod
    def failure(cls, *reasons: str) -> ReadinessResult:
        """Create a failure result with one or more reasons."""
        return cls(ready=False, reasons=list(reasons))


def check_vram_readiness(
    has_vram: bool,
    has_cgram: bool,
    mode: ExtractionMode = ExtractionMode.FULL_COLOR,
) -> ReadinessResult:
    """Check readiness for VRAM dump extraction.

    Args:
        has_vram: Whether VRAM file is loaded
        has_cgram: Whether CGRAM file is loaded
        mode: Current extraction mode

    Returns:
        ReadinessResult indicating if extraction can proceed
    """
    reasons: list[str] = []

    # VRAM is always required
    if not has_vram:
        reasons.append("Load a VRAM file")
        return ReadinessResult(ready=False, reasons=reasons)

    # CGRAM only required for full color mode
    if mode == ExtractionMode.FULL_COLOR and not has_cgram:
        reasons.append("Load a CGRAM file (or use Grayscale mode)")
        return ReadinessResult(ready=False, reasons=reasons)

    return ReadinessResult.success()


def check_rom_extraction_readiness(
    has_rom: bool,
    has_sprite: bool,
    has_output_name: bool,
    mode: ROMExtractionMode = ROMExtractionMode.PRESET,
) -> ReadinessResult:
    """Check readiness for ROM sprite extraction.

    Args:
        has_rom: Whether ROM file is loaded
        has_sprite: Whether a sprite is selected (preset mode only)
        has_output_name: Whether output name is set
        mode: Current extraction mode (preset or manual)

    Returns:
        ReadinessResult indicating if extraction can proceed
    """
    reasons: list[str] = []

    # ROM is always required
    if not has_rom:
        reasons.append("Load a ROM file")

    # Sprite selection required in preset mode
    if mode == ROMExtractionMode.PRESET and not has_sprite:
        reasons.append("Select a sprite preset")

    # Output name always required
    if not has_output_name:
        reasons.append("Enter an output name")

    if reasons:
        return ReadinessResult(ready=False, reasons=reasons)

    return ReadinessResult.success()


def check_generic_readiness(
    requirements: dict[str, tuple[bool, str]],
) -> ReadinessResult:
    """Check readiness using a generic requirements dictionary.

    Useful for custom validation scenarios not covered by specific functions.

    Args:
        requirements: Dict mapping requirement names to (is_met, message_if_not_met)

    Returns:
        ReadinessResult indicating if all requirements are met

    Example:
        >>> check_generic_readiness({
        ...     "rom": (has_rom, "Load a ROM file"),
        ...     "output": (has_output, "Enter output name"),
        ... })
    """
    reasons = [msg for is_met, msg in requirements.values() if not is_met]

    if reasons:
        return ReadinessResult(ready=False, reasons=reasons)

    return ReadinessResult.success()
