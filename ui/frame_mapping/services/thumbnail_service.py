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
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette

logger = get_logger(__name__)

# Default thumbnail size for list items and table cells
DEFAULT_THUMBNAIL_SIZE = 64

# Maximum cached thumbnails (balances memory vs cache hits)
_THUMBNAIL_CACHE_MAXSIZE = 500


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


def create_quantized_thumbnail(
    frame_path: Path,
    sheet_palette: SheetPalette | None,
    size: int = DEFAULT_THUMBNAIL_SIZE,
) -> QPixmap | None:
    """Create a palette-quantized thumbnail for an AI frame.

    If a sheet palette is defined, quantizes the frame image to show
    WYSIWYG colors matching the injection result. Otherwise loads
    the raw PNG.

    Results are cached using LRU cache keyed by (path, mtime, palette, size).
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

        # Create worker and thread
        self._worker = _ThumbnailWorker(requests, sheet_palette, size)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._thread.started.connect(self._worker.run)
        self._worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._worker.finished.connect(self._on_worker_finished)

        # Start loading
        self._thread.start()

    def _on_thumbnail_ready(self, frame_id: str, qimage: QImage) -> None:
        """Convert QImage to QPixmap in main thread and emit signal."""
        if self._destroyed:
            return
        if not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage)
            self.thumbnail_ready.emit(frame_id, pixmap)

    def _on_worker_finished(self) -> None:
        """Clean up after worker finishes."""
        self._cleanup_thread()
        if not self._destroyed:
            self.finished.emit()

    def cancel(self) -> None:
        """Cancel any in-progress loading."""
        if self._worker:
            self._worker.request_stop()
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        """Clean up thread resources.

        Signals are disconnected first to prevent stale results from propagating
        to the UI. The request_id mechanism provides additional protection against
        processing outdated results.
        """
        # Block signals first to prevent emission during cleanup
        if self._worker is not None:
            self._worker.blockSignals(True)
            try:
                self._worker.thumbnail_ready.disconnect()
                self._worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected or never connected

        if self._thread is not None:
            if self._thread.isRunning():
                self._thread.quit()
                # Wait longer and log if it doesn't stop
                if not self._thread.wait(5000):
                    logger.warning("Thumbnail worker thread did not stop within timeout")
            # Only deleteLater if not in destruction context
            if not self._destroyed:
                self._thread.deleteLater()
            self._thread = None
        if self._worker is not None:
            if not self._destroyed:
                self._worker.deleteLater()
            self._worker = None


class _ThumbnailWorker(QObject):
    """Worker that generates thumbnails in a background thread."""

    thumbnail_ready = Signal(str, QImage)
    finished = Signal()

    def __init__(
        self,
        requests: list[tuple[str, Path]],
        sheet_palette: SheetPalette | None,
        size: int,
    ) -> None:
        super().__init__()
        self._requests = requests
        self._sheet_palette = sheet_palette
        self._size = size
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
                    break

                qimage = self._generate_thumbnail(frame_path)
                if qimage is not None and not qimage.isNull():
                    self.thumbnail_ready.emit(frame_id, qimage)
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
