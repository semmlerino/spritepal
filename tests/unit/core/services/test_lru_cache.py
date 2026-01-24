"""
Unit tests for BaseLRUCache thread safety and eviction behavior.

Tests the generic LRU cache implementation in core/services/lru_cache.py:
- Thread safety under concurrent read/write operations
- LRU eviction behavior (count-based and byte-based)
- RLock behavior under contention
- Statistics tracking accuracy
"""

from __future__ import annotations

import concurrent.futures
import threading
import time

import pytest

from core.services.lru_cache import BaseLRUCache


class TestBaseLRUCacheCore:
    """Test core BaseLRUCache functionality."""

    def test_basic_put_and_get(self) -> None:
        """Test basic put and get operations."""
        cache: BaseLRUCache[str] = BaseLRUCache(max_size=10, name="test_cache")

        cache.put("key1", "value1")
        cache.put("key2", "value2")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("nonexistent") is None

    def test_lru_order_on_access(self) -> None:
        """Test that get() moves item to most-recently-used position."""
        cache: BaseLRUCache[str] = BaseLRUCache(max_size=3, name="test_cache")

        cache.put("a", "1")
        cache.put("b", "2")
        cache.put("c", "3")

        # Access 'a' to make it most recently used
        cache.get("a")

        # Add 'd' - should evict 'b' (oldest after 'a' was accessed)
        cache.put("d", "4")

        assert cache.get("a") == "1"  # Should still exist
        assert cache.get("b") is None  # Should be evicted
        assert cache.get("c") == "3"  # Should still exist
        assert cache.get("d") == "4"  # Should exist

    def test_count_based_eviction(self) -> None:
        """Test eviction when max_size is exceeded."""
        cache: BaseLRUCache[str] = BaseLRUCache(max_size=5, name="test_cache")

        # Fill cache
        for i in range(5):
            cache.put(f"key{i}", f"value{i}")

        assert len(cache) == 5

        # Add 6th item - should evict oldest
        cache.put("key5", "value5")

        assert len(cache) == 5
        assert cache.get("key0") is None  # Oldest should be evicted
        assert cache.get("key5") == "value5"

    def test_byte_based_eviction(self) -> None:
        """Test eviction when max_bytes is exceeded."""

        def size_fn(value: str) -> int:
            return len(value)

        cache: BaseLRUCache[str] = BaseLRUCache(
            max_size=100,  # High count limit
            max_bytes=50,  # Low byte limit
            size_fn=size_fn,
            name="test_cache",
        )

        # Add items that total > 50 bytes
        cache.put("a", "x" * 20)  # 20 bytes
        cache.put("b", "y" * 20)  # 20 bytes (total 40)
        cache.put("c", "z" * 20)  # 20 bytes - should evict 'a' to stay under 50

        # 'a' should be evicted due to byte limit
        assert cache.get("a") is None
        assert cache.get("b") == "y" * 20
        assert cache.get("c") == "z" * 20

    def test_update_existing_key(self) -> None:
        """Test updating an existing key."""
        cache: BaseLRUCache[str] = BaseLRUCache(max_size=10, name="test_cache")

        cache.put("key1", "original")
        assert cache.get("key1") == "original"

        cache.put("key1", "updated")
        assert cache.get("key1") == "updated"
        assert len(cache) == 1

    def test_remove(self) -> None:
        """Test explicit removal of items."""
        cache: BaseLRUCache[str] = BaseLRUCache(max_size=10, name="test_cache")

        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"

        removed = cache.remove("key1")
        assert removed is True
        assert cache.get("key1") is None

        # Removing non-existent key
        removed = cache.remove("nonexistent")
        assert removed is False

    def test_clear(self) -> None:
        """Test clearing the cache."""
        cache: BaseLRUCache[str] = BaseLRUCache(max_size=10, name="test_cache")

        for i in range(5):
            cache.put(f"key{i}", f"value{i}")

        assert len(cache) == 5

        cache.clear()

        assert len(cache) == 0
        for i in range(5):
            assert cache.get(f"key{i}") is None

    def test_contains(self) -> None:
        """Test __contains__ method."""
        cache: BaseLRUCache[str] = BaseLRUCache(max_size=10, name="test_cache")

        cache.put("key1", "value1")

        assert "key1" in cache
        assert "nonexistent" not in cache

    def test_statistics_tracking(self) -> None:
        """Test that statistics are tracked correctly."""
        cache: BaseLRUCache[str] = BaseLRUCache(max_size=3, name="test_cache")

        # Misses
        cache.get("a")
        cache.get("b")

        stats = cache.get_stats()
        assert stats["misses"] == 2
        assert stats["hits"] == 0

        # Add items and hit
        cache.put("a", "1")
        cache.get("a")
        cache.get("a")

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 2

        # Evictions
        cache.put("b", "2")
        cache.put("c", "3")
        cache.put("d", "4")  # Should evict 'a' (oldest after accesses)

        stats = cache.get_stats()
        assert stats["evictions"] == 1
        assert stats["evictions_count_limit"] == 1


