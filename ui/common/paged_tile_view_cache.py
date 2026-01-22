"""
Cache for rendered tile page images in the Paged Tile View.

Uses LRU eviction with byte-based limits to manage memory efficiently
when navigating large ROM tile ranges.
"""

from __future__ import annotations

from PySide6.QtGui import QImage

from core.services.lru_cache import BaseLRUCache
from utils.logging_config import get_logger

logger = get_logger(__name__)


def _qimage_byte_size(image: QImage) -> int:
    """Calculate the byte size of a QImage for cache eviction."""
    return image.sizeInBytes()


class PagedTileViewCache(BaseLRUCache[QImage]):
    """
    LRU cache for rendered tile page images.

    Optimized for the paged tile view use case with appropriate defaults
    for caching tile grid pages during ROM exploration.
    """

    # Defaults for tile page caching
    DEFAULT_MAX_PAGES = 10
    DEFAULT_MAX_BYTES = 128 * 1024 * 1024  # 128 MB

    def __init__(
        self,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        """
        Initialize the paged tile view cache.

        Args:
            max_pages: Maximum number of page images to cache
            max_bytes: Maximum total byte size for cached images
        """
        super().__init__(
            max_size=max_pages,
            max_bytes=max_bytes,
            size_fn=_qimage_byte_size,
            name="PagedTileViewCache",
        )
        logger.debug(
            f"PagedTileViewCache initialized: max_pages={max_pages}, max_bytes={max_bytes / (1024 * 1024):.1f} MB"
        )

    @staticmethod
    def make_key(offset: int, cols: int, rows: int, palette_hash: int = 0) -> str:
        """
        Create a cache key for a tile page.

        Args:
            offset: Starting byte offset in ROM data
            cols: Number of tile columns in the grid
            rows: Number of tile rows in the grid
            palette_hash: Hash of the palette colors (0 if default/grayscale)

        Returns:
            Cache key string
        """
        return f"{offset}:{cols}x{rows}:{palette_hash}"

    def get_page(self, offset: int, cols: int, rows: int, palette_hash: int = 0) -> QImage | None:
        """
        Get a cached page image.

        Args:
            offset: Starting byte offset in ROM data
            cols: Number of tile columns
            rows: Number of tile rows
            palette_hash: Hash of the palette

        Returns:
            Cached QImage or None if not in cache
        """
        key = self.make_key(offset, cols, rows, palette_hash)
        return self.get(key)

    def put_page(
        self,
        offset: int,
        cols: int,
        rows: int,
        image: QImage,
        palette_hash: int = 0,
    ) -> None:
        """
        Cache a rendered page image.

        Args:
            offset: Starting byte offset in ROM data
            cols: Number of tile columns
            rows: Number of tile rows
            image: Rendered page image
            palette_hash: Hash of the palette
        """
        key = self.make_key(offset, cols, rows, palette_hash)
        self.put(key, image)

    def invalidate_offset_range(self, start_offset: int, end_offset: int) -> int:
        """
        Invalidate all cached pages that overlap with the given offset range.

        Useful when ROM data changes or palette is updated.

        Args:
            start_offset: Start of the range to invalidate
            end_offset: End of the range to invalidate

        Returns:
            Number of pages invalidated
        """
        invalidated = 0
        keys_to_remove = []

        with self._lock:
            for key in self._cache:
                try:
                    # Parse key format: "offset:colsxrows:palette_hash"
                    parts = key.split(":")
                    if len(parts) >= 2:
                        page_offset = int(parts[0])
                        dims = parts[1].split("x")
                        cols, rows = int(dims[0]), int(dims[1])
                        bytes_per_page = cols * rows * 32  # 32 bytes per 4bpp tile
                        page_end = page_offset + bytes_per_page

                        # Check for overlap
                        if page_offset < end_offset and page_end > start_offset:
                            keys_to_remove.append(key)
                except (ValueError, IndexError):
                    continue

        for key in keys_to_remove:
            if self.remove(key):
                invalidated += 1

        if invalidated > 0:
            logger.debug(
                f"Invalidated {invalidated} cached pages for offset range 0x{start_offset:06X}-0x{end_offset:06X}"
            )

        return invalidated

    def invalidate_all(self) -> None:
        """Clear all cached pages."""
        self.clear()
        logger.debug("All cached tile pages invalidated")
