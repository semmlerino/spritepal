"""
Simple test to verify HAL mocking is working correctly.
"""
from __future__ import annotations

import pytest

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.parallel_safe,
    pytest.mark.performance,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
]

def test_hal_is_mocked():
    """Verify that HAL is automatically mocked for unit tests (when real tools unavailable)."""
    from core.hal_compression import HALCompressor

    # Create a compressor
    compressor = HALCompressor()

    # Check if it's the mock version by looking for mock-specific attributes
    # The mock has get_statistics method, real doesn't
    if hasattr(compressor, 'get_statistics'):
        print("✅ HAL is MOCKED (as expected for unit tests without real tools)")
        stats = compressor.get_statistics()
        assert stats is not None
        assert 'decompress_count' in stats
    else:
        # Real HAL tools are installed - this is fine, just skip the mock-specific test
        print("✅ HAL is REAL (real tools are available, which is valid)")
        # Verify basic attributes exist
        assert hasattr(compressor, 'exhal_path')
        assert hasattr(compressor, 'inhal_path')
        pytest.skip("Real HAL tools available - mock test not applicable")

@pytest.mark.real_hal
def test_hal_is_real_with_marker(tmp_path):
    """Verify that @pytest.mark.real_hal gives real HAL."""
    from core.hal_compression import HALCompressor
    from tests.infrastructure.mock_hal import create_mock_hal_tools

    # Create mock tools (since we don't have real exhal/inhal)
    exhal_path, inhal_path = create_mock_hal_tools(tmp_path)

    # Create a compressor with explicit paths
    compressor = HALCompressor(exhal_path, inhal_path)

    # Check if it's the real version
    if hasattr(compressor, 'get_statistics'):
        print("❌ HAL is MOCKED (unexpected with real_hal marker)")
        pytest.fail("HAL should be real when marked with @pytest.mark.real_hal")
    else:
        print("✅ HAL is REAL (as expected with real_hal marker)")
        # Verify it has the expected real attributes
        assert hasattr(compressor, 'exhal_path')
        assert hasattr(compressor, 'inhal_path')

def test_mock_hal_performance():
    """Test that mock HAL operations are fast.

    This test only runs when HAL is mocked (has get_statistics method).
    When real HAL is installed, the test is skipped via skipif.
    """
    import time

    from core.hal_compression import HALCompressor

    compressor = HALCompressor()

    # Check if this is mock HAL - real HAL doesn't have get_statistics
    if not hasattr(compressor, 'get_statistics'):
        pytest.skip("Real HAL is installed - mock performance test not applicable")

    # Time a decompression (should be instant with mock)
    start = time.perf_counter()

    # Mock doesn't need real ROM file - mock HAL handles this
    data = compressor.decompress_from_rom("dummy.rom", 0x1000)

    elapsed = time.perf_counter() - start

    print(f"Decompression took: {elapsed*1000:.2f}ms")

    # Mock should be under 10ms
    assert elapsed < 0.01, f"Mock decompression too slow: {elapsed:.3f}s"

    # Verify we got deterministic data
    assert data is not None
    assert len(data) > 0

    # Do it again - should get same result (deterministic)
    data2 = compressor.decompress_from_rom("dummy.rom", 0x1000)
    assert data == data2, "Mock should be deterministic"
