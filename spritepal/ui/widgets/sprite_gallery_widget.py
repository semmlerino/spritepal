"""
Sprite gallery widget for displaying multiple sprite thumbnails.
Provides efficient virtual scrolling using Model/View architecture.
"""
from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import (
    MEDIUM_WIDTH,
    SPACING_LARGE,
    SPACING_TINY,
)
from ui.delegates.sprite_gallery_delegate import SpriteGalleryDelegate
from ui.models.sprite_gallery_model import SpriteGalleryModel
from ui.styles.theme import COLORS
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Gallery layout constants
VIEWPORT_MARGIN = 20
THUMBNAIL_REQUEST_BATCH_SIZE = 50  # Request thumbnails in batches
VIEWPORT_BUFFER_ROWS = 2  # Load extra rows above/below viewport

class SpriteGalleryWidget(QWidget):
    """Widget displaying a gallery of sprite thumbnails using virtual scrolling."""

    # Signals
    sprite_selected = Signal(int)  # Emits offset when sprite selected
    sprite_double_clicked = Signal(int)  # Emits offset on double-click
    selection_changed = Signal(list)  # Emits list of selected offsets
    thumbnail_request = Signal(int, int)  # Request thumbnail (offset, priority)

    def __init__(self, parent: QWidget | None = None):
        """
        Initialize the sprite gallery widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Display settings
        self.thumbnail_size = 256  # Default to actually visible size
        self.columns = 4  # Default columns for better visibility
        self.spacing = 16  # Proper visual separation

        # Model/View components
        self.model: SpriteGalleryModel | None = None
        self.delegate: SpriteGalleryDelegate | None = None
        self.list_view: QListView | None = None

        # Performance - explicit parent ensures cleanup with widget
        self.viewport_timer = QTimer(self)
        self.viewport_timer.timeout.connect(self._update_visible_thumbnails)
        self.viewport_timer.setInterval(100)
        self.viewport_timer.setSingleShot(True)

        # UI components
        self.controls_widget: QWidget | None = None

        # Track last visible range to avoid redundant requests
        self._last_visible_range = (-1, -1)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the gallery UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACING_TINY, SPACING_TINY, SPACING_TINY, SPACING_TINY)
        layout.setSpacing(SPACING_TINY)

        # Controls bar
        self.controls_widget = self._create_controls()
        layout.addWidget(self.controls_widget)

        # Create model
        self.model = SpriteGalleryModel(self)
        self.model.selection_changed.connect(self._on_model_selection_changed)
        self.model.thumbnail_needed.connect(self._on_thumbnail_needed)

        # Create delegate
        self.delegate = SpriteGalleryDelegate(self)
        self.delegate.set_thumbnail_size(self.thumbnail_size)

        # Create list view with grid layout
        self.list_view = QListView(self)
        if self.list_view:
            self.list_view.setModel(self.model)
            self.list_view.setItemDelegate(self.delegate)

            # Configure for grid layout
            self.list_view.setViewMode(QListView.ViewMode.IconMode)
            self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
            self.list_view.setLayoutMode(QListView.LayoutMode.Batched)
            self.list_view.setBatchSize(20)  # Process items in batches for performance
            self.list_view.setUniformItemSizes(True)  # All items same size for performance
            self.list_view.setSpacing(self.spacing)

            # Selection mode
            self.list_view.setSelectionMode(QListView.SelectionMode.NoSelection)  # We handle selection in delegate

            # Performance optimizations
            self.list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
            self.list_view.setHorizontalScrollMode(QListView.ScrollMode.ScrollPerPixel)

        # Connect scroll events to trigger thumbnail loading
        if self.list_view:
            scrollbar = self.list_view.verticalScrollBar()
            if scrollbar:
                scrollbar.valueChanged.connect(self._on_scroll)

            # Connect click events
            self.list_view.clicked.connect(self._on_item_clicked)
            self.list_view.doubleClicked.connect(self._on_item_double_clicked)

        layout.addWidget(self.list_view, 1)  # Give it stretch

        self.setLayout(layout)

        # Style with proper dark theme colors
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS["preview_background"]};
                color: {COLORS["text_primary"]};
            }}

            QListView {{
                background-color: {COLORS["preview_background"]};
                border: 1px solid {COLORS["border"]};
                color: {COLORS["text_primary"]};
                outline: none;
            }}

            QListView::item {{
                background-color: transparent;
                border: none;
            }}

            QListView::item:hover {{
                background-color: transparent;
            }}

            QListView::item:selected {{
                background-color: transparent;
            }}

            QLabel {{
                color: {COLORS["text_primary"]};
                background-color: transparent;
            }}

            QLineEdit {{
                background-color: {COLORS["input_background"]};
                color: {COLORS["text_primary"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 3px;
                padding: 4px;
            }}

            QLineEdit:focus {{
                border-color: {COLORS["border_focus"]};
            }}

            QComboBox {{
                background-color: {COLORS["input_background"]};
                color: {COLORS["text_primary"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 3px;
                padding: 4px;
                min-width: 80px;
            }}

            QComboBox:hover {{
                background-color: {COLORS["panel_background"]};
            }}

            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}

            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {COLORS["text_primary"]};
                margin-right: 5px;
            }}

            QComboBox QAbstractItemView {{
                background-color: {COLORS["input_background"]};
                color: {COLORS["text_primary"]};
                border: 1px solid {COLORS["border"]};
                selection-background-color: {COLORS["panel_background"]};
            }}

            QCheckBox {{
                color: {COLORS["text_primary"]};
                background-color: transparent;
            }}

            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                background-color: {COLORS["input_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 2px;
            }}

            QCheckBox::indicator:checked {{
                background-color: {COLORS["border_focus"]};
                border-color: {COLORS["border_focus"]};
            }}

            QSlider::groove:horizontal {{
                background-color: {COLORS["panel_background"]};
                height: 4px;
                border-radius: 2px;
            }}

            QSlider::handle:horizontal {{
                background-color: {COLORS["border_focus"]};
                border: 1px solid {COLORS["border_focus"]};
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}

            QSlider::handle:horizontal:hover {{
                background-color: {COLORS["highlight"]};
            }}

            QPushButton {{
                background-color: {COLORS["panel_background"]};
                color: {COLORS["text_primary"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 3px;
                padding: 6px 12px;
            }}

            QPushButton:hover {{
                background-color: {COLORS["focus_background_subtle"]};
            }}

            QPushButton:pressed {{
                background-color: {COLORS["input_background"]};
            }}
        """)

    def _create_controls(self) -> QWidget:
        """Create the controls bar for the gallery."""
        controls = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(SPACING_TINY, SPACING_TINY, SPACING_TINY, SPACING_TINY)

        # Thumbnail size slider
        size_label = QLabel("Size:")
        layout.addWidget(size_label)

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(128, 768)  # Actually useful range
        self.size_slider.setValue(self.thumbnail_size)
        self.size_slider.setTickInterval(64)  # Bigger steps for bigger range
        self.size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.size_slider.setMinimumWidth(MEDIUM_WIDTH)  # Use minimum instead of fixed
        self.size_slider.valueChanged.connect(self._on_size_changed)
        layout.addWidget(self.size_slider)

        # Size display
        self.size_label = QLabel(f"{self.thumbnail_size}px")
        self.size_label.setMinimumWidth(40)  # Use minimum instead of fixed
        layout.addWidget(self.size_label)

        layout.addSpacing(SPACING_LARGE)

        # Filter controls
        filter_label = QLabel("Filter:")
        layout.addWidget(filter_label)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Search by offset...")
        self.filter_input.setMinimumWidth(150)  # Use minimum instead of fixed
        self.filter_input.textChanged.connect(self._apply_filters)
        layout.addWidget(self.filter_input)

        self.compressed_check = QCheckBox("HAL only")
        self.compressed_check.toggled.connect(self._apply_filters)
        layout.addWidget(self.compressed_check)

        layout.addSpacing(SPACING_LARGE)

        # Sort controls
        sort_label = QLabel("Sort:")
        layout.addWidget(sort_label)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Offset", "Size", "Tiles"])
        self.sort_combo.currentTextChanged.connect(self._apply_sort)
        layout.addWidget(self.sort_combo)

        layout.addStretch()

        # Selection actions
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all)
        layout.addWidget(self.select_all_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_selection)
        layout.addWidget(self.clear_btn)

        # Status
        self.status_label = QLabel("0 sprites")
        layout.addWidget(self.status_label)

        controls.setLayout(layout)
        return controls

    def set_sprites(self, sprites: list[dict[str, Any]]):
        """
        Set the sprites to display in the gallery.

        Args:
            sprites: List of sprite dictionaries with offset, size, etc.
        """
        if not self.model:
            logger.warning("Model not initialized")
            return

        # Set sprites in model
        self.model.set_sprites(sprites)

        # Apply initial sort
        self._apply_sort()

        # Update status
        self._update_status()

        # Trigger initial thumbnail loading for visible items (use managed timer)
        self.viewport_timer.start()

        logger.debug(f"Gallery populated with {len(sprites)} sprites using virtual scrolling")

    def set_thumbnail(self, offset: int, pixmap: QPixmap):
        """
        Set thumbnail for a sprite.

        Args:
            offset: Sprite offset
            pixmap: Thumbnail pixmap
        """
        if self.model:
            self.model.set_thumbnail(offset, pixmap)
            logger.debug(f"Thumbnail set for offset 0x{offset:06X}")

    def _update_visible_thumbnails(self):
        """Request thumbnails for visible items only."""
        if not self.list_view or not self.model:
            return

        # Get visible viewport
        viewport = self.list_view.viewport()
        viewport_rect = viewport.rect()

        # Find first and last visible items
        first_index = self.list_view.indexAt(viewport_rect.topLeft())
        last_index = self.list_view.indexAt(viewport_rect.bottomRight())

        if not first_index.isValid():
            first_index = self.model.index(0, 0)
        if not last_index.isValid():
            last_index = self.model.index(self.model.rowCount() - 1, 0)

        first_row = first_index.row()
        last_row = last_index.row()

        # Add buffer rows above and below viewport
        first_row = max(0, first_row - VIEWPORT_BUFFER_ROWS * self.columns)
        last_row = min(self.model.rowCount() - 1, last_row + VIEWPORT_BUFFER_ROWS * self.columns)

        # Check if range changed
        if (first_row, last_row) == self._last_visible_range:
            return

        self._last_visible_range = (first_row, last_row)

        # Get offsets that need thumbnails
        offsets_needed = self.model.get_visible_range(first_row, last_row)

        # Request thumbnails with priority based on position
        for i, offset in enumerate(offsets_needed[:THUMBNAIL_REQUEST_BATCH_SIZE]):
            priority = i  # Lower number = higher priority
            self.thumbnail_request.emit(offset, priority)

        logger.debug(f"Requested {len(offsets_needed)} thumbnails for rows {first_row}-{last_row}")

    def _on_scroll(self, value: int):
        """Handle scroll events to trigger thumbnail loading."""
        # Use timer to debounce scroll events
        self.viewport_timer.stop()
        self.viewport_timer.start()

    def _on_item_clicked(self, index: Any) -> None:
        """Handle item click."""
        if not index.isValid():
            return

        offset = index.data(SpriteGalleryModel.OffsetRole)
        if offset is not None:
            self.sprite_selected.emit(offset)

    def _on_item_double_clicked(self, index: Any) -> None:
        """Handle item double click."""
        if not index.isValid():
            return

        offset = index.data(SpriteGalleryModel.OffsetRole)
        if offset is not None:
            self.sprite_double_clicked.emit(offset)

    def _on_model_selection_changed(self, selected_offsets: list[int]):
        """Handle selection change from model."""
        self.selection_changed.emit(selected_offsets)
        self._update_status()

    def _on_thumbnail_needed(self, offset: int, priority: int):
        """Handle thumbnail request from model."""
        self.thumbnail_request.emit(offset, priority)

    def _on_size_changed(self, value: int):
        """Handle thumbnail size change."""
        self.thumbnail_size = value
        if self.size_label:
            self.size_label.setText(f"{value}px")

        # Update model and delegate
        if self.model:
            self.model.set_thumbnail_size(value)
        if self.delegate:
            self.delegate.set_thumbnail_size(value)

        # Force view to update item sizes
        if self.list_view:
            self.list_view.reset()

        # Trigger thumbnail reload for new size
        self.viewport_timer.start()

    def _apply_filters(self):
        """Apply current filters to the gallery."""
        if not self.model:
            return

        filter_text = self.filter_input.text()
        compressed_only = self.compressed_check.isChecked()

        self.model.apply_filter(filter_text, compressed_only)
        self._update_status()

        # Trigger thumbnail loading for newly visible items
        self.viewport_timer.start()

    def _apply_sort(self):
        """Apply sorting to the sprite data."""
        if not self.model:
            return

        sort_key = self.sort_combo.currentText()
        self.model.sort_sprites(sort_key)

        # Trigger thumbnail loading for newly visible items
        self.viewport_timer.start()

    def _select_all(self):
        """Select all visible thumbnails."""
        if self.model:
            self.model.select_all()

    def _clear_selection(self):
        """Clear all selections."""
        if self.model:
            self.model.clear_selection()

    def _update_status(self):
        """Update the status label."""
        if not self.model:
            if self.status_label:
                self.status_label.setText("0 sprites")
            return

        visible_count, total_count, selected_count = self.model.get_sprite_count_info()

        # Show total count, with filtered count if different
        if visible_count < total_count:
            status = f"{visible_count}/{total_count} sprites"
        else:
            status = f"{total_count} sprites"

        if selected_count > 0:
            status += f" ({selected_count} selected)"

        if self.status_label:
            self.status_label.setText(status)

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize event."""
        super().resizeEvent(event)
        # Trigger thumbnail loading after resize
        self.viewport_timer.start()

    @override
    def showEvent(self, event: QShowEvent) -> None:
        """Handle show event to ensure proper initial layout."""
        super().showEvent(event)
        # Trigger thumbnail loading when widget becomes visible
        self.viewport_timer.start()

    def get_selected_sprites(self) -> list[dict[str, Any]]:
        """Get information for all selected sprites."""
        if self.model:
            return self.model.get_selected_sprites()
        return []

    def get_selected_sprite_offset(self) -> int | None:
        """Get the offset of the first selected sprite, or None if none selected."""
        if self.model:
            selected = self.model.get_selected_sprites()
            if selected:
                offset = selected[0].get('offset', 0)
                if isinstance(offset, str):
                    return int(offset, 16) if offset.startswith('0x') else int(offset)
                return offset
        return None

    def force_layout_update(self):
        """Force the gallery to recalculate its layout."""
        if self.list_view:
            self.list_view.reset()
            self.viewport_timer.start()
            logger.debug("Forced layout update for list view")

    def get_sprite_pixmap(self, offset: int) -> QPixmap | None:
        """
        Get the sprite pixmap for a given offset.

        Args:
            offset: Sprite offset

        Returns:
            QPixmap if available, None otherwise
        """
        if self.model:
            return self.model.get_sprite_pixmap(offset)
        return None

    # Backward compatibility property
    @property
    def thumbnails(self) -> dict[int, Any]:
        """Backward compatibility: return dict with offset as key."""
        result: dict[int, Any] = {}
        if self.model:
            # Create a minimal compatibility dict
            for i in range(self.model.rowCount()):
                sprite = self.model.get_sprite_at_row(i)
                if sprite:
                    offset = sprite.get('offset', 0)
                    if isinstance(offset, str):
                        offset = int(offset, 16) if offset.startswith('0x') else int(offset)
                    # Create a minimal object that has the offset
                    if isinstance(offset, int):
                        result[offset] = type('ThumbnailCompat', (), {'offset': offset})
        return result

    def cleanup(self) -> None:
        """Clean up resources before deletion to prevent timer callbacks on deleted objects."""
        if self.viewport_timer:
            self.viewport_timer.stop()
        logger.debug("SpriteGalleryWidget cleanup complete")
