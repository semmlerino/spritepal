"""
Mock HAL infrastructure for fast unit testing.

This module provides mock implementations of HAL compression/decompression
that eliminate process pool overhead while maintaining interface compatibility.
Tests run 7x faster with these mocks compared to real HAL process pools.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any

from core.hal_compression import HALRequest, HALResult


class MockHALProcessPool:
    """
    Fast mock implementation of HALProcessPool for unit tests.

    Provides instant responses without process communication overhead.
    Maintains thread safety and singleton pattern compatibility.
    """

    _instance = None
    _lock = threading.Lock()
    _cleanup_registered = False  # Match real HAL class attribute

    def __new__(cls):
        """Maintain singleton pattern for compatibility."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize mock pool state."""
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._pool_lock = threading.RLock()
        self._pool_initialized = False
        self._shutdown = False
        self._pool_size = 4
        self._exhal_path = None
        self._inhal_path = None

        # Mock statistics for testing
        self._request_count = 0
        self._decompress_count = 0
        self._compress_count = 0
        self._batch_count = 0

        # Configuration for mock behavior
        self._mock_delay = 0.0  # Can be set to simulate processing time
        self._mock_failures = {}  # Map request_id to error messages
        self._deterministic_data = True  # Use deterministic mock data

        # Register cleanup hooks for compatibility
        self._register_cleanup_hooks()

    def _register_cleanup_hooks(self):
        """Mock cleanup hook registration for compatibility."""
        # Just set the flag, no actual hooks needed for mock
        if not MockHALProcessPool._cleanup_registered:
            MockHALProcessPool._cleanup_registered = True

    def _connect_qt_cleanup(self):
        """Mock Qt cleanup connection for compatibility."""
        # No-op for mock
        pass

    def initialize(self, exhal_path: str, inhal_path: str, pool_size: int = 4) -> bool:
        """Mock pool initialization - always succeeds instantly."""
        with self._pool_lock:
            if self._pool_initialized:
                return True

            self._exhal_path = exhal_path
            self._inhal_path = inhal_path
            self._pool_size = pool_size
            self._pool_initialized = True

            # No actual processes to start
            return True

    def submit_request(self, request: HALRequest) -> HALResult:
        """
        Process a single request with mock implementation.

        Returns predictable results instantly without process overhead.
        """
        if not self._pool_initialized or self._shutdown:
            return HALResult(
                success=False, error_message="Pool not initialized or shutting down", request_id=request.request_id
            )

        self._request_count += 1

        # Simulate processing delay if configured
        if self._mock_delay > 0:
            time.sleep(self._mock_delay)  # sleep-ok: simulated processing delay

        # Check for configured failures
        if request.request_id in self._mock_failures:
            return HALResult(
                success=False, error_message=self._mock_failures[request.request_id], request_id=request.request_id
            )

        # Process based on operation type
        if request.operation == "decompress":
            return self._mock_decompress(request)
        if request.operation == "compress":
            return self._mock_compress(request)
        return HALResult(
            success=False, error_message=f"Unknown operation: {request.operation}", request_id=request.request_id
        )

    def _mock_decompress(self, request: HALRequest) -> HALResult:
        """Generate mock decompressed data."""
        self._decompress_count += 1

        # Generate deterministic mock data based on offset
        if self._deterministic_data:
            # Create predictable data pattern based on offset
            data_size = 0x8000  # Standard decompressed size (32KB)

            # Generate pattern: offset bytes repeated
            pattern = bytes([request.offset % 256]) * 4
            data = pattern * (data_size // len(pattern))
            data = data[:data_size]  # Trim to exact size

            # Add marker for test verification
            marker = f"MOCK_DECOMP_{request.offset:08X}".encode()
            data = marker + data[len(marker) :]
        else:
            # Random data for stress testing
            data = os.urandom(0x8000)

        return HALResult(success=True, data=data, size=len(data), request_id=request.request_id)

    def _mock_compress(self, request: HALRequest) -> HALResult:
        """Generate mock compressed size."""
        self._compress_count += 1

        if not request.data:
            return HALResult(
                success=False, error_message="No data provided for compression", request_id=request.request_id
            )

        # Simulate compression with ~60% ratio
        original_size = len(request.data)
        compressed_size = int(original_size * 0.4)

        # Write mock file if output path specified
        if request.output_path:
            Path(request.output_path).parent.mkdir(parents=True, exist_ok=True)

            # Create mock compressed data
            if self._deterministic_data:
                # Use hash for deterministic but varied data
                data_hash = hashlib.md5(request.data).hexdigest()
                mock_data = f"MOCK_COMPRESSED_{data_hash}".encode()
                mock_data = mock_data + b"\x00" * (compressed_size - len(mock_data))
            else:
                mock_data = os.urandom(compressed_size)

            Path(request.output_path).write_bytes(mock_data[:compressed_size])

        return HALResult(success=True, size=compressed_size, request_id=request.request_id)

    def submit_batch(self, requests: list[HALRequest]) -> list[HALResult]:
        """Process multiple requests - uses single-threaded mock processing."""
        self._batch_count += 1

        if not self._pool_initialized or self._shutdown:
            return [
                HALResult(
                    success=False, error_message="Pool not initialized or shutting down", request_id=req.request_id
                )
                for req in requests
            ]

        # Process each request sequentially (still fast with mocks)
        results = []
        for req in requests:
            results.append(self.submit_request(req))

        return results

    def shutdown(self):
        """Mock shutdown - instant with no processes to clean up."""
        with self._pool_lock:
            if not self._pool_initialized or self._shutdown:
                return

            self._shutdown = True
            self._pool_initialized = False

            # No processes to terminate
            # Clear mock state
            self._request_count = 0
            self._decompress_count = 0
            self._compress_count = 0
            self._batch_count = 0

    def force_reset(self):
        """Force reset for test cleanup - instant."""
        with self._pool_lock:
            self._shutdown = True
            self._pool_initialized = False
            self._exhal_path = None
            self._inhal_path = None
            self._mock_failures.clear()

            # Reset statistics
            self._request_count = 0
            self._decompress_count = 0
            self._compress_count = 0
            self._batch_count = 0

    @classmethod
    def reset_singleton(cls):
        """Reset singleton for test isolation."""
        with cls._lock:
            if cls._instance is not None:
                with contextlib.suppress(Exception):
                    cls._instance.force_reset()
                cls._instance = None
                cls._cleanup_registered = False  # Reset class attribute

    @property
    def is_initialized(self) -> bool:
        """Check if pool is initialized."""
        return self._pool_initialized and not self._shutdown

    @property
    def _pool(self) -> bool | None:
        """Backward compatibility property."""
        return True if self._pool_initialized else None

    @_pool.setter
    def _pool(self, value: bool | None) -> None:
        """Backward compatibility setter."""
        self._pool_initialized = bool(value) if value is not None else False

    def get_statistics(self) -> dict[str, int]:
        """Get mock usage statistics for test verification."""
        return {
            "request_count": self._request_count,
            "decompress_count": self._decompress_count,
            "compress_count": self._compress_count,
            "batch_count": self._batch_count,
            "pool_size": self._pool_size,
        }

    def configure_failure(self, request_id: str, error_message: str):
        """Configure a specific request to fail for testing error handling."""
        self._mock_failures[request_id] = error_message

    def set_processing_delay(self, delay: float):
        """Set mock processing delay to simulate slower operations."""
        self._mock_delay = max(0.0, delay)

    def set_deterministic_mode(self, enabled: bool):
        """Toggle between deterministic and random mock data."""
        self._deterministic_data = enabled


class MockHALCompressor:
    """
    Fast mock implementation of HALCompressor for unit tests.

    Provides instant compression/decompression without subprocess overhead.
    """

    def __init__(self, exhal_path: str | None = None, inhal_path: str | None = None, use_pool: bool = True):
        """Initialize mock compressor."""
        self.exhal_path = exhal_path or "mock_exhal"
        self.inhal_path = inhal_path or "mock_inhal"
        self._use_pool = use_pool
        self._pool = None
        self._pool_failed = False

        # Statistics
        self._decompress_count = 0
        self._compress_count = 0
        self._batch_decompress_count = 0
        self._batch_compress_count = 0

        # Mock configuration
        self._deterministic = True
        self._compression_ratio = 0.4  # 60% compression

        if use_pool:
            self._pool = MockHALProcessPool()
            # Check if initialization succeeds (can be patched in tests)
            if not self._pool.initialize(self.exhal_path, self.inhal_path):
                self._pool = None
                self._pool_failed = True

    def decompress_from_rom(self, rom_path: str, offset: int, output_path: str | None = None) -> bytes:
        """Mock decompression - returns predictable data instantly."""
        self._decompress_count += 1

        # Use pool if available
        if self._pool and self._pool.is_initialized:
            request = HALRequest(
                operation="decompress",
                rom_path=rom_path,
                offset=offset,
                output_path=output_path,
                request_id=f"decompress_{offset}",
            )

            result = self._pool.submit_request(request)

            if result.success and result.data:
                if output_path:
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(output_path).write_bytes(result.data)
                return result.data

        # Direct mock without pool
        data_size = 0x8000  # Standard size

        if self._deterministic:
            # Deterministic pattern
            pattern = bytes([offset % 256]) * 4
            data = pattern * (data_size // len(pattern))
            data = data[:data_size]

            # Add marker
            marker = f"MOCK_DECOMP_{offset:08X}".encode()
            data = marker + data[len(marker) :]
        else:
            data = os.urandom(data_size)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(data)

        return data

    def compress_to_file(self, input_data: bytes, output_path: str, fast: bool = False) -> int:
        """Mock compression - returns predictable size instantly."""
        self._compress_count += 1

        # Calculate mock compressed size
        compressed_size = int(len(input_data) * self._compression_ratio)

        # Create mock compressed file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if self._deterministic:
            data_hash = hashlib.md5(input_data).hexdigest()
            mock_data = f"MOCK_COMP_{data_hash}".encode()
            mock_data = mock_data + b"\x00" * (compressed_size - len(mock_data))
        else:
            mock_data = os.urandom(compressed_size)

        Path(output_path).write_bytes(mock_data[:compressed_size])

        return compressed_size

    def compress_to_rom(
        self, input_data: bytes, rom_path: str, offset: int, output_rom_path: str | None = None, fast: bool = False
    ) -> tuple[bool, str]:
        """Mock ROM injection - simulates success instantly."""
        self._compress_count += 1

        compressed_size = int(len(input_data) * self._compression_ratio)

        # Simulate ROM modification
        if output_rom_path and output_rom_path != rom_path:
            # Would copy ROM in real implementation
            pass

        message = f"Successfully injected compressed data ({compressed_size} bytes) at offset 0x{offset:X}"
        return True, message

    def test_tools(self) -> tuple[bool, str]:
        """Mock tool test - always succeeds."""
        return True, "HAL compression tools are working correctly"

    def decompress_batch(self, requests: list[tuple[str, int]]) -> list[tuple[bool, bytes | str]]:
        """Mock batch decompression."""
        self._batch_decompress_count += 1

        results = []
        for rom_path, offset in requests:
            try:
                data = self.decompress_from_rom(rom_path, offset)
                results.append((True, data))
            except Exception as e:
                results.append((False, str(e)))

        return results

    def compress_batch(self, requests: list[tuple[bytes, str, bool]]) -> list[tuple[bool, int | str]]:
        """Mock batch compression."""
        self._batch_compress_count += 1

        results = []
        for data, output_path, fast in requests:
            try:
                size = self.compress_to_file(data, output_path, fast)
                results.append((True, size))
            except Exception as e:
                results.append((False, str(e)))

        return results

    @property
    def pool_status(self) -> dict[str, Any]:
        """Get mock pool status."""
        if not self._pool:
            return {
                "enabled": False,
                "reason": "Pool not configured" if not self._use_pool else "Pool initialization failed",
            }

        return {
            "enabled": True,
            "initialized": self._pool.is_initialized,
            "pool_size": 4,
            "mode": "mock_pool",
            "statistics": self._pool.get_statistics() if hasattr(self._pool, "get_statistics") else {},
        }

    def get_statistics(self) -> dict[str, int]:
        """Get usage statistics for test verification."""
        stats = {
            "decompress_count": self._decompress_count,
            "compress_count": self._compress_count,
            "batch_decompress_count": self._batch_decompress_count,
            "batch_compress_count": self._batch_compress_count,
        }

        if self._pool and hasattr(self._pool, "get_statistics"):
            stats["pool"] = self._pool.get_statistics()

        return stats

    def set_deterministic_mode(self, enabled: bool = True) -> None:
        """Toggle between deterministic and random mock data.

        Args:
            enabled: If True, mock data is deterministic (same inputs = same outputs).
                    If False, random data is generated (for stress testing).
        """
        self._deterministic = enabled
        # Also set on pool if available
        if self._pool and hasattr(self._pool, "set_deterministic_mode"):
            self._pool.set_deterministic_mode(enabled)


def create_mock_hal_tools(tmp_path: Path) -> tuple[str, str]:
    """
    Create mock HAL tool executables for testing.

    Returns paths to mock exhal and inhal executables.
    """
    exhal_path = tmp_path / "exhal"
    inhal_path = tmp_path / "inhal"

    # Create mock scripts
    exhal_content = "#!/bin/bash\necho 'Mock exhal tool'"
    inhal_content = "#!/bin/bash\necho 'Mock inhal tool'"

    exhal_path.write_text(exhal_content)
    inhal_path.write_text(inhal_content)

    # Make executable
    exhal_path.chmod(0o755)
    inhal_path.chmod(0o755)

    return str(exhal_path), str(inhal_path)


def patch_hal_for_tests():
    """
    Patch HAL modules to use mock implementations.

    Returns a context manager that replaces real HAL with mocks.
    """
    from unittest.mock import patch

    return patch.multiple("core.hal_compression", HALProcessPool=MockHALProcessPool, HALCompressor=MockHALCompressor)


def configure_hal_mocking(use_mocks: bool = True, deterministic: bool = True):
    """
    Configure global HAL mocking behavior.

    Args:
        use_mocks: Whether to use mock implementations
        deterministic: Whether mocks should return deterministic data
    """
    if use_mocks:
        # Set environment variable for detection
        os.environ["SPRITEPAL_MOCK_HAL"] = "1"
        os.environ["SPRITEPAL_MOCK_HAL_DETERMINISTIC"] = "1" if deterministic else "0"
    else:
        # Clear environment variables
        os.environ.pop("SPRITEPAL_MOCK_HAL", None)
        os.environ.pop("SPRITEPAL_MOCK_HAL_DETERMINISTIC", None)


def is_hal_mocked() -> bool:
    """Check if HAL mocking is enabled."""
    return os.environ.get("SPRITEPAL_MOCK_HAL") == "1"


def is_hal_deterministic() -> bool:
    """Check if HAL mocks should use deterministic data."""
    return os.environ.get("SPRITEPAL_MOCK_HAL_DETERMINISTIC", "1") == "1"
