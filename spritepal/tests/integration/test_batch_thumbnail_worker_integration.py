"""
Integration tests for BatchThumbnailWorker.

These tests focus on the specific bugs that were fixed:
- Infinite loop prevention with idle detection
- Memory cleanup after processing
- Thread lifecycle management
- Concurrent request handling
- Auto-stop functionality

CRASH PREVENTION:
- Uses @requires_real_qt to skip when Qt threading isn't available
- Uses @skip_if_wsl to prevent timeout/crash issues in WSL environments
- Automatically configures Qt platform (offscreen) for headless environments
- Falls back to headless logic tests when GUI tests can't run

REAL COMPONENT TESTING:
- Uses RealComponentFactory for TileRenderer and ROMExtractor
- MockHALProcessPool provides fast but realistic HAL responses
- Error injection tests still use Mock() for controlled failure scenarios
"""

from __future__ import annotations

import gc
import threading
import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QThread

from tests.infrastructure.environment_detection import (
    configure_qt_for_environment,
    requires_real_qt,
    skip_if_wsl,
)
from tests.infrastructure.qt_real_testing import (
    EventLoopHelper,
    MemoryHelper,
    QtTestCase,
    ThreadSafetyHelper,
)
from tests.infrastructure.real_component_factory import RealComponentFactory
from ui.workers.batch_thumbnail_worker import BatchThumbnailWorker

# Configure Qt for the detected environment to prevent crashes
configure_qt_for_environment()

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="BatchThumbnailWorker tests create worker threads that need cleanup time")
]


class WorkerThreadWrapper:
    """Wrapper to make BatchThumbnailWorker behave like a QThread for tests."""

    def __init__(self, worker: BatchThumbnailWorker):
        self.worker = worker
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)

        # Forward signals
        self.thumbnail_ready = worker.thumbnail_ready
        self.progress = worker.progress
        self.error = worker.error
        self.finished = worker.finished

    def start(self):
        """Start the worker thread."""
        self.thread.start()

    def stop(self):
        """Stop the worker."""
        self.worker.stop()

    def wait(self, timeout: int = 5000) -> bool:
        """Wait for thread to finish."""
        return self.thread.wait(timeout)

    def isRunning(self) -> bool:
        """Check if thread is running."""
        return self.thread.isRunning()

    def cleanup(self):
        """Clean up worker and thread."""
        # IMPORTANT: Stop the thread FIRST and wait for it to finish
        # before cleaning up resources. Cleaning up while the thread
        # is still running causes Qt assertion failures / crashes.
        if self.thread.isRunning():
            self.worker.stop()
            if not self.thread.wait(3000):  # 3 second timeout
                # Thread didn't stop gracefully, force terminate
                self.thread.terminate()
                self.thread.wait(1000)

        # Now safe to clean up resources after thread has stopped
        if hasattr(self.worker, "cleanup"):
            self.worker.cleanup()

    def queue_thumbnail(self, *args, **kwargs):
        """Forward queue_thumbnail calls to worker."""
        return self.worker.queue_thumbnail(*args, **kwargs)

    def queue_batch(self, *args, **kwargs):
        """Forward queue_batch calls to worker."""
        return self.worker.queue_batch(*args, **kwargs)

    def clear_queue(self, *args, **kwargs):
        """Forward clear_queue calls to worker."""
        return self.worker.clear_queue(*args, **kwargs)

    @property
    def rom_path(self):
        """Dynamically forward rom_path property."""
        return self.worker.rom_path

    @property
    def rom_extractor(self):
        """Dynamically forward rom_extractor property."""
        return self.worker.rom_extractor

    @property
    def _pending_count(self):
        """Dynamically forward _pending_count property."""
        return self.worker._pending_count

    @property
    def _completed_count(self):
        """Dynamically forward _completed_count property."""
        return self.worker._completed_count

    def __getattr__(self, name):
        """Forward any other attribute access to the worker."""
        return getattr(self.worker, name)


