"""
Performance tests for sprite display fix - Caching improvements and response time benchmarks

Tests focus on:
1. Cache hit/miss performance comparisons
2. Response time benchmarks for real-time scrubbing
3. Memory usage patterns under load
4. Throughput testing with concurrent requests
5. Degradation testing with large datasets
6. Cache efficiency measurements
7. Worker pool performance validation
8. End-to-end pipeline performance
"""
from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import psutil
import pytest

# Skip entire module if pytest-benchmark is not installed
pytest.importorskip("pytest_benchmark")

from core.async_rom_cache import AsyncROMCache
from core.preview_orchestrator import PreviewOrchestrator, Priority
from tests.infrastructure.qt_testing_framework import QtTestingFramework
from ui.common.smart_preview_coordinator import SmartPreviewCoordinator
from ui.widgets.sprite_preview_widget import SpritePreviewWidget

# Serial execution required: Thread safety concerns, Real Qt components
pytestmark = [

    pytest.mark.serial,
    pytest.mark.thread_safety,
    pytest.mark.cache,
    pytest.mark.ci_safe,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.qt_real,
    pytest.mark.rom_data,
    pytest.mark.slow,
    pytest.mark.worker_threads,
]

class PerformanceTestData:
    """Generate consistent test data for performance benchmarks"""

    @staticmethod
    def generate_sprite_data(width: int, height: int, pattern: str = "gradient") -> bytes:
        """Generate test sprite data with specific patterns"""
        total_pixels = width * height
        total_bytes = (total_pixels + 1) // 2  # 4bpp format

        data = bytearray()

        if pattern == "gradient":
            for i in range(total_bytes):
                pixel1 = (i * 2) % 16
                pixel2 = (i * 2 + 1) % 16
                data.append((pixel1 << 4) | pixel2)
        elif pattern == "checkerboard":
            for i in range(total_bytes):
                pixel1 = (i % 2) * 15
                pixel2 = ((i + 1) % 2) * 15
                data.append((pixel1 << 4) | pixel2)
        else:  # random-like
            for i in range(total_bytes):
                data.append((i * 17 + 23) % 256)

        return bytes(data)

    @staticmethod
    def generate_test_dataset(num_sprites: int = 100) -> list[dict]:
        """Generate dataset of test sprites"""
        sprites = []
        for i in range(num_sprites):
            offset = 0x200000 + (i * 0x1000)
            width = 16 if i % 3 == 0 else 32 if i % 3 == 1 else 64
            height = width  # Square sprites for consistency
            data = PerformanceTestData.generate_sprite_data(width, height)

            sprites.append({
                "offset": offset,
                "width": width,
                "height": height,
                "data": data,
                "size": len(data),
                "name": f"perf_sprite_{i:03d}"
            })

        return sprites

