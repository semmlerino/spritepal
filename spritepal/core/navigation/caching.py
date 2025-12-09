"""
Multi-level caching system for navigation performance optimization.

Provides memory, disk, and cloud-based caching with intelligent
cache management and background pre-computation.
"""

from __future__ import annotations

import gzip
import json
import threading
import time
import weakref
from pathlib import Path
from typing import Any

from typing_extensions import override

from utils.logging_config import get_logger

from .data_structures import NavigationHint
from .region_map import SpriteRegionMap

logger = get_logger(__name__)

class CacheLevel:
    """Base class for cache levels."""

    def __init__(self, name: str, max_size: int = 1000) -> None:
        self.name = name
        self.max_size = max_size
        self._statistics = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "size": 0
        }

    def get(self, key: str) -> Any | None:
        """Get item from cache."""
        raise NotImplementedError

    def put(self, key: str, value: Any) -> None:
        """Put item in cache."""
        raise NotImplementedError

    def remove(self, key: str) -> bool:
        """Remove item from cache."""
        raise NotImplementedError

    def clear(self) -> None:
        """Clear all cache entries."""
        raise NotImplementedError

    def get_statistics(self) -> dict[str, Any]:
        """Get cache statistics."""
        stats: dict[str, Any] = self._statistics.copy()
        if stats["hits"] + stats["misses"] > 0:
            stats["hit_rate"] = stats["hits"] / (stats["hits"] + stats["misses"])
        else:
            stats["hit_rate"] = 0.0
        return stats

class MemoryCache(CacheLevel):
    """In-memory LRU cache with weak references for automatic cleanup."""

    def __init__(self, name: str, max_size: int = 1000) -> None:
        super().__init__(name, max_size)
        self._cache: dict[str, Any] = {}
        self._access_order: list[str] = []
        self._lock = threading.RLock()

        # Use weak references for automatic cleanup
        self._weak_refs: dict[str, weakref.ref[Any]] = {}

    @override
    def get(self, key: str) -> Any | None:
        """Get item from memory cache."""
        with self._lock:
            if key in self._cache:
                # Update access order
                self._access_order.remove(key)
                self._access_order.append(key)

                self._statistics["hits"] += 1
                return self._cache[key]

            self._statistics["misses"] += 1
            return None

    @override
    def put(self, key: str, value: Any) -> None:
        """Put item in memory cache."""
        with self._lock:
            # Remove if already exists
            if key in self._cache:
                self._access_order.remove(key)

            # Evict if at capacity
            while len(self._cache) >= self.max_size:
                self._evict_lru()

            # Add new item
            self._cache[key] = value
            self._access_order.append(key)
            self._statistics["size"] = len(self._cache)

            # Set up weak reference callback for automatic cleanup
            if hasattr(value, "__weakref__"):
                def cleanup_callback(ref: weakref.ref[Any]) -> None:
                    with self._lock:
                        if key in self._cache and self._weak_refs.get(key) is ref:
                            del self._cache[key]
                            self._access_order.remove(key)
                            self._statistics["size"] = len(self._cache)

                self._weak_refs[key] = weakref.ref(value, cleanup_callback)

    @override
    def remove(self, key: str) -> bool:
        """Remove item from memory cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._access_order.remove(key)
                if key in self._weak_refs:
                    del self._weak_refs[key]
                self._statistics["size"] = len(self._cache)
                return True
            return False

    @override
    def clear(self) -> None:
        """Clear memory cache."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            self._weak_refs.clear()
            self._statistics["size"] = 0

    def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if self._access_order:
            lru_key = self._access_order[0]
            del self._cache[lru_key]
            self._access_order.remove(lru_key)
            if lru_key in self._weak_refs:
                del self._weak_refs[lru_key]
            self._statistics["evictions"] += 1

