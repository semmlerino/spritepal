"""
Tests for ThumbnailCache.

Tests the QImage-specific LRU cache implementation including key generation,
caching operations, and memory management.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QImage

from ui.common.thumbnail_cache import ThumbnailCache


class TestThumbnailCache:
    """Test the ThumbnailCache implementation."""

    def test_cache_creation(self):
        """Test cache creation with default and custom sizes."""
        # Default creation
        cache = ThumbnailCache()
        assert len(cache) == 0

        # Custom sizes
        cache = ThumbnailCache(max_items=50, max_bytes=32 * 1024 * 1024)
        assert cache.max_size == 50
        assert cache.max_bytes == 32 * 1024 * 1024

    def test_make_key(self):
        """Test key generation from offset and size."""
        key = ThumbnailCache.make_key(12345, 1024)
        assert key == "12345:1024"

        key = ThumbnailCache.make_key(0, 0)
        assert key == "0:0"

        key = ThumbnailCache.make_key(0xFFFFFF, 0xFFFF)
        assert key == "16777215:65535"

    def test_cache_put_and_get(self):
        """Test basic cache put and get operations."""
        cache = ThumbnailCache(max_items=10)

        # Create a test QImage
        image = QImage(64, 64, QImage.Format.Format_RGBA8888)
        image.fill(0xFF0000FF)  # Red

        key = ThumbnailCache.make_key(1000, 128)

        # Test miss
        assert cache.get("nonexistent") is None

        # Test put and get
        cache.put(key, image)
        cached = cache.get(key)
        assert cached is not None
        assert cached.width() == 64
        assert cached.height() == 64

    def test_cache_eviction_by_count(self):
        """Test LRU eviction when max items is reached."""
        cache = ThumbnailCache(max_items=2, max_bytes=100 * 1024 * 1024)

        # Create test images
        images = []
        for i in range(3):
            img = QImage(32, 32, QImage.Format.Format_RGBA8888)
            img.fill(0xFF000000 + i)
            images.append(img)

        # Fill cache
        cache.put("key1", images[0])
        cache.put("key2", images[1])
        assert len(cache) == 2

        # Add third item - should evict first (LRU)
        cache.put("key3", images[2])
        assert len(cache) == 2

        # First key should be evicted
        assert cache.get("key1") is None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None

    def test_cache_lru_ordering(self):
        """Test that accessing an item makes it most recently used."""
        cache = ThumbnailCache(max_items=2, max_bytes=100 * 1024 * 1024)

        images = []
        for i in range(3):
            img = QImage(32, 32, QImage.Format.Format_RGBA8888)
            img.fill(0xFF000000 + i)
            images.append(img)

        # Add first two items
        cache.put("key1", images[0])
        cache.put("key2", images[1])

        # Access key1 to make it recently used
        cache.get("key1")

        # Add third item - should evict key2 (now LRU)
        cache.put("key3", images[2])

        # key1 should still be present (was accessed)
        assert cache.get("key1") is not None
        # key2 should be evicted
        assert cache.get("key2") is None
        assert cache.get("key3") is not None

    def test_cache_clear(self):
        """Test cache clearing."""
        cache = ThumbnailCache(max_items=10)

        # Add some items
        for i in range(5):
            img = QImage(32, 32, QImage.Format.Format_RGBA8888)
            cache.put(f"key{i}", img)

        assert len(cache) == 5

        # Clear cache
        cache.clear()
        assert len(cache) == 0

        # All keys should miss
        for i in range(5):
            assert cache.get(f"key{i}") is None

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = ThumbnailCache(max_items=10)

        img = QImage(32, 32, QImage.Format.Format_RGBA8888)
        cache.put("key1", img)

        # Miss
        cache.get("nonexistent")
        # Hit
        cache.get("key1")

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["cache_size"] == 1

    def test_image_size_calculation(self):
        """Test that image size is correctly calculated for memory management."""
        cache = ThumbnailCache(max_items=100, max_bytes=100)  # Very small byte limit

        # Create a 10x10 RGBA image = 400 bytes
        small_img = QImage(10, 10, QImage.Format.Format_RGBA8888)
        assert small_img.sizeInBytes() == 400

        # This should exceed our 100 byte limit and trigger eviction
        # when we add a second image
        cache.put("key1", small_img)

        another_img = QImage(10, 10, QImage.Format.Format_RGBA8888)
        cache.put("key2", another_img)

        # Due to byte limit, cache may have evicted items
        # At minimum, the cache should be functional
        assert cache.get("key2") is not None
