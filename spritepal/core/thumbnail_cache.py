"""
Thumbnail cache for sprite gallery performance optimization.
Provides disk and memory caching for generated thumbnails.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QMutex, QMutexLocker
from PySide6.QtGui import QPixmap

from utils.logging_config import get_logger

logger = get_logger(__name__)

# Cache size management constants
DEFAULT_MAX_CACHE_MB = 100  # Maximum disk cache size in MB
PRUNE_CHECK_INTERVAL = 100  # Check pruning every N saves

class ThumbnailCache:
    """Cache system for sprite thumbnails."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_cache_mb: float = DEFAULT_MAX_CACHE_MB,
        auto_prune: bool = True,
        max_memory_cache_mb: float = 100.0,  # Memory cache limit in MB
    ):
        """
        Initialize the thumbnail cache.

        Args:
            cache_dir: Directory for disk cache (default: temp dir)
            max_cache_mb: Maximum disk cache size in MB (default: 100MB)
            auto_prune: Whether to automatically prune cache (default: True)
            max_memory_cache_mb: Maximum memory cache size in MB (default: 100MB)
        """
        if cache_dir is None:
            import tempfile
            cache_dir = Path(tempfile.gettempdir()) / "spritepal_thumbnails"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Memory cache (O(1) LRU using OrderedDict)
        self._memory_cache_mutex = QMutex()
        self.memory_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self.memory_cache_limit = 200  # Max items in memory (count-based limit)

        # Memory size tracking for pressure-based eviction
        self._memory_usage_bytes = 0
        self.max_memory_cache_bytes = int(max_memory_cache_mb * 1024 * 1024)

        # Cache metadata
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        self.metadata = self._load_metadata()

        # Auto-pruning configuration
        self.max_cache_mb = max_cache_mb
        self.auto_prune = auto_prune
        self._save_count = 0
        self._access_count = 0  # For debounced metadata saves on cache hits

        logger.info(f"Thumbnail cache initialized at: {self.cache_dir}")

        # Initial prune check on startup
        if self.auto_prune:
            self._maybe_prune()

    def _load_metadata(self) -> dict[str, Any]:
        """Load cache metadata from disk, migrating entries if needed."""
        if self.metadata_file.exists():
            try:
                with Path(self.metadata_file).open() as f:
                    metadata = json.load(f)

                # Migrate entries that lack last_access timestamp
                entries = metadata.get("entries", {})
                current_time = time.time()
                needs_save = False

                for cache_key, entry in entries.items():
                    if "last_access" not in entry:
                        # Use file mtime as fallback for existing entries
                        cache_file = self.cache_dir / f"{cache_key}.png"
                        if cache_file.exists():
                            entry["last_access"] = cache_file.stat().st_mtime
                        else:
                            entry["last_access"] = current_time
                        needs_save = True

                if needs_save:
                    logger.info("Migrated cache metadata to include access timestamps")

                return metadata
            except Exception as e:
                logger.error(f"Failed to load cache metadata: {e}")
        return {"version": "1.0", "entries": {}}

    def _save_metadata(self):
        """Save cache metadata to disk."""
        try:
            with Path(self.metadata_file).open('w') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache metadata: {e}")

    def _get_cache_key(
        self,
        rom_hash: str,
        offset: int,
        size: int,
        palette_index: int = 8
    ) -> str:
        """
        Generate a cache key for a thumbnail.

        Args:
            rom_hash: Hash of the ROM file
            offset: Sprite offset in ROM
            size: Thumbnail size
            palette_index: Palette used

        Returns:
            Cache key string
        """
        key_data = f"{rom_hash}_{offset:08X}_{size}_{palette_index}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def get_thumbnail(
        self,
        rom_hash: str,
        offset: int,
        size: int,
        palette_index: int = 8
    ) -> QPixmap | None:
        """
        Get a thumbnail from cache.

        Args:
            rom_hash: Hash of the ROM file
            offset: Sprite offset
            size: Thumbnail size
            palette_index: Palette index

        Returns:
            Cached QPixmap or None if not found
        """
        cache_key = self._get_cache_key(rom_hash, offset, size, palette_index)

        # Check memory cache first (thread-safe)
        with QMutexLocker(self._memory_cache_mutex):
            if cache_key in self.memory_cache:
                # Move to end (most recently used) - O(1) operation
                self.memory_cache.move_to_end(cache_key)
                logger.debug(f"Thumbnail cache hit (memory): {cache_key}")
                return self.memory_cache[cache_key]

        # Check disk cache
        cache_file = self.cache_dir / f"{cache_key}.png"
        if cache_file.exists():
            try:
                pixmap = QPixmap(str(cache_file))
                if not pixmap.isNull():
                    # Add to memory cache
                    self._add_to_memory_cache(cache_key, pixmap)

                    # Update access time in metadata (debounced to reduce I/O)
                    entries = cast(dict[str, Any], self.metadata.get("entries", {}))
                    if cache_key in entries:
                        entries[cache_key]["last_access"] = time.time()
                        self._access_count += 1
                        # Save metadata every 50 accesses to reduce disk writes
                        if self._access_count % 50 == 0:
                            self._save_metadata()

                    logger.debug(f"Thumbnail cache hit (disk): {cache_key}")
                    return pixmap
            except Exception as e:
                logger.error(f"Failed to load cached thumbnail: {e}")

        logger.debug(f"Thumbnail cache miss: {cache_key}")
        return None

    def save_thumbnail(
        self,
        rom_hash: str,
        offset: int,
        size: int,
        palette_index: int,
        pixmap: QPixmap
    ):
        """
        Save a thumbnail to cache.

        Args:
            rom_hash: Hash of the ROM file
            offset: Sprite offset
            size: Thumbnail size
            palette_index: Palette index
            pixmap: Thumbnail pixmap to cache
        """
        if pixmap.isNull():
            return

        cache_key = self._get_cache_key(rom_hash, offset, size, palette_index)

        # Save to disk
        cache_file = self.cache_dir / f"{cache_key}.png"
        try:
            pixmap.save(str(cache_file), "PNG")

            # Update metadata with access timestamp for LRU eviction
            entries = cast(dict[str, Any], self.metadata["entries"])
            entries[cache_key] = {
                "rom_hash": rom_hash,
                "offset": offset,
                "size": size,
                "palette": palette_index,
                "file": cache_file.name,
                "last_access": time.time(),
            }
            self._save_metadata()

            # Add to memory cache
            self._add_to_memory_cache(cache_key, pixmap)

            logger.debug(f"Thumbnail cached: {cache_key}")

            # Check for pruning periodically
            self._save_count += 1
            if self.auto_prune and self._save_count % PRUNE_CHECK_INTERVAL == 0:
                self._maybe_prune()

        except Exception as e:
            logger.error(f"Failed to cache thumbnail: {e}")

    def _add_to_memory_cache(self, key: str, pixmap: QPixmap):
        """Add an item to the memory cache with LRU eviction (thread-safe).

        Uses both count-based and memory-based eviction to prevent OOM.
        """
        with QMutexLocker(self._memory_cache_mutex):
            # Calculate pixmap memory size (width * height * 4 bytes for RGBA)
            pixmap_size = pixmap.width() * pixmap.height() * 4

            # Evict oldest entries until we're under the memory limit
            while (self._memory_usage_bytes + pixmap_size > self.max_memory_cache_bytes
                   and self.memory_cache):
                _, evicted_pixmap = self.memory_cache.popitem(last=False)
                evicted_size = evicted_pixmap.width() * evicted_pixmap.height() * 4
                self._memory_usage_bytes -= evicted_size
                logger.debug(f"Evicted thumbnail from memory cache (memory pressure): {evicted_size} bytes")

            # Also enforce count-based limit - O(1) operation with OrderedDict
            while len(self.memory_cache) >= self.memory_cache_limit and self.memory_cache:
                _, evicted_pixmap = self.memory_cache.popitem(last=False)
                evicted_size = evicted_pixmap.width() * evicted_pixmap.height() * 4
                self._memory_usage_bytes -= evicted_size
                logger.debug(f"Evicted thumbnail from memory cache (count limit): {evicted_size} bytes")

            # Add new item (automatically at end of OrderedDict)
            self.memory_cache[key] = pixmap
            self._memory_usage_bytes += pixmap_size

    def _get_cache_size_mb(self) -> float:
        """Get total disk cache size in MB."""
        total = sum(f.stat().st_size for f in self.cache_dir.glob("*.png"))
        return total / (1024 * 1024)

    def _maybe_prune(self) -> None:
        """Prune cache if it exceeds size limit using tiered strategy."""
        try:
            current_size_mb = self._get_cache_size_mb()
            if current_size_mb > self.max_cache_mb:
                logger.info(
                    f"Cache size {current_size_mb:.1f}MB exceeds limit "
                    f"{self.max_cache_mb:.1f}MB, pruning..."
                )

                # Stage 1: Age-based pruning (primary strategy)
                self.prune_cache(max_age_days=7)

                # Stage 2: If still over limit, use LRU eviction (fallback)
                current_size_mb = self._get_cache_size_mb()
                if current_size_mb > self.max_cache_mb:
                    logger.info(
                        f"Age-based pruning insufficient ({current_size_mb:.1f}MB), "
                        "applying LRU eviction..."
                    )
                    self._prune_by_size()
        except Exception as e:
            logger.warning(f"Error during cache prune check: {e}")

    def _prune_by_size(self, target_mb: float | None = None) -> int:
        """
        Remove least-recently-used files until cache is under target size.

        Args:
            target_mb: Target size in MB (default: 80% of max_cache_mb)

        Returns:
            Number of files removed
        """
        if target_mb is None:
            target_mb = self.max_cache_mb * 0.8  # Target 80% to avoid thrashing

        target_bytes = target_mb * 1024 * 1024

        # Get all cache files with their access times and sizes
        entries = cast(dict[str, Any], self.metadata.get("entries", {}))
        file_info: list[tuple[str, float, int]] = []  # (cache_key, last_access, size)

        for cache_file in self.cache_dir.glob("*.png"):
            cache_key = cache_file.stem
            try:
                size = cache_file.stat().st_size
                # Get access time from metadata, fallback to file mtime
                if cache_key in entries and "last_access" in entries[cache_key]:
                    last_access = entries[cache_key]["last_access"]
                else:
                    last_access = cache_file.stat().st_mtime
                file_info.append((cache_key, last_access, size))
            except OSError:
                continue

        # Sort by access time (oldest first = LRU)
        file_info.sort(key=lambda x: x[1])

        # Calculate current size
        current_bytes = sum(info[2] for info in file_info)

        removed_count = 0
        for cache_key, _, size in file_info:
            if current_bytes <= target_bytes:
                break

            cache_file = self.cache_dir / f"{cache_key}.png"
            try:
                cache_file.unlink()
                current_bytes -= size
                removed_count += 1

                # Remove from metadata
                if cache_key in entries:
                    del entries[cache_key]
            except Exception as e:
                logger.error(f"Failed to remove cache file {cache_file}: {e}")

        if removed_count > 0:
            self._save_metadata()
            logger.info(f"LRU eviction removed {removed_count} files")

        return removed_count

    def clear_cache(self):
        """Clear all cached thumbnails."""
        # Clear memory cache (thread-safe)
        with QMutexLocker(self._memory_cache_mutex):
            self.memory_cache.clear()
            self._memory_usage_bytes = 0

        # Clear disk cache
        for cache_file in self.cache_dir.glob("*.png"):
            try:
                cache_file.unlink()
            except Exception as e:
                logger.error(f"Failed to delete cache file {cache_file}: {e}")

        # Clear metadata
        self.metadata = {"version": "1.0", "entries": {}}
        self._save_metadata()

        logger.info("Thumbnail cache cleared")

    def get_cache_stats(self) -> dict[str, int | float]:
        """Get cache statistics including memory usage."""
        disk_files = list(self.cache_dir.glob("*.png"))
        disk_size = sum(f.stat().st_size for f in disk_files)

        with QMutexLocker(self._memory_cache_mutex):
            memory_items = len(self.memory_cache)
            memory_bytes = self._memory_usage_bytes

        return {
            "memory_items": memory_items,
            "memory_limit": self.memory_cache_limit,
            "memory_size_mb": memory_bytes / (1024 * 1024),
            "memory_limit_mb": self.max_memory_cache_bytes / (1024 * 1024),
            "disk_items": len(disk_files),
            "disk_size_mb": disk_size / (1024 * 1024),
            "total_items": len(self.metadata.get("entries", {}))
        }

    def prune_cache(self, max_age_days: int = 7):
        """
        Remove old cache entries.

        Args:
            max_age_days: Remove entries older than this many days
        """
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60

        removed_count = 0
        for cache_file in self.cache_dir.glob("*.png"):
            try:
                file_age = current_time - cache_file.stat().st_mtime
                if file_age > max_age_seconds:
                    cache_file.unlink()
                    removed_count += 1

                    # Remove from metadata
                    cache_key = cache_file.stem
                    entries = cast(dict[str, Any], self.metadata.get("entries", {}))
                    if cache_key in entries:
                        del entries[cache_key]

            except Exception as e:
                logger.error(f"Failed to prune cache file {cache_file}: {e}")

        if removed_count > 0:
            self._save_metadata()
            logger.info(f"Pruned {removed_count} old cache entries")

    def get_rom_hash(self, rom_path: str) -> str:
        """
        Calculate hash for a ROM file.

        Args:
            rom_path: Path to ROM file

        Returns:
            SHA-256 hash of the ROM
        """
        hasher = hashlib.sha256()

        try:
            with Path(rom_path).open('rb') as f:
                # Read in chunks for large files
                while chunk := f.read(8192):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash ROM file: {e}")
            # Return a placeholder hash
            return hashlib.sha256(rom_path.encode()).hexdigest()

# Global cache instance
_thumbnail_cache: ThumbnailCache | None = None

def get_thumbnail_cache() -> ThumbnailCache:
    """Get the global thumbnail cache instance."""
    global _thumbnail_cache
    if _thumbnail_cache is None:
        _thumbnail_cache = ThumbnailCache()
    return _thumbnail_cache
