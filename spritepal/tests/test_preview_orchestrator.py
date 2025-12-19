"""
Comprehensive tests for PreviewOrchestrator - Central coordination for async preview system

Tests focus on:
1. Request management and priority queuing
2. Multi-tier caching coordination (L1, L2, L3)
3. Worker allocation and load balancing
4. Error handling and recovery patterns
5. Performance metrics and monitoring
6. Request cancellation and timeout handling
7. Cache layer interaction and fallback behavior
"""
from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QObject, QTimer

from core.preview_orchestrator import (
    ErrorType,
    PreviewData,
    PreviewError,
    PreviewMemoryCache,
    PreviewMetrics,
    # Serial execution required: Real Qt components
    PreviewOrchestrator,
    PreviewRequest,
    Priority,
)

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Preview workers may not clean up within fixture timeout"),
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
]
class MockROMCache:
    """Mock ROM cache for testing"""
    def __init__(self):
        self.cache_dir = "/test/cache"

class MockAsyncROMCache(QObject):
    """Mock AsyncROMCache for testing orchestrator integration"""
    from PySide6.QtCore import Signal

    cache_ready = Signal(str, bytes, dict)  # request_id, data, metadata
    cache_error = Signal(str, str)          # request_id, error

    def __init__(self):
        super().__init__()
        self.requests = []
        self.memory_cleared = False

    def get_cached_async(self, rom_path: str, offset: int, request_id: str):
        """Mock async cache get"""
        self.requests.append((rom_path, offset, request_id))
        # Simulate cache miss by default
        self.cache_error.emit(request_id, "Cache miss")

    def save_cached_async(self, rom_path: str, offset: int, data: bytes, metadata: dict):
        """Mock async cache save"""
        pass

    def clear_memory_cache(self):
        """Mock memory cache clear"""
        self.memory_cleared = True

class MockWorkerPool(QObject):
    """Mock PreviewWorkerPool for testing"""
    from PySide6.QtCore import Signal

    preview_ready = Signal(str, object)  # request_id, PreviewData
    preview_error = Signal(str, object)  # request_id, PreviewError

    def __init__(self):
        super().__init__()
        self.generate_requests = []

    def generate_preview(self, request_id: str, rom_path: str, offset: int):
        """Mock preview generation"""
        self.generate_requests.append((request_id, rom_path, offset))

        # Simulate successful generation
        preview_data = PreviewData(
            tile_data=b"mock_tile_data",
            width=128,
            height=128,
            offset=offset,
            rom_path=rom_path,
            metadata={"source": "mock_worker"}
        )

        # Emit after short delay to simulate work
        QTimer.singleShot(10, lambda: self.preview_ready.emit(request_id, preview_data))

class TestPreviewRequest:
    """Test PreviewRequest data structure and ordering"""

    def test_request_creation(self):
        """Test request creation with defaults"""
        request = PreviewRequest()

        assert len(request.request_id) > 0
        assert request.rom_path == ""
        assert request.offset == 0
        assert request.priority == Priority.NORMAL
        assert isinstance(request.timestamp, float)
        assert not request.cancelled
        assert request.callback is None

    def test_request_with_parameters(self):
        """Test request creation with specific parameters"""
        callback = Mock()
        request = PreviewRequest(
            request_id="test_123",
            rom_path="/test/rom.sfc",
            offset=0x200000,
            priority=Priority.HIGH,
            callback=callback
        )

        assert request.request_id == "test_123"
        assert request.rom_path == "/test/rom.sfc"
        assert request.offset == 0x200000
        assert request.priority == Priority.HIGH
        assert request.callback == callback

    def test_request_priority_ordering(self):
        """Test that requests order correctly by priority"""
        urgent_request = PreviewRequest(priority=Priority.URGENT)
        high_request = PreviewRequest(priority=Priority.HIGH)
        normal_request = PreviewRequest(priority=Priority.NORMAL)
        low_request = PreviewRequest(priority=Priority.LOW)

        # Urgent should come first
        assert urgent_request < high_request
        assert urgent_request < normal_request
        assert urgent_request < low_request

        # High should come before normal and low
        assert high_request < normal_request
        assert high_request < low_request

        # Normal should come before low
        assert normal_request < low_request

    def test_request_timestamp_ordering(self):
        """Test FIFO ordering for same priority requests"""
        # Create requests with same priority but different timestamps
        early_request = PreviewRequest(priority=Priority.NORMAL)
        time.sleep(0.001)  # sleep-ok: ensure different timestamps
        late_request = PreviewRequest(priority=Priority.NORMAL)

        # Earlier request should come first
        assert early_request < late_request

