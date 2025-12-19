"""
Test thread safety of PreviewGenerator singleton implementation.

This test module verifies:
1. Thread-safe singleton initialization
2. No race conditions during concurrent access
3. Proper cleanup handling
4. Cache thread safety
"""
from __future__ import annotations

import concurrent.futures
import os

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

# Serial execution required: Thread safety concerns
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Preview workers may not clean up within fixture timeout"),
    pytest.mark.headless,
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
]

from core.services.preview_generator import (
    PreviewGenerator,
    PreviewRequest,
    PreviewResult,
    cleanup_preview_generator,
    get_preview_generator,
)


def _make_mock_preview_result(tile_count: int, sprite_name: str) -> PreviewResult:
    """Create a PreviewResult with properly configured mocks.

    The byte_size() method accesses pixmap.isNull(), pixmap.width(), pixmap.height(),
    pil_image.mode, pil_image.width, pil_image.height. Bare MagicMock() returns
    MagicMock for these, which can't be compared with integers.
    """
    mock_pixmap = MagicMock()
    mock_pixmap.isNull.return_value = True  # Avoid pixmap size calculation

    mock_pil = MagicMock()
    mock_pil.mode = "RGBA"
    mock_pil.width = 8
    mock_pil.height = 8

    return PreviewResult(
        pixmap=mock_pixmap,
        pil_image=mock_pil,
        tile_count=tile_count,
        sprite_name=sprite_name,
        generation_time=0.1,
    )


class TestPreviewGeneratorThreadSafety:
    """Test thread safety of PreviewGenerator singleton."""

    def test_singleton_concurrent_initialization(self):
        """Test that concurrent initialization creates only one instance."""
        # Clean up any existing instance
        cleanup_preview_generator()

        instances = []
        init_count = 0
        lock = threading.Lock()

        # Patch PreviewGenerator.__init__ to count initializations
        original_init = PreviewGenerator.__init__

        def counted_init(self, *args, **kwargs):
            nonlocal init_count
            with lock:
                init_count += 1
            original_init(self, *args, **kwargs)

        with patch.object(PreviewGenerator, "__init__", counted_init):
            # Try to get instance from multiple threads simultaneously
            def get_instance():
                instance = get_preview_generator()
                instances.append(instance)
                return instance

            # Use ThreadPoolExecutor for concurrent access
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(get_instance) for _ in range(100)]
                concurrent.futures.wait(futures)

            # Verify only one instance was created
            assert init_count == 1, f"Expected 1 initialization, got {init_count}"

            # Verify all threads got the same instance
            first_instance = instances[0]
            for instance in instances:
                assert instance is first_instance, "Multiple instances created!"

    def test_singleton_fast_path_performance(self):
        """Test that initialized singleton uses fast path without locking."""
        # Ensure instance exists
        instance = get_preview_generator()

        # Time multiple accesses
        start_time = time.time()
        for _ in range(10000):
            retrieved = get_preview_generator()
            assert retrieved is instance
        elapsed = time.time() - start_time

        # Should be very fast (no lock contention)
        assert elapsed < 0.1, f"Fast path too slow: {elapsed:.4f}s for 10000 accesses"

    def test_cache_concurrent_access(self):
        """Test LRU cache thread safety with concurrent reads/writes."""
        generator = get_preview_generator()
        cache = generator._cache

        # Clear cache
        cache.clear()

        errors = []

        def cache_writer(thread_id: int):
            """Write to cache from thread."""
            try:
                for i in range(100):
                    key = f"thread_{thread_id}_item_{i}"
                    result = _make_mock_preview_result(
                        tile_count=i,
                        sprite_name=f"sprite_{thread_id}_{i}",
                    )
                    cache.put(key, result)
                    # Small delay to increase contention
                    time.sleep(0.0001)  # sleep-ok: thread interleaving
            except Exception as e:
                errors.append(e)

        def cache_reader(thread_id: int):
            """Read from cache from thread."""
            try:
                for i in range(100):
                    # Try to read various keys
                    for tid in range(5):
                        key = f"thread_{tid}_item_{i}"
                        result = cache.get(key)
                        # Verify result if found
                        if result and not result.cached:
                            errors.append(ValueError("Result not marked as cached"))
            except Exception as e:
                errors.append(e)

        # Run concurrent readers and writers
        threads = []

        # Start writers
        for i in range(5):
            thread = threading.Thread(target=cache_writer, args=(i,))
            threads.append(thread)
            thread.start()

        # Start readers
        for i in range(5):
            thread = threading.Thread(target=cache_reader, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Check for errors
        assert not errors, f"Thread safety errors: {errors}"

        # Verify cache statistics are consistent
        stats = cache.get_stats()
        assert stats["hits"] >= 0
        assert stats["misses"] >= 0
        assert stats["evictions"] >= 0
        assert stats["cache_size"] <= cache.max_size


@pytest.fixture(autouse=True)
def cleanup_singleton():
    """Ensure singleton is cleaned up after each test."""
    yield
    cleanup_preview_generator()
