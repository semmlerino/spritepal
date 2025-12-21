"""
HAL compression/decompression module for SpritePal.
Interfaces with exhal/inhal C tools for ROM sprite injection.
"""
from __future__ import annotations

import atexit
import contextlib
import multiprocessing as mp
import os
import platform
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import weakref
from enum import Enum
from multiprocessing.managers import SyncManager
from pathlib import Path
from typing import NamedTuple


class HALResultStatus(Enum):
    """Status of a HAL operation result for explicit tracking."""
    COMPLETED = "completed"      # Operation completed successfully or with error
    TIMED_OUT = "timed_out"      # Operation did not return within timeout
    PENDING = "pending"          # Operation submitted but no result yet (internal use)

try:
    from PySide6.QtWidgets import QApplication
    QT_AVAILABLE = True
except ImportError:
    QApplication = None
    QT_AVAILABLE = False


def _is_wsl_environment() -> bool:
    """Detect WSL to avoid unsupported multiprocessing behavior."""
    if sys.platform != "linux":
        return False
    try:
        release = os.uname().release.lower()
        return "microsoft" in release or "wsl" in release
    except (OSError, AttributeError):
        return False

from utils.constants import (
    DATA_SIZE,
    HAL_POOL_MIN_WORKER_RATIO,
    HAL_POOL_SIZE_DEFAULT,
    HAL_POOL_SIZE_MAX,
    HAL_POOL_SIZE_MIN,
    HAL_POOL_TIMEOUT_SECONDS,
)
from utils.logging_config import get_logger
from utils.rom_backup import ROMBackupManager
from utils.safe_logging import (
    safe_debug,
    safe_info,
    safe_warning,
    suppress_logging_errors,
)

logger = get_logger(__name__)

class HALCompressionError(Exception):
    """Raised when HAL compression/decompression fails"""

class HALPoolError(HALCompressionError):
    """Raised when HAL process pool operations fail"""

class HALRequest(NamedTuple):
    """Request structure for HAL process pool operations"""
    operation: str  # 'decompress' or 'compress'
    rom_path: str
    offset: int
    data: bytes | None = None
    output_path: str | None = None
    fast: bool = False
    request_id: str | None = None
    batch_id: str | None = None  # Unique batch identifier to prevent result misattribution

class HALResult(NamedTuple):
    """Result structure for HAL process pool operations.

    Attributes:
        success: Whether the operation succeeded
        data: Decompressed data (for decompress operations)
        size: Compressed/decompressed size
        error_message: Error description if failed
        request_id: ID to correlate request with result
        status: Explicit status tracking (COMPLETED, TIMED_OUT, PENDING)
        batch_id: Unique batch identifier to validate result ownership
    """
    success: bool
    data: bytes | None = None
    size: int | None = None
    error_message: str | None = None
    request_id: str | None = None
    status: HALResultStatus = HALResultStatus.COMPLETED
    batch_id: str | None = None

def _hal_worker_process(exhal_path: str, inhal_path: str, request_queue: mp.Queue[HALRequest | None], result_queue: mp.Queue[HALResult]) -> None:
    """Worker process function for HAL operations.

    Runs in a separate process and handles HAL compression/decompression requests.
    """
    import os
    import queue
    import signal

    # Ignore interrupt signals in worker processes
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    # Setup basic logging for worker process to prevent FileNotFoundError issues
    worker_logger = None
    try:
        from utils.logging_config import get_logger
        worker_logger = get_logger(f"hal_worker_{os.getpid()}")
    except Exception:
        # If logging fails, create basic logger to avoid failures
        import logging
        worker_logger = logging.getLogger(f"hal_worker_{os.getpid()}")
        worker_logger.setLevel(logging.DEBUG)
        if not worker_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(levelname)s - %(name)s - %(message)s"))
            worker_logger.addHandler(handler)

    worker_logger.debug(f"HAL worker process {os.getpid()} started")

    while True:
        request: HALRequest | None = None  # Initialize for error handling
        try:
            # Get request from queue (blocking) with error handling for closed pipes
            try:
                request = request_queue.get(timeout=0.5)  # Shorter timeout for faster shutdown
            except (BrokenPipeError, EOFError, OSError, ConnectionResetError):
                # Queue closed, main process has shut down - this is normal during cleanup
                worker_logger.debug(f"Worker process {os.getpid()}: Request queue closed, normal shutdown")
                break
            except queue.Empty:
                # Timeout is normal, continue waiting
                continue
            except Exception as e:
                # Other queue errors (e.g., queue corrupted)
                worker_logger.debug(f"Worker process {os.getpid()}: Queue error, exiting: {e.__class__.__name__}")
                break

            if request is None:  # Shutdown signal
                worker_logger.debug(f"Worker process {os.getpid()}: Received shutdown signal")
                break

            # Process the request
            if request.operation == "decompress":
                result = _process_decompress(exhal_path, request)
            elif request.operation == "compress":
                result = _process_compress(inhal_path, request)
            else:
                result = HALResult(
                    success=False,
                    error_message=f"Unknown operation: {request.operation}",
                    request_id=request.request_id,
                    batch_id=request.batch_id
                )

            # Put result in queue with error handling for closed pipes
            try:
                result_queue.put(result)
            except (BrokenPipeError, EOFError, OSError, ConnectionResetError) as e:
                # Queue closed, main process has shut down
                worker_logger.debug(f"Worker process {os.getpid()}: Queue closed, exiting gracefully: {e}")
                break
            except Exception as e:
                # Other result queue errors
                worker_logger.debug(f"Worker process {os.getpid()}: Result queue error, exiting: {e}")
                break

        except queue.Empty:
            continue  # Keep waiting for requests
        except (BrokenPipeError, EOFError, OSError, ConnectionResetError) as e:
            # Pipe/queue closed, exit gracefully
            worker_logger.debug(f"Worker process {os.getpid()}: Connection closed during request handling: {e}")
            break
        except Exception as e:
            # Send error result if queue is still open
            try:
                result = HALResult(
                    success=False,
                    error_message=f"Worker process error: {e!s}",
                    request_id=getattr(request, "request_id", None) if request is not None else None,
                    batch_id=getattr(request, "batch_id", None) if request is not None else None
                )
                result_queue.put(result)
            except (BrokenPipeError, EOFError, OSError, ConnectionResetError):
                # Queue closed, exit gracefully
                worker_logger.debug(f"Worker process {os.getpid()}: Cannot send error result, queue closed")
                break
            except Exception:
                # Any other error sending result, just exit
                worker_logger.debug(f"Worker process {os.getpid()}: Cannot send error result, unknown error")
                break

    worker_logger.debug(f"HAL worker process {os.getpid()} exiting")