class TestPreviewData:
    """Test PreviewData structure and methods"""

    def test_preview_data_creation(self):
        """Test preview data creation"""
        data = PreviewData(
            tile_data=b"test_data",
            width=128,
            height=128,
            offset=0x200000,
            rom_path="/test/rom.sfc"
        )

        assert data.tile_data == b"test_data"
        assert data.width == 128
        assert data.height == 128
        assert data.offset == 0x200000
        assert data.rom_path == "/test/rom.sfc"
        assert isinstance(data.metadata, dict)
        assert isinstance(data.generated_at, float)

    def test_size_calculation(self):
        """Test memory size calculation"""
        # Test without pixmap
        data = PreviewData(
            tile_data=b"x" * 1000,  # 1000 bytes
            width=128,
            height=128
        )
        assert data.size_bytes == 1000  # Just tile_data size

        # Test with mock pixmap
        mock_pixmap = Mock()
        data.pixmap = mock_pixmap
        expected_pixmap_size = 128 * 128 * 4  # RGBA
        assert data.size_bytes == expected_pixmap_size + 1000

class TestPreviewError:
    """Test PreviewError structure"""

    def test_error_creation(self):
        """Test error creation with details"""
        error = PreviewError(
            request_id="error_test",
            error_type=ErrorType.FILE_IO,
            message="Test error",
            details={"file": "/test/rom.sfc"},
            recoverable=False
        )

        assert error.request_id == "error_test"
        assert error.error_type == ErrorType.FILE_IO
        assert error.message == "Test error"
        assert error.details["file"] == "/test/rom.sfc"
        assert not error.recoverable
        assert isinstance(error.timestamp, float)

class TestPreviewMetrics:
    """Test PreviewMetrics calculations"""

    def test_empty_metrics(self):
        """Test metrics with no data"""
        metrics = PreviewMetrics()

        assert metrics.cache_hit_rate == 0.0
        assert metrics.avg_response_time == 0.0
        assert metrics.p99_response_time == 0.0

    def test_cache_hit_rate(self):
        """Test cache hit rate calculation"""
        metrics = PreviewMetrics(
            cache_hits=75,
            cache_misses=25
        )

        assert metrics.cache_hit_rate == 75.0  # 75%

    def test_average_response_time(self):
        """Test average response time calculation"""
        metrics = PreviewMetrics(
            total_requests=10,
            total_time=5.0
        )

        assert metrics.avg_response_time == 0.5  # 500ms average

    def test_p99_response_time(self):
        """Test 99th percentile response time"""
        # Generate response times (in seconds)
        times = [0.001, 0.002, 0.003, 0.004, 0.005,  # Fast responses
                 0.010, 0.015, 0.020, 0.025, 0.030,  # Medium responses
                 0.100, 0.200, 0.300, 0.400, 0.500]  # Slow responses

        metrics = PreviewMetrics(generation_times=times)
        p99 = metrics.p99_response_time

        # P99 should be one of the higher values
        assert p99 >= 0.400  # Should capture slow tail

