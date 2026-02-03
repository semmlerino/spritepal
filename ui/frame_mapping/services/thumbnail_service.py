"""Thumbnail generation service for frame mapping UI.

This service provides consistent thumbnail generation for AI frames and game frames,
ensuring WYSIWYG behavior by using the same quantization logic as injection.
"""

from __future__ import annotations

import hashlib
import io
import os
import time
from tempfile import gettempdir
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal
from PySide6.QtGui import QImage, QPixmap

from core.palette_utils import (
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    quantize_to_palette,
    quantize_with_mappings,
)
from core.services.image_utils import pil_to_qimage
from ui.common import WorkerManager
from ui.frame_mapping.services.thumbnail_disk_cache import ThumbnailDiskCache
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette

logger = get_logger(__name__)


def _compute_cache_key(
    path: Path,
    mtime: float,
    palette_colors: tuple[tuple[int, int, int], ...],
    palette_mappings: dict[tuple[int, int, int], int] | None,
    background_color: tuple[int, int, int] | None,
    background_tolerance: int,
    size: int,
) -> str:
    """Compute stable SHA-256 cache key for thumbnail parameters.

    Key includes all parameters that affect thumbnail appearance:
    - Source file path and modification time
    - Palette colors and mappings (for quantization)
    - Background removal settings
    - Thumbnail size
    """
    # Build key string from all parameters
    key_parts = [
        str(path),
        str(mtime),
        str(palette_colors),
        str(sorted(palette_mappings.items()) if palette_mappings else None),
        str(background_color),
        str(background_tolerance),
        str(size),
    ]
    key_string = "|".join(key_parts)

    # Return first 16 chars of SHA-256 hash
    return hashlib.sha256(key_string.encode()).hexdigest()[:16]


_disk_cache: ThumbnailDiskCache | None = None


def get_disk_cache() -> ThumbnailDiskCache:
    """Get or create singleton disk cache instance."""
    global _disk_cache
    if _disk_cache is None:
        from core.app_context import get_app_context
        try:
            config = get_app_context().configuration_service
            cache_dir = config.cache_directory / "thumbnails" / "v1" / "quantized"
        except RuntimeError:
            if not os.environ.get("SPRITEPAL_TESTING"):
                raise
            worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
            cache_dir = Path(gettempdir()) / f"spritepal_thumbnails_{worker_id}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        _disk_cache = ThumbnailDiskCache(cache_dir, max_size_mb=100)
    return _disk_cache


# Default thumbnail size for list items and table cells
DEFAULT_THUMBNAIL_SIZE = 64

# Maximum cached thumbnails (balances memory vs cache hits)
_THUMBNAIL_CACHE_MAXSIZE = 500

# QPixmap-level cache to avoid redundant PNG decoding
# Key: (path_str, mtime, palette_hash, size) -> QPixmap
# This cache is separate from the LRU cache which stores PNG bytes
_pixmap_cache: dict[tuple[str, float, int, int], QPixmap] = {}
_PIXMAP_CACHE_MAXSIZE = 200


@lru_cache(maxsize=_THUMBNAIL_CACHE_MAXSIZE)
def _cached_thumbnail_bytes(
    path_str: str,
    mtime: float,
    palette_hash: int,
    size: int,
) -> bytes | None:
    """Generate and cache thumbnail as PNG bytes.

    This is the cached backend for create_quantized_thumbnail(). Uses PNG bytes
    as the cache value since QPixmap isn't hashable and LRU cache needs
    immutable return values.

    Args:
        path_str: String path to the image file
        mtime: File modification time (for cache invalidation)
        palette_hash: Hash of the palette (for cache invalidation)
        size: Thumbnail size in pixels

    Returns:
        PNG bytes of the thumbnail, or None on failure
    """
    # Note: This function is called only on cache miss.
    # The actual implementation loads the image, quantizes it, and returns PNG bytes.
    # The caller will convert PNG bytes back to QPixmap.
    frame_path = Path(path_str)
    if not frame_path.exists():
        return None

    try:
        pil_image = Image.open(frame_path)
    except Exception:
        logger.warning("Failed to load image: %s", frame_path)
        return None

    # Quantization is handled by the caller since we don't have the palette object here
    # This function just stores raw image bytes; quantization happens after cache lookup

    # Scale the image
    pil_image.thumbnail((size, size), Image.Resampling.LANCZOS)

    # Convert to PNG bytes
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return buffer.getvalue()


