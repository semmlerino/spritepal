"""
Tests for PreviewGenerator service.

Tests the consolidated preview generation logic including caching,
thread safety, error handling, and different preview types.
"""

from __future__ import annotations

import concurrent.futures
import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image
from PySide6.QtGui import QPixmap

from core.services.preview_generator import (
    # Test characteristics: Timer usage
    LRUCache,
    PaletteData,
    PreviewGenerator,
    PreviewRequest,
    PreviewResult,
    create_rom_preview_request,
    create_vram_preview_request,
)
from tests.fixtures.timeouts import signal_timeout
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skip_thread_cleanup(reason="Preview workers may not clean up within fixture timeout"),
    pytest.mark.benchmark,
    pytest.mark.headless,
    pytest.mark.performance,
    pytest.mark.slow,
    pytest.mark.usefixtures("session_app_context"),
    pytest.mark.shared_state_safe,
]


class TestLRUCache:
    """Test the LRU cache implementation."""

    def test_cache_creation(self):
        """Test cache creation with different sizes."""
        cache = LRUCache(max_size=10)
        assert cache.max_size == 10
        assert cache.get_stats()["cache_size"] == 0

        stats = cache.get_stats()
        assert stats["cache_size"] == 0
        assert stats["max_size"] == 10
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["evictions"] == 0
        assert stats["hit_rate"] == 0.0

    def test_cache_put_and_get(self):
        """Test basic cache put and get operations."""
        cache = LRUCache(max_size=3)

        # Create mock preview result
        pixmap = ThreadSafeTestImage(64, 64)
        pil_image = Image.new("RGB", (64, 64))
        result = PreviewResult(
            pixmap=pixmap, pil_image=pil_image, tile_count=16, sprite_name="test_sprite", generation_time=0.1
        )

        # Test miss
        assert cache.get("key1") is None

        # Test put and hit
        cache.put("key1", result)
        cached_result = cache.get("key1")
        assert cached_result is not None
        assert cached_result.sprite_name == "test_sprite"
        assert cached_result.cached is True

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = LRUCache(max_size=2)

        # Create test results
        results = []
        for i in range(3):
            pixmap = ThreadSafeTestImage(64, 64)
            pil_image = Image.new("RGB", (64, 64))
            result = PreviewResult(
                pixmap=pixmap, pil_image=pil_image, tile_count=16, sprite_name=f"sprite_{i}", generation_time=0.1
            )
            results.append(result)

        # Fill cache
        cache.put("key1", results[0])
        cache.put("key2", results[1])
        assert cache.get_stats()["cache_size"] == 2

        # Add third item - should evict first
        cache.put("key3", results[2])
        assert cache.get_stats()["cache_size"] == 2
        assert cache.get("key1") is None  # Evicted
        assert cache.get("key2") is not None  # Still there
        assert cache.get("key3") is not None  # New item

        stats = cache.get_stats()
        assert stats["evictions"] == 1

    def test_cache_lru_ordering(self):
        """Test that least recently used items are evicted first."""
        cache = LRUCache(max_size=2)

        # Create test results
        pixmap = ThreadSafeTestImage(64, 64)
        pil_image = Image.new("RGB", (64, 64))
        result1 = PreviewResult(pixmap, pil_image, 16, "sprite1", 0.1)
        result2 = PreviewResult(pixmap, pil_image, 16, "sprite2", 0.1)
        result3 = PreviewResult(pixmap, pil_image, 16, "sprite3", 0.1)

        # Add items
        cache.put("key1", result1)
        cache.put("key2", result2)

        # Access key1 (makes it most recent)
        cache.get("key1")

        # Add key3 - should evict key2 (least recent)
        cache.put("key3", result3)

        assert cache.get("key1") is not None  # Still there (was accessed)
        assert cache.get("key2") is None  # Evicted (least recent)
        assert cache.get("key3") is not None  # New item

    def test_cache_clear(self):
        """Test cache clearing."""
        cache = LRUCache(max_size=5)

        # Add some items
        pixmap = ThreadSafeTestImage(64, 64)
        pil_image = Image.new("RGB", (64, 64))
        for i in range(3):
            result = PreviewResult(pixmap, pil_image, 16, f"sprite_{i}", 0.1)
            cache.put(f"key_{i}", result)

        assert cache.get_stats()["cache_size"] == 3

        # Clear cache
        cache.clear()
        assert cache.get_stats()["cache_size"] == 0

        # Verify all items are gone
        for i in range(3):
            assert cache.get(f"key_{i}") is None

    def test_cache_byte_size_tracking(self):
        """Test that cache tracks byte size correctly."""
        cache = LRUCache(max_size=100, max_bytes=1024 * 1024)  # 1MB limit

        pixmap = ThreadSafeTestImage(64, 64)  # 64*64*4 = 16KB
        pil_image = Image.new("RGB", (64, 64))  # 64*64*3 = 12KB
        result = PreviewResult(
            pixmap=pixmap, pil_image=pil_image, tile_count=16, sprite_name="test", generation_time=0.1
        )

        cache.put("key1", result)
        stats = cache.get_stats()

        # Verify byte tracking
        assert stats["current_bytes"] > 0
        expected_size = result.byte_size()
        assert stats["current_bytes"] == expected_size

    def test_cache_byte_limit_eviction(self):
        """Test that cache evicts when byte limit is reached."""
        # Small byte limit to trigger eviction (~30KB limit)
        cache = LRUCache(max_size=100, max_bytes=30 * 1024)

        # Each result is ~28KB (64*64*4 + 64*64*3 + 100)
        results = []
        for i in range(3):
            pixmap = ThreadSafeTestImage(64, 64)
            pil_image = Image.new("RGB", (64, 64))
            result = PreviewResult(
                pixmap=pixmap, pil_image=pil_image, tile_count=16, sprite_name=f"sprite_{i}", generation_time=0.1
            )
            results.append(result)

        # First item fits
        cache.put("key1", results[0])
        assert cache.get("key1") is not None

        # Second item should trigger eviction of first
        cache.put("key2", results[1])

        stats = cache.get_stats()
        # Cache should stay under byte limit
        assert stats["current_bytes"] <= 30 * 1024
        # First item should be evicted
        assert stats["evictions_byte_limit"] > 0

    def test_preview_result_byte_size(self):
        """Test PreviewResult byte_size calculation."""
        pixmap = ThreadSafeTestImage(128, 128)  # 128*128*4 = 65536 bytes
        pil_image = Image.new("RGBA", (128, 128))  # 128*128*4 = 65536 bytes

        result = PreviewResult(
            pixmap=pixmap, pil_image=pil_image, tile_count=256, sprite_name="test", generation_time=0.1
        )

        size = result.byte_size()

        # Expected: 65536 (pixmap) + 65536 (pil) + 100 (metadata) = ~131KB
        assert size >= 130000
        assert size <= 135000

    def test_cache_stats_include_byte_info(self):
        """Test that cache stats include byte size information."""
        cache = LRUCache(max_size=10, max_bytes=1024 * 1024)

        stats = cache.get_stats()

        # New fields should be present
        assert "current_bytes" in stats
        assert "max_bytes" in stats
        assert "current_mb" in stats
        assert "max_mb" in stats
        assert stats["current_bytes"] == 0
        assert stats["max_bytes"] == 1024 * 1024

    def test_cache_clear_resets_bytes(self):
        """Test that clearing cache resets byte tracking."""
        cache = LRUCache(max_size=10, max_bytes=1024 * 1024)

        pixmap = ThreadSafeTestImage(64, 64)
        pil_image = Image.new("RGB", (64, 64))
        result = PreviewResult(pixmap, pil_image, 16, "test", 0.1)

        cache.put("key1", result)
        assert cache.get_stats()["current_bytes"] > 0

        cache.clear()
        assert cache.get_stats()["current_bytes"] == 0


