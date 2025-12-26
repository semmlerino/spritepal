"""
Offset controller for VRAM offset coordination.

Manages offset state, debouncing, step sizes, and emits signals
for offset changes. Handles the coordination between slider,
spinbox, presets, and jumps without owning any Qt widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from PySide6.QtCore import QObject, QTimer, Signal

from ui.common.timing_constants import REFRESH_RATE_60FPS
from utils.constants import VRAM_SPRITE_OFFSET
from utils.logging_config import get_logger

logger = get_logger(__name__)


# Preset indices
PRESET_KIRBY_SPRITES = 0
PRESET_CUSTOM_RANGE = 1

# Step size options in bytes
STEP_SIZES: list[int] = [0x20, 0x100, 0x1000, 0x4000]
DEFAULT_STEP_INDEX = 0

# VRAM constants
BYTES_PER_TILE = 32


@dataclass(frozen=True)
class OffsetDisplayInfo:
    """Formatted offset display information.

    Attributes:
        hex_text: Hex representation of the offset (e.g., "0x0C00")
        tile_number: Tile index based on 32 bytes per tile
        percentage: Position as percentage of max range
        tooltip: Full tooltip text with tile and percentage info
    """

    hex_text: str
    tile_number: int
    percentage: float
    tooltip: str


@dataclass(frozen=True)
class JumpLocation:
    """Quick jump location definition.

    Attributes:
        offset: Offset value to jump to
        label: Display label for the jump
    """

    offset: int
    label: str


class OffsetController(QObject):
    """Controller for offset state and coordination.

    Manages the current offset value, handles debouncing for spinbox
    changes, and emits signals for offset updates.

    Signals:
        offset_changed: Emitted when offset value changes (debounced for spinbox)
        offset_changing: Emitted during slider drag for real-time updates
        step_changed: Emitted when step size changes
        mode_changed: Emitted when preset mode changes (is_custom_mode)

    Attributes:
        current_offset: Current offset value
        is_custom_mode: Whether custom range mode is active
        step_size: Current step size in bytes
    """

    offset_changed = Signal(int)  # Debounced offset value
    offset_changing = Signal(int)  # Real-time offset during drag
    step_changed = Signal(int, int)  # (step_size, page_step)
    mode_changed = Signal(bool)  # is_custom_mode

    # Default jump locations
    DEFAULT_JUMPS: ClassVar[list[JumpLocation]] = [
        JumpLocation(0x0000, "Start"),
        JumpLocation(VRAM_SPRITE_OFFSET, "Kirby sprites"),
        JumpLocation(0x8000, "Middle"),
    ]

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        initial_offset: int = VRAM_SPRITE_OFFSET,
        max_offset: int = 0xFFFF,
    ) -> None:
        """Initialize the offset controller.

        Args:
            parent: Parent QObject
            initial_offset: Starting offset value
            max_offset: Maximum offset value for percentage calculation
        """
        super().__init__(parent)

        # State
        self._current_offset = initial_offset
        self._max_offset = max_offset
        self._is_custom_mode = False
        self._step_index = DEFAULT_STEP_INDEX
        self._slider_changing = False

        # Debounce timer
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setInterval(REFRESH_RATE_60FPS)
        self._debounce_timer.setSingleShot(True)
        self._pending_offset: int | None = None
        _ = self._debounce_timer.timeout.connect(self._emit_pending_offset)

    @property
    def current_offset(self) -> int:
        """Get the current offset value."""
        return self._current_offset

    @property
    def is_custom_mode(self) -> bool:
        """Whether custom range mode is active."""
        return self._is_custom_mode

    @property
    def step_size(self) -> int:
        """Current step size in bytes."""
        return STEP_SIZES[self._step_index]

    @property
    def page_step(self) -> int:
        """Page step size (4x single step)."""
        return self.step_size * 4

    def set_max_offset(self, max_offset: int) -> None:
        """Update the maximum offset for percentage calculation.

        Args:
            max_offset: New maximum offset value
        """
        self._max_offset = max_offset

    def set_preset_mode(self, is_custom: bool) -> None:
        """Switch between preset and custom mode.

        Args:
            is_custom: True for custom range, False for Kirby sprites preset
        """
        if self._is_custom_mode == is_custom:
            return  # No change

        self._is_custom_mode = is_custom
        logger.debug(f"Offset mode changed: custom={is_custom}")

        if not is_custom:
            # Reset to Kirby sprite offset
            self._current_offset = VRAM_SPRITE_OFFSET

        self.mode_changed.emit(is_custom)
        self.offset_changed.emit(self._current_offset)

    def on_slider_change(self, value: int) -> None:
        """Handle slider value change.

        Emits offset_changing for real-time updates and updates
        internal state. Does not use debouncing.

        Args:
            value: New slider value
        """
        self._slider_changing = True
        self._current_offset = value

        if self._is_custom_mode:
            self.offset_changing.emit(value)

        self._slider_changing = False

    def on_spinbox_change(self, value: int) -> None:
        """Handle spinbox value change.

        Uses debouncing to avoid excessive updates during typing.
        Only applies debouncing when not triggered by slider.

        Args:
            value: New spinbox value
        """
        self._current_offset = value

        if self._is_custom_mode and not self._slider_changing:
            # Debounce spinbox changes
            self._pending_offset = value
            self._debounce_timer.stop()
            self._debounce_timer.start()

    def set_offset(self, value: int, *, emit: bool = True) -> None:
        """Directly set the offset value.

        Args:
            value: New offset value
            emit: Whether to emit offset_changed signal
        """
        self._current_offset = value
        if emit:
            self.offset_changed.emit(value)

    def set_step_index(self, index: int) -> None:
        """Set the step size by index.

        Args:
            index: Index into STEP_SIZES (0-3)
        """
        if not 0 <= index < len(STEP_SIZES):
            logger.warning(f"Invalid step index: {index}")
            return

        self._step_index = index
        step = STEP_SIZES[index]
        page = step * 4

        logger.debug(f"Step size changed to: 0x{step:04X}")
        self.step_changed.emit(step, page)

    def jump_to_location(self, index: int, *, locations: list[JumpLocation] | None = None) -> int | None:
        """Jump to a predefined location by index.

        Args:
            index: Jump location index (0 is "Select...", 1+ are actual jumps)
            locations: Optional custom locations, uses DEFAULT_JUMPS if None

        Returns:
            The offset jumped to, or None if index 0 (placeholder) was selected
        """
        if index <= 0:
            return None

        jumps = locations or self.DEFAULT_JUMPS
        jump_index = index - 1  # Adjust for "Select..." placeholder at index 0

        if not 0 <= jump_index < len(jumps):
            logger.warning(f"Invalid jump index: {index}")
            return None

        location = jumps[jump_index]
        self._current_offset = location.offset
        logger.debug(f"Jumped to offset: 0x{location.offset:04X} ({location.label})")

        self.offset_changed.emit(self._current_offset)
        return self._current_offset

    def get_display_info(self, offset: int | None = None) -> OffsetDisplayInfo:
        """Get formatted display information for an offset.

        Args:
            offset: Offset to format, uses current_offset if None

        Returns:
            OffsetDisplayInfo with hex text, tile number, percentage, and tooltip
        """
        value = offset if offset is not None else self._current_offset

        hex_text = f"0x{value:04X}"
        tile_number = value // BYTES_PER_TILE

        if self._max_offset > 0:
            percentage = (value / self._max_offset) * 100
        else:
            percentage = 0.0

        tooltip = f"Current offset in VRAM\nTile #{tile_number} | {percentage:.1f}%"

        return OffsetDisplayInfo(
            hex_text=hex_text,
            tile_number=tile_number,
            percentage=percentage,
            tooltip=tooltip,
        )

    def parse_jump_text(self, text: str) -> int | None:
        """Parse a jump combo text to extract the offset.

        Args:
            text: Text like "0xC000 - Kirby sprites"

        Returns:
            Parsed offset or None if parsing fails
        """
        hex_part = text.split(" - ")[0]
        try:
            return int(hex_part, 16)
        except ValueError:
            logger.warning(f"Invalid jump offset: {hex_part}")
            return None

    def _emit_pending_offset(self) -> None:
        """Emit the pending offset after debounce delay."""
        try:
            if self._pending_offset is not None:
                offset_value = self._pending_offset
                logger.debug(f"Emitting debounced offset change: {offset_value} (0x{offset_value:04X})")
                self.offset_changed.emit(offset_value)
                self._pending_offset = None
        except RuntimeError:
            # Widget may have been deleted
            pass
        except Exception:
            logger.exception("Error in debounced offset emission")

    def cleanup(self) -> None:
        """Clean up timer resources."""
        self._debounce_timer.stop()
