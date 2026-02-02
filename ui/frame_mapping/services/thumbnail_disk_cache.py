"""Disk cache for thumbnail PNG bytes with LRU eviction."""

import json
import threading
import time
from pathlib import Path
from typing import Any

from utils.logging_config import get_logger

logger = get_logger(__name__)


class ThumbnailDiskCache:
    """Thread-safe disk cache for thumbnail PNG bytes with LRU eviction."""

    METADATA_FILENAME = "metadata.json"
    METADATA_VERSION = "1.0"
    METADATA_FLUSH_INTERVAL = 30  # seconds
    METADATA_FLUSH_COUNT = 10  # updates

    def __init__(self, cache_dir: Path, max_size_mb: int = 100) -> None:
        """Initialize cache directory, load metadata, perform stale entry cleanup.

        Args:
            cache_dir: Directory to store cache files
            max_size_mb: Maximum cache size in megabytes
        """
        self.cache_dir = Path(cache_dir)
        self.max_size = max_size_mb * 1024 * 1024  # Convert to bytes
        self._lock = threading.Lock()
        self._metadata_lock = threading.Lock()
        self._disabled = False
        self._pending_updates = 0
        self._last_flush_time = time.time()

        # Metadata structure
        self._metadata: dict[str, Any] = {  # pyright: ignore[reportExplicitAny] - JSON metadata
            "version": self.METADATA_VERSION,
            "entries": {},
            "total_size": 0,
            "max_size": self.max_size,
        }

        # Ensure cache directory exists
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"Failed to create cache directory: {e}")
            self._disabled = True
            return

        # Load existing metadata
        self._load_metadata()

        # Clean up stale entries
        self._cleanup_stale_entries()

    def _load_metadata(self) -> None:
        """Load metadata from disk or rebuild from directory scan."""
        metadata_path = self.cache_dir / self.METADATA_FILENAME

        try:
            if metadata_path.exists():
                with open(metadata_path) as f:
                    loaded = json.load(f)
                    # Validate structure
                    if isinstance(loaded, dict) and "entries" in loaded and "total_size" in loaded:
                        self._metadata = loaded
                        self._metadata["max_size"] = self.max_size
                        logger.info(
                            f"Loaded cache metadata: {len(self._metadata['entries'])} entries, "
                            f"{self._metadata['total_size']} bytes"
                        )
                    else:
                        raise ValueError("Invalid metadata structure")
            else:
                logger.info("No existing metadata found, starting fresh")

        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.warning(f"Corrupted metadata.json: {e}, rebuilding from directory")
            self._rebuild_metadata_from_disk()

    def _rebuild_metadata_from_disk(self) -> None:
        """Rebuild metadata by scanning cache directory for PNG files."""
        self._metadata = {
            "version": self.METADATA_VERSION,
            "entries": {},
            "total_size": 0,
            "max_size": self.max_size,
        }

        try:
            for png_file in self.cache_dir.glob("*.png"):
                cache_key = png_file.stem
                file_size = png_file.stat().st_size

                # Create minimal entry (no source path info available)
                self._metadata["entries"][cache_key] = {
                    "path": "",
                    "mtime": 0,
                    "size": 0,
                    "palette_hash": 0,
                    "created": png_file.stat().st_ctime,
                    "last_access": png_file.stat().st_atime,
                    "file_size": file_size,
                }
                self._metadata["total_size"] += file_size

            logger.info(f"Rebuilt metadata from {len(self._metadata['entries'])} PNG files")
            self._flush_metadata()

        except OSError as e:
            logger.warning(f"Failed to rebuild metadata: {e}")
            self._disabled = True

    def _cleanup_stale_entries(self) -> None:
        """Remove entries where source file doesn't exist."""
        stale_keys = []

        for cache_key, entry in self._metadata["entries"].items():
            source_path = entry.get("path", "")
            if source_path and not Path(source_path).exists():
                stale_keys.append(cache_key)

        if stale_keys:
            logger.info(f"Removing {len(stale_keys)} stale entries")
            for cache_key in stale_keys:
                self._remove_entry(cache_key)

            self._flush_metadata()

    def _remove_entry(self, cache_key: str) -> None:
        """Remove a cache entry and its PNG file.

        Args:
            cache_key: Cache key to remove
        """
        entry = self._metadata["entries"].get(cache_key)
        if not entry:
            return

        # Remove PNG file
        png_path = self.cache_dir / f"{cache_key}.png"
        try:
            if png_path.exists():
                png_path.unlink()
        except OSError as e:
            logger.warning(f"Failed to delete cache file {png_path}: {e}")

        # Update metadata
        self._metadata["total_size"] -= entry.get("file_size", 0)
        del self._metadata["entries"][cache_key]

    def _flush_metadata(self) -> None:
        """Write metadata to disk atomically."""
        if self._disabled:
            return

        metadata_path = self.cache_dir / self.METADATA_FILENAME
        temp_path = metadata_path.with_suffix(".tmp")

        try:
            with open(temp_path, "w") as f:
                json.dump(self._metadata, f, indent=2)

            # Atomic rename
            temp_path.replace(metadata_path)
            self._pending_updates = 0
            self._last_flush_time = time.time()

        except OSError as e:
            logger.warning(f"Failed to write metadata: {e}")
            if temp_path.exists():
                temp_path.unlink()

    def _maybe_flush_metadata(self) -> None:
        """Flush metadata if batching thresholds are met."""
        with self._metadata_lock:
            self._pending_updates += 1
            time_elapsed = time.time() - self._last_flush_time

            if self._pending_updates >= self.METADATA_FLUSH_COUNT or time_elapsed >= self.METADATA_FLUSH_INTERVAL:
                self._flush_metadata()

    def get(self, cache_key: str) -> bytes | None:
        """Retrieve cached PNG bytes and update last_access timestamp.

        Args:
            cache_key: Cache key to retrieve

        Returns:
            PNG bytes if found, None otherwise
        """
        if self._disabled:
            return None

        with self._lock:
            entry = self._metadata["entries"].get(cache_key)
            if not entry:
                return None

            png_path = self.cache_dir / f"{cache_key}.png"

            try:
                if not png_path.exists():
                    # File missing, remove from metadata
                    self._remove_entry(cache_key)
                    self._maybe_flush_metadata()
                    return None

                with open(png_path, "rb") as f:
                    png_bytes = f.read()

                # Update last_access
                entry["last_access"] = time.time()
                self._maybe_flush_metadata()

                return png_bytes

            except OSError as e:
                logger.warning(f"Failed to read cache file {png_path}: {e}")
                return None

    def put(
        self,
        cache_key: str,
        png_bytes: bytes,
        metadata: dict[str, Any],  # pyright: ignore[reportExplicitAny]
    ) -> None:
        """Store PNG file, update metadata, trigger eviction if needed.

        Args:
            cache_key: Cache key to store under
            png_bytes: PNG file contents
            metadata: Entry metadata (path, mtime, size, palette_hash)
        """
        if self._disabled:
            return

        with self._lock:
            png_path = self.cache_dir / f"{cache_key}.png"
            file_size = len(png_bytes)

            try:
                # Write PNG file
                with open(png_path, "wb") as f:
                    f.write(png_bytes)

            except OSError as e:
                logger.warning(f"Failed to write cache file {png_path}: {e}")
                if "No space left" in str(e) or "Disk quota" in str(e):
                    self._disabled = True
                return

            # Update metadata
            now = time.time()
            entry = {
                "path": metadata.get("path", ""),
                "mtime": metadata.get("mtime", 0),
                "size": metadata.get("size", 0),
                "palette_hash": metadata.get("palette_hash", 0),
                "created": now,
                "last_access": now,
                "file_size": file_size,
            }

            # If updating existing entry, adjust total_size
            if cache_key in self._metadata["entries"]:
                old_size = self._metadata["entries"][cache_key].get("file_size", 0)
                self._metadata["total_size"] -= old_size

            self._metadata["entries"][cache_key] = entry
            self._metadata["total_size"] += file_size

            self._maybe_flush_metadata()

            # Check if eviction needed
            if self._metadata["total_size"] > self.max_size * 1.1:
                target_size = int(self.max_size * 0.8)
                self.evict_lru(target_size)

    def evict_lru(self, target_size: int) -> None:
        """Remove least-recently-used entries to reach target size.

        Args:
            target_size: Target size in bytes
        """
        if self._disabled:
            return

        with self._lock:
            # Sort entries by last_access (oldest first)
            sorted_entries = sorted(
                self._metadata["entries"].items(),
                key=lambda x: x[1].get("last_access", 0),
            )

            removed_count = 0
            for cache_key, _entry in sorted_entries:
                if self._metadata["total_size"] <= target_size:
                    break

                self._remove_entry(cache_key)
                removed_count += 1

            if removed_count > 0:
                logger.info(f"Evicted {removed_count} entries, cache size: {self._metadata['total_size']} bytes")
                self._flush_metadata()

    def clear(self) -> None:
        """Delete all PNG files and metadata.json."""
        with self._lock:
            # Remove all PNG files
            try:
                for png_file in self.cache_dir.glob("*.png"):
                    png_file.unlink()
            except OSError as e:
                logger.warning(f"Failed to clear cache files: {e}")

            # Remove metadata
            metadata_path = self.cache_dir / self.METADATA_FILENAME
            try:
                if metadata_path.exists():
                    metadata_path.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete metadata: {e}")

            # Reset metadata
            self._metadata = {
                "version": self.METADATA_VERSION,
                "entries": {},
                "total_size": 0,
                "max_size": self.max_size,
            }

            logger.info("Cache cleared")

    def get_stats(self) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Return cache statistics.

        Returns:
            Dictionary with size, entries count, and max_size
        """
        with self._metadata_lock:
            return {
                "total_size": self._metadata["total_size"],
                "entries": len(self._metadata["entries"]),
                "max_size": self.max_size,
                "disabled": self._disabled,
            }
