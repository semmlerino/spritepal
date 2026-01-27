"""Async quantization worker for image import dialog.

Offloads color quantization to a background thread to keep
the UI responsive during potentially slow quantization operations.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image
from PySide6.QtCore import QObject, QThread, Signal

from core.color_quantization import ColorQuantizer, QuantizationResult
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class QuantizationRequest:
    """Encapsulates all data needed for a quantization request."""

    request_id: int
    source_image: Image.Image
    target_size: tuple[int, int] | None
    dither: bool
    transparency_threshold: int


class _QuantizationWorker(QObject):
    """Worker that performs color quantization in a background thread."""

    result_ready = Signal(int, object)  # (request_id, QuantizationResult)
    error = Signal(int, str)  # (request_id, error_message)
    finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._stop_requested = False
        self._current_request: QuantizationRequest | None = None

    def request_stop(self) -> None:
        """Request the worker to stop."""
        self._stop_requested = True

    def set_request(self, request: QuantizationRequest) -> None:
        """Set the request to process. Called from main thread before run()."""
        self._current_request = request

    def run(self) -> None:
        """Perform quantization for the current request."""
        if self._current_request is None:
            self.finished.emit()
            return

        request = self._current_request
        request_id = request.request_id

        try:
            if self._stop_requested:
                self.finished.emit()
                return

            # Create quantizer with request options
            quantizer = ColorQuantizer(
                dither=request.dither,
                transparency_threshold=request.transparency_threshold,
            )

            # Perform quantization
            result = quantizer.quantize(
                request.source_image,
                target_size=request.target_size,
            )

            # Check cancellation after heavy work
            if self._stop_requested:
                self.finished.emit()
                return

            self.result_ready.emit(request_id, result)

        except Exception as e:
            logger.exception("Quantization worker error")
            self.error.emit(request_id, str(e))
        finally:
            self.finished.emit()


class AsyncQuantizationService(QObject):
    """Async quantization service for image import dialog.

    Manages a background worker thread for color quantization.
    Uses incrementing request IDs to cancel stale operations.

    Signals:
        result_ready: Emitted when quantization completes.
            Args: (result: QuantizationResult)
        quantization_failed: Emitted on failure.
            Args: (error_message: str)
        quantization_started: Emitted when quantization begins.
    """

    result_ready = Signal(object)  # QuantizationResult
    quantization_failed = Signal(str)  # error_message
    quantization_started = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker: _QuantizationWorker | None = None
        self._thread: QThread | None = None
        self._destroyed = False
        self._current_request_id = 0

        if parent is not None:
            parent.destroyed.connect(self._on_parent_destroyed)

    def _on_parent_destroyed(self) -> None:
        """Handle parent destruction."""
        self._destroyed = True
        self.shutdown()

    def request_quantization(
        self,
        source_image: Image.Image,
        target_size: tuple[int, int] | None,
        dither: bool,
        transparency_threshold: int,
    ) -> None:
        """Request async quantization.

        Cancels any in-progress quantization and starts a new one.

        Args:
            source_image: PIL Image to quantize.
            target_size: Optional (width, height) for scaling.
            dither: Whether to apply dithering.
            transparency_threshold: Alpha threshold for transparency.
        """
        if self._destroyed:
            return

        # Increment request ID to invalidate any in-progress work
        self._current_request_id += 1
        request_id = self._current_request_id

        # Cancel existing work
        self._cancel_current()

        # Create request with image copy to avoid threading issues
        request = QuantizationRequest(
            request_id=request_id,
            source_image=source_image.copy(),
            target_size=target_size,
            dither=dither,
            transparency_threshold=transparency_threshold,
        )

        # Notify that quantization is starting
        self.quantization_started.emit()

        # Start worker
        self._worker = _QuantizationWorker()
        self._worker.set_request(request)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._thread.started.connect(self._worker.run)
        self._worker.result_ready.connect(self._on_result_ready)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)

        # Start
        self._thread.start()

    def _on_result_ready(self, request_id: int, result: QuantizationResult) -> None:
        """Handle result from worker."""
        if self._destroyed:
            return
        if request_id == self._current_request_id:
            self.result_ready.emit(result)

    def _on_error(self, request_id: int, error_message: str) -> None:
        """Handle error from worker."""
        if self._destroyed:
            return
        if request_id == self._current_request_id:
            self.quantization_failed.emit(error_message)

    def _on_worker_finished(self) -> None:
        """Clean up after worker finishes."""
        self._cleanup_thread()

    def _cancel_current(self) -> None:
        """Cancel any in-progress work."""
        if self._worker:
            self._worker.request_stop()
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        """Clean up thread resources."""
        if self._thread is not None:
            if self._thread.isRunning():
                self._thread.quit()
                if not self._thread.wait(1000):
                    logger.warning("Quantization worker thread did not stop within timeout")
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