class TestBaseLRUCacheThreadSafety:
    """Thread safety tests for BaseLRUCache."""

    def test_concurrent_read_write(self) -> None:
        """Test concurrent read and write operations don't corrupt data."""
        cache: BaseLRUCache[int] = BaseLRUCache(max_size=100, name="concurrent_test")
        errors: list[str] = []

        def writer(start: int, count: int) -> None:
            """Write entries to cache."""
            for i in range(count):
                try:
                    cache.put(f"key{start + i}", start + i)
                except Exception as e:
                    errors.append(f"Writer error: {e}")

        def reader(start: int, count: int) -> None:
            """Read entries from cache."""
            for i in range(count):
                try:
                    cache.get(f"key{start + i}")
                except Exception as e:
                    errors.append(f"Reader error: {e}")

        # Run concurrent writers and readers
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            # 5 writers
            for i in range(5):
                futures.append(executor.submit(writer, i * 100, 100))
            # 5 readers
            for i in range(5):
                futures.append(executor.submit(reader, i * 100, 100))

            # Wait for all to complete
            for future in concurrent.futures.as_completed(futures):
                future.result()

        assert not errors, f"Errors during concurrent access: {errors}"

    def test_concurrent_eviction(self) -> None:
        """Test that eviction is thread-safe under concurrent writes."""
        cache: BaseLRUCache[int] = BaseLRUCache(max_size=50, name="eviction_test")
        errors: list[str] = []

        def writer(thread_id: int) -> None:
            """Write many entries, triggering evictions."""
            for i in range(200):
                try:
                    cache.put(f"t{thread_id}_k{i}", i)
                except Exception as e:
                    errors.append(f"Thread {thread_id} error: {e}")

        # Run many concurrent writers that will trigger evictions
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(writer, i) for i in range(10)]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        assert not errors, f"Errors during concurrent eviction: {errors}"

        # Cache should not exceed max_size
        assert len(cache) <= 50

    def test_statistics_thread_safety(self) -> None:
        """Test that statistics are thread-safe."""
        cache: BaseLRUCache[int] = BaseLRUCache(max_size=20, name="stats_test")

        def hammer_cache(thread_id: int) -> None:
            """Perform many operations to stress statistics tracking."""
            for i in range(100):
                cache.put(f"t{thread_id}_k{i}", i)
                cache.get(f"t{thread_id}_k{i}")
                cache.get(f"nonexistent_{thread_id}_{i}")

        # Run concurrent threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(hammer_cache, i) for i in range(10)]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        # Get stats - should not raise
        stats = cache.get_stats()

        # Statistics should be reasonable
        assert stats["hits"] > 0
        assert stats["misses"] > 0
        assert stats["evictions"] > 0  # We wrote more than max_size
        assert stats["hit_rate"] >= 0.0
        assert stats["hit_rate"] <= 1.0

    def test_concurrent_clear(self) -> None:
        """Test that clear() is safe during concurrent operations."""
        cache: BaseLRUCache[int] = BaseLRUCache(max_size=100, name="clear_test")
        errors: list[str] = []

        def writer() -> None:
            """Continuously write to cache."""
            for i in range(500):
                try:
                    cache.put(f"key{i}", i)
                except Exception as e:
                    errors.append(f"Writer error: {e}")

        def clearer() -> None:
            """Periodically clear the cache."""
            for _ in range(10):
                try:
                    time.sleep(0.001)
                    cache.clear()
                except Exception as e:
                    errors.append(f"Clearer error: {e}")

        # Run writer and clearer concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            futures.extend([executor.submit(writer) for _ in range(3)])
            futures.extend([executor.submit(clearer) for _ in range(2)])

            for future in concurrent.futures.as_completed(futures):
                future.result()

        assert not errors, f"Errors during concurrent clear: {errors}"

    def test_high_contention_stress(self) -> None:
        """Stress test under high contention.

        Many threads competing for the same keys to maximize lock contention.
        """

        def size_fn(value: int) -> int:
            return 8  # Fixed size

        cache: BaseLRUCache[int] = BaseLRUCache(
            max_size=10,
            max_bytes=100,
            size_fn=size_fn,
            name="stress_test",
        )
        errors: list[str] = []

        def stress_operation(thread_id: int) -> None:
            """Perform many operations on shared keys."""
            for i in range(1000):
                try:
                    # All threads compete for same small set of keys
                    key = f"shared_key_{i % 5}"
                    cache.put(key, thread_id * 1000 + i)
                    cache.get(key)
                    if i % 100 == 0:
                        cache.remove(key)
                except Exception as e:
                    errors.append(f"Thread {thread_id} error: {e}")

        # Many threads competing for same keys
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(stress_operation, i) for i in range(20)]
            for future in concurrent.futures.as_completed(futures, timeout=30.0):
                future.result()

        assert not errors, f"Errors during stress test: {errors}"
        assert len(cache) <= 10  # Should respect max_size