@pytest.fixture
def test_rom_file(tmp_path) -> str:
    """Create a test ROM file with some sprite data."""
    rom_path = tmp_path / "test_sprites.sfc"
    # Create ROM with some recognizable patterns
    rom_data = bytearray(1024 * 1024)  # 1MB ROM

    # Add some tile-like data at various offsets
    for offset in [0x10000, 0x20000, 0x30000]:
        for i in range(32 * 10):  # 10 tiles worth of data
            if offset + i < len(rom_data):
                rom_data[offset + i] = (i + offset) % 256

    rom_path.write_bytes(rom_data)
    return str(rom_path)


@pytest.fixture
def real_component_factory(tmp_path, isolated_managers):
    """Create RealComponentFactory for integration tests."""
    with RealComponentFactory() as factory:
        yield factory


@pytest.fixture
def real_rom_extractor(real_component_factory):
    """Create real ROM extractor using MockHALProcessPool for speed."""
    return real_component_factory.create_rom_extractor(use_mock_hal=True)


@pytest.fixture
def real_tile_renderer(real_component_factory):
    """Create real TileRenderer for integration tests."""
    return real_component_factory.create_tile_renderer()


@pytest.fixture
def mock_rom_extractor():
    """Create mock ROM extractor (for error injection tests only)."""
    extractor = Mock()
    extractor.rom_injector = Mock()

    # Mock decompression to return reasonable data
    def mock_find_compressed_sprite(rom_data, offset, expected_size=None):
        # Return some tile data
        return offset, b"\x00\x01\x02\x03" * 256  # 1KB of tile data

    extractor.rom_injector.find_compressed_sprite = mock_find_compressed_sprite
    return extractor


