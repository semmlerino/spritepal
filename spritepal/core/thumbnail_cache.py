"""
Thumbnail cache for sprite gallery performance optimization.
Provides disk and memory caching for generated thumbnails.
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QMutex, QMutexLocker
from PySide6.QtGui import QPixmap

from utils.logging_config import get_logger

logger = get_logger(__name__)

class ThumbnailCache:
    """Cache system for sprite thumbnails."""

    def __init__(self, cache_dir: Path | None = None):
        """
        Initialize the thumbnail cache.

        Args:
            cache_dir: Directory for disk cache (default: temp dir)
        """
        if cache_dir is None:
            import tempfile
            cache_dir = Path(tempfile.gettempdir()) / "spritepal_thumbnails"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Memory cache (O(1) LRU using OrderedDict)
        self._memory_cache_mutex = QMutex()
        self.memory_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self.memory_cache_limit = 200  # Max items in memory

        # Cache metadata
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        self.metadata = self._load_metadata()

        logger.info(f"Thumbnail cache initialized at: {self.cache_dir}")

    def _load_metadata(self) -> dict[str, Any]:
        """Load cache metadata from disk."""
        if self.metadata_file.exists():
            try:
                with Path(self.metadata_file).open() as f:
                    return json.load(f)
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

            # Update metadata
            entries = cast(dict[str, Any], self.metadata["entries"])
            entries[cache_key] = {
                "rom_hash": rom_hash,
                "offset": offset,
                "size": size,
                "palette": palette_index,
                "file": cache_file.name
            }
            self._save_metadata()

            # Add to memory cache
            self._add_to_memory_cache(cache_key, pixmap)

            logger.debug(f"Thumbnail cached: {cache_key}")

        except Exception as e:
            logger.error(f"Failed to cache thumbnail: {e}")

    def _add_to_memory_cache(self, key: str, pixmap: QPixmap):
        """Add an item to the memory cache with LRU eviction (thread-safe)."""
        with QMutexLocker(self._memory_cache_mutex):
            # Remove oldest if at limit - O(1) operation with OrderedDict
            if len(self.memory_cache) >= self.memory_cache_limit:
                self.memory_cache.popitem(last=False)

            # Add new item (automatically at end of OrderedDict)
            self.memory_cache[key] = pixmap

    def clear_cache(self):
        """Clear all cached thumbnails."""
        # Clear memory cache (thread-safe)
        with QMutexLocker(self._memory_cache_mutex):
            self.memory_cache.clear()

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
        """Get cache statistics."""
        disk_files = list(self.cache_dir.glob("*.png"))
        disk_size = sum(f.stat().st_size for f in disk_files)

        with QMutexLocker(self._memory_cache_mutex):
            memory_items = len(self.memory_cache)

        return {
            "memory_items": memory_items,
            "memory_limit": self.memory_cache_limit,
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
        import time
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
