"""
Simplified integration tests for HAL compression process pool.

Focuses on:
1. Process lifecycle (startup, shutdown, cleanup)
2. Singleton management
3. Basic integration (compress/decompress)

Replaces the bloated test_hal_compression.py.
"""

from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest

from core.hal_compression import HALCompressor, HALProcessPool, HALRequest
from tests.infrastructure.mock_hal import create_mock_hal_tools
from utils.constants import HAL_POOL_SHUTDOWN_TIMEOUT

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.parallel_unsafe,
]


@pytest.fixture
def mock_not_wsl():
    """Mock _is_wsl_environment to return False."""
    with patch("core.hal_compression._is_wsl_environment", return_value=False):
        yield


@pytest.fixture
def hal_tools(tmp_path):
    """Create mock HAL tool executables."""
    return create_mock_hal_tools(tmp_path)


@pytest.fixture(autouse=True)
def reset_hal_singleton():
    """Reset HAL singleton between tests."""
    HALProcessPool.reset_singleton()
    yield
    try:
        HALProcessPool.reset_singleton()
    except Exception:
        pass


class TestHALProcessPoolLifecycle:
    """Test critical process pool lifecycle events."""

    def test_pool_initialization(self, hal_tools):
        """Test that pool initializes with correct number of processes."""
        exhal_path, inhal_path = hal_tools
        pool = HALProcessPool()

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
            # Setup mocks
            mock_mgr = Mock()
            mock_mgr.Queue.return_value = Mock()
            mock_manager.return_value = mock_mgr

            # Mock processes
            processes = []
            for i in range(2):
                p = Mock()
                p.pid = 1000 + i
                p.is_alive.return_value = True
                processes.append(p)
            mock_process_class.side_effect = processes

            # Initialize
            success = pool.initialize(exhal_path, inhal_path, pool_size=2)

            assert success
            assert pool.is_initialized
            assert mock_process_class.call_count == 2

    def test_pool_shutdown_terminates_processes(self, hal_tools):
        """Test that shutdown terminates all worker processes."""
        exhal_path, inhal_path = hal_tools
        pool = HALProcessPool()

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
            # Setup mocks
            mock_mgr = Mock()
            mock_mgr.Queue.return_value = Mock()
            mock_manager.return_value = mock_mgr

            # Mock processes
            p1 = Mock()
            p1.pid = 2001
            p1.is_alive.return_value = True

            mock_process_class.return_value = p1

            # Init & Shutdown
            pool.initialize(exhal_path, inhal_path, pool_size=1)
            pool.shutdown()

            # Verify termination
            p1.terminate.assert_called_once()
            assert not pool.is_initialized

    def test_shutdown_kills_stuck_processes(self, hal_tools):
        """Test that shutdown force-kills processes that refuse to terminate."""
        exhal_path, inhal_path = hal_tools
        pool = HALProcessPool()

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
            mock_mgr = Mock()
            mock_mgr.Queue.return_value = Mock()
            mock_manager.return_value = mock_mgr

            # Stuck process (always alive)
            stuck_proc = Mock()
            stuck_proc.pid = 3001
            stuck_proc.is_alive.return_value = True
            mock_process_class.return_value = stuck_proc

            pool.initialize(exhal_path, inhal_path, pool_size=1)
            pool.shutdown()

            # Should have called terminate AND kill
            stuck_proc.terminate.assert_called_once()
            stuck_proc.kill.assert_called_once()


class TestHALIntegration:
    """Integration tests for HALCompressor using the pool."""

    def test_compressor_uses_pool_when_enabled(self, hal_tools, mock_not_wsl):
        """Verify HALCompressor delegates to pool when initialized."""
        exhal_path, inhal_path = hal_tools

        # Initialize pool
        pool = HALProcessPool()
        # We need to mock the internal initialization to avoid spawning real processes
        # but we want the pool to appear initialized
        with (
            patch("multiprocessing.Manager"),
            patch("multiprocessing.Process"),
        ):
            pool.initialize(exhal_path, inhal_path, pool_size=1)

        compressor = HALCompressor(exhal_path, inhal_path, use_pool=True)

        # Verify status
        status = compressor.pool_status
        assert status["enabled"]
        assert status["initialized"]

    def test_decompress_request_flow(self, hal_tools, tmp_path, mock_not_wsl):
        """Test end-to-end request submission (mocked execution)."""
        exhal_path, inhal_path = hal_tools
        pool = HALProcessPool()

        # Create a dummy ROM file to satisfy stat() check
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 0x2000)

        # Mock the entire submit_request to simulate successful worker
        with patch.object(pool, "submit_request") as mock_submit:
            # Setup mock result
            mock_result = Mock()
            mock_result.success = True
            mock_result.data = b"DECOMPRESSED_DATA"
            mock_submit.return_value = mock_result

            # Initialize pool mock state
            pool._initialized = True

            # Create compressor using this pool
            compressor = HALCompressor(exhal_path, inhal_path, use_pool=True)

            # Execute
            data = compressor.decompress_from_rom(str(rom_path), 0x1000)

            # Verify
            assert data == b"DECOMPRESSED_DATA"
            mock_submit.assert_called_once()
            call_args = mock_submit.call_args[0][0]
            assert isinstance(call_args, HALRequest)
            assert call_args.operation == "decompress"
            assert call_args.offset == 0x1000
