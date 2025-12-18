"""
Preview Orchestrator - Central coordination for async preview system

This module implements the core orchestration layer for the new preview architecture,
providing non-blocking preview generation with multi-tier caching and comprehensive
error handling.

Key Features:
- Async-first design with zero main thread blocking
- Three-tier caching (widget, memory, disk)
- Request prioritization and cancellation
- Comprehensive error propagation
- Performance monitoring and metrics
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum, auto
from queue import Empty, PriorityQueue
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QTimer, Signal

if TYPE_CHECKING:
    from PySide6.QtGui import QPixmap

    from core.async_rom_cache import AsyncROMCache
    from core.services.rom_cache import ROMCache

from utils.logging_config import get_logger

logger = get_logger(__name__)

class Priority(Enum):
    """Request priority levels"""
    LOW = 3      # Background prefetch
    NORMAL = 2   # User scrolling
    HIGH = 1     # User selection
    URGENT = 0   # User waiting

class ErrorType(Enum):
    """Error categories for handling strategy"""
    FILE_IO = auto()
    DECOMPRESSION = auto()
    INVALID_DATA = auto()
    CACHE_MISS = auto()
    WORKER_BUSY = auto()
    CANCELLED = auto()
    UNKNOWN = auto()

@dataclass
class PreviewRequest:
    """Encapsulates a preview generation request"""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rom_path: str = ""
    offset: int = 0
    priority: Priority = Priority.NORMAL
    timestamp: float = field(default_factory=time.time)
    cancelled: bool = False
    callback: Callable[[PreviewData], None] | None = None

    def __lt__(self, other: PreviewRequest) -> bool:
        """Support priority queue ordering"""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.timestamp < other.timestamp  # FIFO for same priority

@dataclass
class PreviewData:
    """Encapsulates preview display data"""
    pixmap: QPixmap | None = None
    tile_data: bytes = b""
    width: int = 0
    height: int = 0
    offset: int = 0
    rom_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: float = field(default_factory=time.time)
    cache_key: str = ""

    @property
    def size_bytes(self) -> int:
        """Calculate approximate memory size"""
        pixmap_size = (self.width * self.height * 4) if self.pixmap else 0
        return pixmap_size + len(self.tile_data)

@dataclass
class PreviewError:
    """Encapsulates preview generation errors"""
    request_id: str = ""
    error_type: ErrorType = ErrorType.UNKNOWN
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    recoverable: bool = True
    retry_after: float | None = None
    timestamp: float = field(default_factory=time.time)

@dataclass
class PreviewMetrics:
    """Performance metrics for monitoring"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    errors: int = 0
    cancellations: int = 0
    total_time: float = 0.0
    # Bounded deque to prevent unbounded memory growth (last 1000 samples)
    generation_times: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit percentage"""
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0

    @property
    def avg_response_time(self) -> float:
        """Calculate average response time"""
        return self.total_time / self.total_requests if self.total_requests > 0 else 0.0

    @property
    def p99_response_time(self) -> float:
        """Calculate 99th percentile response time"""
        if not self.generation_times:
            return 0.0
        sorted_times = sorted(self.generation_times)
        index = int(len(sorted_times) * 0.99)
        return sorted_times[min(index, len(sorted_times) - 1)]

class PreviewOrchestrator(QObject):
    """
    Central coordinator for the preview system.

    This class orchestrates all preview operations, managing requests,
    caching, worker allocation, and error handling. It provides a
    simple async interface while handling all complexity internally.

    Signals:
        preview_ready: Emitted when preview is ready for display
        preview_loading: Emitted when preview generation starts
        preview_error: Emitted when preview generation fails
        metrics_updated: Emitted when performance metrics change
    """

    # Public signals
    preview_ready = Signal(str, object)  # request_id, PreviewData
    preview_loading = Signal(str, str)   # request_id, message
    preview_error = Signal(str, object)  # request_id, PreviewError
    metrics_updated = Signal(object)     # PreviewMetrics

    def __init__(
        self,
        parent: QObject | None = None,
        worker_pool_factory: Callable[[], Any] | None = None,
    ):
        """
        Initialize the preview orchestrator.

        Args:
            parent: Optional Qt parent object
            worker_pool_factory: Factory function that creates a worker pool instance
                implementing PreviewWorkerPoolProtocol. Required for preview generation.
                The factory is called lazily on first preview request.

        Raises:
            RuntimeError: If worker_pool_factory is not provided and a preview is requested.
        """
        super().__init__(parent)

        # Request management
        self._request_queue: PriorityQueue[PreviewRequest] = PriorityQueue()
        self._active_requests: dict[str, PreviewRequest] = {}
        self._request_mutex = QMutex()

        # Caching layers (initialized lazily)
        self._memory_cache: PreviewMemoryCache | None = None
        self._async_cache: AsyncROMCache | None = None
        self._last_preview: PreviewData | None = None

        # Worker management (initialized lazily via factory)
        self._worker_pool: Any | None = None
        self._worker_pool_factory = worker_pool_factory

        # Performance tracking
        self._metrics = PreviewMetrics()
        self._metrics_timer = QTimer(self)
        self._metrics_timer.timeout.connect(self._emit_metrics)
        # Only start timer if we're in a thread with event loop (Qt main thread)
        # Timers can only be used with threads started with QThread
        try:
            self._metrics_timer.start(5000)  # Emit metrics every 5 seconds
        except RuntimeError:
            logger.debug("Metrics timer not started - not in Qt thread context")

        # Request processing
        self._process_timer = QTimer(self)
        self._process_timer.timeout.connect(self._process_next_request)
        self._process_timer.setInterval(10)  # Check every 10ms for new requests

        # Configuration
        self._max_concurrent_requests = 4
        self._request_timeout_ms = 5000

        logger.info("PreviewOrchestrator initialized")

    def request_preview(self, rom_path: str, offset: int,
                       priority: Priority = Priority.NORMAL,
                       callback: Callable[[PreviewData], None] | None = None) -> str:
        """
        Request a preview with specified priority.

        This method is non-blocking and returns immediately with a request ID.
        The preview will be delivered via signals when ready.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM for preview
            priority: Request priority for queue ordering
            callback: Optional callback for preview delivery

        Returns:
            Request ID for tracking/cancellation
        """
        request = PreviewRequest(
            rom_path=rom_path,
            offset=offset,
            priority=priority,
            callback=callback
        )

        with QMutexLocker(self._request_mutex):
            # Check if we have this in L1 cache (last preview)
            if self._last_preview and self._last_preview.offset == offset:
                logger.debug(f"L1 cache hit for offset {offset:#x}")
                self._metrics.total_requests += 1
                self._metrics.cache_hits += 1
                self._deliver_preview(request.request_id, self._last_preview, callback)
                return request.request_id

            # Check L2 cache (memory)
            if self._memory_cache:
                cache_key = self._generate_cache_key(rom_path, offset)
                if cached := self._memory_cache.get(cache_key):
                    logger.debug(f"L2 cache hit for offset {offset:#x}")
                    self._metrics.total_requests += 1
                    self._metrics.cache_hits += 1
                    self._deliver_preview(request.request_id, cached, callback)
                    return request.request_id

            # Add to queue for async processing
            logger.debug(f"Queuing request {request.request_id} for offset {offset:#x}")
            self._metrics.total_requests += 1
            self._metrics.cache_misses += 1

            self._active_requests[request.request_id] = request
            self._request_queue.put(request)

            # Start processing if not already running
            if not self._process_timer.isActive():
                self._process_timer.start()

            # Emit loading signal
            self.preview_loading.emit(request.request_id, f"Loading preview for {offset:#x}...")

        return request.request_id

    def cancel_request(self, request_id: str) -> None:
        """
        Cancel a pending request.

        Args:
            request_id: ID of request to cancel
        """
        with QMutexLocker(self._request_mutex):
            if request := self._active_requests.get(request_id):
                request.cancelled = True
                self._metrics.cancellations += 1
                logger.debug(f"Cancelled request {request_id}")

    def clear_cache(self) -> None:
        """Clear all cache layers"""
        self._last_preview = None
        if self._memory_cache:
            self._memory_cache.clear()
        if self._async_cache:
            self._async_cache.clear_memory_cache()
        logger.info("Cleared all preview caches")

    def set_rom_cache(self, rom_cache: ROMCache) -> None:
        """
        Set ROM cache for disk-based caching.

        Args:
            rom_cache: ROM cache instance for persistent storage
        """
        if not self._async_cache:
            from core.async_rom_cache import AsyncROMCache
            self._async_cache = AsyncROMCache(rom_cache)
            self._async_cache.cache_ready.connect(self._on_cache_ready)
            self._async_cache.cache_error.connect(self._on_cache_error)

    def _process_next_request(self) -> None:
        """Process the next request from the queue"""
        if self._request_queue.empty():
            self._process_timer.stop()
            return

        # Check concurrent request limit
        active_count = sum(
            1 for r in self._active_requests.values()
            if not r.cancelled
        )
        if active_count >= self._max_concurrent_requests:
            return

        # Get next request
        try:
            request = self._request_queue.get_nowait()
        except Empty:
            return

        # Skip if cancelled
        if request.cancelled:
            self._active_requests.pop(request.request_id, None)
            return

        # Process request
        self._execute_request(request)

    def _execute_request(self, request: PreviewRequest) -> None:
        """Execute a preview request through cache layers"""
        time.time()

        # Check L3 cache (disk) if available
        if self._async_cache:
            self._async_cache.get_cached_async(
                request.rom_path,
                request.offset,
                request.request_id
            )
        else:
            # No disk cache, go straight to generation
            self._generate_preview(request)

    def _generate_preview(self, request: PreviewRequest) -> None:
        """Generate preview using worker pool."""
        if not self._worker_pool:
            if self._worker_pool_factory:
                # Use injected factory
                self._worker_pool = self._worker_pool_factory()
            else:
                raise RuntimeError(
                    "PreviewOrchestrator requires worker_pool_factory. "
                    "Pass a factory function to the constructor that creates a "
                    "worker pool implementing PreviewWorkerPoolProtocol."
                )
            # Connect signals - worker_pool is guaranteed non-None at this point
            assert self._worker_pool is not None
            self._worker_pool.preview_ready.connect(self._on_preview_ready)
            self._worker_pool.preview_error.connect(self._on_preview_error)

        # Check if generate_preview method exists
        if hasattr(self._worker_pool, 'generate_preview'):
            self._worker_pool.generate_preview(
                request.request_id,
                request.rom_path,
                request.offset
            )
        else:
            logger.error("generate_preview method not found on worker pool")

    def _deliver_preview(
        self,
        request_id: str,
        preview_data: PreviewData,
        callback: Callable[[PreviewData], None] | None = None
    ) -> None:
        """Deliver preview to requestor"""
        # Update L1 cache
        self._last_preview = preview_data

        # Store in L2 cache
        if self._memory_cache:
            cache_key = self._generate_cache_key(
                preview_data.rom_path,
                preview_data.offset
            )
            self._memory_cache.put(cache_key, preview_data)

        # Emit signal
        self.preview_ready.emit(request_id, preview_data)

        # Call callback if provided - check parameter first, then active_requests
        if callback:
            callback(preview_data)
        elif request := self._active_requests.get(request_id):
            if request.callback:
                request.callback(preview_data)

        # Clean up
        self._active_requests.pop(request_id, None)

    def _on_cache_ready(self, request_id: str, data: bytes, metadata: dict[str, Any]) -> None:
        """Handle cache hit from async cache"""
        if request := self._active_requests.get(request_id):
            if not request.cancelled:
                preview_data = PreviewData(
                    tile_data=data,
                    offset=request.offset,
                    rom_path=request.rom_path,
                    metadata=metadata,
                    width=metadata.get("width", 128),
                    height=metadata.get("height", 128)
                )
                self._deliver_preview(request_id, preview_data)

    def _on_cache_error(self, request_id: str, error: str) -> None:
        """Handle cache miss - generate preview"""
        if request := self._active_requests.get(request_id):
            if not request.cancelled:
                self._generate_preview(request)

    def _on_preview_ready(self, request_id: str, preview_data: PreviewData) -> None:
        """Handle completed preview from worker"""
        if request := self._active_requests.get(request_id):
            if not request.cancelled:
                # Store in disk cache for next time
                if self._async_cache:
                    self._async_cache.save_cached_async(
                        request.rom_path,
                        request.offset,
                        preview_data.tile_data,
                        preview_data.metadata
                    )

                self._deliver_preview(request_id, preview_data)

                # Update metrics
                generation_time = time.time() - request.timestamp
                self._metrics.generation_times.append(generation_time)
                self._metrics.total_time += generation_time

    def _on_preview_error(self, request_id: str, error: PreviewError) -> None:
        """Handle preview generation error"""
        self._metrics.errors += 1
        self.preview_error.emit(request_id, error)
        self._active_requests.pop(request_id, None)

    def _emit_metrics(self) -> None:
        """Emit current performance metrics"""
        self.metrics_updated.emit(self._metrics)

        # Log if performance is degraded
        if self._metrics.cache_hit_rate < 50:
            logger.warning(f"Low cache hit rate: {self._metrics.cache_hit_rate:.1f}%")
        if self._metrics.avg_response_time > 0.2:
            logger.warning(f"High average response time: {self._metrics.avg_response_time:.3f}s")

    @staticmethod
    def _generate_cache_key(rom_path: str, offset: int) -> str:
        """Generate cache key for preview"""
        import hashlib
        rom_hash = hashlib.md5(rom_path.encode()).hexdigest()[:8]
        return f"{rom_hash}_{offset:08x}"

    def cleanup(self) -> None:
        """Clean up resources including async cache worker thread."""
        # Stop the process timer
        if self._process_timer:
            self._process_timer.stop()

        # Stop the metrics timer
        if self._metrics_timer:
            self._metrics_timer.stop()

        # Shutdown worker pool
        if self._worker_pool:
            self._worker_pool.cleanup()
            self._worker_pool = None

        # Shutdown async cache worker thread
        if self._async_cache:
            self._async_cache.shutdown()
            self._async_cache = None

        # Clear caches
        if self._memory_cache is not None:
            self._memory_cache.clear()
        self._active_requests.clear()

        logger.debug("PreviewOrchestrator cleanup complete")

    def __del__(self) -> None:
        """Ensure cleanup on deletion to prevent thread leaks."""
        with suppress(Exception):
            self.cleanup()


class PreviewMemoryCache:
    """LRU memory cache for preview data"""

    def __init__(self, max_size_mb: int = 10):
        """Initialize memory cache with size limit"""
        from collections import OrderedDict

        self._cache: OrderedDict[str, PreviewData] = OrderedDict()
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._current_size_bytes = 0
        self._mutex = QMutex()

    def get(self, key: str) -> PreviewData | None:
        """Get item from cache"""
        with QMutexLocker(self._mutex):
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def put(self, key: str, data: PreviewData) -> None:
        """Store item in cache with LRU eviction"""
        with QMutexLocker(self._mutex):
            # Remove if already exists
            if key in self._cache:
                old_data = self._cache[key]
                self._current_size_bytes -= old_data.size_bytes
                del self._cache[key]

            # Add new data
            self._cache[key] = data
            self._current_size_bytes += data.size_bytes

            # Evict if over size limit
            while self._current_size_bytes > self._max_size_bytes and self._cache:
                # Remove least recently used
                oldest_key, oldest_data = self._cache.popitem(last=False)
                self._current_size_bytes -= oldest_data.size_bytes
                logger.debug(f"Evicted {oldest_key} from memory cache")

    def clear(self) -> None:
        """Clear all cached items"""
        with QMutexLocker(self._mutex):
            self._cache.clear()
            self._current_size_bytes = 0
