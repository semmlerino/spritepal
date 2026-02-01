"""Mapping Panel (Drawer) for viewing and managing frame mappings."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.common.mime_constants import MIME_AI_FRAME_REORDER, MIME_GAME_FRAME
from ui.frame_mapping.services.async_icon_quantizer import AsyncIconQuantizer
from ui.frame_mapping.services.thumbnail_service import (
    AsyncThumbnailLoader,
    create_quantized_thumbnail,
)
from ui.frame_mapping.signal_error_handling import signal_error_boundary
from ui.frame_mapping.state.batch_selection_manager import BatchSelectionManager
from ui.frame_mapping.utils.signal_utils import block_signals
from ui.frame_mapping.views.status_colors import get_status_color
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame, FrameMappingProject, SheetPalette

logger = get_logger(__name__)

# Thumbnail size for table cells
THUMBNAIL_SIZE = 64


class MappingPanel(QWidget):
    """Drawer panel for displaying and managing frame mappings.

    Displays a table showing the mapping between AI frames and game frames,
    with thumbnail previews, status indicators, and actions.

    Supports drag-drop from CapturesLibraryPane to create/replace mappings.

    Signals:
        mapping_selected: Emitted when a mapping row is selected (ai_frame_index)
        edit_frame_requested: Emitted when user clicks Edit Frame (ai_frame_index)
        remove_mapping_requested: Emitted when user requests to remove a mapping
        adjust_alignment_requested: Emitted when user clicks Adjust Alignment
        drop_game_frame_requested: Emitted when game frame dropped on row (ai_index, game_id)
        inject_mapping_requested: Emitted when user requests injection (ai_frame_index)
    """

    # ID-based signals (stable across index changes)
    mapping_selected = Signal(str)  # AI frame ID (filename)
    edit_frame_requested = Signal(str)  # AI frame ID
    remove_mapping_requested = Signal(str)  # AI frame ID
    adjust_alignment_requested = Signal(str)  # AI frame ID
    drop_game_frame_requested = Signal(str, str)  # AI frame ID, game frame ID
    inject_mapping_requested = Signal(str)  # AI frame ID
    inject_selected_requested = Signal()  # Request to inject selected frames
    row_reorder_requested = Signal(str, int)  # AI frame ID, target index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: FrameMappingProject | None = None
        self._game_frame_previews: dict[str, QPixmap] = {}
        self._drop_target_row: int | None = None
        # Selection state manager handles checkbox tracking for batch injection
        self._selection_state = BatchSelectionManager()
        # Sheet palette for quantized AI frame thumbnails
        self._sheet_palette: SheetPalette | None = None
        # Cache for quantized+scaled game frame icons
        # Key: (game_frame_id, palette_hash), Value: scaled QPixmap
        self._quantized_icon_cache: dict[tuple[str, int], QPixmap] = {}
        # Drag-drop reorder state
        self._drag_source_row: int | None = None
        self._drag_start_pos: QPoint | None = None
        self._drop_insert_index: int | None = None
        # Async thumbnail loader for AI frames (avoids UI blocking during refresh)
        self._thumbnail_loader = AsyncThumbnailLoader(self)
        self._thumbnail_loader.thumbnail_ready.connect(self._on_thumbnail_ready)
        # Async icon quantizer for game frame icons (avoids UI blocking during palette changes)
        self._icon_quantizer = AsyncIconQuantizer(self)
        self._icon_quantizer.icon_ready.connect(self._on_quantized_icon_ready)
        # Visibility-based thumbnail loading state
        self._last_visible_range: tuple[int, int] = (-1, -1)
        self._visible_thumbnail_timer = QTimer(self)
        self._visible_thumbnail_timer.timeout.connect(self._load_visible_thumbnails)
        self._visible_thumbnail_timer.setInterval(100)  # 100ms debounce
        self._visible_thumbnail_timer.setSingleShot(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header row
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Mappings Drawer")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self._status_label = QLabel("No project")
        self._status_label.setStyleSheet("color: #888; font-size: 10px;")
        header_layout.addWidget(self._status_label)

        layout.addLayout(header_layout)

        # Mapping table - now with checkbox column
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(["", "#", "AI Frame", "Game Frame", "Offset", "Flip", "Status"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._table.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))

        # Enable drag-drop: accept drops (for game frames and reorder)
        # NOTE: We handle drag initiation manually via _mouse_move_event + QDrag,
        # so setDragEnabled(False) - Qt's automatic drag causes multi-second hangs
        self._table.setAcceptDrops(True)
        self._table.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self._table.setDragEnabled(False)
        self._table.viewport().setAcceptDrops(True)
        # Install event filter for custom paint (insertion line)
        self._table.viewport().installEventFilter(self)

        # Context menu
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)

        # Configure header
        header = self._table.horizontalHeader()
        if header:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Checkbox
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # #
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # AI Frame
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Game Frame
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Offset
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Flip
            header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Status

        # Set row height for thumbnails
        self._table.verticalHeader().setDefaultSectionSize(THUMBNAIL_SIZE + 8)
        self._table.verticalHeader().setVisible(False)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemChanged.connect(self._on_item_changed)
        # Connect scroll bar to trigger visibility-based thumbnail loading
        self._table.verticalScrollBar().valueChanged.connect(self._on_scroll)
        layout.addWidget(self._table, 1)

        # Selection controls row
        selection_layout = QHBoxLayout()
        selection_layout.setSpacing(4)

        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setToolTip("Check all mapped frames for injection")
        self._select_all_btn.clicked.connect(self._on_select_all)
        selection_layout.addWidget(self._select_all_btn)

        self._deselect_all_btn = QPushButton("Deselect All")
        self._deselect_all_btn.setToolTip("Uncheck all frames")
        self._deselect_all_btn.clicked.connect(self._on_deselect_all)
        selection_layout.addWidget(self._deselect_all_btn)

        selection_layout.addStretch()

        self._inject_selected_btn = QPushButton("Inject Selected")
        self._inject_selected_btn.setToolTip("Inject only checked frames into ROM")
        self._inject_selected_btn.setStyleSheet("background-color: #2c5d2c;")
        self._inject_selected_btn.setEnabled(False)
        self._inject_selected_btn.clicked.connect(self._on_inject_selected_clicked)
        selection_layout.addWidget(self._inject_selected_btn)

        layout.addLayout(selection_layout)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)

        self._edit_button = QPushButton("Edit AI Frame")
        self._edit_button.setToolTip("Open the AI frame in sprite editor")
        self._edit_button.setEnabled(False)
        self._edit_button.clicked.connect(self._on_edit_clicked)
        button_layout.addWidget(self._edit_button)

        self._align_button = QPushButton("Adjust Alignment")
        self._align_button.setToolTip("Focus canvas for alignment (or use arrow keys)")
        self._align_button.setEnabled(False)
        self._align_button.clicked.connect(self._on_align_clicked)
        button_layout.addWidget(self._align_button)

        self._remove_button = QPushButton("Remove Mapping")
        self._remove_button.setToolTip("Unlink the game frame from this AI frame")
        self._remove_button.setEnabled(False)
        self._remove_button.clicked.connect(self._on_remove_clicked)
        button_layout.addWidget(self._remove_button)

        button_layout.addStretch()

        self._inject_button = QPushButton("Inject to ROM")
        self._inject_button.setToolTip("Inject this mapping into the ROM")
        self._inject_button.setEnabled(False)
        self._inject_button.setStyleSheet("background-color: #2c5d2c; font-weight: bold;")
        self._inject_button.clicked.connect(self._on_inject_clicked)
        button_layout.addWidget(self._inject_button)

        layout.addLayout(button_layout)

        # Override drag-drop methods
        self._table.dragEnterEvent = self._drag_enter_event
        self._table.dragMoveEvent = self._drag_move_event
        self._table.dragLeaveEvent = self._drag_leave_event
        self._table.dropEvent = self._drop_event
        # Override mouse events for drag initiation
        self._table.mousePressEvent = self._mouse_press_event
        self._table.mouseMoveEvent = self._mouse_move_event

    def set_project(self, project: FrameMappingProject | None) -> None:
        """Set the project to display mappings from.

        Does NOT call refresh() - caller controls refresh timing to prevent
        double refresh when project_changed signal triggers both set_project
        and _update_mapping_panel_previews.

        Args:
            project: FrameMappingProject or None to clear
        """
        logger.debug("set_project called: project=%s", project.name if project else None)
        self._project = project
        # Reset checkbox state when loading a new project
        self._selection_state.reset()
        logger.debug("set_project: selection state RESET")

    def reset_batch_selection(self) -> None:
        """Reset batch selection to default behavior.

        Called when AI frames are reloaded to restore default (all mapped = checked).
        """
        self._selection_state.reset()

    def set_game_frame_previews(self, previews: dict[str, QPixmap]) -> None:
        """Set the game frame preview pixmaps for thumbnail display.

        Args:
            previews: Mapping of game_frame_id -> QPixmap
        """
        self._game_frame_previews = previews

    def update_game_frame_preview(self, frame_id: str, preview: QPixmap) -> None:
        """Update the preview for a single game frame without full refresh.

        This is more efficient than refresh() when only updating a single
        preview (e.g., after preview cache invalidation).

        Args:
            frame_id: The game frame ID
            preview: The new preview QPixmap
        """
        self._game_frame_previews[frame_id] = preview
        self._update_row_game_frame_icon(frame_id, preview)

    def _update_row_game_frame_icon(self, game_frame_id: str, preview: QPixmap) -> None:
        """Update game frame icon in rows using this game frame.

        Finds all rows mapped to the given game frame and updates their
        Game Frame column icon with the new preview (quantized and scaled).

        Args:
            game_frame_id: The game frame ID
            preview: The preview QPixmap (will be quantized and scaled)
        """
        if self._project is None:
            return

        # Get cached or generate quantized+scaled icon
        scaled = self._get_quantized_scaled_icon(game_frame_id, preview)

        # Find all rows mapped to this game frame and update the icon
        for row in range(self._table.rowCount()):
            checkbox_item = self._table.item(row, 0)  # Checkbox column has AI frame ID
            if checkbox_item is None:
                continue

            ai_frame_id = checkbox_item.data(Qt.ItemDataRole.UserRole + 1)
            if ai_frame_id is None:
                continue

            # Check if this AI frame is mapped to the target game frame
            mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
            if mapping is not None and mapping.game_frame_id == game_frame_id:
                game_item = self._table.item(row, 3)  # Game Frame column
                if game_item is not None:
                    game_item.setIcon(QIcon(scaled))

    @signal_error_boundary()
    def _on_thumbnail_ready(self, frame_id: str, pixmap: QPixmap) -> None:
        """Handle async thumbnail ready signal.

        Finds the row for the given AI frame ID and sets its thumbnail icon.

        Args:
            frame_id: The AI frame ID
            pixmap: The generated thumbnail QPixmap
        """
        # Find ALL rows with matching AI frame ID and update their icons
        # (handles duplicate filenames in the project)
        found = False
        for row in range(self._table.rowCount()):
            ai_item = self._table.item(row, 2)  # AI Frame column
            if ai_item is None:
                continue
            item_frame_id = ai_item.data(Qt.ItemDataRole.UserRole + 1)
            if item_frame_id == frame_id:
                ai_item.setIcon(QIcon(pixmap))
                logger.debug("MappingPanel: set icon for %s at row %d", frame_id, row)
                found = True
                # Don't break - continue to find all duplicates
        if not found:
            logger.debug(
                "MappingPanel: no row found for frame_id=%s (table has %d rows)", frame_id, self._table.rowCount()
            )

    @signal_error_boundary()
    def _on_quantized_icon_ready(self, game_frame_id: str, pixmap: QPixmap, palette_hash: int) -> None:
        """Handle async quantized icon ready signal.

        Updates the icon cache and all table rows using this game frame.

        Args:
            game_frame_id: The game frame ID
            pixmap: The quantized and scaled QPixmap
            palette_hash: Hash of the palette used for quantization
        """
        # Cache the result
        cache_key = (game_frame_id, palette_hash)
        self._quantized_icon_cache[cache_key] = pixmap

        # Update all rows using this game frame
        if self._project is None:
            return

        for row in range(self._table.rowCount()):
            checkbox_item = self._table.item(row, 0)
            if checkbox_item is None:
                continue

            ai_frame_id = checkbox_item.data(Qt.ItemDataRole.UserRole + 1)
            if ai_frame_id is None:
                continue

            mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
            if mapping is not None and mapping.game_frame_id == game_frame_id:
                game_item = self._table.item(row, 3)  # Game Frame column
                if game_item is not None:
                    game_item.setIcon(QIcon(pixmap))

    @signal_error_boundary()
    def _on_scroll(self) -> None:
        """Handle scroll events - debounce thumbnail loading."""
        self._visible_thumbnail_timer.start()

    def _load_visible_thumbnails(self) -> None:
        """Load thumbnails only for visible rows + buffer.

        This implements visibility-based lazy loading following the pattern
        from SpriteGalleryWidget._update_visible_thumbnails().
        """
        if self._project is None:
            return

        # Get visible viewport bounds
        viewport = self._table.viewport()
        viewport_rect = viewport.rect()

        # Find first and last visible rows using table row/column mapping
        first_row = self._table.rowAt(viewport_rect.top())
        last_row = self._table.rowAt(viewport_rect.bottom())

        # Handle edge cases
        first_row = max(first_row, 0)
        if last_row < 0:
            last_row = self._table.rowCount() - 1

        # Add buffer rows above and below viewport (5 rows)
        buffer_rows = 5
        first_row = max(0, first_row - buffer_rows)
        last_row = min(self._table.rowCount() - 1, last_row + buffer_rows)

        # Skip if range hasn't changed
        if (first_row, last_row) == self._last_visible_range:
            return
        self._last_visible_range = (first_row, last_row)

        # Collect thumbnail requests for visible rows only
        thumbnail_requests: list[tuple[str, Path]] = []
        for row in range(first_row, last_row + 1):
            ai_item = self._table.item(row, 2)  # AI Frame column
            if ai_item is None:
                continue

            # Skip if already has an icon (thumbnail loaded)
            if not ai_item.icon().isNull():
                continue

            # Get AI frame ID from item data
            frame_id = ai_item.data(Qt.ItemDataRole.UserRole + 1)
            if frame_id is None:
                continue

            # Find the corresponding AI frame in project
            ai_frame = self._project.get_ai_frame_by_id(frame_id)
            if ai_frame is not None:
                thumbnail_requests.append((ai_frame.id, ai_frame.path))

        # Request thumbnails for visible items only
        if thumbnail_requests:
            logger.debug("Requesting %d thumbnails for rows %d-%d", len(thumbnail_requests), first_row, last_row)
            self._thumbnail_loader.load_thumbnails(thumbnail_requests, self._sheet_palette, THUMBNAIL_SIZE)

    def _get_quantized_scaled_icon(self, game_frame_id: str, preview: QPixmap) -> QPixmap:
        """Get cached or generate quantized+scaled icon for a game frame.

        If cached, returns immediately. Otherwise, queues async quantization
        and returns a scaled-but-unquantized placeholder for immediate display.

        Args:
            game_frame_id: The game frame ID
            preview: The raw preview QPixmap

        Returns:
            Quantized and scaled QPixmap if cached, otherwise scaled placeholder
        """
        # Compute palette hash for cache key
        palette_hash = self._compute_palette_hash()
        cache_key = (game_frame_id, palette_hash)

        if cache_key in self._quantized_icon_cache:
            return self._quantized_icon_cache[cache_key]

        # No palette set - just scale and cache
        if self._sheet_palette is None:
            scaled = preview.scaled(
                THUMBNAIL_SIZE,
                THUMBNAIL_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._quantized_icon_cache[cache_key] = scaled
            return scaled

        # Queue async quantization
        self._icon_quantizer.quantize_icon(
            game_frame_id=game_frame_id,
            raw_pixmap=preview,
            sheet_palette=self._sheet_palette,
            palette_hash=palette_hash,
            target_size=THUMBNAIL_SIZE,
        )

        # Return unquantized placeholder for immediate display
        return preview.scaled(
            THUMBNAIL_SIZE,
            THUMBNAIL_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _compute_palette_hash(self) -> int:
        """Compute hash of current sheet palette for cache keys.

        Returns:
            Integer hash, 0 if no palette set
        """
        if self._sheet_palette is None:
            return 0
        # Use SheetPalette's built-in version_hash property
        return self._sheet_palette.version_hash

    def set_sheet_palette(self, palette: SheetPalette | None) -> None:
        """Set the sheet palette for quantized AI frame thumbnails.

        When set, AI frame thumbnails will be quantized to show how they'll
        look when injected with this palette.

        Args:
            palette: SheetPalette to use, or None to show original colors
        """
        # Skip if palette is unchanged (same object or both None)
        if palette is self._sheet_palette:
            logger.debug("set_sheet_palette: SKIPPED (same object)")
            return

        logger.debug("set_sheet_palette: palette CHANGED, will refresh")
        self._sheet_palette = palette
        # Clear quantized icon cache since palette changed
        self._quantized_icon_cache.clear()
        # Refresh to apply new palette to thumbnails
        self.refresh()

    def refresh(self) -> None:
        """Refresh the mapping table from the current project."""
        # Store current selection by ID (stable across reordering)
        current_selection_id = self.get_selected_ai_frame_id()

        # Capture current checkbox state (stable across index changes)
        # Only update if user has explicitly modified checkboxes
        if self._project is not None and self._table.rowCount() > 0:
            captured_checked_ids = self._capture_checkbox_state()
            logger.debug(
                "refresh: captured %d checked IDs, tracking=%s, tracked_ids=%s",
                len(captured_checked_ids),
                self._selection_state.is_tracking_user_selections(),
                self._selection_state.get_checked_ids(),
            )
            self._selection_state.update_from_refresh(captured_checked_ids)
        else:
            logger.debug(
                "refresh: skipping capture (project=%s, rowCount=%d)",
                self._project is not None,
                self._table.rowCount() if self._project else 0,
            )

        # Block signals during rebuild to prevent spurious selection events
        with block_signals(self._table):
            self._table.setRowCount(0)
            # Reset visible range tracking since table was rebuilt
            self._last_visible_range = (-1, -1)

            if self._project is None:
                self._status_label.setText("No project")
                self._update_inject_selected_state()
                return

            # Show all AI frames with their mapping status
            for ai_frame in self._project.ai_frames:
                row = self._table.rowCount()
                self._table.insertRow(row)

                # Get mapping to determine if frame is mapped (use ID-based lookup)
                mapping = self._project.get_mapping_for_ai_frame(ai_frame.id)
                is_mapped = mapping is not None

                # Checkbox column (column 0)
                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)

                # Determine checkbox state via selection manager
                should_check = self._selection_state.should_check(ai_frame.id, is_mapped)

                checkbox_item.setCheckState(Qt.CheckState.Checked if should_check else Qt.CheckState.Unchecked)
                checkbox_item.setData(Qt.ItemDataRole.UserRole, ai_frame.index)
                # Also store AI frame ID for stable reference (used by checkbox preservation)
                checkbox_item.setData(Qt.ItemDataRole.UserRole + 1, ai_frame.id)
                self._table.setItem(row, 0, checkbox_item)

                # # column (row number) - column 1
                num_item = QTableWidgetItem(str(ai_frame.index + 1))
                num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 1, num_item)

                # AI Frame column with thumbnail - column 2
                # Thumbnails are loaded asynchronously via visibility-based lazy loading
                ai_item = QTableWidgetItem(ai_frame.path.name)
                ai_item.setData(Qt.ItemDataRole.UserRole, ai_frame.index)
                # Also store AI frame ID for ID-based lookups
                ai_item.setData(Qt.ItemDataRole.UserRole + 1, ai_frame.id)
                self._table.setItem(row, 2, ai_item)

                # Game Frame column - column 3
                if mapping:
                    game_item = QTableWidgetItem(mapping.game_frame_id)
                    status = mapping.status

                    # Load game frame thumbnail (use cached quantized+scaled icon)
                    if mapping.game_frame_id in self._game_frame_previews:
                        pixmap = self._game_frame_previews[mapping.game_frame_id]
                        scaled = self._get_quantized_scaled_icon(mapping.game_frame_id, pixmap)
                        game_item.setIcon(QIcon(scaled))

                    # Offset column - column 4
                    if mapping.offset_x != 0 or mapping.offset_y != 0:
                        offset_item = QTableWidgetItem(f"({mapping.offset_x}, {mapping.offset_y})")
                    else:
                        offset_item = QTableWidgetItem("—")

                    # Flip column - column 5
                    flip_parts = []
                    if mapping.flip_h:
                        flip_parts.append("H")
                    if mapping.flip_v:
                        flip_parts.append("V")
                    flip_item = QTableWidgetItem("".join(flip_parts) if flip_parts else "—")
                else:
                    game_item = QTableWidgetItem("—")
                    status = "unmapped"
                    offset_item = QTableWidgetItem("—")
                    flip_item = QTableWidgetItem("—")

                self._table.setItem(row, 3, game_item)
                offset_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 4, offset_item)
                flip_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 5, flip_item)

                # Status column with color and indicator - column 6
                status_indicator = "●" if status != "unmapped" else "○"
                status_item = QTableWidgetItem(f"{status_indicator} {status.capitalize()}")
                color = get_status_color(status)
                status_item.setForeground(QBrush(color))
                self._table.setItem(row, 6, status_item)

            # Update status summary
            mapped = self._project.mapped_count
            total = self._project.total_ai_frames
            self._status_label.setText(f"{mapped}/{total} mapped")

            # Trigger visibility-based thumbnail loading after table is fully built
            # Use QTimer.singleShot to allow Qt to layout the table first
            QTimer.singleShot(0, self._load_visible_thumbnails)

        # Restore selection by ID (stable across reordering)
        if current_selection_id is not None:
            self.select_row_by_ai_id(current_selection_id)

        # Update inject selected button state
        self._update_inject_selected_state()

    def get_selected_ai_frame_index(self) -> int | None:
        """Get the AI frame index of the selected mapping row."""
        selected = self._table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        ai_item = self._table.item(row, 2)  # AI Frame column (shifted due to checkbox)
        if ai_item is None:
            return None
        return ai_item.data(Qt.ItemDataRole.UserRole)

    def get_selected_ai_frame_id(self) -> str | None:
        """Get the AI frame ID (filename) of the selected mapping row.

        This is more stable than index as it doesn't change when frames are reordered.
        """
        selected = self._table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        checkbox_item = self._table.item(row, 0)  # Checkbox column stores ID in UserRole+1
        if checkbox_item is None:
            return None
        return checkbox_item.data(Qt.ItemDataRole.UserRole + 1)

    def select_row_by_ai_id(self, ai_frame_id: str) -> None:
        """Select a row by AI frame ID (filename).

        Blocks signals to prevent feedback loops.
        This is the preferred method as IDs are stable across reloads/reordering.

        Args:
            ai_frame_id: AI frame ID (filename) to select
        """
        with block_signals(self._table):
            for row in range(self._table.rowCount()):
                checkbox_item = self._table.item(row, 0)  # Checkbox column stores ID in UserRole+1
                if checkbox_item is not None and checkbox_item.data(Qt.ItemDataRole.UserRole + 1) == ai_frame_id:
                    self._table.selectRow(row)
                    self._table.scrollToItem(checkbox_item)
                    break
        # Update button states since signals were blocked during selection
        self._update_button_states()

    def update_row_alignment(
        self,
        ai_frame_id: str,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
    ) -> None:
        """Update only the alignment columns for a specific row.

        This is more efficient than full refresh() and preserves checkbox state
        during interactive alignment adjustments (dragging, arrow keys).

        Args:
            ai_frame_id: AI frame ID (filename) to update
            offset_x: New X offset
            offset_y: New Y offset
            flip_h: Horizontal flip state
            flip_v: Vertical flip state
        """
        # Find the row for this AI frame by ID
        for row in range(self._table.rowCount()):
            checkbox_item = self._table.item(row, 0)  # Checkbox column stores ID in UserRole+1
            if checkbox_item is not None and checkbox_item.data(Qt.ItemDataRole.UserRole + 1) == ai_frame_id:
                # Update Offset column (4)
                if offset_x != 0 or offset_y != 0:
                    offset_text = f"({offset_x}, {offset_y})"
                else:
                    offset_text = "—"
                offset_item = self._table.item(row, 4)
                if offset_item is not None:
                    offset_item.setText(offset_text)

                # Update Flip column (5)
                flip_parts = []
                if flip_h:
                    flip_parts.append("H")
                if flip_v:
                    flip_parts.append("V")
                flip_text = "".join(flip_parts) if flip_parts else "—"
                flip_item = self._table.item(row, 5)
                if flip_item is not None:
                    flip_item.setText(flip_text)

                break

    def update_row_status(self, ai_frame_id: str, status: str) -> None:
        """Update only the status column for a specific row.

        This is more efficient than full refresh() and preserves checkbox state
        during interactive alignment adjustments (dragging, arrow keys).

        Args:
            ai_frame_id: AI frame ID (filename) to update
            status: New status ("unmapped", "mapped", "edited", "injected")
        """
        # Find the row for this AI frame by ID
        for row in range(self._table.rowCount()):
            checkbox_item = self._table.item(row, 0)  # Checkbox column stores ID in UserRole+1
            if checkbox_item is not None and checkbox_item.data(Qt.ItemDataRole.UserRole + 1) == ai_frame_id:
                # Update Status column (6)
                status_indicator = "●" if status != "unmapped" else "○"
                status_item = self._table.item(row, 6)
                if status_item is not None:
                    status_item.setText(f"{status_indicator} {status.capitalize()}")
                    color = get_status_color(status)
                    status_item.setForeground(QBrush(color))
                break

    def clear_row_mapping(self, ai_frame_id: str) -> None:
        """Clear mapping data from a row without full refresh.

        Used when a mapping is removed - much faster than refresh() as it
        doesn't regenerate any thumbnails.

        Args:
            ai_frame_id: AI frame ID (filename) to clear mapping for
        """
        # Find the row for this AI frame by ID
        for row in range(self._table.rowCount()):
            checkbox_item = self._table.item(row, 0)
            if checkbox_item is not None and checkbox_item.data(Qt.ItemDataRole.UserRole + 1) == ai_frame_id:
                # Clear Game Frame column (3) - text and icon
                game_item = self._table.item(row, 3)
                if game_item is not None:
                    game_item.setText("—")
                    game_item.setIcon(QIcon())

                # Clear Offset column (4)
                offset_item = self._table.item(row, 4)
                if offset_item is not None:
                    offset_item.setText("—")

                # Clear Flip column (5)
                flip_item = self._table.item(row, 5)
                if flip_item is not None:
                    flip_item.setText("—")

                # Update Status column (6) to unmapped
                status_item = self._table.item(row, 6)
                if status_item is not None:
                    status_item.setText("○ Unmapped")
                    color = get_status_color("unmapped")
                    status_item.setForeground(QBrush(color))

                break

        # Update status label count
        if self._project is not None:
            mapped = self._project.mapped_count
            total = self._project.total_ai_frames
            self._status_label.setText(f"{mapped}/{total} mapped")

        # Update inject selected button state
        self._update_inject_selected_state()

    def move_row(self, from_index: int, to_index: int) -> None:
        """Move a row from one position to another without full refresh.

        This is much faster than calling refresh() as it only moves Qt items
        rather than regenerating all thumbnails.

        Args:
            from_index: Current row position (0-based)
            to_index: Target row position (0-based)
        """
        if from_index == to_index:
            return

        row_count = self._table.rowCount()
        if from_index < 0 or from_index >= row_count:
            return
        if to_index < 0 or to_index >= row_count:
            return

        with block_signals(self._table):
            # Collect all items from the source row
            col_count = self._table.columnCount()
            items: list[QTableWidgetItem | None] = []
            for col in range(col_count):
                # takeItem removes and returns the item
                items.append(self._table.takeItem(from_index, col))

            # Remove the source row
            self._table.removeRow(from_index)

            # Insert a new row at target position
            self._table.insertRow(to_index)

            # Place items in the new row
            for col, item in enumerate(items):
                if item is not None:
                    self._table.setItem(to_index, col, item)

            # Update row number column for all affected rows
            # The row number display (# column) should reflect the new order
            start = min(from_index, to_index)
            end = max(from_index, to_index)
            for row in range(start, end + 1):
                num_item = self._table.item(row, 1)  # # column is index 1
                if num_item:
                    num_item.setText(str(row + 1))
                # Also update the index stored in UserRole for checkbox column
                checkbox_item = self._table.item(row, 0)
                if checkbox_item:
                    checkbox_item.setData(Qt.ItemDataRole.UserRole, row)
                # And the AI frame item
                ai_item = self._table.item(row, 2)
                if ai_item:
                    ai_item.setData(Qt.ItemDataRole.UserRole, row)

            # Select the moved row
            self._table.selectRow(to_index)

    def add_row(self, ai_frame: AIFrame) -> None:
        """Add a single row for a new AI frame without full refresh.

        This is much faster than refresh() as it only creates one row
        and generates one thumbnail, rather than rebuilding everything.

        Args:
            ai_frame: The AIFrame to add a row for
        """
        if self._project is None:
            return

        with block_signals(self._table):
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Checkbox column (column 0)
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            # New frames default to unchecked
            checkbox_item.setCheckState(Qt.CheckState.Unchecked)
            checkbox_item.setData(Qt.ItemDataRole.UserRole, ai_frame.index)
            checkbox_item.setData(Qt.ItemDataRole.UserRole + 1, ai_frame.id)
            self._table.setItem(row, 0, checkbox_item)

            # # column (row number) - column 1
            num_item = QTableWidgetItem(str(ai_frame.index + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, num_item)

            # AI Frame column with thumbnail - column 2
            ai_item = QTableWidgetItem(ai_frame.path.name)
            ai_item.setData(Qt.ItemDataRole.UserRole, ai_frame.index)
            ai_item.setData(Qt.ItemDataRole.UserRole + 1, ai_frame.id)
            # Load thumbnail
            thumbnail = create_quantized_thumbnail(ai_frame.path, self._sheet_palette, THUMBNAIL_SIZE)
            if thumbnail is not None:
                ai_item.setIcon(QIcon(thumbnail))
            self._table.setItem(row, 2, ai_item)

            # Game Frame column - column 3 (unmapped)
            game_item = QTableWidgetItem("—")
            self._table.setItem(row, 3, game_item)

            # Offset column - column 4 (unmapped)
            offset_item = QTableWidgetItem("—")
            offset_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 4, offset_item)

            # Flip column - column 5 (unmapped)
            flip_item = QTableWidgetItem("—")
            flip_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 5, flip_item)

            # Status column - column 6 (unmapped)
            status_item = QTableWidgetItem("○ Unmapped")
            color = get_status_color("unmapped")
            status_item.setForeground(QBrush(color))
            self._table.setItem(row, 6, status_item)

            # Update status summary
            mapped = self._project.mapped_count
            total = self._project.total_ai_frames
            self._status_label.setText(f"{mapped}/{total} mapped")

        # Update inject selected button state
        self._update_inject_selected_state()

    def clear_selection(self) -> None:
        """Clear the current table selection.

        Blocks signals to prevent feedback loops.
        """
        with block_signals(self._table):
            self._table.clearSelection()
        # Update button states since signals were blocked during selection clear
        self._update_button_states()

    def _update_button_states(self) -> None:
        """Update button enabled states based on current selection."""
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is None:
            self._edit_button.setEnabled(False)
            self._align_button.setEnabled(False)
            self._remove_button.setEnabled(False)
            self._inject_button.setEnabled(False)
            return

        has_mapping = False
        if self._project:
            mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
            has_mapping = mapping is not None

        self._edit_button.setEnabled(True)
        self._align_button.setEnabled(has_mapping)
        self._remove_button.setEnabled(has_mapping)
        self._inject_button.setEnabled(has_mapping)

    @signal_error_boundary()
    def _on_selection_changed(self) -> None:
        """Handle selection change in the mapping table."""
        self._update_button_states()
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is not None:
            self.mapping_selected.emit(ai_frame_id)
        else:
            # Notify listeners of cleared selection
            self.mapping_selected.emit("")

    @signal_error_boundary()
    def _on_edit_clicked(self) -> None:
        """Handle edit button click."""
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is not None:
            self.edit_frame_requested.emit(ai_frame_id)

    @signal_error_boundary()
    def _on_remove_clicked(self) -> None:
        """Handle remove button click."""
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is not None:
            self.remove_mapping_requested.emit(ai_frame_id)

    @signal_error_boundary()
    def _on_align_clicked(self) -> None:
        """Handle adjust alignment button click."""
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is not None:
            self.adjust_alignment_requested.emit(ai_frame_id)

    @signal_error_boundary()
    def _on_inject_clicked(self) -> None:
        """Handle inject button click."""
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is not None:
            self.inject_mapping_requested.emit(ai_frame_id)

    @signal_error_boundary()
    def _on_context_menu(self, pos: QPoint) -> None:
        """Show context menu for mappings."""
        item = self._table.itemAt(pos)
        if item is None:
            return

        row = item.row()
        checkbox_item = self._table.item(row, 0)  # Checkbox column has ID
        if checkbox_item is None:
            return

        ai_frame_id = checkbox_item.data(Qt.ItemDataRole.UserRole + 1)
        if ai_frame_id is None:
            return

        has_mapping = False
        if self._project:
            mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
            has_mapping = mapping is not None

        menu = QMenu(self)

        edit_action = menu.addAction("Edit AI Frame")
        edit_action.triggered.connect(partial(self.edit_frame_requested.emit, ai_frame_id))

        if has_mapping:
            align_action = menu.addAction("Adjust Alignment")
            align_action.triggered.connect(partial(self.adjust_alignment_requested.emit, ai_frame_id))

            menu.addSeparator()

            remove_action = menu.addAction("Remove Mapping")
            remove_action.triggered.connect(partial(self.remove_mapping_requested.emit, ai_frame_id))

            menu.addSeparator()

            inject_action = menu.addAction("Inject to ROM")
            inject_action.triggered.connect(partial(self.inject_mapping_requested.emit, ai_frame_id))

        # Row reordering options
        menu.addSeparator()
        row_count = self._table.rowCount()

        move_up_action = menu.addAction("Move Up")
        move_up_action.triggered.connect(partial(self._move_row_relative, ai_frame_id, -1))
        move_up_action.setEnabled(row > 0)

        move_down_action = menu.addAction("Move Down")
        move_down_action.triggered.connect(partial(self._move_row_relative, ai_frame_id, 1))
        move_down_action.setEnabled(row < row_count - 1)

        move_to_top_action = menu.addAction("Send to Top")
        move_to_top_action.triggered.connect(partial(self._move_row_to_index, ai_frame_id, 0))
        move_to_top_action.setEnabled(row > 0)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _move_row_relative(self, ai_frame_id: str, direction: int) -> None:
        """Move row up (-1) or down (+1) relative to current position.

        Args:
            ai_frame_id: ID of the AI frame to move
            direction: -1 for up, +1 for down
        """
        # Find current row for this AI frame
        for row in range(self._table.rowCount()):
            checkbox_item = self._table.item(row, 0)
            if checkbox_item and checkbox_item.data(Qt.ItemDataRole.UserRole + 1) == ai_frame_id:
                new_row = row + direction
                if 0 <= new_row < self._table.rowCount():
                    self.row_reorder_requested.emit(ai_frame_id, new_row)
                break

    def _move_row_to_index(self, ai_frame_id: str, target_index: int) -> None:
        """Move row to a specific index.

        Args:
            ai_frame_id: ID of the AI frame to move
            target_index: Target index (0-based)
        """
        self.row_reorder_requested.emit(ai_frame_id, target_index)

    def _drag_enter_event(self, event: QDragEnterEvent) -> None:
        """Handle drag enter event."""
        mime_data = event.mimeData()
        if mime_data is not None:  # type: ignore[reportUnnecessaryComparison]
            if mime_data.hasFormat(MIME_GAME_FRAME) or mime_data.hasFormat(MIME_AI_FRAME_REORDER):
                event.acceptProposedAction()
                return
        event.ignore()

    def _drag_move_event(self, event: QDragMoveEvent) -> None:
        """Handle drag move event - differentiate visual feedback by MIME type."""
        mime_data = event.mimeData()
        if mime_data is None:  # type: ignore[reportUnnecessaryComparison]
            event.ignore()
            return

        pos = event.position().toPoint()

        # Game frame drop: highlight entire row
        if mime_data.hasFormat(MIME_GAME_FRAME):
            self._clear_insert_indicator()
            item = self._table.itemAt(pos)
            if item is not None:
                new_target = item.row()
                if new_target != self._drop_target_row:
                    self._clear_drop_highlight()
                    self._drop_target_row = new_target
                    self._set_row_highlight(new_target, True)
                event.acceptProposedAction()
            else:
                self._clear_drop_highlight()
                event.ignore()
            return

        # Reorder drop: show insertion line between rows
        if mime_data.hasFormat(MIME_AI_FRAME_REORDER):
            self._clear_drop_highlight()
            insert_index = self._get_insert_index_at_pos(pos)
            if insert_index != self._drop_insert_index:
                self._drop_insert_index = insert_index
                self._table.viewport().update()  # Trigger repaint for insertion line
            event.acceptProposedAction()
            return

        event.ignore()

    def _drag_leave_event(self, event: QDragLeaveEvent) -> None:
        """Handle drag leave event."""
        self._clear_drop_highlight()
        self._clear_insert_indicator()

    def _drop_event(self, event: QDropEvent) -> None:
        """Handle drop event - route to appropriate handler by MIME type."""
        self._clear_drop_highlight()
        self._clear_insert_indicator()

        mime_data = event.mimeData()
        if mime_data is None:  # type: ignore[reportUnnecessaryComparison]
            event.ignore()
            return

        if mime_data.hasFormat(MIME_AI_FRAME_REORDER):
            self._handle_reorder_drop(event)
            return

        if mime_data.hasFormat(MIME_GAME_FRAME):
            self._handle_link_drop(event)
            return

        event.ignore()

    def _set_row_highlight(self, row: int, highlighted: bool) -> None:
        """Set or clear highlight for a row."""
        for col in range(self._table.columnCount()):
            item = self._table.item(row, col)
            if item is not None:
                if highlighted:
                    item.setBackground(QBrush(QColor(60, 100, 140)))
                else:
                    item.setBackground(QBrush())

    def _clear_drop_highlight(self) -> None:
        """Clear any drop highlight."""
        if self._drop_target_row is not None:
            self._set_row_highlight(self._drop_target_row, False)
            self._drop_target_row = None

    def _clear_insert_indicator(self) -> None:
        """Clear the insertion line indicator."""
        if self._drop_insert_index is not None:
            self._drop_insert_index = None
            self._table.viewport().update()

    def _get_insert_index_at_pos(self, pos: QPoint) -> int:
        """Calculate the insertion index based on cursor position.

        If cursor is in top half of a row, insert before that row.
        If in bottom half, insert after. Returns valid index 0..rowCount.
        """
        row_count = self._table.rowCount()
        if row_count == 0:
            return 0

        item = self._table.itemAt(pos)
        if item is None:
            # Below all rows - insert at end
            return row_count

        row = item.row()
        # Get row geometry
        row_rect = self._table.visualItemRect(item)
        row_mid = row_rect.top() + row_rect.height() // 2

        if pos.y() < row_mid:
            return row
        else:
            return row + 1

    def _mouse_press_event(self, event: QMouseEvent) -> None:
        """Handle mouse press - record drag start position."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            item = self._table.itemAt(self._drag_start_pos)
            if item is not None:
                self._drag_source_row = item.row()
        # Call default to maintain selection behavior
        QTableWidget.mousePressEvent(self._table, event)

    def _mouse_move_event(self, event: QMouseEvent) -> None:
        """Handle mouse move - initiate drag if threshold exceeded."""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._drag_start_pos is None or self._drag_source_row is None:
            return

        # Check drag threshold
        distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if distance < 10:  # Standard drag threshold
            return

        # Get the AI frame ID from the source row
        checkbox_item = self._table.item(self._drag_source_row, 0)
        if checkbox_item is None:
            return
        ai_frame_id = checkbox_item.data(Qt.ItemDataRole.UserRole + 1)
        if ai_frame_id is None:
            return

        # Create MIME data for reorder
        mime_data = QMimeData()
        mime_data.setData(MIME_AI_FRAME_REORDER, ai_frame_id.encode("utf-8"))

        # Create drag with visual feedback
        drag = QDrag(self._table)
        drag.setMimeData(mime_data)

        # Create drag pixmap (small indicator showing row number)
        pixmap = QPixmap(50, 20)
        pixmap.fill(QColor(60, 100, 140, 200))
        painter = QPainter(pixmap)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, f"#{self._drag_source_row + 1}")
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(25, 10))

        # Execute drag
        drag.exec(Qt.DropAction.MoveAction)

        # Clear state
        self._drag_start_pos = None
        self._drag_source_row = None

    def _handle_reorder_drop(self, event: QDropEvent) -> None:
        """Handle drop for row reordering."""
        mime_data = event.mimeData()
        if mime_data is None:  # type: ignore[reportUnnecessaryComparison]
            event.ignore()
            return

        # Get source AI frame ID
        raw_data = mime_data.data(MIME_AI_FRAME_REORDER).data()
        ai_frame_id = (
            raw_data.tobytes().decode("utf-8") if isinstance(raw_data, memoryview) else raw_data.decode("utf-8")
        )

        # Calculate target index
        pos = event.position().toPoint()
        target_index = self._get_insert_index_at_pos(pos)

        # Find source index to adjust for shifting
        source_index = -1
        for row in range(self._table.rowCount()):
            checkbox_item = self._table.item(row, 0)
            if checkbox_item and checkbox_item.data(Qt.ItemDataRole.UserRole + 1) == ai_frame_id:
                source_index = row
                break

        if source_index == -1:
            event.ignore()
            return

        # Adjust target if dropping after source (index will shift after removal)
        if target_index > source_index:
            target_index -= 1

        # Emit signal (controller handles the actual reorder)
        self.row_reorder_requested.emit(ai_frame_id, target_index)
        event.acceptProposedAction()

    def _handle_link_drop(self, event: QDropEvent) -> None:
        """Handle drop for linking game frame to AI frame (original behavior)."""
        mime_data = event.mimeData()
        if mime_data is None or not mime_data.hasFormat(MIME_GAME_FRAME):  # type: ignore[reportUnnecessaryComparison]
            event.ignore()
            return

        pos = event.position().toPoint()
        item = self._table.itemAt(pos)
        if item is None:
            event.ignore()
            return

        row = item.row()
        checkbox_item = self._table.item(row, 0)
        if checkbox_item is None:
            event.ignore()
            return

        ai_frame_id = checkbox_item.data(Qt.ItemDataRole.UserRole + 1)
        if ai_frame_id is None:
            event.ignore()
            return

        # Get game frame ID from MIME data
        raw_data = mime_data.data(MIME_GAME_FRAME).data()
        game_frame_id = (
            raw_data.tobytes().decode("utf-8") if isinstance(raw_data, memoryview) else raw_data.decode("utf-8")
        )

        self.drop_game_frame_requested.emit(ai_frame_id, game_frame_id)
        event.acceptProposedAction()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        """Event filter to paint insertion indicator on viewport."""
        from PySide6.QtGui import QPaintEvent

        if watched == self._table.viewport() and isinstance(event, QPaintEvent):
            # Let normal painting happen first
            result = super().eventFilter(watched, event)
            # Then draw our indicator on top
            self._draw_insert_indicator()
            return result
        return super().eventFilter(watched, event)

    def _draw_insert_indicator(self) -> None:
        """Draw horizontal line at insertion point during reorder drag."""
        if self._drop_insert_index is None:
            return

        viewport = self._table.viewport()
        painter = QPainter(viewport)
        pen = QPen(QColor(100, 180, 255), 2)
        painter.setPen(pen)

        # Calculate Y position for the line
        row_count = self._table.rowCount()
        if row_count == 0:
            y = 0
        elif self._drop_insert_index >= row_count:
            # After last row
            last_item = self._table.item(row_count - 1, 0)
            if last_item:
                rect = self._table.visualItemRect(last_item)
                y = rect.bottom()
            else:
                y = viewport.height()
        else:
            # Before a specific row
            item = self._table.item(self._drop_insert_index, 0)
            if item:
                rect = self._table.visualItemRect(item)
                y = rect.top()
            else:
                y = 0

        # Draw horizontal line across viewport
        painter.drawLine(0, y, viewport.width(), y)
        painter.end()

    @signal_error_boundary()
    def _on_select_all(self) -> None:
        """Check all mapped frames for injection."""
        if self._project is None:
            return

        # Collect mapped frame IDs and update selection state
        mapped_ids: set[str] = set()
        with block_signals(self._table):
            for row in range(self._table.rowCount()):
                checkbox_item = self._table.item(row, 0)
                if checkbox_item:
                    ai_frame_id = checkbox_item.data(Qt.ItemDataRole.UserRole + 1)
                    # Only check mapped frames (use ID-based lookup)
                    if ai_frame_id and self._project.get_mapping_for_ai_frame(ai_frame_id):
                        checkbox_item.setCheckState(Qt.CheckState.Checked)
                        mapped_ids.add(ai_frame_id)

        self._selection_state.select_all(mapped_ids)
        self._update_inject_selected_state()

    @signal_error_boundary()
    def _on_deselect_all(self) -> None:
        """Uncheck all frames."""
        with block_signals(self._table):
            for row in range(self._table.rowCount()):
                checkbox_item = self._table.item(row, 0)
                if checkbox_item:
                    checkbox_item.setCheckState(Qt.CheckState.Unchecked)

        self._selection_state.deselect_all()
        self._update_inject_selected_state()

    @signal_error_boundary()
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Handle item changes (checkbox state changes)."""
        # Only care about checkbox column (column 0)
        if item.column() == 0:
            ai_frame_id = item.data(Qt.ItemDataRole.UserRole + 1)
            if ai_frame_id is not None:
                # First user interaction captures baseline state
                is_tracking = self._selection_state.is_tracking_user_selections()
                logger.debug(
                    "_on_item_changed: ai_frame_id=%s, is_tracking=%s",
                    ai_frame_id,
                    is_tracking,
                )
                if not is_tracking:
                    captured = self._capture_checkbox_state()
                    logger.debug("_on_item_changed: calling set_baseline with %s", captured)
                    self._selection_state.set_baseline(captured)

                # Update tracked state
                checked = item.checkState() == Qt.CheckState.Checked
                self._selection_state.toggle_checked(ai_frame_id, checked)

            self._update_inject_selected_state()

    def _capture_checkbox_state(self) -> set[str]:
        """Capture current checkbox state as a set of checked AI frame IDs.

        Returns:
            Set of AI frame IDs (filenames) that are currently checked.
        """
        checked_ids: set[str] = set()
        for row in range(self._table.rowCount()):
            checkbox_item = self._table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                ai_frame_id = checkbox_item.data(Qt.ItemDataRole.UserRole + 1)
                if ai_frame_id is not None:
                    checked_ids.add(ai_frame_id)
        return checked_ids

    @signal_error_boundary()
    def _on_inject_selected_clicked(self) -> None:
        """Handle inject selected button click."""
        self.inject_selected_requested.emit()

    def _update_inject_selected_state(self) -> None:
        """Update the inject selected button enabled state."""
        selected_count = len(self.get_selected_for_injection())
        self._inject_selected_btn.setEnabled(selected_count > 0)
        if selected_count > 0:
            self._inject_selected_btn.setText(f"Inject Selected ({selected_count})")
        else:
            self._inject_selected_btn.setText("Inject Selected")

    def get_selected_for_injection(self) -> list[str]:
        """Get list of AI frame IDs that are checked and mapped.

        Returns:
            List of AI frame IDs selected for injection.
        """
        if self._project is None:
            return []

        selected: list[str] = []
        for row in range(self._table.rowCount()):
            checkbox_item = self._table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                ai_frame_id = checkbox_item.data(Qt.ItemDataRole.UserRole + 1)
                # Only include if actually mapped (use ID-based lookup)
                if ai_frame_id and self._project.get_mapping_for_ai_frame(ai_frame_id):
                    selected.append(ai_frame_id)
        return selected
