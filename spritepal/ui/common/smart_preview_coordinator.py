"""
Smart Preview Coordinator for real-time preview updates with dual-tier caching.

This module provides smooth 60 FPS preview updates by implementing a multi-tier
strategy:
- Tier 1: Immediate visual feedback (0-16ms) for UI elements
- Tier 2: Fast cached previews (50ms debounce) during dragging
- Tier 3: High-quality preview generation (200ms debounce) after release

Dual-Tier Caching:
- Memory Cache: Fast LRU cache (~2MB) for instant access during session
- ROM Cache: Persistent cache for cross-session preview storage
- Cache Workflow: Check memory -> Check ROM -> Generate -> Save to both

Key features:
- Worker thread reuse to prevent excessive thread creation
- Dual-tier caching with performance metrics
- Different timing strategies for drag vs release states
- Cache hit/miss tracking and response time analysis
- Proper Qt signal handling with sliderPressed/sliderReleased
- Backward compatibility with optional ROM cache integration
"""

from __future__ import annotations

import time
import weakref
from collections.abc import Callable
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from utils.rom_cache import ROMCache

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QTimer, Signal
from PySide6.QtWidgets import QSlider

from ui.common.preview_cache import PreviewCache
from ui.common.preview_worker_pool import PreviewWorkerPool
from ui.common.timing_constants import REFRESH_RATE_60FPS
from utils.logging_config import get_logger

logger = get_logger(__name__)

class DragState(Enum):
    """Slider drag state for different preview strategies."""
    IDLE = auto()         # Not dragging, normal operations
    DRAGGING = auto()     # Actively dragging slider
    SETTLING = auto()     # Just released, waiting for final update

class PreviewRequest:
    """Represents a preview request with priority and cancellation support."""

    def __init__(self, request_id: int, offset: int, rom_path: str,
                 priority: int = 0, callback: Callable[..., Any] | None = None):
        self.request_id = request_id
        self.offset = offset
        self.rom_path = rom_path
        self.priority = priority  # Higher = more important
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        """Mark this request as cancelled."""
        self.cancelled = True

    def __lt__(self, other: object) -> bool:
        """Support priority queue ordering."""
        if not isinstance(other, PreviewRequest):
            return NotImplemented
        return self.priority > other.priority  # Higher priority first

