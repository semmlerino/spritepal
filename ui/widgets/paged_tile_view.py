"""
Paged Tile View Widget for fast visual scanning of large ROM tile ranges.

Displays a configurable grid of tiles with paging navigation, optimized for
quickly browsing through ROM data to find sprites.
"""

from __future__ import annotations

import logging
from typing import override

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.common.paged_tile_view_cache import PagedTileViewCache
from ui.common.spacing_constants import SPACING_SMALL, SPACING_STANDARD, SPACING_TINY
from ui.styles.theme import COLORS
from ui.workers.paged_tile_view_worker import (
    BYTES_PER_TILE,
    PagedTileViewWorker,
    _compute_palette_hash,
)

logger = logging.getLogger(__name__)

# Grid preset configurations: (name, cols, rows)
GRID_PRESETS: list[tuple[str, int, int]] = [
    ("Small (20x20)", 20, 20),  # 400 tiles
    ("Medium (35x35)", 35, 35),  # 1225 tiles
    ("Large (50x50)", 50, 50),  # 2500 tiles (default)
    ("XL (100x100)", 100, 100),  # 10000 tiles
]

DEFAULT_PRESET_INDEX = 2  # Large (50x50)


class TileGridGraphicsView(QGraphicsView):
    """
    Custom QGraphicsView that handles tile grid display with click detection.

    Emits tile_clicked when user clicks on a tile, providing the ROM offset.
    """

    tile_clicked = Signal(int)  # ROM offset of clicked tile

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # Store grid info for click coordinate calculation
        self._cols = 50
        self._rows = 50
        self._page_offset = 0
        self._pixmap_item: QGraphicsPixmapItem | None = None

        # View configuration
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Styling
        self.setStyleSheet(f"""
            QGraphicsView {{
                background-color: {COLORS["preview_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
            }}
        """)

    def set_grid_info(self, cols: int, rows: int, page_offset: int) -> None:
        """Update grid dimensions and offset for click calculations."""
        self._cols = cols
        self._rows = rows
        self._page_offset = page_offset

    def set_image(self, image: QImage) -> None:
        """Display an image in the view."""
        pixmap = QPixmap.fromImage(image)
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def clear_image(self) -> None:
        """Clear the displayed image."""
        self._scene.clear()
        self._pixmap_item = None

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse click to detect tile selection."""
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap_item is not None:
            # Map click to scene coordinates
            scene_pos = self.mapToScene(event.pos())
            # Check if within pixmap bounds
            pixmap = self._pixmap_item.pixmap()
            if 0 <= scene_pos.x() < pixmap.width() and 0 <= scene_pos.y() < pixmap.height():
                # Calculate tile coordinates (8x8 pixels per tile)
                tile_x = int(scene_pos.x()) // 8
                tile_y = int(scene_pos.y()) // 8

                # Ensure within grid bounds
                if 0 <= tile_x < self._cols and 0 <= tile_y < self._rows:
                    # Calculate ROM offset
                    tile_index = tile_y * self._cols + tile_x
                    rom_offset = self._page_offset + tile_index * BYTES_PER_TILE

                    logger.debug(f"Tile clicked: ({tile_x}, {tile_y}) -> offset 0x{rom_offset:06X}")
                    self.tile_clicked.emit(rom_offset)
                    return

        super().mousePressEvent(event)

    @override
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle zoom via mouse wheel."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
        else:
            # Normal scroll
            super().wheelEvent(event)

    def reset_zoom(self) -> None:
        """Reset zoom to fit the entire image."""
        if self._scene.sceneRect().isValid():
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class PagedTileViewWidget(QWidget):
    """
    Widget for browsing ROM tiles in a paged grid format.

    Displays a configurable grid of tiles with navigation controls for
    quickly scanning large ROM ranges to find sprites.

    Signals:
        tile_clicked: Emitted when user clicks a tile. Args: ROM offset
        page_changed: Emitted when the page changes. Args: page number
    """

    tile_clicked = Signal(int)  # ROM offset
    page_changed = Signal(int)  # Page number

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Data
        self._rom_data: bytes = b""
        self._palette: list[list[int]] | None = None
        self._palette_hash: int = 0

        # Grid configuration
        self._cols = GRID_PRESETS[DEFAULT_PRESET_INDEX][1]
        self._rows = GRID_PRESETS[DEFAULT_PRESET_INDEX][2]
        self._current_page = 0
        self._total_pages = 0

        # Worker and cache
        self._worker: PagedTileViewWorker | None = None
        self._cache = PagedTileViewCache()

        # UI
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)
        layout.setSpacing(SPACING_SMALL)

        # Navigation bar (top)
        nav_frame = self._create_navigation_bar()
        layout.addWidget(nav_frame)

        # Graphics view (center, expandable)
        self._graphics_view = TileGridGraphicsView()
        self._graphics_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._graphics_view.tile_clicked.connect(self._on_tile_clicked)
        layout.addWidget(self._graphics_view, stretch=1)

        # Status bar (bottom)
        self._status_label = QLabel("No ROM data loaded")
        self._status_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        layout.addWidget(self._status_label)

    def _create_navigation_bar(self) -> QFrame:
        """Create the navigation bar with page controls."""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS["panel_background"]};
                border-radius: 4px;
                padding: {SPACING_TINY}px;
            }}
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(SPACING_SMALL, SPACING_TINY, SPACING_SMALL, SPACING_TINY)
        layout.setSpacing(SPACING_STANDARD)

        # Grid size selector
        layout.addWidget(QLabel("Grid:"))
        self._grid_combo = QComboBox()
        for name, _, _ in GRID_PRESETS:
            self._grid_combo.addItem(name)
        self._grid_combo.setCurrentIndex(DEFAULT_PRESET_INDEX)
        self._grid_combo.currentIndexChanged.connect(self._on_grid_size_changed)
        layout.addWidget(self._grid_combo)

        # Page navigation
        layout.addWidget(QLabel("Page:"))

        self._prev_btn = QPushButton("<")
        self._prev_btn.setFixedWidth(30)
        self._prev_btn.setToolTip("Previous page (Page Up)")
        self._prev_btn.clicked.connect(self._go_prev_page)
        layout.addWidget(self._prev_btn)

        self._page_spinbox = QSpinBox()
        self._page_spinbox.setMinimum(1)
        self._page_spinbox.setMaximum(1)
        self._page_spinbox.setFixedWidth(70)
        self._page_spinbox.valueChanged.connect(self._on_page_spinbox_changed)
        layout.addWidget(self._page_spinbox)

        self._page_total_label = QLabel("/ 0")
        layout.addWidget(self._page_total_label)

        self._next_btn = QPushButton(">")
        self._next_btn.setFixedWidth(30)
        self._next_btn.setToolTip("Next page (Page Down)")
        self._next_btn.clicked.connect(self._go_next_page)
        layout.addWidget(self._next_btn)

        # Spacer
        layout.addStretch()

        # Go to offset input
        layout.addWidget(QLabel("Go to:"))
        self._offset_input = QLineEdit()
        self._offset_input.setPlaceholderText("0x294D0A")
        self._offset_input.setFixedWidth(100)
        self._offset_input.setToolTip("Enter offset (hex with 0x prefix, or decimal)")
        self._offset_input.returnPressed.connect(self._on_goto_offset)
        layout.addWidget(self._offset_input)

        self._goto_btn = QPushButton("Go")
        self._goto_btn.setFixedWidth(40)
        self._goto_btn.setToolTip("Jump to offset (Enter)")
        self._goto_btn.clicked.connect(self._on_goto_offset)
        layout.addWidget(self._goto_btn)

        # Spacer
        layout.addStretch()

        # Zoom controls
        self._zoom_fit_btn = QPushButton("Fit")
        self._zoom_fit_btn.setToolTip("Reset zoom to fit (Home)")
        self._zoom_fit_btn.clicked.connect(self._reset_zoom)
        layout.addWidget(self._zoom_fit_btn)

        # Offset display
        self._offset_label = QLabel("Offset: --")
        self._offset_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self._offset_label)

        return frame

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        pass  # Most connections done in _setup_ui

    def set_rom_data(self, rom_data: bytes) -> None:
        """
        Set the ROM data to display.

        Args:
            rom_data: Raw ROM byte data
        """
        self._rom_data = rom_data
        self._update_page_count()
        self._current_page = 0
        self._cache.invalidate_all()  # Clear cache when ROM changes
        self._update_navigation_state()
        self._request_page_render()

    def set_palette(self, palette: list[list[int]] | None) -> None:
        """
        Set the palette for tile rendering.

        Args:
            palette: List of 16 RGB color lists, or None for grayscale
        """
        new_hash = _compute_palette_hash(palette)
        if new_hash != self._palette_hash:
            self._palette = palette
            self._palette_hash = new_hash
            # Re-render current page with new palette
            self._request_page_render()

    def set_grid_dimensions(self, cols: int, rows: int) -> None:
        """
        Set the grid dimensions.

        Args:
            cols: Number of tile columns
            rows: Number of tile rows
        """
        if cols != self._cols or rows != self._rows:
            self._cols = cols
            self._rows = rows
            self._update_page_count()
            # Clamp current page to valid range
            if self._current_page >= self._total_pages:
                self._current_page = max(0, self._total_pages - 1)
            self._update_navigation_state()
            self._request_page_render()

    def go_to_page(self, page: int) -> None:
        """
        Navigate to a specific page.

        Args:
            page: Page number (0-indexed)
        """
        if 0 <= page < self._total_pages and page != self._current_page:
            self._current_page = page
            self._update_navigation_state()
            self._request_page_render()
            self.page_changed.emit(page)

    def go_to_offset(self, offset: int) -> None:
        """
        Navigate to the page containing a specific ROM offset.

        Args:
            offset: ROM byte offset
        """
        if len(self._rom_data) == 0:
            return

        bytes_per_page = self._cols * self._rows * BYTES_PER_TILE
        page = offset // bytes_per_page
        self.go_to_page(page)

    def get_current_offset(self) -> int:
        """Get the starting offset of the current page."""
        return self._page_to_offset(self._current_page)

    def get_current_page(self) -> int:
        """Get the current page number."""
        return self._current_page

    def _update_page_count(self) -> None:
        """Update total page count based on ROM size and grid dimensions."""
        if len(self._rom_data) == 0:
            self._total_pages = 0
            return

        bytes_per_page = self._cols * self._rows * BYTES_PER_TILE
        self._total_pages = max(1, (len(self._rom_data) + bytes_per_page - 1) // bytes_per_page)

    def _page_to_offset(self, page: int) -> int:
        """Convert page number to ROM byte offset."""
        return page * self._cols * self._rows * BYTES_PER_TILE

    def _offset_to_page(self, offset: int) -> int:
        """Convert ROM byte offset to page number."""
        bytes_per_page = self._cols * self._rows * BYTES_PER_TILE
        return offset // bytes_per_page

    def _update_navigation_state(self) -> None:
        """Update navigation controls to reflect current state."""
        has_data = len(self._rom_data) > 0

        # Update page spinbox
        self._page_spinbox.blockSignals(True)
        self._page_spinbox.setMaximum(max(1, self._total_pages))
        self._page_spinbox.setValue(self._current_page + 1)  # 1-indexed display
        self._page_spinbox.blockSignals(False)

        # Update labels
        self._page_total_label.setText(f"/ {self._total_pages}")

        # Update offset display
        if has_data:
            offset = self._page_to_offset(self._current_page)
            end_offset = min(offset + self._cols * self._rows * BYTES_PER_TILE, len(self._rom_data))
            self._offset_label.setText(f"Offset: 0x{offset:06X} - 0x{end_offset:06X}")
            tiles_on_page = self._cols * self._rows
            self._status_label.setText(
                f"Grid: {self._cols}x{self._rows} ({tiles_on_page} tiles) | ROM size: {len(self._rom_data):,} bytes"
            )
        else:
            self._offset_label.setText("Offset: --")
            self._status_label.setText("No ROM data loaded")

        # Enable/disable buttons
        self._prev_btn.setEnabled(has_data and self._current_page > 0)
        self._next_btn.setEnabled(has_data and self._current_page < self._total_pages - 1)
        self._page_spinbox.setEnabled(has_data and self._total_pages > 1)

    def _request_page_render(self) -> None:
        """Request rendering of the current page."""
        if len(self._rom_data) == 0:
            self._graphics_view.clear_image()
            return

        offset = self._page_to_offset(self._current_page)

        # Check cache first
        cached_image = self._cache.get_page(offset, self._cols, self._rows, self._palette_hash)
        if cached_image is not None:
            logger.debug(f"Cache hit for page {self._current_page}")
            self._display_page(cached_image, offset)
            return

        # Cancel any running worker
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1000)

        # Start new render
        logger.debug(f"Rendering page {self._current_page} (offset 0x{offset:06X})")
        self._worker = PagedTileViewWorker(
            rom_data=self._rom_data,
            page_number=self._current_page,
            offset=offset,
            cols=self._cols,
            rows=self._rows,
            palette=self._palette,
        )
        self._worker.page_ready.connect(self._on_page_ready)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

        # Show loading state
        self._status_label.setText(f"Rendering page {self._current_page + 1}...")

    def _display_page(self, image: QImage, offset: int) -> None:
        """Display a rendered page image."""
        self._graphics_view.set_grid_info(self._cols, self._rows, offset)
        self._graphics_view.set_image(image)
        self._update_navigation_state()

    def _on_page_ready(self, page_number: int, image: QImage, offset: int, palette_hash: int) -> None:
        """Handle completed page render."""
        # Cache the result
        self._cache.put_page(offset, self._cols, self._rows, image, palette_hash)

        # Only display if this is still the current page
        if page_number == self._current_page:
            self._display_page(image, offset)
            logger.debug(f"Page {page_number} displayed: {image.width()}x{image.height()}")

    def _on_worker_error(self, message: str, exception: Exception) -> None:
        """Handle worker error."""
        logger.error(f"Page render error: {message}", exc_info=exception)
        self._status_label.setText(f"Render error: {message}")

    def _on_tile_clicked(self, offset: int) -> None:
        """Handle tile click from graphics view."""
        logger.debug(f"Tile clicked at offset 0x{offset:06X}")
        self.tile_clicked.emit(offset)

    def _go_prev_page(self) -> None:
        """Navigate to previous page."""
        if self._current_page > 0:
            self.go_to_page(self._current_page - 1)

    def _go_next_page(self) -> None:
        """Navigate to next page."""
        if self._current_page < self._total_pages - 1:
            self.go_to_page(self._current_page + 1)

    def _on_page_spinbox_changed(self, value: int) -> None:
        """Handle page spinbox value change."""
        page = value - 1  # Convert from 1-indexed display
        if 0 <= page < self._total_pages:
            self.go_to_page(page)

    def _on_grid_size_changed(self, index: int) -> None:
        """Handle grid size combo selection."""
        if 0 <= index < len(GRID_PRESETS):
            _, cols, rows = GRID_PRESETS[index]
            self.set_grid_dimensions(cols, rows)

    def _on_goto_offset(self) -> None:
        """Handle go-to-offset button click or Enter key in offset input."""
        text = self._offset_input.text().strip()
        if not text:
            return

        try:
            # Parse offset - handle hex (0x prefix or plain) and decimal
            if text.lower().startswith("0x"):
                offset = int(text, 16)
            elif all(c in "0123456789abcdefABCDEF" for c in text):
                # Looks like hex without prefix
                offset = int(text, 16)
            else:
                # Try decimal
                offset = int(text)

            # Validate range
            if offset < 0:
                self._status_label.setText(f"Invalid offset: {text} (negative)")
                return

            if len(self._rom_data) > 0 and offset >= len(self._rom_data):
                self._status_label.setText(f"Offset 0x{offset:X} exceeds ROM size (0x{len(self._rom_data):X})")
                return

            # Navigate to offset
            self.go_to_offset(offset)
            self._offset_input.clear()
            logger.debug(f"Jumped to offset 0x{offset:06X}")

        except ValueError:
            self._status_label.setText(f"Invalid offset format: {text}")

    def _reset_zoom(self) -> None:
        """Reset zoom to fit entire grid."""
        self._graphics_view.reset_zoom()

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts."""
        key = event.key()

        if key == Qt.Key.Key_PageUp:
            self._go_prev_page()
            event.accept()
        elif key == Qt.Key.Key_PageDown:
            self._go_next_page()
            event.accept()
        elif key == Qt.Key.Key_Home:
            self._reset_zoom()
            event.accept()
        else:
            super().keyPressEvent(event)

    def cleanup(self) -> None:
        """Clean up resources."""
        # Cancel any running worker
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)

        # Clear cache
        self._cache.clear()