def _process_decompress(exhal_path: str, request: HALRequest) -> HALResult:
    """Process decompression request in worker process."""
    try:
        # Check if ROM file exists before processing
        if not Path(request.rom_path).exists():
            return HALResult(
                success=False,
                error_message=f"ROM file not found: {request.rom_path}",
                request_id=request.request_id,
                batch_id=request.batch_id
            )

        # Create temporary output file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            output_path = tmp.name

        try:
            # Run exhal: exhal romfile offset outfile
            # Ensure offset is properly formatted as hex with type validation
            if request.offset < 0:
                return HALResult(
                    success=False,
                    error_message=f"Invalid offset: {request.offset} (must be non-negative integer)",
                    request_id=request.request_id,
                    batch_id=request.batch_id
                )

            offset_hex = f"0x{request.offset:X}"
            cmd = [exhal_path, request.rom_path, offset_hex, output_path]

            result = subprocess.run(cmd, check=False, capture_output=True, text=True)

            if result.returncode != 0:
                return HALResult(
                    success=False,
                    error_message=f"Decompression failed: {result.stderr}",
                    request_id=request.request_id,
                    batch_id=request.batch_id
                )

            # Read decompressed data
            data = Path(output_path).read_bytes()

            return HALResult(
                success=True,
                data=data,
                size=len(data),
                request_id=request.request_id,
                batch_id=request.batch_id
            )

        finally:
            # Clean up temp file
            with contextlib.suppress(Exception):
                Path(output_path).unlink()

    except Exception as e:
        return HALResult(
            success=False,
            error_message=f"Decompression error: {e!s}",
            request_id=request.request_id,
            batch_id=request.batch_id
        )

def _process_compress(inhal_path: str, request: HALRequest) -> HALResult:
    """Process compression request in worker process."""
    try:
        if not request.data:
            return HALResult(
                success=False,
                error_message="No data provided for compression",
                request_id=request.request_id,
                batch_id=request.batch_id
            )

        # Write input to temp file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(request.data)
            tmp_path = tmp.name

        try:
            if request.output_path:
                # Compress to file
                cmd = [inhal_path]
                if request.fast:
                    cmd.append("-fast")
                cmd.extend(["-n", tmp_path, request.output_path])

                result = subprocess.run(cmd, check=False, capture_output=True, text=True)

                if result.returncode != 0:
                    return HALResult(
                        success=False,
                        error_message=f"Compression failed: {result.stderr}",
                        request_id=request.request_id,
                        batch_id=request.batch_id
                    )

                # Get compressed size
                compressed_size = Path(request.output_path).stat().st_size

                return HALResult(
                    success=True,
                    size=compressed_size,
                    request_id=request.request_id,
                    batch_id=request.batch_id
                )
            # ROM injection - not supported in pool mode for safety
            return HALResult(
                success=False,
                error_message="ROM injection not supported in pool mode",
                request_id=request.request_id,
                batch_id=request.batch_id
            )

        finally:
            # Clean up temp file
            with contextlib.suppress(Exception):
                Path(tmp_path).unlink()

    except Exception as e:
        return HALResult(
            success=False,
            error_message=f"Compression error: {e!s}",
            request_id=request.request_id,
            batch_id=request.batch_id
        )

