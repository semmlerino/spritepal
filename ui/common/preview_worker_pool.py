"""
Preview Worker Pool for efficient thread reuse during preview generation.

This module provides a pool of reusable worker threads to prevent the overhead
of creating/destroying threads for each preview request. Features:
- Thread reuse (1-2 workers)
- Cancellation support for stale requests
- Automatic cleanup of idle workers
"""

from __future__ import annotations

import contextlib
import queue
import threading
import time
import weakref
from pathlib import Path
from typing import TYPE_CHECKING, override

from PySide6.QtCore import QMutex, QMutexLocker, QObject, Qt, QTimer, Signal

from core.offset_hunting import get_offset_candidates, has_nonzero_content
from core.services.worker_lifecycle import WorkerManager
from core.tile_utils import align_tile_data, calculate_dimensions_from_tile_data
from core.types import CompressionType
from ui.rom_extraction.workers.preview_worker import SpritePreviewWorker
from utils.logging_config import get_logger
from utils.rom_utils import detect_smc_offset

if TYPE_CHECKING:
    from weakref import ReferenceType

    from core.rom_extractor import ROMExtractor
    from ui.common.smart_preview_coordinator import SliderPreviewRequest

logger = get_logger(__name__)


class PooledPreviewWorker(SpritePreviewWorker):
    """
    Enhanced preview worker that supports cancellation and reuse.

    This worker extends the base SpritePreviewWorker with:
    - Request ID tracking for cancellation
    - Periodic cancellation checks during processing
    - Proper cleanup for pool reuse
    """

    # Enhanced signals with request ID
    preview_ready = Signal(
        int, bytes, int, int, str, int, int, int, bool, bytes
    )  # request_id, tile_data, width, height, name, compressed_size, slack_size, actual_offset, hal_succeeded, header_bytes
    preview_error = Signal(int, str)  # request_id, error_msg

    def __init__(self, pool_ref: ReferenceType[PreviewWorkerPool]) -> None:
        # Initialize with dummy values - actual values set per request
        super().__init__("", 0, "", None, None)  # type: ignore[arg-type]  # Dummy init, real values set via setup_request
        self._pool_ref = pool_ref
        self._state_mutex = QMutex()  # Protects _current_request_id and _is_processing
        self._current_request_id = 0
        self._cancel_requested = threading.Event()
        self._is_processing = False
        self._signals_connected = False
        self._being_destroyed = False  # Flag to prevent signal processing during cleanup
        self._full_decompression = False  # If True, don't limit decompression to 4KB
        self._force_compression_type: CompressionType | None = None  # If set, skip auto-detection

    def setup_request(self, request: SliderPreviewRequest, extractor: ROMExtractor) -> None:
        """Setup worker for new request."""
        self.rom_path = request.rom_path
        self.offset = request.offset
        self.sprite_name = f"manual_0x{request.offset:X}"
        self._full_decompression = request.full_decompression
        self._force_compression_type = request.force_compression_type
        logger.debug(
            f"[WORKER] setup_request: offset=0x{request.offset:X}, request_id={request.request_id}, "
            f"sprite_name={self.sprite_name}, full_decompression={self._full_decompression}, "
            f"force_compression_type={self._force_compression_type}"
        )
        self.extractor = extractor
        self.sprite_config = None
        # Thread-safe state updates
        with QMutexLocker(self._state_mutex):
            self._current_request_id = request.request_id
            if self._cancel_requested:
                self._cancel_requested.clear()
            self._is_processing = True

    def cancel_current_request(self) -> None:
        """Cancel the current request."""
        self._cancel_requested.set()
        with QMutexLocker(self._state_mutex):
            request_id = self._current_request_id
        logger.debug(f"Cancellation requested for worker processing request {request_id}")

    def _get_request_id(self) -> int:
        """Thread-safe getter for current request ID."""
        with QMutexLocker(self._state_mutex):
            return self._current_request_id

    def _is_currently_processing(self) -> bool:
        """Thread-safe getter for processing state."""
        with QMutexLocker(self._state_mutex):
            return self._is_processing

    def _set_processing(self, value: bool) -> None:
        """Thread-safe setter for processing state."""
        with QMutexLocker(self._state_mutex):
            self._is_processing = value

    @override
    def run(self) -> None:
        """Enhanced run method with cancellation support."""
        if not self._is_currently_processing():
            return

        try:
            # Check for cancellation before starting
            if self._cancel_requested.is_set():
                logger.debug(f"Request {self._get_request_id()} cancelled before processing")
                return

            # Call parent run method with cancellation checks
            self._run_with_cancellation_checks()

        except Exception as e:
            if not self._cancel_requested.is_set():
                request_id = self._get_request_id()
                logger.exception(f"Error in pooled preview worker for request {request_id}")
                self.preview_error.emit(request_id, str(e))
        finally:
            self._set_processing(False)
            # Return worker to pool (protect against pool being deleted by another thread
            # between weak ref check and method call - race condition during cleanup)
            pool = self._pool_ref()
            if pool:
                try:
                    pool._return_worker(self)
                except RuntimeError:
                    # Pool C++ object was deleted - expected during shutdown
                    logger.debug("Pool already deleted, cannot return worker")

    def _run_with_cancellation_checks(self) -> None:
        """Run preview generation with periodic cancellation checks."""
        # Cache request ID for logging (reduces mutex contention)
        request_id = self._get_request_id()

        # Check both Qt interruption and our cancel flag
        if self._cancel_requested.is_set() or self.isInterruptionRequested():
            logger.debug(f"Request {request_id} cancelled before starting")
            return

        # Validate ROM path
        if not self.rom_path or not self.rom_path.strip():
            raise FileNotFoundError("No ROM path provided")

        # Read ROM data with interruption check
        try:
            # Check interruption before file I/O
            if self.isInterruptionRequested():
                logger.debug(f"Request {request_id} interrupted before file read")
                return

            with Path(self.rom_path).open("rb") as f:
                rom_data = f.read()

            # Strip SMC header if present
            smc_offset = detect_smc_offset(rom_data)
            if smc_offset > 0:
                logger.debug(f"Stripping {smc_offset}-byte SMC header from ROM data")
                rom_data = rom_data[smc_offset:]
        except Exception as e:
            raise OSError(f"Error reading ROM file: {e}") from e

        # Check cancellation after file read
        if self._cancel_requested.is_set() or self.isInterruptionRequested():
            logger.debug(f"Request {request_id} cancelled after file read")
            return

        # Validate ROM size and offset
        rom_size = len(rom_data)
        if rom_size < 0x8000:
            raise ValueError(f"ROM file too small: {rom_size} bytes")
        if self.offset >= rom_size:
            raise ValueError(f"Offset 0x{self.offset:X} beyond ROM size 0x{rom_size:X}")

        # Check cancellation before decompression
        if self._cancel_requested.is_set() or self.isInterruptionRequested():
            logger.debug(f"Request {request_id} cancelled before decompression")
            return

        # Use conservative size for manual offsets during dragging, unless full decompression requested
        if self._full_decompression:
            # Full decompression for opening sprite in editor - no size limit (HAL has 64KB safety limit)
            expected_size = None
            logger.debug(f"[WORKER] Using full decompression (no size limit) for offset 0x{self.offset:X}")
        else:
            # 4KB limit for fast preview during slider dragging
            expected_size = 4096

        # For manual offset browsing, try HAL decompression first
        # This allows Lua-captured offsets (which are compressed sprite offsets) to work correctly
        tile_data = None
        compressed_size = 0
        decompression_succeeded = False
        header_bytes = b""  # Stores leading bytes stripped during alignment for injection restoration
        slack_size = 0

        # Track the original (primary) offset - we should trust it if decompression succeeds
        # Offset hunting exists to correct DMA timing jitter, NOT to "improve" quality
        primary_offset = self.offset

        # Check if user forced a specific compression type
        force_raw = self._force_compression_type == CompressionType.RAW
        force_hal = self._force_compression_type == CompressionType.HAL

        # Skip HAL entirely if user explicitly requested raw mode
        if not force_raw:
            # First, try HAL decompression (for Lua-captured offsets and known sprites)
            # Try the exact offset first, then nearby offsets if it fails (DMA timing jitter)
            offsets_to_try = get_offset_candidates(self.offset, len(rom_data))

            for try_offset in offsets_to_try:
                try:
                    # Check interruption right before decompression
                    if self.isInterruptionRequested():
                        logger.debug(f"Request {request_id} interrupted before decompression")
                        return

                    is_primary_offset = try_offset == primary_offset
                    if not is_primary_offset:
                        logger.debug(
                            f"[TRACE] Trying adjusted offset 0x{try_offset:X} (delta: {try_offset - primary_offset:+d})"
                        )
                    else:
                        logger.debug(f"[TRACE] Attempting HAL decompression at offset 0x{try_offset:X}")

                    # Try to extract as compressed sprite
                    rom_injector = self.extractor.rom_injector
                    # Trust primary offsets even if compression ratio looks odd; enforce on alternates.
                    compressed_size, tile_data, slack_size = rom_injector.find_compressed_sprite(
                        rom_data,
                        try_offset,
                        expected_size,
                        enforce_ratio=not is_primary_offset,
                    )

                    # Handle empty data case first (early continue pattern)
                    if not tile_data or len(tile_data) == 0:
                        logger.debug(f"[TRACE] HAL decompression returned empty data at offset 0x{try_offset:X}")
                        continue

                    # For PRIMARY offset: trust it if decompression succeeded
                    # The has_nonzero_content check is meant to filter garbage at ALTERNATE offsets,
                    # not to reject valid mostly-black sprites at the user's requested offset.
                    # Fix for bug: clicking 0x293AEB opened 0x293AED because the sprite was mostly black.
                    if is_primary_offset:
                        # Primary offset decompression succeeded - use it immediately
                        decompression_succeeded = True
                        logger.debug(f"[TRACE] Primary offset 0x{try_offset:X} decompressed successfully, using it")
                    elif has_nonzero_content(tile_data):
                        # Alternate offset: validate that it's reasonable sprite data
                        decompression_succeeded = True
                        logger.info(
                            f"[TRACE] Successfully decompressed using adjusted offset 0x{try_offset:X} (delta: {try_offset - primary_offset:+d})"
                        )
                    else:
                        # Alternate offset with mostly-zero data - skip it
                        logger.debug(
                            f"[TRACE] HAL decompression at 0x{try_offset:X} returned mostly zeros, trying next offset"
                        )
                        continue

                    # Decompression succeeded (either primary or validated alternate)
                    logger.debug(
                        f"[TRACE] Successfully decompressed {len(tile_data)} bytes from offset 0x{try_offset:X}"
                    )
                    logger.debug(f"[TRACE] Compressed size: {compressed_size} bytes, slack: {slack_size} bytes")
                    logger.debug(
                        f"[TRACE] First 20 bytes of decompressed data: {tile_data[:20].hex() if tile_data else 'None'}"
                    )

                    # Align tile data to 32-byte boundaries
                    # Some HAL-compressed assets have header bytes that cause misalignment
                    # Store header bytes for restoration during injection (prevents color shift bug)
                    original_len = len(tile_data)
                    header_bytes_count = original_len % 32
                    header_bytes = tile_data[:header_bytes_count] if header_bytes_count > 0 else b""
                    tile_data = align_tile_data(tile_data)
                    if len(tile_data) != original_len:
                        logger.debug(
                            f"[TRACE] Aligned tile data: {original_len} -> {len(tile_data)} bytes "
                            f"(removed {original_len - len(tile_data)} header byte(s), stored for injection)"
                        )

                    # Update the actual offset used for display purposes
                    self.offset = try_offset
                    break

                except Exception as decomp_error:
                    # HAL decompression failed - this is normal for non-compressed offsets
                    if try_offset == self.offset:
                        logger.debug(
                            f"[TRACE] HAL decompression failed at offset 0x{try_offset:X}: {decomp_error.__class__.__name__}: {decomp_error}"
                        )
                    continue

            if not decompression_succeeded:
                logger.debug(f"[TRACE] HAL decompression failed at all attempted offsets near 0x{self.offset:X}")
        else:
            logger.debug("[TRACE] Skipping HAL decompression (user requested raw mode)")

        # If HAL was forced and failed, don't fall back to raw - emit error
        if force_hal and not decompression_succeeded:
            raise ValueError(f"HAL decompression failed at 0x{self.offset:X} (forced HAL mode - no raw fallback)")

        # If HAL decompression failed or returned empty data, fall back to raw tile extraction
        # (unless user explicitly requested HAL-only mode, which is handled above)
        if not decompression_succeeded or not tile_data:
            logger.debug(f"[TRACE] Falling back to raw tile extraction for offset 0x{self.offset:X}")
            try:
                # Check interruption
                if self.isInterruptionRequested() or self._cancel_requested.is_set():
                    logger.debug(f"Request {request_id} cancelled")
                    return

                # Read raw bytes from ROM at the offset
                # This is for manual browsing of non-compressed areas
                # Use 4KB default for raw reads (fallback path when HAL decompression fails)
                raw_read_size = expected_size if expected_size is not None else 4096
                if self.offset + raw_read_size <= len(rom_data):
                    tile_data = rom_data[self.offset : self.offset + raw_read_size]
                    logger.debug(
                        f"[TRACE] Extracted {len(tile_data)} bytes of raw tile data from offset 0x{self.offset:X}"
                    )
                else:
                    # Read what's available up to end of ROM
                    tile_data = rom_data[self.offset :]
                    logger.debug(f"[TRACE] Extracted {len(tile_data)} bytes (to EOF) from offset 0x{self.offset:X}")

                logger.debug(f"[TRACE] First 20 bytes of raw data: {tile_data[:20].hex() if tile_data else 'None'}")

            except Exception as e:
                # Both HAL decompression and raw extraction failed
                if self.isInterruptionRequested() or self._cancel_requested.is_set():
                    logger.debug(f"Request {request_id} cancelled during extraction")
                    return
                raise ValueError(f"Failed to extract sprite at 0x{self.offset:X}: {e}") from e

        # Check cancellation after decompression
        if self._cancel_requested.is_set() or self.isInterruptionRequested():
            logger.debug(f"Request {request_id} cancelled after decompression")
            return

        # Validate extracted data
        if not tile_data:
            raise ValueError(f"No sprite data found at offset 0x{self.offset:X}")

        # Calculate dimensions
        num_tiles = len(tile_data) // 32
        if num_tiles == 0:
            raise ValueError("No complete tiles found in sprite data")

        # Calculate dimensions based on actual tile data size and default tiles_per_row
        # Use a default tiles_per_row for calculation, mirroring general discovery behavior
        # The actual output image dimensions are then derived from this grid
        tiles_per_row_for_calc = 16
        _, _, _, width, height = calculate_dimensions_from_tile_data(len(tile_data), tiles_per_row_for_calc)

        # Cap dimensions to prevent excessively large previews
        width = min(width, 384)
        height = min(height, 384)

        # Final cancellation check before emitting
        if self._cancel_requested.is_set():
            return

        # Emit success
        logger.debug(
            f"[WORKER] Emitting preview_ready: request_id={request_id}, "
            f"data_len={len(tile_data) if tile_data else 0}, {width}x{height}, sprite_name={self.sprite_name}, "
            f"compressed_size={compressed_size}, slack_size={slack_size}, actual_offset=0x{self.offset:X}, "
            f"hal_succeeded={decompression_succeeded}, header_bytes={len(header_bytes)}"
        )
        self.preview_ready.emit(
            request_id,
            tile_data,
            width,
            height,
            self.sprite_name,
            compressed_size,
            slack_size,
            self.offset,
            decompression_succeeded,
            header_bytes,
        )
        logger.debug("[TRACE] PoolWorker emitted preview_ready signal")


