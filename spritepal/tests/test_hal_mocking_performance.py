"""
Performance tests to validate HAL mocking improvements.

This module demonstrates the performance improvements achieved by
using mock HAL implementations instead of real process pools.
"""
from __future__ import annotations

import time

import pytest

from core.hal_compression import HALRequest
from tests.infrastructure.mock_hal import MockHALProcessPool

# HAL mocking performance tests must run serially due to singleton management
pytestmark = [
    pytest.mark.serial,
    pytest.mark.process_pool,
    pytest.mark.singleton,
    pytest.mark.benchmark,
    pytest.mark.ci_safe,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.performance,
]

class TestHALMockingPerformance:
    """Test HAL mocking performance improvements."""

    def test_mock_deterministic_behavior(self, hal_pool):
        """Test that mock provides deterministic results."""
        # Same request should give same result
        request = HALRequest(
            operation="decompress",
            rom_path="test.rom",
            offset=0x2000,
            request_id="test_deterministic"
        )

        result1 = hal_pool.submit_request(request)
        result2 = hal_pool.submit_request(request)

        assert result1.success
        assert result2.success
        assert result1.data == result2.data

    def test_mock_error_simulation(self, hal_pool):
        """Test that mock can simulate errors for testing."""
        # Configure a failure
        hal_pool.configure_failure("fail_test", "Simulated error for testing")

        request = HALRequest(
            operation="decompress",
            rom_path="test.rom",
            offset=0x3000,
            request_id="fail_test"
        )

        result = hal_pool.submit_request(request)

        assert not result.success
        assert result.error_message == "Simulated error for testing"

    def test_mock_statistics_tracking(self, hal_pool):
        """Test that mock tracks usage statistics."""
        # Perform various operations
        decompress_req = HALRequest(
            operation="decompress",
            rom_path="test.rom",
            offset=0x4000,
            request_id="stats_1"
        )

        compress_req = HALRequest(
            operation="compress",
            rom_path="",
            offset=0,
            data=b"test data",
            output_path="test.compressed",
            request_id="stats_2"
        )

        hal_pool.submit_request(decompress_req)
        hal_pool.submit_request(compress_req)

        # Check statistics
        stats = hal_pool.get_statistics()
        assert stats["request_count"] == 2
        assert stats["decompress_count"] == 1
        assert stats["compress_count"] == 1

    @pytest.mark.real_hal
    @pytest.mark.slow
    def test_real_vs_mock_performance_comparison(self, request, tmp_path):
        """Compare real HAL pool vs mock performance."""
        # This test is marked with real_hal so it gets the real pool
        # We'll manually create both for comparison

        from core.hal_compression import HALProcessPool
        from tests.infrastructure.mock_hal import create_mock_hal_tools

        # Setup real pool
        HALProcessPool.reset_singleton()
        real_pool = HALProcessPool()
        exhal_path, inhal_path = create_mock_hal_tools(tmp_path)

        # Time real pool initialization
        start = time.perf_counter()
        real_pool.initialize(exhal_path, inhal_path, pool_size=4)
        real_init_time = time.perf_counter() - start

        # Time real pool request
        request = HALRequest(
            operation="decompress",
            rom_path=str(tmp_path / "test.rom"),
            offset=0x1000,
            request_id="perf_test"
        )

        # Create dummy ROM file
        (tmp_path / "test.rom").write_bytes(b"\x00" * 0x10000)

        start = time.perf_counter()
        real_pool.submit_request(request)
        real_request_time = time.perf_counter() - start

        # Cleanup real pool
        real_pool.shutdown()
        HALProcessPool.reset_singleton()

        # Setup mock pool
        mock_pool = MockHALProcessPool()

        # Time mock pool initialization
        start = time.perf_counter()
        mock_pool.initialize("mock_exhal", "mock_inhal")
        mock_init_time = time.perf_counter() - start

        # Time mock pool request
        start = time.perf_counter()
        mock_pool.submit_request(request)
        mock_request_time = time.perf_counter() - start

        # Cleanup mock pool
        mock_pool.shutdown()
        MockHALProcessPool.reset_singleton()

        # Compare performance
        init_speedup = real_init_time / mock_init_time if mock_init_time > 0 else 1000
        request_speedup = real_request_time / mock_request_time if mock_request_time > 0 else 1000

        print("\nPerformance Comparison:")
        print(f"  Initialization: {init_speedup:.1f}x faster")
        print(f"  Request processing: {request_speedup:.1f}x faster")
        print(f"  Real init time: {real_init_time:.3f}s")
        print(f"  Mock init time: {mock_init_time:.6f}s")
        print(f"  Real request time: {real_request_time:.3f}s")
        print(f"  Mock request time: {mock_request_time:.6f}s")

        # Mock should be at least 100x faster for initialization
        assert init_speedup > 100

        # Mock requests should not be slower than real ones; when real calls are
        # effectively instantaneous, allow a small tolerance instead of ratio-based checks.
        if real_request_time < 0.001:
            assert mock_request_time <= real_request_time + 0.001
        else:
            assert request_speedup > 1

