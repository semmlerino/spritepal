"""Mapping Panel (Drawer) for viewing and managing frame mappings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QIcon, QPixmap
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

from ui.common.mime_constants import MIME_GAME_FRAME
from ui.frame_mapping.services.thumbnail_service import (
    create_quantized_thumbnail,
    quantize_qpixmap,
)
from ui.frame_mapping.views.status_colors import get_status_color
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject, SheetPalette

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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: FrameMappingProject | None = None
        self._game_frame_previews: dict[str, QPixmap] = {}
        self._drop_target_row: int | None = None
        # Track user-toggled checkbox state by AI frame ID (stable across reloads)
        # None = use default (checked if mapped), set = explicit user choices
        self._user_checked_ai_frame_ids: set[str] | None = None
        # Sheet palette for quantized AI frame thumbnails
        self._sheet_palette: SheetPalette | None = None
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

        # Enable drag-drop
        self._table.setAcceptDrops(True)
        self._table.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self._table.viewport().setAcceptDrops(True)

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

    def set_project(self, project: FrameMappingProject | None) -> None:
        """Set the project to display mappings from.

        Does NOT call refresh() - caller controls refresh timing to prevent
        double refresh when project_changed signal triggers both set_project
        and _update_mapping_panel_previews.

        Args:
            project: FrameMappingProject or None to clear
        """
        self._project = project
        # Reset checkbox state when loading a new project
        self._user_checked_ai_frame_ids = None

    def set_game_frame_previews(self, previews: dict[str, QPixmap]) -> None:
        """Set the game frame preview pixmaps for thumbnail display.

        Args:
            previews: Mapping of game_frame_id -> QPixmap
        """
        self._game_frame_previews = previews

    def update_game_frame_preview(self, frame_id: str, preview: QPixmap) -> None:
        """Update the preview for a single game frame.

        Args:
            frame_id: The game frame ID
            preview: The new preview QPixmap
        """
        self._game_frame_previews[frame_id] = preview
        self.refresh()

    def set_sheet_palette(self, palette: SheetPalette | None) -> None:
        """Set the sheet palette for quantized AI frame thumbnails.

        When set, AI frame thumbnails will be quantized to show how they'll
        look when injected with this palette.

        Args:
            palette: SheetPalette to use, or None to show original colors
        """
        self._sheet_palette = palette
        # Refresh to apply new palette to thumbnails
        self.refresh()

    def refresh(self) -> None:
        """Refresh the mapping table from the current project."""
        # Store current selection by ID (stable across reordering)
        current_selection_id = self.get_selected_ai_frame_id()

        # Capture current checkbox state by AI frame ID (stable across index changes)
        # Only capture if user has modified checkboxes (_user_checked_ai_frame_ids is not None)
        # or if there's existing data to preserve
        if self._project is not None and self._table.rowCount() > 0:
            captured_checked_ids = self._capture_checkbox_state()
            # Once user has interacted with checkboxes, preserve their choices
            if self._user_checked_ai_frame_ids is not None:
                # Update with any new checked items, remove unchecked items
                self._user_checked_ai_frame_ids = captured_checked_ids
            # Note: if _user_checked_ai_frame_ids is None, we use default behavior
            # (checked = mapped) until user explicitly changes a checkbox

        # Block signals during rebuild to prevent spurious selection events
        self._table.blockSignals(True)
        try:
            self._table.setRowCount(0)

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

                # Determine checkbox state:
                # - If user has toggled checkboxes, use their explicit choices
                # - Otherwise, default to checked if mapped
                if self._user_checked_ai_frame_ids is not None:
                    should_check = ai_frame.id in self._user_checked_ai_frame_ids
                else:
                    should_check = is_mapped

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
                ai_item = QTableWidgetItem(ai_frame.path.name)
                ai_item.setData(Qt.ItemDataRole.UserRole, ai_frame.index)
                # Also store AI frame ID for ID-based lookups
                ai_item.setData(Qt.ItemDataRole.UserRole + 1, ai_frame.id)
                # Load thumbnail (palette-quantized if sheet palette is set)
                thumbnail = create_quantized_thumbnail(ai_frame.path, self._sheet_palette, THUMBNAIL_SIZE)
                if thumbnail is not None:
                    ai_item.setIcon(QIcon(thumbnail))
                self._table.setItem(row, 2, ai_item)

                # Game Frame column - column 3
                if mapping:
                    game_item = QTableWidgetItem(mapping.game_frame_id)
                    status = mapping.status

                    # Load game frame thumbnail (P3 fix: apply palette quantization)
                    if mapping.game_frame_id in self._game_frame_previews:
                        pixmap = self._game_frame_previews[mapping.game_frame_id]
                        # Quantize to sheet palette if set (shows preview-accurate colors)
                        pixmap = quantize_qpixmap(pixmap, self._sheet_palette)
                        scaled = pixmap.scaled(
                            THUMBNAIL_SIZE,
                            THUMBNAIL_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
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

        finally:
            self._table.blockSignals(False)

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

    def select_row_by_ai_index(self, ai_index: int) -> None:
        """Select a row by AI frame index.

        Blocks signals to prevent feedback loops.

        Args:
            ai_index: AI frame index to select
        """
        self._table.blockSignals(True)
        try:
            for row in range(self._table.rowCount()):
                ai_item = self._table.item(row, 2)  # AI Frame column (shifted due to checkbox)
                if ai_item is not None and ai_item.data(Qt.ItemDataRole.UserRole) == ai_index:
                    self._table.selectRow(row)
                    self._table.scrollToItem(ai_item)
                    break
        finally:
            self._table.blockSignals(False)
        # Update button states since signals were blocked during selection
        self._update_button_states()

    def select_row_by_ai_id(self, ai_frame_id: str) -> None:
        """Select a row by AI frame ID (filename).

        Blocks signals to prevent feedback loops.
        This is the preferred method as IDs are stable across reloads/reordering.

        Args:
            ai_frame_id: AI frame ID (filename) to select
        """
        self._table.blockSignals(True)
        try:
            for row in range(self._table.rowCount()):
                checkbox_item = self._table.item(row, 0)  # Checkbox column stores ID in UserRole+1
                if checkbox_item is not None and checkbox_item.data(Qt.ItemDataRole.UserRole + 1) == ai_frame_id:
                    self._table.selectRow(row)
                    self._table.scrollToItem(checkbox_item)
                    break
        finally:
            self._table.blockSignals(False)
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

    def clear_selection(self) -> None:
        """Clear the current table selection.

        Blocks signals to prevent feedback loops.
        """
        self._table.blockSignals(True)
        try:
            self._table.clearSelection()
        finally:
            self._table.blockSignals(False)
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

    def _on_selection_changed(self) -> None:
        """Handle selection change in the mapping table."""
        self._update_button_states()
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is not None:
            self.mapping_selected.emit(ai_frame_id)

    def _on_edit_clicked(self) -> None:
        """Handle edit button click."""
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is not None:
            self.edit_frame_requested.emit(ai_frame_id)

    def _on_remove_clicked(self) -> None:
        """Handle remove button click."""
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is not None:
            self.remove_mapping_requested.emit(ai_frame_id)

    def _on_align_clicked(self) -> None:
        """Handle adjust alignment button click."""
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is not None:
            self.adjust_alignment_requested.emit(ai_frame_id)

    def _on_inject_clicked(self) -> None:
        """Handle inject button click."""
        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is not None:
            self.inject_mapping_requested.emit(ai_frame_id)

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
        edit_action.triggered.connect(lambda: self.edit_frame_requested.emit(ai_frame_id))

        if has_mapping:
            align_action = menu.addAction("Adjust Alignment")
            align_action.triggered.connect(lambda: self.adjust_alignment_requested.emit(ai_frame_id))

            menu.addSeparator()

            remove_action = menu.addAction("Remove Mapping")
            remove_action.triggered.connect(lambda: self.remove_mapping_requested.emit(ai_frame_id))

            menu.addSeparator()

            inject_action = menu.addAction("Inject to ROM")
            inject_action.triggered.connect(lambda: self.inject_mapping_requested.emit(ai_frame_id))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _drag_enter_event(self, event: QDragEnterEvent) -> None:
        """Handle drag enter event."""
        mime_data = event.mimeData()
        if mime_data is not None and mime_data.hasFormat(MIME_GAME_FRAME):  # type: ignore[reportUnnecessaryComparison]
            event.acceptProposedAction()
        else:
            event.ignore()

    def _drag_move_event(self, event: QDragMoveEvent) -> None:
        """Handle drag move event - highlight target row."""
        mime_data = event.mimeData()
        if mime_data is None or not mime_data.hasFormat(MIME_GAME_FRAME):  # type: ignore[reportUnnecessaryComparison]
            event.ignore()
            return

        pos = event.position().toPoint()
        item = self._table.itemAt(pos)

        if item is not None:
            new_target = item.row()
            if new_target != self._drop_target_row:
                # Clear previous highlight
                self._clear_drop_highlight()
                # Set new highlight
                self._drop_target_row = new_target
                self._set_row_highlight(new_target, True)
            event.acceptProposedAction()
        else:
            self._clear_drop_highlight()
            event.ignore()

    def _drag_leave_event(self, event: object) -> None:
        """Handle drag leave event."""
        self._clear_drop_highlight()

    def _drop_event(self, event: QDropEvent) -> None:
        """Handle drop event."""
        self._clear_drop_highlight()

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
        checkbox_item = self._table.item(row, 0)  # Checkbox column has ID
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

    def _on_select_all(self) -> None:
        """Check all mapped frames for injection."""
        if self._project is None:
            return

        # Initialize tracking if not already done
        if self._user_checked_ai_frame_ids is None:
            self._user_checked_ai_frame_ids = set()

        self._table.blockSignals(True)
        try:
            for row in range(self._table.rowCount()):
                checkbox_item = self._table.item(row, 0)
                if checkbox_item:
                    ai_frame_id = checkbox_item.data(Qt.ItemDataRole.UserRole + 1)
                    # Only check mapped frames (use ID-based lookup)
                    if ai_frame_id and self._project.get_mapping_for_ai_frame(ai_frame_id):
                        checkbox_item.setCheckState(Qt.CheckState.Checked)
                        self._user_checked_ai_frame_ids.add(ai_frame_id)
        finally:
            self._table.blockSignals(False)

        self._update_inject_selected_state()

    def _on_deselect_all(self) -> None:
        """Uncheck all frames."""
        # Initialize tracking and clear all
        self._user_checked_ai_frame_ids = set()

        self._table.blockSignals(True)
        try:
            for row in range(self._table.rowCount()):
                checkbox_item = self._table.item(row, 0)
                if checkbox_item:
                    checkbox_item.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._table.blockSignals(False)

        self._update_inject_selected_state()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Handle item changes (checkbox state changes)."""
        # Only care about checkbox column (column 0)
        if item.column() == 0:
            # User has explicitly toggled a checkbox - start tracking their choices
            if self._user_checked_ai_frame_ids is None:
                # First user interaction - capture current state as baseline
                self._user_checked_ai_frame_ids = self._capture_checkbox_state()
            else:
                # Update the tracked set based on this change
                ai_frame_id = item.data(Qt.ItemDataRole.UserRole + 1)
                if ai_frame_id is not None:
                    if item.checkState() == Qt.CheckState.Checked:
                        self._user_checked_ai_frame_ids.add(ai_frame_id)
                    else:
                        self._user_checked_ai_frame_ids.discard(ai_frame_id)
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

    def reset_checkbox_state(self) -> None:
        """Reset checkbox state to default (checked = mapped).

        Call this when loading a new project or when user wants to reset.
        """
        self._user_checked_ai_frame_ids = None
        self.refresh()

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