class SmartPreviewCoordinator(QObject):
    """
    Coordinates real-time preview updates with intelligent timing and dual-tier caching.

    This coordinator implements a multi-tier approach:
    1. Immediate UI updates (labels, indicators) during dragging
    2. Dual-tier cached preview display with 50ms debounce during drag
    3. High-quality preview generation with 200ms debounce after release

    Caching Strategy:
    - Tier 1: Fast LRU memory cache (~2MB) for instant access
    - Tier 2: Persistent ROM cache for cross-session storage
    - Cache workflow: Memory -> ROM -> Generate -> Save to both

    Features:
    - Worker thread reuse via preview worker pool
    - Dual-tier caching with performance tracking
    - Request cancellation to prevent stale updates
    - Adaptive timing based on drag state
    - Cache hit/miss metrics and response time tracking
    """

    # Signals for preview updates
    preview_ready = Signal(bytes, int, int, str)  # tile_data, width, height, name
    preview_cached = Signal(bytes, int, int, str)  # Cached preview displayed
    preview_error = Signal(str)  # Error message

    def __init__(self, parent: QObject | None = None, rom_cache: ROMCache | None = None):
        super().__init__(parent)

        # State management
        self._drag_state = DragState.IDLE
        self._current_offset = 0
        self._request_counter = 0
        self._mutex = QMutex()

        # Slider reference (weak to prevent circular references)
        self._slider_ref: weakref.ReferenceType[Any] | None = None

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

        # Worker pool and dual-tier caching
        self._worker_pool = PreviewWorkerPool(max_workers=8)
        # Use AutoConnection to let Qt choose the best connection type
        # This avoids unnecessary queuing when already on main thread
        self._worker_pool.preview_ready.connect(
            self._on_worker_preview_ready
        )
        self._worker_pool.preview_error.connect(
            self._on_worker_preview_error
        )

        # Tier 1: Fast LRU memory cache
        self._cache = PreviewCache(max_size=20)  # ~2MB cache

        # Tier 2: Persistent ROM cache (optional)
        self._rom_cache = rom_cache

        # Performance tracking
        self._cache_stats: dict[str, int | list[float]] = {
            "memory_hits": 0,
            "memory_misses": 0,
            "rom_hits": 0,
            "rom_misses": 0,
            "generations": 0,
            "response_times": []
        }

        # Batch caching for efficiency
        self._pending_rom_cache_saves: dict[str, dict[int, tuple[bytes, int, int, str]]] = {}
        self._batch_save_timer = QTimer(self)
        self._batch_save_timer.setSingleShot(True)
        self._batch_save_timer.timeout.connect(self._flush_pending_rom_cache_saves)
        self._batch_save_delay_ms = 2000  # 2 seconds delay for batching

        # Callbacks for external integration
        self._ui_update_callback: Callable[[int | None], None] | None = None
        self._rom_data_provider: Callable[[], tuple[str, Any, Any] | None] | None = None

        cache_info = "with ROM cache" if rom_cache else "memory only"
        logger.debug(f"SmartPreviewCoordinator initialized ({cache_info})")

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

    def set_rom_data_provider(self, provider: Callable[[], tuple[str, Any, Any]]) -> None:
        """Set provider for ROM data needed for preview generation.

        Args:
            provider: Function that returns (rom_path, rom_extractor, rom_cache)
                     Third parameter can be None for backward compatibility
        """
        self._rom_data_provider = provider

    def request_preview(self, offset: int, priority: int = 0) -> None:
        """
        Request preview update with intelligent timing and dual-tier caching.

        Cache workflow:
        1. Check memory cache (LRU) first
        2. If miss, check ROM cache
        3. If miss, generate preview
        4. Save to both caches on generation

        Args:
            offset: ROM offset for preview
            priority: Request priority (higher = more important)
        """
        logger.debug("[DEBUG] ========== REQUEST_PREVIEW START ==========")
        logger.debug(f"[DEBUG] Coordinator.request_preview called: offset=0x{offset:06X}, priority={priority}")
        start_time = time.time()

        with QMutexLocker(self._mutex):
            self._current_offset = offset
            self._request_counter += 1
            logger.debug(f"[DEBUG] Request counter: {self._request_counter}")

        # Try dual-tier cache lookup first
        logger.debug("[DEBUG] Attempting cache lookup...")
        cache_hit = False
        try:
            cache_hit = self._try_show_cached_preview_dual_tier()
            logger.debug(f"[DEBUG] Cache lookup result: {cache_hit}")
        except Exception as e:
            logger.exception(f"[DEBUG] Exception during cache lookup: {e}")

        if cache_hit:
            # Record response time for cache hits
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            response_times = self._cache_stats["response_times"]
            assert isinstance(response_times, list)  # Type narrowing for checker
            response_times.append(response_time)
            # Keep only last 100 response times
            if len(response_times) > 100:
                response_times.pop(0)
            logger.debug(f"[DEBUG] Cache hit, returning early (response time: {response_time:.2f}ms)")
            logger.debug("[DEBUG] ========== REQUEST_PREVIEW END (CACHE HIT) ==========")
            return

        # Immediate UI update for smooth feedback
        logger.debug("[DEBUG] Cache miss, scheduling UI update...")
        self._schedule_ui_update()

        # Schedule preview based on current drag state
        if self._drag_state == DragState.DRAGGING:
            logger.debug("[DEBUG] Drag state is DRAGGING, scheduling drag preview")
            self._schedule_drag_preview()
        else:
            logger.debug(f"[DEBUG] Drag state is {self._drag_state}, scheduling release preview")
            self._schedule_release_preview()

        logger.debug("[DEBUG] ========== REQUEST_PREVIEW END (SCHEDULED) ==========")

    def request_manual_preview(self, offset: int) -> None:
        """
        Request preview for manual offset change (outside of slider dragging).
        This bypasses debouncing for immediate response.

        Args:
            offset: ROM offset for preview
        """
        logger.debug(f"[DEBUG] request_manual_preview called for offset 0x{offset:06X}")

        # Just use high priority request for immediate response
        # Avoid complex cache checking that could block
        self.request_preview(offset, priority=10)

    def flush_rom_cache(self) -> None:
        """
        Manually flush all pending ROM cache saves.

        This can be called to force immediate persistence of cached preview data
        without waiting for the batch timer.
        """
        self._flush_pending_rom_cache_saves()

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
        # Simple and fast - just request preview with drag priority
        # Don't do heavy cache checking during rapid drag movements
        self.request_preview(value, priority=1)

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

        # Flush any pending ROM cache saves when drag ends (for immediate persistence)
        if self._pending_rom_cache_saves:
            self._flush_pending_rom_cache_saves()

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

        # Request preview with medium priority
        self._request_worker_preview(priority=5)

    def _handle_release_preview(self) -> None:
        """Handle high-quality preview update after release."""
        logger.debug("Processing release preview request")

        # Request high-quality preview
        self._request_worker_preview(priority=10)

    def _try_show_cached_preview_dual_tier(self) -> bool:
        """
        Try to show cached preview from dual-tier cache system.

        Checks memory cache first, then ROM cache if available.

        Returns:
            bool: True if cached preview was shown
        """
        logger.debug("[DEBUG] _try_show_cached_preview_dual_tier called")
        if not self._rom_data_provider:
            logger.debug("[DEBUG] No ROM data provider, returning False")
            return False

        try:
            logger.debug("[DEBUG] Getting ROM data from provider...")
            provider_result = self._rom_data_provider()
            if provider_result is None:
                logger.debug("[DEBUG] ROM data provider returned None")
                return False
            rom_path, _, _ = provider_result
            logger.debug(f"[DEBUG] Got ROM path: {rom_path}")

            with QMutexLocker(self._mutex):
                offset = self._current_offset
                logger.debug(f"[DEBUG] Checking cache for offset 0x{offset:06X}")

            cache_key = self._cache.make_key(rom_path, offset)

            # Tier 1: Check memory cache first
            logger.debug(f"[TRACE] Checking memory cache with key: {cache_key}")
            cached_data = self._cache.get(cache_key)
            if cached_data:
                logger.debug("[TRACE] Found data in memory cache")
                tile_data, width, height, sprite_name = cached_data
                logger.debug(f"[TRACE] Unpacked cache data: {len(tile_data) if tile_data else 0} bytes, {width}x{height}, name={sprite_name}")

                # CRITICAL: Validate cached data before using it
                if tile_data and len(tile_data) > 0:
                    # Check if data is not all zeros (black)
                    sample_size = min(100, len(tile_data))
                    non_zero_count = sum(1 for b in tile_data[:sample_size] if b != 0)
                    logger.debug(f"[TRACE] Validation: {non_zero_count}/{sample_size} non-zero bytes")

                    if non_zero_count > 0:  # Has some non-zero data
                        logger.debug(f"[TRACE] Valid cache hit: {len(tile_data)} bytes, {non_zero_count}/{sample_size} non-zero")
                        logger.debug("[TRACE] About to emit preview_cached signal...")
                        self.preview_cached.emit(tile_data, width, height, sprite_name)
                        mem_hits = self._cache_stats["memory_hits"]
                        assert isinstance(mem_hits, int)  # Type narrowing
                        self._cache_stats["memory_hits"] = mem_hits + 1
                        logger.debug(f"[SIGNAL_FLOW] Memory cache hit signal emitted for 0x{offset:06X}")
                        return True
                    logger.debug("[TRACE] Cache hit but data is all zeros - ignoring and regenerating")
                    # Remove invalid entry from cache
                    self._cache.remove(cache_key)
                else:
                    logger.debug("[TRACE] Cache hit but data is empty - ignoring")
                    # Remove invalid entry from cache
                    self._cache.remove(cache_key)

            mem_misses = self._cache_stats["memory_misses"]
            assert isinstance(mem_misses, int)  # Type narrowing
            self._cache_stats["memory_misses"] = mem_misses + 1

            # Tier 2: Check ROM cache if available
            logger.debug("[TRACE] Memory cache miss, checking ROM cache...")
            if self._rom_cache and self._rom_cache.cache_enabled:
                rom_cache_data = self._check_rom_cache(rom_path, offset)
                if rom_cache_data:
                    tile_data, width, height, sprite_name = rom_cache_data

                    # CRITICAL: Validate ROM cached data before using it
                    if tile_data and len(tile_data) > 0:
                        non_zero_count = sum(1 for b in tile_data[:min(100, len(tile_data))] if b != 0)
                        if non_zero_count > 0:  # Has some non-zero data
                            logger.debug(f"[TRACE] Valid ROM cache hit: {len(tile_data)} bytes, {non_zero_count}/100 non-zero")
                            # Store in memory cache for faster future access
                            # Ensure sprite_name is not None for cache storage
                            cache_data = (tile_data, width, height, sprite_name or "")
                            self._cache.put(cache_key, cache_data)
                            self.preview_cached.emit(tile_data, width, height, sprite_name)
                            rom_hits = self._cache_stats["rom_hits"]
                            assert isinstance(rom_hits, int)  # Type narrowing
                            self._cache_stats["rom_hits"] = rom_hits + 1
                            logger.debug(f"[SIGNAL_FLOW] ROM cache hit signal emitted for 0x{offset:06X}")
                            return True
                        logger.debug("[TRACE] ROM cache hit but data is all zeros - ignoring")
                    else:
                        logger.debug("[TRACE] ROM cache hit but data is empty - ignoring")

            if self._rom_cache and self._rom_cache.cache_enabled:
                rom_misses = self._cache_stats["rom_misses"]
                assert isinstance(rom_misses, int)  # Type narrowing
                self._cache_stats["rom_misses"] = rom_misses + 1

        except Exception as e:
            logger.warning(f"Error checking cached preview: {e}")

        return False

    def _try_show_cached_preview(self) -> bool:
        """
        Legacy method for backward compatibility.

        Returns:
            bool: True if cached preview was shown
        """
        return self._try_show_cached_preview_dual_tier()

    def _check_rom_cache(self, rom_path: str, offset: int) -> tuple[bytes, int, int, str | None]:
        """
        Check ROM cache for preview data.

        Args:
            rom_path: Path to ROM file
            offset: ROM offset

        Returns:
            Optional tuple of (tile_data, width, height, sprite_name) or None
        """
        if not self._rom_cache or not self._rom_cache.cache_enabled:
            return (b"", 0, 0, None)

        try:
            logger.debug(f"Checking ROM cache for preview at 0x{offset:06X}")

            # Get preview data from ROM cache
            preview_data = self._rom_cache.get_preview_data(rom_path, offset)
            if not preview_data:
                return (b"", 0, 0, None)

            # Extract data components
            tile_data = preview_data["tile_data"]
            width = preview_data["width"]
            height = preview_data["height"]

            # Generate sprite name from offset
            # Use "manual_" prefix so SpritePreviewWorker knows to extract raw tiles
            sprite_name = f"manual_0x{offset:06X}"

            logger.debug(f"ROM cache hit: {len(tile_data)} bytes, {width}x{height}")
            return (tile_data, width, height, sprite_name)

        except Exception as e:
            logger.warning(f"Error checking ROM cache: {e}")
            return (b"", 0, 0, None)

    def _save_to_rom_cache(self, rom_path: str, offset: int,
                          preview_data: tuple[bytes, int, int, str]) -> bool:
        """
        Save preview data to ROM cache.

        Args:
            rom_path: Path to ROM file
            offset: ROM offset
            preview_data: Tuple of (tile_data, width, height, sprite_name)

        Returns:
            bool: True if saved successfully
        """
        if not self._rom_cache or not self._rom_cache.cache_enabled:
            return False

        try:
            tile_data, width, height, _sprite_name = preview_data

            logger.debug(f"Saving preview to ROM cache for 0x{offset:06X} ({len(tile_data)} bytes, {width}x{height})")

            # Save to ROM cache using existing preview storage method
            success = self._rom_cache.save_preview_data(
                rom_path=rom_path,
                offset=offset,
                tile_data=tile_data,
                width=width,
                height=height,
                params=None  # No special parameters for now
            )

            if success:
                logger.debug(f"Successfully saved preview to ROM cache for 0x{offset:06X}")
            else:
                logger.debug(f"Failed to save preview to ROM cache for 0x{offset:06X}")

            return success

        except Exception as e:
            logger.warning(f"Error saving to ROM cache: {e}")
            return False

    def _queue_rom_cache_save(self, rom_path: str, offset: int,
                             preview_data: tuple[bytes, int, int, str]) -> None:
        """
        Queue preview data for batch saving to ROM cache.

        This reduces I/O overhead by batching multiple saves together.

        Args:
            rom_path: Path to ROM file
            offset: ROM offset
            preview_data: Tuple of (tile_data, width, height, sprite_name)
        """
        if not self._rom_cache or not self._rom_cache.cache_enabled:
            return

        # Add to pending saves
        if rom_path not in self._pending_rom_cache_saves:
            self._pending_rom_cache_saves[rom_path] = {}

        self._pending_rom_cache_saves[rom_path][offset] = preview_data

        # Schedule batch save
        self._batch_save_timer.stop()
        self._batch_save_timer.start(self._batch_save_delay_ms)

        logger.debug(f"Queued ROM cache save for 0x{offset:06X} (batch size: {len(self._pending_rom_cache_saves[rom_path])})")

    def _flush_pending_rom_cache_saves(self) -> None:
        """
        Flush all pending ROM cache saves using batch operations.

        This method processes all queued preview data and saves it to ROM cache
        using batch operations for maximum efficiency.
        """
        if not self._pending_rom_cache_saves:
            return

        total_saved = 0
        total_failed = 0

        for rom_path, offset_data in self._pending_rom_cache_saves.items():
            if not offset_data:
                continue

            try:
                # Convert to batch format expected by ROM cache
                batch_data = {}
                for offset, (tile_data, width, height, _sprite_name) in offset_data.items():
                    batch_data[offset] = {
                        "tile_data": tile_data,
                        "width": width,
                        "height": height,
                        "params": None  # No special parameters for now
                    }

                # Use ROM cache batch save for efficiency
                if len(batch_data) > 1:
                    success = self._rom_cache.save_preview_batch(rom_path, batch_data) if self._rom_cache else False
                    if success:
                        total_saved += len(batch_data)
                        logger.debug(f"Batch saved {len(batch_data)} previews to ROM cache for {rom_path}")
                    else:
                        total_failed += len(batch_data)
                        logger.warning(f"Failed to batch save {len(batch_data)} previews to ROM cache")
                else:
                    # Single save for lone entries
                    offset = next(iter(batch_data.keys()))
                    data = batch_data[offset]
                    success = self._rom_cache.save_preview_data(
                        rom_path, offset, data["tile_data"],
                        data["width"], data["height"], data["params"]
                    ) if self._rom_cache else False
                    if success:
                        total_saved += 1
                    else:
                        total_failed += 1

            except Exception as e:
                logger.warning(f"Error flushing ROM cache saves for {rom_path}: {e}")
                total_failed += len(offset_data)

        # Clear pending saves
        if self._pending_rom_cache_saves:
            self._pending_rom_cache_saves.clear()

        if total_saved > 0 or total_failed > 0:
            logger.debug(f"ROM cache batch flush complete: {total_saved} saved, {total_failed} failed")

    def _request_worker_preview(self, priority: int) -> None:
        """Request preview from worker pool."""
        logger.debug(f"[DEBUG] _request_worker_preview called with priority={priority}")
        if not self._rom_data_provider:
            logger.warning("[DEBUG] No ROM data provider set!")
            return

        try:
            provider_result = self._rom_data_provider()
            if provider_result is None:
                logger.warning("[DEBUG] ROM data provider returned None!")
                return
            rom_path, extractor, rom_cache = provider_result
            logger.debug(f"[DEBUG] Got ROM data: path={bool(rom_path)}, extractor={bool(extractor)}, cache={bool(rom_cache)}")

            # Check if ROM data is actually valid before proceeding
            if not rom_path or not rom_path.strip():
                logger.debug("[DEBUG] ROM path not available, skipping preview request")
                return
            if not extractor:
                logger.debug("[DEBUG] ROM extractor not available, skipping preview request")
                return
            with QMutexLocker(self._mutex):
                offset = self._current_offset
                request_id = self._request_counter
                logger.debug(f"[DEBUG] Creating request: id={request_id}, offset=0x{offset:06X}")

            # Create preview request
            request = PreviewRequest(
                request_id=request_id,
                offset=offset,
                rom_path=rom_path,
                priority=priority
            )

            # Submit to worker pool with ROM cache support
            logger.debug("[DEBUG] Submitting request to worker pool")
            self._worker_pool.submit_request(request, extractor, rom_cache)

        except Exception as e:
            logger.exception("[DEBUG] Error requesting worker preview")  # TRY401: exception already logged
            self.preview_error.emit(f"Preview request failed: {e}")

    def _on_worker_preview_ready(self, request_id: int, tile_data: bytes,
                                width: int, height: int, sprite_name: str) -> None:
        """Handle preview ready from worker."""
        logger.debug(f"[DEBUG] _on_worker_preview_ready: request_id={request_id}, data_len={len(tile_data) if tile_data else 0}, {width}x{height}")
        # Check if this is still the current request
        with QMutexLocker(self._mutex):
            if request_id < self._request_counter - 1:  # Allow some lag
                logger.debug(f"[DEBUG] Ignoring stale preview {request_id} (current: {self._request_counter})")
                return

        # Update generation counter
        generations = self._cache_stats["generations"]
        assert isinstance(generations, int)  # Type narrowing
        self._cache_stats["generations"] = generations + 1

        # Cache the result in both tiers - but ONLY if data is valid
        if self._rom_data_provider and tile_data and len(tile_data) > 0:
            # Validate data before caching to prevent caching black/empty sprites
            non_zero_count = sum(1 for b in tile_data[:min(100, len(tile_data))] if b != 0)

            if non_zero_count > 0:  # Has some non-zero data - valid to cache
                try:
                    provider_result = self._rom_data_provider()
                    if provider_result is None:
                        return  # Don't cache if provider fails
                    rom_path, _, _ = provider_result
                    preview_data = (tile_data, width, height, sprite_name)

                    # Tier 1: Save to memory cache
                    cache_key = self._cache.make_key(rom_path, self._current_offset)
                    self._cache.put(cache_key, preview_data)
                    logger.debug(f"[TRACE] Cached valid preview data: {len(tile_data)} bytes, {non_zero_count}/100 non-zero")

                    # Tier 2: Save to ROM cache if available (use batching for efficiency)
                    if self._rom_cache:
                        self._queue_rom_cache_save(rom_path, self._current_offset, preview_data)
                except Exception as e:
                    logger.warning(f"[DEBUG] Error caching preview: {e}")
            else:
                logger.debug("[TRACE] Not caching preview - data appears to be all zeros (black)")
        else:
            logger.debug("[TRACE] Not caching preview - data is empty or invalid")

        # Emit preview ready with enhanced debugging
        logger.debug("[SIGNAL_FLOW] About to emit preview_ready signal")
        logger.debug(f"[SIGNAL_FLOW] Signal data: request_id={request_id}, data_len={len(tile_data) if tile_data else 0}, {width}x{height}, name={sprite_name}")
        # Note: PySide6 signals don't have receivers() method - removed debug line

        self.preview_ready.emit(tile_data, width, height, sprite_name)

        logger.debug(f"[SIGNAL_FLOW] Preview ready signal emitted successfully for request {request_id}")
        logger.debug(f"[SIGNAL_FLOW] Emitted tile_data: first 20 bytes = {tile_data[:20].hex() if tile_data else 'None'}")

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
        self._batch_save_timer.stop()

        # Flush any pending ROM cache saves
        self._flush_pending_rom_cache_saves()

        # Cleanup worker pool
        self._worker_pool.cleanup()

        # Clear cache
        if self._cache:
            self._cache.clear()

        # Clear references
        self._slider_ref = None
        self._ui_update_callback = None
        self._rom_data_provider = None

    def get_cache_statistics(self) -> dict[str, Any]:
        """
        Get comprehensive cache statistics.

        Returns:
            dict: Cache performance metrics including hit/miss ratios and response times
        """
        with QMutexLocker(self._mutex):
            stats = self._cache_stats.copy()

        # Calculate derived metrics
        # Type narrowing for int fields
        mem_hits = stats["memory_hits"]
        mem_misses = stats["memory_misses"]
        rom_hits_val = stats["rom_hits"]
        rom_misses_val = stats["rom_misses"]
        assert isinstance(mem_hits, int)
        assert isinstance(mem_misses, int)
        assert isinstance(rom_hits_val, int)
        assert isinstance(rom_misses_val, int)

        total_memory_requests = mem_hits + mem_misses
        total_rom_requests = rom_hits_val + rom_misses_val

        # Memory cache metrics
        memory_hit_rate = (mem_hits / total_memory_requests * 100) if total_memory_requests > 0 else 0

        # ROM cache metrics (only if ROM cache is available)
        rom_hit_rate = (rom_hits_val / total_rom_requests * 100) if total_rom_requests > 0 else 0

        # Overall cache performance
        total_hits = mem_hits + rom_hits_val
        total_requests = total_memory_requests
        overall_hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0

        # Response time metrics
        response_times = stats["response_times"]
        assert isinstance(response_times, list)  # Type narrowing for list field
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        min_response_time = min(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0

        # Get memory cache stats
        memory_cache_stats = self._cache.get_stats()

        return {
            # Cache hit/miss counts
            "memory_hits": stats["memory_hits"],
            "memory_misses": stats["memory_misses"],
            "rom_hits": stats["rom_hits"],
            "rom_misses": stats["rom_misses"],
            "generations": stats["generations"],

            # Calculated rates
            "memory_hit_rate_percent": round(memory_hit_rate, 2),
            "rom_hit_rate_percent": round(rom_hit_rate, 2),
            "overall_hit_rate_percent": round(overall_hit_rate, 2),

            # Response times
            "avg_response_time_ms": round(avg_response_time, 2),
            "min_response_time_ms": round(min_response_time, 2),
            "max_response_time_ms": round(max_response_time, 2),

            # Memory cache details
            "memory_cache": memory_cache_stats,

            # ROM cache availability
            "rom_cache_enabled": self._rom_cache is not None and self._rom_cache.cache_enabled,

            # Batch cache stats
            "pending_rom_cache_saves": sum(len(saves) for saves in self._pending_rom_cache_saves.values()),
            "batch_save_timer_active": self._batch_save_timer.isActive(),

            # Total requests
            "total_requests": total_requests
        }
