"""
Batch thumbnail worker for generating sprite thumbnails asynchronously.
Handles queue management and priority-based generation.
"""
from __future__ import annotations

import mmap
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from queue import PriorityQueue
from typing import Any, override

from PIL import Image
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

from core.rom_extractor import ROMExtractor
from core.tile_renderer import TileRenderer
from utils.logging_config import get_logger

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

class LRUCache:
    """Thread-safe LRU cache for QImage thumbnails."""

    def __init__(self, maxsize: int = 100):
        """
        Initialize LRU cache with maximum size.

        Args:
            maxsize: Maximum number of items to store
        """
        self.maxsize = maxsize
        self._cache: OrderedDict[tuple[int, int], QImage] = OrderedDict()
        self._mutex = QMutex()
        self._hits = 0
        self._misses = 0

    def get(self, key: tuple[int, int]) -> QImage | None:
        """
        Get item from cache, updating access order.

        Args:
            key: Cache key (offset, size)

        Returns:
            Cached QImage or None if not found
        """
        with QMutexLocker(self._mutex):
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def put(self, key: tuple[int, int], value: QImage) -> None:
        """
        Add item to cache with LRU eviction.

        Args:
            key: Cache key (offset, size)
            value: QImage to cache
        """
        with QMutexLocker(self._mutex):
            if key in self._cache:
                # Update existing and move to end
                self._cache.move_to_end(key)
            else:
                # Add new item
                if len(self._cache) >= self.maxsize:
                    # Remove least recently used (first item)
                    self._cache.popitem(last=False)
                self._cache[key] = value

    def clear(self) -> None:
        """Clear all cached items."""
        with QMutexLocker(self._mutex):
            if self._cache:
                self._cache.clear()
            self._hits = 0
            self._misses = 0

    def size(self) -> int:
        """Get current cache size."""
        with QMutexLocker(self._mutex):
            return len(self._cache)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with QMutexLocker(self._mutex):
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                'size': len(self._cache),
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate
            }

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

    def __init__(
        self,
        rom_path: str,
        rom_extractor: ROMExtractor | None = None,
        parent: QObject | None = None
    ):
        """
        Initialize the batch thumbnail worker.

        Args:
            rom_path: Path to ROM file
            rom_extractor: ROM extractor instance
            parent: Parent object (not thread)
        """
        super().__init__(parent)

        self.rom_path = rom_path
        self.rom_extractor = rom_extractor or ROMExtractor()
        self.tile_renderer = TileRenderer()

        # Thread control
        self._stop_requested = False
        self._pause_requested = False
        self._mutex = QMutex()
        self._cache_mutex = QMutex()  # Separate mutex for cache

        # Request queue
        self._request_queue: PriorityQueue[Any] = PriorityQueue()
        self._pending_count = 0
        self._completed_count = 0

        # LRU Cache for recently generated thumbnails (store QImage, not QPixmap)
        self._cache = LRUCache(maxsize=100)

        # Memory-mapped ROM data
        self._rom_file = None
        self._rom_mmap = None

        # Multi-threading for parallel thumbnail generation
        self._use_multithreading = True
        self._thread_pool = None
        self._max_workers = 4  # Optimal for I/O + CPU bound tasks
        
        # Cleanup tracking for idempotent cleanup
        self._cleanup_called = False  # Optimal for I/O + CPU bound tasks

    def __del__(self) -> None:
        """Ensure cleanup when object is garbage collected."""
        self.cleanup()

    def queue_thumbnail(
        self,
        offset: int,
        size: int = 128,
        priority: int = 0
    ) -> None:
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

    def queue_batch(
        self,
        offsets: list[int],
        size: int = 128,
        priority_start: int = 0
    ) -> None:
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
                except Exception:
                    # Queue is empty or other queue operation error
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

        # Idle threshold for releasing ROM handle (2 seconds = 20 * 100ms)
        IDLE_ROM_RELEASE_THRESHOLD = 20

        try:
            # Load ROM data using memory mapping
            self._load_rom_data()
            logger.info(f"ROM data mapped: {len(self._rom_mmap) if self._rom_mmap else 0} bytes")

            processed_count = 0
            idle_iterations = 0
            max_idle_iterations = 100  # Stop after 10 seconds of idle (100 * 100ms)
            last_log_count = -1  # Track last logged count to avoid spam

            # Initialize thread pool if multi-threading is enabled
            if self._use_multithreading:
                self._thread_pool = ThreadPoolExecutor(max_workers=self._max_workers)
                logger.info(f"Initialized thread pool with {self._max_workers} workers")

            while not self._is_stop_requested():
                # Check for pause (thread-safe)
                if self._is_pause_requested():
                    QThread.currentThread().msleep(100)
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
                            cache_key = (request.offset, request.size)
                            cached_image = self._get_cached_image(cache_key)
                            if cached_image:
                                self.thumbnail_ready.emit(request.offset, cached_image)
                                self._completed_count += 1
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

                    # Release ROM handle after 2 seconds idle to free file lock on Windows
                    if idle_iterations == IDLE_ROM_RELEASE_THRESHOLD and self._rom_mmap is not None:
                        logger.debug("Releasing ROM handle during idle to free file lock")
                        self._clear_rom_data()

                    # Auto-stop after being idle for too long
                    if idle_iterations >= max_idle_iterations:
                        logger.info(f"Auto-stopping after {idle_iterations * 100}ms idle, processed {processed_count} total")
                        break

                    # Sleep longer when idle to reduce CPU usage
                    QThread.currentThread().msleep(100)  # Sleep 100ms instead of busy-waiting
                    continue

                # Reset idle counter when we get work
                idle_iterations = 0

                # Reload ROM if needed after idle release
                if self._rom_mmap is None:
                    logger.debug("Reloading ROM data after idle release")
                    self._load_rom_data()

                logger.debug(f"Processing thumbnail request: offset=0x{request.offset:06X}, size={request.size}")

                # Check cache first (thread-safe)
                cache_key = (request.offset, request.size)
                cached_image = self._get_cached_image(cache_key)

                if cached_image:
                    self.thumbnail_ready.emit(request.offset, cached_image)
                    self._completed_count += 1
                    self._emit_progress()
                    continue

                # Generate thumbnail
                qimage = self._generate_thumbnail(request)

                if qimage and not qimage.isNull():
                    logger.debug(f"Generated valid thumbnail for 0x{request.offset:06X} (size: {qimage.width()}x{qimage.height()})")
                    # Cache it
                    self._add_to_cache(cache_key, qimage)

                    # Emit result (QImage is thread-safe)
                    self.thumbnail_ready.emit(request.offset, qimage)
                    processed_count += 1
                else:
                    logger.warning(f"Failed to generate thumbnail for 0x{request.offset:06X} - image is null or None")

                self._completed_count += 1
                self._emit_progress()

        except Exception as e:
            logger.error(f"Thumbnail worker error: {e}", exc_info=True)
            self.error.emit(str(e))
        finally:
            logger.info("BatchThumbnailWorker stopped")
            # Shutdown thread pool first to prevent resource leak
            if self._thread_pool:
                try:
                    self._thread_pool.shutdown(wait=False, cancel_futures=True)
                    logger.debug("Thread pool shutdown complete in finally block")
                except Exception as pool_error:
                    logger.warning(f"Error shutting down thread pool: {pool_error}")
                finally:
                    self._thread_pool = None
            # Clear ROM data to free memory
            self._clear_rom_data()
            # Clear cache as well
            self._clear_cache_memory()
            self.finished.emit()

    @contextmanager
    def _rom_context(self):
        """Context manager for safe ROM file and memory map handling."""
        rom_file = None
        rom_mmap = None
        try:
            rom_file = Path(self.rom_path).open('rb')
            try:
                # Try memory mapping first
                rom_mmap = mmap.mmap(rom_file.fileno(), 0, access=mmap.ACCESS_READ)
                yield rom_mmap
            except Exception as mmap_error:
                logger.warning(f"Failed to memory-map ROM, using fallback: {mmap_error}")
                # Fallback to reading entire file
                rom_file.seek(0)
                rom_data = rom_file.read()

                # Create a mmap-compatible wrapper
                class BytesMMAPWrapper:
                    def __init__(self, data: bytes):
                        self._data = data
                    def __getitem__(self, key: int | slice) -> bytes | int:
                        return self._data[key]
                    def __len__(self) -> int:
                        return len(self._data)
                    def close(self) -> None:
                        pass  # No-op for bytes wrapper

                yield BytesMMAPWrapper(rom_data)
        finally:
            # Ensure proper cleanup in all cases
            with suppress(Exception):
                if rom_mmap is not None:
                    rom_mmap.close()
            with suppress(Exception):
                if rom_file is not None:
                    rom_file.close()

    def _load_rom_data(self):
        """Load ROM data using memory mapping for efficiency with proper resource management."""
        # Clear any existing handles first to prevent leaks
        self._clear_rom_data()

        rom_file = None
        rom_mmap = None
        try:
            rom_file = Path(self.rom_path).open('rb')
            try:
                # Try memory mapping first
                rom_mmap = mmap.mmap(rom_file.fileno(), 0, access=mmap.ACCESS_READ)
                # Store handles for persistent use (cleanup via _clear_rom_data)
                self._rom_file = rom_file
                self._rom_mmap = rom_mmap
                logger.info(f"ROM data mapped: {len(self._rom_mmap)} bytes")
            except Exception as mmap_error:
                # Memory mapping failed - close file and use fallback
                logger.warning(f"Failed to memory-map ROM, using fallback: {mmap_error}")
                rom_data = rom_file.read()
                rom_file.close()
                rom_file = None

                # Create a mmap-compatible wrapper (no file handle needed)
                class BytesMMAPWrapper:
                    def __init__(self, data: bytes):
                        self._data = data
                    def __getitem__(self, key: int | slice) -> bytes | int:
                        return self._data[key]
                    def __len__(self) -> int:
                        return len(self._data)
                    def close(self) -> None:
                        pass  # No-op for bytes wrapper

                self._rom_mmap = BytesMMAPWrapper(rom_data)
                self._rom_file = None
                logger.info(f"ROM data loaded (fallback): {len(self._rom_mmap)} bytes")

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
        """Read a chunk from memory-mapped ROM."""
        if not self._rom_mmap:
            return None

        try:
            # Bounds checking
            if offset < 0 or offset >= len(self._rom_mmap):
                return None

            end_offset = min(offset + size, len(self._rom_mmap))
            chunk = self._rom_mmap[offset:end_offset]
            # Slicing always returns bytes, not int
            return chunk if isinstance(chunk, bytes) else bytes(chunk) if hasattr(chunk, '__iter__') else None
        except Exception as e:
            logger.error(f"Failed to read ROM chunk at 0x{offset:06X}: {e}")
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

    def _get_cached_image(self, key: tuple[int, int]) -> QImage | None:
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

        # Submit all requests to thread pool
        futures = []
        for request in batch_requests:
            future = self._thread_pool.submit(self._generate_thumbnail_thread_safe, request)
            futures.append((future, request))

        # Collect results as they complete
        for future, request in futures:
            try:
                qimage = future.result(timeout=2.0)  # 2 second timeout per thumbnail
                if qimage:
                    # Cache the result
                    cache_key = (request.offset, request.size)
                    self._add_to_cache(cache_key, qimage)

                    # Emit result (thread-safe)
                    self.thumbnail_ready.emit(request.offset, qimage)
                    self._completed_count += 1
                    self._emit_progress()

                    logger.debug(f"Generated thumbnail for offset 0x{request.offset:06X} (parallel)")
            except Exception as e:
                logger.warning(f"Parallel thumbnail generation failed for 0x{request.offset:06X}: {e}")
                self._completed_count += 1
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

            if self.rom_extractor and hasattr(self.rom_extractor, 'rom_injector'):
                # Try HAL decompression
                try:
                    # Read chunk for decompression
                    chunk = self._read_rom_chunk(request.offset, 0x10000)  # Read up to 64KB
                    if chunk:
                        _, decompressed_data = self.rom_extractor.rom_injector.find_compressed_sprite(
                            chunk,
                            0,  # Offset within chunk
                            expected_size=None
                        )
                        if decompressed_data:
                            logger.debug(f"HAL decompressed {len(decompressed_data)} bytes from 0x{request.offset:06X}")
                except Exception as e:
                    # Log decompression failures for debugging, but continue with fallback to raw data
                    logger.debug(f"HAL decompression failed for offset 0x{request.offset:06X}: {e}")
                    decompressed_data = None

            # If no decompressed data, use raw data
            if not decompressed_data:
                # Read raw tile data (up to 256 tiles)
                max_size = 32 * 256  # 32 bytes per tile, max 256 tiles
                decompressed_data = self._read_rom_chunk(request.offset, max_size)
                if decompressed_data:
                    logger.debug(f"Using raw data: {len(decompressed_data)} bytes from 0x{request.offset:06X}")

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
            logger.debug(f"Rendering {tile_count} tiles as {width_tiles}x{height_tiles} grid")

            # Render using tile renderer
            # Use palette_index=None for grayscale (will trigger grayscale fallback)
            image = self.tile_renderer.render_tiles(
                decompressed_data,
                width_tiles,
                height_tiles,
                palette_index=None  # Grayscale by default
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
                    Qt.TransformationMode.SmoothTransformation
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
        width, height = image.size

        # Optimize based on image mode to avoid unnecessary conversions
        if image.mode == "RGBA":
            # Already in RGBA - most efficient path
            bytes_data = image.tobytes("raw", "RGBA")
            qimage = QImage(bytes_data, width, height, width * 4, QImage.Format.Format_RGBA8888)
        elif image.mode == "RGB":
            # RGB - convert directly without alpha
            bytes_data = image.tobytes("raw", "RGB")
            qimage = QImage(bytes_data, width, height, width * 3, QImage.Format.Format_RGB888)
        elif image.mode == "L":
            # Grayscale - use native grayscale format
            bytes_data = image.tobytes("raw", "L")
            qimage = QImage(bytes_data, width, height, width, QImage.Format.Format_Grayscale8)
        elif image.mode == "P":
            # Palette mode - convert to RGB (more efficient than RGBA)
            image = image.convert("RGB")
            bytes_data = image.tobytes("raw", "RGB")
            qimage = QImage(bytes_data, width, height, width * 3, QImage.Format.Format_RGB888)
        else:
            # Fallback for other modes
            image = image.convert("RGBA")
            bytes_data = image.tobytes("raw", "RGBA")
            qimage = QImage(bytes_data, width, height, width * 4, QImage.Format.Format_RGBA8888)

        # Use copy() only when necessary - if the bytes_data might be garbage collected
        # Since we're in a worker thread and the data is from tobytes(), we need the copy
        return qimage.copy()

    def _add_to_cache(self, key: tuple[int, int], qimage: QImage):
        """Add an image to the cache (thread-safe with LRU eviction)."""
        self._cache.put(key, qimage)

    def _emit_progress(self) -> None:
        """Emit progress signal."""
        total = self._pending_count + self._completed_count
        if total > 0:
            self.progress.emit(self._completed_count, total)

    def get_cache_size(self) -> int:
        """Get the current cache size (thread-safe)."""
        return self._cache.size()

    def clear_cache(self) -> None:
        """Clear the thumbnail cache (thread-safe)."""
        if self._cache:
            self._cache.clear()

    def _clear_cache_memory(self) -> None:
        """Clear cache memory with logging."""
        if hasattr(self, '_cache') and self._cache:
            cache_size = self._cache.size()
            if self._cache:
                self._cache.clear()
            if cache_size > 0:
                logger.debug(f"Cleared thumbnail cache: freed {cache_size} cached images")
                # Log cache statistics before clearing
                stats = self._cache.get_stats()
                logger.debug(f"Cache stats before clear: hit_rate={stats['hit_rate']:.1f}%, hits={stats['hits']}, misses={stats['misses']}")

    def _clear_rom_data(self) -> None:
        """Clear ROM data from memory with logging."""
        if hasattr(self, '_rom_mmap') and self._rom_mmap is not None:
            try:
                if hasattr(self._rom_mmap, '__len__'):
                    rom_size = len(self._rom_mmap)
                else:
                    rom_size = 0

                # Close memory map
                if hasattr(self._rom_mmap, 'close') and callable(getattr(self._rom_mmap, 'close', None)):
                    self._rom_mmap.close()
                self._rom_mmap = None

                # Close file handle
                if hasattr(self, '_rom_file') and self._rom_file:
                    self._rom_file.close()
                    self._rom_file = None

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

        # Shutdown thread pool if it exists
        if self._thread_pool:
            try:
                self._thread_pool.shutdown(wait=True, cancel_futures=True)
                logger.debug("Thread pool shutdown complete")
            except Exception as e:
                logger.warning(f"Error shutting down thread pool: {e}")
            finally:
                self._thread_pool = None

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

    def __del__(self) -> None:
        """Ensure cleanup when object is garbage collected."""
        self.cleanup()

    def start_worker(self, rom_path: str, rom_extractor: ROMExtractor | None = None) -> None:
        """Start worker with proper thread management."""
        if self._thread and self._thread.isRunning():
            logger.warning("Worker already running, stopping first")
            self.stop_worker()

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

    @Slot(int, QImage)
    def _on_thumbnail_ready(self, offset: int, qimage: QImage) -> None:
        """Convert QImage to QPixmap in main thread and forward signal."""
        if not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage)
            self.thumbnail_ready.emit(offset, pixmap)

    def queue_thumbnail(self, offset: int, size: int = 128, priority: int = 0) -> None:
        """Queue a thumbnail for generation."""
        if self.worker:
            self.worker.queue_thumbnail(offset, size, priority)

    def queue_batch(self, offsets: list[int], size: int = 128, priority_start: int = 0) -> None:
        """Queue multiple thumbnails for generation."""
        if self.worker:
            self.worker.queue_batch(offsets, size, priority_start)

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
                    if not self._thread.wait(3000):  # Wait up to 3 seconds
                        logger.warning("Thread did not stop within timeout")
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
