"""Mapping Panel (Drawer) for viewing and managing frame mappings."""

from __future__ import annotations

import logging
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

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

logger = logging.getLogger(__name__)

# MIME type for drag-drop (must match captures_library_pane.py)
MIME_TYPE_GAME_FRAME = "application/x-spritepal-game-frame"

# Thumbnail size for table cells
THUMBNAIL_SIZE = 64

# Status colors
STATUS_COLORS = {
    "unmapped": QColor(128, 128, 128),  # Gray
    "mapped": QColor(76, 175, 80),  # Green
    "edited": QColor(33, 150, 243),  # Blue
    "injected": QColor(156, 39, 176),  # Purple
}


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

    mapping_selected = Signal(int)  # AI frame index
    edit_frame_requested = Signal(int)  # AI frame index
    remove_mapping_requested = Signal(int)  # AI frame index
    adjust_alignment_requested = Signal(int)  # AI frame index
    drop_game_frame_requested = Signal(int, str)  # AI frame index, game frame ID
    inject_mapping_requested = Signal(int)  # AI frame index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: FrameMappingProject | None = None
        self._game_frame_previews: dict[str, QPixmap] = {}
        self._drop_target_row: int | None = None
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

        # Mapping table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["#", "AI Frame", "Game Frame", "Offset", "Flip", "Status"])
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
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # #
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # AI Frame
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Game Frame
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Offset
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Flip
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Status

        # Set row height for thumbnails
        self._table.verticalHeader().setDefaultSectionSize(THUMBNAIL_SIZE + 8)
        self._table.verticalHeader().setVisible(False)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table, 1)

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

        Args:
            project: FrameMappingProject or None to clear
        """
        self._project = project
        self.refresh()

    def set_game_frame_previews(self, previews: dict[str, QPixmap]) -> None:
        """Set the game frame preview pixmaps for thumbnail display.

        Args:
            previews: Mapping of game_frame_id -> QPixmap
        """
        self._game_frame_previews = previews

    def refresh(self) -> None:
        """Refresh the mapping table from the current project."""
        # Store current selection before clearing
        current_selection = self.get_selected_ai_frame_index()

        # Block signals during rebuild to prevent spurious selection events
        self._table.blockSignals(True)
        try:
            self._table.setRowCount(0)

            if self._project is None:
                self._status_label.setText("No project")
                return

            # Show all AI frames with their mapping status
            for ai_frame in self._project.ai_frames:
                row = self._table.rowCount()
                self._table.insertRow(row)

                # # column (row number)
                num_item = QTableWidgetItem(str(ai_frame.index + 1))
                num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 0, num_item)

                # AI Frame column with thumbnail
                ai_item = QTableWidgetItem(ai_frame.path.name)
                ai_item.setData(Qt.ItemDataRole.UserRole, ai_frame.index)
                # Load thumbnail
                if ai_frame.path.exists():
                    pixmap = QPixmap(str(ai_frame.path))
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(
                            THUMBNAIL_SIZE,
                            THUMBNAIL_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        ai_item.setIcon(QIcon(scaled))
                self._table.setItem(row, 1, ai_item)

                # Game Frame column
                mapping = self._project.get_mapping_for_ai_frame(ai_frame.index)
                if mapping:
                    game_item = QTableWidgetItem(mapping.game_frame_id)
                    status = mapping.status

                    # Load game frame thumbnail
                    if mapping.game_frame_id in self._game_frame_previews:
                        pixmap = self._game_frame_previews[mapping.game_frame_id]
                        scaled = pixmap.scaled(
                            THUMBNAIL_SIZE,
                            THUMBNAIL_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        game_item.setIcon(QIcon(scaled))

                    # Offset column
                    if mapping.offset_x != 0 or mapping.offset_y != 0:
                        offset_item = QTableWidgetItem(f"({mapping.offset_x}, {mapping.offset_y})")
                    else:
                        offset_item = QTableWidgetItem("—")

                    # Flip column
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

                self._table.setItem(row, 2, game_item)
                offset_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 3, offset_item)
                flip_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 4, flip_item)

                # Status column with color and indicator
                status_indicator = "●" if status != "unmapped" else "○"
                status_item = QTableWidgetItem(f"{status_indicator} {status.capitalize()}")
                color = STATUS_COLORS.get(status, STATUS_COLORS["unmapped"])
                status_item.setForeground(QBrush(color))
                self._table.setItem(row, 5, status_item)

            # Update status summary
            mapped = self._project.mapped_count
            total = self._project.total_ai_frames
            self._status_label.setText(f"{mapped}/{total} mapped")

        finally:
            self._table.blockSignals(False)

        # Restore selection (outside try/finally so signals fire normally if needed)
        if current_selection is not None:
            self.select_row_by_ai_index(current_selection)

    def get_selected_ai_frame_index(self) -> int | None:
        """Get the AI frame index of the selected mapping row."""
        selected = self._table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        ai_item = self._table.item(row, 1)  # AI Frame column
        if ai_item is None:
            return None
        return ai_item.data(Qt.ItemDataRole.UserRole)

    def select_row_by_ai_index(self, ai_index: int) -> None:
        """Select a row by AI frame index.

        Blocks signals to prevent feedback loops.

        Args:
            ai_index: AI frame index to select
        """
        self._table.blockSignals(True)
        try:
            for row in range(self._table.rowCount()):
                ai_item = self._table.item(row, 1)
                if ai_item is not None and ai_item.data(Qt.ItemDataRole.UserRole) == ai_index:
                    self._table.selectRow(row)
                    self._table.scrollToItem(ai_item)
                    break
        finally:
            self._table.blockSignals(False)

    def _on_selection_changed(self) -> None:
        """Handle selection change in the mapping table."""
        ai_index = self.get_selected_ai_frame_index()
        if ai_index is None:
            self._edit_button.setEnabled(False)
            self._align_button.setEnabled(False)
            self._remove_button.setEnabled(False)
            self._inject_button.setEnabled(False)
            return

        # Check if there's a mapping for this frame
        has_mapping = False
        if self._project:
            mapping = self._project.get_mapping_for_ai_frame(ai_index)
            has_mapping = mapping is not None

        self._edit_button.setEnabled(True)  # Can always edit AI frame
        self._align_button.setEnabled(has_mapping)
        self._remove_button.setEnabled(has_mapping)
        self._inject_button.setEnabled(has_mapping)
        self.mapping_selected.emit(ai_index)

    def _on_edit_clicked(self) -> None:
        """Handle edit button click."""
        ai_index = self.get_selected_ai_frame_index()
        if ai_index is not None:
            self.edit_frame_requested.emit(ai_index)

    def _on_remove_clicked(self) -> None:
        """Handle remove button click."""
        ai_index = self.get_selected_ai_frame_index()
        if ai_index is not None:
            self.remove_mapping_requested.emit(ai_index)

    def _on_align_clicked(self) -> None:
        """Handle adjust alignment button click."""
        ai_index = self.get_selected_ai_frame_index()
        if ai_index is not None:
            self.adjust_alignment_requested.emit(ai_index)

    def _on_inject_clicked(self) -> None:
        """Handle inject button click."""
        ai_index = self.get_selected_ai_frame_index()
        if ai_index is not None:
            self.inject_mapping_requested.emit(ai_index)

    def _on_context_menu(self, pos: QPoint) -> None:
        """Show context menu for mappings."""
        item = self._table.itemAt(pos)
        if item is None:
            return

        row = item.row()
        ai_item = self._table.item(row, 1)
        if ai_item is None:
            return

        ai_index = ai_item.data(Qt.ItemDataRole.UserRole)
        if ai_index is None:
            return

        has_mapping = False
        if self._project:
            mapping = self._project.get_mapping_for_ai_frame(ai_index)
            has_mapping = mapping is not None

        menu = QMenu(self)

        edit_action = menu.addAction("Edit AI Frame")
        edit_action.triggered.connect(lambda: self.edit_frame_requested.emit(ai_index))

        if has_mapping:
            align_action = menu.addAction("Adjust Alignment")
            align_action.triggered.connect(lambda: self.adjust_alignment_requested.emit(ai_index))

            menu.addSeparator()

            remove_action = menu.addAction("Remove Mapping")
            remove_action.triggered.connect(lambda: self.remove_mapping_requested.emit(ai_index))

            menu.addSeparator()

            inject_action = menu.addAction("Inject to ROM")
            inject_action.triggered.connect(lambda: self.inject_mapping_requested.emit(ai_index))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _drag_enter_event(self, event: QDragEnterEvent) -> None:
        """Handle drag enter event."""
        mime_data = event.mimeData()
        if mime_data is not None and mime_data.hasFormat(MIME_TYPE_GAME_FRAME):  # type: ignore[reportUnnecessaryComparison]
            event.acceptProposedAction()
        else:
            event.ignore()

    def _drag_move_event(self, event: QDragMoveEvent) -> None:
        """Handle drag move event - highlight target row."""
        mime_data = event.mimeData()
        if mime_data is None or not mime_data.hasFormat(MIME_TYPE_GAME_FRAME):  # type: ignore[reportUnnecessaryComparison]
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
        if mime_data is None or not mime_data.hasFormat(MIME_TYPE_GAME_FRAME):  # type: ignore[reportUnnecessaryComparison]
            event.ignore()
            return

        pos = event.position().toPoint()
        item = self._table.itemAt(pos)
        if item is None:
            event.ignore()
            return

        row = item.row()
        ai_item = self._table.item(row, 1)
        if ai_item is None:
            event.ignore()
            return

        ai_index = ai_item.data(Qt.ItemDataRole.UserRole)
        if ai_index is None:
            event.ignore()
            return

        # Get game frame ID from MIME data
        raw_data = mime_data.data(MIME_TYPE_GAME_FRAME).data()
        game_frame_id = (
            raw_data.tobytes().decode("utf-8") if isinstance(raw_data, memoryview) else raw_data.decode("utf-8")
        )

        # Emit signal for workspace to handle (including confirmation dialog)
        self.drop_game_frame_requested.emit(ai_index, game_frame_id)
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
