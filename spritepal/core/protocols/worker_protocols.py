"""
Protocol definitions for worker pools to break circular dependencies.

These protocols define the interfaces that worker pools must implement,
enabling the core layer to use workers without importing from the UI layer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PySide6.QtCore import SignalInstance


class PreviewWorkerPoolProtocol(Protocol):
    """
    Protocol for preview worker pool implementations.

    This protocol defines the interface expected by PreviewOrchestrator.
    Implementations must provide:
    - preview_ready signal: Emitted when preview generation completes
    - preview_error signal: Emitted when preview generation fails
    - generate_preview method: Submits a preview generation request
    - cleanup method: Cleans up worker pool resources
    """

    preview_ready: SignalInstance  # (request_id, preview_data)
    preview_error: SignalInstance  # (request_id, error_msg)

    def generate_preview(
        self, request_id: str, rom_path: str, offset: int
    ) -> None:
        """
        Submit a preview generation request.

        Args:
            request_id: Unique identifier for this request
            rom_path: Path to the ROM file
            offset: Offset within the ROM for sprite data
        """
        ...

    def cleanup(self) -> None:
        """Clean up worker pool resources."""
        ...