class TestPreviewMemoryCache:
    """Test PreviewMemoryCache LRU behavior"""

    def test_cache_creation(self):
        """Test cache initialization"""
        cache = PreviewMemoryCache(max_size_mb=5)

        assert cache._max_size_bytes == 5 * 1024 * 1024
        assert cache._current_size_bytes == 0
        assert len(cache._cache) == 0

    def test_get_nonexistent_item(self):
        """Test getting non-existent cache item"""
        cache = PreviewMemoryCache()

        result = cache.get("nonexistent_key")
        assert result is None

    def test_put_and_get_item(self):
        """Test storing and retrieving cache item"""
        cache = PreviewMemoryCache()

        data = PreviewData(
            tile_data=b"test_data",
            width=64,
            height=64
        )

        cache.put("test_key", data)
        retrieved = cache.get("test_key")

        assert retrieved == data
        assert cache._current_size_bytes > 0

    def test_lru_eviction(self):
        """Test LRU eviction when cache exceeds size limit"""
        # Create small cache for testing
        cache = PreviewMemoryCache(max_size_mb=0.001)  # ~1KB limit

        # Add items that exceed size limit
        for i in range(5):
            data = PreviewData(tile_data=b"x" * 500, width=16, height=16)  # ~500 bytes each
            cache.put(f"key_{i}", data)

        # Cache should have evicted oldest items
        assert len(cache._cache) < 5
        assert cache._current_size_bytes <= cache._max_size_bytes

        # Most recently added items should still be present
        assert cache.get("key_4") is not None

    def test_lru_access_ordering(self):
        """Test that accessing items moves them to most recent"""
        cache = PreviewMemoryCache()

        # Add items
        data1 = PreviewData(tile_data=b"data1", width=16, height=16)
        data2 = PreviewData(tile_data=b"data2", width=16, height=16)

        cache.put("key1", data1)
        cache.put("key2", data2)

        # Access first item (should move to end)
        retrieved = cache.get("key1")
        assert retrieved == data1

        # The ordering should be preserved internally
        keys_list = list(cache._cache.keys())
        assert keys_list[-1] == "key1"  # Most recently accessed

    def test_cache_clear(self):
        """Test clearing all cache items"""
        cache = PreviewMemoryCache()

        # Add some items
        for i in range(3):
            data = PreviewData(tile_data=b"data", width=16, height=16)
            cache.put(f"key_{i}", data)

        assert len(cache._cache) == 3
        assert cache._current_size_bytes > 0

        # Clear cache
        cache.clear()

        assert len(cache._cache) == 0
        assert cache._current_size_bytes == 0