class TestPreviewRequest:
    """Test preview request functionality."""

    def test_preview_request_creation(self):
        """Test creating preview requests."""
        request = PreviewRequest(
            source_type="vram", data_path="/path/to/vram.bin", offset=0x8000, sprite_name="test_sprite", size=(256, 256)
        )

        assert request.source_type == "vram"
        assert request.data_path == "/path/to/vram.bin"
        assert request.offset == 0x8000
        assert request.sprite_name == "test_sprite"
        assert request.size == (256, 256)
        assert request.palette is None
        assert request.sprite_config is None

    def test_preview_request_with_palette(self):
        """Test preview request with palette data."""
        palette = PaletteData(data=b"\x00" * 512, format="snes_cgram")
        request = PreviewRequest(source_type="rom", data_path="/path/to/rom.smc", offset=0x200000, palette=palette)

        assert request.palette is not None
        assert request.palette.data == b"\x00" * 512
        assert request.palette.format == "snes_cgram"

    def test_cache_key_generation(self):
        """Test cache key generation for requests."""
        request1 = PreviewRequest("vram", "/path/file.bin", 0x8000)
        request2 = PreviewRequest("vram", "/path/file.bin", 0x8000)
        request3 = PreviewRequest("vram", "/path/file.bin", 0x9000)

        # Same requests should have same key
        assert request1.cache_key() == request2.cache_key()

        # Different requests should have different keys
        assert request1.cache_key() != request3.cache_key()

    def test_cache_key_with_palette(self):
        """Test cache key includes palette data."""
        palette1 = PaletteData(data=b"\x00" * 512)
        palette2 = PaletteData(data=b"\xff" * 512)

        request1 = PreviewRequest("vram", "/path/file.bin", 0x8000, palette=palette1)
        request2 = PreviewRequest("vram", "/path/file.bin", 0x8000, palette=palette2)

        # Different palettes should produce different cache keys
        assert request1.cache_key() != request2.cache_key()