def clear_all_thumbnail_caches() -> None:
    """Clear in-memory and disk thumbnail caches.

    Call this when the palette changes to ensure thumbnails are regenerated
    with the new palette colors.
    """
    # Existing in-memory cache clearing
    _cached_thumbnail_bytes.cache_clear()
    _cached_quantized_thumbnail_bytes.cache_clear()
    _pixmap_cache.clear()

    # Clear disk cache
    try:
        get_disk_cache().clear()
    except Exception as e:
        logger.warning(f"Failed to clear disk cache: {e}")

    logger.debug("All thumbnail caches cleared")


@lru_cache(maxsize=_THUMBNAIL_CACHE_MAXSIZE)
def _cached_quantized_thumbnail_bytes(
    path_str: str,
    mtime: float,
    palette_colors: tuple[tuple[int, int, int], ...],
    palette_mappings: tuple[tuple[tuple[int, int, int], int], ...] | None,
    background_color: tuple[int, int, int] | None,
    background_tolerance: int,
    size: int,
) -> bytes | None:
    """Generate and cache a quantized thumbnail as PNG bytes.

    Args:
        path_str: String path to the image file
        mtime: File modification time (for cache invalidation)
        palette_colors: Tuple of (R, G, B) color tuples
        palette_mappings: Tuple of ((R, G, B), index) mappings, or None
        background_color: Background color for removal, or None
        background_tolerance: Tolerance for background removal
        size: Thumbnail size in pixels

    Returns:
        PNG bytes of the quantized thumbnail, or None on failure
    """
    frame_path = Path(path_str)
    if not frame_path.exists():
        return None

    # Check disk cache
    disk_cache = get_disk_cache()
    palette_mappings_dict = dict(palette_mappings) if palette_mappings else None
    cache_key = _compute_cache_key(
        frame_path,
        mtime,
        palette_colors,
        palette_mappings_dict,
        background_color,
        background_tolerance,
        size,
    )
    cached_bytes = disk_cache.get(cache_key)
    if cached_bytes:
        return cached_bytes

    try:
        pil_image = Image.open(frame_path)
    except Exception:
        logger.warning("Failed to load image: %s", frame_path)
        return None

    # Ensure RGBA for quantization
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")

    # Apply background removal if configured
    if background_color is not None:
        from core.services.content_bounds_analyzer import remove_background

        pil_image = remove_background(pil_image, background_color, background_tolerance)

    # Scale FIRST, then quantize.
    # Quantization with LAB color space is O(pixels * palette * mappings),
    # so scaling before quantizing is much faster for large images.
    pil_image.thumbnail((size, size), Image.Resampling.LANCZOS)

    # Apply quantization (on smaller scaled image)
    try:
        # Convert tuple to list for quantization functions
        palette_list = list(palette_colors)
        if palette_mappings:
            # Convert back to dict format for quantize_with_mappings
            mappings_dict = dict(palette_mappings)
            indexed = quantize_with_mappings(
                pil_image,
                palette_list,
                mappings_dict,
                transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
            )
        else:
            indexed = quantize_to_palette(
                pil_image,
                palette_list,
                transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
            )
        # Convert indexed back to RGBA for display
        pil_image = indexed.convert("RGBA")
    except Exception:
        logger.debug("Failed to quantize image: %s", frame_path)
        # Fall through to use original image

    # Convert to PNG bytes
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    # Save to disk cache
    metadata = {
        "path": str(frame_path),
        "mtime": mtime,
        "size": size,
        "palette_hash": hash(palette_colors),
        "created": time.time(),
        "last_access": time.time(),
        "file_size": len(png_bytes),
    }
    disk_cache.put(cache_key, png_bytes, metadata)

    return png_bytes


