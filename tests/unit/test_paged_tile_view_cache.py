"""
Tests for PagedTileViewCache.

Tests the LRU cache for tile page images, including key generation,
caching operations, and invalidation.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QImage

from ui.common.paged_tile_view_cache import PagedTileViewCache


class TestPagedTileViewCache:
    """Test the PagedTileViewCache implementation."""

    def test_cache_creation(self) -> None:
        """Test cache creation with default and custom sizes."""
        # Default creation
        cache = PagedTileViewCache()
        assert len(cache) == 0
        assert cache.max_size == PagedTileViewCache.DEFAULT_MAX_PAGES
        assert cache.max_bytes == PagedTileViewCache.DEFAULT_MAX_BYTES

        # Custom sizes
        cache = PagedTileViewCache(max_pages=5, max_bytes=64 * 1024 * 1024)
        assert cache.max_size == 5
        assert cache.max_bytes == 64 * 1024 * 1024

    def test_make_key(self) -> None:
        """Test key generation from offset, dimensions, and palette hash."""
        key = PagedTileViewCache.make_key(0x10000, 50, 50, 0)
        assert key == "65536:50x50:0"

        key = PagedTileViewCache.make_key(0, 20, 20, 12345)
        assert key == "0:20x20:12345"

        key = PagedTileViewCache.make_key(0xFFFFFF, 100, 100, -1)
        assert key == "16777215:100x100:-1"

    def test_cache_put_and_get_page(self) -> None:
        """Test basic put_page and get_page operations."""
        cache = PagedTileViewCache(max_pages=10)

        # Create a test QImage (50x50 tiles * 8 pixels = 400x400 pixels)
        image = QImage(400, 400, QImage.Format.Format_RGBA8888)
        image.fill(0xFF0000FF)

        # Test miss
        assert cache.get_page(0, 50, 50, 0) is None

        # Test put and get
        cache.put_page(0, 50, 50, image, 0)
        cached = cache.get_page(0, 50, 50, 0)
        assert cached is not None
        assert cached.width() == 400
        assert cached.height() == 400

    def test_cache_different_palettes(self) -> None:
        """Test that different palette hashes result in cache misses."""
        cache = PagedTileViewCache(max_pages=10)

        image1 = QImage(100, 100, QImage.Format.Format_RGBA8888)
        image1.fill(0xFF0000FF)
        image2 = QImage(100, 100, QImage.Format.Format_RGBA8888)
        image2.fill(0x00FF00FF)

        # Store with different palette hashes
        cache.put_page(0, 10, 10, image1, palette_hash=100)
        cache.put_page(0, 10, 10, image2, palette_hash=200)

        # Get with specific palette hashes
        cached1 = cache.get_page(0, 10, 10, 100)
        cached2 = cache.get_page(0, 10, 10, 200)
        cached_other = cache.get_page(0, 10, 10, 300)

        assert cached1 is not None
        assert cached2 is not None
        assert cached_other is None

    def test_cache_eviction_by_count(self) -> None:
        """Test LRU eviction when max pages is reached."""
        cache = PagedTileViewCache(max_pages=2, max_bytes=100 * 1024 * 1024)

        # Create test images
        images = []
        for i in range(3):
            img = QImage(100, 100, QImage.Format.Format_RGBA8888)
            img.fill(0xFF000000 + i)
            images.append(img)

        # Add 3 items to a cache of size 2
        cache.put_page(0, 10, 10, images[0], 0)
        cache.put_page(3200, 10, 10, images[1], 0)
        cache.put_page(6400, 10, 10, images[2], 0)

        # First item should be evicted
        assert cache.get_page(0, 10, 10, 0) is None
        assert cache.get_page(3200, 10, 10, 0) is not None
        assert cache.get_page(6400, 10, 10, 0) is not None
        assert len(cache) == 2

    def test_invalidate_offset_range(self) -> None:
        """Test invalidation of cached pages within an offset range."""
        cache = PagedTileViewCache(max_pages=10)

        # Create test images
        # Each page with 10x10 tiles = 100 tiles * 32 bytes = 3200 bytes per page
        for i in range(5):
            img = QImage(80, 80, QImage.Format.Format_RGBA8888)
            img.fill(0xFF000000 + i)
            cache.put_page(i * 3200, 10, 10, img, 0)

        assert len(cache) == 5

        # Invalidate pages 1-3 (offsets 3200-9600)
        # Page 0 (0-3199) should remain
        # Page 1 (3200-6399) should be invalidated
        # Page 2 (6400-9599) should be invalidated
        # Page 3 (9600-12799) should be invalidated
        # Page 4 (12800-15999) should remain
        invalidated = cache.invalidate_offset_range(3200, 12800)

        assert invalidated == 3
        assert len(cache) == 2
        assert cache.get_page(0, 10, 10, 0) is not None
        assert cache.get_page(3200, 10, 10, 0) is None
        assert cache.get_page(6400, 10, 10, 0) is None
        assert cache.get_page(9600, 10, 10, 0) is None
        assert cache.get_page(12800, 10, 10, 0) is not None

    def test_invalidate_all(self) -> None:
        """Test clearing all cached pages."""
        cache = PagedTileViewCache(max_pages=10)

        for i in range(5):
            img = QImage(80, 80, QImage.Format.Format_RGBA8888)
            img.fill(0xFF000000 + i)
            cache.put_page(i * 3200, 10, 10, img, 0)

        assert len(cache) == 5

        cache.invalidate_all()

        assert len(cache) == 0
        for i in range(5):
            assert cache.get_page(i * 3200, 10, 10, 0) is None

    def test_stats(self) -> None:
        """Test cache statistics."""
        cache = PagedTileViewCache(max_pages=10)

        # Create and cache an image
        img = QImage(80, 80, QImage.Format.Format_RGBA8888)
        img.fill(0xFF000000)
        cache.put_page(0, 10, 10, img, 0)

        # Miss
        cache.get_page(3200, 10, 10, 0)

        # Hit
        cache.get_page(0, 10, 10, 0)

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["cache_size"] == 1
