"""
Paged Tile View Widget for fast visual scanning of large ROM tile ranges.

Displays a configurable grid of tiles with paging navigation, optimized for
quickly browsing through ROM data to find sprites.

Supports two view modes:
- Raw: Display raw 4bpp tile data (fast, for finding compressed data patterns)
- Decompressed: Attempt HAL decompression at grid positions (slower, shows actual sprites)
"""

from __future__ import annotations

import json
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, override

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.rom_injector import ROMInjector


class PaletteFileData(TypedDict):
    """Type for palette file data."""

    name: str
    colors: list[list[int]]


class ViewMode(Enum):
    """View mode for the paged tile view."""

    RAW = auto()  # Display raw tile bytes
    DECOMPRESSED = auto()  # Attempt HAL decompression at each cell


from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.common.decompressed_sprite_cache import DecompressedSpriteCache
from ui.common.paged_tile_view_cache import PagedTileViewCache
from ui.common.spacing_constants import SPACING_SMALL, SPACING_STANDARD, SPACING_TINY
from ui.styles.theme import COLORS
from ui.workers.decompressed_page_worker import DecompressedPageWorker
from ui.workers.paged_tile_view_worker import (
    BYTES_PER_TILE,
    PagedTileViewWorker,
    _compute_palette_hash,
)

logger = get_logger(__name__)

# Grid preset configurations for RAW mode: (name, cols, rows)
GRID_PRESETS_RAW: list[tuple[str, int, int]] = [
    ("Small (20x20)", 20, 20),  # 400 tiles
    ("Medium (35x35)", 35, 35),  # 1225 tiles
    ("Large (50x50)", 50, 50),  # 2500 tiles (default)
    ("XL (100x100)", 100, 100),  # 10000 tiles
]

# Grid preset configurations for DECOMPRESSED mode: (name, cols, rows)
# Smaller grids because decompression is slower and cells are larger (32x32 vs 8x8)
GRID_PRESETS_DECOMP: list[tuple[str, int, int]] = [
    ("4x4 (16)", 4, 4),  # 16 cells
    ("6x6 (36)", 6, 6),  # 36 cells
    ("8x8 (64)", 8, 8),  # 64 cells (default)
    ("10x10 (100)", 10, 10),  # 100 cells
]

# Keep legacy reference for compatibility
GRID_PRESETS = GRID_PRESETS_RAW

DEFAULT_PRESET_INDEX_RAW = 2  # Large (50x50)
DEFAULT_PRESET_INDEX_DECOMP = 2  # 8x8 (64)
DEFAULT_PRESET_INDEX = DEFAULT_PRESET_INDEX_RAW

# Step size options for decompressed mode (bytes between cells)
STEP_SIZE_OPTIONS: list[tuple[str, int]] = [
    ("32 bytes", 32),
    ("128 bytes", 128),
    ("256 bytes", 256),  # default
    ("512 bytes", 512),
    ("1024 bytes", 1024),
]

DEFAULT_STEP_SIZE_INDEX = 2  # 256 bytes

# Default directory for palette files
DEFAULT_PALETTE_DIR = Path("output")


