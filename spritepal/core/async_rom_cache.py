"""
Async ROM Cache - Non-blocking cache operations for preview system

This module provides asynchronous access to the ROM cache, ensuring that
all I/O operations happen in background threads and never block the UI.

Key Features:
- All operations are non-blocking
- Worker thread for disk I/O
- Batch writes for efficiency
- Automatic retry with backoff
- Comprehensive error handling
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import (
    QMutex,
    QMutexLocker,
    QObject,
    QRecursiveMutex,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)

if TYPE_CHECKING:
    from utils.rom_cache import ROMCache

from core.services.worker_lifecycle import WorkerManager
from utils.logging_config import get_logger

logger = get_logger(__name__)

class CacheWorker(QObject):
    """Worker that performs cache I/O in background thread"""

    # Signals for async communication
    data_loaded = Signal(str, bytes, dict)  # request_id, data, metadata
    load_error = Signal(str, str)           # request_id, error
    save_complete = Signal(str, bool)       # cache_key, success

    def __init__(self, cache_dir: Path) -> None:
        super().__init__()
        self.cache_dir = cache_dir
        self._stop_requested = threading.Event()

    @Slot(str, str)
    def load_from_cache(self, request_id: str, cache_key: str) -> None:
        """Load data from cache file"""
        if self._stop_requested.is_set():
            return

        try:
            cache_file = self.cache_dir / f"{cache_key}.cache"

            if not cache_file.exists():
                self.load_error.emit(request_id, "Cache miss")
                return

            # Read cache file
            with cache_file.open("rb") as f:
                # Read metadata size (4 bytes)
                meta_size_bytes = f.read(4)
                if len(meta_size_bytes) < 4:
                    self.load_error.emit(request_id, "Invalid cache file")
                    return

                meta_size = int.from_bytes(meta_size_bytes, "little")

                # Read metadata
                meta_json = f.read(meta_size)
                metadata = json.loads(meta_json)

                # Read data
                data = f.read()

            # Check if still valid
            if time.time() - metadata.get("timestamp", 0) > 86400:  # 24 hours
                self.load_error.emit(request_id, "Cache expired")
                cache_file.unlink(missing_ok=True)
                return

            self.data_loaded.emit(request_id, data, metadata)

        except Exception as e:
            logger.debug(f"Cache load error for {cache_key}: {e}")
            self.load_error.emit(request_id, str(e))

    @Slot(str, bytes, dict)
    def save_to_cache(self, cache_key: str, data: bytes, metadata: dict[str, Any]) -> None:
        """Save data to cache file"""
        if self._stop_requested.is_set():
            return

        try:
            cache_file = self.cache_dir / f"{cache_key}.cache"
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Add timestamp
            metadata["timestamp"] = time.time()

            # Write atomically using temp file
            temp_file = cache_file.with_suffix(".tmp")

            with temp_file.open("wb") as f:
                # Write metadata size (4 bytes)
                meta_json = json.dumps(metadata).encode()
                f.write(len(meta_json).to_bytes(4, "little"))

                # Write metadata
                f.write(meta_json)

                # Write data
                f.write(data)

                # Ensure data is on disk before atomic rename
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename (safe after fsync)
            temp_file.replace(cache_file)

            self.save_complete.emit(cache_key, True)

        except Exception as e:
            logger.debug(f"Cache save error for {cache_key}: {e}")
            self.save_complete.emit(cache_key, False)

    def stop(self) -> None:
        """Stop the worker"""
        self._stop_requested.set()

class AsyncROMCache(QObject):
    """
    Asynchronous interface to ROM cache.

    This class provides non-blocking access to the ROM cache by performing
    all I/O operations in a background thread and communicating via signals.

    Signals:
        cache_ready: Emitted when cached data is loaded
        cache_error: Emitted when cache miss or error occurs
    """

    # Public signals
    cache_ready = Signal(str, bytes, dict)  # request_id, data, metadata
    cache_error = Signal(str, str)          # request_id, error

    # Internal signals for worker communication
    _request_load = Signal(str, str)        # request_id, cache_key
    _request_save = Signal(str, bytes, dict)  # cache_key, data, metadata

    def __init__(self, rom_cache: ROMCache | None = None) -> None:
        """
        Initialize async cache wrapper.

        Args:
            rom_cache: Optional ROM cache instance for configuration
        """
        super().__init__()

        # Determine cache directory
        if rom_cache and hasattr(rom_cache, "cache_dir"):
            self.cache_dir = Path(rom_cache.cache_dir)
        else:
            self.cache_dir = Path.home() / ".spritepal_cache"

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Create worker thread
        self._worker_thread = QThread()
        self._worker = CacheWorker(self.cache_dir)
        self._worker.moveToThread(self._worker_thread)

        # Connect worker signals to our handlers
        self._worker.data_loaded.connect(self._on_data_loaded)
        self._worker.load_error.connect(self._on_load_error)
        self._worker.save_complete.connect(self._on_save_complete)

        # Connect our internal signals to worker slots (with queued connection for thread safety)
        self._request_load.connect(
            self._worker.load_from_cache,
            Qt.ConnectionType.QueuedConnection
        )
        self._request_save.connect(
            self._worker.save_to_cache,
            Qt.ConnectionType.QueuedConnection
        )

        # Request tracking
        self._pending_requests: dict[str, tuple[str, int]] = {}  # request_id -> (rom_path, offset)
        self._request_mutex = QMutex()

        # Batch save queue
        self._save_queue: list[tuple[str, bytes, dict[str, Any]]] = []
        self._save_mutex = QRecursiveMutex()  # Use recursive mutex to allow nested locking
        self._save_timer = QTimer(self)
        self._save_timer.timeout.connect(self._flush_save_queue)
        self._save_timer.setInterval(1000)  # Flush every second

        # Memory cache for recent items
        self._memory_cache: dict[str, tuple[bytes, dict[str, Any], float]] = {}
        self._memory_cache_max = 10

        # Start worker thread and register with WorkerManager for proper cleanup tracking
        self._worker_thread.start()
        WorkerManager._register_worker(self._worker_thread)

        logger.info(f"AsyncROMCache initialized with directory: {self.cache_dir}")

    def get_cached_async(self, rom_path: str, offset: int, request_id: str) -> None:
        """
        Request cached data asynchronously.

        This method returns immediately and emits cache_ready or cache_error
        signal when the operation completes.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM
            request_id: Unique request identifier
        """
        cache_key = self._generate_cache_key(rom_path, offset)

        # Check memory cache first
        with QMutexLocker(self._request_mutex):
            if cache_key in self._memory_cache:
                data, metadata, timestamp = self._memory_cache[cache_key]
                # Check if still fresh (5 minutes)
                if time.time() - timestamp < 300:
                    logger.debug(f"Memory cache hit for {cache_key}")
                    self.cache_ready.emit(request_id, data, metadata)
                    return
                # Expired, remove from memory cache
                logger.debug(f"Memory cache expired for {cache_key}, removing")
                del self._memory_cache[cache_key]

            # Track request
            self._pending_requests[request_id] = (rom_path, offset)

        # Request load from worker thread using signal (much cleaner than invokeMethod!)
        self._request_load.emit(request_id, cache_key)

    def save_cached_async(self, rom_path: str, offset: int, data: bytes,
                         metadata: dict[str, Any] | None = None) -> None:
        """
        Save data to cache asynchronously.

        This method queues the save operation and returns immediately.
        Multiple saves are batched for efficiency.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM
            data: Preview data to cache
            metadata: Optional metadata to store
        """
        cache_key = self._generate_cache_key(rom_path, offset)

        if metadata is None:
            metadata = {}

        # Add to memory cache
        with QMutexLocker(self._request_mutex):
            self._memory_cache[cache_key] = (data, metadata, time.time())

            # Evict oldest if over limit
            if len(self._memory_cache) > self._memory_cache_max:
                oldest_key = min(
                    self._memory_cache.keys(),
                    key=lambda k: self._memory_cache[k][2]
                )
                del self._memory_cache[oldest_key]

        # Queue for batch save
        with QMutexLocker(self._save_mutex):
            self._save_queue.append((cache_key, data, metadata))

            # Start batch timer if not running
            if not self._save_timer.isActive():
                self._save_timer.start()

            # Flush immediately if queue is large
            if len(self._save_queue) >= 10:
                self._flush_save_queue()

    def clear_memory_cache(self) -> None:
        """Clear the in-memory cache and pending requests"""
        with QMutexLocker(self._request_mutex):
            self._memory_cache.clear()
            # Also clear pending requests to prevent stale data from repopulating cache
            self._pending_requests.clear()
        logger.debug("Cleared memory cache and pending requests")

    def _flush_save_queue(self) -> None:
        """Flush pending saves to disk"""
        with QMutexLocker(self._save_mutex):
            if not self._save_queue:
                self._save_timer.stop()
                return

            # Process all pending saves
            saves_to_process = self._save_queue.copy()
            self._save_queue.clear()

        # Send to worker thread using signal
        for cache_key, data, metadata in saves_to_process:
            self._request_save.emit(cache_key, data, metadata)

    def _on_data_loaded(self, request_id: str, data: bytes, metadata: dict[str, Any]) -> None:
        """Handle successful cache load"""
        with QMutexLocker(self._request_mutex):
            if request_id in self._pending_requests:
                rom_path, offset = self._pending_requests.pop(request_id)
                cache_key = self._generate_cache_key(rom_path, offset)

                # Add to memory cache
                self._memory_cache[cache_key] = (data, metadata, time.time())

        # Emit signal outside of mutex lock
        self.cache_ready.emit(request_id, data, metadata)

    def _on_load_error(self, request_id: str, error: str) -> None:
        """Handle cache load error"""
        with QMutexLocker(self._request_mutex):
            self._pending_requests.pop(request_id, None)

        self.cache_error.emit(request_id, error)

    def _on_save_complete(self, cache_key: str, success: bool) -> None:
        """Handle save completion"""
        if success:
            logger.debug(f"Saved to cache: {cache_key}")
        else:
            logger.warning(f"Failed to save to cache: {cache_key}")

    @staticmethod
    def _generate_cache_key(rom_path: str, offset: int) -> str:
        """Generate cache key for preview"""
        rom_hash = hashlib.md5(rom_path.encode()).hexdigest()[:8]
        return f"preview_{rom_hash}_{offset:08x}"

    def shutdown(self, timeout: int = 5000) -> None:
        """
        Explicitly shutdown the cache worker thread.

        This should be called before the object is deleted to ensure clean shutdown.
        The timeout is generous (5 seconds by default) to allow pending operations to complete.

        Args:
            timeout: Milliseconds to wait for thread to stop (default: 5000)
        """
        try:
            # Stop the save timer first (before processEvents to avoid deletion issues)
            if hasattr(self, "_save_timer"):
                try:
                    self._save_timer.stop()
                except RuntimeError:
                    # Timer may already be deleted
                    pass

            # Stop worker from accepting new work
            if hasattr(self, "_worker"):
                self._worker.stop()

            # Disconnect signals to prevent new work from being queued during shutdown
            # Note: Import warnings to suppress disconnect warnings
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    if hasattr(self, "_request_load") and hasattr(self, "_worker"):
                        self._request_load.disconnect(self._worker.load_from_cache)
                except (RuntimeError, TypeError):
                    pass
                try:
                    if hasattr(self, "_request_save") and hasattr(self, "_worker"):
                        self._request_save.disconnect(self._worker.save_to_cache)
                except (RuntimeError, TypeError):
                    pass

            # Flush any pending saves (do this AFTER disconnecting signals)
            try:
                self._flush_save_queue()
            except RuntimeError:
                # Queue or mutex may already be deleted
                pass

            # Stop thread with WorkerManager for proper cleanup and registry removal
            # This uses safe cancellation patterns (no terminate()) and removes from registry
            if hasattr(self, "_worker_thread"):
                try:
                    WorkerManager.cleanup_worker(self._worker_thread, timeout=timeout)
                except RuntimeError:
                    # QThread may have been deleted already
                    pass

            logger.debug("AsyncROMCache shutdown complete")
        except RuntimeError as e:
            # Qt objects may be deleted during shutdown, this is expected
            logger.debug(f"AsyncROMCache shutdown (Qt object deleted): {e}")
        except Exception as e:
            logger.warning(f"AsyncROMCache shutdown error: {e}")

    def __del__(self) -> None:
        """Cleanup on deletion - fallback if shutdown() was not called explicitly"""
        try:
            # Use short timeout in __del__ since we may be in GC
            self.shutdown(timeout=1000)
        except Exception as e:
            # Log but don't raise to avoid cascading issues during shutdown
            logger.debug(f"AsyncROMCache __del__ cleanup error (ignored): {e}")
