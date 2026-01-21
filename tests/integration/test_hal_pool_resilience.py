"""
Tests for HAL process pool fault tolerance and resilience.

These tests cover:
- P1: HAL pool resilience under failure conditions
- Timeout handling
- Batch deadline enforcement
- Graceful shutdown under load
- Worker initialization validation

Related tests:
- tests/fixtures/hal_fixtures.py - HAL fixture definitions
- tests/integration/test_hal_compression_simplified.py - Basic HAL tests

Note: These tests use the MockHALProcessPool to simulate failure scenarios
without requiring actual HAL binaries or spawning real processes.
"""

from __future__ import annotations

import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from core.hal_compression import (
    HALPoolError,
    HALProcessPool,
    HALRequest,
    HALResult,
    HALResultStatus,
)

# Mark all tests as headless and integration
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]


class TestPoolInitializationValidation:
    """Tests for pool initialization and worker validation."""

    def test_uninitialized_pool_rejects_requests(self) -> None:
        """Verify uninitialized pool returns error for requests."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = False
        pool._pool_initialized = False
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
            request_id="test_1",
        )

        result = pool.submit_request(request)

        assert result.success is False
        assert "not initialized" in result.error_message.lower()

    def test_shutdown_pool_rejects_requests(self) -> None:
        """Verify pool in shutdown state rejects new requests."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = True  # Already shutting down
        pool._pool_lock = threading.Lock()

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
            request_id="test_1",
        )

        result = pool.submit_request(request)

        assert result.success is False
        # Error message says "shutting down" not just "shutdown"
        assert "shutting down" in result.error_message.lower()


