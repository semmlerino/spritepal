"""
Batch thumbnail worker for generating sprite thumbnails asynchronously.
Handles queue management and priority-based generation.
"""

from __future__ import annotations

import mmap
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, PriorityQueue
from typing import TYPE_CHECKING, Any, override

from PIL import Image

from ui.common.thumbnail_cache import ThumbnailCache

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor
from PySide6.QtCore import (
    QMutex,
    QMutexLocker,
    QObject,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage, QPixmap

from core.offset_hunting import get_offset_candidates, has_nonzero_content
from core.services.image_utils import pil_to_qimage
from core.tile_renderer import TileRenderer
from core.tile_utils import align_tile_data
from utils.constants import (
    THREAD_POOL_TIMEOUT_SECONDS,
    WORKER_IDLE_CHECK_INTERVAL_MS,
    WORKER_IDLE_ITERATIONS,
    WORKER_MAX_IDLE_ITERATIONS,
)
from utils.logging_config import get_logger
from utils.rom_utils import BytesMMAPWrapper, detect_smc_offset

logger = get_logger(__name__)


@dataclass
class ThumbnailRequest:
    """Request for thumbnail generation."""

    offset: int
    size: int
    priority: int = 0

    def __lt__(self, other: object) -> bool:
        """For priority queue sorting (lower priority value = higher priority)."""
        if not isinstance(other, ThumbnailRequest):
            return NotImplemented
        return self.priority < other.priority


class BatchThumbnailWorker(QObject):
    """
    Worker for batch thumbnail generation.

    IMPORTANT: This class now inherits from QObject, not QThread.
    Use the WorkerController class to manage the thread lifecycle.
    """

    # Signals - Use QImage instead of QPixmap for thread safety
    thumbnail_ready = Signal(int, QImage)
    """Emitted when thumbnail is ready. Args: offset (int), qimage (QImage, thread-safe)."""

    progress = Signal(int, int)
    """Emitted with generation progress. Args: completed_count, total_count."""

    error = Signal(str)
    """Emitted on error. Args: error_message."""

    started = Signal()
    """Emitted when worker starts processing."""

    finished = Signal()
    """Emitted when worker finishes all requests."""

    def __init__(self, rom_path: str, rom_extractor: ROMExtractor, parent: QObject | None = None):
        """
        Initialize the batch thumbnail worker.

        Args:
            rom_path: Path to ROM file
            rom_extractor: ROM extractor instance
            parent: Parent object (not thread)
        """
        super().__init__(parent)

        self.rom_path = rom_path
        self.rom_extractor = rom_extractor
        self.tile_renderer = TileRenderer()

        # Thread control
        self._stop_requested = False
        self._pause_requested = False
        self._mutex = QMutex()
        self._cache_mutex = QMutex()  # Separate mutex for cache
        self._counter_mutex = QMutex()  # Mutex for progress counters (thread-safe access)

        # Request queue
        self._request_queue: PriorityQueue[Any] = PriorityQueue()  # pyright: ignore[reportExplicitAny] - Generic queue type
        self._pending_count = 0
        self._completed_count = 0

        # LRU Cache for recently generated thumbnails (store QImage, not QPixmap)
        self._cache = ThumbnailCache(max_items=100)

        # Memory-mapped ROM data
        self._rom_file = None
        self._rom_mmap = None
        self._smc_offset = 0  # SMC header offset (0 or 512)
        # Cached ROM data without SMC header for HAL decompression (created once in _load_rom_data)
        # Uses memoryview for mmap (zero-copy) or bytes for BytesMMAPWrapper fallback
        self._rom_data_for_hal: bytes | memoryview | None = None

        # Multi-threading for parallel thumbnail generation
        self._use_multithreading = True
        self._thread_pool = None
        self._max_workers = 4  # Optimal for I/O + CPU bound tasks

        # Cleanup tracking for idempotent cleanup
        self._cleanup_called = False

    def queue_thumbnail(self, offset: int, size: int = 384, priority: int = 0) -> None:
        """
        Queue a thumbnail for generation.

        Args:
            offset: ROM offset of sprite
            size: Thumbnail size in pixels
            priority: Priority (0 = highest)
        """
        request = ThumbnailRequest(offset, size, priority)

        with QMutexLocker(self._mutex):
            self._request_queue.put(request)
            self._pending_count += 1

    def queue_batch(self, offsets: list[int], size: int = 384, priority_start: int = 0) -> None:
        """
        Queue multiple thumbnails for generation.

        Args:
            offsets: List of ROM offsets
            size: Thumbnail size for all
            priority_start: Starting priority (increments for each)
        """
        for i, offset in enumerate(offsets):
            self.queue_thumbnail(offset, size, priority_start + i)

    def clear_queue(self) -> None:
        """Clear all pending requests."""
        with QMutexLocker(self._mutex):
            # Clear the queue
            while not self._request_queue.empty():
                try:
                    self._request_queue.get_nowait()
                except Empty:
                    # Queue is empty
                    break
            self._pending_count = 0

    @Slot()
    def stop(self):
        """Request the worker to stop (thread-safe)."""
        with QMutexLocker(self._mutex):
            self._stop_requested = True
        # Also clear the queue to stop processing immediately
        self.clear_queue()

    @Slot()
    def pause(self):
        """Pause thumbnail generation (thread-safe)."""
        with QMutexLocker(self._mutex):
            self._pause_requested = True

    @Slot()
    def resume(self):
        """Resume thumbnail generation (thread-safe)."""
        with QMutexLocker(self._mutex):
            self._pause_requested = False

    def _is_stop_requested(self) -> bool:
        """Check if stop was requested (thread-safe)."""
        with QMutexLocker(self._mutex):
            return self._stop_requested

    def _is_pause_requested(self) -> bool:
        """Check if pause was requested (thread-safe)."""
        with QMutexLocker(self._mutex):
            return self._pause_requested

    @Slot()
    @override
    def run(self):
        """Main worker execution - runs in worker thread."""
        logger.info("BatchThumbnailWorker started")
        self.started.emit()

        try:
            # Load ROM data using memory mapping
            self._load_rom_data()
            logger.info(f"ROM data mapped: {len(self._rom_mmap) if self._rom_mmap else 0} bytes")

            processed_count = 0
            idle_iterations = 0
            last_log_count = -1  # Track last logged count to avoid spam

            # Initialize thread pool if multi-threading is enabled
            if self._use_multithreading:
                self._thread_pool = ThreadPoolExecutor(max_workers=self._max_workers)
                logger.info(f"Initialized thread pool with {self._max_workers} workers")

            while not self._is_stop_requested():
                # Check for pause (thread-safe)
                if self._is_pause_requested():
                    QThread.currentThread().msleep(WORKER_IDLE_CHECK_INTERVAL_MS)
                    continue

                # Collect batch of requests for parallel processing
                if self._use_multithreading and not self._request_queue.empty():
                    batch_requests = []
                    batch_size = min(self._max_workers * 2, 8)  # Process up to 8 at once

                    # Reload ROM if needed after idle release
                    if self._rom_mmap is None:
                        logger.debug("Reloading ROM data after idle release")
                        self._load_rom_data()

                    for _ in range(batch_size):
                        request = self._get_next_request()
                        if request:
                            # Check cache first
                            cache_key = ThumbnailCache.make_key(request.offset, request.size)
                            cached_image = self._get_cached_image(cache_key)
                            if cached_image:
                                self.thumbnail_ready.emit(request.offset, cached_image)
                                self._increment_completed_count()
                                self._emit_progress()
                            else:
                                batch_requests.append(request)
                        else:
                            break

                    # Process batch in parallel
                    if batch_requests:
                        self._process_batch_parallel(batch_requests)
                        processed_count += len(batch_requests)
                        idle_iterations = 0
                        continue

                # Single-threaded fallback or when queue is getting empty
                request = self._get_next_request()
                if not request:
                    # Log only once when we finish processing
                    if processed_count > 0 and processed_count != last_log_count:
                        logger.debug(f"Finished batch: processed {processed_count} thumbnails")
                        last_log_count = processed_count

                    # Increment idle counter
                    idle_iterations += 1

                    # Release ROM handle after idle to free file lock on Windows
                    if idle_iterations == WORKER_IDLE_ITERATIONS and self._rom_mmap is not None:
                        logger.debug("Releasing ROM handle during idle to free file lock")
                        self._clear_rom_data()

                    # Auto-stop after being idle for too long
                    if idle_iterations >= WORKER_MAX_IDLE_ITERATIONS:
                        idle_ms = idle_iterations * WORKER_IDLE_CHECK_INTERVAL_MS
                        logger.info(f"Auto-stopping after {idle_ms}ms idle, processed {processed_count} total")
                        break

                    # Sleep when idle to reduce CPU usage
                    QThread.currentThread().msleep(WORKER_IDLE_CHECK_INTERVAL_MS)
                    continue

                # Reset idle counter when we get work
                idle_iterations = 0

                # Reload ROM if needed after idle release
                if self._rom_mmap is None:
                    logger.debug("Reloading ROM data after idle release")
                    self._load_rom_data()

                logger.debug(f"Processing thumbnail request: offset=0x{request.offset:06X}, size={request.size}")

                # Check cache first (thread-safe)
                cache_key = ThumbnailCache.make_key(request.offset, request.size)
                cached_image = self._get_cached_image(cache_key)

                if cached_image:
                    self.thumbnail_ready.emit(request.offset, cached_image)
                    self._increment_completed_count()
                    self._emit_progress()
                    continue

                # Generate thumbnail
                qimage = self._generate_thumbnail(request)

                if qimage and not qimage.isNull():
                    # logger.debug(
                    #     f"Generated valid thumbnail for 0x{request.offset:06X} (size: {qimage.width()}x{qimage.height()})"
                    # )
                    # Cache it
                    self._add_to_cache(cache_key, qimage)

                    # Emit result (QImage is thread-safe)
                    self.thumbnail_ready.emit(request.offset, qimage)
                    processed_count += 1
                else:
                    logger.warning(f"Failed to generate thumbnail for 0x{request.offset:06X} - image is null or None")

                self._increment_completed_count()
                self._emit_progress()

        except Exception as e:
            logger.error(f"Thumbnail worker error: {e}", exc_info=True)
            self.error.emit(str(e))
        finally:
            logger.info("BatchThumbnailWorker stopped")
            # Shutdown thread pool first to prevent resource leak
            self._shutdown_thread_pool()
            # Clear ROM data to free memory
            self._clear_rom_data()
            # Clear cache as well
            self._clear_cache_memory()
            self.finished.emit()

    def _load_rom_data(self):
        """Load ROM data using memory mapping for efficiency with proper resource management."""
        # Clear any existing handles first to prevent leaks
        self._clear_rom_data()

        rom_file = None
        rom_mmap = None
        try:
            rom_file = Path(self.rom_path).open("rb")
            try:
                # Try memory mapping first
                rom_mmap = mmap.mmap(rom_file.fileno(), 0, access=mmap.ACCESS_READ)
                # Store handles for persistent use (cleanup via _clear_rom_data)
                self._rom_file = rom_file
                self._rom_mmap = rom_mmap
                # Detect SMC header using utility
                file_size = len(self._rom_mmap)
                self._smc_offset = detect_smc_offset(self._rom_mmap)
                if self._smc_offset > 0:
                    logger.info(f"Detected {self._smc_offset}-byte SMC header in ROM")
                # Cache ROM data without SMC header for HAL decompression (zero-copy memoryview)
                self._rom_data_for_hal = memoryview(self._rom_mmap)[self._smc_offset :]
                logger.info(f"ROM data mapped: {file_size} bytes (SMC offset: {self._smc_offset})")
            except Exception as mmap_error:
                # Memory mapping failed - close file and use fallback
                logger.warning(f"Failed to memory-map ROM, using fallback: {mmap_error}")
                rom_data = rom_file.read()
                rom_file.close()
                rom_file = None

                # Detect SMC header using utility
                file_size = len(rom_data)
                self._smc_offset = detect_smc_offset(rom_data)
                if self._smc_offset > 0:
                    logger.info(f"Detected {self._smc_offset}-byte SMC header in ROM")

                # Use BytesMMAPWrapper from rom_utils for mmap-compatible interface
                self._rom_mmap = BytesMMAPWrapper(rom_data)
                self._rom_file = None
                # Cache ROM data without SMC header for HAL decompression (single copy)
                self._rom_data_for_hal = rom_data[self._smc_offset :]
                logger.info(f"ROM data loaded (fallback): {file_size} bytes (SMC offset: {self._smc_offset})")

        except Exception as e:
            # Clean up any partially opened handles on failure
            with suppress(Exception):
                if rom_mmap is not None:
                    rom_mmap.close()
            with suppress(Exception):
                if rom_file is not None:
                    rom_file.close()
            logger.error(f"Failed to load ROM: {e}")
            self._rom_mmap = None
            self._rom_file = None
            self.error.emit(f"Failed to load ROM: {e}")

    def _read_rom_chunk(self, offset: int, size: int) -> bytes | None:
        """Read a chunk from memory-mapped ROM.

        The offset is treated as a ROM offset (without SMC header).
        If the file has an SMC header, this method adjusts the offset automatically.
        """
        if not self._rom_mmap:
            return None

        try:
            # Adjust offset for SMC header (ROM offset -> file offset)
            file_offset = offset + self._smc_offset

            # Bounds checking (use adjusted file offset)
            if file_offset < 0 or file_offset >= len(self._rom_mmap):
                return None

            end_offset = min(file_offset + size, len(self._rom_mmap))
            chunk = self._rom_mmap[file_offset:end_offset]
            # Slicing always returns bytes, not int
            return chunk if isinstance(chunk, bytes) else bytes(chunk) if hasattr(chunk, "__iter__") else None
        except Exception as e:
            logger.error(
                f"Failed to read ROM chunk at ROM offset 0x{offset:06X} (file: 0x{offset + self._smc_offset:06X}): {e}"
            )
            return None

    def _get_next_request(self) -> ThumbnailRequest | None:
        """Get the next request from the queue."""
        with QMutexLocker(self._mutex):
            if not self._request_queue.empty():
                try:
                    return self._request_queue.get_nowait()
                except Exception:
                    # Queue operation error (e.g., queue became empty during operation)
                    pass
        return None

    def _get_cached_image(self, key: str) -> QImage | None:
        """Thread-safe cache read with LRU."""
        return self._cache.get(key)

    def _process_batch_parallel(self, batch_requests: list[ThumbnailRequest]) -> None:
        """
        Process a batch of thumbnail requests in parallel.

        Args:
            batch_requests: List of thumbnail requests to process
        """
        if not self._thread_pool:
            return

        # Check stop flag before starting batch
        if self._is_stop_requested():
            return

        # Submit all requests to thread pool
        futures = []
        for request in batch_requests:
            future = self._thread_pool.submit(self._generate_thumbnail_thread_safe, request)
            futures.append((future, request))

        # Collect results as they complete
        for future, request in futures:
            # Check stop flag during batch processing for faster response
            if self._is_stop_requested():
                # Cancel remaining futures
                for remaining_future, _ in futures:
                    remaining_future.cancel()
                return

            try:
                qimage = future.result(timeout=THREAD_POOL_TIMEOUT_SECONDS)
                if qimage:
                    # Cache the result
                    cache_key = ThumbnailCache.make_key(request.offset, request.size)
                    self._add_to_cache(cache_key, qimage)

                    # Emit result (thread-safe)
                    self.thumbnail_ready.emit(request.offset, qimage)
                    self._increment_completed_count()
                    self._emit_progress()

                    logger.debug(f"Generated thumbnail for offset 0x{request.offset:06X} (parallel)")
            except Exception as e:
                logger.warning(f"Parallel thumbnail generation failed for 0x{request.offset:06X}: {e}")
                self._increment_completed_count()
                self._emit_progress()

    def _generate_thumbnail_thread_safe(self, request: ThumbnailRequest) -> QImage | None:
        """
        Thread-safe version of thumbnail generation for parallel processing.

        Args:
            request: Thumbnail request

        Returns:
            Generated QImage or None
        """
        # This runs in a thread pool thread, not the main worker thread
        # Need to ensure thread safety for ROM data access

        # The ROM data is read-only mmap, safe for concurrent reads
        return self._generate_thumbnail(request)

    def _generate_thumbnail(self, request: ThumbnailRequest) -> QImage | None:
        """
        Generate a thumbnail for a sprite.

        Args:
            request: Thumbnail request

        Returns:
            Generated QImage (thread-safe) or None
        """
        if not self._rom_mmap:
            return None

        try:
            # Try to decompress sprite at offset
            decompressed_data = None
            primary_offset = request.offset

            if self.rom_extractor and self._rom_data_for_hal:
                # Try HAL decompression with offset hunting (matches preview_worker_pool behavior)
                # Lua-captured offsets may be slightly off due to DMA timing jitter
                rom_injector = self.rom_extractor.rom_injector
                rom_size = len(self._rom_data_for_hal)

                for try_offset in get_offset_candidates(request.offset, rom_size):
                    try:
                        _, data, _ = rom_injector.find_compressed_sprite(
                            self._rom_data_for_hal,
                            try_offset,
                            expected_size=None,
                        )
                        if not data or len(data) == 0:
                            continue

                        is_primary_offset = try_offset == primary_offset

                        # Trust primary offset if HAL decompression succeeded
                        # (matches preview_worker_pool behavior - don't skip mostly-black sprites)
                        if is_primary_offset:
                            decompressed_data = data
                            # Align tile data to 32-byte boundaries (some assets have header bytes)
                            original_len = len(decompressed_data)
                            decompressed_data = align_tile_data(decompressed_data)
                            if len(decompressed_data) != original_len:
                                # logger.debug(
                                #     f"Aligned HAL data: {original_len} -> {len(decompressed_data)} bytes "
                                #     f"(removed {original_len - len(decompressed_data)} header byte(s)) "
                                #     f"from 0x{try_offset:06X}"
                                # )
                                pass
                            else:
                                # logger.debug(f"HAL decompressed {len(decompressed_data)} bytes from 0x{try_offset:06X}")
                                pass
                            break
                        if has_nonzero_content(data):
                            # Non-primary offset: require visible content to prevent
                            # shifting to wrong nearby sprite
                            decompressed_data = data
                            if try_offset != request.offset:
                                logger.info(
                                    f"Thumbnail: adjusted offset 0x{request.offset:06X} -> 0x{try_offset:06X} "
                                    f"(delta: {try_offset - request.offset:+d})"
                                )
                                # NOTE: Do NOT mutate request.offset here!
                                # The thumbnail must be emitted with the ORIGINAL offset so it
                                # matches the item in the asset browser. Mutating the offset
                                # causes desync between thumbnail and browser item.
                            # Align tile data to 32-byte boundaries (some assets have header bytes)
                            original_len = len(decompressed_data)
                            decompressed_data = align_tile_data(decompressed_data)
                            if len(decompressed_data) != original_len:
                                # logger.debug(
                                #     f"Aligned HAL data: {original_len} -> {len(decompressed_data)} bytes "
                                #     f"(removed {original_len - len(decompressed_data)} header byte(s)) "
                                #     f"from 0x{try_offset:06X}"
                                # )
                                pass
                            else:
                                # logger.debug(f"HAL decompressed {len(decompressed_data)} bytes from 0x{try_offset:06X}")
                                pass
                            break
                    except Exception as e:
                        if try_offset == request.offset:
                            logger.debug(f"HAL decompression failed for offset 0x{request.offset:06X}: {e}")
                        continue

            # If no decompressed data, use raw data
            if not decompressed_data:
                # Read raw tile data (up to 256 tiles)
                max_size = 32 * 256  # 32 bytes per tile, max 256 tiles
                decompressed_data = self._read_rom_chunk(request.offset, max_size)
                if decompressed_data:
                    # logger.debug(f"Using raw data: {len(decompressed_data)} bytes from 0x{request.offset:06X}")
                    pass

            if not decompressed_data:
                return None

            # Render tiles to image
            tile_count = len(decompressed_data) // 32
            if tile_count == 0:
                logger.debug(f"No tiles to render for 0x{request.offset:06X}")
                return None

            # Calculate dimensions (try to make roughly square)
            width_tiles = min(16, tile_count)
            height_tiles = (tile_count + width_tiles - 1) // width_tiles
            # logger.debug(f"Rendering {tile_count} tiles as {width_tiles}x{height_tiles} grid")

            # Render using tile renderer
            # Use palette_index=None for grayscale (will trigger grayscale fallback)
            image = self.tile_renderer.render_tiles(
                decompressed_data,
                width_tiles,
                height_tiles,
                palette_index=None,  # Grayscale by default
            )

            if not image:
                logger.warning(f"TileRenderer returned None for 0x{request.offset:06X}")
                return None

            # Convert PIL Image to QImage (thread-safe)
            qimage = self._pil_to_qimage(image)

            # Scale to requested size
            if qimage and not qimage.isNull():
                qimage = qimage.scaled(
                    request.size,
                    request.size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

            return qimage

        except Exception as e:
            logger.debug(f"Failed to generate thumbnail for offset {request.offset:06X}: {e}")
            return None

    def _pil_to_qimage(self, image: Image.Image) -> QImage:
        """
        Convert PIL Image to QImage (thread-safe and optimized).

        Args:
            image: PIL Image

        Returns:
            QImage (thread-safe alternative to QPixmap)
        """
        # Use centralized utility with thread_safe=True for worker thread safety
        return pil_to_qimage(image, thread_safe=True)

    def _add_to_cache(self, key: str, qimage: QImage) -> None:
        """Add an image to the cache (thread-safe with LRU eviction)."""
        self._cache.put(key, qimage)

    def _increment_completed_count(self) -> None:
        """Thread-safe increment of completed count."""
        with QMutexLocker(self._counter_mutex):
            self._completed_count += 1

    def _emit_progress(self) -> None:
        """Emit progress signal (thread-safe)."""
        with QMutexLocker(self._counter_mutex):
            total = self._pending_count + self._completed_count
            completed = self._completed_count
        if total > 0:
            self.progress.emit(completed, total)

    def get_cache_size(self) -> int:
        """Get the current cache size (thread-safe)."""
        return len(self._cache)

    def clear_cache(self) -> None:
        """Clear the thumbnail cache (thread-safe)."""
        if self._cache:
            self._cache.clear()

    def invalidate_offset(self, offset: int, size: int = 384) -> bool:
        """Remove specific offset from cache (thread-safe).

        Args:
            offset: ROM offset of the sprite to invalidate
            size: Thumbnail size (must match the original request size)

        Returns:
            True if an entry was removed, False if not found
        """
        cache_key = ThumbnailCache.make_key(offset, size)
        with QMutexLocker(self._cache_mutex):
            return self._cache.remove(cache_key)

    def is_rom_loaded(self) -> bool:
        """Check if ROM data is currently loaded.

        Returns:
            True if ROM is memory-mapped.
        """
        return self._rom_mmap is not None

    @property
    def pending_count(self) -> int:
        """Get the number of pending thumbnail requests.

        Returns:
            Number of thumbnails waiting to be processed.
        """
        with QMutexLocker(self._counter_mutex):
            return self._pending_count

    @property
    def completed_count(self) -> int:
        """Get the number of completed thumbnail requests.

        Returns:
            Number of thumbnails that have been processed.
        """
        with QMutexLocker(self._counter_mutex):
            return self._completed_count

    def _shutdown_thread_pool(self) -> None:
        """Shutdown thread pool safely with proper wait and error handling."""
        if self._thread_pool:
            try:
                # cancel_futures=True cancels queued work, wait=True waits
                # for in-progress work to complete
                self._thread_pool.shutdown(wait=True, cancel_futures=True)
                logger.debug("Thread pool shutdown complete")
            except Exception as e:
                logger.warning(f"Error shutting down thread pool: {e}")
            finally:
                self._thread_pool = None

    def _clear_cache_memory(self) -> None:
        """Clear cache memory with logging."""
        if self._cache:
            cache_size = len(self._cache)
            self._cache.clear()
            if cache_size > 0:
                logger.debug(f"Cleared thumbnail cache: freed {cache_size} cached images")
                # Log cache statistics before clearing
                stats = self._cache.get_stats()
                logger.debug(
                    f"Cache stats before clear: hit_rate={stats['hit_rate']:.1f}%, hits={stats['hits']}, misses={stats['misses']}"
                )

    def _clear_rom_data(self) -> None:
        """Clear ROM data from memory with logging."""
        if self._rom_mmap is not None:
            try:
                rom_size = len(self._rom_mmap)

                # Clear cached HAL data FIRST to release memoryview references to mmap
                # This prevents BufferError: cannot close exported pointers exist
                self._rom_data_for_hal = None

                # Close memory map
                if hasattr(self._rom_mmap, "close") and callable(getattr(self._rom_mmap, "close", None)):
                    self._rom_mmap.close()
                self._rom_mmap = None

                # Close file handle
                if self._rom_file:
                    self._rom_file.close()
                    self._rom_file = None

                # Reset SMC offset
                self._smc_offset = 0

                if rom_size > 0:
                    logger.debug(f"Cleared ROM data: freed {rom_size} bytes")
            except Exception as e:
                logger.warning(f"Error clearing ROM data: {e}")

    def cleanup(self) -> None:
        """Clean up the worker resources properly. Safe to call multiple times."""
        if self._cleanup_called:
            return
        self._cleanup_called = True

        logger.debug("BatchThumbnailWorker cleanup started")

        # Request stop
        self.stop()

        # Shutdown thread pool
        self._shutdown_thread_pool()

        # Clear resources thoroughly with error protection
        try:
            self._clear_cache_memory()
        except Exception as e:
            logger.warning(f"Error clearing cache during cleanup: {e}")

        try:
            self._clear_rom_data()
        except Exception as e:
            logger.warning(f"Error clearing ROM data during cleanup: {e}")

        logger.debug("BatchThumbnailWorker cleanup completed")


class ThumbnailWorkerController(QObject):
    """
    Controller for managing BatchThumbnailWorker lifecycle properly.
    This handles thread creation and management.
    """

    # Forward signals from worker
    thumbnail_ready = Signal(int, QPixmap)
    """Forwarded from worker. Args: offset (int), pixmap (QPixmap, converted from QImage)."""

    progress = Signal(int, int)
    """Forwarded from worker. Args: completed_count, total_count."""

    error = Signal(str)
    """Forwarded from worker. Args: error_message."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.worker: BatchThumbnailWorker | None = None
        self._thread: QThread | None = None
        self._cleanup_called = False
        # Store ROM context for auto-restart when worker auto-stops
        self._rom_path: str | None = None
        self._rom_extractor: ROMExtractor | None = None

    def start_worker(self, rom_path: str, rom_extractor: ROMExtractor) -> None:
        """Start worker with proper thread management."""
        if self._thread and self._thread.isRunning():
            logger.warning("Worker already running, stopping first")
            self.stop_worker()

        # Store ROM context for auto-restart
        self._rom_path = rom_path
        self._rom_extractor = rom_extractor

        # Create worker and thread
        self.worker = BatchThumbnailWorker(rom_path, rom_extractor)
        self._thread = QThread()

        # Move worker to thread
        self.worker.moveToThread(self._thread)

        # Connect signals for proper lifecycle
        self._thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        # Forward worker signals, converting QImage to QPixmap
        self.worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.worker.progress.connect(self.progress.emit)
        self.worker.error.connect(self.error.emit)

        # Start thread
        self._thread.start()

    def _ensure_worker_running(self) -> bool:
        """Ensure worker is running, restarting if needed.

        The worker auto-stops after being idle. This method checks if the thread
        is still running and restarts if necessary.

        Returns:
            True if worker is running (or was restarted), False if cannot restart.
        """
        # Check if thread is running (handle C++ object deletion)
        try:
            if self._thread and self._thread.isRunning():
                return True
        except RuntimeError:
            # C++ object already deleted by deleteLater() - treat as stopped
            self._thread = None
            self.worker = None

        # Worker has auto-stopped - try to restart if we have ROM context
        if self._rom_path and self._rom_extractor:
            logger.debug("Worker auto-stopped, restarting for new requests")
            self.start_worker(self._rom_path, self._rom_extractor)
            return True

        logger.warning("Cannot restart worker - no ROM context stored")
        return False

    @Slot(int, QImage)
    def _on_thumbnail_ready(self, offset: int, qimage: QImage) -> None:
        """Convert QImage to QPixmap in main thread and forward signal."""
        if not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage)
            self.thumbnail_ready.emit(offset, pixmap)

    def queue_thumbnail(self, offset: int, size: int = 384, priority: int = 0) -> None:
        """Queue a thumbnail for generation.

        If the worker has auto-stopped due to idle timeout, this will restart it.
        """
        if not self._ensure_worker_running():
            return
        if self.worker:
            self.worker.queue_thumbnail(offset, size, priority)

    def queue_batch(self, offsets: list[int], size: int = 384, priority_start: int = 0) -> None:
        """Queue multiple thumbnails for generation.

        If the worker has auto-stopped due to idle timeout, this will restart it.
        """
        if not self._ensure_worker_running():
            return
        if self.worker:
            self.worker.queue_batch(offsets, size, priority_start)

    def invalidate_offset(self, offset: int, size: int = 384) -> bool:
        """Remove specific offset from worker cache.

        Args:
            offset: ROM offset of the sprite to invalidate
            size: Thumbnail size (must match the original request size)

        Returns:
            True if an entry was removed, False if not found or worker not running
        """
        if self.worker:
            return self.worker.invalidate_offset(offset, size)
        return False

    def stop_worker(self) -> None:
        """Safely stop worker and thread."""
        if self.worker:
            self.worker.stop()
        if self._thread:
            try:
                # Check if thread is still valid (not already deleted by deleteLater)
                # and actually running before trying to quit
                if self._thread.isRunning():
                    self._thread.quit()
                    if not self._thread.wait(5000):  # Wait up to 5 seconds
                        # Log critical error but do NOT call terminate() - it causes
                        # undefined behavior including resource leaks, mutex deadlocks,
                        # and memory corruption. Let the orphan thread eventually finish.
                        logger.critical(
                            "Thread did not stop within timeout. "
                            "Thread may be orphaned - check for blocking operations."
                        )
            except RuntimeError:
                # C++ object already deleted - this is expected when cleanup
                # is called after the thread has finished and deleteLater executed
                pass

    def cleanup(self) -> None:
        """Clean up resources. Safe to call multiple times."""
        if self._cleanup_called:
            return
        self._cleanup_called = True

        self.stop_worker()
        if self.worker:
            self.worker.cleanup()
            self.worker = None
        self._thread = None
