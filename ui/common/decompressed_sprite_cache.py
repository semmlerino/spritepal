"""
Cache for decompressed sprite thumbnails in the Paged Tile View.

Uses LRU eviction with byte-based limits to manage memory efficiently
when scanning ROM for HAL-compressed sprites.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QImage

from core.services.lru_cache import BaseLRUCache

logger = logging.getLogger(__name__)


def _qimage_byte_size(image: QImage) -> int:
    """Calculate the byte size of a QImage for cache eviction."""
    return image.sizeInBytes()


class DecompressedSpriteCache(BaseLRUCache[QImage]):
    """
    LRU cache for decompressed sprite thumbnails.

    Optimized for the decompressed tile view use case with appropriate defaults
    for caching decompressed sprite images during ROM exploration.

    Key differences from PagedTileViewCache:
    - Caches individual sprite thumbnails (not full page grids)
    - Keys are based on offset + step_size + palette_hash
    - Smaller default capacity since sprites are larger than raw tile pages
    """

    # Defaults for decompressed sprite caching
    DEFAULT_MAX_SPRITES = 200  # More sprites, smaller images
    DEFAULT_MAX_BYTES = 64 * 1024 * 1024  # 64 MB

    def __init__(
        self,
        max_sprites: int = DEFAULT_MAX_SPRITES,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        """
        Initialize the decompressed sprite cache.

        Args:
            max_sprites: Maximum number of sprite thumbnails to cache
            max_bytes: Maximum total byte size for cached images
        """
        super().__init__(
            max_size=max_sprites,
            max_bytes=max_bytes,
            size_fn=_qimage_byte_size,
            name="DecompressedSpriteCache",
        )
        logger.debug(
            f"DecompressedSpriteCache initialized: max_sprites={max_sprites}, "
            f"max_bytes={max_bytes / (1024 * 1024):.1f} MB"
        )

    @staticmethod
    def make_key(offset: int, step_size: int, palette_hash: int = 0) -> str:
        """
        Create a cache key for a decompressed sprite thumbnail.

        Args:
            offset: ROM byte offset where decompression was attempted
            step_size: Step size used for the page layout
            palette_hash: Hash of the palette colors (0 if default/grayscale)

        Returns:
            Cache key string
        """
        return f"decomp:{offset}:{step_size}:{palette_hash}"

    @staticmethod
    def make_page_key(
        page_offset: int,
        cols: int,
        rows: int,
        step_size: int,
        palette_hash: int = 0,
    ) -> str:
        """
        Create a cache key for a full decompressed page composite.

        Args:
            page_offset: Starting ROM byte offset of the page
            cols: Number of columns in the grid
            rows: Number of rows in the grid
            step_size: Step size between cells
            palette_hash: Hash of the palette colors

        Returns:
            Cache key string
        """
        return f"decomp_page:{page_offset}:{cols}x{rows}:{step_size}:{palette_hash}"

    def get_sprite(
        self,
        offset: int,
        step_size: int,
        palette_hash: int = 0,
    ) -> QImage | None:
        """
        Get a cached sprite thumbnail.

        Args:
            offset: ROM byte offset
            step_size: Step size
            palette_hash: Hash of the palette

        Returns:
            Cached QImage or None if not in cache
        """
        key = self.make_key(offset, step_size, palette_hash)
        return self.get(key)

    def put_sprite(
        self,
        offset: int,
        step_size: int,
        image: QImage,
        palette_hash: int = 0,
    ) -> None:
        """
        Cache a decompressed sprite thumbnail.

        Args:
            offset: ROM byte offset
            step_size: Step size
            image: Rendered sprite thumbnail
            palette_hash: Hash of the palette
        """
        key = self.make_key(offset, step_size, palette_hash)
        self.put(key, image)

    def get_page(
        self,
        page_offset: int,
        cols: int,
        rows: int,
        step_size: int,
        palette_hash: int = 0,
    ) -> QImage | None:
        """
        Get a cached page composite image.

        Args:
            page_offset: Starting ROM byte offset of the page
            cols: Number of columns
            rows: Number of rows
            step_size: Step size between cells
            palette_hash: Hash of the palette

        Returns:
            Cached QImage or None if not in cache
        """
        key = self.make_page_key(page_offset, cols, rows, step_size, palette_hash)
        return self.get(key)

    def put_page(
        self,
        page_offset: int,
        cols: int,
        rows: int,
        step_size: int,
        image: QImage,
        palette_hash: int = 0,
    ) -> None:
        """
        Cache a page composite image.

        Args:
            page_offset: Starting ROM byte offset of the page
            cols: Number of columns
            rows: Number of rows
            step_size: Step size between cells
            image: Rendered page composite
            palette_hash: Hash of the palette
        """
        key = self.make_page_key(page_offset, cols, rows, step_size, palette_hash)
        self.put(key, image)

    def invalidate_offset_range(self, start_offset: int, end_offset: int) -> int:
        """
        Invalidate all cached sprites that overlap with the given offset range.

        Useful when ROM data changes or palette is updated.

        Args:
            start_offset: Start of the range to invalidate
            end_offset: End of the range to invalidate

        Returns:
            Number of sprites invalidated
        """
        invalidated = 0
        keys_to_remove = []

        with self._lock:
            for key in self._cache:
                try:
                    # Parse key format: "decomp:offset:step_size:palette_hash"
                    # or "decomp_page:offset:colsxrows:step_size:palette_hash"
                    parts = key.split(":")
                    if len(parts) >= 3 and parts[0] == "decomp":
                        sprite_offset = int(parts[1])
                        # Check if offset is within range
                        if start_offset <= sprite_offset < end_offset:
                            keys_to_remove.append(key)
                    elif len(parts) >= 4 and parts[0] == "decomp_page":
                        page_offset = int(parts[1])
                        dims = parts[2].split("x")
                        cols, rows = int(dims[0]), int(dims[1])
                        step_size = int(parts[3])
                        page_end = page_offset + (cols * rows * step_size)
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
                f"Invalidated {invalidated} cached sprites for offset range 0x{start_offset:06X}-0x{end_offset:06X}"
            )

        return invalidated

    def invalidate_all(self) -> None:
        """Clear all cached sprites."""
        self.clear()
        logger.debug("All cached decompressed sprites invalidated")
