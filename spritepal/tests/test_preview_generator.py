"""
Tests for PreviewGenerator service.

Tests the consolidated preview generation logic including caching,
thread safety, error handling, and different preview types.
"""
from __future__ import annotations

import time
from unittest.mock import Mock, patch

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
    get_preview_generator,
)
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Preview workers may not clean up within fixture timeout"),
    pytest.mark.benchmark,
    pytest.mark.headless,
    pytest.mark.performance,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.serial,
    pytest.mark.widget,
    pytest.mark.worker_threads,
    pytest.mark.cache,
    pytest.mark.ci_safe,
    pytest.mark.signals_slots,
    pytest.mark.slow,
    pytest.mark.usefixtures("session_managers"),  # DI system initialization
]
class TestLRUCache:
    """Test the LRU cache implementation."""

    def test_cache_creation(self):
        """Test cache creation with different sizes."""
        cache = LRUCache(max_size=10)
        assert cache.max_size == 10
        assert len(cache._cache) == 0

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
            pixmap=pixmap,
            pil_image=pil_image,
            tile_count=16,
            sprite_name="test_sprite",
            generation_time=0.1
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
                pixmap=pixmap,
                pil_image=pil_image,
                tile_count=16,
                sprite_name=f"sprite_{i}",
                generation_time=0.1
            )
            results.append(result)

        # Fill cache
        cache.put("key1", results[0])
        cache.put("key2", results[1])
        assert len(cache._cache) == 2

        # Add third item - should evict first
        cache.put("key3", results[2])
        assert len(cache._cache) == 2
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
        assert cache.get("key2") is None      # Evicted (least recent)
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

        assert len(cache._cache) == 3

        # Clear cache
        cache.clear()
        assert len(cache._cache) == 0

        # Verify all items are gone
        for i in range(3):
            assert cache.get(f"key_{i}") is None

class TestPreviewRequest:
    """Test preview request functionality."""

    def test_preview_request_creation(self):
        """Test creating preview requests."""
        request = PreviewRequest(
            source_type="vram",
            data_path="/path/to/vram.bin",
            offset=0x8000,
            sprite_name="test_sprite",
            size=(256, 256)
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
        request = PreviewRequest(
            source_type="rom",
            data_path="/path/to/rom.smc",
            offset=0x200000,
            palette=palette
        )

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
        palette2 = PaletteData(data=b"\xFF" * 512)

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
        """Test preview generator creation."""
        assert generator._cache.max_size == 5
        assert generator._debounce_delay_ms == 10
        assert generator._debounce_timer is not None
        assert generator._pending_request is None

    def test_set_managers(self, generator, preview_mock_extraction_manager, preview_mock_rom_extractor):
        """Test setting manager references."""
        generator.set_managers(preview_mock_extraction_manager, preview_mock_rom_extractor)

        # Verify weak references are set
        assert generator._extraction_manager_ref is not None
        assert generator._rom_extractor_ref is not None

        # Verify managers can be retrieved
        assert generator._extraction_manager_ref() is preview_mock_extraction_manager
        assert generator._rom_extractor_ref() is preview_mock_rom_extractor

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
            assert result.pixmap is mock_pixmap
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
            with qtbot.waitSignal(generator.preview_ready, timeout=1000) as blocker:
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
        """Test canceling pending requests."""
        request = create_vram_preview_request("/path/to/vram.bin", 0x8000)

        # Make a debounced request
        generator.generate_preview_async(request, use_debounce=True)
        assert generator._pending_request is not None

        # Cancel it
        generator.cancel_pending_requests()
        assert generator._pending_request is None
        assert not generator._debounce_timer.isActive()

    def test_cleanup(self, generator):
        """Test cleanup functionality."""
        # Add some cached items
        generator._cache.put("test_key", Mock())
        assert len(generator._cache._cache) > 0

        # Set a pending request
        generator._pending_request = Mock()

        # Cleanup
        generator.cleanup()

        # Verify everything is cleaned up
        assert len(generator._cache._cache) == 0
        assert generator._pending_request is None
        assert generator._extraction_manager_ref is None
        assert generator._rom_extractor_ref is None

class TestHelperFunctions:
    """Test helper functions."""

    def test_create_vram_preview_request(self):
        """Test VRAM preview request creation helper."""
        request = create_vram_preview_request(
            "/path/to/vram.bin",
            0x8000,
            "test_sprite",
            (256, 256)
        )

        assert request.source_type == "vram"
        assert request.data_path == "/path/to/vram.bin"
        assert request.offset == 0x8000
        assert request.sprite_name == "test_sprite"
        assert request.size == (256, 256)

    def test_create_rom_preview_request(self):
        """Test ROM preview request creation helper."""
        sprite_config = {"width": 16, "height": 16}
        request = create_rom_preview_request(
            "/path/to/rom.smc",
            0x200000,
            "rom_sprite",
            sprite_config,
            (128, 128)
        )

        assert request.source_type == "rom"
        assert request.data_path == "/path/to/rom.smc"
        assert request.offset == 0x200000
        assert request.sprite_name == "rom_sprite"
        assert request.sprite_config is sprite_config
        assert request.size == (128, 128)

    def test_global_preview_generator(self):
        """Test global preview generator instance."""
        gen1 = get_preview_generator()
        gen2 = get_preview_generator()

        # Should return the same instance
        assert gen1 is gen2
        assert isinstance(gen1, PreviewGenerator)

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