class PreviewWorkerPool(QObject):
    """
    Pool of reusable preview workers for efficient thread management.

    Features:
    - Maintains pool of 1-2 workers to prevent thread churn
    - Automatic cancellation of stale requests
    - Worker cleanup after idle period
    - Thread-safe request submission
    """

    # Signals for completed previews
    preview_ready = Signal(
        int, bytes, int, int, str, int, int, int, bool, bytes
    )  # request_id, tile_data, width, height, name, compressed_size, slack_size, actual_offset, hal_succeeded, header_bytes
    preview_error = Signal(int, str)  # request_id, error_msg

    def __init__(self, max_workers: int = 2, idle_timeout: int = 30000):
        super().__init__()

        self._max_workers = max_workers
        self._idle_timeout = idle_timeout

        # Thread-safe collections
        self._available_workers: queue.Queue[PooledPreviewWorker] = queue.Queue()
        self._active_workers: set[PooledPreviewWorker] = set()
        self._request_queue: queue.Queue[tuple[float, SliderPreviewRequest, ROMExtractor]] = queue.Queue()

        # Synchronization
        self._mutex = QMutex()
        self._shutdown_requested = threading.Event()

        # Pool management
        self._worker_count = 0
        self._last_activity = time.time()

        # Cleanup timer
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.timeout.connect(self._cleanup_idle_workers)
        self._cleanup_timer.start(10000)  # Check every 10 seconds

        logger.debug(f"PreviewWorkerPool initialized with max_workers={max_workers}")

    def submit_request(self, request: SliderPreviewRequest, extractor: ROMExtractor) -> None:
        """
        Submit a preview request to the worker pool.

        Args:
            request: SliderPreviewRequest object
            extractor: ROM extractor for sprite processing
        """
        if self._shutdown_requested.is_set():
            return

        current_time = time.time()

        with QMutexLocker(self._mutex):
            # Cancel any active workers (new request takes priority)
            for worker in list(self._active_workers):
                worker.cancel_current_request()

            # Get or create a worker
            worker = self._get_available_worker()
            if worker is None:
                # Queue the request instead of rejecting it
                self._request_queue.put((current_time, request, extractor))
                QTimer.singleShot(10, self._process_queued_requests)
                return

            # Setup worker for this request
            worker.setup_request(request, extractor)

            # Connect signals only if not already connected
            if not worker._signals_connected:
                worker.preview_ready.connect(self._on_worker_ready, Qt.ConnectionType.QueuedConnection)
                worker.preview_error.connect(self._on_worker_error, Qt.ConnectionType.QueuedConnection)
                worker._signals_connected = True

            # Move to active set
            self._active_workers.add(worker)
            self._last_activity = time.time()

            # Start processing
            worker.start()

        logger.debug(f"Submitted request {request.request_id} to worker pool")

    def _get_available_worker(self) -> PooledPreviewWorker | None:
        """Get an available worker, creating one if needed."""
        # Try to get existing worker
        try:
            worker = self._available_workers.get_nowait()
            logger.debug("Reusing existing worker")
            return worker
        except queue.Empty:
            pass

        # Create new worker if under limit
        if self._worker_count < self._max_workers:
            worker = PooledPreviewWorker(weakref.ref(self))
            WorkerManager._register_worker(worker)  # Register with centralized tracker
            self._worker_count += 1
            logger.debug(f"Created new worker (count: {self._worker_count})")
            return worker

        logger.debug(f"Worker pool at capacity (workers: {self._worker_count})")
        return None

    def _return_worker(self, worker: PooledPreviewWorker) -> None:
        """Return a worker to the available pool."""
        with QMutexLocker(self._mutex):
            # Remove from active set
            self._active_workers.discard(worker)

            # CRITICAL FIX: Do NOT disconnect signals here!
            # Disconnecting signals while they might still be processing causes crashes.
            # Instead, leave signals connected and just return worker to pool.
            # We'll only disconnect when actually cleaning up the worker for good.

            # Return to available pool if not shutting down
            if not self._shutdown_requested.is_set():
                try:
                    self._available_workers.put_nowait(worker)
                    logger.debug("Worker returned to pool (signals remain connected)")
                    # Process any queued requests now that a worker is available
                    QTimer.singleShot(0, self._process_queued_requests)
                except queue.Full:
                    # Pool full, clean up worker
                    logger.debug("Available worker pool full, cleaning up worker")
                    self._cleanup_worker(worker)
            else:
                self._cleanup_worker(worker)

    def _process_queued_requests(self) -> None:
        """Process any queued requests when workers become available."""
        if self._shutdown_requested.is_set():
            return

        # Try to process one request from the queue
        try:
            if not self._request_queue.empty():
                timestamp, request, extractor = self._request_queue.get_nowait()

                # Check if request is still recent (not stale)
                age = time.time() - timestamp
                if age > 2.0:  # Discard requests older than 2 seconds
                    # Try next request
                    QTimer.singleShot(0, self._process_queued_requests)
                    return

                # Try to submit the request
                with QMutexLocker(self._mutex):
                    worker = self._get_available_worker()
                    if worker:
                        # Setup and start worker
                        worker.setup_request(request, extractor)

                        # Connect signals only if not already connected
                        if not worker._signals_connected:
                            worker.preview_ready.connect(self._on_worker_ready, Qt.ConnectionType.QueuedConnection)
                            worker.preview_error.connect(self._on_worker_error, Qt.ConnectionType.QueuedConnection)
                            worker._signals_connected = True

                        # Move to active set
                        self._active_workers.add(worker)
                        self._last_activity = time.time()
                        worker.start()

                        # Check for more queued requests
                        if not self._request_queue.empty():
                            QTimer.singleShot(10, self._process_queued_requests)
                    else:
                        # No worker available, put request back
                        self._request_queue.put((timestamp, request, extractor))
        except queue.Empty:
            pass
        except Exception as e:
            logger.warning(f"Error processing queued request: {e}")

    def _on_worker_ready(
        self,
        request_id: int,
        tile_data: bytes,
        width: int,
        height: int,
        sprite_name: str,
        compressed_size: int,
        slack_size: int,
        actual_offset: int,
        hal_succeeded: bool,
        header_bytes: bytes,
    ) -> None:
        """Handle worker preview ready."""
        logger.debug(
            f"[TRACE] Worker pool received preview: request_id={request_id}, "
            f"data_len={len(tile_data) if tile_data else 0}, {width}x{height}, "
            f"compressed_size={compressed_size}, slack_size={slack_size}, "
            f"actual_offset=0x{actual_offset:X}, hal_succeeded={hal_succeeded}, "
            f"header_bytes={len(header_bytes)}"
        )
        self.preview_ready.emit(
            request_id,
            tile_data,
            width,
            height,
            sprite_name,
            compressed_size,
            slack_size,
            actual_offset,
            hal_succeeded,
            header_bytes,
        )
        logger.debug("[TRACE] Worker pool emitted preview_ready signal")

    def _on_worker_error(self, request_id: int, error_msg: str) -> None:
        """Handle worker preview error."""
        self.preview_error.emit(request_id, error_msg)

    def _cleanup_idle_workers(self) -> None:
        """Clean up idle workers after timeout."""
        if self._shutdown_requested.is_set():
            return

        current_time = time.time()
        idle_time = current_time - self._last_activity

        if idle_time > (self._idle_timeout / 1000.0):  # Convert to seconds
            with QMutexLocker(self._mutex):
                # Clean up some idle workers
                workers_to_cleanup = []
                try:
                    while not self._available_workers.empty() and len(workers_to_cleanup) < 1:
                        worker = self._available_workers.get_nowait()
                        workers_to_cleanup.append(worker)
                except queue.Empty:
                    pass

                for worker in workers_to_cleanup:
                    self._cleanup_worker(worker)
                    self._worker_count -= 1

                if workers_to_cleanup:
                    logger.debug(f"Cleaned up {len(workers_to_cleanup)} idle workers")

    def _cleanup_worker(self, worker: PooledPreviewWorker) -> None:
        """Clean up a single worker safely using WorkerManager.

        Uses the centralized WorkerManager for proper cleanup and registry removal.
        """
        try:
            # Mark worker as being destroyed to prevent signal processing
            worker._being_destroyed = True

            # First, cancel any current operation
            worker.cancel_current_request()

            # Block signals BEFORE disconnecting to prevent crashes
            # This ensures no signals are emitted during disconnect
            worker.blockSignals(True)

            # Disconnect signals safely now that they're blocked
            if worker._signals_connected:
                try:
                    worker.preview_ready.disconnect(self._on_worker_ready)
                except (TypeError, RuntimeError):
                    pass  # Already disconnected or object deleted
                try:
                    worker.preview_error.disconnect(self._on_worker_error)
                except (TypeError, RuntimeError):
                    pass  # Already disconnected or object deleted
                worker._signals_connected = False
                logger.debug("Disconnected worker signals after blocking")

            # Use WorkerManager for proper cleanup and registry removal
            # This handles: requestInterruption, quit, wait, deleteLater
            WorkerManager.cleanup_worker(worker, timeout=1500)

            # If worker is still running after cleanup, do NOT call deleteLater()
            # which would crash with "QThread: Destroyed while thread is still running"
            if worker.isRunning():
                logger.warning("Worker still running after cleanup, keeping reference to prevent crash")
                # Keep reference to prevent GC (leak is better than crash)
                # Decrement worker count so we can create a replacement
                if self._worker_count > 0:
                    self._worker_count -= 1

        except Exception as e:
            logger.warning(f"Error cleaning up worker: {e}")
            # Only delete if not running to avoid crash
            try:
                if not worker.isRunning():
                    worker.deleteLater()
            except Exception:
                pass  # Worker object already invalid

    def cleanup(self) -> None:
        """Clean up the entire worker pool."""
        logger.debug("Cleaning up PreviewWorkerPool")

        self._shutdown_requested.set()
        self._cleanup_timer.stop()

        with QMutexLocker(self._mutex):
            # Cancel all active workers
            for worker in list(self._active_workers):
                worker.cancel_current_request()

            # Clean up all workers
            workers_to_cleanup = []

            # Collect active workers
            workers_to_cleanup.extend(self._active_workers)

            # Collect available workers
            try:
                while not self._available_workers.empty():
                    worker = self._available_workers.get_nowait()
                    workers_to_cleanup.append(worker)
            except queue.Empty:
                pass

            # Clean up all workers with proper termination
            for worker in workers_to_cleanup:
                try:
                    # First cancel the request
                    worker.cancel_current_request()

                    # Block signals BEFORE disconnecting to prevent crashes
                    worker.blockSignals(True)

                    # Disconnect signals safely now that they're blocked
                    if worker._signals_connected:
                        with contextlib.suppress(TypeError):
                            worker.preview_ready.disconnect()
                        with contextlib.suppress(TypeError):
                            worker.preview_error.disconnect()
                        worker._signals_connected = False

                    # Request interruption
                    worker.requestInterruption()

                    # Give worker a short chance to finish gracefully
                    if worker.isRunning():
                        if not worker.wait(200):  # Wait only 200ms
                            logger.debug("Worker still running, requesting quit")
                            worker.quit()
                            if not worker.wait(300):  # Additional 300ms after quit
                                # Do NOT call deleteLater() if still running - would crash
                                logger.warning("Worker not responding to quit, keeping reference to prevent crash")
                                continue  # Skip deleteLater for this worker

                    # Only schedule for deletion if thread has stopped
                    worker.deleteLater()
                except Exception as e:
                    logger.warning(f"Error during worker cleanup: {e}")

            if self._active_workers:
                self._active_workers.clear()
            self._worker_count = 0

        logger.debug("PreviewWorkerPool cleanup complete")
