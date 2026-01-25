"""
Tests for HAL process pool behavior and data structures.

These tests cover:
- HAL pool lifecycle (initialization, shutdown)
- Request/Result data structures
- Error handling and message quality
- Pool state machine behavior
- HALCompressor integration with pool

Tests use public API where possible. For edge cases that require
simulating failure conditions (timeouts, broken queues), minimal
mocking is used with clear documentation of why.

Related tests:
- tests/fixtures/hal_fixtures.py - HAL fixture definitions
"""

from __future__ import annotations

import queue
import threading
from unittest.mock import MagicMock, Mock, patch

import pytest

from core.hal_compression import (
    HALCompressor,
    HALProcessPool,
    HALRequest,
    HALResult,
    HALResultStatus,
)
from tests.infrastructure.mock_hal import create_mock_hal_tools

# Mark all tests as headless and unit
pytestmark = [
    pytest.mark.headless,
]


# =============================================================================
# Data Structure Tests (Pure, No Mocking Needed)
# =============================================================================


class TestHALResultDataclass:
    """Tests for HALResult data structure behavior."""

    def test_result_defaults(self) -> None:
        """Verify HALResult has sensible defaults."""
        result = HALResult(success=True)

        assert result.success is True
        assert result.data is None
        assert result.size is None
        assert result.error_message is None
        assert result.request_id is None
        assert result.status == HALResultStatus.COMPLETED
        assert result.batch_id is None

    def test_result_with_error(self) -> None:
        """Verify HALResult properly stores error information."""
        result = HALResult(
            success=False,
            error_message="Test error message",
            request_id="error_test",
            status=HALResultStatus.COMPLETED,
        )

        assert result.success is False
        assert result.error_message == "Test error message"
        assert result.request_id == "error_test"

    def test_timed_out_status(self) -> None:
        """Verify HALResultStatus.TIMED_OUT can be used."""
        result = HALResult(
            success=False,
            error_message="Operation timed out",
            status=HALResultStatus.TIMED_OUT,
        )

        assert result.status == HALResultStatus.TIMED_OUT

    def test_batch_id_correlation(self) -> None:
        """Verify batch_id is preserved for batch result filtering."""
        result = HALResult(
            success=True,
            data=b"test",
            batch_id="batch_abc123",
        )

        assert result.batch_id == "batch_abc123"


class TestHALRequestDataclass:
    """Tests for HALRequest data structure behavior."""

    def test_decompress_request(self) -> None:
        """Verify decompress request structure."""
        request = HALRequest(
            operation="decompress",
            rom_path="/path/to/rom.sfc",
            offset=0x1000,
            request_id="decomp_1",
        )

        assert request.operation == "decompress"
        assert request.rom_path == "/path/to/rom.sfc"
        assert request.offset == 0x1000
        assert request.request_id == "decomp_1"
        assert request.data is None
        assert request.fast is False

    def test_compress_request(self) -> None:
        """Verify compress request structure."""
        test_data = b"\x00" * 100
        request = HALRequest(
            operation="compress",
            rom_path="",
            offset=0,
            data=test_data,
            output_path="/tmp/output.bin",
            fast=True,
            request_id="comp_1",
        )

        assert request.operation == "compress"
        assert request.data == test_data
        assert request.output_path == "/tmp/output.bin"
        assert request.fast is True

    def test_request_with_batch_id(self) -> None:
        """Verify request batch_id is preserved."""
        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0,
            batch_id="batch_xyz",
        )

        assert request.batch_id == "batch_xyz"


# =============================================================================
# Pool Lifecycle Tests (Using Public API)
# =============================================================================


class TestPoolLifecycle:
    """Tests for pool initialization and shutdown via public API."""

    def test_fresh_pool_is_not_initialized(self) -> None:
        """Verify newly created pool reports not initialized."""
        pool = HALProcessPool()
        try:
            assert pool.is_initialized is False
        finally:
            pool.shutdown()

    def test_uninitialized_pool_rejects_requests(self) -> None:
        """Verify uninitialized pool returns error for requests."""
        pool = HALProcessPool()
        try:
            request = HALRequest(
                operation="decompress",
                rom_path="/test.sfc",
                offset=0x1000,
                request_id="test_1",
            )

            result = pool.submit_request(request)

            assert result.success is False
            assert "not initialized" in result.error_message.lower()
        finally:
            pool.shutdown()

    def test_shutdown_is_idempotent(self) -> None:
        """Verify calling shutdown multiple times is safe."""
        pool = HALProcessPool()

        # Multiple shutdowns should not raise
        pool.shutdown()
        pool.shutdown()
        pool.shutdown()

        # Pool should report not initialized after shutdown
        assert pool.is_initialized is False

    def test_shutdown_pool_rejects_requests(self) -> None:
        """Verify pool after shutdown rejects new requests."""
        pool = HALProcessPool()
        pool.shutdown()

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
            request_id="test_1",
        )

        result = pool.submit_request(request)

        assert result.success is False
        # Pool may say "not initialized" or "shutting down" depending on state
        assert result.error_message is not None
        assert len(result.error_message) > 0


# =============================================================================
# Error Simulation Tests (Minimal Mocking for Edge Cases)
# =============================================================================