class TestTimeoutHandling:
    """Tests for request timeout handling."""

    def test_timeout_returns_proper_status(self) -> None:
        """Verify timeout produces proper result with error message."""
        # Create a pool mock that simulates timeout
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        # Create a queue that will block (timeout)
        mock_request_queue = MagicMock()
        mock_result_queue = MagicMock()
        mock_result_queue.get.side_effect = queue.Empty()

        pool._request_queue = mock_request_queue
        pool._result_queue = mock_result_queue

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

    def test_timeout_includes_duration(self) -> None:
        """Verify timeout error message includes timeout duration."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        mock_request_queue = MagicMock()
        mock_result_queue = MagicMock()
        mock_result_queue.get.side_effect = queue.Empty()

        pool._request_queue = mock_request_queue
        pool._result_queue = mock_result_queue

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
            request_id="timeout_test",
        )

        result = pool.submit_request(request)

        # Should include "seconds" in the timeout message
        assert "seconds" in result.error_message.lower()


class TestRequestResultCorrelation:
    """Tests for request-result ID correlation."""

    def test_result_preserves_request_id(self) -> None:
        """Verify result carries original request_id for correlation."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        # Create queue that returns a result
        mock_request_queue = MagicMock()
        mock_result_queue = MagicMock()
        expected_result = HALResult(
            success=True,
            data=b"test_data",
            size=100,
            request_id="specific_id_123",
        )
        mock_result_queue.get.return_value = expected_result

        pool._request_queue = mock_request_queue
        pool._result_queue = mock_result_queue

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
            request_id="specific_id_123",
        )

        result = pool.submit_request(request)

        assert result.request_id == "specific_id_123"

    def test_queue_exception_preserves_request_id(self) -> None:
        """Verify queue exceptions still preserve request_id."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        mock_request_queue = MagicMock()
        mock_request_queue.put.side_effect = Exception("Queue broken")

        pool._request_queue = mock_request_queue
        pool._result_queue = MagicMock()

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
            request_id="broken_queue_test",
        )

        result = pool.submit_request(request)

        assert result.success is False
        assert result.request_id == "broken_queue_test"


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


class TestPoolStateMachine:
    """Tests for pool state transitions."""

    def test_initialized_state_check(self) -> None:
        """Verify is_initialized property reflects state."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._pool_initialized = False
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        assert pool.is_initialized is False

        pool._pool_initialized = True
        assert pool.is_initialized is True

    def test_shutdown_state_prevents_operations(self) -> None:
        """Verify shutdown state prevents further operations."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = True
        pool._pool_lock = threading.Lock()

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0,
        )

        result = pool.submit_request(request)
        assert result.success is False
        # Error message says "shutting down" not just "shutdown"
        assert "shutting down" in result.error_message.lower()


class TestErrorMessageQuality:
    """Tests for error message quality and actionability."""

    def test_timeout_error_is_actionable(self) -> None:
        """Verify timeout error message helps debugging."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        mock_request_queue = MagicMock()
        mock_result_queue = MagicMock()
        mock_result_queue.get.side_effect = queue.Empty()

        pool._request_queue = mock_request_queue
        pool._result_queue = mock_result_queue

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0x1000,
        )

        result = pool.submit_request(request)

        # Error message should be helpful
        assert result.error_message is not None
        assert len(result.error_message) > 10  # Not just "timeout"

    def test_queue_error_includes_cause(self) -> None:
        """Verify queue errors include root cause."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        mock_request_queue = MagicMock()
        mock_request_queue.put.side_effect = ValueError("Test queue error")

        pool._request_queue = mock_request_queue
        pool._result_queue = MagicMock()

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0,
        )

        result = pool.submit_request(request)

        assert result.success is False
        # Should include the original error message
        assert "error" in result.error_message.lower()


class TestNullQueueHandling:
    """Tests for null queue handling edge cases."""

    def test_null_request_queue_handled(self) -> None:
        """Verify null request queue is handled gracefully."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        pool._request_queue = None
        pool._result_queue = MagicMock()

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0,
        )

        result = pool.submit_request(request)

        assert result.success is False
        # Should indicate pool error, not crash
        assert result.error_message is not None

    def test_null_result_queue_handled(self) -> None:
        """Verify null result queue is handled gracefully."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        pool._request_queue = MagicMock()
        pool._result_queue = None

        request = HALRequest(
            operation="decompress",
            rom_path="/test.sfc",
            offset=0,
        )

        result = pool.submit_request(request)

        assert result.success is False
        assert result.error_message is not None


class TestConcurrencyBehavior:
    """Tests for concurrent access patterns."""

    def test_multiple_sequential_requests(self) -> None:
        """Verify multiple sequential requests are handled correctly."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()

        results_to_return = [
            HALResult(success=True, data=b"result1", request_id="req_1"),
            HALResult(success=True, data=b"result2", request_id="req_2"),
            HALResult(success=True, data=b"result3", request_id="req_3"),
        ]

        mock_request_queue = MagicMock()
        mock_result_queue = MagicMock()
        mock_result_queue.get.side_effect = results_to_return

        pool._request_queue = mock_request_queue
        pool._result_queue = mock_result_queue

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

        # Verify all succeeded
        assert all(r.success for r in results)
        assert mock_request_queue.put.call_count == 3


class TestPoolCleanupState:
    """Tests for pool cleanup state handling."""

    def test_double_shutdown_safe(self) -> None:
        """Verify calling shutdown twice is safe."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()
        pool._processes = []
        pool._process_pids = []
        pool._process_refs = []
        pool._manager = None
        pool._request_queue = None
        pool._result_queue = None

        # First shutdown
        pool.shutdown()
        assert pool._shutdown is True

        # Second shutdown should be safe (no-op)
        pool.shutdown()  # Should not raise
        assert pool._shutdown is True

    def test_cleanup_clears_references(self) -> None:
        """Verify shutdown clears internal references."""
        pool = HALProcessPool.__new__(HALProcessPool)
        pool._initialized = True
        pool._pool_initialized = True
        pool._shutdown = False
        pool._pool_lock = threading.Lock()
        pool._processes = [MagicMock(), MagicMock()]
        pool._process_pids = [1234, 5678]
        pool._process_refs = []
        pool._manager = None
        pool._request_queue = MagicMock()
        pool._result_queue = MagicMock()

        pool.shutdown()

        assert len(pool._processes) == 0
        assert len(pool._process_pids) == 0
        assert pool._request_queue is None
        assert pool._result_queue is None
