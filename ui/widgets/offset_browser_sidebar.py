"""Sidebar widget for the Manual Offset Browser.

Contains History, Nearby Sprites, Scan Results, and Bookmarks panels in a collapsible layout.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.common.collapsible_group_box import CollapsibleGroupBox
from ui.common.spacing_constants import SPACING_SMALL
from ui.styles.theme import COLORS

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor
    from ui.dialogs.services.bookmark_manager import BookmarkManager

logger = logging.getLogger(__name__)

# Constants for Nearby panel
NEARBY_DELTAS_CORE = [-128, -64, -32, 32, 64, 128]
NEARBY_DELTAS_EXTENDED = [-1024, -512, -256, 256, 512, 1024]
NEARBY_SIZES: dict[str, int] = {"small": 36, "medium": 48, "large": 64}
NEARBY_UPDATE_DEBOUNCE_MS = 300


class OffsetBrowserSidebar(QWidget):
    """Sidebar for the Manual Offset Browser with History, Nearby, Scan Results, and Bookmarks.

    Signals:
        history_offset_selected: Emitted when a history item is clicked.
            Args: offset (int)
        history_offset_applied: Emitted when a history item is double-clicked.
            Args: offset (int)
        nearby_offset_selected: Emitted when a nearby thumbnail is clicked.
            Args: offset (int)
        scan_result_selected: Emitted when a scan result is clicked.
            Args: offset (int)
        scan_result_applied: Emitted when a scan result is double-clicked.
            Args: offset (int)
        bookmark_selected: Emitted when a bookmark is clicked.
            Args: offset (int)
    """

    history_offset_selected = Signal(int)
    history_offset_applied = Signal(int)
    nearby_offset_selected = Signal(int)
    scan_result_selected = Signal(int)
    scan_result_applied = Signal(int)
    bookmark_selected = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        bookmark_manager: BookmarkManager | None = None,
    ) -> None:
        """Initialize the sidebar.

        Args:
            parent: Parent widget.
            bookmark_manager: Optional bookmark manager for bookmark display.
        """
        super().__init__(parent)
        self._bookmark_manager = bookmark_manager

        # History tracking
        self._history_offsets: list[int] = []
        self._max_history_items = 50

        # Scan results
        self._scan_results: list[dict[str, int | float]] = []

        # Nearby panel state
        self._nearby_labels: list[QLabel] = []
        self._nearby_offsets: list[int] = []  # Current calculated offsets
        self._nearby_timer: QTimer | None = None
        self._pending_nearby_center: int = 0
        self._pending_nearby_rom_size: int = 0
        self._rom_extractor: ROMExtractor | None = None
        self._rom_path: str = ""
        self._nearby_current_offset_label: QLabel | None = None

        # Configurable nearby panel settings
        self._nearby_thumbnail_size: int = NEARBY_SIZES["medium"]
        self._nearby_expanded: bool = False
        self._nearby_size_buttons: dict[str, QPushButton] = {}
        self._nearby_expand_btn: QPushButton | None = None
        self._nearby_grid_container: QWidget | None = None
        self._nearby_grid_layout: QGridLayout | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the sidebar UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_SMALL)
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)

        # History panel - starts collapsed, expands on first navigation
        self._history_panel = CollapsibleGroupBox("History", collapsed=True)
        self._history_list = QListWidget()
        self._history_list.setMaximumHeight(150)
        self._history_list.itemClicked.connect(self._on_history_item_clicked)
        self._history_list.itemDoubleClicked.connect(self._on_history_item_double_clicked)
        self._history_panel.add_widget(self._history_list)

        # History controls
        history_controls = QHBoxLayout()
        clear_history_btn = QPushButton("Clear")
        clear_history_btn.setFixedHeight(24)
        clear_history_btn.clicked.connect(self.clear_history)
        history_controls.addWidget(clear_history_btn)
        history_controls.addStretch()
        self._history_panel.add_layout(history_controls)

        layout.addWidget(self._history_panel)

        # Nearby panel - shows sprite previews at fixed offsets around current position
        self._nearby_panel = CollapsibleGroupBox("Nearby", collapsed=False)
        self._setup_nearby_panel()
        layout.addWidget(self._nearby_panel)

        # Scan Results panel - hidden until scan completes
        self._scan_panel = CollapsibleGroupBox("Scan Results", collapsed=True)
        self._scan_label = QLabel("No scan performed")
        self._scan_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        self._scan_panel.add_widget(self._scan_label)

        self._scan_list = QListWidget()
        self._scan_list.setMaximumHeight(200)
        self._scan_list.itemClicked.connect(self._on_scan_item_clicked)
        self._scan_list.itemDoubleClicked.connect(self._on_scan_item_double_clicked)
        self._scan_list.hide()
        self._scan_panel.add_widget(self._scan_list)

        # Scan controls
        scan_controls = QHBoxLayout()
        self._clear_scan_btn = QPushButton("Clear")
        self._clear_scan_btn.setFixedHeight(24)
        self._clear_scan_btn.clicked.connect(self.clear_scan_results)
        self._clear_scan_btn.setEnabled(False)
        scan_controls.addWidget(self._clear_scan_btn)
        scan_controls.addStretch()
        self._scan_panel.add_layout(scan_controls)

        layout.addWidget(self._scan_panel)

        # Bookmarks panel - visible if bookmarks exist
        self._bookmarks_panel = CollapsibleGroupBox("Bookmarks", collapsed=True)
        self._bookmarks_list = QListWidget()
        self._bookmarks_list.setMaximumHeight(150)
        self._bookmarks_list.itemClicked.connect(self._on_bookmark_item_clicked)
        self._bookmarks_panel.add_widget(self._bookmarks_list)

        # Bookmark controls
        bookmark_controls = QHBoxLayout()
        self._add_bookmark_btn = QPushButton("Add Current")
        self._add_bookmark_btn.setFixedHeight(24)
        self._add_bookmark_btn.clicked.connect(self._on_add_bookmark_clicked)
        bookmark_controls.addWidget(self._add_bookmark_btn)
        bookmark_controls.addStretch()
        self._bookmarks_panel.add_layout(bookmark_controls)

        layout.addWidget(self._bookmarks_panel)

        # Stretch at bottom to push panels up
        layout.addStretch()

        # Set minimum width for sidebar
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    # ============= History Management =============

    def add_to_history(self, offset: int) -> None:
        """Add an offset to the history.

        Args:
            offset: The offset to add.
        """
        # Don't add duplicates of the most recent item
        if self._history_offsets and self._history_offsets[0] == offset:
            return

        # Add to front of list
        self._history_offsets.insert(0, offset)

        # Enforce max size
        if len(self._history_offsets) > self._max_history_items:
            self._history_offsets = self._history_offsets[: self._max_history_items]

        # Update UI
        self._update_history_list()

        # Expand history panel on first entry
        if len(self._history_offsets) == 1:
            self._history_panel.set_collapsed(False)

    def _update_history_list(self) -> None:
        """Update the history list widget."""
        self._history_list.clear()
        for offset in self._history_offsets:
            item = QListWidgetItem(f"0x{offset:06X}")
            item.setData(256, offset)  # Qt.ItemDataRole.UserRole = 256
            self._history_list.addItem(item)

    def clear_history(self) -> None:
        """Clear all history items."""
        self._history_offsets.clear()
        self._history_list.clear()

    def get_history_offsets(self) -> list[int]:
        """Get the list of history offsets.

        Returns:
            List of offsets in history (most recent first).
        """
        return list(self._history_offsets)

    def _on_history_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle history item single click."""
        offset = item.data(256)
        if offset is not None:
            self.history_offset_selected.emit(offset)

    def _on_history_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle history item double click."""
        offset = item.data(256)
        if offset is not None:
            self.history_offset_applied.emit(offset)

    # ============= Scan Results Management =============

    def set_scan_results(self, results: list[dict[str, int | float]]) -> None:
        """Set scan results.

        Args:
            results: List of dicts with 'offset' and optionally 'quality' keys.
        """
        self._scan_results = results
        self._update_scan_list()

        # Show/expand panel if results exist
        if results:
            self._scan_label.hide()
            self._scan_list.show()
            self._scan_panel.set_collapsed(False)
            self._clear_scan_btn.setEnabled(True)
        else:
            self._scan_label.setText("No sprites found")
            self._scan_label.show()
            self._scan_list.hide()
            self._clear_scan_btn.setEnabled(False)

    def _update_scan_list(self) -> None:
        """Update the scan results list widget."""
        self._scan_list.clear()
        self._scan_label.setText(f"{len(self._scan_results)} sprites found")

        for result in self._scan_results:
            offset = result.get("offset", 0)
            quality = result.get("quality", 0.0)
            if isinstance(offset, int):
                text = f"0x{offset:06X}"
                if isinstance(quality, float) and quality > 0:
                    text += f" ({quality:.1%})"
                item = QListWidgetItem(text)
                item.setData(256, offset)
                self._scan_list.addItem(item)

    def clear_scan_results(self) -> None:
        """Clear all scan results."""
        self._scan_results.clear()
        self._scan_list.clear()
        self._scan_label.setText("No scan performed")
        self._scan_label.show()
        self._scan_list.hide()
        self._clear_scan_btn.setEnabled(False)

    def _on_scan_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle scan result single click."""
        offset = item.data(256)
        if offset is not None:
            self.scan_result_selected.emit(offset)

    def _on_scan_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle scan result double click."""
        offset = item.data(256)
        if offset is not None:
            self.scan_result_applied.emit(offset)

    # ============= Bookmarks Management =============

    def refresh_bookmarks(self) -> None:
        """Refresh the bookmarks list from the bookmark manager."""
        self._bookmarks_list.clear()

        if self._bookmark_manager is None:
            return

        bookmarks = self._bookmark_manager.bookmarks
        for offset, name in bookmarks:
            display_name = name if name else f"0x{offset:06X}"
            item = QListWidgetItem(f"★ {display_name}")
            item.setData(256, offset)
            self._bookmarks_list.addItem(item)

        # Show/hide panel based on bookmark count
        if bookmarks:
            self._bookmarks_panel.set_collapsed(False)

    def _on_bookmark_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle bookmark item click."""
        offset = item.data(256)
        if offset is not None:
            self.bookmark_selected.emit(offset)

    def _on_add_bookmark_clicked(self) -> None:
        """Handle add bookmark button click.

        This should be connected to the parent dialog's current offset.
        """
        # The parent dialog should handle this via signal connection
        pass

    def set_bookmark_manager(self, manager: BookmarkManager) -> None:
        """Set the bookmark manager.

        Args:
            manager: The bookmark manager to use.
        """
        self._bookmark_manager = manager
        self.refresh_bookmarks()

    # ============= Nearby Panel Management =============

    def _setup_nearby_panel(self) -> None:
        """Set up the Nearby panel with thumbnail grid and controls."""
        # Size selector row (S|M|L buttons)
        size_row = QHBoxLayout()
        size_row.setContentsMargins(4, 0, 4, 0)
        size_row.setSpacing(2)

        for key, label in [("small", "S"), ("medium", "M"), ("large", "L")]:
            btn = QPushButton(label)
            btn.setFixedSize(24, 20)
            btn.setCheckable(True)
            btn.setChecked(key == "medium")  # Default to medium
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {COLORS["input_background"]};
                    border: 1px solid {COLORS["border"]};
                    border-radius: 3px;
                    font-size: 10px;
                    padding: 0;
                }}
                QPushButton:checked {{
                    background-color: {COLORS["primary"]};
                    color: white;
                }}
                QPushButton:hover {{
                    border-color: {COLORS["primary"]};
                }}
                """
            )
            btn.clicked.connect(lambda checked, k=key: self._on_size_changed(k))
            size_row.addWidget(btn)
            self._nearby_size_buttons[key] = btn
        size_row.addStretch()

        size_widget = QWidget()
        size_widget.setLayout(size_row)
        self._nearby_panel.add_widget(size_widget)

        # Grid container (will be populated by _rebuild_nearby_grid)
        self._nearby_grid_container = QWidget()
        self._nearby_grid_layout = QGridLayout(self._nearby_grid_container)
        self._nearby_grid_layout.setSpacing(4)
        self._nearby_grid_layout.setContentsMargins(4, 4, 4, 4)
        self._nearby_panel.add_widget(self._nearby_grid_container)

        # Build initial grid
        self._rebuild_nearby_grid()

        # Expand/collapse button
        self._nearby_expand_btn = QPushButton("▼ Show More")
        self._nearby_expand_btn.setFlat(True)
        self._nearby_expand_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._nearby_expand_btn.setStyleSheet(
            f"""
            QPushButton {{
                color: {COLORS["primary"]};
                font-size: 10px;
                padding: 4px;
                text-align: center;
            }}
            QPushButton:hover {{
                color: {COLORS["text_primary"]};
            }}
            """
        )
        self._nearby_expand_btn.clicked.connect(self._on_expand_toggled)
        self._nearby_panel.add_widget(self._nearby_expand_btn)

        # Current offset label
        self._nearby_current_offset_label = QLabel("No offset")
        self._nearby_current_offset_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._nearby_current_offset_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
        self._nearby_panel.add_widget(self._nearby_current_offset_label)

        # Setup debounce timer
        self._nearby_timer = QTimer(self)
        self._nearby_timer.setSingleShot(True)
        self._nearby_timer.timeout.connect(self._do_nearby_update)

        # Initialize with placeholder state
        self._clear_nearby_thumbnails()

    def _get_active_deltas(self) -> list[int]:
        """Get the list of deltas based on current expansion state.

        Returns:
            List of delta values to show in the grid.
        """
        if self._nearby_expanded:
            return NEARBY_DELTAS_CORE + NEARBY_DELTAS_EXTENDED
        return NEARBY_DELTAS_CORE

    def _on_size_changed(self, size_key: str) -> None:
        """Handle thumbnail size change.

        Args:
            size_key: The size key ("small", "medium", or "large").
        """
        if size_key not in NEARBY_SIZES:
            return

        self._nearby_thumbnail_size = NEARBY_SIZES[size_key]

        # Update button states (uncheck others, check selected)
        for key, btn in self._nearby_size_buttons.items():
            btn.setChecked(key == size_key)

        # Rebuild grid and regenerate thumbnails
        self._rebuild_nearby_grid()
        if self._pending_nearby_center > 0:
            self._do_nearby_update()

    def _on_expand_toggled(self) -> None:
        """Handle expand/collapse toggle."""
        self._nearby_expanded = not self._nearby_expanded

        # Update button text
        if self._nearby_expand_btn is not None:
            text = "▲ Show Less" if self._nearby_expanded else "▼ Show More"
            self._nearby_expand_btn.setText(text)

        # Rebuild grid and regenerate thumbnails
        self._rebuild_nearby_grid()
        if self._pending_nearby_center > 0:
            self._do_nearby_update()

    def _rebuild_nearby_grid(self) -> None:
        """Rebuild the thumbnail grid with current size and expansion state."""
        if self._nearby_grid_layout is None:
            return

        # Clear existing labels
        for label in self._nearby_labels:
            label.deleteLater()
        self._nearby_labels.clear()
        self._nearby_offsets.clear()

        # Get active deltas
        deltas = self._get_active_deltas()
        size = self._nearby_thumbnail_size

        # Create new labels
        # Layout: negative deltas sorted by absolute value descending in top rows,
        # positive deltas sorted by absolute value ascending in bottom rows
        neg_deltas = sorted([d for d in deltas if d < 0], key=lambda x: -abs(x))  # -128, -64, -32, then -1024...
        pos_deltas = sorted([d for d in deltas if d > 0], key=lambda x: abs(x))  # +32, +64, +128, then +256...

        # Core deltas: row 0 (neg), row 1 (pos)
        # Extended deltas (when expanded): row 2 (neg), row 3 (pos)

        # Add negative core deltas (row 0)
        for col, delta in enumerate(neg_deltas[:3]):
            self._add_nearby_label(delta, size, 0, col)

        # Add positive core deltas (row 1)
        for col, delta in enumerate(pos_deltas[:3]):
            self._add_nearby_label(delta, size, 1, col)

        # Add extended deltas if expanded
        if self._nearby_expanded:
            # Extended negative deltas (row 2) - sorted by absolute value descending
            for col, delta in enumerate(neg_deltas[3:]):
                self._add_nearby_label(delta, size, 2, col)

            # Extended positive deltas (row 3)
            for col, delta in enumerate(pos_deltas[3:]):
                self._add_nearby_label(delta, size, 3, col)

    def _add_nearby_label(self, delta: int, size: int, row: int, col: int) -> None:
        """Add a single nearby label to the grid.

        Args:
            delta: The offset delta for this label.
            size: The thumbnail size in pixels.
            row: Grid row.
            col: Grid column.
        """
        if self._nearby_grid_layout is None:
            return

        label = QLabel()
        label.setFixedSize(size, size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"""
            QLabel {{
                background-color: {COLORS["input_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
            }}
            QLabel:hover {{
                border-color: {COLORS["primary"]};
            }}
            """
        )
        label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # Delta label (overlay showing offset delta)
        delta_text = f"{delta:+d}" if delta != 0 else "0"
        label.setToolTip(f"Click to navigate to offset {delta_text} bytes")

        # Store delta for click handling
        label.setProperty("nearby_delta", delta)
        index = len(self._nearby_labels)
        label.setProperty("nearby_index", index)

        # Connect mouse press
        label.mousePressEvent = lambda event, idx=index: self._on_nearby_clicked(idx)

        self._nearby_grid_layout.addWidget(label, row, col)
        self._nearby_labels.append(label)

    def set_rom_extractor(self, extractor: ROMExtractor, rom_path: str) -> None:
        """Set the ROM extractor and path for thumbnail generation.

        Args:
            extractor: The ROM extractor instance.
            rom_path: Path to the ROM file.
        """
        self._rom_extractor = extractor
        self._rom_path = rom_path
        logger.debug(f"Nearby panel: ROM extractor set, path={rom_path}")

    def update_nearby_offsets(self, center_offset: int, rom_size: int) -> None:
        """Schedule a debounced update of nearby thumbnails.

        Args:
            center_offset: The current offset being viewed.
            rom_size: Total size of the ROM file.
        """
        self._pending_nearby_center = center_offset
        self._pending_nearby_rom_size = rom_size

        # Restart debounce timer
        if self._nearby_timer is not None:
            self._nearby_timer.stop()
            self._nearby_timer.start(NEARBY_UPDATE_DEBOUNCE_MS)

    def _do_nearby_update(self) -> None:
        """Actually generate thumbnails for nearby offsets."""
        center_offset = self._pending_nearby_center
        rom_size = self._pending_nearby_rom_size

        # Update current offset label
        if self._nearby_current_offset_label is not None:
            self._nearby_current_offset_label.setText(f"0x{center_offset:06X}")

        # Check if we can generate previews
        can_generate_previews = self._rom_extractor is not None and bool(self._rom_path)

        # Calculate actual offsets and update each thumbnail
        self._nearby_offsets = []
        for i, label in enumerate(self._nearby_labels):
            delta = label.property("nearby_delta")
            if delta is None:
                self._nearby_offsets.append(-1)
                continue

            actual_offset = center_offset + delta

            # Validate offset bounds
            if actual_offset < 0 or actual_offset >= rom_size:
                self._set_nearby_thumbnail_invalid(i)
                self._nearby_offsets.append(-1)  # Invalid marker
            else:
                self._nearby_offsets.append(actual_offset)
                if can_generate_previews:
                    self._generate_nearby_thumbnail(i, actual_offset)
                else:
                    # Show delta placeholder without preview
                    self._set_nearby_thumbnail_placeholder(i, delta, actual_offset)

    def _generate_nearby_thumbnail(self, index: int, offset: int) -> None:
        """Generate a thumbnail for a nearby offset.

        This uses a synchronous approach with fallback to raw data for simplicity.

        Args:
            index: Index in the nearby labels list.
            offset: ROM offset to generate thumbnail for.
        """
        if index >= len(self._nearby_labels):
            return

        label = self._nearby_labels[index]
        delta = label.property("nearby_delta")
        if delta is None:
            return

        try:
            from pathlib import Path

            from core.tile_renderer import TileRenderer
            from utils.rom_utils import detect_smc_offset

            # Read a small chunk of ROM data for thumbnail
            rom_path = Path(self._rom_path)
            if not rom_path.exists():
                self._set_nearby_thumbnail_error(index, "ROM not found")
                return

            with rom_path.open("rb") as f:
                # Read enough for SMC detection
                f.seek(0)
                header_data = f.read(1024)
                smc_offset = detect_smc_offset(header_data)

                # Seek to the actual offset (accounting for SMC header)
                f.seek(offset + smc_offset)

                # Read a small amount for thumbnail (1KB is enough for a few tiles)
                tile_data = f.read(1024)

            if not tile_data:
                self._set_nearby_thumbnail_error(index, "No data")
                return

            # Try HAL decompression first
            decompressed_data: bytes | None = None
            try:
                if self._rom_extractor is not None:
                    with rom_path.open("rb") as f:
                        rom_data = f.read()
                    smc_offset = detect_smc_offset(rom_data[:1024])
                    if smc_offset > 0:
                        rom_data = rom_data[smc_offset:]

                    # Try decompression (may fail for non-compressed data)
                    _, decompressed_data, _ = self._rom_extractor.rom_injector.find_compressed_sprite(
                        rom_data,
                        offset,
                        1024,  # Small expected size for thumbnail
                    )
            except Exception:
                # Decompression failed, use raw data
                decompressed_data = None

            # Use decompressed data if available, otherwise raw
            render_data = decompressed_data if decompressed_data else tile_data

            # Render to image
            renderer = TileRenderer()
            # Calculate tile dimensions for small preview (assume 4x4 tiles = 32x32 pixels)
            num_tiles = min(len(render_data) // 32, 16)  # Max 16 tiles
            if num_tiles < 1:
                self._set_nearby_thumbnail_error(index, "No tiles")
                return

            # Try to make a square layout
            width_tiles = min(4, num_tiles)
            height_tiles = (num_tiles + width_tiles - 1) // width_tiles

            image = renderer.render_tiles(
                render_data[: width_tiles * height_tiles * 32], width_tiles, height_tiles, palette_index=None
            )

            if image is None:
                self._set_nearby_thumbnail_error(index, "Render failed")
                return

            # Convert PIL Image to QPixmap
            from io import BytesIO

            buffer = BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)

            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())

            # Scale to thumbnail size (with margin for border)
            thumb_size = self._nearby_thumbnail_size - 4
            scaled = pixmap.scaled(
                thumb_size,
                thumb_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            label.setPixmap(scaled)
            label.setToolTip(f"0x{offset:06X} ({delta:+d})\nClick to navigate")

        except Exception as e:
            logger.debug(f"Failed to generate nearby thumbnail at 0x{offset:X}: {e}")
            self._set_nearby_thumbnail_error(index, "Error")

    def _set_nearby_thumbnail_invalid(self, index: int) -> None:
        """Mark a nearby thumbnail as invalid (out of bounds).

        Args:
            index: Index in the nearby labels list.
        """
        if index >= len(self._nearby_labels):
            return

        label = self._nearby_labels[index]
        label.clear()
        label.setText("—")
        label.setStyleSheet(
            f"""
            QLabel {{
                background-color: {COLORS["input_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                color: {COLORS["text_muted"]};
            }}
            """
        )
        label.setToolTip("Out of range")
        label.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def _set_nearby_thumbnail_error(self, index: int, message: str) -> None:
        """Mark a nearby thumbnail as having an error.

        Args:
            index: Index in the nearby labels list.
            message: Error message for tooltip.
        """
        if index >= len(self._nearby_labels):
            return

        label = self._nearby_labels[index]
        label.clear()
        label.setText("?")
        label.setStyleSheet(
            f"""
            QLabel {{
                background-color: {COLORS["input_background"]};
                border: 1px solid {COLORS["warning"]};
                border-radius: 4px;
                color: {COLORS["text_muted"]};
            }}
            QLabel:hover {{
                border-color: {COLORS["primary"]};
            }}
            """
        )
        label.setToolTip(f"Preview unavailable: {message}")
        # Keep cursor clickable
        label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def _set_nearby_thumbnail_placeholder(self, index: int, delta: int, offset: int) -> None:
        """Set a nearby thumbnail to show placeholder with offset info.

        Used when offset is valid but no ROM extractor is available.

        Args:
            index: Index in the nearby labels list.
            delta: The delta value for this thumbnail.
            offset: The calculated offset.
        """
        if index >= len(self._nearby_labels):
            return

        label = self._nearby_labels[index]
        label.clear()
        label.setText(f"{delta:+d}")
        label.setStyleSheet(
            f"""
            QLabel {{
                background-color: {COLORS["input_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                color: {COLORS["text_muted"]};
                font-size: 9px;
            }}
            QLabel:hover {{
                border-color: {COLORS["primary"]};
            }}
            """
        )
        label.setToolTip(f"0x{offset:06X} ({delta:+d})\nClick to navigate\n(No preview available)")
        label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def _clear_nearby_thumbnails(self) -> None:
        """Clear all nearby thumbnails to placeholder state."""
        for label in self._nearby_labels:
            delta = label.property("nearby_delta")
            if delta is None:
                delta = 0
            label.clear()
            label.setText(f"{delta:+d}")
            label.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {COLORS["input_background"]};
                    border: 1px solid {COLORS["border"]};
                    border-radius: 4px;
                    color: {COLORS["text_muted"]};
                    font-size: 9px;
                }}
                """
            )
            label.setToolTip(f"Offset {delta:+d} bytes\nLoad ROM to see preview")
            label.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        if self._nearby_current_offset_label is not None:
            self._nearby_current_offset_label.setText("No offset")

        self._nearby_offsets = []

    def _on_nearby_clicked(self, index: int) -> None:
        """Handle click on a nearby thumbnail.

        Args:
            index: Index of the clicked thumbnail.
        """
        if index >= len(self._nearby_offsets):
            return

        offset = self._nearby_offsets[index]
        if offset < 0:
            # Invalid offset, ignore click
            return

        logger.debug(f"Nearby thumbnail clicked: index={index}, offset=0x{offset:X}")
        self.nearby_offset_selected.emit(offset)
