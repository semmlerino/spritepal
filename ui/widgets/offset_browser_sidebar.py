"""Sidebar widget for the Manual Offset Browser.

Contains Nearby Sprites and Bookmarks panels in a collapsible layout.
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
NEARBY_SIZES: dict[str, int] = {"small": 64, "medium": 96, "large": 128}
NEARBY_UPDATE_DEBOUNCE_MS = 300


class OffsetBrowserSidebar(QWidget):
    """Sidebar for the Manual Offset Browser with Nearby and Bookmarks.

    Signals:
        nearby_offset_selected: Emitted when a nearby thumbnail is clicked.
            Args: offset (int)
        bookmark_selected: Emitted when a bookmark is clicked.
            Args: offset (int)
    """

    nearby_offset_selected = Signal(int)
    bookmark_selected = Signal(int)
    add_bookmark_requested = Signal()  # Request parent to add bookmark at current offset

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

        # Nearby panel state
        self._nearby_labels: list[QLabel] = []
        self._nearby_offsets: list[int] = []  # Current calculated offsets
        self._nearby_timer: QTimer | None = None
        self._pending_nearby_center: int = 0
        self._pending_nearby_rom_size: int = 0
        self._rom_extractor: ROMExtractor | None = None
        self._rom_path: str = ""
        self._nearby_current_offset_label: QLabel | None = None
        self._current_palette: list[list[int]] | None = None
        self._use_custom_palette: bool = False

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

        # Header with global actions
        header_layout = QHBoxLayout()

        # Sidebar Title
        title_label = QLabel("Navigation")
        title_label.setStyleSheet("font-weight: bold; color: " + COLORS["text_secondary"])
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # Add Bookmark Button (Always visible)
        self._add_bookmark_btn = QPushButton("★ Bookmark")
        self._add_bookmark_btn.setToolTip("Bookmark current offset")
        self._add_bookmark_btn.setFixedHeight(24)
        self._add_bookmark_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._add_bookmark_btn.clicked.connect(self._on_add_bookmark_clicked)
        self._add_bookmark_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS["panel_background"]};
                border: 1px solid {COLORS["border"]};
                color: {COLORS["text_primary"]};
                padding: 0 8px;
            }}
            QPushButton:hover {{
                border-color: {COLORS["primary"]};
                background-color: {COLORS["surface_hover"]};
            }}
        """)
        header_layout.addWidget(self._add_bookmark_btn)

        layout.addLayout(header_layout)

        # Nearby panel - shows sprite previews at fixed offsets around current position
        self._nearby_panel = CollapsibleGroupBox("Nearby", collapsed=False)
        self._setup_nearby_panel()
        layout.addWidget(self._nearby_panel)

        # Bookmarks panel - visible if bookmarks exist
        self._bookmarks_panel = CollapsibleGroupBox("Bookmarks", collapsed=True)
        self._bookmarks_list = QListWidget()
        self._bookmarks_list.setMaximumHeight(150)
        self._bookmarks_list.itemClicked.connect(self._on_bookmark_item_clicked)
        self._bookmarks_panel.add_widget(self._bookmarks_list)

        # Note: Add Bookmark button moved to header

        layout.addWidget(self._bookmarks_panel)

        # Stretch at bottom to push panels up
        layout.addStretch()

        # Set minimum width for sidebar
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

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

        Emits add_bookmark_requested so parent dialog can handle it with current offset.
        """
        self.add_bookmark_requested.emit()

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

        # Tooltip map for size buttons with shortcut hints
        tooltip_map = {
            "small": "Small thumbnails (64px) [1]",
            "medium": "Medium thumbnails (96px) [2]",
            "large": "Large thumbnails (128px) [3]",
        }

        for key, label in [("small", "S"), ("medium", "M"), ("large", "L")]:
            btn = QPushButton(label)
            btn.setFixedSize(24, 20)
            btn.setCheckable(True)
            btn.setChecked(key == "medium")  # Default to medium
            btn.setToolTip(tooltip_map[key])
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

        # Add palette toggle
        self._palette_toggle_btn = QPushButton("🎨")
        self._palette_toggle_btn.setFixedSize(24, 20)
        self._palette_toggle_btn.setCheckable(True)
        self._palette_toggle_btn.setEnabled(False)  # Disabled until palette set
        self._palette_toggle_btn.setToolTip("Toggle Palette Preview (No palette loaded)")
        self._palette_toggle_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS["input_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 3px;
                font-size: 12px;
                padding: 0;
            }}
            QPushButton:checked {{
                background-color: {COLORS["highlight"]};
                border-color: {COLORS["highlight"]};
                color: white;
            }}
            QPushButton:hover:!checked {{
                border-color: {COLORS["primary"]};
            }}
            QPushButton:disabled {{
                color: {COLORS["text_muted"]};
                border-color: {COLORS["border"]};
                background-color: {COLORS["panel_background"]};
            }}
            """
        )
        self._palette_toggle_btn.clicked.connect(self._on_palette_toggled)
        size_row.addWidget(self._palette_toggle_btn)

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
        self._nearby_expand_btn.setToolTip("Show extended range (±256, ±512, ±1024) [E]")
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

    def set_palette(self, palette: list[list[int]] | None) -> None:
        """Set the palette to use for previews.

        Args:
            palette: List of 16 RGB colors (as [r, g, b] lists) or None.
        """
        self._current_palette = palette
        has_palette = palette is not None and len(palette) > 0

        if self._palette_toggle_btn:
            self._palette_toggle_btn.setEnabled(has_palette)
            if has_palette:
                self._palette_toggle_btn.setToolTip("Toggle Palette Preview")
                # Auto-enable if it was previously checked or if it's the first time
                # (Optional: preserve user preference or auto-enable)
            else:
                self._palette_toggle_btn.setToolTip("Toggle Palette Preview (No palette loaded)")
                self._palette_toggle_btn.setChecked(False)
                self._use_custom_palette = False

        # If we have a palette and use_custom is true, refresh
        if self._use_custom_palette and has_palette:
            if self._pending_nearby_rom_size > 0:
                self._do_nearby_update()

    def _on_palette_toggled(self, checked: bool) -> None:
        """Handle palette toggle click."""
        self._use_custom_palette = checked
        if self._pending_nearby_rom_size > 0:
            self._do_nearby_update()

    def _on_expand_toggled(self) -> None:
        """Handle expand/collapse toggle."""
        self._nearby_expanded = not self._nearby_expanded

        # Update button text and tooltip
        if self._nearby_expand_btn is not None:
            if self._nearby_expanded:
                self._nearby_expand_btn.setText("▲ Show Less")
                self._nearby_expand_btn.setToolTip("Hide extended range [E]")
            else:
                self._nearby_expand_btn.setText("▼ Show More")
                self._nearby_expand_btn.setToolTip("Show extended range (±256, ±512, ±1024) [E]")

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
                background-color: #2D2D2D;
                border: 2px solid {COLORS["border"]};
                border-radius: 6px;
            }}
            QLabel:hover {{
                border-color: {COLORS["primary"]};
                background-color: #353535;
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
            # Calculate tile dimensions for preview (assume 8x8 tiles = 64x64 pixels)
            num_tiles = min(len(render_data) // 32, 64)  # Increase to 64 tiles
            if num_tiles < 1:
                self._set_nearby_thumbnail_error(index, "No tiles")
                return

            # Try to make a square layout
            width_tiles = min(8, num_tiles)  # Wider grid
            height_tiles = (num_tiles + width_tiles - 1) // width_tiles

            # Determine palette to use
            custom_palette = self._current_palette if self._use_custom_palette else None

            image = renderer.render_tiles(
                render_data[: width_tiles * height_tiles * 32],
                width_tiles,
                height_tiles,
                palette_index=None,
                custom_palette=custom_palette,
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
                background-color: #2D2D2D;
                border: 2px solid {COLORS["border"]};
                border-radius: 6px;
                color: {COLORS["text_muted"]};
                font-size: 11px;
                font-weight: bold;
            }}
            QLabel:hover {{
                border-color: {COLORS["primary"]};
                background-color: #353535;
                color: {COLORS["text_primary"]};
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
                    background-color: #2D2D2D;
                    border: 2px solid {COLORS["border"]};
                    border-radius: 6px;
                    color: {COLORS["text_muted"]};
                    font-size: 11px;
                    font-weight: bold;
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