class HALProcessPool:
    """Singleton HAL process pool for efficient compression/decompression operations."""

    _instance = None
    _lock = threading.Lock()
    _cleanup_registered = False

    def __new__(cls) -> HALProcessPool:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Only initialize once
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._pool_lock: threading.RLock = threading.RLock()
        self._pool_initialized = False  # Use a boolean flag for initialization status
        self._manager: SyncManager | None = None
        self._request_queue: mp.Queue[HALRequest | None] | None = None
        self._result_queue: mp.Queue[HALResult] | None = None
        self._processes: list[mp.Process] = []
        self._process_pids: list[int] = []  # Track PIDs for debugging
        self._shutdown = False
        self._pool_size = HAL_POOL_SIZE_DEFAULT
        self._exhal_path = None
        self._inhal_path = None
        self._qt_cleanup_connected = False

        # Register comprehensive cleanup hooks
        self._register_cleanup_hooks()

        logger.info("HALProcessPool singleton initialized")

    def _register_cleanup_hooks(self) -> None:
        """Register cleanup hooks to prevent memory leaks"""
        # Thread-safe check-then-act to prevent duplicate cleanup registration
        with HALProcessPool._lock:
            if HALProcessPool._cleanup_registered:
                return
            HALProcessPool._cleanup_registered = True

        # Register atexit handler with suppress_logging_errors to prevent I/O errors during shutdown
        @suppress_logging_errors
        def cleanup_at_exit() -> None:
            try:
                self.shutdown()
            except Exception:
                pass  # Ignore errors during shutdown

        atexit.register(cleanup_at_exit)
        # Qt cleanup is registered separately in _connect_qt_cleanup() during initialize()

    def initialize(self, exhal_path: str, inhal_path: str, pool_size: int = HAL_POOL_SIZE_DEFAULT) -> bool:
        """Initialize the process pool with HAL tool paths.

        Returns:
            True if initialization successful, False otherwise
        """
        with self._pool_lock:
            if self._pool_initialized:
                logger.debug("Pool already initialized")
                return True

            try:
                # Validate pool size
                pool_size = max(HAL_POOL_SIZE_MIN, min(pool_size, HAL_POOL_SIZE_MAX))
                self._pool_size = pool_size
                self._exhal_path = exhal_path
                self._inhal_path = inhal_path

                # Create multiprocessing manager for queues
                self._manager = mp.Manager()
                self._request_queue = self._manager.Queue()  # type: ignore[assignment] - Manager.Queue() returns untyped proxy
                self._result_queue = self._manager.Queue()  # type: ignore[assignment] - Manager.Queue() returns untyped proxy

                # Start worker processes (daemon=False to prevent zombie processes)
                logger.info(f"Starting HAL process pool with {pool_size} workers")
                for i in range(pool_size):
                    p = mp.Process(
                        target=_hal_worker_process,
                        args=(exhal_path, inhal_path, self._request_queue, self._result_queue),
                        daemon=False  # Changed from True to prevent zombie processes
                    )
                    p.start()
                    self._processes.append(p)
                    if p.pid is not None:  # Ensure PID is available before appending
                        self._process_pids.append(p.pid)
                    logger.debug(f"Started worker process {i+1}/{pool_size}: PID {p.pid}")

                # Connect to Qt application aboutToQuit signal if available
                self._connect_qt_cleanup()

                # Create weak references to processes for better cleanup tracking
                self._process_refs = [weakref.ref(p) for p in self._processes]

                # Test ALL workers with individual test requests
                # This ensures every worker in the pool is responsive, not just one
                test_requests = [
                    HALRequest(
                        operation="decompress",
                        rom_path="",  # Will fail but tests communication
                        offset=0,
                        request_id=f"init_test_{i}"
                    )
                    for i in range(pool_size)
                ]

                if self._request_queue is None:
                    raise HALPoolError("Request queue not initialized")
                if self._result_queue is None:
                    raise HALPoolError("Result queue not initialized")

                # Submit test requests to all workers
                for test_req in test_requests:
                    self._request_queue.put(test_req)

                # Wait for ALL workers to respond
                per_worker_timeout = 2.0
                responses_received = 0
                for _ in range(pool_size):
                    try:
                        self._result_queue.get(timeout=per_worker_timeout)
                        responses_received += 1
                    except queue.Empty:
                        # Worker didn't respond in time, continue to check others
                        break

                # FIX T2.4: Require minimum ratio of workers to respond
                min_required = max(1, int(pool_size * HAL_POOL_MIN_WORKER_RATIO))

                if responses_received == 0:
                    raise HALPoolError("Pool communication test failed - no workers responded")
                elif responses_received < min_required:
                    # Insufficient workers - fail initialization
                    raise HALPoolError(
                        f"Insufficient pool workers: {responses_received}/{pool_size} responded "
                        f"(minimum {min_required} required, ratio={HAL_POOL_MIN_WORKER_RATIO})"
                    )
                elif responses_received < pool_size:
                    # Partial pool but meets minimum - warn and continue
                    safe_warning(
                        logger,
                        f"HAL pool partially initialized: {responses_received}/{pool_size} workers responded. "
                        f"Meets minimum threshold ({min_required}), but some operations may be slower."
                    )
                else:
                    logger.debug(f"Pool communication test successful - all {pool_size} workers responded")

                self._pool_initialized = True  # Mark as initialized
                logger.info("HAL process pool initialized successfully")
                return True

            except Exception as e:
                logger.exception(f"Failed to initialize HAL process pool: {e}")
                # Use force_cleanup on init failure to ensure no zombie processes
                self.force_reset()
                return False

    def _connect_qt_cleanup(self) -> None:
        """Connect cleanup to QApplication.aboutToQuit signal if Qt is available."""
        if not QT_AVAILABLE or self._qt_cleanup_connected:
            return

        try:
            if QApplication is not None:
                app = QApplication.instance()
                if app is not None:
                    app.aboutToQuit.connect(self.shutdown)
                    self._qt_cleanup_connected = True
                    logger.debug("Connected HAL pool cleanup to QApplication.aboutToQuit signal")
        except Exception as e:
            logger.debug(f"Could not connect to QApplication.aboutToQuit: {e}")

    def submit_request(self, request: HALRequest) -> HALResult:
        """Submit a single request to the pool and wait for result.

        Args:
            request: HAL operation request

        Returns:
            HAL operation result
        """
        if not self._pool_initialized or self._shutdown:
            return HALResult(
                success=False,
                error_message="Pool not initialized or shutting down",
                request_id=request.request_id
            )

        # Set timeout before try block to ensure it's available in exception handlers
        timeout = HAL_POOL_TIMEOUT_SECONDS

        try:
            # Put request in queue
            if self._request_queue is not None:
                self._request_queue.put(request)
            else:
                raise HALPoolError("Request queue not initialized")

            # Wait for result with timeout
            if self._result_queue is not None:
                return self._result_queue.get(timeout=timeout)
            raise HALPoolError("Result queue not initialized")

        except queue.Empty:
            return HALResult(
                success=False,
                error_message=f"Operation timed out after {timeout} seconds",
                request_id=request.request_id
            )
        except Exception as e:
            return HALResult(
                success=False,
                error_message=f"Pool error: {e!s}",
                request_id=request.request_id
            )

    def submit_batch(self, requests: list[HALRequest]) -> list[HALResult]:
        """Submit multiple requests to the pool for parallel processing.

        Args:
            requests: List of HAL operation requests

        Returns:
            List of HAL operation results in same order as requests.
            Each result includes explicit status (COMPLETED or TIMED_OUT).
        """
        if not self._pool_initialized or self._shutdown:
            return [
                HALResult(
                    success=False,
                    error_message="Pool not initialized or shutting down",
                    request_id=req.request_id,
                    status=HALResultStatus.COMPLETED,  # Not a timeout, it's a setup error
                )
                for req in requests
            ]

        if not requests:
            return []

        try:
            # Generate unique batch ID to prevent result misattribution between batches
            current_batch_id = f"batch_{uuid.uuid4().hex[:12]}"

            # Validate unique request IDs to prevent result collisions
            # HALRequest is a NamedTuple (immutable), so we need to create new instances
            request_ids = [req.request_id for req in requests]
            non_none_ids = [rid for rid in request_ids if rid is not None]
            if len(set(non_none_ids)) != len(non_none_ids):
                safe_warning(
                    logger,
                    "Non-unique request IDs detected in batch - reassigning unique IDs"
                )
                # Create new requests with unique IDs and batch_id to prevent result collision
                requests = [
                    req._replace(request_id=f"batch_{id(req)}_{i}", batch_id=current_batch_id)
                    for i, req in enumerate(requests)
                ]
            elif None in request_ids:
                safe_warning(
                    logger,
                    "None request_id detected in batch - assigning unique IDs"
                )
                # Create new requests for those with None IDs, add batch_id to all
                requests = [
                    req._replace(
                        request_id=f"batch_none_{id(req)}_{i}" if req.request_id is None else req.request_id,
                        batch_id=current_batch_id
                    )
                    for i, req in enumerate(requests)
                ]
            else:
                # All IDs valid, just add batch_id
                requests = [req._replace(batch_id=current_batch_id) for req in requests]

            # Submit all requests
            for req in requests:
                if self._request_queue is not None:
                    self._request_queue.put(req)
                else:
                    raise HALPoolError("Request queue not initialized")

            # Collect results with per-request timeout guarantee
            results: dict[str | None, HALResult] = {}
            total_timeout = HAL_POOL_TIMEOUT_SECONDS
            # Minimum 5 seconds per request, but don't exceed total timeout
            per_request_timeout = max(5.0, total_timeout / len(requests))
            deadline = time.time() + total_timeout

            received_count = 0
            for _ in requests:
                # Each request gets at least per_request_timeout, but respect overall deadline
                remaining = deadline - time.time()
                wait_time = min(per_request_timeout, max(0.1, remaining))

                if remaining <= 0:
                    safe_warning(
                        logger,
                        f"Batch timeout: received {received_count}/{len(requests)} results"
                    )
                    break

                try:
                    if self._result_queue is not None:
                        result = self._result_queue.get(timeout=wait_time)
                    else:
                        raise HALPoolError("Result queue not initialized")

                    # Validate batch_id to prevent misattribution from stale results
                    if result.batch_id == current_batch_id:
                        if result.request_id:
                            results[result.request_id] = result
                            received_count += 1
                    else:
                        # Stale result from previous batch - discard and log
                        safe_debug(
                            logger,
                            f"Discarding stale result with batch_id={result.batch_id} (expected {current_batch_id})"
                        )
                except queue.Empty:
                    # Individual request timed out, but continue trying for others
                    # This prevents one slow request from blocking all subsequent results
                    continue

            # Drain any late-arriving results to prevent queue pollution
            # Use zero timeout to capture anything already in queue
            if received_count < len(requests):
                drained_count = 0
                discarded_stale = 0
                while True:
                    try:
                        if self._result_queue is not None:
                            late_result = self._result_queue.get(timeout=0.0)
                            # Only accept results from current batch
                            if late_result.batch_id == current_batch_id:
                                if late_result.request_id:
                                    results[late_result.request_id] = late_result
                                    drained_count += 1
                            else:
                                discarded_stale += 1
                        else:
                            break
                    except queue.Empty:
                        break
                if drained_count > 0:
                    safe_debug(
                        logger,
                        f"Drained {drained_count} late-arriving results from queue"
                    )
                if discarded_stale > 0:
                    safe_debug(
                        logger,
                        f"Discarded {discarded_stale} stale results from previous batches"
                    )

            # Return results in same order as requests with explicit status
            final_results = []
            for req in requests:
                if req.request_id in results:
                    final_results.append(results[req.request_id])
                else:
                    # Result was not received - mark as TIMED_OUT
                    final_results.append(
                        HALResult(
                            success=False,
                            error_message=f"Operation timed out after {total_timeout}s",
                            request_id=req.request_id,
                            status=HALResultStatus.TIMED_OUT,
                            batch_id=current_batch_id,
                        )
                    )
            return final_results

        except Exception as e:
            logger.exception(f"Batch processing error: {e}")
            return [
                HALResult(
                    success=False,
                    error_message=f"Batch error: {e!s}",
                    request_id=req.request_id,
                    status=HALResultStatus.COMPLETED,  # Error, not timeout
                )
                for req in requests
            ]

    @suppress_logging_errors
    def shutdown(self) -> None:
        """Properly shutdown pool with process joining."""
        with self._pool_lock:
            if not self._pool_initialized or self._shutdown:
                return

            self._shutdown = True
            safe_info(logger, f"Shutting down HAL process pool (PIDs: {self._process_pids})")

            # Send shutdown signals to all worker processes
            if self._request_queue is not None:
                try:
                    for _ in range(len(self._processes)):
                        self._request_queue.put(None)  # None signals shutdown
                except Exception as e:
                    safe_debug(logger, f"Error sending shutdown signals: {e}")

            # Wait for processes to finish gracefully with shorter timeouts
            # Create defensive copy to avoid issues if list is modified during iteration
            processes_snapshot = list(self._processes)
            for p in processes_snapshot:
                try:
                    # Give process a short time to exit cleanly
                    p.join(timeout=0.5)
                    if p.is_alive():
                        safe_debug(logger, f"Process {p.pid} did not shutdown gracefully, terminating")
                        p.terminate()
                        p.join(timeout=0.5)
                        if p.is_alive():
                            safe_debug(logger, f"Process {p.pid} did not terminate, killing")
                            p.kill()
                            p.join(timeout=0.1)  # Brief wait after kill
                except Exception as e:
                    safe_debug(logger, f"Error shutting down process {getattr(p, 'pid', 'unknown')}: {e}")

            self._pool_initialized = False

            # Close manager properly with timeout
            if self._manager:
                try:
                    # Use a thread with timeout for manager shutdown
                    def shutdown_manager():
                        try:
                            if self._manager is not None:
                                self._manager.shutdown()
                        except (BrokenPipeError, EOFError, OSError, ConnectionResetError):
                            pass  # Expected during shutdown
                        except Exception as e:
                            safe_debug(logger, f"Manager shutdown error: {e}")

                    # Use non-daemon thread for proper cleanup tracking
                    # Daemon threads are killed on exit, potentially leaving resources leaked
                    shutdown_thread = threading.Thread(target=shutdown_manager)
                    shutdown_thread.daemon = False
                    shutdown_thread.start()

                    # Escalating wait: 1s initial, then 2s additional if needed
                    shutdown_thread.join(timeout=1.0)
                    if shutdown_thread.is_alive():
                        safe_debug(logger, "Manager shutdown taking longer, waiting additional 2s")
                        shutdown_thread.join(timeout=2.0)
                        if shutdown_thread.is_alive():
                            safe_warning(
                                logger,
                                "Manager shutdown did not complete in 3s - forcing cleanup"
                            )
                except Exception as e:
                    safe_debug(logger, f"Error during manager shutdown: {e}")
                finally:
                    self._manager = None

            # Clear all references
            self._processes.clear()
            self._process_pids.clear()
            if hasattr(self, '_process_refs'):
                self._process_refs.clear()
            self._request_queue = None
            self._result_queue = None

            safe_info(logger, "HAL process pool shutdown complete")

    def _force_cleanup_zombies(self):
        """Emergency cleanup for zombie processes with robust error handling."""
        if not self._process_pids:
            logger.debug("No process PIDs to clean up")
            return

        logger.debug(f"Checking {len(self._process_pids)} processes for zombies")
        zombies_found = 0

        for pid in self._process_pids[:]:  # Create a copy to avoid modification during iteration
            try:
                # Check if process still exists (os.kill with signal 0 just checks existence)
                os.kill(pid, 0)
                logger.warning(f"Zombie process detected: PID {pid}")
                zombies_found += 1

                try:
                    # First try SIGTERM
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.1)

                    # Check if it's still there
                    try:
                        os.kill(pid, 0)
                        # Still alive, use SIGKILL
                        os.kill(pid, signal.SIGKILL)
                        time.sleep(0.1)
                        logger.debug(f"Forcefully cleaned up zombie process {pid}")
                    except (OSError, ProcessLookupError):
                        logger.debug(f"Zombie process {pid} terminated after SIGTERM")

                except (OSError, ProcessLookupError):
                    # Process terminated between checks
                    logger.debug(f"Process {pid} no longer exists during cleanup")
                except Exception as e:
                    logger.warning(f"Error sending signals to process {pid}: {e}")

            except (OSError, ProcessLookupError):
                # Process doesn't exist anymore - this is normal
                logger.debug(f"Process {pid} already terminated")
            except Exception as e:
                logger.debug(f"Error checking process {pid}: {e}")

        if zombies_found > 0:
            logger.warning(f"Found and attempted cleanup of {zombies_found} zombie processes")
        else:
            logger.debug("No zombie processes found")

    def __del__(self):
        """Destructor to ensure cleanup happens even if shutdown is not called explicitly."""
        try:
            # More defensive checks during destructor
            if (hasattr(self, "_pool_initialized") and
                hasattr(self, "_shutdown") and
                self._pool_initialized and
                not self._shutdown):
                safe_debug(logger, "HALProcessPool destructor triggered - cleaning up resources")
                self.shutdown()
        except Exception:
            # Ignore all errors in destructor to prevent issues during interpreter shutdown
            # This includes AttributeError if attributes don't exist, or any other errors
            pass

    @property
    def is_initialized(self) -> bool:
        """Check if pool is initialized and ready."""
        return self._pool_initialized and not self._shutdown

    @property
    def _pool(self) -> bool | None:
        """Backward compatibility property for tests.

        Returns None when not initialized, True when initialized.
        This maintains the interface that tests expect.
        """
        return True if self._pool_initialized else None

    @_pool.setter
    def _pool(self, value: bool | None) -> None:
        """Setter for backward compatibility with tests.

        Tests may set _pool directly to simulate different states.
        """
        self._pool_initialized = bool(value) if value is not None else False

    def force_reset(self) -> None:
        """Force reset the pool state - for test cleanup and error recovery.

        This is more aggressive than shutdown() and will reset the singleton state.
        Use with caution - mainly for test cleanup or error recovery scenarios.
        """
        with self._pool_lock:
            safe_warning(logger, "Force resetting HAL process pool")

            # Mark as shutdown first to prevent new operations
            self._shutdown = True

            # Immediately terminate and kill all processes
            if self._processes:
                for p in self._processes:
                    try:
                        if p.is_alive():
                            p.terminate()
                            # Minimal wait before force kill
                            time.sleep(0.1)
                            if p.is_alive():
                                p.kill()
                    except Exception as e:
                        safe_debug(logger, f"Error force terminating process {getattr(p, 'pid', 'unknown')}: {e}")

            # Direct manager shutdown with minimal timeout
            if self._manager is not None:
                try:
                    # Force manager shutdown in a thread with very short timeout
                    def force_shutdown_manager():
                        try:
                            if self._manager is not None:
                                self._manager.shutdown()
                        except (BrokenPipeError, EOFError, OSError, ConnectionResetError):
                            pass  # Expected during force shutdown
                        except Exception:
                            pass  # Ignore all errors during force shutdown

                    shutdown_thread = threading.Thread(target=force_shutdown_manager)
                    shutdown_thread.daemon = True
                    shutdown_thread.start()
                    shutdown_thread.join(timeout=0.2)  # Very short timeout for force reset
                except Exception as e:
                    safe_debug(logger, f"Error force shutting down manager: {e}")

            # Clear all state including weak references
            self._processes.clear()
            self._process_pids.clear()
            if hasattr(self, '_process_refs'):
                self._process_refs.clear()
            self._pool_initialized = False
            self._manager = None
            self._request_queue = None
            self._result_queue = None
            self._shutdown = False  # Allow re-initialization

            # Skip explicit gc.collect() during cleanup
            # Reason: gc.collect() can trigger finalization of PySide6/Qt objects
            # while background threads are still running, which causes segfaults.
            # The Python GC will clean up remaining objects naturally when safe.

            safe_debug(logger, "HAL process pool force reset complete")

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset the singleton instance - for testing purposes only."""
        with cls._lock:
            # Reset flag first to ensure it happens even if force_reset fails
            cls._cleanup_registered = False  # Allow re-registration

            if cls._instance is not None:
                try:
                    cls._instance.force_reset()
                except Exception as e:
                    # Only log if not during interpreter shutdown
                    if not sys.is_finalizing():
                        safe_debug(logger, f"Error during singleton reset: {e}")
                cls._instance = None
                # Only log if not during interpreter shutdown
                if not sys.is_finalizing():
                    logger.debug("HAL process pool singleton reset")

    @classmethod
    def reset_for_tests(cls) -> None:
        """Reset singleton state for test isolation.

        This is the ONLY approved way to reset the HAL pool in tests.
        Alias for reset_singleton() to match ManagerRegistry API.

        WARNING: This method is for test infrastructure only.
        Do not use in production code.
        """
        cls.reset_singleton()

class HALCompressor:
    """Handles HAL compression/decompression for ROM injection"""

    def __init__(
        self, exhal_path: str | None = None, inhal_path: str | None = None, use_pool: bool = True
    ):
        """
        Initialize HAL compressor.

        Args:
            exhal_path: Path to exhal executable (decompressor)
            inhal_path: Path to inhal executable (compressor)
            use_pool: Whether to use process pool for performance
        """
        logger.info("Initializing HAL compressor")
        # Try to find tools in various locations
        self.exhal_path: str = self._find_tool("exhal", exhal_path)
        self.inhal_path: str = self._find_tool("inhal", inhal_path)
        logger.info(f"HAL compressor initialized with exhal={self.exhal_path}, inhal={self.inhal_path}")

        # Initialize process pool if requested
        pool_disabled = False
        if use_pool and _is_wsl_environment():
            logger.warning("WSL detected; disabling HAL process pool")
            use_pool = False
            pool_disabled = True

        self._use_pool = use_pool
        self._pool = None
        self._pool_failed = pool_disabled

        if use_pool:
            try:
                self._pool = HALProcessPool()
                if self._pool.initialize(self.exhal_path, self.inhal_path):
                    logger.info("HAL process pool enabled for enhanced performance")
                else:
                    logger.warning("HAL process pool initialization failed - falling back to subprocess mode")
                    self._pool = None
                    self._pool_failed = True
            except Exception as e:
                logger.warning(f"Could not enable HAL process pool: {e} - falling back to subprocess mode")
                self._pool = None
                self._pool_failed = True

    def _find_tool(self, tool_name: str, provided_path: str | None = None) -> str:
        """Find HAL compression tool executable"""
        logger.info(f"Searching for {tool_name} tool")

        if provided_path:
            logger.debug(f"Checking provided path: {provided_path}")
            if Path(provided_path).is_file():
                logger.info(f"Using provided {tool_name} at: {provided_path}")
                return provided_path
            logger.warning(f"Provided path does not exist: {provided_path}")

        # Platform-specific executable suffix
        exe_suffix = ".exe" if platform.system() == "Windows" else ""
        tool_with_suffix = f"{tool_name}{exe_suffix}"

        # Get absolute path to spritepal directory to avoid working directory dependency
        # This file is in core/hal_compression.py, so spritepal is the parent directory
        spritepal_dir = Path(__file__).parent.parent
        logger.debug(f"SpritePal directory: {spritepal_dir}")

        # Search locations with robust path handling
        search_paths = [
            # Compiled tools directory (preferred) - use absolute paths
            spritepal_dir / "tools" / tool_with_suffix,
            # Alternative tools locations relative to spritepal
            spritepal_dir.parent / "tools" / tool_with_suffix,  # exhal-master/tools/
            # Archive directory (from codebase structure)
            spritepal_dir.parent / "archive" / "obsolete_test_images" / "ultrathink" / tool_name,
            spritepal_dir.parent / "archive" / "obsolete_test_images" / "ultrathink" / tool_with_suffix,
            # Working directory relative paths (for backward compatibility)
            Path.cwd() / "tools" / tool_with_suffix,
            Path.cwd() / tool_with_suffix,
            # Parent directories from current working directory
            Path.cwd().parent / tool_name,
            Path.cwd().parent.parent / tool_name,
        ]

        # Add system PATH as string for shutil.which
        system_tool = shutil.which(tool_name)
        if system_tool:
            search_paths.append(Path(system_tool))

        logger.debug(f"Searching {len(search_paths)} locations for {tool_name}")
        for i, path in enumerate(search_paths, 1):
            try:
                # All paths in search_paths are already Path objects
                full_path = path.resolve()

                if full_path.is_file():
                    logger.info(f"Found {tool_name} at location {i}/{len(search_paths)}: {full_path}")
                    # Check if file is executable
                    if not os.access(full_path, os.X_OK):
                        logger.warning(f"Found {tool_name} but it may not be executable: {full_path}")
                    return str(full_path)
                logger.debug(f"Location {i}/{len(search_paths)}: Not found at {full_path}")
            except Exception as e:
                logger.debug(f"Location {i}/{len(search_paths)}: Error checking {path}: {e}")

        logger.error(f"Could not find {tool_name} executable in any search path")
        raise HALCompressionError(
            f"Could not find {tool_name} executable. "
            f"Please run 'python compile_hal_tools.py' to build for your platform."
        )

    def decompress_from_rom(
        self, rom_path: str, offset: int, output_path: str | None = None
    ) -> bytes:
        """
        Decompress data from ROM at specified offset.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM where compressed data starts
            output_path: path to save decompressed data

        Returns:
            Decompressed data as bytes
        """
        logger.info(f"Decompressing from ROM: {rom_path} at offset 0x{offset:X}")

        # Validate offset before subprocess/pool operations
        if offset < 0:
            raise ValueError(f"Invalid negative offset: {offset}")
        rom_size = Path(rom_path).stat().st_size
        if offset >= rom_size:
            raise ValueError(f"Offset 0x{offset:X} exceeds ROM size 0x{rom_size:X}")

        # Try to use pool if available
        if self._pool and self._pool.is_initialized:
            request = HALRequest(
                operation="decompress",
                rom_path=rom_path,
                offset=offset,
                output_path=output_path,
                request_id=f"decompress_{offset}"
            )

            result = self._pool.submit_request(request)

            if result.success and result.data:
                logger.info(f"Successfully decompressed {len(result.data)} bytes using pool")
                # Save to output file if specified
                if output_path:
                    Path(output_path).write_bytes(result.data)
                return result.data
            if not self._pool_failed:
                # Pool operation failed, fall back to subprocess
                logger.warning(f"Pool decompression failed: {result.error_message}, falling back to subprocess")

        # Subprocess fallback (original implementation)
        # Create temporary output file if not specified
        if output_path is None:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                output_path = tmp.name

        try:
            # Run exhal: exhal romfile offset outfile
            cmd = [self.exhal_path, rom_path, f"0x{offset:X}", output_path]
            logger.debug(f"Running command: {' '.join(cmd)}")

            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            logger.debug(f"Command completed with return code: {result.returncode}")

            if result.stdout:
                logger.debug(f"stdout: {result.stdout.strip()}")
            if result.stderr:
                logger.debug(f"stderr: {result.stderr.strip()}")

            if result.returncode != 0:
                logger.error(f"Decompression failed with return code {result.returncode}")
                raise HALCompressionError(f"Decompression failed: {result.stderr}")

            # Read decompressed data
            data = Path(output_path).read_bytes()

            logger.info(f"Successfully decompressed {len(data)} bytes from ROM offset 0x{offset:X}")
            return data

        finally:
            # Clean up temp file if we created one
            if output_path and output_path.startswith(tempfile.gettempdir()):
                with contextlib.suppress(Exception):
                    Path(output_path).unlink()

    def compress_to_file(
        self, input_data: bytes, output_path: str, fast: bool = False
    ) -> int:
        """
        Compress data to a file.

        Args:
            input_data: Data to compress
            output_path: Path to save compressed data
            fast: Use fast compression mode

        Returns:
            Size of compressed data
        """
        logger.info(f"Compressing {len(input_data)} bytes to file: {output_path}")

        # Check size limit
        if len(input_data) > DATA_SIZE:
            logger.error(f"Input data too large: {len(input_data)} bytes (max {DATA_SIZE})")
            raise HALCompressionError(
                f"Input data too large: {len(input_data)} bytes (max {DATA_SIZE})"
            )

        # Write input to temp file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(input_data)
            tmp_path = tmp.name

        try:
            # Run inhal: inhal [-fast] -n infile outfile
            cmd = [self.inhal_path]
            if fast:
                cmd.append("-fast")
                logger.debug("Using fast compression mode")
            cmd.extend(["-n", tmp_path, output_path])

            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            logger.debug(f"Command completed with return code: {result.returncode}")

            if result.stdout:
                logger.debug(f"stdout: {result.stdout.strip()}")
            if result.stderr:
                logger.debug(f"stderr: {result.stderr.strip()}")

            if result.returncode != 0:
                logger.error(f"Compression failed with return code {result.returncode}: {result.stderr}")
                raise HALCompressionError(f"Compression failed: {result.stderr}")

            # Get compressed size
            compressed_size = Path(output_path).stat().st_size
            compression_ratio = (len(input_data) - compressed_size) / len(input_data) * 100
            logger.info(f"Compressed to {compressed_size} bytes ({compression_ratio:.1f}% reduction)")
            return compressed_size

        finally:
            # Clean up temp file
            with contextlib.suppress(Exception):
                Path(tmp_path).unlink()

    def compress_to_rom(
        self,
        input_data: bytes,
        rom_path: str,
        offset: int,
        output_rom_path: str | None = None,
        fast: bool = False
    ) -> tuple[bool, str]:
        """
        Compress data and inject into ROM at specified offset.

        Args:
            input_data: Data to compress and inject
            rom_path: Path to input ROM file
            offset: Offset in ROM to inject compressed data
            output_rom_path: Path for output ROM (if None, modifies in place)
            fast: Use fast compression mode

        Returns:
            Tuple of (success, message)
        """
        logger.info(f"Compressing {len(input_data)} bytes to ROM: {rom_path} at offset 0x{offset:X}")

        # Check size limit
        if len(input_data) > DATA_SIZE:
            logger.error(f"Input data too large: {len(input_data)} bytes (max {DATA_SIZE})")
            return (
                False,
                f"Input data too large: {len(input_data)} bytes (max {DATA_SIZE})"
            )

        # If no output path, modify in place - but create backup first
        if output_rom_path is None:
            # Create backup before in-place modification (safety critical)
            try:
                backup_path = ROMBackupManager.create_backup(rom_path)
                logger.info(f"In-place mode: created safety backup at {backup_path}")
            except Exception as e:
                logger.error(f"Failed to create backup for in-place modification: {e}")
                return (
                    False,
                    f"Cannot modify ROM in-place: backup failed ({e}). "
                    "Specify an output path or free up disk space."
                )
            output_rom_path = rom_path
            logger.debug("Modifying ROM in place (backup created)")
        else:
            # Copy ROM to output path first
            logger.debug(f"Copying ROM to output path: {output_rom_path}")
            shutil.copy2(rom_path, output_rom_path)

        # Write input to temp file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(input_data)
            tmp_path = tmp.name

        try:
            # Run inhal: inhal [-fast] infile romfile offset
            cmd = [self.inhal_path]
            if fast:
                cmd.append("-fast")
                logger.debug("Using fast compression mode")
            cmd.extend([tmp_path, output_rom_path, f"0x{offset:X}"])

            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            logger.debug(f"Command completed with return code: {result.returncode}")

            if result.stdout:
                logger.debug(f"stdout: {result.stdout.strip()}")
            if result.stderr:
                logger.debug(f"stderr: {result.stderr.strip()}")

            if result.returncode != 0:
                logger.error(f"ROM injection failed with return code {result.returncode}")
                return False, f"ROM injection failed: {result.stderr}"

            # Extract size info from output if available
            compressed_size = "unknown"
            if "bytes" in result.stdout:
                # Try to parse compressed size from output
                match = re.search(r"(\d+)\s+bytes", result.stdout)
                if match:
                    compressed_size = match.group(1)

            logger.info(f"Successfully injected compressed data ({compressed_size} bytes) at offset 0x{offset:X}")
            return (
                True,
                f"Successfully injected compressed data ({compressed_size} bytes) at offset 0x{offset:X}"
            )

        finally:
            # Clean up temp file
            with contextlib.suppress(Exception):
                Path(tmp_path).unlink()

    def test_tools(self) -> tuple[bool, str]:
        """Test if HAL compression tools are available and working"""
        logger.info("Testing HAL compression tools")

        def _test_tool(tool_path: str, tool_name: str) -> str | None:
            """Helper to test a single HAL tool. Returns error message or None if success."""
            logger.debug(f"Testing {tool_name} at: {tool_path}")
            result = subprocess.run(
                [tool_path], check=False, capture_output=True, text=True
            )
            # Check both stdout and stderr for tool output
            output = (result.stdout + result.stderr).lower()
            if tool_name.lower() not in output and "usage" not in output:
                logger.error(f"{tool_name} tool not working correctly. Output: {output[:100]}")
                return f"{tool_name} tool not working correctly"
            return None

        try:
            # Test both tools
            error_msg = _test_tool(self.exhal_path, "exhal")
            if error_msg:
                return False, error_msg

            error_msg = _test_tool(self.inhal_path, "inhal")
            if error_msg:
                return False, error_msg

        except FileNotFoundError:
            logger.exception("HAL tools not found")
            error_msg = f"HAL tools not found. Please run 'python compile_hal_tools.py' to build for {platform.system()}"
        except OSError as e:
            logger.exception("OS error testing tools")
            if platform.system() == "Windows" and hasattr(e, "winerror") and getattr(e, "winerror", None) == 193:
                error_msg = "Wrong platform binaries. Please run 'python compile_hal_tools.py' to build for Windows"
            else:
                error_msg = f"Error testing tools: {e!s}"
        except subprocess.SubprocessError as e:
            logger.exception("Subprocess error testing tools")
            error_msg = f"Error running tools: {e!s}"
        except ValueError as e:
            logger.exception("Value error testing tools")
            error_msg = f"Invalid tool configuration: {e!s}"
        else:
            logger.info("HAL compression tools are working correctly")
            return True, "HAL compression tools are working correctly"

        return False, error_msg

    def decompress_batch(self, requests: list[tuple[str, int]]) -> list[tuple[bool, bytes | str]]:
        """
        Decompress multiple ROM offsets in parallel for improved performance.

        Args:
            requests: List of (rom_path, offset) tuples

        Returns:
            List of (success, data_or_error) tuples in same order as requests
        """
        if not self._pool or not self._pool.is_initialized:
            # Fall back to sequential processing
            logger.debug("Pool not available, using sequential batch processing")
            results = []
            for rom_path, offset in requests:
                try:
                    data = self.decompress_from_rom(rom_path, offset)
                    results.append((True, data))
                except Exception as e:
                    results.append((False, str(e)))
            return results

        # Convert to HALRequest objects
        hal_requests = [
            HALRequest(
                operation="decompress",
                rom_path=rom_path,
                offset=offset,
                request_id=f"batch_{i}"
            )
            for i, (rom_path, offset) in enumerate(requests)
        ]

        # Submit batch to pool
        logger.info(f"Processing batch of {len(requests)} decompression requests using pool")
        hal_results = self._pool.submit_batch(hal_requests)

        # Convert results
        results = []
        for result in hal_results:
            if result.success and result.data:
                results.append((True, result.data))
            else:
                results.append((False, result.error_message or "Unknown error"))

        return results

    def compress_batch(self, requests: list[tuple[bytes, str, bool]]) -> list[tuple[bool, int | str]]:
        """
        Compress multiple data blocks in parallel for improved performance.

        Args:
            requests: List of (data, output_path, fast) tuples

        Returns:
            List of (success, size_or_error) tuples in same order as requests
        """
        if not self._pool or not self._pool.is_initialized:
            # Fall back to sequential processing
            logger.debug("Pool not available, using sequential batch processing")
            results = []
            for data, output_path, fast in requests:
                try:
                    size = self.compress_to_file(data, output_path, fast)
                    results.append((True, size))
                except Exception as e:
                    results.append((False, str(e)))
            return results

        # Convert to HALRequest objects
        hal_requests = [
            HALRequest(
                operation="compress",
                rom_path="",  # Not used for compression
                offset=0,  # Not used for compression
                data=data,
                output_path=output_path,
                fast=fast,
                request_id=f"batch_compress_{i}"
            )
            for i, (data, output_path, fast) in enumerate(requests)
        ]

        # Submit batch to pool
        logger.info(f"Processing batch of {len(requests)} compression requests using pool")
        hal_results = self._pool.submit_batch(hal_requests)

        # Convert results
        results = []
        for result in hal_results:
            if result.success and result.size is not None:
                results.append((True, result.size))
            else:
                results.append((False, result.error_message or "Unknown error"))

        return results

    @property
    def pool_status(self) -> dict[str, object]:
        """Get status information about the HAL process pool."""
        if not self._pool:
            return {
                "enabled": False,
                "reason": "Pool initialization failed" if self._pool_failed else "Pool not configured"
            }

        return {
            "enabled": True,
            "initialized": self._pool.is_initialized,
            "pool_size": getattr(self._pool, "_pool_size", 0),
            "mode": "pool" if self._pool.is_initialized else "subprocess"
        }

# Module-level cleanup for memory leak prevention
# WARNING: SPOOKY ACTION AT A DISTANCE
# This atexit handler runs in UNDEFINED ORDER relative to other atexit handlers in:
# - core/managers/registry.py (_cleanup_global_registry)
# - core/managers/context.py (_cleanup_context_manager)
# If HAL tries to access managers that were already cleaned up, it will fail silently.
# If you add new atexit handlers, ensure they don't depend on HAL or vice versa.
@suppress_logging_errors
def _cleanup_hal_singleton():
    """Cleanup HAL singleton at module exit"""
    try:
        HALProcessPool.reset_singleton()
    except Exception:
        pass  # Ignore errors during cleanup

atexit.register(_cleanup_hal_singleton)
