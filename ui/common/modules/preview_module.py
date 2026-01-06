"""
Preview Module for dependency injection.

Provides a lightweight wrapper around SmartPreviewCoordinator to enable
dependency injection and resource sharing across components.

Key benefits:
- Components don't create their own coordinators internally
- Enables single shared worker pool across application
- OR isolation when needed (fresh instance per context)
- Clean interface for testing and mocking
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QSlider

from ui.common.smart_preview_coordinator import SmartPreviewCoordinator
from utils.logging_config import get_logger

logger = get_logger(__name__)


class PreviewModule(QObject):
    """Injectable wrapper for preview coordination.

    Provides a consistent interface for preview generation that can be:
    - Shared across components (single worker pool)
    - OR created fresh per context (isolation)

    The key benefit is dependency injection - components don't create
    their own coordinators internally.

    Example usage:
        # In application setup (shared resources)
        preview_module = PreviewModule(rom_extractor)

        # In dialog/panel (injected dependency)
        dialog = ManualOffsetDialog(preview_module=preview_module)

        # Request preview
        preview_module.request_preview(
            offset=0x123456,
            rom_path="/path/to/rom.sfc"
        )

    Signals:
        preview_ready: Emitted when preview is ready
            (tile_data: bytes, width: int, height: int, sprite_name: str, compressed_size: int, slack_size: int)
        preview_cached: Emitted when cached preview is displayed
            (tile_data: bytes, width: int, height: int, sprite_name: str, compressed_size: int, slack_size: int)
        preview_error: Emitted when preview generation fails (error_msg: str)
    """

    # Forwarded signals from coordinator
    preview_ready = Signal(bytes, int, int, str, int, int)  # tile_data, w, h, name, compressed_size, slack_size
    preview_cached = Signal(bytes, int, int, str, int, int)  # Cached preview displayed, with compressed_size, slack_size
    preview_error = Signal(str)  # Error message

    def __init__(
        self,
        rom_extractor: ROMExtractor,
        parent: QObject | None = None,
    ) -> None:
        """Create preview module with shared resources.

        Args:
            rom_extractor: Shared ROM extractor instance
            parent: Parent QObject for memory management
        """
        super().__init__(parent)

        self._rom_extractor = rom_extractor
        self._coordinator = SmartPreviewCoordinator(parent=self)

        # Forward signals from coordinator
        self._coordinator.preview_ready.connect(self.preview_ready.emit)
        self._coordinator.preview_cached.connect(self.preview_cached.emit)
        self._coordinator.preview_error.connect(self.preview_error.emit)

        # Set up ROM data provider
        self._coordinator.set_rom_data_provider(self._get_rom_data)

        logger.debug("PreviewModule initialized")

    def _get_rom_data(self) -> tuple[str, object] | None:
        """Provide ROM data to coordinator.

        Returns:
            Tuple of (rom_path, rom_extractor) or None if unavailable
        """
        # For now, we don't track a specific ROM path in the module.
        # The rom_path will be provided via request_preview().
        # This provider is mainly for the coordinator's internal use.
        # We'll store the most recent rom_path for cache key generation.
        if hasattr(self, "_current_rom_path") and self._current_rom_path:
            return (self._current_rom_path, self._rom_extractor)
        return None

    def request_preview(
        self,
        offset: int,
        rom_path: str,
        callback: Callable[..., object] | None = None,
    ) -> None:
        """Request preview generation at offset.

        Args:
            offset: ROM offset for preview extraction
            rom_path: Path to ROM file
            callback: Optional callback for completion (forwarded to coordinator)
        """
        # Store rom_path for provider
        self._current_rom_path = rom_path

        # Forward to coordinator
        self._coordinator.request_preview(offset)

    def request_manual_preview(self, offset: int, rom_path: str) -> None:
        """Request preview for manual offset change (bypasses debouncing).

        Args:
            offset: ROM offset for preview extraction
            rom_path: Path to ROM file
        """
        # Store rom_path for provider
        self._current_rom_path = rom_path

        # Forward to coordinator
        self._coordinator.request_manual_preview(offset)

    def request_background_preload(self, offset: int, rom_path: str) -> None:
        """Request background preloading of offset without affecting display.

        This method caches previews for adjacent offsets but does NOT:
        - Update current offset (preserves user's position)
        - Emit UI signals (no visual feedback)
        - Affect current preview display

        Args:
            offset: ROM offset to preload
            rom_path: Path to ROM file
        """
        # Store rom_path for provider (but don't overwrite if this is just preloading)
        if not hasattr(self, "_current_rom_path") or not self._current_rom_path:
            self._current_rom_path = rom_path

        # Forward to coordinator
        self._coordinator.request_background_preload(offset)

    def cancel_pending(self) -> None:
        """Cancel any pending preview requests.

        Note: The coordinator handles request cancellation internally
        via request IDs. This method is provided for API completeness.
        """
        # The coordinator automatically cancels stale requests via request_id tracking
        logger.debug("cancel_pending called (coordinator handles this internally)")

    def connect_to_slider(self, slider: QSlider) -> None:
        """Connect to slider for drag-aware preview timing.

        Args:
            slider: QSlider to monitor for drag events
        """
        self._coordinator.connect_slider(slider)
        logger.debug(f"Connected PreviewModule to slider: {slider.objectName()}")

    def set_ui_update_callback(self, callback: Callable[[int], None]) -> None:
        """Set callback for immediate UI updates during dragging.

        Args:
            callback: Function to call with offset during drag operations
        """
        self._coordinator.set_ui_update_callback(callback)

    @property
    def coordinator(self) -> SmartPreviewCoordinator:
        """Access to internal coordinator for components that need direct access.

        Returns:
            The internal SmartPreviewCoordinator instance
        """
        return self._coordinator

    def shutdown(self) -> None:
        """Clean up resources and stop background workers."""
        logger.debug("PreviewModule shutting down")
        self._coordinator.cleanup()
