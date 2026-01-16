"""
Smart Preview Coordinator for real-time preview updates with memory caching.

This module provides smooth 60 FPS preview updates with:
- Immediate UI feedback during dragging (16ms updates)
- Cached preview display with 50ms debounce during drag
- High-quality preview generation with 200ms debounce after release

Key features:
- Worker thread reuse via preview worker pool (2 workers)
- Fast LRU memory cache (~2MB) for instant access
- Different timing strategies for drag vs release states
- Proper Qt signal handling with sliderPressed/sliderReleased
"""

from __future__ import annotations

import weakref
from collections.abc import Callable
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QTimer, Signal
from PySide6.QtWidgets import QSlider

from ui.common.preview_cache import PreviewCache
from ui.common.preview_worker_pool import PreviewWorkerPool
from ui.common.timing_constants import REFRESH_RATE_60FPS
from utils.logging_config import get_logger

logger = get_logger(__name__)


def _validate_tile_data(tile_data: bytes | None, sample_size: int = 100) -> bool:
    """Check if tile data is valid (non-empty and has non-zero bytes).

    Args:
        tile_data: The tile data bytes to validate
        sample_size: Number of bytes to sample for non-zero check

    Returns:
        True if data is valid (has non-zero content), False otherwise
    """
    if not tile_data or len(tile_data) == 0:
        return False
    check_size = min(sample_size, len(tile_data))
    return any(b != 0 for b in tile_data[:check_size])


class DragState(Enum):
    """Slider drag state for different preview strategies."""

    IDLE = auto()  # Not dragging, normal operations
    DRAGGING = auto()  # Actively dragging slider
    SETTLING = auto()  # Just released, waiting for final update


class PendingPreviewRequest:
    """Represents a pending preview request with cancellation support.

    Note: This is distinct from core.services.preview_generator.PreviewRequest,
    which is used for cache key generation. This class handles request lifecycle
    and cancellation in the UI layer.
    """

    def __init__(
        self,
        request_id: int,
        offset: int,
        rom_path: str,
        callback: Callable[..., object] | None = None,
        *,
        full_decompression: bool = False,
    ):
        self.request_id = request_id
        self.offset = offset
        self.rom_path = rom_path
        self.callback = callback
        self.cancelled = False
        self.full_decompression = full_decompression  # If True, don't truncate at 4KB

    def cancel(self) -> None:
        """Mark this request as cancelled."""
        self.cancelled = True


