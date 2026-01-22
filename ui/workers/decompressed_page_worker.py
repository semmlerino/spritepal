"""
Background worker for rendering decompressed sprite pages in the Paged Tile View.

Attempts HAL decompression at grid positions to show actual sprites instead of
raw compressed bytes. Failed decompressions show placeholder images.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter

from core.services.image_utils import pil_to_qimage
from core.tile_renderer import TileRenderer
from core.workers.base import BaseWorker, handle_worker_errors
from ui.workers.paged_tile_view_worker import _compute_palette_hash
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.rom_injector import ROMInjector

logger = get_logger(__name__)

# Constants for sprite thumbnail rendering
CELL_SIZE = 256  # Size of each cell in pixels (larger for better sprite visibility)
PLACEHOLDER_COLOR = QColor(80, 80, 80)  # Gray for failed decompression
PLACEHOLDER_TEXT_COLOR = QColor(150, 150, 150)  # Light gray for "?" text


class DecompressedPageWorker(BaseWorker):
    """
    Worker thread that renders a page by attempting HAL decompression at each grid position.

    For each cell in the grid, attempts to decompress sprite data at the calculated
    ROM offset. Successful decompressions are rendered as thumbnails; failures show
    a gray placeholder with "?" indicator.

    Signals:
        page_ready: Emitted when page rendering is complete.
            Args: page_number, rendered QImage, page_offset, palette_hash
    """

    page_ready = Signal(int, QImage, int, int)  # page_number, image, offset, palette_hash

    def __init__(
        self,
        rom_data: bytes,
        rom_injector: ROMInjector,
        page_number: int,
        offset: int,
        cols: int,
        rows: int,
        step_size: int,
        palette: list[list[int]] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the decompressed page rendering worker.

        Args:
            rom_data: Raw ROM byte data (without SMC header)
            rom_injector: ROMInjector instance for HAL decompression
            page_number: Page number being rendered (for signal)
            offset: Starting byte offset in ROM data
            cols: Number of tile columns in the grid
            rows: Number of tile rows in the grid
            step_size: Byte step between grid cells
            palette: Optional custom palette (list of 16 RGB lists)
            parent: Qt parent object
        """
        super().__init__(parent)
        self._rom_data = rom_data
        self._rom_injector = rom_injector
        self._page_number = page_number
        self._offset = offset
        self._cols = cols
        self._rows = rows
        self._step_size = step_size
        self._palette = palette
        self._palette_hash = _compute_palette_hash(palette)
        self._tile_renderer = TileRenderer()

    @handle_worker_errors("decompressed page rendering", handle_interruption=True)
    @override
    def run(self) -> None:
        """Render the decompressed page in the background thread."""
        logger.debug(
            f"Rendering decompressed page {self._page_number}: offset=0x{self._offset:06X}, "
            f"grid={self._cols}x{self._rows}, step={self._step_size}, palette_hash={self._palette_hash}"
        )

        self.emit_progress(0, f"Rendering decompressed page {self._page_number}...")

        # Check for cancellation
        self.check_cancellation()

        total_cells = self._cols * self._rows
        cell_images: list[QImage] = []

        for idx in range(total_cells):
            # Check for cancellation periodically
            if idx % 8 == 0:
                self.check_cancellation()
                progress = int((idx / total_cells) * 80)
                self.emit_progress(progress, f"Decompressing cell {idx + 1}/{total_cells}...")

            cell_offset = self._offset + (idx * self._step_size)

            # Attempt decompression at this offset
            cell_image = self._try_decompress_cell(cell_offset)
            cell_images.append(cell_image)

        self.emit_progress(85, "Compositing page...")
        self.check_cancellation()

        # Compose all cells into a single image
        composite = self._compose_grid(cell_images)

        self.emit_progress(100, "Page ready")

        logger.debug(f"Decompressed page {self._page_number} rendered: {composite.width()}x{composite.height()} pixels")

        # Emit the result
        self.page_ready.emit(self._page_number, composite, self._offset, self._palette_hash)
        self.operation_finished.emit(True, f"Decompressed page {self._page_number} rendered")

    def _try_decompress_cell(self, offset: int) -> QImage:
        """
        Try to decompress sprite data at the given offset.

        Args:
            offset: ROM byte offset to attempt decompression

        Returns:
            Rendered thumbnail QImage on success, placeholder on failure
        """
        # Bounds check
        if offset < 0 or offset >= len(self._rom_data):
            return self._create_placeholder_image()

        try:
            # Attempt HAL decompression
            _compressed_size, tile_data, _slack = self._rom_injector.find_compressed_sprite(
                self._rom_data,
                offset,
                expected_size=4096,  # Max 128 tiles * 32 bytes
                enforce_ratio=True,  # Reject invalid ratios to filter out garbage
            )

            if not tile_data or len(tile_data) < 32:
                return self._create_placeholder_image()

            # Render the decompressed tiles as a thumbnail
            return self._render_thumbnail(tile_data)

        except Exception as e:
            logger.debug(f"Decompression failed at 0x{offset:06X}: {e}")
            return self._create_placeholder_image()

    def _render_thumbnail(self, tile_data: bytes) -> QImage:
        """
        Render decompressed tile data as a thumbnail.

        Args:
            tile_data: Decompressed 4bpp tile data

        Returns:
            Rendered QImage thumbnail
        """
        try:
            # Calculate tile count and dimensions
            tile_count = len(tile_data) // 32
            if tile_count == 0:
                return self._create_placeholder_image()

            # Calculate grid dimensions (try to make roughly square)
            width_tiles = min(8, tile_count)  # Max 8 tiles wide for thumbnail
            height_tiles = min(8, (tile_count + width_tiles - 1) // width_tiles)

            # Render using TileRenderer (PIL-based, thread-safe)
            pil_image = self._tile_renderer.render_tiles(
                tile_data,
                width_tiles,
                height_tiles,
                custom_palette=self._palette,
            )

            if pil_image is None:
                return self._create_placeholder_image()

            # Convert to QImage (thread_safe=True for worker thread)
            qimage = pil_to_qimage(pil_image, with_alpha=True, thread_safe=True)

            # Scale to cell size
            if not qimage.isNull():
                qimage = qimage.scaled(
                    CELL_SIZE,
                    CELL_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

            return qimage

        except Exception as e:
            logger.debug(f"Thumbnail rendering failed: {e}")
            return self._create_placeholder_image()

    def _create_placeholder_image(self) -> QImage:
        """
        Create a placeholder image for failed decompression.

        Returns:
            Gray QImage with "?" indicator
        """
        image = QImage(CELL_SIZE, CELL_SIZE, QImage.Format.Format_RGBA8888)
        image.fill(PLACEHOLDER_COLOR)

        # Draw "?" indicator
        painter = QPainter(image)
        try:
            painter.setPen(PLACEHOLDER_TEXT_COLOR)
            font = painter.font()
            font.setPixelSize(16)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(image.rect(), 0x84, "?")  # AlignCenter = 0x84
        finally:
            painter.end()

        return image

    def _compose_grid(self, cell_images: list[QImage]) -> QImage:
        """
        Compose cell images into a single grid image.

        Args:
            cell_images: List of cell thumbnail images

        Returns:
            Composite QImage containing all cells arranged in a grid
        """
        # Calculate composite dimensions
        width = self._cols * CELL_SIZE
        height = self._rows * CELL_SIZE

        # Create composite image
        composite = QImage(width, height, QImage.Format.Format_RGBA8888)
        composite.fill(QColor(40, 40, 40))  # Dark background

        painter = QPainter(composite)
        try:
            for idx, cell_image in enumerate(cell_images):
                col = idx % self._cols
                row = idx // self._cols
                x = col * CELL_SIZE
                y = row * CELL_SIZE

                if not cell_image.isNull():
                    # Center the cell image if it's smaller than CELL_SIZE
                    cell_w = cell_image.width()
                    cell_h = cell_image.height()
                    offset_x = (CELL_SIZE - cell_w) // 2
                    offset_y = (CELL_SIZE - cell_h) // 2
                    painter.drawImage(x + offset_x, y + offset_y, cell_image)
        finally:
            painter.end()

        return composite

    @property
    def page_number(self) -> int:
        """Get the page number this worker is rendering."""
        return self._page_number

    @property
    def offset(self) -> int:
        """Get the byte offset this worker is rendering from."""
        return self._offset

    @property
    def step_size(self) -> int:
        """Get the step size between cells."""
        return self._step_size

    @property
    def palette_hash(self) -> int:
        """Get the palette hash for cache key generation."""
        return self._palette_hash
