"""
LRU Cache for sprite previews to enable instant display during slider scrubbing.

This module provides a memory-efficient cache for preview data:
- LRU eviction policy to manage memory usage
- Cache key generation based on ROM path and offset
- Thread-safe operations for concurrent access
- Size-based eviction to prevent memory bloat
"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from utils.logging_config import get_logger

logger = get_logger(__name__)

class PreviewCache:
    """
    LRU cache for sprite preview data.

    Features:
    - Thread-safe operations
    - Size-based eviction (both count and memory)
    - Efficient key generation
    - Memory usage tracking
    """

    def __init__(self, max_size: int = 20, max_memory_mb: float = 2.0):
        """
        Initialize preview cache.

        Args:
            max_size: Maximum number of entries to cache
            max_memory_mb: Maximum memory usage in MB
        """
        self._max_size = max_size
        self._max_memory_bytes = int(max_memory_mb * 1024 * 1024)

        # Thread-safe collections
        self._cache = OrderedDict()
        self._memory_usage = 0
        self._lock = threading.RLock()

        logger.debug(f"PreviewCache initialized: max_size={max_size}, max_memory={max_memory_mb}MB")

    def make_key(self, rom_path: str, offset: int, sprite_config_hash: str | None = None) -> str:
        """
        Generate cache key for preview data.

        Args:
            rom_path: Path to ROM file
            offset: ROM offset for sprite
            sprite_config_hash: Optional sprite configuration hash

        Returns:
            str: Cache key
        """
        # Use filename and size for ROM identity (faster than full path hash)
        try:
            rom_name = Path(rom_path).name
            # Single stat() call avoids TOCTOU race with exists()
            rom_size = Path(rom_path).stat().st_size
        except OSError:
            rom_name = Path(rom_path).name if rom_path else "unknown"
            rom_size = 0

        # Create key components
        key_parts = [
            rom_name,
            str(rom_size),
            f"{offset:06X}",
        ]

        if sprite_config_hash:
            key_parts.append(sprite_config_hash)

        # Generate deterministic key
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()[:16]

    def get(self, key: str) -> tuple[bytes, int, int, str | None]:
        """
        Get cached preview data.

        Args:
            key: Cache key

        Returns:
            Optional tuple of (tile_data, width, height, sprite_name) or None
        """
        with self._lock:
            if key not in self._cache:
                return (b"", 0, 0, None)

            # Move to end (mark as recently used)
            entry = self._cache.pop(key)
            self._cache[key] = entry

            logger.debug(f"Cache hit for key {key}")
            return entry["data"]

    def put(self, key: str, data: tuple[bytes, int, int, str]) -> None:
        """
        Store preview data in cache.

        Args:
            key: Cache key
            data: Tuple of (tile_data, width, height, sprite_name)
        """
        tile_data, _width, _height, sprite_name = data
        # Handle None sprite_name to avoid TypeError on len()
        name_len = len(sprite_name) if sprite_name else 0
        data_size = len(tile_data) + name_len + 16  # Rough size estimate

        with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                old_entry = self._cache.pop(key)
                self._memory_usage -= old_entry["size"]

            # Create new entry
            entry = {
                "data": data,
                "size": data_size
            }

            # Add new entry
            self._cache[key] = entry
            self._memory_usage += data_size

            # Evict if necessary
            self._evict_if_needed()

            logger.debug(f"Cached preview for key {key} (size: {data_size} bytes)")

    def _evict_if_needed(self) -> None:
        """Evict entries if cache limits are exceeded."""
        evicted_count = 0

        # Evict by count limit
        while len(self._cache) > self._max_size:
            self._evict_oldest()
            evicted_count += 1

        # Evict by memory limit
        while self._memory_usage > self._max_memory_bytes and self._cache:
            self._evict_oldest()
            evicted_count += 1

        if evicted_count > 0:
            logger.debug(f"Evicted {evicted_count} cache entries")

    def _evict_oldest(self) -> None:
        """Evict the oldest (least recently used) entry."""
        if not self._cache:
            return

        # Remove oldest entry (first in OrderedDict)
        key, entry = self._cache.popitem(last=False)
        self._memory_usage -= entry["size"]

        logger.debug(f"Evicted cache entry {key}")

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            entry_count = len(self._cache)
            if self._cache:
                self._cache.clear()
            self._memory_usage = 0

            if entry_count > 0:
                logger.debug(f"Cleared {entry_count} cache entries")

    def get_stats(self) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny] - Cache statistics dict
        """
        Get cache statistics.

        Returns:
            dict: Cache statistics
        """
        with self._lock:
            return {
                "entry_count": len(self._cache),
                "max_size": self._max_size,
                "memory_usage_bytes": self._memory_usage,
                "max_memory_bytes": self._max_memory_bytes,
                "memory_usage_mb": self._memory_usage / (1024 * 1024),
                "max_memory_mb": self._max_memory_bytes / (1024 * 1024),
                "memory_utilization": self._memory_usage / self._max_memory_bytes if self._max_memory_bytes > 0 else 0
            }

    def contains(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            bool: True if key exists in cache
        """
        with self._lock:
            return key in self._cache

    def remove(self, key: str) -> bool:
        """
        Remove specific entry from cache.

        Args:
            key: Cache key to remove

        Returns:
            bool: True if entry was removed, False if not found
        """
        with self._lock:
            if key not in self._cache:
                return False

            entry = self._cache.pop(key)
            self._memory_usage -= entry["size"]

            logger.debug(f"Removed cache entry {key}")
            return True
