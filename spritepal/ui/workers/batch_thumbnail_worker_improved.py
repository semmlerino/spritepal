"""
Improved batch thumbnail worker using proper moveToThread pattern.
This demonstrates the correct Qt threading architecture.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from queue import PriorityQueue
from typing import Any

from PySide6.QtCore import (
    QMutex,
    QMutexLocker,
    QObject,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage

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

    def __lt__(self, other: object):
        """For priority queue sorting (lower priority value = higher priority)."""
        if not isinstance(other, ThumbnailRequest):
            return NotImplemented
        return self.priority < other.priority

class BatchThumbnailWorker(QObject):
    """
    Worker for batch thumbnail generation - PROPER PATTERN.
    Uses moveToThread instead of subclassing QThread.
    """

    # Signals - Use QImage instead of QPixmap for thread safety
    # QPixmap must only be used in GUI thread; QImage is thread-safe
    thumbnail_ready = Signal(int, QImage)  # offset, qimage (thread-safe)
    progress = Signal(int, int)  # current, total
    error = Signal(str)
    started = Signal()
    finished = Signal()

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
            parent: Parent object (None for moveToThread pattern)
        """
        super().__init__(parent)

        self.rom_path = rom_path
        self.rom_extractor = rom_extractor or ROMExtractor()
        self.tile_renderer = TileRenderer()

        # Thread control
        self._stop_requested = False
        self._pause_requested = False
        self._control_mutex = QMutex()

        # Request queue with proper mutex
        self._queue_mutex = QMutex()
        self._request_queue: PriorityQueue[Any] = PriorityQueue()
        self._pending_count = 0
        self._completed_count = 0

        # Cache with proper thread-safe access (use QImage, not QPixmap, for thread safety)
        self._cache_mutex = QMutex()
        self._cache: dict[tuple[int, int], QImage] = {}
        self._cache_size_limit = 100

        # ROM data
        self._rom_data: bytes | None = None

        # Timer and other QObjects will be created in initialize()
        self._process_timer = None

    @Slot()
    def initialize(self):
        """
        Initialize thread-local objects.
        MUST be called AFTER moveToThread() to ensure proper thread affinity.
        """
        # Create QTimer in the worker thread
        from PySide6.QtCore import QTimer
        self._process_timer = QTimer()
        self._process_timer.timeout.connect(self._process_next_request)
        self._process_timer.setInterval(10)  # Process every 10ms

        logger.info("Worker initialized in thread: %s", QThread.currentThread())

    @Slot(int, int, int)
    def queue_thumbnail(self, offset: int, size: int = 128, priority: int = 0):
        """
        Queue a thumbnail for generation (thread-safe).

        Args:
            offset: ROM offset of sprite
            size: Thumbnail size in pixels
            priority: Priority (0 = highest)
        """
        request = ThumbnailRequest(offset, size, priority)

        with QMutexLocker(self._queue_mutex):
            self._request_queue.put(request)
            self._pending_count += 1

    @Slot(list, int, int)
    def queue_batch(self, offsets: list[int], size: int = 128, priority_start: int = 0):
        """
        Queue multiple thumbnails for generation (thread-safe).

        Args:
            offsets: List of ROM offsets
            size: Thumbnail size for all
            priority_start: Starting priority
        """
        with QMutexLocker(self._queue_mutex):
            for i, offset in enumerate(offsets):
                request = ThumbnailRequest(offset, size, priority_start + i)
                self._request_queue.put(request)
                self._pending_count += 1

    @Slot()
    def clear_queue(self):
        """Clear all pending requests (thread-safe)."""
        with QMutexLocker(self._queue_mutex):
            while not self._request_queue.empty():
                try:
                    self._request_queue.get_nowait()
                except Exception:
                    break
            self._pending_count = 0

    @Slot()
    def start_processing(self):
        """Start processing thumbnails."""
        logger.info("Starting thumbnail processing in thread: %s", QThread.currentThread())

        # Load ROM data once
        self._load_rom_data()

        # Start processing timer
        if self._process_timer:
            self._process_timer.start()

        self.started.emit()

    @Slot()
    def stop(self):
        """Request the worker to stop (thread-safe)."""
        with QMutexLocker(self._control_mutex):
            self._stop_requested = True

        # Stop timer
        if self._process_timer:
            self._process_timer.stop()

        # Clear queue
        self.clear_queue()

        # Emit finished
        self.finished.emit()

    @Slot()
    def pause(self):
        """Pause thumbnail generation (thread-safe)."""
        with QMutexLocker(self._control_mutex):
            self._pause_requested = True

        if self._process_timer:
            self._process_timer.stop()

    @Slot()
    def resume(self):
        """Resume thumbnail generation (thread-safe)."""
        with QMutexLocker(self._control_mutex):
            self._pause_requested = False

        if self._process_timer:
            self._process_timer.start()

    @Slot()
    def _process_next_request(self):
        """Process the next thumbnail request from the queue."""
        # Check control flags
        with QMutexLocker(self._control_mutex):
            if self._stop_requested or self._pause_requested:
                return

        # Get next request
        request = self._get_next_request()
        if not request:
            return

        logger.debug(f"Processing thumbnail: offset=0x{request.offset:06X}")

        # Check cache first (thread-safe)
        cache_key = (request.offset, request.size)
        pixmap = self._get_from_cache(cache_key)

        if pixmap:
            self.thumbnail_ready.emit(request.offset, pixmap)
            self._update_progress()
            return

        # Generate thumbnail
        pixmap = self._generate_thumbnail(request)

        if pixmap and not pixmap.isNull():
            # Cache it (thread-safe)
            self._add_to_cache(cache_key, pixmap)

            # Emit result
            self.thumbnail_ready.emit(request.offset, pixmap)

        self._update_progress()

    def _get_next_request(self) -> ThumbnailRequest | None:
        """Get the next request from the queue (thread-safe)."""
        with QMutexLocker(self._queue_mutex):
            if not self._request_queue.empty():
                try:
                    return self._request_queue.get_nowait()
                except Exception:
                    pass
        return None

    def _get_from_cache(self, key: tuple[int, int]) -> QImage | None:
        """Get QImage from cache (thread-safe)."""
        with QMutexLocker(self._cache_mutex):
            return self._cache.get(key)

    def _add_to_cache(self, key: tuple[int, int], qimage: QImage):
        """Add QImage to cache (thread-safe)."""
        with QMutexLocker(self._cache_mutex):
            # Limit cache size
            if len(self._cache) >= self._cache_size_limit:
                # Remove oldest entry
                first_key = next(iter(self._cache))
                del self._cache[first_key]

            self._cache[key] = qimage

    def _update_progress(self):
        """Update and emit progress (thread-safe)."""
        with QMutexLocker(self._queue_mutex):
            self._completed_count += 1
            total = self._pending_count + self._completed_count
            if total > 0:
                self.progress.emit(self._completed_count, total)

    def _load_rom_data(self):
        """Load ROM data into memory."""
        try:
            with Path(self.rom_path).open('rb') as f:
                self._rom_data = f.read()
            logger.info(f"Loaded ROM data: {len(self._rom_data)} bytes")
        except Exception as e:
            logger.error(f"Failed to load ROM: {e}")
            self.error.emit(f"Failed to load ROM: {e}")

    def _generate_thumbnail(self, request: ThumbnailRequest) -> QImage | None:
        """
        Generate a thumbnail for a sprite (thread-safe).

        Args:
            request: Thumbnail request

        Returns:
            Generated QImage (thread-safe) or None
        """
        if not self._rom_data:
            return None

        try:
            # Use QImage instead of QPixmap for thread safety
            # QPixmap must only be used in GUI thread; QImage is thread-safe
            qimage = QImage(request.size, request.size, QImage.Format.Format_ARGB32)
            qimage.fill(Qt.GlobalColor.gray)
            return qimage

        except Exception as e:
            logger.debug(f"Failed to generate thumbnail: {e}")
            return None

    @Slot(result=int)
    def get_cache_size(self) -> int:
        """Get current cache size (thread-safe)."""
        with QMutexLocker(self._cache_mutex):
            return len(self._cache)

    @Slot()
    def clear_cache(self):
        """Clear the thumbnail cache (thread-safe)."""
        with QMutexLocker(self._cache_mutex):
            if self._cache:
                self._cache.clear()

    @Slot()
    def cleanup(self):
        """Clean up worker resources (thread-safe)."""
        logger.debug("Worker cleanup started")

        # Stop processing
        self.stop()

        # Clear cache
        self.clear_cache()

        # Clear ROM data
        self._rom_data = None

        # Clean up timer
        if self._process_timer:
            self._process_timer.deleteLater()
            self._process_timer = None

        logger.debug("Worker cleanup completed")

