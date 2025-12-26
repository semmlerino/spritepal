"""
Cache Operations Manager.

Handles ROM cache operations including statistics, clearing,
and scan progress tracking. This is a focused sub-manager delegated
from CoreOperationsManager.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from core.exceptions import CacheError

if TYPE_CHECKING:
    from core.services.rom_cache import ROMCache


class CacheOperationsManager(QObject):
    """
    Manages cache operations for ROM data.

    Responsibilities:
    - Cache statistics retrieval
    - Cache clearing (with optional age filtering)
    - Scan progress persistence
    - Cache monitoring signals

    Thread-safe: ROMCache provides its own thread safety.
    """

    # Cache monitoring signals
    cache_operation_started = Signal(str, str)  # operation, key
    cache_hit = Signal(str, float)  # key, load_time
    cache_miss = Signal(str)  # key
    cache_saved = Signal(str, int)  # key, size_bytes

    def __init__(
        self,
        *,
        rom_cache: ROMCache | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize cache operations manager.

        Args:
            rom_cache: ROM cache instance
            parent: Qt parent object
        """
        super().__init__(parent)
        self._logger = logging.getLogger(__name__)
        self._rom_cache = rom_cache

    # ========== Helper Methods ==========

    def _ensure_rom_cache(self) -> ROMCache:
        """Ensure ROM cache is available."""
        if self._rom_cache is None:
            raise CacheError("ROM cache not initialized")
        return self._rom_cache

    # ========== Cache Statistics ==========

    def get_cache_stats(self) -> dict[str, object]:  # Cache stats with mixed types
        """Get ROM cache statistics."""
        rom_cache = self._ensure_rom_cache()
        return dict(rom_cache.get_cache_stats())  # Convert Mapping to dict

    def clear_rom_cache(self, older_than_days: int | None = None) -> int:
        """
        Clear ROM scan cache.

        Args:
            older_than_days: If specified, only clear files older than this many days

        Returns:
            Number of cache files removed
        """
        rom_cache = self._ensure_rom_cache()
        removed_count = rom_cache.clear_cache(older_than_days)
        self._logger.info(f"ROM cache cleared: {removed_count} files removed")
        return removed_count

    # ========== Scan Progress ==========

    def get_scan_progress(
        self, rom_path: str, scan_params: dict[str, int]
    ) -> dict[str, object] | None:  # Scan progress with found sprites, current offset, completed flag
        """
        Get cached scan progress for resumable scanning.

        Args:
            rom_path: Path to ROM file
            scan_params: Scan parameters (int values like start offset, end offset)

        Returns:
            Dictionary with scan progress or None if not cached
        """
        rom_cache = self._ensure_rom_cache()
        result = rom_cache.get_partial_scan_results(rom_path, scan_params)
        return dict(result) if result else None  # Convert Mapping to dict

    def save_scan_progress(
        self,
        rom_path: str,
        scan_params: dict[str, int],
        found_sprites: list[Mapping[str, object]],  # Sprite data dicts
        current_offset: int,
        completed: bool = False,
    ) -> bool:
        """
        Save partial scan results for resumable scanning.

        Args:
            rom_path: Path to ROM file
            scan_params: Scan parameters (int values like start offset, end offset)
            found_sprites: List of sprites found so far
            current_offset: Current scan position
            completed: Whether the scan is complete

        Returns:
            True if saved successfully, False otherwise
        """
        rom_cache = self._ensure_rom_cache()
        return rom_cache.save_partial_scan_results(rom_path, scan_params, found_sprites, current_offset, completed)

    def clear_scan_progress(
        self,
        rom_path: str | None = None,
        scan_params: dict[str, int] | None = None,
    ) -> int:
        """
        Clear scan progress caches.

        Args:
            rom_path: If specified, only clear caches for this ROM
            scan_params: If specified, only clear cache for this specific scan

        Returns:
            Number of files removed
        """
        rom_cache = self._ensure_rom_cache()
        removed_count = rom_cache.clear_scan_progress_cache(rom_path, scan_params)
        self._logger.info(f"Scan progress cache cleared: {removed_count} files removed")
        return removed_count

    # ========== State Management ==========

    def reset_state(self) -> None:
        """Reset internal state for test isolation."""
        # No mutable state to reset - cache state is managed by ROMCache
        pass