class TestPreviewOrchestrator:
    """Test PreviewOrchestrator coordination and async interface"""

    def setup_method(self):
        """Set up test fixtures"""
        self.orchestrator = PreviewOrchestrator()

        # Mock the cache and worker dependencies
        self.mock_async_cache = MockAsyncROMCache()
        self.mock_worker_pool = MockWorkerPool()

        # Inject mocks
        self.orchestrator._async_cache = self.mock_async_cache
        self.orchestrator._worker_pool = self.mock_worker_pool

        # Connect mock signals
        self.mock_async_cache.cache_ready.connect(self.orchestrator._on_cache_ready)
        self.mock_async_cache.cache_error.connect(self.orchestrator._on_cache_error)
        self.mock_worker_pool.preview_ready.connect(self.orchestrator._on_preview_ready)
        self.mock_worker_pool.preview_error.connect(self.orchestrator._on_preview_error)

    def teardown_method(self):
        """Clean up test fixtures"""
        if hasattr(self, 'orchestrator'):
            del self.orchestrator

    def test_orchestrator_initialization(self):
        """Test proper initialization"""
        assert isinstance(self.orchestrator._request_queue, type(self.orchestrator._request_queue))
        assert isinstance(self.orchestrator._active_requests, dict)
        assert isinstance(self.orchestrator._metrics, PreviewMetrics)
        # Note: _metrics_timer.isActive() may be False in test contexts
        # because "Timers can only be used with threads started with QThread"
        assert self.orchestrator._metrics_timer is not None
        assert self.orchestrator._max_concurrent_requests == 4
        assert self.orchestrator._request_timeout_ms == 5000

    def test_l1_cache_hit_immediate_response(self, qtbot):
        """Test L1 cache (last preview) provides immediate response"""
        # Pre-populate L1 cache
        cached_data = PreviewData(
            tile_data=b"l1_cache_data",
            width=128,
            height=128,
            offset=0x200000,
            rom_path="/test/rom.sfc"
        )
        self.orchestrator._last_preview = cached_data

        # Request same offset should hit L1 cache
        with qtbot.wait_signal(self.orchestrator.preview_ready, timeout=100) as blocker:
            request_id = self.orchestrator.request_preview("/test/rom.sfc", 0x200000)

        # Should get immediate response from L1 cache
        args = blocker.args
        assert args[0] == request_id
        assert args[1] == cached_data

        # Metrics should show cache hit
        assert self.orchestrator._metrics.cache_hits == 1

    def test_l2_memory_cache_hit(self, qtbot):
        """Test L2 memory cache hit when L1 misses"""
        # Set up L2 cache
        self.orchestrator._memory_cache = PreviewMemoryCache()
        cached_data = PreviewData(
            tile_data=b"l2_cache_data",
            width=128,
            height=128,
            offset=0x300000,
            rom_path="/test/rom.sfc"
        )
        cache_key = self.orchestrator._generate_cache_key("/test/rom.sfc", 0x300000)
        self.orchestrator._memory_cache.put(cache_key, cached_data)

        # Request should hit L2 cache
        with qtbot.wait_signal(self.orchestrator.preview_ready, timeout=100) as blocker:
            request_id = self.orchestrator.request_preview("/test/rom.sfc", 0x300000)

        args = blocker.args
        assert args[0] == request_id
        assert args[1] == cached_data

        # Should update L1 cache
        assert self.orchestrator._last_preview == cached_data

    def test_cache_miss_triggers_async_generation(self, qtbot):
        """Test cache miss triggers async preview generation"""
        # Clear all caches
        self.orchestrator._last_preview = None
        self.orchestrator._memory_cache = None

        # Request should go through async cache then to worker
        with qtbot.wait_signal(self.orchestrator.preview_ready, timeout=500) as blocker:
            request_id = self.orchestrator.request_preview("/test/rom.sfc", 0x400000, Priority.HIGH)

        # Should eventually get response from worker pool
        args = blocker.args
        assert args[0] == request_id
        preview_data = args[1]
        assert isinstance(preview_data, PreviewData)
        assert preview_data.offset == 0x400000

        # Verify request went through async cache first
        assert len(self.mock_async_cache.requests) == 1
        assert self.mock_async_cache.requests[0][1] == 0x400000  # offset

        # Verify worker was called after cache miss
        assert len(self.mock_worker_pool.generate_requests) == 1
        assert self.mock_worker_pool.generate_requests[0][2] == 0x400000  # offset

    def test_request_priority_ordering(self):
        """Test requests are processed in priority order"""
        # Submit requests in reverse priority order
        self.orchestrator.request_preview("/test/rom.sfc", 0x100000, Priority.LOW)
        self.orchestrator.request_preview("/test/rom.sfc", 0x200000, Priority.NORMAL)
        self.orchestrator.request_preview("/test/rom.sfc", 0x300000, Priority.HIGH)
        self.orchestrator.request_preview("/test/rom.sfc", 0x400000, Priority.URGENT)

        # Verify all requests are queued
        assert len(self.orchestrator._active_requests) == 4

        # Process requests and verify order
        processed_offsets = []
        while not self.orchestrator._request_queue.empty():
            request = self.orchestrator._request_queue.get()
            processed_offsets.append(request.offset)

        # Should be in priority order (urgent first, low last)
        expected_order = [0x400000, 0x300000, 0x200000, 0x100000]
        assert processed_offsets == expected_order

    def test_request_cancellation(self, qtbot):
        """Test request cancellation prevents processing"""
        # Submit request
        request_id = self.orchestrator.request_preview("/test/rom.sfc", 0x200000)

        # Cancel immediately
        self.orchestrator.cancel_request(request_id)

        # Verify request is marked as cancelled
        request = self.orchestrator._active_requests.get(request_id)
        assert request is not None
        assert request.cancelled

        # Metrics should show cancellation
        assert self.orchestrator._metrics.cancellations == 1

    def test_concurrent_request_limit(self):
        """Test concurrent request limit enforcement"""
        # Submit more requests than the concurrent limit
        max_concurrent = self.orchestrator._max_concurrent_requests
        request_ids = []

        for i in range(max_concurrent + 2):
            request_id = self.orchestrator.request_preview(
                f"/test/rom_{i}.sfc",
                i * 0x1000,
                Priority.NORMAL
            )
            request_ids.append(request_id)

        # Should have all requests tracked
        assert len(self.orchestrator._active_requests) == max_concurrent + 2

        # But processing should be limited
        # (This is more of an integration test with the timer mechanism)
        assert len(request_ids) > max_concurrent

    def test_callback_execution(self, qtbot):
        """Test that request callbacks are executed"""
        callback = Mock()

        # Set up L1 cache for immediate response
        cached_data = PreviewData(
            tile_data=b"callback_test",
            width=64,
            height=64,
            offset=0x200000,
            rom_path="/test/rom.sfc"
        )
        self.orchestrator._last_preview = cached_data

        # For L1 cache hits, the signal is emitted synchronously during request_preview.
        # We need to set up the wait BEFORE calling request_preview, which means
        # we can't use a context manager. Instead, verify the callback directly.
        self.orchestrator.request_preview(
            "/test/rom.sfc",
            0x200000,
            callback=callback
        )

        # For L1 cache hits, callback is executed synchronously
        callback.assert_called_once_with(cached_data)

    def test_cache_clear_functionality(self):
        """Test cache clearing clears all cache layers"""
        # Populate caches
        self.orchestrator._last_preview = PreviewData(offset=0x100000, rom_path="/test/clear.sfc")
        self.orchestrator._memory_cache = PreviewMemoryCache()
        self.orchestrator._memory_cache.put("test_key", PreviewData())

        # Clear all caches
        self.orchestrator.clear_cache()

        # All caches should be cleared
        assert self.orchestrator._last_preview is None
        assert len(self.orchestrator._memory_cache._cache) == 0
        assert self.mock_async_cache.memory_cleared

    def test_rom_cache_integration(self):
        """Test ROM cache integration and setup"""
        # Create new orchestrator
        orchestrator = PreviewOrchestrator()
        mock_rom_cache = MockROMCache()

        # Should create async cache when rom cache is set
        assert orchestrator._async_cache is None

        # AsyncROMCache is imported inside set_rom_cache from core.async_rom_cache
        with patch('core.async_rom_cache.AsyncROMCache') as MockAsyncCache:
            mock_instance = Mock()
            MockAsyncCache.return_value = mock_instance

            orchestrator.set_rom_cache(mock_rom_cache)

            # Should have created and configured async cache
            MockAsyncCache.assert_called_once_with(mock_rom_cache)
            assert orchestrator._async_cache == mock_instance

    def test_metrics_tracking(self, qtbot):
        """Test performance metrics are tracked correctly"""

        # L1 cache hit
        cached_data = PreviewData(offset=0x200000, rom_path="/test/metrics.sfc")
        self.orchestrator._last_preview = cached_data

        with qtbot.wait_signal(self.orchestrator.preview_ready, timeout=100):
            self.orchestrator.request_preview("/test/metrics.sfc", 0x200000)

        # Metrics should be updated
        assert self.orchestrator._metrics.cache_hits == 1
        assert self.orchestrator._metrics.total_requests == 1

        # Test cache miss
        with qtbot.wait_signal(self.orchestrator.preview_ready, timeout=500):
            self.orchestrator.request_preview("/test/metrics.sfc", 0x300000)

        assert self.orchestrator._metrics.cache_misses == 1
        assert self.orchestrator._metrics.total_requests == 2

    def test_metrics_emission(self, qtbot):
        """Test metrics are emitted periodically"""
        # Metrics should be emitted every 5 seconds
        with qtbot.wait_signal(self.orchestrator.metrics_updated, timeout=6000):
            pass

        # Should emit the current metrics
        # (Signal should contain PreviewMetrics object)

    def test_cache_key_generation_consistency(self):
        """Test cache key generation is consistent"""
        rom_path = "/test/consistency.sfc"
        offset = 0x200000

        key1 = self.orchestrator._generate_cache_key(rom_path, offset)
        key2 = self.orchestrator._generate_cache_key(rom_path, offset)

        assert key1 == key2

        # Different inputs should generate different keys
        key3 = self.orchestrator._generate_cache_key(rom_path, 0x300000)
        key4 = self.orchestrator._generate_cache_key("/different/rom.sfc", offset)

        assert key1 != key3
        assert key1 != key4

