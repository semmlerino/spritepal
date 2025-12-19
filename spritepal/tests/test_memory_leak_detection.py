
"""
Comprehensive memory leak detection tests.

These tests verify:
- No memory leaks in ROM file handling
- Proper cleanup of cache memory
- Worker thread memory management
- QImage/QPixmap lifecycle
- Signal/slot connection cleanup
- Large file handling without leaks
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]

import gc
import os
import weakref
from typing import Any
from unittest.mock import Mock, patch

import psutil
import pytest
from PySide6.QtCore import QObject
from PySide6.QtGui import QImage, QPixmap

from ui.workers.batch_thumbnail_worker import (
    BatchThumbnailWorker,
    LRUCache,
    ThumbnailWorkerController,
)


class MemoryMonitor:
    """Monitor memory usage for leak detection."""

    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.initial_memory = None
        self.peak_memory = 0
        self.measurements = []

    def start(self):
        """Start monitoring memory."""
        gc.collect()
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.peak_memory = self.initial_memory
        self.measurements = [self.initial_memory]

    def measure(self):
        """Take a memory measurement."""
        gc.collect()
        current = self.process.memory_info().rss / 1024 / 1024  # MB
        self.measurements.append(current)
        self.peak_memory = max(self.peak_memory, current)
        return current

    def get_increase(self) -> float:
        """Get memory increase from start."""
        if not self.initial_memory:
            return 0
        current = self.measure()
        return current - self.initial_memory

    def assert_no_leak(self, max_increase_mb: float = 10.0):
        """Assert no significant memory leak."""
        increase = self.get_increase()
        assert increase < max_increase_mb, (
            f"Memory leak detected: {increase:.2f}MB increase "
            f"(initial: {self.initial_memory:.2f}MB, current: {self.measurements[-1]:.2f}MB)"
        )

class WeakrefTracker:
    """Track object lifecycle using weakrefs."""

    def __init__(self):
        self.refs = []

    def track(self, obj: Any) -> weakref.ref:
        """Track an object with a weakref."""
        ref = weakref.ref(obj)
        self.refs.append(ref)
        return ref

    def assert_all_deleted(self):
        """Assert all tracked objects have been deleted."""
        gc.collect()
        alive = [ref for ref in self.refs if ref() is not None]
        assert not alive, f"{len(alive)} objects still alive"

    def get_alive_count(self) -> int:
        """Get count of still-alive objects."""
        gc.collect()
        return sum(1 for ref in self.refs if ref() is not None)

@pytest.fixture
def memory_monitor():
    """Create a memory monitor."""
    return MemoryMonitor()

@pytest.fixture
def weakref_tracker():
    """Create a weakref tracker."""
    return WeakrefTracker()

@pytest.fixture
def large_rom_file(tmp_path) -> str:
    """Create a large test ROM file."""
    rom_path = tmp_path / "large_test.sfc"
    # Create 16MB ROM
    rom_data = bytearray(16 * 1024 * 1024)

    # Add some patterns
    for i in range(0, len(rom_data), 1024):
        rom_data[i:i+32] = b'\x00\x01\x02\x03' * 8

    rom_path.write_bytes(rom_data)
    return str(rom_path)


@pytest.fixture
def mock_rom_extractor() -> Mock:
    """Create a mock ROMExtractor to avoid DI container dependency."""
    extractor = Mock()
    extractor.extract_sprite.return_value = None
    extractor.decompress.return_value = b'\x00' * 1024
    return extractor

class TestLRUCacheMemoryManagement:
    """Test memory management in LRU cache."""

    def test_cache_eviction_frees_memory(self, memory_monitor, weakref_tracker):
        """Test that evicted items are properly freed."""
        cache = LRUCache(maxsize=10)
        memory_monitor.start()

        # Create tracked QImages
        images = []
        for i in range(20):
            # Create a substantial image to see memory impact
            img = QImage(256, 256, QImage.Format.Format_RGBA8888)
            img.fill(i)  # Different fill for each
            images.append(img)
            weakref_tracker.track(img)
            cache.put((i, i), img)

        # First 10 images should be evicted
        cache_size = cache.size()
        assert cache_size == 10

        # Clear references to evicted images
        images[:10] = [None] * 10
        gc.collect()

        # Memory should not grow unbounded
        memory_monitor.assert_no_leak(max_increase_mb=50)  # Allow some overhead

    def test_cache_stats_dont_leak(self, memory_monitor):
        """Test getting cache stats doesn't leak memory."""
        cache = LRUCache(maxsize=50)
        memory_monitor.start()

        # Populate cache
        for i in range(50):
            img = QImage(64, 64, QImage.Format.Format_RGBA8888)
            cache.put((i, i), img)

        # Repeatedly get stats
        for _ in range(10000):
            stats = cache.get_stats()
            assert 'hit_rate' in stats

        # Should not leak memory
        memory_monitor.assert_no_leak(max_increase_mb=5)