class SmartPreviewCoordinator(QObject):
    """
    Coordinates real-time preview updates with intelligent timing and memory caching.

    Timing Strategy:
    - Immediate UI updates (16ms) during dragging for smooth feedback
    - Cached preview display with 50ms debounce during drag
    - High-quality preview generation with 200ms debounce after release

    Features:
    - Worker thread reuse via preview worker pool (2 workers)
    - Fast LRU memory cache (~2MB) for instant access
    - Request cancellation to prevent stale updates
    """

    # Signals for preview updates
    preview_ready = Signal(
        bytes, int, int, str, int, int, int, bool, bytes
    )  # tile_data, width, height, name, compressed_size, slack_size, actual_offset, hal_succeeded, header_bytes
    preview_cached = Signal(
        bytes, int, int, str, int, int, int, bool, bytes
    )  # Cached preview displayed, with compressed_size, slack_size, actual_offset, hal_succeeded, header_bytes
    preview_error = Signal(str)  # Error message

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # State management
        self._drag_state = DragState.IDLE
        self._current_offset = 0
        self._request_counter = 0
        self._mutex = QMutex()
        self._pending_full_decompression = False  # If True, next request uses full decompression

        # Slider reference (weak to prevent circular references)
        self._slider_ref: weakref.ReferenceType[Any] | None = None  # pyright: ignore[reportExplicitAny] - Weak reference to QSlider

        # Timing configuration optimized for 60 FPS real-time updates
        self._drag_debounce_ms = REFRESH_RATE_60FPS  # 16ms for 60 FPS drag updates
        self._release_debounce_ms = 200  # Quality updates after release
        self._ui_update_ms = REFRESH_RATE_60FPS  # 16ms for smooth UI

        # Timer management
        self._drag_timer = QTimer(self)
        self._drag_timer.setSingleShot(True)
        self._drag_timer.timeout.connect(self._handle_drag_preview)

        self._release_timer = QTimer(self)
        self._release_timer.setSingleShot(True)
        self._release_timer.timeout.connect(self._handle_release_preview)

        self._ui_timer = QTimer(self)
        self._ui_timer.setSingleShot(True)
        self._ui_timer.timeout.connect(self._handle_ui_update)

        # Worker pool for background preview generation (2 workers)
        self._worker_pool = PreviewWorkerPool(max_workers=2)
        # Use AutoConnection to let Qt choose the best connection type
        # This avoids unnecessary queuing when already on main thread
        self._worker_pool.preview_ready.connect(self._on_worker_preview_ready)
        self._worker_pool.preview_error.connect(self._on_worker_preview_error)

        # Fast LRU memory cache
        self._cache = PreviewCache(max_size=20)  # ~2MB cache

        # Callbacks for external integration
        self._ui_update_callback: Callable[[int | None], None] | None = None
        self._rom_data_provider: Callable[[], tuple[str, object] | None] | None = None

        logger.debug("SmartPreviewCoordinator initialized")

    def connect_slider(self, slider: QSlider) -> None:
        """
        Connect to slider signals for smart preview coordination.

        Args:
            slider: QSlider to monitor for drag events
        """
        self._slider_ref = weakref.ref(slider)

        # Connect to slider signals for different drag phases
        slider.sliderPressed.connect(self._on_drag_start)
        slider.sliderMoved.connect(self._on_drag_move)
        slider.sliderReleased.connect(self._on_drag_end)

        # ALSO connect to valueChanged for non-drag changes (keyboard, programmatic, etc)
        # Note: We'll get this via offset_changed from the browse tab now

        logger.debug(f"[DEBUG] Connected to slider {slider.objectName()} - drag events only")

    def set_ui_update_callback(self, callback: Callable[[int], None]) -> None:
        """Set callback for immediate UI updates during dragging."""
        self._ui_update_callback = callback  # type: ignore[assignment]

    def set_rom_data_provider(self, provider: Callable[[], tuple[str, object] | None]) -> None:
        """Set provider for ROM data needed for preview generation.

        Args:
            provider: Function that returns (rom_path, rom_extractor) or None
        """
        self._rom_data_provider = provider

    def invalidate_preview_cache(self, offset: int | None = None) -> None:
        """Invalidate cached preview data for a specific offset.

        Args:
            offset: ROM offset to invalidate. Defaults to current offset.
        """
        if not self._rom_data_provider:
            return

        provider_result = self._rom_data_provider()
        if provider_result is None:
            return

        rom_path, _ = provider_result
        if not rom_path:
            return

        target_offset = self._current_offset if offset is None else offset
        cache_key = self._cache.make_key(rom_path, target_offset)
        removed = self._cache.remove(cache_key)
        if removed:
            logger.debug(f"Invalidated preview cache for 0x{target_offset:06X}")

    def request_preview(self, offset: int) -> None:
        """
        Request preview update with intelligent timing and memory caching.

        Args:
            offset: ROM offset for preview
        """
        logger.debug(f"Coordinator.request_preview: offset=0x{offset:06X}")

        with QMutexLocker(self._mutex):
            self._current_offset = offset
            self._request_counter += 1

        # Try cache lookup first
        if self._try_show_cached_preview():
            return

        # Immediate UI update for smooth feedback
        self._schedule_ui_update()

        # Schedule preview based on current drag state
        if self._drag_state == DragState.DRAGGING:
            self._schedule_drag_preview()
        else:
            self._schedule_release_preview()

    def request_manual_preview(self, offset: int) -> None:
        """
        Request preview for manual offset change (outside of slider dragging).
        This bypasses debouncing for immediate response.

        Args:
            offset: ROM offset for preview
        """
        logger.debug(f"[DEBUG] request_manual_preview called for offset 0x{offset:06X}")

        # Request preview for immediate response
        self.request_preview(offset)

    def request_full_preview(self, offset: int) -> None:
        """
        Request full decompression preview (not truncated to 4KB).

        Use this when opening a sprite in the editor, where you need the complete
        decompressed data, not just a preview. Normal previews are limited to 4KB
        for performance during slider dragging.

        Args:
            offset: ROM offset for preview
        """
        logger.debug(f"[DEBUG] request_full_preview called for offset 0x{offset:06X}")
        with QMutexLocker(self._mutex):
            self._pending_full_decompression = True
        # Request preview with immediate response (bypasses debouncing)
        self.request_preview(offset)

    def request_background_preload(self, offset: int) -> None:
        """
        Request background preloading of an offset without affecting current display.

        This method caches previews for adjacent offsets but does NOT:
        - Update _current_offset (preserves the user's current position)
        - Emit UI signals (no visual feedback)
        - Affect the current preview display

        Args:
            offset: ROM offset to preload
        """
        # Check if already cached
        if self._rom_data_provider:
            try:
                provider_result = self._rom_data_provider()
                if provider_result:
                    rom_path, _ = provider_result
                    cache_key = self._cache.make_key(rom_path, offset)
                    if self._cache.get(cache_key):
                        logger.debug(f"[PRELOAD] Already cached: 0x{offset:06X}")
                        return
            except Exception:
                pass

        # Request worker preview directly without updating _current_offset
        self._request_background_worker_preview(offset)

    def _request_background_worker_preview(self, offset: int) -> None:
        """Request background worker preview for caching only."""
        try:
            provider_result = self._rom_data_provider() if self._rom_data_provider else None
            if provider_result is None:
                return
            rom_path, extractor_obj = provider_result
            extractor: ROMExtractor | None = cast("ROMExtractor | None", extractor_obj)

            if not rom_path or not rom_path.strip() or not extractor:
                return

            # Use a separate request ID counter space (negative) to differentiate preloads
            with QMutexLocker(self._mutex):
                request_id = -(self._request_counter + 1000)  # Negative IDs for preloads

            logger.debug(f"[PRELOAD] Creating background request: offset=0x{offset:06X}")

            # Create and submit background request
            request = PendingPreviewRequest(
                request_id=request_id,
                offset=offset,
                rom_path=rom_path,
            )
            self._worker_pool.submit_request(request, extractor)

        except Exception as e:
            logger.debug(f"Error in background preload for 0x{offset:06X}: {e}")

    def _on_drag_start(self) -> None:
        """Handle start of slider dragging."""
        logger.debug("Drag start detected")
        self._drag_state = DragState.DRAGGING

        # Cancel any pending release previews
        self._release_timer.stop()

        # Try to show cached preview immediately
        if self._try_show_cached_preview():
            logger.debug("Showed cached preview for drag start")

    def _on_drag_move(self, value: int) -> None:
        """Handle slider movement during dragging."""
        logger.debug(f"[DEBUG] _on_drag_move: value=0x{value:06X}")
        # Simple and fast - just request preview
        # Don't do heavy cache checking during rapid drag movements
        self.request_preview(value)

    def _on_drag_end(self) -> None:
        """Handle end of slider dragging."""
        logger.debug("Drag end detected")
        self._drag_state = DragState.SETTLING

        # Cancel drag timers
        self._drag_timer.stop()

        # Schedule high-quality release preview
        self._schedule_release_preview()

        # Return to idle state after brief settling period
        QTimer.singleShot(500, lambda: setattr(self, "_drag_state", DragState.IDLE))

    def _schedule_ui_update(self) -> None:
        """Schedule immediate UI update for smooth feedback."""
        if not self._ui_timer.isActive():
            self._ui_timer.start(self._ui_update_ms)

    def _schedule_drag_preview(self) -> None:
        """Schedule preview update during dragging with short debounce."""
        self._drag_timer.stop()
        self._drag_timer.start(self._drag_debounce_ms)

    def _schedule_release_preview(self) -> None:
        """Schedule preview update after release with longer debounce."""
        self._release_timer.stop()
        self._release_timer.start(self._release_debounce_ms)

    def _handle_ui_update(self) -> None:
        """Handle immediate UI updates for smooth feedback."""
        if self._ui_update_callback:
            with QMutexLocker(self._mutex):
                offset = self._current_offset
            self._ui_update_callback(offset)

    def _handle_drag_preview(self) -> None:
        """Handle preview update during dragging."""
        logger.debug("Processing drag preview request")

        # Check cache first for instant display
        if self._try_show_cached_preview():
            return

        # Request preview from worker pool
        self._request_worker_preview()

    def _handle_release_preview(self) -> None:
        """Handle high-quality preview update after release."""
        logger.debug("Processing release preview request")

        # Request high-quality preview from worker pool
        self._request_worker_preview()

    def _try_show_cached_preview(self) -> bool:
        """
        Try to show cached preview from memory cache.

        Returns:
            bool: True if cached preview was shown
        """
        if not self._rom_data_provider:
            return False

        try:
            provider_result = self._rom_data_provider()
            if provider_result is None:
                return False
            rom_path, _ = provider_result

            with QMutexLocker(self._mutex):
                offset = self._current_offset

            cache_key = self._cache.make_key(rom_path, offset)
            cached_data = self._cache.get(cache_key)

            # cached_data is never None, but might be empty (b"", 0, 0, None, 0, 0, -1, True, b"")
            if cached_data and cached_data[0]:  # Check if tile_data is not empty
                # Unpack all 9 elements (tile_data, width, height, sprite_name, compressed_size, slack_size, actual_offset, hal_succeeded, header_bytes)
                # Old cache entries with fewer elements will fail to unpack and be invalidated
                if len(cached_data) != 9:
                    # Invalidate old-format cache entry
                    self._cache.remove(cache_key)
                    return False
                (
                    tile_data,
                    width,
                    height,
                    sprite_name,
                    compressed_size,
                    slack_size,
                    actual_offset,
                    hal_succeeded,
                    header_bytes,
                ) = cached_data

                if _validate_tile_data(tile_data):
                    logger.debug(
                        f"Cache hit for 0x{offset:06X}: {len(tile_data)} bytes (hal: {hal_succeeded}, header: {len(header_bytes)})"
                    )
                    # Emit both signals: preview_cached for statistics, preview_ready for data consumers
                    self.preview_cached.emit(
                        tile_data,
                        width,
                        height,
                        sprite_name or "",
                        compressed_size,
                        slack_size,
                        actual_offset,
                        hal_succeeded,
                        header_bytes,
                    )
                    self.preview_ready.emit(
                        tile_data,
                        width,
                        height,
                        sprite_name or "",
                        compressed_size,
                        slack_size,
                        actual_offset,
                        hal_succeeded,
                        header_bytes,
                    )
                    return True

                # Remove invalid entry from cache
                self._cache.remove(cache_key)

        except Exception as e:
            logger.warning(f"Error checking cached preview: {e}")

        return False

    def _request_worker_preview(self) -> None:
        """Request preview from worker pool."""
        logger.debug("_request_worker_preview called")
        if not self._rom_data_provider:
            self.preview_error.emit("Preview not available: no ROM data provider")
            return

        try:
            provider_result = self._rom_data_provider()
            if provider_result is None:
                self.preview_error.emit("ROM must be loaded first")
                return
            rom_path, extractor_obj = provider_result
            extractor: ROMExtractor | None = cast("ROMExtractor | None", extractor_obj)

            # Check if ROM data is actually valid before proceeding
            if not rom_path or not rom_path.strip():
                self.preview_error.emit("ROM must be loaded first")
                return
            if not extractor:
                self.preview_error.emit("ROM extractor not available")
                return

            with QMutexLocker(self._mutex):
                offset = self._current_offset
                request_id = self._request_counter
                full_decompression = self._pending_full_decompression
                self._pending_full_decompression = False  # Reset after reading

            logger.debug(
                f"[COORD] Creating preview request: offset=0x{offset:06X}, "
                f"request_id={request_id}, full_decompression={full_decompression}"
            )

            # Create preview request
            request = PendingPreviewRequest(
                request_id=request_id,
                offset=offset,
                rom_path=rom_path,
                full_decompression=full_decompression,
            )

            # Submit to worker pool
            self._worker_pool.submit_request(request, extractor)

        except Exception as e:
            logger.exception("Error requesting worker preview")
            self.preview_error.emit(f"Preview request failed: {e}")

    def _on_worker_preview_ready(
        self,
        request_id: int,
        tile_data: bytes,
        width: int,
        height: int,
        sprite_name: str,
        compressed_size: int,
        slack_size: int = 0,
        actual_offset: int = -1,
        hal_succeeded: bool = True,
        header_bytes: bytes = b"",
    ) -> None:
        """Handle preview ready from worker."""
        # Use current offset if actual_offset not provided (backward compat)
        if actual_offset == -1:
            with QMutexLocker(self._mutex):
                actual_offset = self._current_offset

        logger.debug(
            f"[COORD] Received worker preview: request_id={request_id}, sprite_name={sprite_name}, "
            f"current_counter={self._request_counter}, slack_size={slack_size}, "
            f"actual_offset=0x{actual_offset:X}, hal_succeeded={hal_succeeded}, header_bytes={len(header_bytes)}"
        )
        # Check if this is still the current request
        # Note: Negative request IDs are used for background preloads and should
        # bypass the staleness check - they're always valid for caching purposes.
        with QMutexLocker(self._mutex):
            if request_id >= 0 and request_id < self._request_counter:
                logger.debug(f"[COORD] Ignoring stale request {request_id} (current={self._request_counter})")
                return

        # Cache the result if data is valid
        if self._rom_data_provider and _validate_tile_data(tile_data):
            try:
                provider_result = self._rom_data_provider()
                if provider_result is None:
                    # Emit result even if caching fails
                    self.preview_ready.emit(
                        tile_data,
                        width,
                        height,
                        sprite_name,
                        compressed_size,
                        slack_size,
                        actual_offset,
                        hal_succeeded,
                        header_bytes,
                    )
                    return
                rom_path, _ = provider_result
                preview_data = (
                    tile_data,
                    width,
                    height,
                    sprite_name,
                    compressed_size,
                    slack_size,
                    actual_offset,
                    hal_succeeded,
                    header_bytes,
                )

                # Save to memory cache
                cache_key = self._cache.make_key(rom_path, self._current_offset)
                self._cache.put(cache_key, preview_data)
                logger.debug(
                    f"Cached preview for 0x{self._current_offset:06X}: {len(tile_data)} bytes "
                    f"(slack: {slack_size}, hal: {hal_succeeded}, header: {len(header_bytes)})"
                )
            except Exception as e:
                logger.warning(f"Error caching preview: {e}")

        logger.debug(f"[COORD] Forwarding preview_ready: sprite_name={sprite_name}, hal_succeeded={hal_succeeded}")
        self.preview_ready.emit(
            tile_data,
            width,
            height,
            sprite_name,
            compressed_size,
            slack_size,
            actual_offset,
            hal_succeeded,
            header_bytes,
        )

    def _on_worker_preview_error(self, request_id: int, error_msg: str) -> None:
        """Handle preview error from worker."""
        # Check if this is still relevant
        with QMutexLocker(self._mutex):
            if request_id < self._request_counter - 1:
                return

        self.preview_error.emit(error_msg)
        logger.debug(f"Preview error for request {request_id}: {error_msg}")

    def cleanup(self) -> None:
        """Clean up resources."""
        logger.debug("Cleaning up SmartPreviewCoordinator")

        # Stop all timers
        self._drag_timer.stop()
        self._release_timer.stop()
        self._ui_timer.stop()

        # Cleanup worker pool
        self._worker_pool.cleanup()

        # Clear cache
        if self._cache:
            self._cache.clear()

        # Clear references
        self._slider_ref = None
        self._ui_update_callback = None
        self._rom_data_provider = None