class TestHALCompressorMocking:
    """Test HAL compressor mocking."""

    def test_mock_compressor_interface_compatibility(self, hal_compressor):
        """Test that mock compressor has compatible interface."""
        # Should have all required methods
        assert hasattr(hal_compressor, 'decompress_from_rom')
        assert hasattr(hal_compressor, 'compress_to_file')
        assert hasattr(hal_compressor, 'compress_to_rom')
        assert hasattr(hal_compressor, 'test_tools')
        assert hasattr(hal_compressor, 'decompress_batch')
        assert hasattr(hal_compressor, 'compress_batch')
        assert hasattr(hal_compressor, 'pool_status')

    def test_mock_compressor_decompression(self, hal_compressor, tmp_path):
        """Test mock decompression functionality."""
        # Create dummy ROM
        rom_path = tmp_path / "test.rom"
        rom_path.write_bytes(b"\x00" * 0x10000)

        # Decompress
        data = hal_compressor.decompress_from_rom(str(rom_path), 0x2000)

        # Should return deterministic data
        assert data is not None
        assert len(data) == 0x8000  # Standard size
        assert b"MOCK_DECOMP" in data  # Contains marker

    def test_mock_compressor_compression(self, hal_compressor, tmp_path):
        """Test mock compression functionality."""
        test_data = b"Test data for compression" * 100
        output_path = tmp_path / "compressed.bin"

        # Compress
        size = hal_compressor.compress_to_file(test_data, str(output_path))

        # Should create file with reasonable compression ratio
        assert output_path.exists()
        assert size < len(test_data)  # Should be compressed
        assert size == output_path.stat().st_size

    def test_mock_compressor_batch_operations(self, hal_compressor, tmp_path):
        """Test mock batch operations."""
        # Create dummy ROM
        rom_path = tmp_path / "test.rom"
        rom_path.write_bytes(b"\x00" * 0x10000)

        # Batch decompression
        requests = [(str(rom_path), offset) for offset in range(0x1000, 0x5000, 0x1000)]
        results = hal_compressor.decompress_batch(requests)

        assert len(results) == 4
        assert all(success for success, _ in results)

        # Batch compression
        compress_requests = [
            (b"data" * 100, str(tmp_path / f"out_{i}.bin"), False)
            for i in range(3)
        ]
        compress_results = hal_compressor.compress_batch(compress_requests)

        assert len(compress_results) == 3
        assert all(success for success, _ in compress_results)

    def test_mock_compressor_statistics(self, hal_compressor, tmp_path):
        """Test that mock compressor tracks statistics."""
        rom_path = tmp_path / "test.rom"
        rom_path.write_bytes(b"\x00" * 0x10000)

        # Perform operations
        hal_compressor.decompress_from_rom(str(rom_path), 0x1000)
        hal_compressor.compress_to_file(b"test", str(tmp_path / "out.bin"))

        # Check statistics
        stats = hal_compressor.get_statistics()
        assert stats["decompress_count"] == 1
        assert stats["compress_count"] == 1

class TestAutoMocking:
    """Test automatic HAL mocking based on test type."""

    @pytest.mark.real_hal
    def test_real_hal_marker_overrides_mocking(self, tmp_path):
        """Tests marked with real_hal should get real implementation."""
        from core.hal_compression import HALCompressor
        from tests.infrastructure.mock_hal import create_mock_hal_tools

        # Create tools
        exhal_path, inhal_path = create_mock_hal_tools(tmp_path)

        # This should be the real version (but with mock tools)
        compressor = HALCompressor(exhal_path, inhal_path)

        # Real compressor doesn't have get_statistics method
        assert not hasattr(compressor, 'get_statistics')

    def test_fixture_provides_correct_implementation(self, hal_compressor):
        """Fixture should provide mock by default."""
        # Should be mock version
        assert hasattr(hal_compressor, 'get_statistics')

        # Should have statistics initialized
        stats = hal_compressor.get_statistics()
        assert stats["decompress_count"] == 0
        assert stats["compress_count"] == 0