class TestBatchThumbnailWorkerMemoryLeaks:
    """Test memory leak prevention in BatchThumbnailWorker."""

    def test_rom_file_cleanup_on_worker_deletion(self, large_rom_file, memory_monitor, mock_rom_extractor):
        """Test ROM file handles are cleaned up when worker is deleted."""
        memory_monitor.start()

        # Create and destroy multiple workers
        for _ in range(3):
            worker = BatchThumbnailWorker(large_rom_file, rom_extractor=mock_rom_extractor)
            # Load ROM data
            worker._load_rom_data()
            assert worker._rom_mmap is not None

            # Clean up
            worker._clear_rom_data()
            del worker
            gc.collect()

        # Memory should not accumulate
        memory_monitor.assert_no_leak(max_increase_mb=10)

    def test_context_manager_prevents_file_handle_leak(self, large_rom_file, memory_monitor, mock_rom_extractor):
        """Test context manager prevents file handle leaks."""
        memory_monitor.start()

        worker = BatchThumbnailWorker(large_rom_file, rom_extractor=mock_rom_extractor)

        # Use context manager multiple times
        for _ in range(100):
            with worker._rom_context() as rom_data:
                # Read some data
                data = rom_data[0:1024]
                assert len(data) == 1024

        # Check file handles aren't leaked
        open_files = psutil.Process().open_files()
        rom_handles = [f for f in open_files if large_rom_file in f.path]
        assert len(rom_handles) == 0, f"File handles leaked: {rom_handles}"

        # Memory should be stable
        memory_monitor.assert_no_leak(max_increase_mb=5)

    def test_thumbnail_generation_memory_cleanup(self, large_rom_file, memory_monitor, mock_rom_extractor):
        """Test memory is cleaned up after thumbnail generation."""
        memory_monitor.start()

        with patch('ui.workers.batch_thumbnail_worker.TileRenderer') as mock_renderer:
            # Mock renderer to return images
            def create_image(*args, **kwargs):
                img = Mock(spec=['size', 'mode', 'convert', 'tobytes'])
                img.size = (64, 64)
                img.mode = 'RGBA'
                img.convert.return_value = img
                img.tobytes.return_value = b'\x00' * (64 * 64 * 4)
                return img

            mock_renderer.return_value.render_tiles = create_image

            worker = BatchThumbnailWorker(large_rom_file, rom_extractor=mock_rom_extractor)
            worker._load_rom_data()

            # Generate many thumbnails
            for i in range(100):
                request = Mock(offset=i * 0x1000, size=128)
                thumbnail = worker._generate_thumbnail(request)
                # Don't keep references
                del thumbnail

            # Clean up
            worker._clear_rom_data()
            worker._clear_cache_memory()
            gc.collect()

        # Memory should not grow significantly
        memory_monitor.assert_no_leak(max_increase_mb=20)