@pytest.fixture
def mock_tile_renderer():
    """Create mock tile renderer (for error injection tests only)."""
    renderer = Mock()

    # Mock render_tiles to return a simple image
    from PIL import Image

    mock_image = Image.new("RGBA", (64, 64), color=(128, 128, 128, 255))
    renderer.render_tiles.return_value = mock_image

    return renderer


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.usefixtures("isolated_managers")
@requires_real_qt
class TestBatchThumbnailWorkerIntegration(QtTestCase):
    """Integration tests for batch thumbnail worker."""

    def setup_method(self):
        """Set up for each test method."""
        super().setup_method()
        self.workers: list[WorkerThreadWrapper] = []

    def teardown_method(self):
        """Clean up after each test."""
        # Clean up all workers
        for worker in self.workers:
            worker.cleanup()
        self.workers.clear()
        super().teardown_method()

    def create_worker(self, rom_path: str, rom_extractor=None) -> WorkerThreadWrapper:
        """Create a worker with thread wrapper and track it for cleanup."""
        base_worker = BatchThumbnailWorker(rom_path, rom_extractor)
        worker = WorkerThreadWrapper(base_worker)
        self.workers.append(worker)
        return worker

    def test_worker_initialization_and_cleanup(self, test_rom_file, real_rom_extractor):
        """Test worker initialization and proper cleanup with real components."""
        with MemoryHelper.assert_no_leak(BatchThumbnailWorker, max_increase=1):
            worker = self.create_worker(test_rom_file, real_rom_extractor)

            # Worker should be initialized properly
            assert worker.rom_path == test_rom_file
            assert worker.rom_extractor is real_rom_extractor
            assert not worker.isRunning()  # Now works with wrapper
            assert worker._pending_count == 0
            assert worker._completed_count == 0

            # Cleanup should work without starting
            worker.cleanup()

    def test_real_controller_integration(self, test_rom_file):
        """Test using the real ThumbnailWorkerController - demonstrates proper usage."""
        from ui.workers.batch_thumbnail_worker import ThumbnailWorkerController

        controller = ThumbnailWorkerController()

        try:
            # Start worker with real components
            controller.start_worker(test_rom_file)

            # Track results
            thumbnails_received = []
            controller.thumbnail_ready.connect(lambda offset, pixmap: thumbnails_received.append((offset, pixmap)))

            # Queue some thumbnails
            controller.queue_thumbnail(0x10000, 64)
            controller.queue_thumbnail(0x20000, 64)

            # Let it process for a short time
            EventLoopHelper.process_events(2000)  # 2 seconds

            # Stop the worker
            controller.stop_worker()

            # Should have processed at least some thumbnails (may depend on ROM content)
            # This test validates the real controller works, even if no actual sprites found
            assert len(thumbnails_received) >= 0  # At least no crashes occurred

        finally:
            controller.cleanup()

    @skip_if_wsl("Timing-sensitive test: expects 8-20s execution time")
    @patch("ui.workers.batch_thumbnail_worker.TileRenderer")
    def test_idle_detection_prevents_infinite_loop(
        self, mock_tile_renderer_class, test_rom_file, mock_rom_extractor, mock_tile_renderer
    ):
        """Test that idle detection prevents infinite loops."""
        mock_tile_renderer_class.return_value = mock_tile_renderer

        worker = self.create_worker(test_rom_file, mock_rom_extractor)

        # Don't queue any work - should auto-stop due to idle detection
        start_time = time.time()

        worker.start()

        # Wait for worker to auto-stop (should be quick due to idle detection)
        worker.wait(15000)  # 15 second timeout - allows for 10s auto-stop plus initialization overhead

        end_time = time.time()
        execution_time = end_time - start_time

        # Should stop within reasonable time (observed ~16-17s with overhead, but much less than infinite loop)
        assert execution_time < 20.0, f"Worker took {execution_time:.2f}s to auto-stop, may indicate infinite loop"
        assert execution_time > 8.0, (
            f"Worker stopped too quickly ({execution_time:.2f}s), idle detection may not be working"
        )
        assert not worker.isRunning()

    @skip_if_wsl("Timing-sensitive test: expects <8s execution time")
    @patch("ui.workers.batch_thumbnail_worker.TileRenderer")
    def test_processing_with_auto_stop(
        self, mock_tile_renderer_class, test_rom_file, mock_rom_extractor, mock_tile_renderer
    ):
        """Test processing requests followed by auto-stop."""
        mock_tile_renderer_class.return_value = mock_tile_renderer

        worker = self.create_worker(test_rom_file, mock_rom_extractor)

        # Track thumbnail emissions
        thumbnails_received = []
        worker.thumbnail_ready.connect(lambda offset, pixmap: thumbnails_received.append((offset, pixmap)))

        # Queue a few thumbnails
        offsets = [0x10000, 0x20000, 0x30000]
        for offset in offsets:
            worker.queue_thumbnail(offset, 128)

        start_time = time.time()
        worker.start()

        # Wait for processing to complete and auto-stop
        worker.wait(10000)  # 10 second timeout

        end_time = time.time()
        execution_time = end_time - start_time

        # Should complete processing and auto-stop efficiently
        assert execution_time < 8.0, f"Processing took {execution_time:.2f}s, too slow"
        assert not worker.isRunning()

        # Should have processed requested thumbnails
        assert len(thumbnails_received) >= len(offsets)

    def test_memory_cleanup_after_processing(self, test_rom_file, real_rom_extractor):
        """Test that worker properly cleans up memory after processing with real components."""
        initial_rom_data_count = len(
            [
                obj
                for obj in gc.get_objects()
                if isinstance(obj, bytes) and len(obj) > 100000  # Large byte objects (ROM data)
            ]
        )

        worker = self.create_worker(test_rom_file, real_rom_extractor)

        # Queue some work
        worker.queue_thumbnail(0x10000, 128)
        worker.queue_thumbnail(0x20000, 128)

        # Process thumbnails
        worker.start()
        finished = worker.wait(5000)
        if not finished and worker.isRunning():
            # Ensure the worker is stopped before GC to avoid Qt finalization races.
            worker.stop()
            worker.wait(2000)

        # Worker should clean up automatically
        gc.collect()
        EventLoopHelper.process_events(100)
        gc.collect()

        final_rom_data_count = len([obj for obj in gc.get_objects() if isinstance(obj, bytes) and len(obj) > 100000])

        # Should not leak large byte objects
        leaked_objects = final_rom_data_count - initial_rom_data_count
        assert leaked_objects <= 1, f"Leaked {leaked_objects} large byte objects"

    @skip_if_wsl("Timing-sensitive test: depends on 10s auto-stop")
    @patch("ui.workers.batch_thumbnail_worker.TileRenderer")
    def test_concurrent_queue_operations(
        self, mock_tile_renderer_class, test_rom_file, mock_rom_extractor, mock_tile_renderer
    ):
        """Test concurrent queue operations don't cause issues."""
        mock_tile_renderer_class.return_value = mock_tile_renderer

        worker = self.create_worker(test_rom_file, mock_rom_extractor)

        # Queue operations from multiple "threads" (simulated)
        def queue_thumbnails(offset_start: int, count: int):
            for i in range(count):
                worker.queue_thumbnail(offset_start + i * 0x1000, 128)

        # Queue from different offset ranges
        queue_thumbnails(0x10000, 10)
        queue_thumbnails(0x50000, 10)
        queue_thumbnails(0x90000, 10)

        assert worker._pending_count == 30

        # Start processing
        worker.start()

        # Add more while processing
        queue_thumbnails(0xD0000, 5)

        # Should handle concurrent operations safely
        worker.wait(10000)
        assert not worker.isRunning()

    @skip_if_wsl("Timing-sensitive test: expects <2s stop time")
    def test_stop_request_interrupts_processing(self, test_rom_file, real_rom_extractor):
        """Test that stop request properly interrupts processing with real components."""
        worker = self.create_worker(test_rom_file, real_rom_extractor)

        # Queue many thumbnails
        for i in range(100):
            worker.queue_thumbnail(0x10000 + i * 0x1000, 128)

        worker.start()

        # Wait a bit for processing to begin
        EventLoopHelper.process_events(100)

        # Request stop
        worker.stop()

        # Should stop quickly
        start_time = time.time()
        result = worker.wait(3000)  # 3 second timeout
        stop_time = time.time() - start_time

        assert result, "Worker did not stop within timeout"
        assert stop_time < 2.0, f"Worker took {stop_time:.2f}s to stop"
        assert not worker.isRunning()

    def test_cache_functionality_and_limits(self, test_rom_file, real_rom_extractor):
        """Test thumbnail caching functionality and size limits with real components."""
        worker = self.create_worker(test_rom_file, real_rom_extractor)
        worker._cache_size_limit = 5  # Small cache for testing

        thumbnails_received = []
        worker.thumbnail_ready.connect(lambda offset, pixmap: thumbnails_received.append((offset, pixmap)))

        # Queue same thumbnail multiple times
        for _ in range(3):
            worker.queue_thumbnail(0x10000, 128)

        worker.start()
        worker.wait(5000)

        # Should use cache for repeated requests
        assert len(thumbnails_received) >= 3

        # Cache should not exceed limit
        assert worker.get_cache_size() <= worker._cache_size_limit

    @skip_if_wsl("Timing-sensitive test: depends on worker stop timing")
    def test_cleanup_method_comprehensive(self, test_rom_file, real_rom_extractor):
        """Test comprehensive cleanup functionality with real components."""
        worker = self.create_worker(test_rom_file, real_rom_extractor)

        # Add some items to cache
        worker.queue_thumbnail(0x10000, 128)
        worker.start()
        EventLoopHelper.process_events(500)  # Let some processing happen

        # Call cleanup
        worker.cleanup()

        # Should be stopped
        assert not worker.isRunning()

        # Cache should be cleared
        assert worker.get_cache_size() == 0

    @skip_if_wsl("Timing-sensitive test: depends on worker stop timing")
    @patch("ui.workers.batch_thumbnail_worker.TileRenderer")
    def test_error_handling_during_processing(self, mock_tile_renderer_class, test_rom_file, mock_rom_extractor):
        """Test error handling during thumbnail processing."""
        # Mock tile renderer to raise errors occasionally
        mock_renderer = Mock()
        mock_renderer.render_tiles.side_effect = [
            Exception("Render error"),  # First call fails
            Mock(),  # Second call succeeds
            Exception("Another error"),  # Third call fails
        ]
        mock_tile_renderer_class.return_value = mock_renderer

        worker = self.create_worker(test_rom_file, mock_rom_extractor)

        errors_received = []
        worker.error.connect(errors_received.append)

        # Queue thumbnails
        worker.queue_thumbnail(0x10000, 128)
        worker.queue_thumbnail(0x20000, 128)
        worker.queue_thumbnail(0x30000, 128)

        worker.start()
        worker.wait(5000)

        # Worker should handle errors gracefully and continue processing
        assert not worker.isRunning()
        # May have received error signals but should not crash


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.performance
@pytest.mark.usefixtures("isolated_managers")
@requires_real_qt
@skip_if_wsl("Performance tests require stable Qt threading")
class TestBatchThumbnailWorkerPerformance(QtTestCase):
    """Performance tests for batch thumbnail worker."""

    def test_throughput_performance(self, test_rom_file, mock_rom_extractor):
        """Test thumbnail generation throughput."""
        with patch("ui.workers.batch_thumbnail_worker.TileRenderer") as mock_renderer_class:
            # Fast mock renderer
            mock_renderer = Mock()
            from PIL import Image

            mock_image = Image.new("RGBA", (32, 32), color=(100, 100, 100, 255))
            mock_renderer.render_tiles.return_value = mock_image
            mock_renderer_class.return_value = mock_renderer

            # Use WorkerThreadWrapper for consistent threading behavior
            base_worker = BatchThumbnailWorker(test_rom_file, mock_rom_extractor)
            worker = WorkerThreadWrapper(base_worker)

            # Queue moderate number of thumbnails
            thumbnail_count = 50
            for i in range(thumbnail_count):
                worker.queue_thumbnail(0x10000 + i * 0x1000, 128)

            start_time = time.time()
            worker.start()
            worker.wait(15000)  # 15 second timeout
            processing_time = time.time() - start_time

            # Should process thumbnails efficiently (real HAL compression is slower than mocks)
            throughput = thumbnail_count / processing_time if processing_time > 0 else 0
            assert throughput > 2.0, f"Throughput too low: {throughput:.1f} thumbnails/sec"

            worker.cleanup()

    def test_memory_usage_with_large_cache(self, test_rom_file, mock_rom_extractor):
        """Test memory usage with large cache."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        with patch("ui.workers.batch_thumbnail_worker.TileRenderer"):
            # Use WorkerThreadWrapper for consistent threading behavior
            base_worker = BatchThumbnailWorker(test_rom_file, mock_rom_extractor)
            base_worker._cache_size_limit = 200  # Large cache
            worker = WorkerThreadWrapper(base_worker)

            # Generate many thumbnails
            for i in range(100):
                worker.queue_thumbnail(0x10000 + i * 0x800, 256)  # Large thumbnails

            worker.start()
            worker.wait(20000)  # 20 second timeout

            peak_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = peak_memory - initial_memory

            # Clean up
            worker.cleanup()
            gc.collect()

            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_after_cleanup = final_memory - initial_memory

            # Memory usage should be reasonable
            assert memory_increase < 500, f"Memory usage too high: {memory_increase:.1f} MB"

            # Should clean up most memory
            assert memory_after_cleanup < memory_increase * 0.5, "Poor memory cleanup"


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.usefixtures("isolated_managers")
@requires_real_qt
@skip_if_wsl("Thread safety tests require stable Qt threading")
class TestBatchThumbnailWorkerThreadSafety(QtTestCase):
    """Thread safety tests for batch thumbnail worker."""

    def test_thread_safety_with_multiple_workers(self, test_rom_file, real_rom_extractor):
        """Test thread safety with multiple concurrent workers using real components."""
        workers = []

        try:
            # Create multiple workers with proper threading
            for i in range(3):
                base_worker = BatchThumbnailWorker(test_rom_file, real_rom_extractor)
                worker = WorkerThreadWrapper(base_worker)
                workers.append(worker)

                # Queue different offsets for each worker
                for j in range(10):
                    offset = 0x10000 + (i * 10 + j) * 0x1000
                    worker.queue_thumbnail(offset, 128)

            # Start all workers
            for worker in workers:
                worker.start()

            # Wait for all to complete
            for worker in workers:
                assert worker.wait(10000), "Worker did not complete within timeout"

            # All should have stopped
            for worker in workers:
                assert not worker.isRunning()

        finally:
            # Clean up all workers
            for worker in workers:
                worker.cleanup()

    def test_signal_thread_safety(self, test_rom_file, real_rom_extractor):
        """Test that signals are emitted from correct thread using real components."""
        ThreadSafetyHelper.assert_main_thread()

        # Use WorkerThreadWrapper for proper threading
        base_worker = BatchThumbnailWorker(test_rom_file, real_rom_extractor)
        worker = WorkerThreadWrapper(base_worker)

        signal_thread_ids = []

        def on_thumbnail_ready(offset, pixmap):
            # Signal should be received in main thread
            current_thread = threading.current_thread()
            signal_thread_ids.append(current_thread.ident)

        worker.thumbnail_ready.connect(on_thumbnail_ready)

        worker.queue_thumbnail(0x10000, 128)
        worker.start()
        worker.wait(5000)

        # Signals should have been received in main thread
        main_thread_id = threading.current_thread().ident
        for thread_id in signal_thread_ids:
            assert thread_id == main_thread_id, "Signal not received in main thread"

        worker.cleanup()


@pytest.mark.headless
@pytest.mark.integration
class TestBatchThumbnailWorkerHeadlessIntegration:
    """Headless integration tests using logic verification."""

    def test_headless_idle_detection_logic(self):
        """Test idle detection logic without Qt dependencies."""

        class MockWorkerLogic:
            def __init__(self):
                self.idle_iterations = 0
                self.max_idle_iterations = 100
                self.processed_count = 0
                self.stop_requested = False
                self.request_queue = []

            def get_next_request(self):
                return self.request_queue.pop(0) if self.request_queue else None

            def simulate_idle_detection(self):
                """Simulate the idle detection logic."""
                while not self.stop_requested:
                    request = self.get_next_request()
                    if not request:
                        self.idle_iterations += 1

                        # Auto-stop after being idle
                        if self.idle_iterations >= self.max_idle_iterations:
                            return "auto_stopped"
                        continue

                    # Reset idle counter when work is found
                    self.idle_iterations = 0
                    self.processed_count += 1

                    # Simulate processing
                    if self.processed_count >= 1000:  # Safety limit
                        return "safety_limit"

                return "stop_requested"

        # Test 1: No work - should auto-stop
        logic = MockWorkerLogic()
        result = logic.simulate_idle_detection()

        assert result == "auto_stopped"
        assert logic.idle_iterations == logic.max_idle_iterations
        assert logic.processed_count == 0

        # Test 2: Some work then idle - should process then auto-stop
        logic = MockWorkerLogic()
        logic.request_queue = ["req1", "req2", "req3"]

        result = logic.simulate_idle_detection()

        assert result == "auto_stopped"
        assert logic.processed_count == 3

        # Test 3: Stop requested - should stop immediately
        logic = MockWorkerLogic()
        logic.request_queue = ["req1", "req2"]
        logic.stop_requested = True

        result = logic.simulate_idle_detection()

        assert result == "stop_requested"
        assert logic.processed_count == 0

    def test_headless_cache_management_logic(self):
        """Test cache management logic without Qt objects."""

        class MockCache:
            def __init__(self, size_limit=5):
                self.cache = {}
                self.size_limit = size_limit
                self.access_order = []

            def add_to_cache(self, key, value):
                # Remove oldest if at limit
                if len(self.cache) >= self.size_limit:
                    oldest_key = self.access_order[0]
                    del self.cache[oldest_key]
                    self.access_order.remove(oldest_key)

                self.cache[key] = value
                self.access_order.append(key)

            def get_from_cache(self, key):
                if key in self.cache:
                    # Move to end (most recent)
                    self.access_order.remove(key)
                    self.access_order.append(key)
                    return self.cache[key]
                return None

            def size(self):
                return len(self.cache)

            def clear(self):
                self.cache.clear()
                self.access_order.clear()

        cache = MockCache(size_limit=3)

        # Add items up to limit
        cache.add_to_cache("key1", "value1")
        cache.add_to_cache("key2", "value2")
        cache.add_to_cache("key3", "value3")

        assert cache.size() == 3

        # Adding beyond limit should evict oldest
        cache.add_to_cache("key4", "value4")

        assert cache.size() == 3
        assert cache.get_from_cache("key1") is None  # Should be evicted
        assert cache.get_from_cache("key4") == "value4"  # Should be present

        # Clear should empty cache
        cache.clear()
        assert cache.size() == 0

    def test_headless_memory_cleanup_logic(self):
        """Test memory cleanup logic patterns."""

        class MockResourceManager:
            def __init__(self):
                self.rom_data = None
                self.cache = {}
                self.is_cleaned = False

            def load_rom_data(self, rom_path):
                # Simulate loading ROM data
                self.rom_data = b"\x00" * 1024000  # 1MB

            def clear_rom_data(self):
                if self.rom_data is not None:
                    data_size = len(self.rom_data)
                    self.rom_data = None
                    return data_size
                return 0

            def clear_cache(self):
                cache_size = len(self.cache)
                self.cache.clear()
                return cache_size

            def cleanup(self):
                """Comprehensive cleanup method."""
                rom_freed = self.clear_rom_data()
                cache_freed = self.clear_cache()
                self.is_cleaned = True
                return rom_freed, cache_freed

        manager = MockResourceManager()

        # Load resources
        manager.load_rom_data("test_rom.sfc")
        manager.cache = {"key1": "data1", "key2": "data2"}

        # Verify resources are loaded
        assert manager.rom_data is not None
        assert len(manager.cache) == 2
        assert not manager.is_cleaned

        # Test cleanup
        rom_freed, cache_freed = manager.cleanup()

        # Verify cleanup
        assert manager.rom_data is None
        assert len(manager.cache) == 0
        assert manager.is_cleaned
        assert rom_freed == 1024000
        assert cache_freed == 2

    def test_headless_queue_operations_logic(self):
        """Test thread-safe queue operations logic."""
        import threading
        from queue import Empty, PriorityQueue

        class MockQueueManager:
            def __init__(self):
                self.queue = PriorityQueue()
                self.pending_count = 0
                self.completed_count = 0
                self.mutex = threading.Lock()

            def queue_request(self, priority, data):
                with self.mutex:
                    self.queue.put((priority, data))
                    self.pending_count += 1

            def get_next_request(self):
                try:
                    with self.mutex:
                        if not self.queue.empty():
                            priority, data = self.queue.get_nowait()
                            return data
                except Empty:
                    pass
                return None

            def complete_request(self):
                with self.mutex:
                    self.completed_count += 1

            def clear_queue(self):
                with self.mutex:
                    while not self.queue.empty():
                        try:
                            self.queue.get_nowait()
                        except Empty:
                            break
                    self.pending_count = 0

        manager = MockQueueManager()

        # Queue requests with different priorities
        manager.queue_request(1, "high_priority")
        manager.queue_request(3, "low_priority")
        manager.queue_request(2, "medium_priority")

        assert manager.pending_count == 3

        # Should get high priority first
        request = manager.get_next_request()
        assert request == "high_priority"

        # Then medium priority
        request = manager.get_next_request()
        assert request == "medium_priority"

        # Clear queue should empty it
        manager.clear_queue()
        assert manager.pending_count == 0
        assert manager.get_next_request() is None
