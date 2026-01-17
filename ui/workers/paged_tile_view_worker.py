"""
Background worker for rendering tile grid pages in the Paged Tile View.

Renders large tile grids without blocking the UI thread.
"""

from __future__ import annotations

import logging
from typing import override

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from core.services.image_utils import pil_to_qimage
from core.tile_renderer import TileRenderer
from core.workers.base import BaseWorker, handle_worker_errors

logger = logging.getLogger(__name__)

# Constants for 4bpp SNES tiles
BYTES_PER_TILE = 32


def _compute_palette_hash(palette: list[list[int]] | None) -> int:
    """Compute a hash for palette data for cache key generation.

    Returns a 31-bit positive hash to fit within Qt Signal's int type.
    """
    if palette is None:
        return 0
    # Simple hash based on first and last colors + length
    if len(palette) == 0:
        return 0
    first = tuple(palette[0]) if palette[0] else (0, 0, 0)
    last = tuple(palette[-1]) if palette[-1] else (0, 0, 0)
    # Mask to 31 bits to ensure it fits in signed 32-bit int
    return hash((first, last, len(palette))) & 0x7FFFFFFF


class PagedTileViewWorker(BaseWorker):
    """
    Worker thread that renders a single page of tiles from ROM data.

    Renders tiles using TileRenderer (PIL-based, thread-safe) and emits
    the result as a QImage.

    Signals:
        page_ready: Emitted when page rendering is complete.
            Args: page_number, rendered QImage, page_offset, palette_hash
    """

    page_ready = Signal(int, QImage, int, int)  # page_number, image, offset, palette_hash

    def __init__(
        self,
        rom_data: bytes,
        page_number: int,
        offset: int,
        cols: int,
        rows: int,
        palette: list[list[int]] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the page rendering worker.

        Args:
            rom_data: Raw ROM byte data
            page_number: Page number being rendered (for signal)
            offset: Starting byte offset in ROM data
            cols: Number of tile columns in the grid
            rows: Number of tile rows in the grid
            palette: Optional custom palette (list of 16 RGB lists)
            parent: Qt parent object
        """
        super().__init__(parent)
        self._rom_data = rom_data
        self._page_number = page_number
        self._offset = offset
        self._cols = cols
        self._rows = rows
        self._palette = palette
        self._palette_hash = _compute_palette_hash(palette)

    @handle_worker_errors("tile page rendering", handle_interruption=True)
    @override
    def run(self) -> None:
        """Render the tile page in the background thread."""
        logger.debug(
            f"Rendering page {self._page_number}: offset=0x{self._offset:06X}, "
            f"grid={self._cols}x{self._rows}, palette_hash={self._palette_hash}"
        )

        self.emit_progress(0, f"Rendering page {self._page_number}...")

        # Check for cancellation
        self.check_cancellation()

        # Calculate byte range for this page
        bytes_per_page = self._cols * self._rows * BYTES_PER_TILE

        # Extract tile data for this page
        end_offset = min(self._offset + bytes_per_page, len(self._rom_data))
        tile_data = self._rom_data[self._offset : end_offset]

        if len(tile_data) == 0:
            logger.warning(f"No tile data at offset 0x{self._offset:06X}")
            # Create a small placeholder image
            empty_image = QImage(1, 1, QImage.Format.Format_RGBA8888)
            empty_image.fill(0)
            self.page_ready.emit(self._page_number, empty_image, self._offset, self._palette_hash)
            self.operation_finished.emit(True, "Page rendered (empty)")
            return

        self.emit_progress(20, "Rendering tiles...")
        self.check_cancellation()

        # Render using TileRenderer (PIL-based, thread-safe)
        renderer = TileRenderer()
        pil_image = renderer.render_tiles(
            tile_data,
            self._cols,
            self._rows,
            custom_palette=self._palette,
        )

        self.emit_progress(80, "Converting to Qt image...")
        self.check_cancellation()

        if pil_image is None:
            logger.error(f"Failed to render page {self._page_number}")
            self.emit_error(f"Failed to render page {self._page_number}")
            self.operation_finished.emit(False, "Render failed")
            return

        # Convert to QImage (thread_safe=True for worker thread)
        qimage = pil_to_qimage(pil_image, with_alpha=True, thread_safe=True)

        self.emit_progress(100, "Page ready")

        logger.debug(f"Page {self._page_number} rendered: {qimage.width()}x{qimage.height()} pixels")

        # Emit the result
        self.page_ready.emit(self._page_number, qimage, self._offset, self._palette_hash)
        self.operation_finished.emit(True, f"Page {self._page_number} rendered")

    @property
    def page_number(self) -> int:
        """Get the page number this worker is rendering."""
        return self._page_number

    @property
    def offset(self) -> int:
        """Get the byte offset this worker is rendering from."""
        return self._offset

    @property
    def palette_hash(self) -> int:
        """Get the palette hash for cache key generation."""
        return self._palette_hash
