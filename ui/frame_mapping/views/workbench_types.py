"""Typed data structures for WorkbenchCanvas.

This module defines frozen dataclasses to replace anonymous tuples for snapshots
and alignment state, providing self-documenting code and IDE assistance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMapping


@dataclass(frozen=True, slots=True)
class TileCalcSnapshot:
    """Snapshot of alignment state for debounced tile calculation.

    Captured when scheduling tile touch updates to ensure the calculation
    uses the state that triggered it, even if alignment changes before
    the timer fires.
    """

    offset_x: int
    offset_y: int
    scale: float
    flip_h: bool = False
    flip_v: bool = False


@dataclass(frozen=True, slots=True)
class AlignmentState:
    """Complete alignment state for a frame mapping.

    Used for:
    - Tracking drag-start state (for undo coalescing)
    - Alignment change signals
    - Debounced preview generation snapshots

    Contains all parameters that affect how the AI frame is positioned
    and transformed relative to the game frame.
    """

    offset_x: int
    offset_y: int
    flip_h: bool
    flip_v: bool
    scale: float
    sharpen: float
    resampling: str

    @classmethod
    def from_mapping(cls, mapping: FrameMapping) -> AlignmentState:
        """Create AlignmentState from a FrameMapping's alignment fields."""
        return cls(
            offset_x=mapping.offset_x,
            offset_y=mapping.offset_y,
            flip_h=mapping.flip_h,
            flip_v=mapping.flip_v,
            scale=mapping.scale,
            sharpen=mapping.sharpen,
            resampling=mapping.resampling,
        )
