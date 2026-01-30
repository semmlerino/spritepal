"""Typed data structures for WorkbenchCanvas.

This module defines frozen dataclasses to replace anonymous tuples for snapshots
and alignment state, providing self-documenting code and IDE assistance.
"""

from __future__ import annotations

from dataclasses import dataclass


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
