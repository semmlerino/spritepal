"""Thumbnail generation service for frame mapping UI.

This service provides consistent thumbnail generation for AI frames and game frames,
ensuring WYSIWYG behavior by using the same quantization logic as injection.
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QMutex, QMutexLocker, QObject, Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap

from core.palette_utils import (
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    quantize_to_palette,
    quantize_with_mappings,
)
from core.services.image_utils import pil_to_qimage, pil_to_qpixmap
from ui.common import WorkerManager
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette

logger = get_logger(__name__)

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


def clear_thumbnail_cache() -> None:
    """Clear the thumbnail cache.

    Call this when the palette changes to ensure thumbnails are regenerated
    with the new palette colors.
    """
    _cached_thumbnail_bytes.cache_clear()
    _cached_quantized_thumbnail_bytes.cache_clear()
    _pixmap_cache.clear()
    logger.debug("Thumbnail cache cleared")


@lru_cache(maxsize=_THUMBNAIL_CACHE_MAXSIZE)
def _cached_quantized_thumbnail_bytes(
    path_str: str,
    mtime: float,
    palette_colors: tuple[tuple[int, int, int], ...],
    palette_mappings: tuple[tuple[tuple[int, int, int], int], ...] | None,
    size: int,
) -> bytes | None:
    """Generate and cache a quantized thumbnail as PNG bytes.

    Args:
        path_str: String path to the image file
        mtime: File modification time (for cache invalidation)
        palette_colors: Tuple of (R, G, B) color tuples
        palette_mappings: Tuple of ((R, G, B), index) mappings, or None
        size: Thumbnail size in pixels

    Returns:
        PNG bytes of the quantized thumbnail, or None on failure
    """
    frame_path = Path(path_str)
    if not frame_path.exists():
        return None

    try:
        pil_image = Image.open(frame_path)
    except Exception:
        logger.warning("Failed to load image: %s", frame_path)
        return None

    # Ensure RGBA for quantization
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")

    # Apply quantization
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

    # Scale the image
    pil_image.thumbnail((size, size), Image.Resampling.LANCZOS)

    # Convert to PNG bytes
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return buffer.getvalue()


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

    Call clear_thumbnail_cache() when palette changes to force regeneration.

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

        png_bytes = _cached_quantized_thumbnail_bytes(path_str, mtime, palette_colors, palette_mappings, size)
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


def quantize_qpixmap(
    pixmap: QPixmap,
    sheet_palette: SheetPalette | None,
) -> QPixmap:
    """Quantize a QPixmap to match the sheet palette.

    When a sheet palette is set, the pixmap will be quantized to show
    how the sprite will look when injected. This ensures WYSIWYG behavior
    between preview thumbnails and actual injection results.

    Args:
        pixmap: The raw QPixmap to quantize
        sheet_palette: SheetPalette for quantization, or None to return original

    Returns:
        Quantized QPixmap if sheet palette is set, otherwise the original
    """
    if sheet_palette is None:
        return pixmap

    try:
        # Convert QPixmap to PIL Image via QImage
        qimage = pixmap.toImage()
        if qimage.isNull():
            return pixmap

        width = qimage.width()
        height = qimage.height()

        # Ensure ARGB32 format for consistent byte layout
        qimage = qimage.convertToFormat(qimage.Format.Format_ARGB32)

        # Get raw bytes and convert to PIL
        img_data = bytes(qimage.bits())
        pil_image = Image.frombytes("RGBA", (width, height), img_data, "raw", "BGRA")

        # Quantize to sheet palette
        pil_image = quantize_pil_image(pil_image, sheet_palette)

        # Convert back to QPixmap
        result = pil_to_qpixmap(pil_image)
        if result is None or result.isNull():
            return pixmap
        return result

    except Exception:
        logger.debug("QPixmap quantization failed, using original")
        return pixmap


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

        # Ensure cleanup on destruction
        if parent is not None:
            parent.destroyed.connect(self._on_parent_destroyed)

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

        # Check cache first - emit immediately for hits, collect misses
        palette_hash = _compute_palette_hash(sheet_palette)
        cache_misses: list[tuple[str, Path]] = []

        for frame_id, frame_path in requests:
            try:
                mtime = frame_path.stat().st_mtime
                cache_key = (str(frame_path), mtime, palette_hash, size)
                cached_pixmap = _pixmap_cache.get(cache_key)
                if cached_pixmap is not None:
                    # Emit immediately for cache hit
                    self.thumbnail_ready.emit(frame_id, cached_pixmap)
                else:
                    cache_misses.append((frame_id, frame_path))
            except OSError:
                cache_misses.append((frame_id, frame_path))

        # If all hits, we're done
        if not cache_misses:
            self.finished.emit()
            return

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
            logger.debug("AsyncThumbnailLoader emitting thumbnail_ready for %s", frame_id)
            self.thumbnail_ready.emit(frame_id, pixmap)
        else:
            logger.debug("AsyncThumbnailLoader: null qimage for %s", frame_id)

    def _on_worker_finished(self) -> None:
        """Clean up after worker finishes."""
        self._cleanup_thread()
        if not self._destroyed:
            self.finished.emit()

    def cancel(self) -> None:
        """Cancel any in-progress loading."""
        if self._worker:
            try:
                self._worker.request_stop()
            except (RuntimeError, TypeError, AttributeError):
                # Worker already deleted or invalid
                self._worker = None
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
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

            stopped_cleanly = WorkerManager.cleanup_worker(thread, timeout=2000)
            if not stopped_cleanly:
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
        """
        if not frame_path.exists():
            return None

        try:
            pil_image = Image.open(frame_path)
        except Exception:
            logger.debug("Failed to load image: %s", frame_path)
            return None

        # Apply palette quantization if palette is defined
        if self._sheet_palette is not None:
            try:
                pil_image = quantize_pil_image(pil_image, self._sheet_palette)
            except Exception:
                logger.debug("Failed to quantize image: %s", frame_path)
                # Fall through to use original image

        # Convert to QImage (thread-safe)
        try:
            qimage = pil_to_qimage(pil_image, thread_safe=True)
            if qimage.isNull():
                return None

            # Scale to thumbnail size using fast transformation (good enough for small thumbnails)
            return qimage.scaled(
                self._size,
                self._size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        except Exception:
            logger.debug("Failed to convert/scale image: %s", frame_path)
            return None
