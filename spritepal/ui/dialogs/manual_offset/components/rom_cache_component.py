"""
ROM Cache Component

Handles ROM cache integration and adjacent offset preloading optimization.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ui.dialogs.manual_offset_unified_integrated import UnifiedManualOffsetDialog

from utils.logging_config import get_logger

logger = get_logger(__name__)

class ROMCacheComponent:
    """
    Manages ROM cache integration for the Manual Offset Dialog.

    Handles cache initialization, preloading, and performance tracking.
    """

    def __init__(self, dialog: UnifiedManualOffsetDialog) -> None:
        """Initialize the ROM cache component."""
        self.dialog = dialog
        self.rom_cache = None
        self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
        self._adjacent_offsets_cache = set()

        # Get ROM cache instance
        try:
            from core.di_container import inject
            from core.protocols.manager_protocols import ROMCacheProtocol
            self.rom_cache = inject(ROMCacheProtocol)
        except (ImportError, ValueError):
            logger.warning("ROM cache not available")

    def initialize_rom(self, rom_path: str, rom_size: int):
        """Initialize cache for the current ROM."""
        logger.debug(f"Initializing ROM cache for {rom_path}")

        # Reset cache stats
        self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
        if self._adjacent_offsets_cache:
            self._adjacent_offsets_cache.clear()

        if self.rom_cache and self.rom_cache.cache_enabled:
            logger.debug("ROM cache is enabled")
        else:
            logger.debug("ROM cache is disabled")

    def preload_adjacent_offsets(self, current_offset: int, rom_size: int):
        """Preload adjacent offsets for smooth navigation."""
        if not self.rom_cache or not self.rom_cache.cache_enabled:
            return

        # Calculate adjacent offsets
        step_sizes = [0x100, 0x1000, 0x2000]
        for step in step_sizes:
            prev_offset = max(0, current_offset - step)
            next_offset = min(rom_size, current_offset + step)

            if prev_offset not in self._adjacent_offsets_cache:
                self._adjacent_offsets_cache.add(prev_offset)
                # Would trigger preloading here

            if next_offset not in self._adjacent_offsets_cache:
                self._adjacent_offsets_cache.add(next_offset)
                # Would trigger preloading here

    def on_cache_hit(self):
        """Handle cache hit event."""
        self._cache_stats["hits"] += 1

    def on_cache_miss(self):
        """Handle cache miss event."""
        self._cache_stats["misses"] += 1

    def update_request_count(self):
        """Update total request count."""
        self._cache_stats["total_requests"] += 1

    def get_cache_stats(self) -> dict[str, Any]:
        """Get current cache statistics."""
        return self._cache_stats.copy()

    def cleanup(self):
        """Clean up cache resources."""
        logger.debug("Cleaning up ROM cache component")
        if self._adjacent_offsets_cache:
            self._adjacent_offsets_cache.clear()
        self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
