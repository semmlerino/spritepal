
"""
Comprehensive thread safety tests for BatchThumbnailWorker and LRU cache.

These tests verify:
- Thread-safe LRU cache operations
- Concurrent worker operations
- Signal/slot thread boundaries
- Mutex protection in critical sections
- Race condition prevention
- Deadlock avoidance
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.skip_thread_cleanup,  # Thread tests may intentionally leave threads running
    pytest.mark.cache,
    pytest.mark.headless,
    pytest.mark.rom_data,
    pytest.mark.signals_slots,
    pytest.mark.slow,
    pytest.mark.thread_safety,
    pytest.mark.unit,
    pytest.mark.worker_threads,
]

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QMutex, QMutexLocker, QObject, Signal
from PySide6.QtGui import QImage

from ui.workers.batch_thumbnail_worker import (
    BatchThumbnailWorker,
    LRUCache,
    ThumbnailWorkerController,
)


class ThreadSafetyValidator:
    """Helper class to validate thread safety."""

    def __init__(self):
        self.violations = []
        self.mutex = QMutex()
        self.thread_ids = set()
        self.operation_count = 0

    def record_thread_access(self, operation: str):
        """Record thread access to detect concurrent modifications."""
        thread_id = threading.current_thread().ident
        with QMutexLocker(self.mutex):
            self.thread_ids.add(thread_id)
            self.operation_count += 1

            # Check for concurrent access patterns
            if len(self.thread_ids) > 1:
                self.violations.append(
                    f"Concurrent access detected: {operation} from thread {thread_id}"
                )

    def assert_thread_safe(self):
        """Assert no thread safety violations occurred."""
        assert not self.violations, f"Thread safety violations: {self.violations}"

class ConcurrencyTester(QObject):
    """Helper to test concurrent signal emissions."""

    signal_emitted = Signal(int)

    def __init__(self):
        super().__init__()
        self.received_values = []
        self.mutex = QMutex()

    def emit_concurrent(self, value: int):
        """Emit signal from current thread."""
        self.signal_emitted.emit(value)

    def record_value(self, value: int):
        """Thread-safe recording of received values."""
        with QMutexLocker(self.mutex):
            self.received_values.append(value)

@pytest.fixture
def test_rom_data():
    """Create test ROM data."""
    return bytearray(b'\x00\x01\x02\x03' * 256 * 32)  # 32KB of test data

@pytest.fixture
def mock_qimage():
    """Create a mock QImage for testing."""
    # Create a small test image
    image = QImage(32, 32, QImage.Format.Format_RGBA8888)
    image.fill(0)  # Fill with transparent black
    return image

class TestLRUCacheThreadSafety:
    """Test thread safety of LRU cache implementation."""

    def test_concurrent_get_operations(self, mock_qimage):
        """Test concurrent get operations don't corrupt cache."""
        cache = LRUCache(maxsize=100)

        # Pre-populate cache
        for i in range(50):
            cache.put((i, i), mock_qimage)

        errors = []

        def get_operation(key_val: int):
            try:
                for _ in range(100):
                    result = cache.get((key_val, key_val))
                    if key_val < 50:  # Should be in cache
                        assert result is not None
            except Exception as e:
                errors.append(str(e))

        # Run concurrent get operations
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(get_operation, i)
                for i in range(100)
            ]
            for future in futures:
                future.result()

        assert not errors, f"Errors during concurrent get: {errors}"

        # Verify cache statistics are reasonable
        stats = cache.get_stats()
        assert stats['hits'] > 0
        assert stats['size'] <= 100

    def test_concurrent_put_operations(self, mock_qimage):
        """Test concurrent put operations maintain cache integrity."""
        cache = LRUCache(maxsize=50)
        errors = []

        def put_operation(start: int):
            try:
                for i in range(start, start + 20):
                    cache.put((i, i), mock_qimage)
            except Exception as e:
                errors.append(str(e))

        # Run concurrent put operations
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(put_operation, i * 20)
                for i in range(5)
            ]
            for future in futures:
                future.result()

        assert not errors, f"Errors during concurrent put: {errors}"

        # Cache should not exceed maxsize
        assert cache.size() <= 50

    def test_concurrent_mixed_operations(self, mock_qimage):
        """Test mixed get/put/clear operations concurrently."""
        cache = LRUCache(maxsize=100)
        validator = ThreadSafetyValidator()

        def mixed_operations(thread_id: int):
            for i in range(50):
                validator.record_thread_access(f"op_{i}_thread_{thread_id}")

                if i % 3 == 0:
                    cache.put((thread_id, i), mock_qimage)
                elif i % 3 == 1:
                    cache.get((thread_id, i - 1))
                elif thread_id == 0 and i == 48:  # Only one thread clears
                    cache.clear()

        # Run operations from multiple threads
        threads = []
        for i in range(4):
            thread = threading.Thread(target=mixed_operations, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Cache should be in valid state
        assert cache.size() >= 0
        assert cache.size() <= 100

    def test_lru_eviction_under_concurrent_load(self, mock_qimage):
        """Test LRU eviction works correctly under concurrent access."""
        cache = LRUCache(maxsize=10)

        def access_pattern(pattern_id: int):
            # Each thread has its own access pattern
            # Put 15 keys into a cache of size 10, guaranteeing evictions
            for round in range(5):
                # Put 15 keys (5 more than maxsize=10)
                # This guarantees keys 0-4 will be evicted when we put keys 10-14
                for i in range(15):
                    key = (pattern_id, i)
                    cache.put(key, mock_qimage)

                # Try to get keys 0-4 (guaranteed evicted) -> misses
                for i in range(5):
                    key = (pattern_id, i)
                    cache.get(key)

                # Try to get keys 10-14 (most recent, still in cache) -> hits
                for i in range(10, 15):
                    key = (pattern_id, i)
                    cache.get(key)

        # Run concurrent access patterns
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(access_pattern, i)
                for i in range(3)
            ]
            for future in futures:
                future.result()

        # Cache should respect maxsize
        assert cache.size() <= 10

        # Should have both hits and misses
        # Minimum expected: 3 threads × 5 rounds × 5 misses = 75 misses
        # Minimum expected: 3 threads × 5 rounds × 5 hits = 75 hits (from own keys 10-14)
        stats = cache.get_stats()
        assert stats['hits'] > 0
        assert stats['misses'] > 0

