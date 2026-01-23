"""AI Frames Pane for displaying and selecting AI-generated sprite frames."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame

logger = get_logger(__name__)

# Thumbnail size for list items
THUMBNAIL_SIZE = 64

# Status colors for AI frame mapping status
STATUS_COLORS = {
    "unmapped": QColor(180, 180, 180),  # Light gray
    "mapped": QColor(76, 175, 80),  # Green
    "edited": QColor(33, 150, 243),  # Blue
    "injected": QColor(156, 39, 176),  # Purple
}


class AIFramesPane(QWidget):
    """Left pane for browsing AI-generated frames.

    Displays a list of AI frames with thumbnails, search, and filter controls.
    Rows are 1:1 with AI frames - they cannot be created/deleted independently.

    Signals:
        ai_frame_selected: Emitted when an AI frame is selected (index)
        map_requested: Emitted when user clicks the Map Selected button
        auto_advance_changed: Emitted when auto-advance toggle changes
        edit_in_sprite_editor_requested: Emitted when user requests to edit (index)
        remove_from_project_requested: Emitted when user requests removal (index)
    """

    ai_frame_selected = Signal(str)  # AI frame ID (filename)
    map_requested = Signal()  # User wants to map selected frames
    auto_advance_changed = Signal(bool)  # Auto-advance toggle state changed
    edit_in_sprite_editor_requested = Signal(int)  # AI frame index
    remove_from_project_requested = Signal(int)  # AI frame index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ai_frames: list[AIFrame] = []
        self._mapping_status: dict[int, str] = {}  # ai_frame_index -> status
        self._show_unmapped_only = False
        self._search_text: str = ""

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        title = QLabel("AI Frames")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(title)

        # Search box
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search...")
        self._search_box.setStyleSheet("font-size: 11px;")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_box)

        # Filter row
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)

        self._count_label = QLabel("No frames")
        self._count_label.setStyleSheet("color: #888; font-size: 10px;")
        filter_layout.addWidget(self._count_label)

        filter_layout.addStretch()

        self._unmapped_filter = QCheckBox("Unmapped")
        self._unmapped_filter.setToolTip("Show only unmapped AI frames")
        self._unmapped_filter.setStyleSheet("font-size: 10px;")
        self._unmapped_filter.toggled.connect(self._on_filter_changed)
        filter_layout.addWidget(self._unmapped_filter)

        layout.addLayout(filter_layout)

        # List widget
        self._list = QListWidget()
        self._list.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self._list.setViewMode(QListWidget.ViewMode.ListMode)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.setDragEnabled(False)  # AI frames are not draggable (they ARE rows)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list, 1)

        # Bottom controls
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(4)

        self._auto_advance_checkbox = QCheckBox("Auto-advance")
        self._auto_advance_checkbox.setToolTip("Auto-select next unmapped frame after linking")
        self._auto_advance_checkbox.setStyleSheet("font-size: 10px;")
        self._auto_advance_checkbox.setChecked(False)
        self._auto_advance_checkbox.toggled.connect(self.auto_advance_changed.emit)
        bottom_layout.addWidget(self._auto_advance_checkbox)

        bottom_layout.addStretch()

        self._map_button = QPushButton("Map Selected")
        self._map_button.setToolTip("Link selected AI frame to selected game capture")
        self._map_button.setEnabled(False)
        self._map_button.clicked.connect(self.map_requested.emit)
        bottom_layout.addWidget(self._map_button)

        layout.addLayout(bottom_layout)

    def set_ai_frames(self, frames: list[AIFrame]) -> None:
        """Set the AI frames to display.

        Args:
            frames: List of AIFrame objects
        """
        # Only emit signal if frame list actually changed (new objects, different length, etc.)
        is_frame_list_change = frames is not self._ai_frames or len(frames) != len(self._ai_frames)
        self._ai_frames = frames
        self._refresh_list(is_frame_list_change=is_frame_list_change)
        logger.debug("Loaded %d AI frames into pane", len(frames))

    def set_mapping_status(self, status_map: dict[int, str]) -> None:
        """Update the mapping status for AI frames.

        Args:
            status_map: Dictionary mapping AI frame index to status string
        """
        self._mapping_status = status_map
        self._refresh_list(is_frame_list_change=False)

    def get_selected_index(self) -> int | None:
        """Get the currently selected AI frame index.

        Note: Prefer get_selected_id() for stable references across reloads.
        """
        current = self._list.currentItem()
        if current is None:  # type: ignore[reportUnnecessaryComparison]
            return None
        return current.data(Qt.ItemDataRole.UserRole + 1)

    def get_selected_id(self) -> str | None:
        """Get the currently selected AI frame ID (filename).

        This is the preferred method as IDs are stable across reloads/reordering.
        """
        current = self._list.currentItem()
        if current is None:  # type: ignore[reportUnnecessaryComparison]
            return None
        return current.data(Qt.ItemDataRole.UserRole)

    def select_frame(self, index: int) -> None:
        """Programmatically select an AI frame by index.

        Blocks signals to prevent feedback loops.
        Note: Prefer select_frame_by_id() for stable references across reloads.

        Args:
            index: The AI frame index to select
        """
        self._list.blockSignals(True)
        try:
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item is not None and item.data(Qt.ItemDataRole.UserRole + 1) == index:  # type: ignore[reportUnnecessaryComparison]
                    self._list.setCurrentRow(row)
                    self._list.scrollToItem(item)
                    break
        finally:
            self._list.blockSignals(False)

    def select_frame_by_id(self, frame_id: str) -> None:
        """Programmatically select an AI frame by ID (filename).

        Blocks signals to prevent feedback loops.
        This is the preferred method as IDs are stable across reloads/reordering.

        Args:
            frame_id: The AI frame ID (filename) to select
        """
        self._list.blockSignals(True)
        try:
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == frame_id:  # type: ignore[reportUnnecessaryComparison]
                    self._list.setCurrentRow(row)
                    self._list.scrollToItem(item)
                    break
        finally:
            self._list.blockSignals(False)

    def clear(self) -> None:
        """Clear all AI frames."""
        self._ai_frames = []
        self._mapping_status = {}
        self._list.clear()
        self._count_label.setText("No frames")

    def set_map_button_enabled(self, enabled: bool) -> None:
        """Set the enabled state of the Map Selected button."""
        self._map_button.setEnabled(enabled)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._search_text = text.lower()
        self._refresh_list()

    def _on_filter_changed(self, checked: bool) -> None:
        """Handle filter checkbox toggle."""
        self._show_unmapped_only = checked
        self._refresh_list()

    def _on_selection_changed(self, row: int) -> None:
        """Handle AI frame selection change."""
        if row < 0:
            # Phase 4 fix: Notify listeners of cleared selection
            self.ai_frame_selected.emit("")
            return
        item = self._list.item(row)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return
        frame_id = item.data(Qt.ItemDataRole.UserRole)
        if frame_id is not None:
            self.ai_frame_selected.emit(frame_id)

    def _on_context_menu(self, pos: object) -> None:
        """Show context menu for AI frames."""
        from PySide6.QtCore import QPoint

        if not isinstance(pos, QPoint):
            return

        item = self._list.itemAt(pos)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return

        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return

        menu = QMenu(self)

        edit_action = menu.addAction("Edit in Sprite Editor")
        edit_action.triggered.connect(lambda: self.edit_in_sprite_editor_requested.emit(index))

        menu.addSeparator()

        remove_action = menu.addAction("Remove from Project")
        remove_action.triggered.connect(lambda: self.remove_from_project_requested.emit(index))

        menu.exec(self._list.mapToGlobal(pos))

    def _refresh_list(self, is_frame_list_change: bool = False) -> None:
        """Refresh the list with current filter and search.

        Args:
            is_frame_list_change: If True (set_ai_frames), emit signal when selection
                is restored to notify workspace. If False (set_mapping_status), suppress
                signal to avoid spurious updates during status-only changes.
        """
        current_selection_id = self.get_selected_id()
        selection_restored = False
        restored_id: str | None = None

        self._list.blockSignals(True)
        try:
            self._list.clear()

            visible_count = 0
            total_count = len(self._ai_frames)

            for frame in self._ai_frames:
                status = self._mapping_status.get(frame.index, "unmapped")

                # Apply unmapped filter
                if self._show_unmapped_only and status != "unmapped":
                    continue

                # Apply search filter
                if self._search_text and self._search_text not in frame.path.name.lower():
                    continue

                visible_count += 1

                item = QListWidgetItem()
                # Add status indicator to text
                status_indicator = "●" if status != "unmapped" else "○"
                item.setText(f"{status_indicator} {frame.path.name}")
                # Store frame ID in UserRole (primary), index in UserRole+1 (backward compat)
                item.setData(Qt.ItemDataRole.UserRole, frame.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, frame.index)

                # Apply status color
                color = STATUS_COLORS.get(status, STATUS_COLORS["unmapped"])
                item.setForeground(QBrush(color))

                # Load thumbnail if file exists
                if frame.path.exists():
                    pixmap = QPixmap(str(frame.path))
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(
                            THUMBNAIL_SIZE,
                            THUMBNAIL_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        item.setIcon(QIcon(scaled))

                self._list.addItem(item)

            # Update count label
            if self._show_unmapped_only or self._search_text:
                self._count_label.setText(f"{visible_count}/{total_count}")
            else:
                self._count_label.setText(f"{total_count} frame{'s' if total_count != 1 else ''}")

            # Restore selection by ID (stable across reloads)
            if current_selection_id is not None:
                for row in range(self._list.count()):
                    item = self._list.item(row)
                    if item and item.data(Qt.ItemDataRole.UserRole) == current_selection_id:
                        self._list.setCurrentRow(row)
                        self._list.scrollToItem(item)
                        selection_restored = True
                        restored_id = current_selection_id
                        break

            if not selection_restored:
                self._list.setCurrentRow(-1)
                self._list.clearSelection()
        finally:
            self._list.blockSignals(False)

        # Phase 2 fix: Notify listeners if selection was silently restored during frame list change
        if is_frame_list_change and selection_restored and restored_id is not None:
            self.ai_frame_selected.emit(restored_id)
        # Bug #1 fix: Always emit empty string when selection was lost (filter/search/reload)
        elif current_selection_id is not None and not selection_restored:
            self.ai_frame_selected.emit("")
