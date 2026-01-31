"""Async icon quantization service for game frame icons in MappingPanel.

Offloads palette quantization to a background thread to keep UI responsive
during palette changes when many game frame icons need to be re-quantized.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

from core.services.image_utils import pil_to_qimage
from ui.frame_mapping.services.thumbnail_service import quantize_pil_image
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette

logger = get_logger(__name__)


@dataclass
class QuantizeRequest:
    """Request to quantize a game frame icon."""

    request_id: int
    game_frame_id: str
    image_bytes: bytes  # Raw BGRA bytes from QImage
    width: int
    height: int
    sheet_palette: SheetPalette
    palette_hash: int
    target_size: int


class _QuantizeWorker(QObject):
    """Worker that quantizes icons in a background thread.

    Emits QImage (thread-safe) instead of QPixmap. The main thread
    must convert to QPixmap.
    """

    # Signal: (request_id, game_frame_id, qimage, palette_hash)
    result_ready = Signal(int, str, QImage, int)
    error = Signal(int, str, str)  # (request_id, game_frame_id, error_message)

    def __init__(self) -> None:
        super().__init__()
        self._state_mutex = QMutex()
        self._target_request_id = 0

    def set_target_request_id(self, req_id: int) -> None:
        """Update the target request ID to cancel stale requests.

        Thread-safe. Called from main thread.
        """
        with QMutexLocker(self._state_mutex):
            self._target_request_id = req_id

    def _should_cancel(self, request_id: int) -> bool:
        """Check if this request should be cancelled.

        Thread-safe. Called from worker thread.
        Returns True if this request is stale (a newer request has arrived).
        """
        with QMutexLocker(self._state_mutex):
            return request_id != self._target_request_id

    @Slot(QuantizeRequest)
    def process_request(self, request: QuantizeRequest) -> None:
        """Process quantization request. Called from worker thread via signal."""
        request_id = request.request_id

        # Fast rejection if this request is already stale
        if self._should_cancel(request_id):
            return

        try:
            # Convert raw bytes to PIL Image
            pil_image = Image.frombytes(
                "RGBA",
                (request.width, request.height),
                request.image_bytes,
                "raw",
                "BGRA",
            )

            # Check cancellation before heavy work
            if self._should_cancel(request_id):
                return

            # Quantize to palette
            quantized_pil = quantize_pil_image(pil_image, request.sheet_palette)

            # Check cancellation after heavy work
            if self._should_cancel(request_id):
                return

            # Scale to target size (maintaining aspect ratio)
            quantized_pil.thumbnail(
                (request.target_size, request.target_size),
                Image.Resampling.LANCZOS,
            )

            # Convert to QImage (thread-safe)
            qimage = pil_to_qimage(quantized_pil, thread_safe=True)

            if qimage.isNull():
                if not self._should_cancel(request_id):
                    self.error.emit(request_id, request.game_frame_id, "Failed to convert to QImage")
            elif not self._should_cancel(request_id):
                self.result_ready.emit(request_id, request.game_frame_id, qimage, request.palette_hash)

        except Exception as e:
            logger.exception("Icon quantization error for %s", request.game_frame_id)
            if not self._should_cancel(request_id):
                self.error.emit(request_id, request.game_frame_id, str(e))


class AsyncIconQuantizer(QObject):
    """Main-thread coordinator for async icon quantization.

    Manages a background worker thread for quantizing game frame icons.
    Provides immediate return with placeholder while quantization proceeds
    in background.

    Signals:
        icon_ready: Emitted when quantized icon is ready (game_frame_id, pixmap, palette_hash)
    """

    # Signal: (game_frame_id, QPixmap, palette_hash)
    icon_ready = Signal(str, QPixmap, int)

    # Internal signal to trigger worker
    _start_worker = Signal(QuantizeRequest)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._request_id = 0
        self._thread: QThread | None = None
        self._worker: _QuantizeWorker | None = None
        # Pending requests: game_frame_id -> request_id (for deduplication)
        self._pending_requests: dict[str, int] = {}

        self._setup_worker()

        # Clean up thread when parent is destroyed
        if parent is not None:
            parent.destroyed.connect(self._on_parent_destroyed)

    def _setup_worker(self) -> None:
        """Set up the background worker thread."""
        self._thread = QThread()
        self._worker = _QuantizeWorker()
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._start_worker.connect(self._worker.process_request)
        self._worker.result_ready.connect(self._on_result_ready)
        self._worker.error.connect(self._on_error)

        self._thread.start()

    def _on_parent_destroyed(self) -> None:
        """Clean up when parent widget is destroyed."""
        self.shutdown()

    def quantize_icon(
        self,
        game_frame_id: str,
        raw_pixmap: QPixmap,
        sheet_palette: SheetPalette,
        palette_hash: int,
        target_size: int,
    ) -> None:
        """Queue an icon for async quantization.

        The QPixmap is converted to raw bytes on the main thread (safe),
        then the heavy quantization work happens on the background thread.

        Args:
            game_frame_id: The game frame ID for the icon
            raw_pixmap: The raw preview pixmap to quantize
            sheet_palette: Palette to quantize to
            palette_hash: Hash of the palette (for cache invalidation)
            target_size: Target size for the scaled icon
        """
        if self._worker is None:
            return

        # Convert QPixmap to QImage on main thread (QPixmap is not thread-safe)
        qimage = raw_pixmap.toImage()
        if qimage.isNull():
            return

        # Ensure ARGB32 format for consistent byte layout
        qimage = qimage.convertToFormat(QImage.Format.Format_ARGB32)

        # Extract raw bytes (thread-safe data)
        width = qimage.width()
        height = qimage.height()
        image_bytes = bytes(qimage.bits())

        # Update request tracking
        self._request_id += 1
        request_id = self._request_id

        self._worker.set_target_request_id(request_id)
        self._pending_requests[game_frame_id] = request_id

        request = QuantizeRequest(
            request_id=request_id,
            game_frame_id=game_frame_id,
            image_bytes=image_bytes,
            width=width,
            height=height,
            sheet_palette=sheet_palette,
            palette_hash=palette_hash,
            target_size=target_size,
        )

        # Trigger processing in worker thread via signal
        self._start_worker.emit(request)

    @Slot(int, str, QImage, int)
    def _on_result_ready(self, request_id: int, game_frame_id: str, qimage: QImage, palette_hash: int) -> None:
        """Handle quantization result from worker."""
        # Verify this result is still relevant
        if game_frame_id in self._pending_requests:
            if self._pending_requests[game_frame_id] == request_id:
                del self._pending_requests[game_frame_id]
            else:
                # Stale result, ignore
                return

        # Convert QImage to QPixmap on main thread
        pixmap = QPixmap.fromImage(qimage)
        if not pixmap.isNull():
            self.icon_ready.emit(game_frame_id, pixmap, palette_hash)

    @Slot(int, str, str)
    def _on_error(self, request_id: int, game_frame_id: str, error_msg: str) -> None:
        """Handle quantization error from worker."""
        logger.debug("Icon quantization failed for %s: %s", game_frame_id, error_msg)
        # Clean up pending request
        if game_frame_id in self._pending_requests:
            if self._pending_requests[game_frame_id] == request_id:
                del self._pending_requests[game_frame_id]

    def cancel_all(self) -> None:
        """Cancel all pending quantization requests."""
        self._request_id += 1
        if self._worker:
            self._worker.set_target_request_id(self._request_id)
        self._pending_requests.clear()

    def shutdown(self) -> None:
        """Shut down the background thread."""
        # Block signals first to prevent emission during cleanup
        if self._worker is not None:
            self._worker.blockSignals(True)
            try:
                self._start_worker.disconnect()
                self._worker.result_ready.disconnect()
                self._worker.error.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected

        # Schedule worker deletion when thread stops
        if self._worker is not None and self._thread is not None:
            self._thread.finished.connect(self._worker.deleteLater)

        if self._thread is not None:
            self._thread.quit()
            if not self._thread.wait(3000):
                logger.warning("Icon quantizer thread did not stop in time")
            self._thread.deleteLater()
            self._thread = None

        self._worker = None
        self._pending_requests.clear()