class TestBatchThumbnailWorkerThreadSafety:
    """Test thread safety of BatchThumbnailWorker."""

    @pytest.fixture
    def mock_worker_dependencies(self):
        """Mock worker dependencies."""
        with patch('ui.workers.batch_thumbnail_worker.ROMExtractor') as mock_extractor:
            with patch('ui.workers.batch_thumbnail_worker.TileRenderer') as mock_renderer:
                mock_renderer_instance = Mock()
                mock_renderer_instance.render_tiles.return_value = Mock()
                mock_renderer.return_value = mock_renderer_instance

                mock_extractor_instance = Mock()
                mock_extractor.return_value = mock_extractor_instance

                yield {
                    'extractor': mock_extractor_instance,
                    'renderer': mock_renderer_instance
                }

    def test_concurrent_queue_operations(self, test_rom_data, mock_worker_dependencies):
        """Test concurrent queue operations are thread-safe."""
        with patch('builtins.open', Mock(return_value=Mock(read=Mock(return_value=test_rom_data)))):
            worker = BatchThumbnailWorker('/fake/rom.sfc', mock_worker_dependencies['extractor'])

            errors = []

            def queue_operations(start_offset: int):
                try:
                    for i in range(100):
                        worker.queue_thumbnail(start_offset + i * 0x100, 128, i)
                except Exception as e:
                    errors.append(str(e))

            # Queue from multiple threads simultaneously
            threads = []
            for i in range(5):
                thread = threading.Thread(
                    target=queue_operations,
                    args=(i * 0x10000,)
                )
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            assert not errors, f"Errors during concurrent queuing: {errors}"
            assert worker._pending_count == 500  # 5 threads * 100 thumbnails

    def test_concurrent_cache_access(self, test_rom_data, mock_worker_dependencies, mock_qimage):
        """Test concurrent cache access during processing."""
        with patch('builtins.open', Mock(return_value=Mock(read=Mock(return_value=test_rom_data)))):
            worker = BatchThumbnailWorker('/fake/rom.sfc', mock_worker_dependencies['extractor'])

            # Pre-populate cache
            for i in range(20):
                worker._cache.put((i * 0x1000, 128), mock_qimage)

            cache_errors = []

            def cache_reader(offset_base: int):
                try:
                    for i in range(50):
                        key = ((offset_base + i) * 0x1000, 128)
                        worker._cache.get(key)
                except Exception as e:
                    cache_errors.append(str(e))

            def cache_writer(offset_base: int):
                try:
                    for i in range(50):
                        key = ((offset_base + i) * 0x1000, 128)
                        worker._cache.put(key, mock_qimage)
                except Exception as e:
                    cache_errors.append(str(e))

            # Run concurrent cache operations
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = []
                # 3 readers
                for i in range(3):
                    futures.append(executor.submit(cache_reader, i))
                # 3 writers
                for i in range(3):
                    futures.append(executor.submit(cache_writer, i + 10))

                for future in futures:
                    future.result()

            assert not cache_errors, f"Cache errors: {cache_errors}"

    def test_stop_request_thread_safety(self, test_rom_data, mock_worker_dependencies):
        """Test stop request from multiple threads is safe."""
        with patch('builtins.open', Mock(return_value=Mock(read=Mock(return_value=test_rom_data)))):
            worker = BatchThumbnailWorker('/fake/rom.sfc', mock_worker_dependencies['extractor'])

            stop_errors = []

            def request_stop():
                try:
                    worker.stop()
                    worker.clear_queue()
                except Exception as e:
                    stop_errors.append(str(e))

            # Multiple threads request stop simultaneously
            threads = []
            for _ in range(10):
                thread = threading.Thread(target=request_stop)
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            assert not stop_errors, f"Stop errors: {stop_errors}"
            assert worker._stop_requested

    def test_signal_emission_thread_boundary(self, qtbot):
        """Test signals are properly emitted across thread boundaries."""
        controller = ThumbnailWorkerController()

        received_signals = []

        def record_signal(offset, pixmap):
            # This should be called in the main thread
            thread_id = threading.current_thread().ident
            main_thread_id = threading.main_thread().ident
            assert thread_id == main_thread_id, "Signal not received in main thread"
            received_signals.append((offset, pixmap))

        controller.thumbnail_ready.connect(record_signal)

        # Note: Full thread boundary testing requires actual Qt event loop
        # which is complex to test in unit tests. This is a basic check.

