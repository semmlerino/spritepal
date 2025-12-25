"""
Controller for ROM extraction parameters and readiness.

Manages mode state (preset vs manual), validates readiness,
and builds extraction parameters for the worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from core.services.extraction_readiness_service import (
    ReadinessResult,
    ROMExtractionMode,
    check_rom_extraction_readiness,
)
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


@dataclass(frozen=True)
class ExtractionParams:
    """Immutable extraction parameters for the worker.

    Attributes:
        rom_path: Path to the ROM file
        sprite_offset: Offset within ROM for sprite data
        sprite_name: Name for the sprite (from preset or manual)
        output_base: Base name for output files
        cgram_path: Optional path to CGRAM file for palette
    """

    rom_path: str
    sprite_offset: int
    sprite_name: str
    output_base: str
    cgram_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dict for backward compatibility with existing code."""
        return {
            "rom_path": self.rom_path,
            "sprite_offset": self.sprite_offset,
            "sprite_name": self.sprite_name,
            "output_base": self.output_base,
            "cgram_path": self.cgram_path,
        }


# Default offset for manual mode (2MB ROM boundary)
ROM_SIZE_2MB = 0x200000


class ExtractionParamsController(QObject):
    """Controller for managing extraction parameters and readiness state.

    This controller owns the mode state (preset vs manual) and provides
    validation of extraction readiness. It emits signals when state changes
    so the panel can update the UI accordingly.

    Signals:
        readiness_changed: Emitted when extraction readiness changes.
            Args: (ready: bool, reason: str)
        mode_changed: Emitted when mode switches between preset and manual.
            Args: (is_manual: bool)

    Example usage:
        controller = ExtractionParamsController()
        controller.readiness_changed.connect(panel.on_readiness_changed)

        # Set manual mode with specific offset
        controller.set_manual_mode(True, offset=0x100000)

        # Check readiness with current state
        controller.check_readiness(
            has_rom=True,
            has_sprite=False,  # Not needed in manual mode
            has_output_name=True,
        )

        # Build params for extraction
        params = controller.build_params(
            rom_path="/path/to/rom.sfc",
            output_base="my_sprite",
            sprite_data=None,  # Manual mode uses stored offset
            cgram_path=None,
        )
    """

    readiness_changed = Signal(bool, str)  # (ready, reason_text)
    mode_changed = Signal(bool)  # (is_manual_mode)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the controller.

        Args:
            parent: Parent QObject for proper Qt lifecycle management
        """
        super().__init__(parent)
        self._manual_mode = False
        self._manual_offset = ROM_SIZE_2MB
        self._last_readiness: ReadinessResult | None = None

    @property
    def is_manual_mode(self) -> bool:
        """Whether the controller is in manual offset mode."""
        return self._manual_mode

    @property
    def manual_offset(self) -> int:
        """The current manual offset value."""
        return self._manual_offset

    def set_manual_mode(self, enabled: bool, offset: int | None = None) -> None:
        """Set manual mode state.

        Args:
            enabled: Whether to enable manual mode
            offset: Optional offset to set (if not provided, keeps current)
        """
        if offset is not None:
            self._manual_offset = offset

        if self._manual_mode != enabled:
            self._manual_mode = enabled
            logger.debug(f"Mode changed: manual={enabled}, offset=0x{self._manual_offset:X}")
            self.mode_changed.emit(enabled)

    def set_preset_mode(self, offset: int | None = None) -> None:
        """Switch to preset mode (sprite picker visible).

        Args:
            offset: Optional offset to store for potential manual use later
        """
        if offset is not None:
            self._manual_offset = offset
        self.set_manual_mode(enabled=False)

    def set_offset(self, offset: int) -> None:
        """Update the manual offset value.

        Args:
            offset: New offset value
        """
        self._manual_offset = offset
        logger.debug(f"Manual offset set: 0x{offset:X}")

    def check_readiness(
        self,
        *,
        has_rom: bool,
        has_sprite: bool,
        has_output_name: bool,
    ) -> ReadinessResult:
        """Check if extraction is ready given current state.

        Uses the extraction readiness service for mode-aware validation.

        Args:
            has_rom: Whether a ROM file is loaded
            has_sprite: Whether a sprite is selected (ignored in manual mode)
            has_output_name: Whether an output name is provided

        Returns:
            ReadinessResult with ready status and any failure reasons
        """
        mode = ROMExtractionMode.MANUAL if self._manual_mode else ROMExtractionMode.PRESET

        result = check_rom_extraction_readiness(
            has_rom=has_rom,
            has_sprite=has_sprite,
            has_output_name=has_output_name,
            mode=mode,
        )

        # Only emit if changed
        if self._last_readiness is None or result != self._last_readiness:
            self._last_readiness = result
            self.readiness_changed.emit(result.ready, result.reason_text)
            logger.debug(f"Readiness changed: ready={result.ready}, reasons={result.reasons}")

        return result

    def build_params(
        self,
        *,
        rom_path: str | Path,
        output_base: str,
        sprite_data: tuple[str, int] | None,
        cgram_path: str | Path | None = None,
    ) -> ExtractionParams | None:
        """Build extraction parameters.

        In manual mode, uses the stored offset. In preset mode, uses
        the sprite_data tuple.

        Args:
            rom_path: Path to the ROM file
            output_base: Base name for output files
            sprite_data: Tuple of (sprite_name, offset) from preset selector,
                         or None if in manual mode
            cgram_path: Optional path to CGRAM file

        Returns:
            ExtractionParams if all required data is available, None otherwise
        """
        if not rom_path:
            logger.debug("build_params: No ROM path")
            return None

        rom_path_str = str(rom_path)

        if self._manual_mode:
            offset = self._manual_offset
            sprite_name = f"manual_0x{offset:X}"
        else:
            # Preset mode - need sprite data
            if not sprite_data:
                logger.debug("build_params: No sprite data in preset mode")
                return None
            sprite_name, offset = sprite_data

        cgram_path_str = str(cgram_path) if cgram_path else None

        return ExtractionParams(
            rom_path=rom_path_str,
            sprite_offset=offset,
            sprite_name=sprite_name,
            output_base=output_base,
            cgram_path=cgram_path_str,
        )

    def get_params_dict(
        self,
        *,
        rom_path: str | Path,
        output_base: str,
        sprite_data: tuple[str, int] | None,
        cgram_path: str | Path | None = None,
    ) -> dict[str, object] | None:
        """Build extraction parameters as a dict.

        Convenience method for backward compatibility with existing code
        that expects dict return values.

        Args:
            rom_path: Path to the ROM file
            output_base: Base name for output files
            sprite_data: Tuple of (sprite_name, offset) from preset selector
            cgram_path: Optional path to CGRAM file

        Returns:
            Dict with extraction params if available, None otherwise
        """
        params = self.build_params(
            rom_path=rom_path,
            output_base=output_base,
            sprite_data=sprite_data,
            cgram_path=cgram_path,
        )
        return params.to_dict() if params else None

    def reset(self) -> None:
        """Reset controller to initial state."""
        self._manual_mode = False
        self._manual_offset = ROM_SIZE_2MB
        self._last_readiness = None
        self.mode_changed.emit(False)
        logger.debug("ExtractionParamsController reset to initial state")