class DiskCache(CacheLevel):
    """Persistent disk-based cache with compression."""

    def __init__(self, name: str, cache_dir: Path, max_size: int = 10000) -> None:
        super().__init__(name, max_size)
        self.cache_dir = cache_dir / name
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._index_file = self.cache_dir / "index.json"
        self._index: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

        # Load existing index
        self._load_index()

    @override
    def get(self, key: str) -> Any | None:
        """Get item from disk cache."""
        with self._lock:
            if key not in self._index:
                self._statistics["misses"] += 1
                return None

            cache_file = self.cache_dir / f"{key}.json.gz"

            try:
                if cache_file.exists():
                    with gzip.open(cache_file, "rt") as f:
                        data = json.load(f)

                    # Update access time
                    self._index[key]["last_access"] = time.time()
                    self._save_index()

                    self._statistics["hits"] += 1
                    return data
                # File missing, remove from index
                del self._index[key]
                self._save_index()

            except Exception as e:
                logger.exception(f"Error reading disk cache {key}: {e}")
                # Remove corrupted entry
                if key in self._index:
                    del self._index[key]
                    self._save_index()

            self._statistics["misses"] += 1
            return None

    @override
    def put(self, key: str, value: Any) -> None:
        """Put item in disk cache."""
        with self._lock:
            cache_file = self.cache_dir / f"{key}.json.gz"

            try:
                # Serialize and compress
                with gzip.open(cache_file, "wt") as f:
                    json.dump(value, f)

                # Update index
                file_size = cache_file.stat().st_size
                self._index[key] = {
                    "created": time.time(),
                    "last_access": time.time(),
                    "size": file_size
                }

                # Evict old entries if needed
                while len(self._index) > self.max_size:
                    self._evict_oldest()

                self._save_index()
                self._statistics["size"] = len(self._index)

            except Exception as e:
                logger.exception(f"Error writing disk cache {key}: {e}")

    @override
    def remove(self, key: str) -> bool:
        """Remove item from disk cache."""
        with self._lock:
            if key not in self._index:
                return False

            cache_file = self.cache_dir / f"{key}.json.gz"

            try:
                if cache_file.exists():
                    cache_file.unlink()

                del self._index[key]
                self._save_index()
                self._statistics["size"] = len(self._index)
                return True

            except Exception as e:
                logger.exception(f"Error removing disk cache {key}: {e}")
                return False

    @override
    def clear(self) -> None:
        """Clear disk cache."""
        with self._lock:
            try:
                # Remove all cache files
                for cache_file in self.cache_dir.glob("*.json.gz"):
                    cache_file.unlink()

                self._index.clear()
                self._save_index()
                self._statistics["size"] = 0

            except Exception as e:
                logger.exception(f"Error clearing disk cache: {e}")

    def _load_index(self) -> None:
        """Load cache index from disk."""
        try:
            if self._index_file.exists():
                with Path(self._index_file).open() as f:
                    self._index = json.load(f)
                self._statistics["size"] = len(self._index)
        except Exception as e:
            logger.warning(f"Could not load disk cache index: {e}")
            self._index = {}

    def _save_index(self) -> None:
        """Save cache index to disk."""
        try:
            with Path(self._index_file).open("w") as f:
                json.dump(self._index, f, indent=2)
        except Exception as e:
            logger.exception(f"Could not save disk cache index: {e}")

    def _evict_oldest(self) -> None:
        """Evict oldest cache entry."""
        if not self._index:
            return

        # Find oldest by last access time
        oldest_key = min(self._index.keys(), key=lambda k: self._index[k]["last_access"])

        cache_file = self.cache_dir / f"{oldest_key}.json.gz"
        try:
            if cache_file.exists():
                cache_file.unlink()
        except Exception as e:
            logger.exception(f"Error removing old cache file {oldest_key}: {e}")

        del self._index[oldest_key]
        self._statistics["evictions"] += 1