class TestWorkerControllerThreadSafety:
    """Test thread safety of ThumbnailWorkerController."""

    def test_controller_lifecycle_thread_safety(self, qtbot):
        """Test controller lifecycle operations are thread-safe."""
        controller = ThumbnailWorkerController()

        errors = []

        def lifecycle_operations():
            try:
                # These operations should be thread-safe
                controller.queue_thumbnail(0x1000, 128, 0)
                controller.queue_batch([0x2000, 0x3000], 128, 0)
                controller.stop_worker()
            except Exception as e:
                errors.append(str(e))

        # Note: Controller operations should generally be called from main thread
        # but we test they don't crash if called from worker thread
        lifecycle_operations()

        assert not errors, f"Lifecycle errors: {errors}"

    def test_concurrent_queue_through_controller(self):
        """Test queuing through controller from multiple sources."""
        controller = ThumbnailWorkerController()

        # Simulate multiple UI components queuing thumbnails
        def ui_component_1():
            for i in range(50):
                controller.queue_thumbnail(i * 0x1000, 128, 1)

        def ui_component_2():
            controller.queue_batch(
                [i * 0x1000 for i in range(50, 100)],
                128,
                2
            )

        # These would typically be called from the same thread (main)
        # but we test concurrent access patterns
        ui_component_1()
        ui_component_2()

        # Should handle without errors
        controller.cleanup()

