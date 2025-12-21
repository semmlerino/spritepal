"""
Protocol definitions for preview coordinators.

These protocols define the interfaces for preview coordination components,
enabling dependency injection and better testability.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QSlider


class PreviewCoordinatorProtocol(Protocol):
    """Protocol for preview coordinators.

    This protocol defines the interface for SmartPreviewCoordinator,
    enabling type-safe usage and better testability through dependency injection.
    """

    # Signals (accessed via attributes)
    preview_ready: Signal  # Signal(bytes, int, int, str) - tile_data, width, height, name
    preview_cached: Signal  # Signal(bytes, int, int, str) - cached preview displayed
    preview_error: Signal  # Signal(str) - error message

    def connect_slider(self, slider: QSlider) -> None:
        """Connect to slider signals for preview coordination.

        Args:
            slider: The slider widget to connect to
        """
        ...

    def set_ui_update_callback(self, callback: Callable[..., None]) -> None:
        """Set callback for UI updates.

        Args:
            callback: Callback function for UI updates
        """
        ...

    def set_rom_data_provider(
        self, provider: Callable[[], tuple[str, object, object] | None]
    ) -> None:
        """Set provider for ROM data needed for preview generation.

        Args:
            provider: Callable that returns (rom_path, extractor, rom_cache) or None
        """
        ...

    def request_preview(self, offset: int, priority: int = 0) -> None:
        """Request a preview at the given offset.

        Args:
            offset: The ROM offset to generate preview for
            priority: Priority for the request (lower = higher priority, -1 for background)
        """
        ...

    def request_manual_preview(self, offset: int) -> None:
        """Request a manual preview (higher priority).

        Args:
            offset: The ROM offset to generate preview for
        """
        ...

    def cleanup(self) -> None:
        """Clean up resources and stop any pending operations."""
        ...