@pytest.mark.usefixtures("qapp")  # QPixmap requires QApplication
@pytest.mark.parallel_unsafe  # Heavy Qt operations crash in parallel
class TestQImageQPixmapMemoryManagement:
    """Test memory management of Qt image objects."""

    def test_qimage_to_qpixmap_conversion_cleanup(self, memory_monitor):
        """Test QImage to QPixmap conversion doesn't leak."""
        memory_monitor.start()

        for _ in range(100):
            # Create QImage
            qimage = QImage(512, 512, QImage.Format.Format_RGBA8888)
            qimage.fill(0)

            # Convert to QPixmap
            qpixmap = QPixmap.fromImage(qimage)

            # Use it
            assert not qpixmap.isNull()

            # Delete explicitly
            del qpixmap
            del qimage

        gc.collect()

        # Memory should be stable
        memory_monitor.assert_no_leak(max_increase_mb=10)

    def test_qimage_copy_cleanup(self, memory_monitor):
        """Test QImage.copy() doesn't leak memory."""
        memory_monitor.start()

        original = QImage(256, 256, QImage.Format.Format_RGBA8888)
        original.fill(0)

        for _ in range(1000):
            copy = original.copy()
            assert not copy.isNull()
            del copy

        gc.collect()

        # Should not leak
        memory_monitor.assert_no_leak(max_increase_mb=5)

class TestLargeDataProcessingMemoryLeaks:
    """Test memory leaks when processing large amounts of data."""

    def test_processing_many_sprites_no_leak(self, large_rom_file, memory_monitor, mock_rom_extractor):
        """Test processing many sprites doesn't leak memory."""
        memory_monitor.start()

        with patch('ui.workers.batch_thumbnail_worker.TileRenderer'):
            worker = BatchThumbnailWorker(large_rom_file, rom_extractor=mock_rom_extractor)

            # Process many sprite offsets
            for batch in range(10):
                # Queue batch
                for i in range(100):
                    offset = batch * 100000 + i * 1000
                    worker.queue_thumbnail(offset, 128, i)

                # Clear queue to simulate processing
                worker.clear_queue()

                # Clear cache periodically
                if batch % 3 == 0:
                    worker.clear_cache()

            # Final cleanup
            worker.cleanup()
            del worker
            gc.collect()

        # Memory should not grow unbounded
        memory_monitor.assert_no_leak(max_increase_mb=25)

    def test_rom_mmap_fallback_memory_management(self, large_rom_file, memory_monitor, mock_rom_extractor):
        """Test BytesMMAPWrapper fallback doesn't leak memory."""
        memory_monitor.start()

        # Force fallback by mocking mmap to fail
        with patch('mmap.mmap', side_effect=Exception("mmap failed")):
            worker = BatchThumbnailWorker(large_rom_file, rom_extractor=mock_rom_extractor)

            # This should use BytesMMAPWrapper fallback
            worker._load_rom_data()

            # ROM should be loaded via fallback
            assert worker._rom_mmap is not None
            assert hasattr(worker._rom_mmap, '_data')  # BytesMMAPWrapper

            # Use the ROM data
            for i in range(100):
                chunk = worker._read_rom_chunk(i * 1000, 1024)
                assert chunk is not None

            # Cleanup
            worker._clear_rom_data()
            del worker
            gc.collect()

        # Memory should be released
        memory_monitor.assert_no_leak(max_increase_mb=30)  # Allow for 16MB ROM

@pytest.mark.skip_thread_cleanup(
    reason="ThreadPoolExecutor Dummy threads require OS-level cleanup time after shutdown"
)
class TestMemoryLeakIntegration:
    """Integration tests for memory leak detection."""

    def test_full_workflow_no_memory_leak(self, large_rom_file, memory_monitor, qtbot, mock_rom_extractor):
        """Test complete workflow doesn't leak memory."""
        memory_monitor.start()

        # Simulate full workflow multiple times
        for iteration in range(3):
            controller = ThumbnailWorkerController()

            # Start worker with mock extractor to avoid DI dependency
            controller.start_worker(large_rom_file, rom_extractor=mock_rom_extractor)

            # Queue many thumbnails
            offsets = [i * 0x1000 for i in range(50)]
            controller.queue_batch(offsets, 128)

            # Allow worker to start processing
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()

            # Stop and cleanup
            controller.stop_worker()
            controller.cleanup()

            del controller
            gc.collect()

        # Memory should not accumulate across iterations
        memory_monitor.assert_no_leak(max_increase_mb=20)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