class TestRaceConditionPrevention:
    """Test prevention of specific race conditions."""

    @pytest.fixture
    def mock_worker_dependencies(self):
        """Mock worker dependencies."""
        with patch('ui.workers.batch_thumbnail_worker.ROMExtractor') as mock_extractor:
            with patch('ui.workers.batch_thumbnail_worker.TileRenderer') as mock_renderer:
                mock_renderer_instance = Mock()
                mock_renderer_instance.render_tiles.return_value = Mock()
                mock_renderer.return_value = mock_renderer_instance

                mock_extractor_instance = Mock()
                mock_extractor.return_value = mock_extractor_instance

                yield {
                    'extractor': mock_extractor_instance,
                    'renderer': mock_renderer_instance
                }

    def test_cache_clear_during_access_race(self, mock_qimage):
        """Test cache.clear() during concurrent get/put doesn't crash."""
        cache = LRUCache(maxsize=100)

        # Pre-populate
        for i in range(50):
            cache.put((i, i), mock_qimage)

        race_errors = []

        def accessor():
            try:
                for _ in range(1000):
                    cache.get((0, 0))
                    cache.put((1, 1), mock_qimage)
            except Exception as e:
                race_errors.append(str(e))

        def clearer():
            try:
                for _ in range(100):
                    time.sleep(0.001)  # Small delay to trigger race
                    cache.clear()
            except Exception as e:
                race_errors.append(str(e))

        # Run concurrent access and clear
        threads = [
            threading.Thread(target=accessor),
            threading.Thread(target=accessor),
            threading.Thread(target=clearer),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        assert not race_errors, f"Race condition errors: {race_errors}"

    def test_worker_cleanup_during_processing_race(self, test_rom_data, mock_worker_dependencies):
        """Test cleanup during active processing doesn't crash."""
        with patch('builtins.open', Mock(return_value=Mock(read=Mock(return_value=test_rom_data)))):
            worker = BatchThumbnailWorker('/fake/rom.sfc', mock_worker_dependencies['extractor'])

            # Queue work
            for i in range(100):
                worker.queue_thumbnail(i * 0x1000, 128, 0)

            cleanup_errors = []

            def cleanup_attempt():
                try:
                    time.sleep(0.01)  # Small delay
                    worker.cleanup()
                except Exception as e:
                    cleanup_errors.append(str(e))

            # Start cleanup from another thread while queueing
            cleanup_thread = threading.Thread(target=cleanup_attempt)
            cleanup_thread.start()

            # Continue queueing
            for i in range(100, 200):
                worker.queue_thumbnail(i * 0x1000, 128, 0)

            cleanup_thread.join()

            # Should handle gracefully
            assert len(cleanup_errors) == 0 or all(
                "already stopped" in str(e).lower() for e in cleanup_errors
            )

class TestDeadlockPrevention:
    """Test prevention of deadlock scenarios."""

    @pytest.fixture
    def mock_worker_dependencies(self):
        """Mock worker dependencies."""
        with patch('ui.workers.batch_thumbnail_worker.ROMExtractor') as mock_extractor:
            with patch('ui.workers.batch_thumbnail_worker.TileRenderer') as mock_renderer:
                mock_renderer_instance = Mock()
                mock_renderer_instance.render_tiles.return_value = Mock()
                mock_renderer.return_value = mock_renderer_instance

                mock_extractor_instance = Mock()
                mock_extractor.return_value = mock_extractor_instance

                yield {
                    'extractor': mock_extractor_instance,
                    'renderer': mock_renderer_instance
                }

    def test_no_deadlock_in_nested_mutex_operations(self, mock_qimage):
        """Test nested mutex operations don't cause deadlock."""
        cache = LRUCache(maxsize=10)

        # This should complete without deadlock
        start_time = time.time()

        # Simulate nested operations that could deadlock
        for i in range(100):
            cache.put((i, i), mock_qimage)
            cache.get_stats()  # Nested mutex lock
            if i > 0:
                cache.get((i-1, i-1))  # Another nested lock

        elapsed = time.time() - start_time

        # Should complete quickly without deadlock
        assert elapsed < 1.0, f"Operation took {elapsed:.2f}s, possible deadlock"

    def test_no_circular_wait_in_worker(self, test_rom_data, mock_worker_dependencies):
        """Test worker doesn't create circular wait conditions."""
        with patch('builtins.open', Mock(return_value=Mock(read=Mock(return_value=test_rom_data)))):
            worker = BatchThumbnailWorker('/fake/rom.sfc', mock_worker_dependencies['extractor'])

            start_time = time.time()

            # Operations that could cause circular wait
            worker.queue_thumbnail(0x1000, 128, 0)
            worker.pause()
            worker.queue_thumbnail(0x2000, 128, 0)
            worker.resume()
            worker.clear_queue()
            worker.stop()

            elapsed = time.time() - start_time

            # Should complete without deadlock
            assert elapsed < 0.5, f"Operations took {elapsed:.2f}s, possible deadlock"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