class TestAsyncROMCachePerformance:
    """Performance tests for AsyncROMCache"""

    def setup_method(self):
        """Set up performance test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.mock_rom_cache = Mock()
        self.mock_rom_cache.cache_dir = str(self.temp_dir)
        self.async_cache = AsyncROMCache(self.mock_rom_cache)

        # Generate test data
        self.test_sprites = PerformanceTestData.generate_test_dataset(50)

    def teardown_method(self):
        """Clean up performance test environment"""
        if hasattr(self, 'async_cache'):
            del self.async_cache
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.performance
    def test_memory_cache_hit_performance(self, benchmark):
        """Benchmark memory cache hit performance for real-time scrubbing"""
        # Pre-populate memory cache
        rom_path = "/test/benchmark.sfc"
        sprite = self.test_sprites[0]

        cache_key = self.async_cache._generate_cache_key(rom_path, sprite["offset"])
        with self.async_cache._request_mutex:
            self.async_cache._memory_cache[cache_key] = (
                sprite["data"],
                {"width": sprite["width"], "height": sprite["height"]},
                time.time()
            )

        # Benchmark memory cache lookup
        def memory_lookup():
            with self.async_cache._request_mutex:
                return self.async_cache._memory_cache.get(cache_key)

        result = benchmark(memory_lookup)

        assert result is not None
        assert result[0] == sprite["data"]

        # Memory cache hits should be extremely fast (< 1ms for 60fps scrubbing)
        assert benchmark.stats.mean < 0.001  # < 1ms average

    @pytest.mark.performance
    def test_concurrent_cache_access_performance(self, qtbot):
        """Test performance under concurrent cache access"""
        rom_path = "/test/concurrent.sfc"
        num_threads = 8
        requests_per_thread = 25

        # Pre-populate some cache entries
        for i in range(10):
            sprite = self.test_sprites[i]
            self.async_cache.save_cached_async(
                rom_path, sprite["offset"], sprite["data"],
                {"width": sprite["width"], "height": sprite["height"]}
            )

        time.sleep(1.0)  # sleep-ok: benchmark cooldown

        # Measure concurrent access performance
        start_time = time.perf_counter()

        def worker_thread(thread_id):
            results = []
            for i in range(requests_per_thread):
                sprite_idx = (thread_id * requests_per_thread + i) % len(self.test_sprites)
                sprite = self.test_sprites[sprite_idx]
                request_id = f"thread_{thread_id}_req_{i}"

                # Mix of cache hits and misses
                self.async_cache.get_cached_async(rom_path, sprite["offset"], request_id)
                results.append(request_id)
            return results

        # Execute concurrent requests
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_thread, i) for i in range(num_threads)]
            [future.result() for future in futures]

        total_time = time.perf_counter() - start_time
        total_requests = num_threads * requests_per_thread

        # Performance assertions
        avg_response_time = total_time / total_requests
        assert avg_response_time < 0.01  # < 10ms average per request
        assert total_time < 5.0  # Complete all requests in < 5 seconds

        print(f"Concurrent performance: {total_requests} requests in {total_time:.2f}s")
        print(f"Average response time: {avg_response_time*1000:.2f}ms")

    @pytest.mark.performance
    def test_cache_efficiency_under_realistic_usage(self):
        """Test cache efficiency with realistic usage patterns"""
        rom_path = "/test/realistic.sfc"

        # Simulate realistic browsing: user explores ROM with some backtracking
        access_pattern = []
        base_offsets = [sprite["offset"] for sprite in self.test_sprites[:20]]

        # Forward exploration
        access_pattern.extend(base_offsets)

        # Backtracking (should hit cache)
        access_pattern.extend(reversed(base_offsets[10:15]))

        # Random jumps (mix of hits and misses)
        import random
        random.seed(42)  # Reproducible test
        access_pattern.extend(random.choices(base_offsets, k=30))

        cache_hits = 0
        cache_misses = 0
        response_times = []

        for offset in access_pattern:
            start_time = time.perf_counter()

            # Check memory cache directly for timing
            cache_key = self.async_cache._generate_cache_key(rom_path, offset)
            with self.async_cache._request_mutex:
                if cache_key in self.async_cache._memory_cache:
                    cache_hits += 1
                else:
                    cache_misses += 1
                    # Simulate cache miss by adding to cache
                    sprite_data = b"mock_data"
                    self.async_cache._memory_cache[cache_key] = (
                        sprite_data, {}, time.time()
                    )

            response_time = time.perf_counter() - start_time
            response_times.append(response_time)

        # Calculate metrics
        hit_rate = cache_hits / len(access_pattern) * 100
        avg_response_time = sum(response_times) / len(response_times)
        p99_response_time = sorted(response_times)[int(len(response_times) * 0.99)]

        # Performance assertions
        assert hit_rate > 30, f"Cache hit rate too low: {hit_rate:.1f}%"
        assert avg_response_time < 0.001, f"Average response too slow: {avg_response_time*1000:.2f}ms"
        assert p99_response_time < 0.005, f"P99 response too slow: {p99_response_time*1000:.2f}ms"

        print(f"Cache efficiency: {hit_rate:.1f}% hit rate")
        print(f"Response times: avg={avg_response_time*1000:.2f}ms, p99={p99_response_time*1000:.2f}ms")

    @pytest.mark.performance
    def test_memory_usage_scaling(self):
        """Test memory usage scales appropriately with cache size"""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        rom_path = "/test/memory_scaling.sfc"

        # Add many cache entries
        for i, sprite in enumerate(self.test_sprites):
            self.async_cache.save_cached_async(
                rom_path, sprite["offset"], sprite["data"],
                {"width": sprite["width"], "height": sprite["height"]}
            )

            # Check memory every 10 entries
            if i % 10 == 0:
                current_memory = process.memory_info().rss
                memory_growth = current_memory - initial_memory

                # Memory growth should be reasonable
                max_allowed_growth = (i + 1) * 0.1 * 1024 * 1024  # ~100KB per sprite
                assert memory_growth < max_allowed_growth, \
                    f"Excessive memory growth: {memory_growth/1024/1024:.1f}MB after {i+1} sprites"

        final_memory = process.memory_info().rss
        total_growth = final_memory - initial_memory

        print(f"Memory scaling: {total_growth/1024/1024:.1f}MB for {len(self.test_sprites)} sprites")

        # Should not exceed reasonable bounds
        assert total_growth < 50 * 1024 * 1024, f"Total memory growth too high: {total_growth/1024/1024:.1f}MB"

class TestPreviewOrchestratorPerformance:
    """Performance tests for PreviewOrchestrator"""

    @pytest.fixture(autouse=True)
    def setup_orchestrator(self, tmp_path):
        """Set up orchestrator performance tests"""
        self.orchestrator = PreviewOrchestrator()
        self.test_sprites = PerformanceTestData.generate_test_dataset(100)

        # Mock ROM cache for testing
        mock_rom_cache = Mock()
        mock_rom_cache.cache_dir = str(tmp_path / "test_cache")
        self.orchestrator.set_rom_cache(mock_rom_cache)

        yield

        # Cleanup
        if hasattr(self, "orchestrator"):
            del self.orchestrator

    @pytest.mark.performance
    def test_request_throughput_performance(self, qtbot):
        """Test request throughput under high load"""
        rom_path = "/test/throughput.sfc"
        num_requests = 100

        # Submit many requests rapidly
        start_time = time.perf_counter()
        request_ids = []

        for i in range(num_requests):
            sprite = self.test_sprites[i % len(self.test_sprites)]
            priority = Priority.HIGH if i % 10 == 0 else Priority.NORMAL

            request_id = self.orchestrator.request_preview(
                rom_path, sprite["offset"], priority
            )
            request_ids.append(request_id)

        submission_time = time.perf_counter() - start_time

        # Request submission should be very fast
        assert submission_time < 1.0, f"Request submission too slow: {submission_time:.3f}s"
        assert len(request_ids) == num_requests

        # Requests should be queued efficiently
        queue_size = self.orchestrator._request_queue.qsize()
        assert queue_size > 0, "Requests should be queued"

        print(f"Throughput: {num_requests} requests submitted in {submission_time*1000:.1f}ms")

    @pytest.mark.performance
    def test_priority_queue_performance(self):
        """Test priority queue performance with mixed priority requests"""
        rom_path = "/test/priority.sfc"

        # Submit requests with different priorities
        priorities = [Priority.LOW, Priority.NORMAL, Priority.HIGH, Priority.URGENT]
        num_requests_per_priority = 25

        start_time = time.perf_counter()

        for priority in priorities:
            for i in range(num_requests_per_priority):
                sprite = self.test_sprites[i % len(self.test_sprites)]
                self.orchestrator.request_preview(
                    rom_path, sprite["offset"], priority
                )

        queue_time = time.perf_counter() - start_time

        # Should handle priority queuing efficiently
        total_requests = len(priorities) * num_requests_per_priority
        assert queue_time < 0.5, f"Priority queuing too slow: {queue_time:.3f}s for {total_requests} requests"

        # Verify queue ordering (highest priority first)
        priorities_seen = []
        while not self.orchestrator._request_queue.empty():
            try:
                request = self.orchestrator._request_queue.get_nowait()
                priorities_seen.append(request.priority.value)
            except Exception:
                break

        # Should be sorted by priority (lower values = higher priority)
        assert priorities_seen == sorted(priorities_seen), "Requests not properly prioritized"

    @pytest.mark.performance
    def test_cache_layer_performance_comparison(self, qtbot):
        """Test performance comparison between cache layers"""
        rom_path = "/test/cache_layers.sfc"
        sprite = self.test_sprites[0]

        # Test L1 cache (last preview) performance
        cached_data = Mock()
        cached_data.offset = sprite["offset"]
        self.orchestrator._last_preview = cached_data

        l1_start = time.perf_counter()
        with qtbot.wait_signal(self.orchestrator.preview_ready, timeout=100):
            self.orchestrator.request_preview(rom_path, sprite["offset"])
        l1_time = time.perf_counter() - l1_start

        # L1 cache should be extremely fast
        assert l1_time < 0.01, f"L1 cache too slow: {l1_time*1000:.1f}ms"

        # Test cache miss performance (would go to worker)
        self.orchestrator._last_preview = None
        if self.orchestrator._memory_cache:
            self.orchestrator._memory_cache.clear()

        miss_start = time.perf_counter()
        self.orchestrator.request_preview(
            rom_path, sprite["offset"] + 0x1000
        )

        # Should queue quickly even for cache miss
        queue_time = time.perf_counter() - miss_start
        assert queue_time < 0.01, f"Cache miss queuing too slow: {queue_time*1000:.1f}ms"

        print(f"Cache performance: L1 hit={l1_time*1000:.2f}ms, miss queue={queue_time*1000:.2f}ms")

    @pytest.mark.performance
    def test_concurrent_request_handling_performance(self):
        """Test performance with concurrent requests from multiple threads"""
        rom_path = "/test/concurrent_orchestrator.sfc"
        num_threads = 4
        requests_per_thread = 25

        def worker_thread(thread_id):
            request_times = []
            for i in range(requests_per_thread):
                sprite = self.test_sprites[(thread_id * requests_per_thread + i) % len(self.test_sprites)]

                start_time = time.perf_counter()
                self.orchestrator.request_preview(
                    rom_path, sprite["offset"], Priority.NORMAL
                )
                request_time = time.perf_counter() - start_time

                request_times.append(request_time)

                # Small delay to simulate realistic usage
                time.sleep(0.001)  # sleep-ok: benchmark timing

            return request_times

        # Execute concurrent requests
        overall_start = time.perf_counter()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_thread, i) for i in range(num_threads)]
            thread_results = [future.result() for future in futures]

        total_time = time.perf_counter() - overall_start

        # Analyze results
        all_request_times = [t for thread_times in thread_results for t in thread_times]
        avg_request_time = sum(all_request_times) / len(all_request_times)
        max_request_time = max(all_request_times)

        total_requests = num_threads * requests_per_thread

        # Performance assertions
        assert avg_request_time < 0.005, f"Average request time too slow: {avg_request_time*1000:.2f}ms"
        assert max_request_time < 0.02, f"Worst request time too slow: {max_request_time*1000:.2f}ms"
        assert total_time < 10.0, f"Total time too long: {total_time:.2f}s"

        print(f"Concurrent orchestrator: {total_requests} requests, avg={avg_request_time*1000:.2f}ms")

class TestSmartPreviewCoordinatorPerformance:
    """Performance tests for SmartPreviewCoordinator"""

    def setup_method(self):
        """Set up coordinator performance tests"""
        self.qt_framework = QtTestingFramework()
        self.coordinator = SmartPreviewCoordinator()
        self.test_sprites = PerformanceTestData.generate_test_dataset(50)

    def teardown_method(self):
        """Clean up coordinator tests"""
        if hasattr(self, 'coordinator'):
            self.coordinator.cleanup()
            del self.coordinator

    @pytest.mark.performance
    def test_high_frequency_slider_updates_performance(self):
        """Test performance during rapid slider movement (60fps simulation)"""
        rom_path = "/test/high_frequency.sfc"

        # Simulate 60 FPS updates for 1 second
        num_updates = 60
        update_interval = 1.0 / 60  # 16.67ms between updates

        response_times = []
        start_time = time.perf_counter()

        for i in range(num_updates):
            sprite = self.test_sprites[i % len(self.test_sprites)]

            update_start = time.perf_counter()
            self.coordinator.request_preview(rom_path, sprite["offset"])
            update_time = time.perf_counter() - update_start

            response_times.append(update_time)

            # Simulate real-time timing
            time.sleep(max(0, update_interval - update_time))  # sleep-ok: benchmark timing

        total_time = time.perf_counter() - start_time
        avg_response = sum(response_times) / len(response_times)
        max_response = max(response_times)

        # Performance requirements for smooth 60fps
        assert avg_response < 0.002, f"Average response too slow for 60fps: {avg_response*1000:.2f}ms"
        assert max_response < 0.005, f"Max response too slow for 60fps: {max_response*1000:.2f}ms"
        assert total_time < 2.0, f"Total time too long: {total_time:.2f}s"

        print(f"60fps simulation: avg={avg_response*1000:.2f}ms, max={max_response*1000:.2f}ms")

    @pytest.mark.performance
    def test_debouncing_effectiveness_performance(self):
        """Test debouncing effectiveness under rapid updates"""
        rom_path = "/test/debouncing.sfc"

        # Submit rapid updates that should be debounced
        num_rapid_updates = 100
        debounce_window = 0.05  # 50ms debounce window

        start_time = time.perf_counter()
        request_ids = []

        for i in range(num_rapid_updates):
            sprite = self.test_sprites[i % 10]  # Cycle through 10 offsets
            request_id = self.coordinator.request_preview(rom_path, sprite["offset"])
            request_ids.append(request_id)

            # Rapid updates (5ms apart - should trigger debouncing)
            time.sleep(0.005)  # sleep-ok: benchmark timing

        submission_time = time.perf_counter() - start_time

        # Wait for debouncing to settle
        time.sleep(debounce_window * 2)  # sleep-ok: benchmark timing

        # Should handle rapid updates efficiently due to debouncing
        assert submission_time < 1.0, f"Rapid update submission too slow: {submission_time:.3f}s"

        # Check performance metrics (if available)
        if hasattr(self.coordinator, '_performance_metrics'):
            metrics = self.coordinator._performance_metrics
            total_requests = metrics.get("total_requests", 0)

            # Should have fewer actual preview generations than input requests
            debounce_ratio = total_requests / num_rapid_updates if total_requests > 0 else 1
            assert debounce_ratio < 0.5, f"Debouncing not effective: {debounce_ratio*100:.1f}% requests processed"

            print(f"Debouncing effectiveness: {debounce_ratio*100:.1f}% of rapid updates processed")

    @pytest.mark.performance
    def test_cache_hit_rate_optimization(self):
        """Test cache hit rate optimization with realistic browsing patterns"""
        rom_path = "/test/cache_optimization.sfc"

        # Simulate realistic user behavior: forward browsing with some backtracking
        browsing_pattern = []

        # Forward exploration
        base_sprites = self.test_sprites[:20]
        browsing_pattern.extend([sprite["offset"] for sprite in base_sprites])

        # Backtracking (should generate cache hits)
        browsing_pattern.extend([sprite["offset"] for sprite in reversed(base_sprites[10:15])])

        # Return to previously seen areas (more cache hits)
        browsing_pattern.extend([base_sprites[5]["offset"], base_sprites[12]["offset"]])

        cache_operations = {"hits": 0, "misses": 0}
        response_times = []

        for offset in browsing_pattern:
            start_time = time.perf_counter()

            # Mock cache check
            if hasattr(self.coordinator, '_memory_cache'):
                cache_key = f"preview_{hash(rom_path)}_{offset:08x}"
                if self.coordinator._memory_cache and hasattr(self.coordinator._memory_cache, 'get'):
                    if self.coordinator._memory_cache.get(cache_key):
                        cache_operations["hits"] += 1
                    else:
                        cache_operations["misses"] += 1
                        # Simulate adding to cache
                        if hasattr(self.coordinator._memory_cache, 'put'):
                            self.coordinator._memory_cache.put(cache_key, b"mock_data")

            # Request preview
            self.coordinator.request_preview(rom_path, offset)

            response_time = time.perf_counter() - start_time
            response_times.append(response_time)

        # Calculate performance metrics
        total_operations = cache_operations["hits"] + cache_operations["misses"]
        hit_rate = cache_operations["hits"] / total_operations * 100 if total_operations > 0 else 0
        avg_response_time = sum(response_times) / len(response_times)

        # With backtracking, should achieve decent hit rate
        expected_hit_rate = 25  # At least 25% with backtracking pattern
        assert hit_rate >= expected_hit_rate, f"Cache hit rate too low: {hit_rate:.1f}%"
        assert avg_response_time < 0.01, f"Average response too slow: {avg_response_time*1000:.2f}ms"

        print(f"Cache optimization: {hit_rate:.1f}% hit rate, avg={avg_response_time*1000:.2f}ms")

class TestEndToEndPerformance:
    """End-to-end performance tests for the complete sprite display pipeline"""

    def setup_method(self):
        """Set up end-to-end performance tests"""
        self.qt_framework = QtTestingFramework()
        self.test_sprites = PerformanceTestData.generate_test_dataset(30)

        # Create complete pipeline components
        self.preview_widget = SpritePreviewWidget("E2E Performance")
        self.coordinator = SmartPreviewCoordinator()

        # Mock ROM cache
        self.temp_dir = Path(tempfile.mkdtemp())
        mock_rom_cache = Mock()
        mock_rom_cache.cache_dir = str(self.temp_dir)

        self.async_cache = AsyncROMCache(mock_rom_cache)

    def teardown_method(self):
        """Clean up end-to-end tests"""
        if hasattr(self, 'preview_widget'):
            self.preview_widget.close()
        if hasattr(self, 'coordinator'):
            self.coordinator.cleanup()
        if hasattr(self, 'async_cache'):
            del self.async_cache

        # Clean up temp directory
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.performance
    def test_complete_pipeline_performance(self, qtbot):
        """Test complete pipeline from slider movement to widget display"""
        rom_path = "/test/e2e_pipeline.sfc"

        # Simulate complete user workflow with timing
        workflow_times = {
            "cache_lookup": [],
            "preview_generation": [],
            "widget_update": [],
            "total_pipeline": []
        }

        for sprite in self.test_sprites[:10]:  # Test with 10 sprites
            pipeline_start = time.perf_counter()

            # 1. Cache lookup phase
            cache_start = time.perf_counter()
            request_id = f"e2e_{sprite['offset']:08x}"
            self.async_cache.get_cached_async(rom_path, sprite["offset"], request_id)
            cache_time = time.perf_counter() - cache_start
            workflow_times["cache_lookup"].append(cache_time)

            # 2. Preview generation phase (simulate)
            gen_start = time.perf_counter()
            # Simulate preview generation work
            tile_data = sprite["data"]
            gen_time = time.perf_counter() - gen_start
            workflow_times["preview_generation"].append(gen_time)

            # 3. Widget update phase
            update_start = time.perf_counter()
            self.preview_widget.load_sprite_from_4bpp(
                tile_data, sprite["width"], sprite["height"], sprite["name"]
            )
            update_time = time.perf_counter() - update_start
            workflow_times["widget_update"].append(update_time)

            # Total pipeline time
            total_time = time.perf_counter() - pipeline_start
            workflow_times["total_pipeline"].append(total_time)

        # Analyze performance across pipeline stages
        for stage, times in workflow_times.items():
            avg_time = sum(times) / len(times)
            max_time = max(times)

            print(f"{stage}: avg={avg_time*1000:.2f}ms, max={max_time*1000:.2f}ms")

            # Performance requirements for smooth user experience
            if stage == "cache_lookup":
                assert avg_time < 0.01, f"{stage} too slow: {avg_time*1000:.2f}ms"
            elif stage == "widget_update":
                assert avg_time < 0.05, f"{stage} too slow: {avg_time*1000:.2f}ms"
            elif stage == "total_pipeline":
                assert avg_time < 0.1, f"{stage} too slow: {avg_time*1000:.2f}ms"

    @pytest.mark.performance
    def test_sustained_performance_under_load(self):
        """Test sustained performance over extended usage"""
        rom_path = "/test/sustained_load.sfc"

        # Simulate 5-minute browsing session
        num_iterations = 100  # Reduced for test speed
        performance_samples = []
        memory_samples = []

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        for iteration in range(num_iterations):
            iteration_start = time.perf_counter()

            # Simulate user actions: browsing, backtracking, searching
            sprite = self.test_sprites[iteration % len(self.test_sprites)]

            # Cache operation
            self.async_cache.save_cached_async(
                rom_path, sprite["offset"], sprite["data"],
                {"width": sprite["width"], "height": sprite["height"]}
            )

            # Widget update
            self.preview_widget.load_sprite_from_4bpp(
                sprite["data"], sprite["width"], sprite["height"], sprite["name"]
            )

            iteration_time = time.perf_counter() - iteration_start
            performance_samples.append(iteration_time)

            # Monitor memory usage every 10 iterations
            if iteration % 10 == 0:
                current_memory = process.memory_info().rss
                memory_growth = current_memory - initial_memory
                memory_samples.append(memory_growth)

        # Analyze sustained performance
        avg_iteration_time = sum(performance_samples) / len(performance_samples)
        performance_degradation = performance_samples[-10:] # Last 10 iterations
        avg_final_performance = sum(performance_degradation) / len(performance_degradation)

        # Memory growth analysis
        final_memory_growth = memory_samples[-1] if memory_samples else 0

        # Performance should remain consistent (no significant degradation)
        degradation_ratio = avg_final_performance / avg_iteration_time
        assert degradation_ratio < 1.5, f"Performance degraded significantly: {degradation_ratio:.2f}x slower"

        # Memory growth should be bounded
        max_allowed_memory_growth = 100 * 1024 * 1024  # 100MB
        assert final_memory_growth < max_allowed_memory_growth, \
            f"Excessive memory growth: {final_memory_growth/1024/1024:.1f}MB"

        print(f"Sustained performance: avg={avg_iteration_time*1000:.2f}ms, "
              f"degradation={degradation_ratio:.2f}x, memory={final_memory_growth/1024/1024:.1f}MB")

    @pytest.mark.performance
    def test_real_time_scrubbing_simulation(self, qtbot):
        """Test real-time scrubbing simulation with performance targets"""

        # Simulate user dragging slider at 30fps for 2 seconds
        fps = 30
        duration_seconds = 2
        total_frames = fps * duration_seconds
        frame_time = 1.0 / fps

        frame_times = []
        dropped_frames = 0

        start_time = time.perf_counter()

        for frame in range(total_frames):
            frame_start = time.perf_counter()

            # Simulate slider position change
            sprite_idx = frame % len(self.test_sprites)
            sprite = self.test_sprites[sprite_idx]

            # Complete update cycle
            self.preview_widget.load_sprite_from_4bpp(
                sprite["data"], sprite["width"], sprite["height"], sprite["name"]
            )

            frame_end = time.perf_counter()
            frame_duration = frame_end - frame_start
            frame_times.append(frame_duration)

            # Check if frame budget exceeded
            if frame_duration > frame_time:
                dropped_frames += 1

            # Wait for next frame (if not behind schedule)
            elapsed_since_start = frame_end - start_time
            target_time = (frame + 1) * frame_time
            sleep_time = max(0, target_time - elapsed_since_start)

            if sleep_time > 0:
                time.sleep(sleep_time)  # sleep-ok: benchmark timing

        time.perf_counter() - start_time

        # Analyze scrubbing performance
        avg_frame_time = sum(frame_times) / len(frame_times)
        max_frame_time = max(frame_times)
        frame_drop_rate = dropped_frames / total_frames * 100

        # Performance requirements for smooth scrubbing
        assert avg_frame_time < frame_time, f"Average frame time too slow: {avg_frame_time*1000:.2f}ms"
        assert frame_drop_rate < 10, f"Too many dropped frames: {frame_drop_rate:.1f}%"
        assert max_frame_time < frame_time * 2, f"Worst frame too slow: {max_frame_time*1000:.2f}ms"

        print(f"Scrubbing simulation: {fps}fps, {frame_drop_rate:.1f}% drops, "
              f"avg={avg_frame_time*1000:.2f}ms, max={max_frame_time*1000:.2f}ms")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "performance"])
