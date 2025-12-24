"""
Generic thread-safe LRU cache with size-based eviction.

This module provides a reusable LRU cache implementation that can be
specialized for different value types. It supports both count-based
and memory-based eviction policies.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

from utils.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class BaseLRUCache(Generic[T]):
    """Thread-safe LRU cache with size-based eviction.

    This generic cache can be used for any value type. Size calculation
    is delegated to a provided function.

    Type Parameters:
        T: The type of values stored in the cache

    Thread Safety:
        All public methods are thread-safe using an RLock.
    """

    # Default limits
    DEFAULT_MAX_ITEMS = 50
    DEFAULT_MAX_BYTES = 32 * 1024 * 1024  # 32 MB

    def __init__(
        self,
        max_size: int = DEFAULT_MAX_ITEMS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        size_fn: Callable[[T], int] | None = None,
        name: str = "cache",
    ):
        """Initialize LRU cache with dual eviction policy.

        Args:
            max_size: Maximum number of cached items
            max_bytes: Maximum cache size in bytes
            size_fn: Function to calculate byte size of a value.
                     If None, size eviction is disabled.
            name: Name for logging purposes
        """
        self.max_size = max_size
        self.max_bytes = max_bytes
        self._size_fn = size_fn
        self._name = name

        self._cache: OrderedDict[str, T] = OrderedDict()
        self._sizes: dict[str, int] = {}  # Track size per key
        self._lock = threading.RLock()
        self._current_bytes = 0

        self._stats: dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "evictions_count_limit": 0,
            "evictions_byte_limit": 0,
        }
        self._last_stats_log = 0.0
        self._stats_log_interval = 60.0  # Log stats every 60 seconds

    def _calculate_size(self, value: T) -> int:
        """Calculate byte size of a value."""
        if self._size_fn is None:
            return 0  # Size tracking disabled
        return self._size_fn(value)

    def _maybe_log_stats(self) -> None:
        """Log cache statistics periodically."""
        current_time = time.time()
        if current_time - self._last_stats_log >= self._stats_log_interval:
            self._last_stats_log = current_time
            stats = self.get_stats()
            logger.debug(
                f"{self._name} stats: {stats['cache_size']}/{stats['max_size']} items, "
                f"{stats['current_mb']:.1f}/{stats['max_mb']:.1f} MB, "
                f"hit_rate={stats['hit_rate']:.1%}, evictions={stats['evictions']}"
            )

    def get(self, key: str) -> T | None:
        """Get item from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                value = self._cache.pop(key)
                self._cache[key] = value
                self._stats["hits"] += 1
                return value

            self._stats["misses"] += 1
            return None

    def put(self, key: str, value: T) -> None:
        """Put item in cache with size-aware eviction.

        Args:
            key: Cache key
            value: Value to cache
        """
        item_size = self._calculate_size(value)

        with self._lock:
            # Remove if already exists (update scenario)
            if key in self._cache:
                self._cache.pop(key)
                old_size = self._sizes.pop(key, 0)
                self._current_bytes -= old_size

            # Evict oldest items until within byte limit
            if self._size_fn is not None:
                while self._current_bytes + item_size > self.max_bytes and self._cache:
                    self._evict_oldest("byte_limit")

            # Evict oldest if over item count limit
            while len(self._cache) >= self.max_size and self._cache:
                self._evict_oldest("count_limit")

            # Add to end (most recently used)
            self._cache[key] = value
            self._sizes[key] = item_size
            self._current_bytes += item_size

            # Periodic stats logging
            self._maybe_log_stats()

    def _evict_oldest(self, reason: str) -> None:
        """Evict the oldest entry."""
        oldest_key = next(iter(self._cache))
        self._cache.pop(oldest_key)
        old_size = self._sizes.pop(oldest_key, 0)
        self._current_bytes -= old_size
        self._stats["evictions"] += 1
        self._stats[f"evictions_{reason}"] += 1

    def contains(self, key: str) -> bool:
        """Check if key exists in cache."""
        with self._lock:
            return key in self._cache

    def remove(self, key: str) -> bool:
        """Remove specific entry from cache.

        Returns:
            True if entry was removed, False if not found
        """
        with self._lock:
            if key not in self._cache:
                return False

            self._cache.pop(key)
            old_size = self._sizes.pop(key, 0)
            self._current_bytes -= old_size
            logger.debug(f"{self._name}: Removed entry {key}")
            return True

    def clear(self) -> None:
        """Clear all cached items."""
        with self._lock:
            self._cache.clear()
            self._sizes.clear()
            self._current_bytes = 0
            logger.debug(f"{self._name}: Cache cleared")

    def get_stats(self) -> dict[str, object]:
        """Get cache statistics including memory usage."""
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0.0

            return {
                **self._stats,
                "cache_size": len(self._cache),
                "max_size": self.max_size,
                "current_bytes": self._current_bytes,
                "max_bytes": self.max_bytes,
                "current_mb": self._current_bytes / (1024 * 1024),
                "max_mb": self.max_bytes / (1024 * 1024),
                "hit_rate": hit_rate,
            }

    def __len__(self) -> int:
        """Return number of items in cache."""
        with self._lock:
            return len(self._cache)
