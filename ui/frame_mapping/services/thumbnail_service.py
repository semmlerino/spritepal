"""Thumbnail generation service for frame mapping UI.

This service provides consistent thumbnail generation for AI frames and game frames,
ensuring WYSIWYG behavior by using the same quantization logic as injection.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QObject, Qt, QThread, Signal
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


def create_quantized_thumbnail(
    frame_path: Path,
    sheet_palette: SheetPalette | None,
    size: int = DEFAULT_THUMBNAIL_SIZE,
) -> QPixmap | None:
    """Create a palette-quantized thumbnail for an AI frame.

    If a sheet palette is defined, quantizes the frame image to show
    WYSIWYG colors matching the injection result. Otherwise loads
    the raw PNG.

    Args:
        frame_path: Path to the AI frame PNG file
        sheet_palette: SheetPalette for quantization, or None for raw colors
        size: Thumbnail size in pixels (square)

    Returns:
        Scaled QPixmap ready for list item icon, or None on failure
    """
    if not frame_path.exists():
        return None

    # Load original image with PIL
    try:
        pil_image = Image.open(frame_path)
    except Exception:
        logger.warning("Failed to load image: %s", frame_path)
        return None

    # Apply palette quantization if palette is defined
    if sheet_palette is not None:
        try:
            pil_image = quantize_pil_image(pil_image, sheet_palette)
        except Exception:
            logger.warning("Failed to quantize image: %s", frame_path, exc_info=True)
            # Fall through to use original image

    # Convert to QPixmap
    pixmap = pil_to_qpixmap(pil_image)
    if pixmap is None or pixmap.isNull():
        return None

    # Scale to thumbnail size using fast transformation (good enough for small thumbnails)
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )


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
        # Disconnect signals first to prevent stale results from reaching UI
        if self._worker is not None:
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
        self._stop_requested = False

    def request_stop(self) -> None:
        """Request the worker to stop."""
        self._stop_requested = True

    def run(self) -> None:
        """Generate thumbnails for all requests."""
        try:
            for frame_id, frame_path in self._requests:
                if self._stop_requested:
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