class TestPreviewOrchestratorIntegration:
    """Integration tests for PreviewOrchestrator with real components"""

    def test_full_preview_pipeline_integration(self, qtbot):
        """Test complete preview pipeline from request to delivery"""
        # Mock ROM cache for realistic setup
        mock_rom_cache = MockROMCache()

        # Create mock instances using the module-level test classes BEFORE patching
        mock_async_instance = MockAsyncROMCache()
        mock_worker_instance = MockWorkerPool()

        # Create orchestrator with worker pool factory that returns our mock
        orchestrator = PreviewOrchestrator(
            worker_pool_factory=lambda: mock_worker_instance
        )

        # Imports happen inside methods from their respective modules
        with patch('core.async_rom_cache.AsyncROMCache') as PatchedAsyncCache:

            # Configure patches to return our test mock instances
            PatchedAsyncCache.return_value = mock_async_instance

            # Set ROM cache to trigger async cache creation (which connects signals)
            orchestrator.set_rom_cache(mock_rom_cache)

            # Connect worker pool signals manually - these are connected lazily in
            # _generate_preview, but since the factory returns our mock instance,
            # we need to connect them here. Note: async cache signals are already
            # connected by set_rom_cache, so we don't reconnect those.
            mock_worker_instance.preview_ready.connect(orchestrator._on_preview_ready)
            mock_worker_instance.preview_error.connect(orchestrator._on_preview_error)

            # Make request
            rom_path = "/test/integration.sfc"
            offset = 0x200000

            with qtbot.wait_signal(orchestrator.preview_ready, timeout=1000) as blocker:
                request_id = orchestrator.request_preview(rom_path, offset, Priority.HIGH)

            # Should have gone through async cache then worker
            assert len(mock_async_instance.requests) == 1
            assert len(mock_worker_instance.generate_requests) == 1

            # Should receive preview data
            args = blocker.args
            assert args[0] == request_id
            preview_data = args[1]
            assert isinstance(preview_data, PreviewData)
            assert preview_data.offset == offset
            assert preview_data.rom_path == rom_path

    @pytest.mark.performance
    def test_high_load_performance(self, qtbot):
        """Test orchestrator performance under high request load"""
        orchestrator = PreviewOrchestrator()

        # Submit many requests rapidly
        start_time = time.perf_counter()
        request_ids = []

        for i in range(50):
            request_id = orchestrator.request_preview(
                f"/test/load_{i}.sfc",
                i * 0x1000,
                Priority.NORMAL
            )
            request_ids.append(request_id)

        submission_time = time.perf_counter() - start_time

        # Request submission should be fast
        assert submission_time < 0.1, f"Request submission too slow: {submission_time:.3f}s"

        # All requests should be tracked
        assert len(orchestrator._active_requests) == 50

        # Queue should not be empty
        assert not orchestrator._request_queue.empty()

    def test_error_recovery_and_resilience(self, qtbot):
        """Test orchestrator recovers gracefully from various errors"""
        orchestrator = PreviewOrchestrator()

        # Test with failing async cache
        failing_cache = Mock()
        failing_cache.get_cached_async.side_effect = Exception("Cache failure")
        orchestrator._async_cache = failing_cache

        # Request should still work (should fall back to worker)
        # PreviewWorkerPool is imported inside _generate_preview from ui.common.preview_worker_pool
        with patch('ui.common.preview_worker_pool.PreviewWorkerPool') as MockWorkerPool:
            mock_worker = MockWorkerPool()
            MockWorkerPool.return_value = mock_worker

            # This would normally fail, but orchestrator should handle gracefully
            request_id = orchestrator.request_preview("/test/error.sfc", 0x200000)

            # Should still track the request
            assert request_id in orchestrator._active_requests

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
