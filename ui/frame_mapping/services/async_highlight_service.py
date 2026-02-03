"""Async pixel highlight mask generation service for frame mapping workbench.

This service offloads the 65K pixel iteration for palette index highlighting
to a background thread, preventing UI blocking during palette swatch hover.

Uses the same pattern as AsyncPreviewService:
- Persistent worker thread (avoids creation/destruction overhead)
- Request ID pattern cancels stale highlights when new request arrives
- QImage created in worker (thread-safe), QPixmap conversion on main thread
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image
from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage

from core.services.image_utils import pil_to_qimage
from ui.common import WorkerManager, is_valid_qt
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette

logger = get_logger(__name__)


@dataclass
class HighlightRequest:
    """Encapsulates all data needed for a highlight mask generation request."""

    request_id: int
    ai_image: Image.Image
    palette_index: int
    sheet_palette: SheetPalette | None
    display_scale: int
    user_scale: float
    flip_h: bool
    flip_v: bool
    # Optional: pre-computed palette index map for fast vectorized lookup
    ai_index_map: np.ndarray | None = field(default=None)


class _HighlightWorker(QObject):
    """Worker that generates highlight masks in a background thread.

    Emits QImage (thread-safe) instead of QPixmap. The main thread
    must convert to QPixmap.
    """

    highlight_ready = Signal(int, QImage)
    """Emitted when highlight mask generation completes.

    Args:
        request_id: Internal request ID for tracking stale requests
        qimage: QImage of the highlight mask (thread-safe)
    """

    error = Signal(int, str)
    """Emitted when highlight generation fails.

    Args:
        request_id: Internal request ID
        error_message: Description of the error
    """

    finished = Signal()
    """Emitted when worker completes all processing."""

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

    @Slot(HighlightRequest)
    def process_request(self, request: HighlightRequest) -> None:
        """Generate highlight mask for the request. Runs in Worker Thread."""
        request_id = request.request_id

        # Fast rejection if this request is already stale
        if self._should_cancel(request_id):
            return

        try:
            ai_image = request.ai_image
            palette_index = request.palette_index
            sheet_palette = request.sheet_palette
            ai_index_map = request.ai_index_map

            # Create mask image with same size as AI frame
            width, height = ai_image.size
            mask = Image.new("RGBA", (width, height), (0, 0, 0, 0))

            # Fast path: use pre-computed index map with vectorized numpy
            if ai_index_map is not None:
                # Get alpha channel to exclude transparent pixels
                rgba_array = np.array(ai_image.convert("RGBA"))
                alpha = rgba_array[:, :, 3]

                # Vectorized mask: pixels matching palette_index AND alpha > 0
                match_mask = (ai_index_map == palette_index) & (alpha > 0)

                # Create mask array: yellow (255, 255, 0) with 128 alpha where matched
                mask_array = np.zeros((height, width, 4), dtype=np.uint8)
                mask_array[match_mask] = [255, 255, 0, 128]

                mask = Image.fromarray(mask_array, "RGBA")
            else:
                # Fallback: pixel-by-pixel iteration using RGB lookup
                # Build palette index lookup if sheet palette available
                palette_lookup: dict[tuple[int, int, int], int] = {}
                if sheet_palette is not None and sheet_palette.colors:
                    palette_lookup = {color: idx for idx, color in enumerate(sheet_palette.colors)}

                mask_pixels = mask.load()
                ai_pixels = ai_image.load()

                if mask_pixels is None or ai_pixels is None:
                    self.error.emit(request_id, "Failed to load pixels")
                    return

                # Iterate all pixels and find matches
                for y in range(height):
                    # Periodic cancellation check (every 64 rows)
                    if y % 64 == 0 and self._should_cancel(request_id):
                        return

                    for x in range(width):
                        pixel_raw = ai_pixels[x, y]
                        if isinstance(pixel_raw, int | float):
                            continue  # Grayscale, skip

                        # At this point pixel_raw is a tuple - check length
                        if len(pixel_raw) < 3:
                            continue

                        # Check if pixel has alpha and is transparent
                        if len(pixel_raw) >= 4 and int(pixel_raw[3]) == 0:
                            continue  # Skip transparent pixels

                        rgb = (int(pixel_raw[0]), int(pixel_raw[1]), int(pixel_raw[2]))
                        pixel_idx = self._lookup_palette_index(rgb, palette_lookup)

                        if pixel_idx == palette_index:
                            # Highlight this pixel with yellow tint at 50% opacity
                            mask_pixels[x, y] = (255, 255, 0, 128)

            # Check cancellation after heavy work
            if self._should_cancel(request_id):
                return

            # Apply flip transforms to match AI frame display
            if request.flip_h:
                mask = mask.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if request.flip_v:
                mask = mask.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

            # Scale to display size (display_scale * user_scale)
            total_scale = request.display_scale * request.user_scale
            scaled_width = int(width * total_scale)
            scaled_height = int(height * total_scale)
            scaled_mask = mask.resize((scaled_width, scaled_height), Image.Resampling.NEAREST)

            # Convert PIL image to QImage (thread-safe)
            qimage = pil_to_qimage(scaled_mask, thread_safe=True)

            # Final check before emit
            if not self._should_cancel(request_id):
                self.highlight_ready.emit(request_id, qimage)

        except Exception as e:
            logger.exception("Highlight worker error")
            if not self._should_cancel(request_id):
                self.error.emit(request_id, str(e))
        finally:
            self.finished.emit()

    def _lookup_palette_index(self, rgb: tuple[int, int, int], palette_lookup: dict[tuple[int, int, int], int]) -> int:
        """Look up palette index for an RGB color.

        Args:
            rgb: RGB tuple to look up
            palette_lookup: Color -> index mapping

        Returns:
            Palette index, or -1 if not found
        """
        # Exact match first
        if rgb in palette_lookup:
            return palette_lookup[rgb]

        # No match found
        return -1


class AsyncHighlightService(QObject):
    """Async highlight service for workbench canvas.

    Manages a background worker thread for generating pixel highlight masks.
    Uses incrementing request IDs to cancel stale highlights when new
    requests arrive.

    Signals:
        highlight_ready: Emitted when highlight mask is ready.
            Args: (qimage: QImage)
        highlight_failed: Emitted when highlight generation fails.
            Args: (error_message: str)
    """

    highlight_ready = Signal(QImage)
    highlight_failed = Signal(str)

    # Internal signal to trigger worker
    _start_worker = Signal(HighlightRequest)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._destroyed = False
        self._current_request_id = 0

        # Image buffer cache to avoid repeated copies during rapid palette hover
        # Only copy when the source image identity changes
        self._cached_ai_image: Image.Image | None = None
        self._cached_ai_index_map: np.ndarray | None = None
        self._cached_image_id: int | None = None  # id() of source ai_image

        # Create persistent thread and worker
        self._thread: QThread | None = QThread()
        self._worker: _HighlightWorker | None = _HighlightWorker()
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._start_worker.connect(self._worker.process_request)
        self._worker.highlight_ready.connect(self._on_highlight_ready)
        self._worker.error.connect(self._on_error)

        # Start the thread via WorkerManager for proper lifecycle tracking
        WorkerManager.start_worker(self._thread)

        if parent is not None:
            parent.destroyed.connect(self._on_parent_destroyed)

    def __del__(self) -> None:  # pragma: no cover - best-effort Qt cleanup
        try:
            self.shutdown()
        except Exception:
            pass

    def _on_parent_destroyed(self) -> None:
        """Handle parent destruction."""
        self._destroyed = True
        self.shutdown()

    def request_highlight(
        self,
        ai_image: Image.Image,
        palette_index: int,
        sheet_palette: SheetPalette | None,
        display_scale: int,
        user_scale: float,
        flip_h: bool,
        flip_v: bool,
        ai_index_map: np.ndarray | None = None,
    ) -> None:
        """Request a highlight mask generation.

        Cancels any in-progress generation and starts a new one.
        The result will be emitted via highlight_ready signal.

        Args:
            ai_image: The AI-generated frame (PIL Image).
            palette_index: The palette index to highlight.
            sheet_palette: The sheet palette for color lookup.
            display_scale: Base scale factor for display.
            user_scale: User-controlled scale factor.
            flip_h: Horizontal flip state.
            flip_v: Vertical flip state.
            ai_index_map: Optional pre-computed palette index map for fast vectorized lookup.
                If provided, enables 2-3x faster highlighting via numpy operations.
        """
        if self._destroyed:
            return

        # Increment request ID to invalidate any in-progress work
        self._current_request_id += 1
        request_id = self._current_request_id

        # Use cached copies if image identity unchanged (avoids repeated copies during palette hover)
        image_id = id(ai_image)
        if image_id != self._cached_image_id:
            self._cached_ai_image = ai_image.copy()
            self._cached_ai_index_map = ai_index_map.copy() if ai_index_map is not None else None
            self._cached_image_id = image_id

        # Create request with cached copies
        request = HighlightRequest(
            request_id=request_id,
            ai_image=self._cached_ai_image,  # type: ignore[arg-type]  # cached copy
            palette_index=palette_index,
            sheet_palette=sheet_palette,
            display_scale=display_scale,
            user_scale=user_scale,
            flip_h=flip_h,
            flip_v=flip_v,
            ai_index_map=self._cached_ai_index_map,
        )

        # Update worker target ID
        if self._worker:
            self._worker.set_target_request_id(request_id)
            # Trigger processing in worker thread
            self._start_worker.emit(request)

    def cancel(self) -> None:
        """Cancel any in-progress highlight generation."""
        # Simply increment request ID to invalidate in-progress work
        self._current_request_id += 1
        if self._worker:
            self._worker.set_target_request_id(self._current_request_id)

    def clear_image_cache(self) -> None:
        """Clear cached image buffers.

        Call this when the AI frame changes (set_ai_frame) to ensure
        the next request uses fresh copies.
        """
        self._cached_ai_image = None
        self._cached_ai_index_map = None
        self._cached_image_id = None

    def _on_highlight_ready(self, request_id: int, qimage: QImage) -> None:
        """Handle highlight ready from worker."""
        if self._destroyed:
            return
        # Only emit if this is the current request (not stale)
        if request_id == self._current_request_id:
            self.highlight_ready.emit(qimage)

    def _on_error(self, request_id: int, error_message: str) -> None:
        """Handle error from worker."""
        if self._destroyed:
            return
        if request_id == self._current_request_id:
            self.highlight_failed.emit(error_message)

    def shutdown(self) -> None:
        """Shutdown the service and clean up resources."""
        self._destroyed = True
        self.clear_image_cache()

        try:
            # Block signals first to prevent emission during cleanup
            if self._worker is not None and is_valid_qt(self._worker):
                self._worker.blockSignals(True)
                try:
                    self._worker.highlight_ready.disconnect()
                    self._worker.error.disconnect()
                except (RuntimeError, TypeError):
                    pass  # Already disconnected or never connected

            # Clean up thread via WorkerManager
            if self._thread is not None and is_valid_qt(self._thread):
                WorkerManager.cleanup_worker(self._thread, timeout=3000)
                self._thread = None

            if self._worker is not None and is_valid_qt(self._worker):
                self._worker.deleteLater()
                self._worker = None
        except RuntimeError:
            # Objects already deleted by Qt parent-child mechanism
            pass
