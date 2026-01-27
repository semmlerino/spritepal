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


@dataclass(frozen=True, slots=True)
class PreviewSnapshot:
    """Snapshot of all transform parameters for debounced preview generation.

    Captured when scheduling preview updates to ensure the preview uses
    the state that triggered it. The compositor needs all transform params.
    """

    offset_x: int
    offset_y: int
    flip_h: bool
    flip_v: bool
    scale: float
    sharpen: float
    resampling: str


@dataclass(frozen=True, slots=True)
class AlignmentState:
    """Complete alignment state for a frame mapping.

    Used for tracking drag-start state (for undo coalescing) and for
    alignment change signals. Contains all parameters that affect how
    the AI frame is positioned and transformed relative to the game frame.
    """

    offset_x: int
    offset_y: int
    flip_h: bool
    flip_v: bool
    scale: float
    sharpen: float
    resampling: str

    def to_preview_snapshot(self) -> PreviewSnapshot:
        """Convert to PreviewSnapshot (identical fields)."""
        return PreviewSnapshot(
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            flip_h=self.flip_h,
            flip_v=self.flip_v,
            scale=self.scale,
            sharpen=self.sharpen,
            resampling=self.resampling,
        )

    @classmethod
    def from_preview_snapshot(cls, snapshot: PreviewSnapshot) -> AlignmentState:
        """Create from PreviewSnapshot (identical fields)."""
        return cls(
            offset_x=snapshot.offset_x,
            offset_y=snapshot.offset_y,
            flip_h=snapshot.flip_h,
            flip_v=snapshot.flip_v,
            scale=snapshot.scale,
            sharpen=snapshot.sharpen,
            resampling=snapshot.resampling,
        )
