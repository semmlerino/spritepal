"""Async preview generation service for frame mapping workbench.

This service offloads heavy compositor operations to a background thread,
preventing UI blocking during preview generation. Uses the same pattern as
AsyncThumbnailLoader for thread-safe QImage handling.

Key design:
- Worker runs compositor.composite_frame() in background thread
- Request ID pattern cancels stale previews when new request arrives
- QImage created in worker (thread-safe), QPixmap conversion on main thread
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
from PIL import Image
from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage

from core.services.image_utils import pil_to_qimage
from core.services.sprite_compositor import SpriteCompositor, TransformParams
from ui.common import WorkerManager, is_valid_qt
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette
    from core.mesen_integration.click_extractor import CaptureResult

logger = get_logger(__name__)


@dataclass
class PreviewRequest:
    """Encapsulates all data needed for a preview generation request."""

    request_id: int
    ai_image: Image.Image
    capture_result: CaptureResult
    transform: TransformParams
    uncovered_policy: Literal["transparent", "original"]
    sheet_palette: SheetPalette | None
    ai_index_map: np.ndarray | None
    display_scale: int


class _PreviewWorker(QObject):
    """Worker that generates preview images in a background thread.

    Uses persistent thread model with signal-triggered processing.
    Emits QImage (thread-safe) instead of QPixmap. The main thread
    must convert to QPixmap.
    """

    # Signal: (request_id, qimage, preview_width, preview_height)
    preview_ready = Signal(int, QImage, int, int)
    error = Signal(int, str)  # (request_id, error_message)

    def __init__(self) -> None:
        super().__init__()
        self._state_mutex = QMutex()
        self._target_request_id = 0
        self._stop_requested = False

    def set_target_request_id(self, req_id: int) -> None:
        """Update the target request ID and request stop of current work.

        Thread-safe. Called from main thread.
        """
        with QMutexLocker(self._state_mutex):
            self._target_request_id = req_id
            self._stop_requested = True

    def _should_cancel(self, request_id: int) -> bool:
        """Check if this request should be cancelled.

        Thread-safe. Called from worker thread.
        Returns True if this request is stale (a newer request has arrived).
        """
        with QMutexLocker(self._state_mutex):
            return request_id != self._target_request_id

    def _clear_stop_flag(self) -> None:
        """Clear stop flag at start of valid request processing.

        Thread-safe. Called from worker thread.
        """
        with QMutexLocker(self._state_mutex):
            self._stop_requested = False

    @Slot(PreviewRequest)
    def process_request(self, request: PreviewRequest) -> None:
        """Process preview request. Called from worker thread via signal."""
        request_id = request.request_id

        # Fast rejection if this request is already stale
        if self._should_cancel(request_id):
            return

        # Clear stop flag for this new valid request
        self._clear_stop_flag()

        try:
            # Create compositor and generate preview
            compositor = SpriteCompositor(uncovered_policy=request.uncovered_policy)
            result = compositor.composite_frame(
                ai_image=request.ai_image,
                capture_result=request.capture_result,
                transform=request.transform,
                quantize=True,
                sheet_palette=request.sheet_palette,
                ai_index_map=request.ai_index_map,
            )

            # Check cancellation after heavy work
            if self._should_cancel(request_id):
                return

            preview_img = result.composited_image

            # Convert PIL image to QImage (thread-safe)
            qimage = pil_to_qimage(preview_img, thread_safe=True)

            if qimage.isNull():
                if not self._should_cancel(request_id):
                    self.error.emit(request_id, "Failed to convert preview to QImage")
            else:
                # Scale for display
                scaled_qimage = qimage.scaled(
                    preview_img.width * request.display_scale,
                    preview_img.height * request.display_scale,
                )
                if not self._should_cancel(request_id):
                    self.preview_ready.emit(
                        request_id,
                        scaled_qimage,
                        preview_img.width,
                        preview_img.height,
                    )

        except Exception as e:
            logger.exception("Preview worker error")
            if not self._should_cancel(request_id):
                self.error.emit(request_id, str(e))


class AsyncPreviewService(QObject):
    """Async preview service for workbench canvas.

    Manages a persistent background worker thread for generating preview images.
    Uses incrementing request IDs to cancel stale previews when new
    requests arrive.

    Signals:
        preview_ready: Emitted when preview is ready.
            Args: (qimage: QImage, width: int, height: int)
        preview_failed: Emitted when preview generation fails.
            Args: (error_message: str)
    """

    preview_ready = Signal(QImage, int, int)  # qimage, width, height
    preview_failed = Signal(str)  # error_message

    # Internal signal to trigger worker
    _start_worker = Signal(PreviewRequest)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._destroyed = False
        self._request_id_mutex = QMutex()  # Protects _current_request_id
        self._current_request_id = 0

        # Image buffer cache to avoid repeated copies during rapid drags
        # Only copy when the source image identity changes
        self._cached_ai_image: Image.Image | None = None
        self._cached_ai_index_map: np.ndarray | None = None
        self._cached_image_id: int | None = None  # id() of source ai_image

        # Create persistent thread and worker
        self._thread = QThread()
        self._worker = _PreviewWorker()
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._start_worker.connect(self._worker.process_request)
        self._worker.preview_ready.connect(self._on_preview_ready)
        self._worker.error.connect(self._on_error)

        # Start the thread via WorkerManager for proper lifecycle tracking
        WorkerManager.start_worker(self._thread)

        if parent is not None:
            parent.destroyed.connect(self._on_parent_destroyed)

    def _on_parent_destroyed(self) -> None:
        """Handle parent destruction."""
        self._destroyed = True
        self.shutdown()

    def request_preview(
        self,
        ai_image: Image.Image,
        capture_result: CaptureResult,
        transform: TransformParams,
        uncovered_policy: Literal["transparent", "original"],
        sheet_palette: SheetPalette | None,
        ai_index_map: np.ndarray | None,
        display_scale: int,
    ) -> None:
        """Request a preview generation.

        Cancels any in-progress preview and starts a new one.
        The result will be emitted via preview_ready signal.

        Args:
            ai_image: The AI-generated frame (PIL Image).
            capture_result: Parsed Mesen capture with OAM entries.
            transform: Alignment parameters.
            uncovered_policy: How to handle uncovered areas.
            sheet_palette: Palette for quantization.
            ai_index_map: Pre-indexed map for the AI frame.
            display_scale: Scale factor for display.
        """
        if self._destroyed:
            return

        # Increment request ID to invalidate any in-progress work (mutex-protected)
        with QMutexLocker(self._request_id_mutex):
            self._current_request_id += 1
            request_id = self._current_request_id

        # Use cached copies if image identity unchanged (avoids repeated copies during drag)
        image_id = id(ai_image)
        if image_id != self._cached_image_id:
            self._cached_ai_image = ai_image.copy()
            self._cached_ai_index_map = ai_index_map.copy() if ai_index_map is not None else None
            self._cached_image_id = image_id

        # Create request with cached copies
        request = PreviewRequest(
            request_id=request_id,
            ai_image=self._cached_ai_image,  # type: ignore[arg-type]  # cached copy
            capture_result=capture_result,
            transform=transform,
            uncovered_policy=uncovered_policy,
            sheet_palette=sheet_palette,
            ai_index_map=self._cached_ai_index_map,
            display_scale=display_scale,
        )

        # Update worker target ID to invalidate in-progress work
        if self._worker is not None:
            self._worker.set_target_request_id(request_id)
            # Trigger processing in worker thread
            self._start_worker.emit(request)

    def cancel(self) -> None:
        """Cancel any in-progress preview generation."""
        # Increment request ID to invalidate in-progress work (mutex-protected)
        with QMutexLocker(self._request_id_mutex):
            self._current_request_id += 1
            current_id = self._current_request_id
        if self._worker is not None:
            self._worker.set_target_request_id(current_id)

    def clear_image_cache(self) -> None:
        """Clear cached image buffers.

        Call this when the AI frame changes (set_ai_frame) to ensure
        the next request uses fresh copies.
        """
        self._cached_ai_image = None
        self._cached_ai_index_map = None
        self._cached_image_id = None

    def _on_preview_ready(self, request_id: int, qimage: QImage, width: int, height: int) -> None:
        """Handle preview ready from worker."""
        if self._destroyed:
            return
        # Only emit if this is the current request (not stale) - mutex-protected read
        with QMutexLocker(self._request_id_mutex):
            is_current = request_id == self._current_request_id
        if is_current:
            self.preview_ready.emit(qimage, width, height)

    def _on_error(self, request_id: int, error_message: str) -> None:
        """Handle error from worker."""
        if self._destroyed:
            return
        # Only emit if this is the current request (not stale) - mutex-protected read
        with QMutexLocker(self._request_id_mutex):
            is_current = request_id == self._current_request_id
        if is_current:
            self.preview_failed.emit(error_message)

    def shutdown(self) -> None:
        """Shutdown the service and clean up resources."""
        self._destroyed = True
        self.clear_image_cache()

        try:
            # Block signals first to prevent emission during cleanup
            if is_valid_qt(self._worker):
                self._worker.blockSignals(True)
                try:
                    self._worker.preview_ready.disconnect()
                    self._worker.error.disconnect()
                except (RuntimeError, TypeError):
                    pass  # Already disconnected or never connected

            # Clean up thread via WorkerManager
            if is_valid_qt(self._thread):
                WorkerManager.cleanup_worker(self._thread, timeout=3000)
                self._thread = None

            if is_valid_qt(self._worker):
                self._worker.deleteLater()
                self._worker = None
        except RuntimeError:
            # Objects already deleted by Qt parent-child mechanism
            pass
