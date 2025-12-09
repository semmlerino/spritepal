"""
Simple Preview Coordinator - A simplified replacement for SmartPreviewCoordinator.

This implementation removes the complex worker pool and uses simple one-shot
QThread workers for each preview request. This approach is simpler and more
robust, avoiding the complex signal lifecycle management that was causing crashes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typing_extensions import override

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ROMCacheProtocol

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from utils.logging_config import get_logger

logger = get_logger(__name__)

class SimplePreviewWorker(QThread):
    """Simple one-shot preview worker that generates a preview and exits."""

    preview_ready = Signal(bytes, int, int, str)  # tile_data, width, height, name
    preview_error = Signal(str)

    def __init__(self, rom_path: str, offset: int, extractor: Any, parent: QObject | None = None):
        super().__init__(parent)
        self.rom_path = rom_path
        self.offset = offset
        self.extractor = extractor
        self.sprite_name = f"manual_0x{offset:X}"

    @override
    def run(self) -> None:
        """Generate the preview."""
        try:
            logger.debug(f"[SIMPLE] Generating preview for offset 0x{self.offset:X}")

            # Read ROM data
            with Path(self.rom_path).open("rb") as f:
                rom_data = f.read()

            # For manual browsing, try decompression first (most sprites are compressed)
            expected_size = 8192  # Typical sprite size
            tile_data = None

            # Try decompression first - most sprites in Kirby are HAL-compressed
            if self.extractor and hasattr(self.extractor, 'rom_injector'):
                try:
                    compressed_size, decompressed_data = (
                        self.extractor.rom_injector.find_compressed_sprite(
                            rom_data, self.offset, expected_size
                        )
                    )
                    if decompressed_data and len(decompressed_data) > 0:
                        logger.debug(f"[SIMPLE] Found compressed sprite: {compressed_size} bytes -> {len(decompressed_data)} bytes")
                        tile_data = decompressed_data
                except Exception as decomp_error:
                    # Not a compressed sprite, will use raw data
                    logger.debug(f"[SIMPLE] Not a compressed sprite: {decomp_error}")

            # Fall back to raw data if decompression failed or no extractor
            if not tile_data:
                try:
                    # Extract raw tile data for browsing
                    expected_size = 4096  # 4KB for raw browsing
                    if self.offset + expected_size <= len(rom_data):
                        tile_data = rom_data[self.offset:self.offset + expected_size]
                    else:
                        tile_data = rom_data[self.offset:]
                    logger.debug(f"[SIMPLE] Using raw data: {len(tile_data)} bytes")
                except Exception as e:
                    logger.error(f"[SIMPLE] Failed to extract raw data: {e}")
                    raise ValueError(f"Failed to extract at 0x{self.offset:X}: {e}") from e

            if not tile_data:
                raise ValueError(f"No data at offset 0x{self.offset:X}")

            # Calculate dimensions
            num_tiles = len(tile_data) // 32
            if num_tiles == 0:
                raise ValueError("No complete tiles found")

            tiles_per_row = 16
            tile_rows = (num_tiles + tiles_per_row - 1) // tiles_per_row
            width = min(tiles_per_row * 8, 128)
            height = min(tile_rows * 8, 128)

            # Emit the preview
            logger.debug(f"[SIMPLE] Emitting preview: {width}x{height}, {len(tile_data)} bytes")
            self.preview_ready.emit(tile_data, width, height, self.sprite_name)

        except Exception as e:
            logger.error(f"[SIMPLE] Error generating preview: {e}")
            self.preview_error.emit(str(e))

class SimplePreviewCoordinator(QObject):
    """
    Simplified preview coordinator that uses one-shot workers.

    This replaces the complex SmartPreviewCoordinator with a simpler approach:
    - Creates a new worker for each preview request
    - No worker pooling or reuse
    - Simple timer-based debouncing
    - No complex signal lifecycle management
    """

    # Signals for preview updates
    preview_ready = Signal(bytes, int, int, str)  # tile_data, width, height, name
    preview_cached = Signal(bytes, int, int, str)  # For compatibility
    preview_error = Signal(str)

    def __init__(self, parent: QObject | None = None, rom_cache: ROMCacheProtocol | None = None):
        super().__init__(parent)

        # Current state
        self._current_offset = 0
        self._current_rom_path = ""
        self._extractor = None
        self._current_worker = None

        # Debounce timer
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._generate_preview)

        # Store ROM cache for compatibility (not used in simple version)
        self._rom_cache = rom_cache

        # ROM data provider for compatibility with existing code
        self._rom_data_provider = None

        logger.info("[SIMPLE] SimplePreviewCoordinator initialized")

    def attach_slider(self, slider: Any) -> None:
        """Attach to a slider for automatic preview updates."""
        # For compatibility - we don't actually use the slider
        logger.debug("[SIMPLE] Slider attached (no-op)")

    def set_rom_data_provider(self, provider: Any) -> None:
        """Set provider for ROM data needed for preview generation."""
        self._rom_data_provider = provider
        logger.debug("[SIMPLE] ROM data provider set")

    def connect_slider(self, slider: Any) -> None:
        """Connect to slider signals for preview coordination."""
        # For compatibility - we don't use the slider's signals
        logger.debug("[SIMPLE] Slider connected (no-op)")

    def set_ui_update_callback(self, callback: Callable[..., Any]) -> None:
        """Set callback for UI updates."""
        # For compatibility - we don't use this callback
        logger.debug("[SIMPLE] UI update callback set (no-op)")

    def request_preview(self, offset: int, priority: int = 0):
        """Request a preview at the given offset."""
        logger.debug(f"[SIMPLE] Preview requested for offset 0x{offset:X}")

        # Store the request
        self._current_offset = offset

        # Cancel any pending request
        self._debounce_timer.stop()

        # Cancel current worker if running (with safety check)
        try:
            if self._current_worker and self._current_worker.isRunning():
                logger.debug("[SIMPLE] Terminating previous worker")
                self._current_worker.requestInterruption()
                self._current_worker.wait(100)  # Wait briefly for cleanup
                if self._current_worker.isRunning():
                    # Force quit if still running
                    self._current_worker.quit()
                    self._current_worker.wait(50)
        except RuntimeError:
            # Worker was already deleted by Qt
            logger.debug("[SIMPLE] Previous worker already deleted")
            self._current_worker = None

        # Start debounce timer (50ms for smooth updates)
        self._debounce_timer.start(50)

    def request_manual_preview(self, offset: int) -> None:
        """Request a manual preview (alias for request_preview)."""
        self.request_preview(offset, priority=10)  # Higher priority for manual

    def set_rom_data(self, rom_path: str, rom_size: int, extractor: Any) -> None:
        """Set ROM data for preview generation."""
        logger.debug(f"[SIMPLE] ROM data set: {rom_path}")
        self._current_rom_path = rom_path
        self._extractor = extractor

    def set_drag_state(self, is_dragging: bool):
        """Set whether the slider is being dragged."""
        # For compatibility - we use same timing regardless
        logger.debug(f"[SIMPLE] Drag state: {is_dragging}")

    def _generate_preview(self):
        """Generate a preview for the current offset."""
        # Try to get ROM data from provider if available
        if self._rom_data_provider:
            try:
                rom_path, extractor, _rom_cache = self._rom_data_provider()
                self._current_rom_path = rom_path
                self._extractor = extractor
            except Exception as e:
                logger.error(f"[SIMPLE] Error getting ROM data from provider: {e}")

        if not self._current_rom_path or not self._extractor:
            logger.warning("[SIMPLE] Cannot generate preview - no ROM data")
            return

        logger.debug(f"[SIMPLE] Starting preview generation for 0x{self._current_offset:X}")

        # Clear any stale reference first
        self._current_worker = None

        # Create a new worker (with parent for proper cleanup)
        worker = SimplePreviewWorker(
            self._current_rom_path,
            self._current_offset,
            self._extractor,
            parent=self  # Set parent for proper Qt object management
        )
        self._current_worker = worker

        # Connect signals
        worker.preview_ready.connect(self._on_preview_ready)
        worker.preview_error.connect(self._on_preview_error)

        # Clean up worker when done - capture specific worker to avoid race condition
        worker.finished.connect(lambda w=worker: self._cleanup_specific_worker(w))

        # Start the worker
        worker.start()

    def _cleanup_specific_worker(self, worker: SimplePreviewWorker) -> None:
        """Clean up a specific finished worker."""
        # Only clear reference if this is still the current worker
        if worker == self._current_worker:
            self._current_worker = None
        worker.deleteLater()
        logger.debug("[SIMPLE] Worker cleaned up after finishing")

    def _on_preview_ready(self, tile_data: bytes, width: int, height: int, name: str):
        """Handle preview ready from worker."""
        logger.debug(f"[SIMPLE] Preview ready: {width}x{height}, {len(tile_data)} bytes")
        self.preview_ready.emit(tile_data, width, height, name)

    def _on_preview_error(self, error_msg: str):
        """Handle preview error from worker."""
        logger.error(f"[SIMPLE] Preview error: {error_msg}")
        self.preview_error.emit(error_msg)

    def cleanup(self):
        """Clean up resources."""
        logger.debug("[SIMPLE] Cleaning up coordinator")

        # Stop timer
        self._debounce_timer.stop()

        # Stop current worker if running
        try:
            if self._current_worker and self._current_worker.isRunning():
                self._current_worker.requestInterruption()
                self._current_worker.quit()
                if not self._current_worker.wait(200):
                    logger.warning("[SIMPLE] Worker didn't stop cleanly")
                self._current_worker.deleteLater()
                self._current_worker = None
        except RuntimeError:
            # Worker was already deleted by Qt
            logger.debug("[SIMPLE] Worker already deleted by Qt")
            self._current_worker = None