class TileGridGraphicsView(QGraphicsView):
    """
    Custom QGraphicsView that handles tile grid display with click detection.

    Emits tile_clicked when user clicks on a tile, providing the ROM offset.
    Supports both raw tile mode (8x8 cells) and decompressed mode (32x32 cells).
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

        # View mode configuration
        self._view_mode = ViewMode.RAW
        self._cell_size = 8  # 8 for raw (8x8 tile), 32 for decompressed
        self._step_size = BYTES_PER_TILE  # 32 for raw, configurable for decompressed

        # Highlight rectangle for go-to-offset
        self._highlight_rect: QGraphicsRectItem | None = None
        self._highlight_offset: int | None = None

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

    def set_grid_info(
        self,
        cols: int,
        rows: int,
        page_offset: int,
        view_mode: ViewMode = ViewMode.RAW,
        step_size: int = BYTES_PER_TILE,
    ) -> None:
        """Update grid dimensions and offset for click calculations.

        Args:
            cols: Number of columns in the grid
            rows: Number of rows in the grid
            page_offset: Starting ROM offset for this page
            view_mode: Current view mode (RAW or DECOMPRESSED)
            step_size: Byte step between cells (used for offset calculation)
        """
        self._cols = cols
        self._rows = rows
        self._page_offset = page_offset
        self._view_mode = view_mode
        self._step_size = step_size
        # Cell size: 8 pixels for raw tiles, 32 pixels for decompressed sprites
        self._cell_size = 8 if view_mode == ViewMode.RAW else 32

    def set_image(self, image: QImage) -> None:
        """Display an image in the view."""
        pixmap = QPixmap.fromImage(image)
        self._scene.clear()
        self._highlight_rect = None  # Cleared by scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        # Recreate highlight if we have a target offset on this page
        if self._highlight_offset is not None:
            self._create_highlight_at_offset(self._highlight_offset)

    def clear_image(self) -> None:
        """Clear the displayed image."""
        self._scene.clear()
        self._pixmap_item = None
        self._highlight_rect = None

    def set_highlight(self, offset: int | None) -> None:
        """
        Set or clear the highlight at a specific ROM offset.

        Args:
            offset: ROM offset to highlight, or None to clear
        """
        self._highlight_offset = offset

        # Remove existing highlight
        if self._highlight_rect is not None:
            self._scene.removeItem(self._highlight_rect)
            self._highlight_rect = None

        # Create new highlight if offset is set and on current page
        if offset is not None:
            self._create_highlight_at_offset(offset)

    def _create_highlight_at_offset(self, offset: int) -> None:
        """Create a highlight rectangle at the given ROM offset."""
        if self._pixmap_item is None:
            return

        # Check if offset is on the current page
        bytes_per_page = self._cols * self._rows * self._step_size
        if offset < self._page_offset or offset >= self._page_offset + bytes_per_page:
            return  # Offset not on this page

        # Calculate cell position within page
        offset_in_page = offset - self._page_offset
        cell_index = offset_in_page // self._step_size
        cell_x = cell_index % self._cols
        cell_y = cell_index // self._cols

        # Calculate pixel position based on cell size
        cell_size = self._cell_size
        half_cell = cell_size // 2
        cell_center_x = cell_x * cell_size + half_cell
        cell_center_y = cell_y * cell_size + half_cell

        # Highlight size scales with cell size (covers ~8 cells in raw, ~2 cells in decomp)
        highlight_size = cell_size * 8 if self._view_mode == ViewMode.RAW else cell_size * 2
        half_size = highlight_size // 2

        # Calculate highlight rectangle bounds, clamped to image bounds
        pixmap = self._pixmap_item.pixmap()
        x = max(0, cell_center_x - half_size)
        y = max(0, cell_center_y - half_size)
        width = min(highlight_size, pixmap.width() - x)
        height = min(highlight_size, pixmap.height() - y)

        # Create highlight rectangle
        self._highlight_rect = QGraphicsRectItem(x, y, width, height)

        # Style: bright cyan border, semi-transparent fill
        pen = QPen(QColor(0, 255, 255))  # Cyan
        pen.setWidth(2)
        pen.setCosmetic(True)  # Constant width regardless of zoom
        self._highlight_rect.setPen(pen)
        self._highlight_rect.setBrush(QColor(0, 255, 255, 40))  # Semi-transparent fill

        self._scene.addItem(self._highlight_rect)
        logger.debug(f"Highlight created at cell ({cell_x}, {cell_y}) for offset 0x{offset:06X}")

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse click to detect cell selection."""
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap_item is not None:
            # Map click to scene coordinates
            scene_pos = self.mapToScene(event.pos())
            # Check if within pixmap bounds
            pixmap = self._pixmap_item.pixmap()
            if 0 <= scene_pos.x() < pixmap.width() and 0 <= scene_pos.y() < pixmap.height():
                # Calculate cell coordinates based on cell size (8 for raw, 32 for decompressed)
                cell_x = int(scene_pos.x()) // self._cell_size
                cell_y = int(scene_pos.y()) // self._cell_size

                # Ensure within grid bounds
                if 0 <= cell_x < self._cols and 0 <= cell_y < self._rows:
                    # Calculate ROM offset using step size
                    cell_index = cell_y * self._cols + cell_x
                    rom_offset = self._page_offset + cell_index * self._step_size

                    logger.debug(f"Cell clicked: ({cell_x}, {cell_y}) -> offset 0x{rom_offset:06X}")
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

    Supports two view modes:
    - Raw: Display raw 4bpp tile data (fast, for finding compressed data patterns)
    - Decompressed: Attempt HAL decompression at grid positions (slower, shows actual sprites)

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
        self._palette_enabled: bool = True  # Whether to use palette (vs grayscale)

        # ROM injector for decompression (set via set_rom_injector)
        self._rom_injector: ROMInjector | None = None

        # Available palettes: dict of name -> palette (list of 16 RGB lists)
        # "Grayscale" always available; others added via add_palette_option()
        self._palette_options: dict[str, list[list[int]] | None] = {"Grayscale": None}
        self._selected_palette_name: str = "Grayscale"

        # Track user-loaded palettes (vs built-in like Grayscale and Kirby palettes)
        self._user_palettes: set[str] = set()
        self._last_palette_dir: Path = DEFAULT_PALETTE_DIR

        # View mode configuration
        self._view_mode = ViewMode.RAW
        self._step_size = STEP_SIZE_OPTIONS[DEFAULT_STEP_SIZE_INDEX][1]  # 256 bytes default

        # Grid configuration (mode-dependent)
        self._cols = GRID_PRESETS_RAW[DEFAULT_PRESET_INDEX_RAW][1]
        self._rows = GRID_PRESETS_RAW[DEFAULT_PRESET_INDEX_RAW][2]
        self._current_page = 0
        self._total_pages = 0
        self._decomp_base_offset = 0  # Custom start offset for decompressed mode

        # Worker and cache (raw mode)
        self._worker: PagedTileViewWorker | None = None
        self._cache = PagedTileViewCache()

        # Worker and cache (decompressed mode)
        self._decomp_worker: DecompressedPageWorker | None = None
        self._decomp_cache = DecompressedSpriteCache()

        # Prefetch workers (decompressed mode)
        self._prefetch_workers: list[DecompressedPageWorker] = []
        self._is_prefetching = False

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
        """Create the navigation bar with page controls (two rows)."""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS["panel_background"]};
                border-radius: 4px;
                padding: {SPACING_TINY}px;
            }}
        """)

        # Main vertical layout for two rows
        main_layout = QVBoxLayout(frame)
        main_layout.setContentsMargins(SPACING_SMALL, SPACING_TINY, SPACING_SMALL, SPACING_TINY)
        main_layout.setSpacing(SPACING_TINY)

        # === Row 1: View settings and page navigation ===
        row1 = QHBoxLayout()
        row1.setSpacing(SPACING_STANDARD)

        # Grid size selector
        row1.addWidget(QLabel("Grid:"))
        self._grid_combo = QComboBox()
        self._populate_grid_combo()  # Populate based on current mode
        self._grid_combo.currentIndexChanged.connect(self._on_grid_size_changed)
        row1.addWidget(self._grid_combo)

        # View mode toggle (Raw / Decomp)
        row1.addWidget(QLabel("Mode:"))
        self._mode_group = QButtonGroup(self)
        self._raw_mode_btn = QRadioButton("Raw")
        self._raw_mode_btn.setToolTip("Show raw tile bytes (fast)")
        self._raw_mode_btn.setChecked(True)
        self._decomp_mode_btn = QRadioButton("Decomp")
        self._decomp_mode_btn.setToolTip("Attempt HAL decompression at each cell (slower)")
        self._mode_group.addButton(self._raw_mode_btn, 0)
        self._mode_group.addButton(self._decomp_mode_btn, 1)
        self._mode_group.idClicked.connect(self._on_view_mode_changed)
        row1.addWidget(self._raw_mode_btn)
        row1.addWidget(self._decomp_mode_btn)

        # Step size selector (visible only in decomp mode)
        self._step_label = QLabel("Step:")
        self._step_label.setVisible(False)
        row1.addWidget(self._step_label)
        self._step_combo = QComboBox()
        for name, _ in STEP_SIZE_OPTIONS:
            self._step_combo.addItem(name)
        self._step_combo.setCurrentIndex(DEFAULT_STEP_SIZE_INDEX)
        self._step_combo.currentIndexChanged.connect(self._on_step_size_changed)
        self._step_combo.setVisible(False)
        self._step_combo.setToolTip("Byte offset between grid cells")
        row1.addWidget(self._step_combo)

        # Prefetch button (visible only in decomp mode)
        self._prefetch_btn = QPushButton("\u21bb Prefetch")  # Clockwise arrow
        self._prefetch_btn.setToolTip("Cache nearby pages (\u00b12) in background")
        self._prefetch_btn.clicked.connect(self._on_prefetch_clicked)
        self._prefetch_btn.setVisible(False)
        row1.addWidget(self._prefetch_btn)

        # Separator
        row1.addStretch()

        # Page navigation
        row1.addWidget(QLabel("Page:"))

        self._prev_btn = QPushButton("<")
        self._prev_btn.setFixedWidth(30)
        self._prev_btn.setToolTip("Previous page (Page Up)")
        self._prev_btn.clicked.connect(self._go_prev_page)
        row1.addWidget(self._prev_btn)

        self._page_spinbox = QSpinBox()
        self._page_spinbox.setMinimum(1)
        self._page_spinbox.setMaximum(1)
        self._page_spinbox.setFixedWidth(70)
        self._page_spinbox.valueChanged.connect(self._on_page_spinbox_changed)
        row1.addWidget(self._page_spinbox)

        self._page_total_label = QLabel("/ 0")
        row1.addWidget(self._page_total_label)

        self._next_btn = QPushButton(">")
        self._next_btn.setFixedWidth(30)
        self._next_btn.setToolTip("Next page (Page Down)")
        self._next_btn.clicked.connect(self._go_next_page)
        row1.addWidget(self._next_btn)

        main_layout.addLayout(row1)

        # === Row 2: Go to offset, zoom, palette controls ===
        row2 = QHBoxLayout()
        row2.setSpacing(SPACING_STANDARD)

        # Go to offset input
        row2.addWidget(QLabel("Go to:"))
        self._offset_input = QLineEdit()
        self._offset_input.setPlaceholderText("0x294D0A")
        self._offset_input.setFixedWidth(100)
        self._offset_input.setToolTip("Enter offset (hex with 0x prefix, or decimal)")
        self._offset_input.returnPressed.connect(self._on_goto_offset)
        row2.addWidget(self._offset_input)

        self._goto_btn = QPushButton("Go")
        self._goto_btn.setFixedWidth(40)
        self._goto_btn.setToolTip("Jump to offset (Enter)")
        self._goto_btn.clicked.connect(self._on_goto_offset)
        row2.addWidget(self._goto_btn)

        # Zoom controls
        self._zoom_fit_btn = QPushButton("Fit")
        self._zoom_fit_btn.setToolTip("Reset zoom to fit (Home)")
        self._zoom_fit_btn.clicked.connect(self._reset_zoom)
        row2.addWidget(self._zoom_fit_btn)

        # Separator
        row2.addStretch()

        # Palette toggle checkbox
        self._palette_checkbox = QCheckBox("Palette")
        self._palette_checkbox.setChecked(True)
        self._palette_checkbox.setToolTip("Show tiles with palette colors (uncheck for grayscale)")
        self._palette_checkbox.toggled.connect(self._on_palette_toggled)
        row2.addWidget(self._palette_checkbox)

        # Palette selector dropdown
        self._palette_combo = QComboBox()
        self._palette_combo.addItem("Grayscale")
        self._palette_combo.setToolTip("Select palette for tile rendering")
        self._palette_combo.setMinimumWidth(100)
        self._palette_combo.currentTextChanged.connect(self._on_palette_selected)
        row2.addWidget(self._palette_combo)

        # Palette management menu button
        self._palette_menu_btn = QToolButton()
        self._palette_menu_btn.setText("...")
        self._palette_menu_btn.setToolTip("Palette management: Load, Rename, Delete")
        self._palette_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._palette_menu = QMenu(self._palette_menu_btn)
        self._action_load = self._palette_menu.addAction("Load Palette...")
        self._action_load.triggered.connect(self._on_load_palette)
        self._palette_menu.addSeparator()
        self._action_rename = self._palette_menu.addAction("Rename...")
        self._action_rename.triggered.connect(self._on_rename_palette)
        self._action_delete = self._palette_menu.addAction("Delete")
        self._action_delete.triggered.connect(self._on_delete_palette)
        self._palette_menu_btn.setMenu(self._palette_menu)
        row2.addWidget(self._palette_menu_btn)
        self._update_palette_menu_state()

        # Separator
        row2.addStretch()

        # Offset display
        self._offset_label = QLabel("Offset: --")
        self._offset_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        row2.addWidget(self._offset_label)

        main_layout.addLayout(row2)

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

    def set_palette(self, palette: list[list[int]] | None, name: str = "Custom") -> None:
        """
        Set the palette for tile rendering.

        Args:
            palette: List of 16 RGB color lists, or None for grayscale
            name: Display name for the palette in the dropdown (default: "Custom")
        """
        if palette is not None:
            # Add/update as a named palette option
            self.add_palette_option(name, palette)

            # Select it in the dropdown (this will trigger _on_palette_selected)
            # Block signals to avoid double-rendering
            self._palette_combo.blockSignals(True)
            index = self._palette_combo.findText(name)
            if index >= 0:
                self._palette_combo.setCurrentIndex(index)
            self._palette_combo.blockSignals(False)

            # Update internal state
            self._selected_palette_name = name
            self._palette = palette
            self._palette_hash = _compute_palette_hash(palette)
            self._palette_checkbox.setEnabled(True)
            self._palette_checkbox.setChecked(True)
            self._palette_enabled = True
        else:
            # Select Grayscale
            self._palette_combo.blockSignals(True)
            self._palette_combo.setCurrentIndex(0)  # Grayscale is always first
            self._palette_combo.blockSignals(False)

            self._selected_palette_name = "Grayscale"
            self._palette = None
            self._palette_hash = 0
            self._palette_checkbox.setEnabled(False)
            self._palette_checkbox.setChecked(False)
            self._palette_enabled = False

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
        Navigate to a specific ROM offset.

        In raw mode: Navigates to the page containing the offset.
        In decompressed mode: Sets the offset as cell 0 (page 0).

        Args:
            offset: ROM byte offset
        """
        if len(self._rom_data) == 0:
            return

        # Clamp to valid range
        offset = max(0, min(offset, len(self._rom_data) - 1))

        if self._view_mode == ViewMode.DECOMPRESSED:
            # In decompressed mode, set the offset as the base (cell 0 of page 0)
            self._decomp_base_offset = offset
            self._update_page_count()
            self.go_to_page(0)
            logger.debug(f"Decompressed mode: set base offset to 0x{offset:06X}")
        else:
            # In raw mode, navigate to the page containing the offset
            page = offset // self._bytes_per_page
            self.go_to_page(page)

    def get_current_offset(self) -> int:
        """Get the starting offset of the current page."""
        return self._page_to_offset(self._current_page)

    def get_current_page(self) -> int:
        """Get the current page number."""
        return self._current_page

    @property
    def _bytes_per_cell(self) -> int:
        """Get bytes per cell based on current view mode."""
        if self._view_mode == ViewMode.DECOMPRESSED:
            return self._step_size
        return BYTES_PER_TILE

    @property
    def _bytes_per_page(self) -> int:
        """Get bytes per page based on current grid and view mode."""
        return self._cols * self._rows * self._bytes_per_cell

    def _update_page_count(self) -> None:
        """Update total page count based on ROM size and grid dimensions."""
        if len(self._rom_data) == 0:
            self._total_pages = 0
            return

        if self._view_mode == ViewMode.DECOMPRESSED:
            # In decompressed mode, count pages from the base offset
            remaining = len(self._rom_data) - self._decomp_base_offset
            self._total_pages = max(1, (remaining + self._bytes_per_page - 1) // self._bytes_per_page)
        else:
            self._total_pages = max(1, (len(self._rom_data) + self._bytes_per_page - 1) // self._bytes_per_page)

    def _page_to_offset(self, page: int) -> int:
        """Convert page number to ROM byte offset."""
        if self._view_mode == ViewMode.DECOMPRESSED:
            # In decompressed mode, use custom base offset so user-specified
            # offsets appear at cell 0
            return self._decomp_base_offset + page * self._bytes_per_page
        return page * self._bytes_per_page

    def _offset_to_page(self, offset: int) -> int:
        """Convert ROM byte offset to page number."""
        if self._view_mode == ViewMode.DECOMPRESSED:
            return (offset - self._decomp_base_offset) // self._bytes_per_page
        return offset // self._bytes_per_page

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
            end_offset = min(offset + self._bytes_per_page, len(self._rom_data))
            self._offset_label.setText(f"Offset: 0x{offset:06X} - 0x{end_offset:06X}")
            cells_on_page = self._cols * self._rows
            mode_str = "decomp" if self._view_mode == ViewMode.DECOMPRESSED else "raw"
            step_info = f", step {self._step_size}B" if self._view_mode == ViewMode.DECOMPRESSED else ""
            self._status_label.setText(
                f"Grid: {self._cols}x{self._rows} ({cells_on_page} cells, {mode_str}{step_info}) | "
                f"ROM size: {len(self._rom_data):,} bytes"
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

        # Get effective palette (None for grayscale when disabled)
        effective_palette = self._palette if self._palette_enabled else None
        effective_hash = self._palette_hash if self._palette_enabled else 0

        # Route to appropriate renderer based on mode
        if self._view_mode == ViewMode.DECOMPRESSED:
            self._request_decompressed_page_render(offset, effective_palette, effective_hash)
        else:
            self._request_raw_page_render(offset, effective_palette, effective_hash)

    def _request_raw_page_render(self, offset: int, palette: list[list[int]] | None, palette_hash: int) -> None:
        """Request rendering of the current page in raw tile mode."""
        # Check cache first
        cached_image = self._cache.get_page(offset, self._cols, self._rows, palette_hash)
        if cached_image is not None:
            logger.debug(f"Cache hit for raw page {self._current_page}")
            self._display_page(cached_image, offset)
            return

        # Cancel any running worker
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1000)

        # Start new render
        logger.debug(f"Rendering raw page {self._current_page} (offset 0x{offset:06X})")
        self._worker = PagedTileViewWorker(
            rom_data=self._rom_data,
            page_number=self._current_page,
            offset=offset,
            cols=self._cols,
            rows=self._rows,
            palette=palette,
        )
        self._worker.page_ready.connect(self._on_page_ready)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

        # Show loading state
        self._status_label.setText(f"Rendering page {self._current_page + 1}...")

    def _request_decompressed_page_render(
        self, offset: int, palette: list[list[int]] | None, palette_hash: int
    ) -> None:
        """Request rendering of the current page in decompressed sprite mode."""
        # Check if ROM injector is available
        if self._rom_injector is None:
            self._status_label.setText("Decompressed mode requires ROM extractor")
            logger.warning("Cannot render decompressed page: ROM injector not set")
            return

        # Check cache first (decompressed cache uses step_size in key)
        cached_image = self._decomp_cache.get_page(offset, self._cols, self._rows, self._step_size, palette_hash)
        if cached_image is not None:
            logger.debug(f"Cache hit for decompressed page {self._current_page}")
            self._display_page(cached_image, offset)
            return

        # Cancel any running decompressed worker
        if self._decomp_worker is not None and self._decomp_worker.isRunning():
            self._decomp_worker.cancel()
            self._decomp_worker.wait(1000)

        # Start new render
        logger.debug(
            f"Rendering decompressed page {self._current_page} (offset 0x{offset:06X}, step={self._step_size})"
        )
        self._decomp_worker = DecompressedPageWorker(
            rom_data=self._rom_data,
            rom_injector=self._rom_injector,
            page_number=self._current_page,
            offset=offset,
            cols=self._cols,
            rows=self._rows,
            step_size=self._step_size,
            palette=palette,
        )
        self._decomp_worker.page_ready.connect(self._on_decomp_page_ready)
        self._decomp_worker.error.connect(self._on_worker_error)
        self._decomp_worker.start()

        # Show loading state
        self._status_label.setText(f"Decompressing page {self._current_page + 1}...")

    def _on_decomp_page_ready(self, page_number: int, image: QImage, offset: int, palette_hash: int) -> None:
        """Handle completed decompressed page render."""
        # Cache the result with step_size
        self._decomp_cache.put_page(offset, self._cols, self._rows, self._step_size, image, palette_hash)

        # Only display if this is still the current page
        if page_number == self._current_page:
            self._display_page(image, offset)
            logger.debug(f"Decompressed page {page_number} displayed: {image.width()}x{image.height()}")

    def _display_page(self, image: QImage, offset: int) -> None:
        """Display a rendered page image."""
        self._graphics_view.set_grid_info(self._cols, self._rows, offset, self._view_mode, self._bytes_per_cell)
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
        # Clear highlight when user clicks a tile
        self._graphics_view.set_highlight(None)
        logger.debug(f"Tile clicked at offset 0x{offset:06X}")
        self.tile_clicked.emit(offset)

    def _go_prev_page(self) -> None:
        """Navigate to previous page."""
        if self._current_page > 0:
            self._graphics_view.set_highlight(None)  # Clear highlight on page change
            self.go_to_page(self._current_page - 1)

    def _go_next_page(self) -> None:
        """Navigate to next page."""
        if self._current_page < self._total_pages - 1:
            self._graphics_view.set_highlight(None)  # Clear highlight on page change
            self.go_to_page(self._current_page + 1)

    def _on_page_spinbox_changed(self, value: int) -> None:
        """Handle page spinbox value change."""
        page = value - 1  # Convert from 1-indexed display
        if 0 <= page < self._total_pages:
            self._graphics_view.set_highlight(None)  # Clear highlight on page change
            self.go_to_page(page)

    def _on_grid_size_changed(self, index: int) -> None:
        """Handle grid size combo selection."""
        presets = GRID_PRESETS_DECOMP if self._view_mode == ViewMode.DECOMPRESSED else GRID_PRESETS_RAW
        if 0 <= index < len(presets):
            _, cols, rows = presets[index]
            self.set_grid_dimensions(cols, rows)

    def _populate_grid_combo(self) -> None:
        """Populate grid combo based on current view mode."""
        presets = GRID_PRESETS_DECOMP if self._view_mode == ViewMode.DECOMPRESSED else GRID_PRESETS_RAW
        default_index = (
            DEFAULT_PRESET_INDEX_DECOMP if self._view_mode == ViewMode.DECOMPRESSED else DEFAULT_PRESET_INDEX_RAW
        )

        self._grid_combo.blockSignals(True)
        self._grid_combo.clear()
        for name, _, _ in presets:
            self._grid_combo.addItem(name)
        self._grid_combo.setCurrentIndex(default_index)
        self._grid_combo.blockSignals(False)

    def _on_view_mode_changed(self, button_id: int) -> None:
        """Handle view mode toggle."""
        new_mode = ViewMode.DECOMPRESSED if button_id == 1 else ViewMode.RAW
        if new_mode == self._view_mode:
            return

        logger.debug(f"View mode changed to: {new_mode.name}")
        self._view_mode = new_mode

        # Reset decomp base offset when switching modes
        self._decomp_base_offset = 0

        # Show/hide decomp-specific controls
        is_decomp = new_mode == ViewMode.DECOMPRESSED
        self._step_label.setVisible(is_decomp)
        self._step_combo.setVisible(is_decomp)
        self._prefetch_btn.setVisible(is_decomp)

        # Update grid presets for new mode
        self._populate_grid_combo()

        # Apply new grid dimensions
        presets = GRID_PRESETS_DECOMP if is_decomp else GRID_PRESETS_RAW
        default_index = DEFAULT_PRESET_INDEX_DECOMP if is_decomp else DEFAULT_PRESET_INDEX_RAW
        _, cols, rows = presets[default_index]
        self._cols = cols
        self._rows = rows

        # Recalculate page count and clamp current page
        self._update_page_count()
        if self._current_page >= self._total_pages:
            self._current_page = max(0, self._total_pages - 1)

        # Re-render with new mode
        self._update_navigation_state()
        self._request_page_render()

    def _on_step_size_changed(self, index: int) -> None:
        """Handle step size combo selection."""
        if 0 <= index < len(STEP_SIZE_OPTIONS):
            _, step_size = STEP_SIZE_OPTIONS[index]
            if step_size == self._step_size:
                return

            logger.debug(f"Step size changed to: {step_size}")
            self._step_size = step_size

            # Recalculate page count and clamp current page
            self._update_page_count()
            if self._current_page >= self._total_pages:
                self._current_page = max(0, self._total_pages - 1)

            # Re-render with new step size
            self._update_navigation_state()
            self._request_page_render()

    def _on_prefetch_clicked(self) -> None:
        """Handle prefetch button click - cache nearby pages in background."""
        if self._is_prefetching:
            self._status_label.setText("Prefetch already in progress...")
            return

        if self._rom_injector is None:
            self._status_label.setText("Prefetch requires ROM extractor")
            return

        # Determine pages to prefetch (±2 from current)
        pages_to_prefetch = []
        for delta in [-2, -1, 1, 2]:
            page = self._current_page + delta
            if 0 <= page < self._total_pages:
                # Check if already cached
                offset = self._page_to_offset(page)
                effective_hash = self._palette_hash if self._palette_enabled else 0
                cached = self._decomp_cache.get_page(offset, self._cols, self._rows, self._step_size, effective_hash)
                if cached is None:
                    pages_to_prefetch.append(page)

        if not pages_to_prefetch:
            self._status_label.setText("Nearby pages already cached")
            return

        logger.debug(f"Prefetching pages: {pages_to_prefetch}")
        self._is_prefetching = True
        self._prefetch_btn.setEnabled(False)
        self._status_label.setText(f"Prefetching {len(pages_to_prefetch)} pages...")

        # Cancel any existing prefetch workers
        for worker in self._prefetch_workers:
            if worker.isRunning():
                worker.cancel()
                worker.wait(500)
        self._prefetch_workers.clear()

        # Start prefetch workers
        effective_palette = self._palette if self._palette_enabled else None
        for page in pages_to_prefetch:
            offset = self._page_to_offset(page)
            worker = DecompressedPageWorker(
                rom_data=self._rom_data,
                rom_injector=self._rom_injector,
                page_number=page,
                offset=offset,
                cols=self._cols,
                rows=self._rows,
                step_size=self._step_size,
                palette=effective_palette,
            )
            worker.page_ready.connect(self._on_prefetch_page_ready)
            worker.operation_finished.connect(self._on_prefetch_worker_finished)
            self._prefetch_workers.append(worker)
            worker.start()

    def _on_prefetch_page_ready(self, page_number: int, image: QImage, offset: int, palette_hash: int) -> None:
        """Handle completed prefetch page render."""
        # Cache the result
        self._decomp_cache.put_page(offset, self._cols, self._rows, self._step_size, image, palette_hash)
        logger.debug(f"Prefetched page {page_number} cached")

    def _on_prefetch_worker_finished(self, success: bool, message: str) -> None:
        """Handle prefetch worker completion."""
        # Check if all prefetch workers are done
        all_done = all(not w.isRunning() for w in self._prefetch_workers)
        if all_done:
            self._is_prefetching = False
            self._prefetch_btn.setEnabled(True)
            self._prefetch_workers.clear()
            self._status_label.setText("Prefetch complete")
            logger.debug("All prefetch workers finished")

    def set_rom_injector(self, rom_injector: ROMInjector | None) -> None:
        """Set the ROM injector for decompression mode.

        Args:
            rom_injector: ROMInjector instance, or None to disable decompression mode
        """
        self._rom_injector = rom_injector
        # Enable/disable decomp mode button based on availability
        self._decomp_mode_btn.setEnabled(rom_injector is not None)
        if rom_injector is None and self._view_mode == ViewMode.DECOMPRESSED:
            # Switch back to raw mode if injector is removed
            self._raw_mode_btn.setChecked(True)
            self._on_view_mode_changed(0)

    def _on_palette_toggled(self, checked: bool) -> None:
        """Handle palette toggle checkbox state change."""
        self._palette_enabled = checked
        logger.debug(f"Palette preview {'enabled' if checked else 'disabled'}")
        # Re-render current page with new palette setting
        self._request_page_render()

    def _on_palette_selected(self, name: str) -> None:
        """Handle palette dropdown selection."""
        if not name or name == self._selected_palette_name:
            return

        self._selected_palette_name = name
        palette = self._palette_options.get(name)

        logger.debug(f"Palette selected: {name}")

        # Update the internal palette and re-render
        self._palette = palette
        self._palette_hash = _compute_palette_hash(palette)

        # Update checkbox state based on whether a non-grayscale palette is selected
        has_palette = palette is not None
        self._palette_checkbox.setEnabled(has_palette)
        if has_palette:
            self._palette_checkbox.setChecked(True)
            self._palette_enabled = True
        else:
            self._palette_checkbox.setChecked(False)
            self._palette_enabled = False

        self._request_page_render()
        self._update_palette_menu_state()

    def _update_palette_menu_state(self) -> None:
        """Update palette menu actions based on current selection."""
        # Rename and Delete are only available for user-loaded palettes
        current_name = self._selected_palette_name
        is_user_palette = current_name in self._user_palettes
        self._action_rename.setEnabled(is_user_palette)
        self._action_delete.setEnabled(is_user_palette)

    def _on_load_palette(self) -> None:
        """Handle Load Palette action - open file dialog to load .pal.json files."""
        # Determine default directory
        start_dir = str(self._last_palette_dir)
        if not Path(start_dir).exists():
            # Try to find the output folder relative to the project
            project_output = Path(__file__).parent.parent.parent / "output"
            if project_output.exists():
                start_dir = str(project_output)
            else:
                start_dir = str(Path.home())

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Load Palette Files",
            start_dir,
            "Palette Files (*.pal.json);;JSON Files (*.json);;All Files (*)",
        )

        if not file_paths:
            return

        # Remember the directory for next time
        self._last_palette_dir = Path(file_paths[0]).parent

        loaded_count = 0
        for file_path in file_paths:
            try:
                palette_data = self._load_palette_file(Path(file_path))
                if palette_data:
                    name = palette_data["name"]
                    colors = palette_data["colors"]

                    # Add to options and mark as user palette
                    self.add_palette_option(name, colors, is_user_palette=True)
                    loaded_count += 1
                    logger.info(f"Loaded palette: {name} from {file_path}")

            except Exception as e:
                logger.error(f"Failed to load palette from {file_path}: {e}")
                QMessageBox.warning(
                    self,
                    "Load Failed",
                    f"Failed to load palette from:\n{file_path}\n\nError: {e}",
                )

        if loaded_count > 0:
            # Select the last loaded palette
            self._status_label.setText(f"Loaded {loaded_count} palette(s)")

    def _load_palette_file(self, file_path: Path) -> PaletteFileData | None:
        """
        Load a palette from a .pal.json file.

        Args:
            file_path: Path to the palette file

        Returns:
            PaletteFileData with "name" and "colors" keys, or None on failure
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            # Validate structure
            if "colors" not in data:
                raise ValueError("Missing 'colors' field")

            colors = data["colors"]
            if not isinstance(colors, list) or len(colors) < 1:
                raise ValueError("'colors' must be a non-empty list")

            # Validate and normalize colors
            normalized_colors: list[list[int]] = []
            for color in colors:
                if (isinstance(color, list | tuple)) and len(color) >= 3:
                    normalized_colors.append([int(color[0]), int(color[1]), int(color[2])])
                else:
                    raise ValueError(f"Invalid color format: {color}")

            # Get name from file or generate from filename
            name = data.get("name", file_path.stem)
            if not name:
                name = file_path.stem

            return PaletteFileData(name=str(name), colors=normalized_colors)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

    def _on_rename_palette(self) -> None:
        """Handle Rename action - rename the currently selected user palette."""
        current_name = self._selected_palette_name

        if current_name not in self._user_palettes:
            QMessageBox.warning(
                self,
                "Cannot Rename",
                "Only user-loaded palettes can be renamed.",
            )
            return

        # Show input dialog
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Palette",
            "Enter new name:",
            text=current_name,
        )

        if not ok or not new_name or new_name == current_name:
            return

        # Check for name conflict
        if new_name in self._palette_options and new_name != current_name:
            QMessageBox.warning(
                self,
                "Name Conflict",
                f"A palette named '{new_name}' already exists.",
            )
            return

        # Rename the palette
        palette = self._palette_options.pop(current_name)
        self._palette_options[new_name] = palette
        self._user_palettes.discard(current_name)
        self._user_palettes.add(new_name)

        # Update the combo box
        index = self._palette_combo.findText(current_name)
        if index >= 0:
            self._palette_combo.setItemText(index, new_name)

        self._selected_palette_name = new_name
        logger.info(f"Renamed palette: {current_name} -> {new_name}")
        self._status_label.setText(f"Renamed palette to '{new_name}'")

    def _on_delete_palette(self) -> None:
        """Handle Delete action - remove the currently selected user palette."""
        current_name = self._selected_palette_name

        if current_name not in self._user_palettes:
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "Only user-loaded palettes can be deleted.",
            )
            return

        # Confirm deletion
        result = QMessageBox.question(
            self,
            "Delete Palette",
            f"Delete palette '{current_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        # Remove from data structures
        self._palette_options.pop(current_name, None)
        self._user_palettes.discard(current_name)

        # Remove from combo box
        index = self._palette_combo.findText(current_name)
        if index >= 0:
            self._palette_combo.blockSignals(True)
            self._palette_combo.removeItem(index)
            self._palette_combo.blockSignals(False)

        # Select Grayscale
        self._palette_combo.setCurrentIndex(0)
        logger.info(f"Deleted palette: {current_name}")
        self._status_label.setText(f"Deleted palette '{current_name}'")

    def add_palette_option(self, name: str, palette: list[list[int]], *, is_user_palette: bool = False) -> None:
        """
        Add a palette option to the dropdown.

        Args:
            name: Display name for the palette
            palette: List of 16 RGB color lists
            is_user_palette: True if this is a user-loaded palette (can be renamed/deleted)
        """
        if name in self._palette_options:
            # Update existing palette
            self._palette_options[name] = palette
            logger.debug(f"Updated palette option: {name}")
        else:
            self._palette_options[name] = palette
            self._palette_combo.addItem(name)
            logger.debug(f"Added palette option: {name}")

        # Track user palettes
        if is_user_palette:
            self._user_palettes.add(name)

    def clear_palette_options(self) -> None:
        """Clear all palette options except Grayscale."""
        # Block signals during clear to avoid triggering re-renders
        self._palette_combo.blockSignals(True)

        # Keep only Grayscale
        self._palette_options = {"Grayscale": None}
        self._user_palettes.clear()
        self._palette_combo.clear()
        self._palette_combo.addItem("Grayscale")
        self._selected_palette_name = "Grayscale"

        # Update internal state
        self._palette = None
        self._palette_hash = 0
        self._palette_checkbox.setEnabled(False)
        self._palette_checkbox.setChecked(False)
        self._palette_enabled = False

        self._palette_combo.blockSignals(False)
        self._update_palette_menu_state()
        logger.debug("Cleared all palette options")

    def get_user_palettes(self) -> dict[str, list[list[int]]]:
        """
        Get all user-loaded palettes for persistence.

        Returns:
            Dict mapping palette names to color lists (only user palettes)
        """
        result: dict[str, list[list[int]]] = {}
        for name in self._user_palettes:
            palette = self._palette_options.get(name)
            if palette is not None:
                result[name] = palette
        return result

    def load_user_palettes(self, palettes: dict[str, list[list[int]]]) -> None:
        """
        Load user palettes from saved data.

        Args:
            palettes: Dict mapping palette names to color lists
        """
        for name, colors in palettes.items():
            self.add_palette_option(name, colors, is_user_palette=True)
        logger.debug(f"Loaded {len(palettes)} user palettes")

    def select_palette(self, name: str) -> bool:
        """
        Select a palette by name.

        Args:
            name: Name of the palette to select

        Returns:
            True if palette was found and selected, False otherwise
        """
        if name not in self._palette_options:
            logger.warning(f"Palette not found: {name}")
            return False

        index = self._palette_combo.findText(name)
        if index >= 0:
            self._palette_combo.setCurrentIndex(index)
            return True
        return False

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

            # Navigate to offset and highlight
            self._graphics_view.set_highlight(offset)
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