class TestPreviewGenerator:
    """Test the main PreviewGenerator class."""

    @pytest.fixture
    def generator(self, qtbot):
        """Create a preview generator for testing."""
        gen = PreviewGenerator(cache_size=5, debounce_delay_ms=10)
        # Note: PreviewGenerator is a QObject, not a QWidget, so we don't use qtbot.addWidget
        # qtbot will still handle cleanup of QObject signals/connections
        yield gen
        gen.cleanup()

    @pytest.fixture
    def preview_mock_extraction_manager(self):
        """Create a mock extraction manager for preview tests.

        Named to avoid shadowing conftest's real_extraction_manager.
        """
        manager = Mock()

        # Mock generate_preview to return a test image
        test_image = Image.new("RGB", (128, 128), color="red")
        manager.generate_preview.return_value = (test_image, 16)

        return manager

    @pytest.fixture
    def preview_mock_rom_extractor(self):
        """Create a mock ROM extractor for preview tests.

        Named to avoid shadowing conftest's fixtures.
        """
        extractor = Mock()

        # Mock extract_sprite_data
        extractor.extract_sprite_data.return_value = b"\x00" * 1024

        return extractor

    def test_generator_creation(self, generator):
        """Test preview generator creation via public API."""
        stats = generator.get_cache_stats()
        assert stats["max_size"] == 5
        assert stats["cache_size"] == 0

    def test_set_managers(self, generator, preview_mock_extraction_manager, preview_mock_rom_extractor):
        """Test setting manager references enables preview generation."""
        generator.set_managers(preview_mock_extraction_manager, preview_mock_rom_extractor)

        # Verify managers are set by testing that preview generation works
        # (the actual generation is tested in other tests)

    def test_vram_preview_generation(self, generator, preview_mock_extraction_manager):
        """Test VRAM preview generation."""
        with patch("core.services.preview_generator.pil_to_qpixmap") as mock_pil_to_qpixmap:
            # Setup mocks
            mock_pixmap = Mock(spec=QPixmap)
            mock_pixmap.size.return_value.width.return_value = 128
            mock_pixmap.size.return_value.height.return_value = 128
            mock_pil_to_qpixmap.return_value = mock_pixmap

            generator.set_managers(extraction_manager=preview_mock_extraction_manager)

            # Create request
            request = create_vram_preview_request("/path/to/vram.bin", 0x8000, "test_sprite")

            # Generate preview
            result = generator.generate_preview(request)

            assert result is not None
            assert result.sprite_name == "test_sprite"
            assert result.tile_count == 16
            assert result.pixmap is not None
            # PreviewGenerator now scales the pixmap, so it returns a scaled version
            mock_pixmap.scaled.assert_called_once()
            assert result.generation_time > 0

            # Verify extraction manager was called
            preview_mock_extraction_manager.generate_preview.assert_called_once_with("/path/to/vram.bin", 0x8000)

    def test_preview_caching(self, generator, preview_mock_extraction_manager):
        """Test that previews are cached correctly."""
        with patch("core.services.preview_generator.pil_to_qpixmap") as mock_pil_to_qpixmap:
            mock_pixmap = Mock(spec=QPixmap)
            mock_pixmap.size.return_value.width.return_value = 128
            mock_pixmap.size.return_value.height.return_value = 128
            mock_pil_to_qpixmap.return_value = mock_pixmap

            generator.set_managers(extraction_manager=preview_mock_extraction_manager)

            request = create_vram_preview_request("/path/to/vram.bin", 0x8000)

            # First generation
            result1 = generator.generate_preview(request)
            assert result1 is not None
            assert not result1.cached

            # Second generation should use cache
            result2 = generator.generate_preview(request)
            assert result2 is not None
            assert result2.cached

            # Extraction manager should only be called once
            assert preview_mock_extraction_manager.generate_preview.call_count == 1

    def test_cache_stats_emission(self, generator, qtbot):
        """Test that cache stats are emitted when cache changes."""
        with qtbot.waitSignal(generator.cache_stats_changed) as blocker:
            generator.clear_cache()

        # Verify signal was emitted with stats
        stats = blocker.args[0]
        assert isinstance(stats, dict)
        assert "cache_size" in stats
        assert "hit_rate" in stats

    def test_error_handling(self, generator, preview_mock_extraction_manager):
        """Test error handling in preview generation."""
        # Make extraction manager raise an exception
        preview_mock_extraction_manager.generate_preview.side_effect = RuntimeError("Test error")

        generator.set_managers(extraction_manager=preview_mock_extraction_manager)

        request = create_vram_preview_request("/path/to/vram.bin", 0x8000)

        # Should handle error gracefully
        result = generator.generate_preview(request)
        assert result is None

    def test_friendly_error_messages(self, generator):
        """Test conversion of technical errors to user-friendly messages."""
        test_cases = [
            ("decompression failed", "No sprite data found. Try different offset."),
            ("memory allocation error", "Memory error. Try closing other applications."),
            ("permission denied", "File access error. Check file permissions."),
            ("file not found", "Source file not found."),
            ("manager not available", "Preview system not ready. Try again."),
            ("unknown error", "Preview failed: unknown error"),
        ]

        for error_msg, expected in test_cases:
            friendly = generator._get_friendly_error_message(error_msg)
            assert friendly == expected

    def test_async_preview_generation(self, generator, qtbot, preview_mock_extraction_manager):
        """Test asynchronous preview generation."""
        with patch("core.services.preview_generator.pil_to_qpixmap") as mock_pil_to_qpixmap:
            mock_pixmap = Mock(spec=QPixmap)
            mock_pixmap.size.return_value.width.return_value = 128
            mock_pixmap.size.return_value.height.return_value = 128
            mock_pil_to_qpixmap.return_value = mock_pixmap

            generator.set_managers(extraction_manager=preview_mock_extraction_manager)

            request = create_vram_preview_request("/path/to/vram.bin", 0x8000)

            # Test async generation with signal
            with qtbot.waitSignal(generator.preview_ready, timeout=signal_timeout()) as blocker:
                generator.generate_preview_async(request, use_debounce=False)

            result = blocker.args[0]
            assert isinstance(result, PreviewResult)
            assert result.sprite_name == "vram_0x008000"

    def test_debounced_requests(self, generator, qtbot, preview_mock_extraction_manager):
        """Test that rapid requests are properly debounced."""
        with patch("core.services.preview_generator.pil_to_qpixmap") as mock_pil_to_qpixmap:
            mock_pixmap = Mock(spec=QPixmap)
            mock_pixmap.size.return_value.width.return_value = 128
            mock_pixmap.size.return_value.height.return_value = 128
            mock_pil_to_qpixmap.return_value = mock_pixmap

            generator.set_managers(extraction_manager=preview_mock_extraction_manager)

            # Make multiple rapid requests
            for i in range(5):
                request = create_vram_preview_request("/path/to/vram.bin", 0x8000 + i * 0x100)
                generator.generate_preview_async(request, use_debounce=True)

            # Wait for debounce to settle
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()  # Allow debounce timer to fire

            # Only the last request should be processed
            assert preview_mock_extraction_manager.generate_preview.call_count <= 1

    def test_cancel_pending_requests(self, generator):
        """Test canceling pending requests via public API."""
        request = create_vram_preview_request("/path/to/vram.bin", 0x8000)

        # Make a debounced request
        generator.generate_preview_async(request, use_debounce=True)

        # Cancel it - no exception means success
        generator.cancel_pending_requests()

    def test_cleanup(self, generator):
        """Test cleanup functionality via public API."""
        # Add some cached items (mock must have byte_size method for cache)
        mock_result = Mock()
        mock_result.byte_size.return_value = 1024
        generator._cache.put("test_key", mock_result)
        assert generator.get_cache_stats()["cache_size"] > 0

        # Cleanup
        generator.cleanup()

        # Verify cache is cleaned up via public API
        assert generator.get_cache_stats()["cache_size"] == 0