class ThumbnailController(QObject):
    """
    Controller for managing thumbnail worker with proper threading.
    This demonstrates the CORRECT pattern for Qt threading.
    """

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        self.worker: BatchThumbnailWorker | None = None
        self._worker_thread: QThread | None = None

    def start_worker(self, rom_path: str, rom_extractor: ROMExtractor | None = None):
        """Start the thumbnail worker with proper threading."""

        # Create thread and worker
        self._worker_thread = QThread()
        self.worker = BatchThumbnailWorker(rom_path, rom_extractor)

        # Move worker to thread BEFORE connecting signals
        self.worker.moveToThread(self._worker_thread)

        # Connect initialization
        self._worker_thread.started.connect(self.worker.initialize)

        # Connect cleanup signals for proper lifecycle
        self.worker.finished.connect(self._worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        # Start thread
        self._worker_thread.start()

        # After thread starts, initialize and start processing
        QTimer.singleShot(100, self.worker.start_processing)

    def stop_worker(self):
        """Stop the worker with proper cleanup."""
        if self.worker:
            self.worker.stop()

        if self._worker_thread and self._worker_thread.isRunning():
            self._worker_thread.quit()
            self._worker_thread.wait(3000)  # Wait up to 3 seconds

        self.worker = None
        self._worker_thread = None
