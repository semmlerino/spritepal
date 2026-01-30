"""Thread-safe repository for parsed CaptureResult objects.

Provides shared caching between PreviewService and AsyncStaleEntryDetector
to eliminate duplicate JSON parsing of capture files.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMutex, QMutexLocker

from core.mesen_integration.click_extractor import CaptureResult, MesenCaptureParser
from utils.logging_config import get_logger

logger = get_logger(__name__)


class CaptureResultRepository:
    """Thread-safe cache for parsed CaptureResult objects.

    Caches parsed capture files keyed by path. Cache entries are invalidated
    when file modification time changes. Thread-safe for concurrent access
    from main thread (PreviewService) and worker threads (AsyncStaleEntryDetector).

    Usage:
        repo = CaptureResultRepository()
        result = repo.get_or_parse(capture_path)  # Thread-safe
    """

    def __init__(self) -> None:
        """Initialize the repository with empty cache."""
        # Cache: path -> (CaptureResult, mtime)
        self._cache: dict[Path, tuple[CaptureResult, float]] = {}
        self._mutex = QMutex()
        self._parser = MesenCaptureParser()

    def get_or_parse(self, path: Path) -> CaptureResult:
        """Get cached CaptureResult or parse file if cache miss/stale.

        Thread-safe. If the file's mtime has changed since caching,
        the cache entry is invalidated and the file is re-parsed.

        Args:
            path: Path to capture JSON file

        Returns:
            Parsed CaptureResult

        Raises:
            OSError: If file cannot be read
            CaptureParseError: If file cannot be parsed
        """
        # Get current mtime outside lock (filesystem operation)
        current_mtime = path.stat().st_mtime

        with QMutexLocker(self._mutex):
            # Check cache
            if path in self._cache:
                cached_result, cached_mtime = self._cache[path]
                if cached_mtime == current_mtime:
                    logger.debug("Cache hit for %s", path.name)
                    return cached_result
                # Mtime changed - invalidate
                logger.debug("Cache invalidated for %s (mtime changed)", path.name)

            # Parse outside lock would be better for concurrency,
            # but parsing is fast and we need to ensure cache consistency
            result = self._parser.parse_file(path)
            self._cache[path] = (result, current_mtime)
            logger.debug("Cached parse result for %s", path.name)
            return result

    def get_if_cached(self, path: Path) -> CaptureResult | None:
        """Get cached CaptureResult if available and fresh.

        Thread-safe. Returns None if not cached or cache is stale.

        Args:
            path: Path to capture JSON file

        Returns:
            Cached CaptureResult or None
        """
        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            return None

        with QMutexLocker(self._mutex):
            if path in self._cache:
                cached_result, cached_mtime = self._cache[path]
                if cached_mtime == current_mtime:
                    return cached_result
            return None

    def invalidate(self, path: Path) -> bool:
        """Invalidate cache entry for a specific path.

        Thread-safe.

        Args:
            path: Path to invalidate

        Returns:
            True if entry was cached and removed, False otherwise
        """
        with QMutexLocker(self._mutex):
            if path in self._cache:
                del self._cache[path]
                logger.debug("Invalidated cache for %s", path.name)
                return True
            return False

    def invalidate_all(self) -> int:
        """Clear all cache entries.

        Thread-safe.

        Returns:
            Number of entries cleared
        """
        with QMutexLocker(self._mutex):
            count = len(self._cache)
            self._cache.clear()
            if count > 0:
                logger.debug("Invalidated all %d cache entries", count)
            return count

    def cache_size(self) -> int:
        """Get current cache size.

        Thread-safe.

        Returns:
            Number of cached entries
        """
        with QMutexLocker(self._mutex):
            return len(self._cache)
