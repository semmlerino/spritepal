"""
Thumbnail cache for QImage thumbnails.

Extends BaseLRUCache to provide thread-safe caching of QImage thumbnails
with both count-based and memory-based eviction.
"""

from __future__ import annotations

from PySide6.QtGui import QImage

from core.services.lru_cache import BaseLRUCache


class ThumbnailCache(BaseLRUCache[QImage]):
    """
    Thread-safe LRU cache for QImage thumbnails.

    Uses BaseLRUCache with QImage-specific size calculation for memory management.
    Keys are strings in the format "offset:size" to identify thumbnails by
    their ROM offset and compressed size.
    """

    # Default limits for thumbnail caching
    DEFAULT_MAX_ITEMS = 100
    DEFAULT_MAX_BYTES = 64 * 1024 * 1024  # 64 MB

    def __init__(
        self,
        max_items: int = DEFAULT_MAX_ITEMS,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        """
        Initialize thumbnail cache.

        Args:
            max_items: Maximum number of thumbnails to cache
            max_bytes: Maximum memory usage in bytes
        """
        super().__init__(
            max_size=max_items,
            max_bytes=max_bytes,
            size_fn=self._image_size,
            name="ThumbnailCache",
        )

    @staticmethod
    def _image_size(img: QImage) -> int:
        """Calculate memory size of a QImage."""
        return img.sizeInBytes()

    @staticmethod
    def make_key(offset: int, size: int, source_type: str = "") -> str:
        """
        Create a cache key from offset, size, and optional source type.

        Args:
            offset: ROM offset of the sprite
            size: Compressed size of the sprite
            source_type: Optional source type ("rom", "mesen", "library").
                        Empty string for backwards compatibility.

        Returns:
            String key in format "offset:size" or "offset:size:source_type"
        """
        if source_type:
            return f"{offset}:{size}:{source_type}"
        return f"{offset}:{size}"