class TestTimeoutSimulation:
    """Tests for timeout behavior.

    These tests require simulating timeout conditions which cannot be
    easily achieved with real components without long waits.
    We use targeted mocking of the result queue to simulate timeout.
    """

    def _create_pool_with_mock_queues(
        self, request_queue: MagicMock | None = None, result_queue: MagicMock | None = None
    ) -> HALProcessPool:
        """Create a pool instance with mock queues for testing edge cases.

        This bypasses normal initialization to test specific failure modes.
        Used only for error simulation tests.
        """
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()
        pool._request_queue = request_queue or MagicMock()
        pool._result_queue = result_queue or MagicMock()
        return pool

    def test_timeout_returns_failure_result(self) -> None:
        """Verify timeout produces proper result with error message."""
        mock_result_queue = MagicMock()
        mock_result_queue.get.side_effect = queue.Empty()

        pool = self._create_pool_with_mock_queues(result_queue=mock_result_queue)

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
            request_id="timeout_test",
        )

        result = pool.submit_request(request)

        assert result.success is False
        assert "timed out" in result.error_message.lower()
        assert result.request_id == "timeout_test"

    def test_timeout_message_includes_duration(self) -> None:
        """Verify timeout error message includes timeout duration."""
        mock_result_queue = MagicMock()
        mock_result_queue.get.side_effect = queue.Empty()

        pool = self._create_pool_with_mock_queues(result_queue=mock_result_queue)

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
            request_id="timeout_test",
        )

        result = pool.submit_request(request)

        # Should include "seconds" in the timeout message
        assert "seconds" in result.error_message.lower()


class TestQueueErrorSimulation:
    """Tests for queue error handling.

    These tests simulate broken queues to verify error handling.
    """

    def _create_pool_with_mock_queues(
        self, request_queue: MagicMock | None = None, result_queue: MagicMock | None = None
    ) -> HALProcessPool:
        """Create a pool instance with mock queues for testing edge cases."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()
        pool._request_queue = request_queue or MagicMock()
        pool._result_queue = result_queue or MagicMock()
        return pool

    def test_queue_exception_preserves_request_id(self) -> None:
        """Verify queue exceptions still preserve request_id."""
        mock_request_queue = MagicMock()
        mock_request_queue.put.side_effect = Exception("Queue broken")

        pool = self._create_pool_with_mock_queues(request_queue=mock_request_queue)

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
            request_id="broken_queue_test",
        )

        result = pool.submit_request(request)

        assert result.success is False
        assert result.request_id == "broken_queue_test"

    def test_null_request_queue_handled(self) -> None:
        """Verify null request queue is handled gracefully."""
        pool = self._create_pool_with_mock_queues()
        pool._request_queue = None

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0,
        )

        result = pool.submit_request(request)

        assert result.success is False
        assert result.error_message is not None

    def test_null_result_queue_handled(self) -> None:
        """Verify null result queue is handled gracefully."""
        pool = self._create_pool_with_mock_queues()
        pool._result_queue = None

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0,
        )

        result = pool.submit_request(request)

        assert result.success is False
        assert result.error_message is not None


class TestResultCorrelation:
    """Tests for request-result ID correlation."""

    def _create_pool_with_mock_queues(
        self, request_queue: MagicMock | None = None, result_queue: MagicMock | None = None
    ) -> HALProcessPool:
        """Create a pool instance with mock queues for testing edge cases."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()
        pool._request_queue = request_queue or MagicMock()
        pool._result_queue = result_queue or MagicMock()
        return pool

    def test_result_preserves_request_id(self) -> None:
        """Verify result carries original request_id for correlation."""
        expected_result = HALResult(
            success=True,
            data=b"test_data",
            size=100,
            request_id="specific_id_123",
        )
        mock_result_queue = MagicMock()
        mock_result_queue.get.return_value = expected_result

        pool = self._create_pool_with_mock_queues(result_queue=mock_result_queue)

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
            request_id="specific_id_123",
        )

        result = pool.submit_request(request)

        assert result.request_id == "specific_id_123"

    def test_multiple_sequential_requests_correlation(self) -> None:
        """Verify multiple sequential requests maintain ID correlation."""
        results_to_return = [
            HALResult(success=True, data=b"result1", request_id="req_1"),
            HALResult(success=True, data=b"result2", request_id="req_2"),
            HALResult(success=True, data=b"result3", request_id="req_3"),
        ]

        mock_result_queue = MagicMock()
        mock_result_queue.get.side_effect = results_to_return

        pool = self._create_pool_with_mock_queues(result_queue=mock_result_queue)

        # Submit multiple requests
        results = []
        for i in range(3):
            request = HALRequest(
                operation="decompress",
                rom_path="/test.sfc",
                offset=0x1000 * i,
                request_id=f"req_{i + 1}",
            )
            results.append(pool.submit_request(request))

        # Verify all succeeded and IDs preserved
        assert all(r.success for r in results)
        assert results[0].request_id == "req_1"
        assert results[1].request_id == "req_2"
        assert results[2].request_id == "req_3"


# =============================================================================
# Process Pool Lifecycle Tests (With Mocked Multiprocessing)
# =============================================================================


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


class TestHALProcessPoolWithMocks:
    """Test critical process pool lifecycle events with mocked multiprocessing.

    These tests use mocked multiprocessing to verify process management behavior
    without spawning real processes.
    """

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


# =============================================================================
# HALCompressor Integration Tests
# =============================================================================


@pytest.fixture
def mock_not_wsl():
    """Mock _is_wsl_environment to return False."""
    with patch("core.hal_compression._is_wsl_environment", return_value=False):
        yield


class TestHALCompressorIntegration:
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
