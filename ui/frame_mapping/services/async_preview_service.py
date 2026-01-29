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
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QImage

from core.services.image_utils import pil_to_qimage
from core.services.sprite_compositor import SpriteCompositor, TransformParams
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

    Emits QImage (thread-safe) instead of QPixmap. The main thread
    must convert to QPixmap.
    """

    # Signal: (request_id, qimage, preview_width, preview_height)
    preview_ready = Signal(int, QImage, int, int)
    error = Signal(int, str)  # (request_id, error_message)
    finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._stop_requested = False
        self._current_request: PreviewRequest | None = None

    def request_stop(self) -> None:
        """Request the worker to stop."""
        self._stop_requested = True

    def set_request(self, request: PreviewRequest) -> None:
        """Set the request to process. Called from main thread before run()."""
        self._current_request = request

    def run(self) -> None:
        """Generate preview for the current request."""
        if self._current_request is None:
            self.finished.emit()
            return

        request = self._current_request
        request_id = request.request_id

        try:
            if self._stop_requested:
                self.finished.emit()
                return

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
            if self._stop_requested:
                self.finished.emit()
                return

            preview_img = result.composited_image

            # Convert PIL image to QImage (thread-safe)
            qimage = pil_to_qimage(preview_img, thread_safe=True)

            if qimage.isNull():
                self.error.emit(request_id, "Failed to convert preview to QImage")
            else:
                # Scale for display
                scaled_qimage = qimage.scaled(
                    preview_img.width * request.display_scale,
                    preview_img.height * request.display_scale,
                )
                self.preview_ready.emit(
                    request_id,
                    scaled_qimage,
                    preview_img.width,
                    preview_img.height,
                )

        except Exception as e:
            logger.exception("Preview worker error")
            self.error.emit(request_id, str(e))
        finally:
            self.finished.emit()


class AsyncPreviewService(QObject):
    """Async preview service for workbench canvas.

    Manages a background worker thread for generating preview images.
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

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker: _PreviewWorker | None = None
        self._thread: QThread | None = None
        self._destroyed = False
        self._current_request_id = 0

        # Track pending request to avoid duplicate processing
        self._pending_request: PreviewRequest | None = None

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

        # Increment request ID to invalidate any in-progress work
        self._current_request_id += 1
        request_id = self._current_request_id

        # Cancel existing work
        self._cancel_current()

        # Create request
        request = PreviewRequest(
            request_id=request_id,
            ai_image=ai_image.copy(),  # Copy to avoid threading issues
            capture_result=capture_result,
            transform=transform,
            uncovered_policy=uncovered_policy,
            sheet_palette=sheet_palette,
            ai_index_map=ai_index_map.copy() if ai_index_map is not None else None,
            display_scale=display_scale,
        )

        # Start worker
        self._worker = _PreviewWorker()
        self._worker.set_request(request)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._thread.started.connect(self._worker.run)
        self._worker.preview_ready.connect(self._on_preview_ready)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)

        # Start
        self._thread.start()

    def _on_preview_ready(self, request_id: int, qimage: QImage, width: int, height: int) -> None:
        """Handle preview ready from worker."""
        if self._destroyed:
            return
        # Only emit if this is the current request (not stale)
        if request_id == self._current_request_id:
            self.preview_ready.emit(qimage, width, height)

    def _on_error(self, request_id: int, error_message: str) -> None:
        """Handle error from worker."""
        if self._destroyed:
            return
        if request_id == self._current_request_id:
            self.preview_failed.emit(error_message)

    def _on_worker_finished(self) -> None:
        """Clean up after worker finishes."""
        self._cleanup_thread()

    def _cancel_current(self) -> None:
        """Cancel any in-progress work."""
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
                self._worker.preview_ready.disconnect()
                self._worker.error.disconnect()
                self._worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected or never connected

        if self._thread is not None:
            if self._thread.isRunning():
                self._thread.quit()
                if not self._thread.wait(1000):
                    logger.warning("Preview worker thread did not stop within timeout")
            if not self._destroyed:
                self._thread.deleteLater()
            self._thread = None
        if self._worker is not None:
            if not self._destroyed:
                self._worker.deleteLater()
            self._worker = None

    def shutdown(self) -> None:
        """Shutdown the service and clean up resources."""
        self._cancel_current()
        self._destroyed = True