def _compute_palette_hash(sheet_palette: SheetPalette | None) -> int:
    """Compute a hash for the palette for cache key.

    Returns a 32-bit compatible hash to avoid OverflowError when passed
    through Qt signals (which use C++ int, typically 32-bit).
    """
    if sheet_palette is None:
        return 0
    colors_hash = hash(tuple(sheet_palette.colors))
    if sheet_palette.color_mappings:
        mappings_hash = hash(tuple(sorted(sheet_palette.color_mappings.items())))
        full_hash = hash((colors_hash, mappings_hash))
    else:
        full_hash = colors_hash
    # Constrain to 32-bit signed int range for Qt signal compatibility
    return full_hash & 0x7FFFFFFF


def create_quantized_thumbnail(
    frame_path: Path,
    sheet_palette: SheetPalette | None,
    size: int = DEFAULT_THUMBNAIL_SIZE,
) -> QPixmap | None:
    """Create a palette-quantized thumbnail for an AI frame.

    If a sheet palette is defined, quantizes the frame image to show
    WYSIWYG colors matching the injection result. Otherwise loads
    the raw PNG.

    Results are cached at two levels:
    1. LRU cache for PNG bytes (survives between calls)
    2. QPixmap cache to avoid redundant PNG decoding

    Call clear_all_thumbnail_caches() when palette changes to force regeneration.

    Args:
        frame_path: Path to the AI frame PNG file
        sheet_palette: SheetPalette for quantization, or None for raw colors
        size: Thumbnail size in pixels (square)

    Returns:
        Scaled QPixmap ready for list item icon, or None on failure
    """
    if not frame_path.exists():
        return None

    # Get file mtime for cache invalidation
    try:
        mtime = frame_path.stat().st_mtime
    except OSError:
        return None

    path_str = str(frame_path)
    palette_hash = _compute_palette_hash(sheet_palette)

    # Check QPixmap cache first (avoids PNG decode on repeated calls)
    cache_key = (path_str, mtime, palette_hash, size)
    cached_pixmap = _pixmap_cache.get(cache_key)
    if cached_pixmap is not None:
        return cached_pixmap

    # Use cached version based on whether we have a palette
    if sheet_palette is not None:
        # Convert palette to hashable format for cache key
        palette_colors = tuple(sheet_palette.colors)
        palette_mappings: tuple[tuple[tuple[int, int, int], int], ...] | None = None
        if sheet_palette.color_mappings:
            palette_mappings = tuple(sorted(sheet_palette.color_mappings.items()))

        # Extract background settings
        background_color = sheet_palette.background_color if hasattr(sheet_palette, "background_color") else None
        if not (isinstance(background_color, (tuple, list)) and len(background_color) == 3):
            background_color = None
        background_tolerance = (
            sheet_palette.background_tolerance if hasattr(sheet_palette, "background_tolerance") else 0
        )

        png_bytes = _cached_quantized_thumbnail_bytes(
            path_str, mtime, palette_colors, palette_mappings, background_color, background_tolerance, size
        )
    else:
        # No palette - use simpler cache
        png_bytes = _cached_thumbnail_bytes(path_str, mtime, 0, size)

    if png_bytes is None:
        return None

    # Convert PNG bytes to QPixmap
    pixmap = QPixmap()
    if not pixmap.loadFromData(png_bytes):
        return None

    # Store in QPixmap cache (with size limit)
    if len(_pixmap_cache) >= _PIXMAP_CACHE_MAXSIZE:
        # Simple eviction: remove oldest entries (first quarter)
        keys_to_remove = list(_pixmap_cache.keys())[: _PIXMAP_CACHE_MAXSIZE // 4]
        for key in keys_to_remove:
            _pixmap_cache.pop(key, None)

    _pixmap_cache[cache_key] = pixmap
    return pixmap


def quantize_pil_image(
    pil_image: Image.Image,
    sheet_palette: SheetPalette,
) -> Image.Image:
    """Quantize a PIL image to the sheet palette.

    Args:
        pil_image: Source image (any mode, will be converted to RGBA)
        sheet_palette: SheetPalette with colors and optional color_mappings

    Returns:
        Quantized RGBA image
    """
    # Ensure RGBA for quantization
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")

    # Use color_mappings if defined, otherwise simple quantization
    if sheet_palette.color_mappings:
        indexed = quantize_with_mappings(
            pil_image,
            sheet_palette.colors,
            sheet_palette.color_mappings,
            transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
        )
    else:
        indexed = quantize_to_palette(
            pil_image,
            sheet_palette.colors,
            transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
        )

    # Convert indexed back to RGBA for display (preserves palette colors)
    return indexed.convert("RGBA")


class AsyncThumbnailLoader(QObject):
    """Async thumbnail loader for AI frames.

    Loads thumbnails in a background thread to avoid UI freezing
    when loading folders with many images.
    """

    # Signal emitted when a thumbnail is ready
    # Args: frame_id (str), thumbnail (QPixmap)
    thumbnail_ready = Signal(str, QPixmap)

    # Signal emitted when all thumbnails are loaded
    finished = Signal()

    # Class-level set to prevent GC of orphaned threads that didn't stop in time
    # This prevents "QThread: Destroyed while thread is still running" crashes
    _orphaned_threads: set[QThread] = set()
    # Class-level set to keep threads alive between cleanup attempts
    _pending_cleanup_threads: set[QThread] = set()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker: _ThumbnailWorker | None = None
        self._thread: QThread | None = None
        self._destroyed = False
        self._current_request_id = 0  # Track request batches for stale filtering

        # Metadata for pending requests: request_id -> dict of frame_id -> (path_str, mtime, palette_hash, size)
        self._request_metadata: dict[int, dict[str, tuple[str, float, int, int]]] = {}

        # Ensure cleanup on destruction
        if parent is not None:
            parent.destroyed.connect(self._on_parent_destroyed)

    def __del__(self) -> None:  # pragma: no cover - best-effort Qt cleanup
        try:
            self.shutdown()
        except Exception:
            pass

    def _on_parent_destroyed(self) -> None:
        """Handle parent destruction - cancel any running work."""
        self._destroyed = True
        self.cancel()

    def load_thumbnails(
        self,
        requests: list[tuple[str, Path]],
        sheet_palette: SheetPalette | None,
        size: int = DEFAULT_THUMBNAIL_SIZE,
    ) -> None:
        """Start loading thumbnails asynchronously.

        Checks the QPixmap cache first and emits immediately for cache hits.
        Only queues cache misses for background generation.

        Args:
            requests: List of (frame_id, frame_path) tuples
            sheet_palette: SheetPalette for quantization, or None for raw colors
            size: Thumbnail size in pixels
        """
        # Increment request ID to invalidate any in-progress work
        self._current_request_id += 1

        # Cancel any existing work
        self.cancel()

        if not requests:
            self.finished.emit()
            return

        # In tests, run synchronously to avoid QThread cleanup races.
        if os.environ.get("SPRITEPAL_TESTING"):
            for frame_id, frame_path in requests:
                pixmap = create_quantized_thumbnail(frame_path, sheet_palette, size)
                if pixmap is not None:
                    self.thumbnail_ready.emit(frame_id, pixmap)
            self.finished.emit()
            return

        # Check cache first - emit immediately for hits, collect misses
        palette_hash = _compute_palette_hash(sheet_palette)
        cache_misses: list[tuple[str, Path]] = []
        request_metadata: dict[str, tuple[str, float, int, int]] = {}

        for frame_id, frame_path in requests:
            try:
                mtime = frame_path.stat().st_mtime
                cache_key = (str(frame_path), mtime, palette_hash, size)
                cached_pixmap = _pixmap_cache.get(cache_key)
                if cached_pixmap is not None:
                    # Emit immediately for cache hit
                    self.thumbnail_ready.emit(frame_id, cached_pixmap)
                else:
                    # Cache miss - store metadata for later cache population
                    request_metadata[frame_id] = cache_key
                    cache_misses.append((frame_id, frame_path))
            except OSError:
                cache_misses.append((frame_id, frame_path))

        # If all hits, we're done
        if not cache_misses:
            self.finished.emit()
            return

        # Store metadata for cache population when thumbnails complete
        self._request_metadata[self._current_request_id] = request_metadata

        # Create worker and thread for cache misses
        self._worker = _ThumbnailWorker(cache_misses, sheet_palette, size, self._current_request_id)
        self._thread = QThread()
        self._thread.setObjectName(f"AsyncThumbnailLoader-{self._current_request_id}")
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._thread.started.connect(self._worker.run)
        self._worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._worker.finished.connect(self._on_worker_finished)

        # Start loading (use WorkerManager for lifecycle tracking)
        WorkerManager.start_worker(self._thread)

    def _on_thumbnail_ready(self, frame_id: str, qimage: QImage, request_id: int) -> None:
        """Convert QImage to QPixmap in main thread and emit signal.

        Args:
            frame_id: The frame identifier
            qimage: The generated thumbnail image
            request_id: The request batch ID (unused - kept for signal signature)
        """
        # Note: We intentionally do NOT filter by request_id here.
        # Thumbnails are looked up by stable frame_id (filename), not row index,
        # so thumbnails from a "cancelled" batch are still valid for the current
        # table state. Filtering caused race conditions where rapid refresh()
        # calls would discard valid thumbnails (worker didn't stop in time).
        _ = request_id  # Unused but kept for signal signature compatibility
        if self._destroyed:
            logger.debug("AsyncThumbnailLoader._on_thumbnail_ready: destroyed, ignoring %s", frame_id)
            return
        if not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage)

            # Populate _pixmap_cache for future cache hits
            if request_id in self._request_metadata:
                metadata = self._request_metadata[request_id]
                if frame_id in metadata:
                    cache_key = metadata[frame_id]
                    # Apply same eviction logic as sync path
                    if len(_pixmap_cache) >= _PIXMAP_CACHE_MAXSIZE:
                        keys_to_remove = list(_pixmap_cache.keys())[: _PIXMAP_CACHE_MAXSIZE // 4]
                        for key in keys_to_remove:
                            _pixmap_cache.pop(key, None)
                    _pixmap_cache[cache_key] = pixmap

            logger.debug("AsyncThumbnailLoader emitting thumbnail_ready for %s", frame_id)
            self.thumbnail_ready.emit(frame_id, pixmap)
        else:
            logger.debug("AsyncThumbnailLoader: null qimage for %s", frame_id)

    def _on_worker_finished(self) -> None:
        """Clean up after worker finishes."""
        # Clean up metadata for completed request
        self._request_metadata.pop(self._current_request_id, None)
        self._cleanup_thread()
        if not self._destroyed:
            self.finished.emit()

    def cancel(self) -> None:
        """Cancel any in-progress loading."""
        # Clean up metadata for cancelled requests
        self._request_metadata.clear()
        if self._worker:
            try:
                self._worker.request_stop()
            except (RuntimeError, TypeError, AttributeError):
                # Worker already deleted or invalid
                self._worker = None
        self._cleanup_thread()

    def shutdown(self) -> None:
        """Shutdown loader and wait longer for background threads to stop."""
        self._destroyed = True
        self._request_metadata.clear()
        if self._worker:
            try:
                self._worker.request_stop()
            except (RuntimeError, TypeError, AttributeError):
                self._worker = None
        self._cleanup_thread(timeout_ms=8000, allow_orphan=True)

    def _cleanup_thread(self, timeout_ms: int = 2000, allow_orphan: bool = True) -> None:
        """Clean up thread resources without blocking UI.

        Signals are disconnected first to prevent stale results from propagating
        to the UI. The request_id mechanism provides additional protection against
        processing outdated results.

        Uses a short initial wait (100ms) followed by deferred cleanup to avoid
        blocking the UI thread for up to 5 seconds.
        """
        worker = self._worker
        thread = self._thread
        destroyed = self._destroyed

        # Block signals first to prevent emission during cleanup
        if worker is not None:
            try:
                from shiboken6 import isValid

                if isValid(worker):
                    worker.blockSignals(True)
                    worker.thumbnail_ready.disconnect()
                    worker.finished.disconnect()
            except (ImportError, RuntimeError, TypeError, AttributeError):
                pass  # Already disconnected or invalid

        if thread is not None:
            # Ensure worker is deleted once the thread finishes
            if worker is not None and not destroyed:
                try:
                    thread.finished.connect(worker.deleteLater)
                except (RuntimeError, TypeError):
                    pass

            stopped_cleanly = WorkerManager.cleanup_worker(thread, timeout=timeout_ms)
            if not stopped_cleanly:
                if allow_orphan:
                    # Keep reference in class-level set to prevent GC while running
                    AsyncThumbnailLoader._orphaned_threads.add(thread)
                    # Remove from WorkerManager registry to prevent cleanup_all() from
                    # processing this thread again with a shorter timeout, which could
                    # call deleteLater() before the OS thread has fully exited.
                    WorkerManager._worker_registry.discard(thread)
                    try:
                        thread.finished.connect(lambda t=thread: AsyncThumbnailLoader._orphaned_threads.discard(t))
                    except (RuntimeError, TypeError):
                        pass
                    self._thread = None
                    self._worker = None
                    return

        self._do_cleanup(thread, worker, destroyed)

    def _finish_cleanup(self, thread: QThread, worker: QObject | None, destroyed: bool) -> None:
        """Complete cleanup after delayed wait."""
        self._do_cleanup(thread, worker, destroyed)

    def _do_cleanup(self, thread: QThread | None, worker: QObject | None, destroyed: bool) -> None:
        """Perform actual cleanup of thread and worker objects."""
        if thread is not None and not destroyed:
            try:
                from shiboken6 import isValid

                if isValid(thread) and not thread.isRunning():
                    thread.deleteLater()
            except (ImportError, RuntimeError, TypeError):
                pass
        if worker is not None and not destroyed:
            try:
                from shiboken6 import isValid

                if isValid(worker):
                    worker.deleteLater()
            except (ImportError, RuntimeError, TypeError):
                pass
        self._thread = None
        self._worker = None


class _ThumbnailWorker(QObject):
    """Worker that generates thumbnails in a background thread."""

    thumbnail_ready = Signal(str, QImage, int)
    """Emitted when a thumbnail is successfully generated.

    Args:
        frame_id: The frame identifier
        qimage: Generated thumbnail as QImage (thread-safe)
        request_id: Request batch ID for filtering stale results
    """

    finished = Signal()
    """Emitted when worker completes all thumbnail processing."""

    def __init__(
        self,
        requests: list[tuple[str, Path]],
        sheet_palette: SheetPalette | None,
        size: int,
        request_id: int,
    ) -> None:
        super().__init__()
        self._requests = requests
        self._sheet_palette = sheet_palette
        self._size = size
        self._request_id = request_id
        self._state_mutex = QMutex()
        self._stop_requested = False

    def request_stop(self) -> None:
        """Request the worker to stop. Thread-safe."""
        with QMutexLocker(self._state_mutex):
            self._stop_requested = True

    def _is_stop_requested(self) -> bool:
        """Check if stop has been requested. Thread-safe."""
        with QMutexLocker(self._state_mutex):
            return self._stop_requested

    def run(self) -> None:
        """Generate thumbnails for all requests."""
        try:
            for frame_id, frame_path in self._requests:
                if self._is_stop_requested():
                    logger.debug("Thumbnail worker stopped early at frame_id=%s", frame_id)
                    break

                qimage = self._generate_thumbnail(frame_path)
                if qimage is not None and not qimage.isNull():
                    logger.debug(
                        "Worker emitting thumbnail_ready for %s (%dx%d)", frame_id, qimage.width(), qimage.height()
                    )
                    self.thumbnail_ready.emit(frame_id, qimage, self._request_id)
                else:
                    logger.debug("Worker failed to generate thumbnail for %s", frame_id)
        except Exception as e:
            logger.warning("Thumbnail worker error: %s", e, exc_info=True)
        finally:
            self.finished.emit()

    def _generate_thumbnail(self, frame_path: Path) -> QImage | None:
        """Generate a single thumbnail.

        Returns QImage (thread-safe) instead of QPixmap.
        Uses disk cache for persistence across sessions.
        """
        if not frame_path.exists():
            return None

        # Get file mtime for cache key
        try:
            mtime = frame_path.stat().st_mtime
        except OSError:
            return None

        # Compute cache key parameters
        if self._sheet_palette is not None:
            palette_colors = tuple(self._sheet_palette.colors)
            palette_mappings = dict(self._sheet_palette.color_mappings) if self._sheet_palette.color_mappings else None
            background_color = self._sheet_palette.background_color
            if not (isinstance(background_color, (tuple, list)) and len(background_color) == 3):
                background_color = None
            background_tolerance = self._sheet_palette.background_tolerance
        else:
            palette_colors = ()
            palette_mappings = None
            background_color = None
            background_tolerance = 0

        # Check disk cache first
        disk_cache = get_disk_cache()
        cache_key = _compute_cache_key(
            frame_path,
            mtime,
            palette_colors,
            palette_mappings,
            background_color,
            background_tolerance,
            self._size,
        )
        cached_bytes = disk_cache.get(cache_key)
        if cached_bytes:
            # Convert PNG bytes to QImage
            qimage = QImage()
            if qimage.loadFromData(cached_bytes):
                return qimage
            # If loading failed, fall through to regenerate

        # Cache miss - generate thumbnail
        try:
            pil_image = Image.open(frame_path)
        except Exception:
            logger.debug("Failed to load image: %s", frame_path)
            return None

        # Apply background removal if configured in sheet palette
        if self._sheet_palette is not None and self._sheet_palette.background_color is not None:
            from core.services.content_bounds_analyzer import remove_background

            # Convert to RGBA first for background removal
            if pil_image.mode != "RGBA":
                pil_image = pil_image.convert("RGBA")
            pil_image = remove_background(
                pil_image,
                self._sheet_palette.background_color,
                self._sheet_palette.background_tolerance,
            )

        # Scale to thumbnail size FIRST, then quantize.
        # Quantization with LAB color space is O(pixels * palette * mappings),
        # so scaling a 260x370 image down to 64x64 BEFORE quantizing is ~24x faster.
        pil_image.thumbnail((self._size, self._size), Image.Resampling.LANCZOS)

        # Apply palette quantization if palette is defined
        if self._sheet_palette is not None:
            try:
                pil_image = quantize_pil_image(pil_image, self._sheet_palette)
            except Exception:
                logger.debug("Failed to quantize image: %s", frame_path)
                # Fall through to use original image

        # Convert to PNG bytes for disk cache
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        png_bytes = buffer.getvalue()

        # Save to disk cache
        metadata = {
            "path": str(frame_path),
            "mtime": mtime,
            "size": self._size,
            "palette_hash": hash(palette_colors),
        }
        disk_cache.put(cache_key, png_bytes, metadata)

        # Convert to QImage (thread-safe) - already at thumbnail size
        try:
            qimage = pil_to_qimage(pil_image, thread_safe=True)
            if qimage.isNull():
                return None
            return qimage
        except Exception:
            logger.debug("Failed to convert/scale image: %s", frame_path)
            return None
