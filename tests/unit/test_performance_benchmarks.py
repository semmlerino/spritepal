"""
Performance tests for sprite display - SmartPreviewCoordinator benchmarks.

Tests focus on:
1. Cache hit/miss performance comparisons
2. Response time benchmarks for real-time scrubbing
3. Debouncing effectiveness
4. Cache efficiency measurements
"""

from __future__ import annotations

import time

import pytest

# Skip entire module if pytest-benchmark is not installed
pytest.importorskip("pytest_benchmark")

from tests.fixtures.timeouts import perf_bound
from ui.common.smart_preview_coordinator import SmartPreviewCoordinator

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.performance,
]


class PerformanceTestData:
    """Generate consistent test data for performance benchmarks."""

    @staticmethod
    def generate_sprite_data(width: int, height: int, pattern: str = "gradient") -> bytes:
        """Generate test sprite data with specific patterns."""
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
        """Generate dataset of test sprites."""
        sprites = []
        for i in range(num_sprites):
            offset = 0x200000 + (i * 0x1000)
            width = 16 if i % 3 == 0 else 32 if i % 3 == 1 else 64
            height = width  # Square sprites for consistency
            data = PerformanceTestData.generate_sprite_data(width, height)

            sprites.append(
                {
                    "offset": offset,
                    "width": width,
                    "height": height,
                    "data": data,
                    "size": len(data),
                    "name": f"perf_sprite_{i:03d}",
                }
            )

        return sprites


class TestSmartPreviewCoordinatorPerformance:
    """Performance tests for SmartPreviewCoordinator."""

    def setup_method(self) -> None:
        """Set up coordinator performance tests."""
        self.coordinator = SmartPreviewCoordinator()
        self.test_sprites = PerformanceTestData.generate_test_dataset(50)

    def teardown_method(self) -> None:
        """Clean up coordinator tests."""
        if hasattr(self, "coordinator"):
            self.coordinator.cleanup()
            del self.coordinator

    @pytest.mark.performance
    def test_high_frequency_slider_updates_performance(self) -> None:
        """Test performance during rapid slider movement (60fps simulation)."""
        # Simulate 60 FPS updates for 1 second
        num_updates = 60
        update_interval = 1.0 / 60  # 16.67ms between updates

        response_times = []
        start_time = time.perf_counter()

        for i in range(num_updates):
            sprite = self.test_sprites[i % len(self.test_sprites)]

            update_start = time.perf_counter()
            self.coordinator.request_preview(sprite["offset"])
            update_time = time.perf_counter() - update_start

            response_times.append(update_time)

            # Simulate real-time timing
            time.sleep(max(0, update_interval - update_time))  # sleep-ok: benchmark timing

        total_time = time.perf_counter() - start_time
        avg_response = sum(response_times) / len(response_times)
        max_response = max(response_times)

        # Sanity bounds: loose enough for CI, catches major regressions
        assert avg_response < perf_bound(0.01), f"Average response too slow: {avg_response * 1000:.2f}ms"
        assert max_response < perf_bound(0.02), f"Max response too slow: {max_response * 1000:.2f}ms"
        assert total_time < perf_bound(2.0), f"Total time too long: {total_time:.2f}s"

        print(f"60fps simulation: avg={avg_response * 1000:.2f}ms, max={max_response * 1000:.2f}ms")

    @pytest.mark.performance
    def test_debouncing_effectiveness_performance(self) -> None:
        """Test debouncing effectiveness under rapid updates."""
        # Submit rapid updates that should be debounced
        num_rapid_updates = 100
        debounce_window = 0.05  # 50ms debounce window

        start_time = time.perf_counter()
        request_ids = []

        for i in range(num_rapid_updates):
            sprite = self.test_sprites[i % 10]  # Cycle through 10 offsets
            request_id = self.coordinator.request_preview(sprite["offset"])
            request_ids.append(request_id)

            # Rapid updates (5ms apart - should trigger debouncing)
            time.sleep(0.005)  # sleep-ok: benchmark timing

        submission_time = time.perf_counter() - start_time

        # Wait for debouncing to settle
        time.sleep(debounce_window * 2)  # sleep-ok: benchmark timing

        # Should handle rapid updates efficiently due to debouncing
        assert submission_time < perf_bound(1.0), f"Rapid update submission too slow: {submission_time:.3f}s"

        # Check performance metrics (if available)
        if hasattr(self.coordinator, "_performance_metrics"):
            metrics = self.coordinator._performance_metrics
            total_requests = metrics.get("total_requests", 0)

            # Should have fewer actual preview generations than input requests
            debounce_ratio = total_requests / num_rapid_updates if total_requests > 0 else 1
            assert debounce_ratio < 0.5, f"Debouncing not effective: {debounce_ratio * 100:.1f}% requests processed"

            print(f"Debouncing effectiveness: {debounce_ratio * 100:.1f}% of rapid updates processed")

    @pytest.mark.performance
    def test_cache_hit_rate_optimization(self) -> None:
        """Test cache hit rate optimization with realistic browsing patterns."""
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

            # Mock cache check using current PreviewCache interface
            if hasattr(self.coordinator, "_cache"):
                cache_key = self.coordinator._cache.make_key(rom_path, offset)
                if cache_key in self.coordinator._cache:
                    cache_operations["hits"] += 1
                else:
                    cache_operations["misses"] += 1
                    # Simulate adding to cache - needs 8-tuple for SpritePreviewCache
                    self.coordinator._cache.put(cache_key, (b"mock_data", 0, 0, "mock", 0, 0, -1, True))

            # Request preview
            self.coordinator.request_preview(offset)

            response_time = time.perf_counter() - start_time
            response_times.append(response_time)

        # Calculate performance metrics
        total_operations = cache_operations["hits"] + cache_operations["misses"]
        hit_rate = cache_operations["hits"] / total_operations * 100 if total_operations > 0 else 0
        avg_response_time = sum(response_times) / len(response_times)

        # With backtracking, should achieve decent hit rate
        expected_hit_rate = 25  # At least 25% with backtracking pattern
        assert hit_rate >= expected_hit_rate, f"Cache hit rate too low: {hit_rate:.1f}%"
        assert avg_response_time < perf_bound(0.05), f"Average response too slow: {avg_response_time * 1000:.2f}ms"

        print(f"Cache optimization: {hit_rate:.1f}% hit rate, avg={avg_response_time * 1000:.2f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "performance"])