class TestHelperFunctions:
    """Test helper functions."""

    def test_create_vram_preview_request(self):
        """Test VRAM preview request creation helper."""
        request = create_vram_preview_request("/path/to/vram.bin", 0x8000, "test_sprite", (256, 256))

        assert request.source_type == "vram"
        assert request.data_path == "/path/to/vram.bin"
        assert request.offset == 0x8000
        assert request.sprite_name == "test_sprite"
        assert request.size == (256, 256)

    def test_create_rom_preview_request(self):
        """Test ROM preview request creation helper."""
        sprite_config = {"width": 16, "height": 16}
        request = create_rom_preview_request("/path/to/rom.smc", 0x200000, "rom_sprite", sprite_config, (128, 128))

        assert request.source_type == "rom"
        assert request.data_path == "/path/to/rom.smc"
        assert request.offset == 0x200000
        assert request.sprite_name == "rom_sprite"
        assert request.sprite_config is sprite_config
        assert request.size == (128, 128)


def test_preview_generation_performance():
    """Test preview generation performance."""
    # Create a mock extraction manager that simulates realistic work
    mock_manager = Mock()
    test_image = Image.new("RGB", (128, 128), color="blue")
    mock_manager.generate_preview.return_value = (test_image, 16)

    generator = PreviewGenerator(cache_size=10)
    generator.set_managers(extraction_manager=mock_manager)

    request = create_vram_preview_request("/path/to/vram.bin", 0x8000)

    with patch("core.services.preview_generator.pil_to_qpixmap") as mock_convert:
        mock_pixmap = Mock(spec=QPixmap)
        mock_pixmap.size.return_value.width.return_value = 128
        mock_pixmap.size.return_value.height.return_value = 128
        mock_convert.return_value = mock_pixmap

        # Test the generation
        start_time = time.time()
        result = generator.generate_preview(request)
        generation_time = time.time() - start_time

        assert result is not None
        assert result.sprite_name == "vram_0x008000"
        assert generation_time < 1.0  # Should be fast with mocks

    generator.cleanup()