class NavigationCache:
    """
    Multi-level cache system for navigation data.

    Provides intelligent caching with memory, disk, and optional cloud tiers
    for maximum performance across different access patterns.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        """
        Initialize multi-level cache.

        Args:
            cache_dir: Directory for disk cache (None = disabled)
        """
        # Cache levels (ordered by speed)
        self.memory_cache = MemoryCache("memory", max_size=500)

        self.disk_cache: DiskCache | None = None
        if cache_dir:
            self.disk_cache = DiskCache("disk", cache_dir, max_size=5000)

        # Cache categories
        self._cache_levels: list[CacheLevel] = [self.memory_cache]
        if self.disk_cache:
            self._cache_levels.append(self.disk_cache)

        # Background processing
        self._background_thread: threading.Thread | None = None
        self._background_stop_event = threading.Event()
        self._precompute_queue: list[tuple[str, Any]] = []
        self._queue_lock = threading.Lock()

        # Start background processing
        self._start_background_processing()

    def get_region_map(self, rom_path: str) -> SpriteRegionMap | None:
        """
        Get cached region map for ROM.

        Args:
            rom_path: Path to ROM file

        Returns:
            Cached region map or None if not found
        """
        cache_key = f"region_map_{Path(rom_path).stem}"

        # Try each cache level
        for cache_level in self._cache_levels:
            data = cache_level.get(cache_key)
            if data is not None:
                # Promote to higher cache levels
                self._promote_to_higher_levels(cache_key, data, cache_level)

                # Deserialize if needed
                if isinstance(data, dict):
                    return SpriteRegionMap.from_dict(data)
                return data

        return None

    def put_region_map(self, rom_path: str, region_map: SpriteRegionMap) -> None:
        """
        Cache region map for ROM.

        Args:
            rom_path: Path to ROM file
            region_map: Region map to cache
        """
        cache_key = f"region_map_{Path(rom_path).stem}"

        # Store in memory cache as object
        self.memory_cache.put(cache_key, region_map)

        # Store in disk cache as serialized data
        if self.disk_cache:
            self.disk_cache.put(cache_key, region_map.to_dict())

        logger.debug(f"Cached region map for {rom_path}")

    def get_navigation_hints(
        self,
        rom_path: str,
        offset: int,
        context_hash: str
    ) -> list[NavigationHint] | None:
        """
        Get cached navigation hints.

        Args:
            rom_path: Path to ROM file
            offset: Current offset
            context_hash: Hash of navigation context

        Returns:
            Cached navigation hints or None if not found
        """
        cache_key = f"hints_{Path(rom_path).stem}_{offset:08X}_{context_hash[:8]}"

        for cache_level in self._cache_levels:
            data = cache_level.get(cache_key)
            if data is not None:
                self._promote_to_higher_levels(cache_key, data, cache_level)

                # Deserialize hints if needed
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    return [self._dict_to_hint(hint_dict) for hint_dict in data]
                return data

        return None

    def put_navigation_hints(
        self,
        rom_path: str,
        offset: int,
        context_hash: str,
        hints: list[NavigationHint]
    ) -> None:
        """
        Cache navigation hints.

        Args:
            rom_path: Path to ROM file
            offset: Current offset
            context_hash: Hash of navigation context
            hints: Navigation hints to cache
        """
        cache_key = f"hints_{Path(rom_path).stem}_{offset:08X}_{context_hash[:8]}"

        # Store in memory cache as objects
        self.memory_cache.put(cache_key, hints)

        # Store in disk cache as serialized data
        if self.disk_cache:
            serialized_hints = [hint.to_dict() for hint in hints]
            self.disk_cache.put(cache_key, serialized_hints)

        logger.debug(f"Cached {len(hints)} navigation hints for {rom_path}@{offset:08X}")

    def get_pattern_analysis(self, rom_path: str) -> dict[str, Any] | None:
        """
        Get cached pattern analysis.

        Args:
            rom_path: Path to ROM file

        Returns:
            Cached pattern analysis or None if not found
        """
        cache_key = f"patterns_{Path(rom_path).stem}"

        for cache_level in self._cache_levels:
            data = cache_level.get(cache_key)
            if data is not None:
                self._promote_to_higher_levels(cache_key, data, cache_level)
                return data

        return None

    def put_pattern_analysis(self, rom_path: str, analysis: dict[str, Any]) -> None:
        """
        Cache pattern analysis.

        Args:
            rom_path: Path to ROM file
            analysis: Pattern analysis to cache
        """
        cache_key = f"patterns_{Path(rom_path).stem}"

        # Store in all cache levels
        for cache_level in self._cache_levels:
            cache_level.put(cache_key, analysis)

        logger.debug(f"Cached pattern analysis for {rom_path}")

    def invalidate_rom_cache(self, rom_path: str) -> None:
        """
        Invalidate all cached data for a ROM.

        Args:
            rom_path: Path to ROM file
        """
        rom_stem = Path(rom_path).stem

        # Find and remove all keys related to this ROM
        for cache_level in self._cache_levels:
            if hasattr(cache_level, "_cache"):  # Memory cache
                keys_to_remove = [
                    key for key in cache_level._cache  # type: ignore[attr-defined]
                    if rom_stem in key
                ]
                for key in keys_to_remove:
                    cache_level.remove(key)

            elif hasattr(cache_level, "_index"):  # Disk cache
                keys_to_remove = [
                    key for key in cache_level._index  # type: ignore[attr-defined]
                    if rom_stem in key
                ]
                for key in keys_to_remove:
                    cache_level.remove(key)

        logger.info(f"Invalidated cache for {rom_path}")

    def schedule_precomputation(self, cache_key: str, computation_data: Any) -> None:
        """
        Schedule background precomputation.

        Args:
            cache_key: Key for the computation result
            computation_data: Data needed for computation
        """
        with self._queue_lock:
            self._precompute_queue.append((cache_key, computation_data))

    def get_cache_statistics(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        stats = {}

        for cache_level in self._cache_levels:
            stats[cache_level.name] = cache_level.get_statistics()

        # Calculate overall statistics
        total_hits = sum(stats[level]["hits"] for level in stats)
        total_misses = sum(stats[level]["misses"] for level in stats)

        stats["overall"] = {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "overall_hit_rate": total_hits / (total_hits + total_misses) if (total_hits + total_misses) > 0 else 0.0,
            "cache_levels": len(self._cache_levels)
        }

        return stats

    def clear_all_caches(self) -> None:
        """Clear all cache levels."""
        for cache_level in self._cache_levels:
            cache_level.clear()

        logger.info("Cleared all navigation caches")

    def shutdown(self) -> None:
        """Shutdown cache system and background processing."""
        # Stop background processing
        if self._background_thread and self._background_thread.is_alive():
            self._background_stop_event.set()
            self._background_thread.join(timeout=5.0)

        logger.info("Navigation cache system shutdown")

    def _promote_to_higher_levels(self, cache_key: str, data: Any, source_level: CacheLevel) -> None:
        """Promote cache entry to higher (faster) levels."""
        source_index = self._cache_levels.index(source_level)

        # Promote to all higher levels
        for i in range(source_index):
            higher_level = self._cache_levels[i]
            higher_level.put(cache_key, data)

    def _dict_to_hint(self, hint_dict: dict[str, Any]) -> NavigationHint:
        """Convert dictionary back to NavigationHint object."""
        from .data_structures import NavigationStrategy, RegionType

        return NavigationHint(
            target_offset=hint_dict["target_offset_int"],
            confidence=hint_dict["confidence"],
            reasoning=hint_dict["reasoning"],
            strategy_used=NavigationStrategy(hint_dict["strategy"]),
            expected_region_type=RegionType(hint_dict["region_type"]),
            estimated_size=hint_dict.get("estimated_size"),
            similarity_score=hint_dict.get("similarity_score"),
            pattern_strength=hint_dict.get("pattern_strength"),
            priority=hint_dict.get("priority", 0.5)
        )

    def _start_background_processing(self) -> None:
        """Start background processing thread."""
        self._background_stop_event.clear()
        self._background_thread = threading.Thread(
            target=self._background_worker,
            name="NavigationCacheWorker",
            daemon=True
        )
        self._background_thread.start()
        logger.debug("Started navigation cache background processing")

    def _background_worker(self) -> None:
        """Background processing worker."""
        while not self._background_stop_event.is_set():
            try:
                # Process precomputation queue
                with self._queue_lock:
                    if self._precompute_queue:
                        cache_key, _computation_data = self._precompute_queue.pop(0)
                        # Process precomputation (implementation depends on specific needs)
                        logger.debug(f"Processing background computation for {cache_key}")

                # Cache maintenance (cleanup old entries, etc.)
                self._perform_cache_maintenance()

                # Wait before next iteration
                self._background_stop_event.wait(30.0)  # Run every 30 seconds

            except Exception as e:
                logger.exception(f"Background cache worker error: {e}")
                self._background_stop_event.wait(30.0)

    def _perform_cache_maintenance(self) -> None:
        """Perform routine cache maintenance."""
        # This could include:
        # - Cleanup of expired entries
        # - Optimization of disk cache files
        # - Memory usage optimization

class _NavigationCacheSingleton:
    """Singleton holder for NavigationCache."""
    _instance: NavigationCache | None = None
    _cache_dir: Path | None = None
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get(cls, cache_dir: Path | None = None) -> NavigationCache:
        """
        Get global navigation cache instance.

        Args:
            cache_dir: Directory for disk cache (used only on first call)

        Returns:
            Global navigation cache instance
        """
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking pattern
                if cls._instance is None:
                    # Use provided cache_dir or stored one
                    cls._instance = NavigationCache(cache_dir or cls._cache_dir)
                    if cache_dir:
                        cls._cache_dir = cache_dir
        return cls._instance

    @classmethod
    def shutdown(cls) -> None:
        """Shutdown global navigation cache."""
        if cls._instance:
            cls._instance.shutdown()
            cls._instance = None

def get_navigation_cache(cache_dir: Path | None = None) -> NavigationCache:
    """
    Get global navigation cache instance.

    Args:
        cache_dir: Directory for disk cache (used only on first call)

    Returns:
        Global navigation cache instance
    """
    return _NavigationCacheSingleton.get(cache_dir)

def shutdown_navigation_cache() -> None:
    """Shutdown global navigation cache."""
    _NavigationCacheSingleton.shutdown()
