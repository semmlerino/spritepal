"""
Preview result processor for ROM workflow.

Extracts decision logic from _on_preview_ready() into a pure processor
that computes actions without mutating state. The controller applies
the computed actions to its own state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.types import CompressionType

if TYPE_CHECKING:
    from core.services.signal_payloads import PreviewData


@dataclass(frozen=True)
class PreviewActions:
    """Computed actions from preview result - no mutation, just decisions.

    This dataclass captures all decisions computed from a preview payload,
    allowing the controller to apply them in a single pass.
    """

    # Offset adjustment info
    offset_adjusted: bool
    """Whether the offset was adjusted during preview (e.g., alignment correction)."""

    old_offset: int
    """Original offset before any adjustment."""

    actual_offset: int
    """Final offset after any adjustment."""

    offset_delta: int
    """Difference between actual and old offset (0 if no adjustment)."""

    # Preview data (pass-through from payload)
    tile_data: bytes
    """Decompressed tile data."""

    width: int
    """Sprite width in tiles."""

    height: int
    """Sprite height in tiles."""

    sprite_name: str
    """Display name for the sprite."""

    compressed_size: int
    """Original compressed size in bytes."""

    slack_size: int
    """Available slack space after compressed data."""

    header_bytes: bytes
    """Header bytes stripped during alignment (prepended back during injection)."""

    # Computed values
    compression_type: CompressionType
    """Determined compression type (HAL or RAW)."""

    status_message: str
    """User-facing status message describing the preview result."""

    # Auto-open decision
    should_auto_open: bool
    """Whether to automatically open in editor (from pending flag + offset match)."""

    should_warn_unusual_size: bool
    """Whether to warn about unusual (non-32-byte-multiple) sprite size."""


class PreviewResultProcessor:
    """
    Stateless processor that computes actions from preview results.

    This extracts the decision logic from ROMWorkflowController._on_preview_ready()
    into a testable, pure function. The controller calls process() and then
    applies the returned actions to its state.

    Benefits:
    - Testable without Qt widgets or controller state
    - Clear separation between decision logic and state mutation
    - Easier to reason about preview behavior
    """

    @staticmethod
    def process(
        payload: PreviewData,
        *,
        current_offset: int,
        pending_open_in_editor: bool,
        pending_open_offset: int,
    ) -> PreviewActions:
        """Process a preview payload and compute resulting actions.

        Args:
            payload: PreviewData with tile data and metadata from preview worker.
            current_offset: The offset the controller currently has selected.
            pending_open_in_editor: Whether auto-open was requested (double-click).
            pending_open_offset: The offset that triggered pending open (-1 for any).

        Returns:
            PreviewActions dataclass with computed decisions and pass-through data.
        """
        # Determine actual offset (use current if not provided in payload)
        actual_offset = payload.actual_offset
        if actual_offset == -1:
            actual_offset = current_offset

        # Check if offset was adjusted during preview
        offset_adjusted = actual_offset != current_offset
        offset_delta = actual_offset - current_offset if offset_adjusted else 0
        old_offset = current_offset

        # Determine compression type
        hal_succeeded = payload.hal_succeeded
        compression_type = CompressionType.HAL if hal_succeeded else CompressionType.RAW

        # Build status message
        if hal_succeeded:
            slack_info = f" (+{payload.slack_size} slack)" if payload.slack_size > 0 else ""
            status_message = f"Sprite found! Original size: {payload.compressed_size} bytes{slack_info}"
            if offset_adjusted:
                status_message += f" (Aligned to 0x{actual_offset:06X})"
        else:
            # Raw sprite - can be edited and injected without compression
            status_message = (
                f"Raw sprite data at 0x{actual_offset:06X} ({len(payload.tile_data)} bytes, no HAL compression)"
            )

        # Determine auto-open behavior
        # Only auto-open if:
        # 1. pending_open_in_editor flag is set (double-click triggered it)
        # 2. pending_open_offset matches actual_offset OR is -1 (any offset)
        should_auto_open = pending_open_in_editor and (pending_open_offset in (-1, actual_offset))

        # Check for unusual size (not multiple of 32 bytes = SNES tile size)
        should_warn_unusual_size = should_auto_open and len(payload.tile_data) % 32 != 0

        return PreviewActions(
            offset_adjusted=offset_adjusted,
            old_offset=old_offset,
            actual_offset=actual_offset,
            offset_delta=offset_delta,
            tile_data=payload.tile_data,
            width=payload.width,
            height=payload.height,
            sprite_name=payload.sprite_name,
            compressed_size=payload.compressed_size,
            slack_size=payload.slack_size,
            header_bytes=payload.header_bytes,
            compression_type=compression_type,
            status_message=status_message,
            should_auto_open=should_auto_open,
            should_warn_unusual_size=should_warn_unusual_size,
        )