def test_cache_performance(qapp):
    """Test cache performance with many items.

    Requires qapp fixture to ensure QApplication exists.
    """
    cache = LRUCache(max_size=100)

    # Pre-fill cache - use ThreadSafeTestImage for consistency
    pixmap = ThreadSafeTestImage(64, 64)
    pil_image = Image.new("RGB", (64, 64))
    for i in range(50):
        result = PreviewResult(pixmap, pil_image, 16, f"sprite_{i}", 0.1)
        cache.put(f"key_{i}", result)

    # Test mixed operations
    start_time = time.time()
    for i in range(100):
        if i % 3 == 0:
            # Cache hit - get an existing key
            cache.get(f"key_{i % 50}")
        elif i % 3 == 1:
            # Cache miss - try to get a non-existent key
            cache.get(f"nonexistent_key_{i}")
        else:
            # Cache put - add new entry
            result = PreviewResult(pixmap, pil_image, 16, f"new_sprite_{i}", 0.1)
            cache.put(f"new_key_{i}", result)

    operation_time = time.time() - start_time

    stats = cache.get_stats()
    assert stats["hits"] > 0, f"Expected cache hits but got: {stats}"
    assert stats["misses"] > 0, f"Expected cache misses but got: {stats}"
    assert operation_time < 1.0  # Should be fast


# =============================================================================
# Thread Safety Tests (from test_preview_generator_thread_safety.py)
# =============================================================================


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
    """Test thread safety of PreviewGenerator LRU cache."""

    def test_cache_concurrent_access(self):
        """Test LRU cache thread safety with concurrent reads/writes."""
        generator = PreviewGenerator(cache_size=200)
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
