"""Captures Library Pane for displaying Mesen capture frames."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import QMimeData, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.common.mime_constants import MIME_GAME_FRAME
from ui.frame_mapping.signal_error_handling import signal_error_boundary
from ui.frame_mapping.utils.signal_utils import block_signals
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import GameFrame

logger = get_logger(__name__)

# Thumbnail size for grid items
THUMBNAIL_SIZE = 64

# Status colors
STATUS_COLORS = {
    "unlinked": QColor(180, 180, 180),  # Light gray
    "linked": QColor(76, 175, 80),  # Green
}


class CapturesLibraryPane(QWidget):
    """Right pane for browsing Mesen capture frames.

    Displays a grid of game frame captures with thumbnails, search, and filter.
    Supports drag-and-drop to create mappings.

    Signals:
        game_frame_selected: Emitted when a game frame is selected (frame_id)
        edit_in_sprite_editor_requested: Emitted when user requests edit (frame_id)
        delete_capture_requested: Emitted when user requests deletion (frame_id)
        show_details_requested: Emitted when user wants to see details (frame_id)
        capture_rename_requested: Emitted when user wants to rename (frame_id, new_name)
    """

    game_frame_selected = Signal(str)
    """Emitted when user selects a game frame (capture) in the library.

    Args:
        game_frame_id: ID of the selected game frame

    Emitted by:
        - _on_selection_changed() → when user clicks list item

    Triggers:
        - FrameMappingWorkspace → updates mapping panel and workbench
    """

    edit_in_sprite_editor_requested = Signal(str)
    """Emitted when user requests to open a game frame in sprite editor.

    Args:
        game_frame_id: ID of the game frame to edit

    Emitted by:
        - _on_context_menu() → when user clicks context menu item

    Triggers:
        - FrameMappingWorkspace → opens sprite editor with frame
    """

    delete_capture_requested = Signal(str)
    """Emitted when user requests to delete a game frame from the project.

    Args:
        game_frame_id: ID of the game frame to delete

    Emitted by:
        - _on_context_menu() → when user clicks delete context menu item

    Triggers:
        - FrameMappingWorkspace → removes frame after confirmation
    """

    show_details_requested = Signal(str)
    """Emitted when user requests to see game frame details.

    Args:
        game_frame_id: ID of the game frame to show details for

    Emitted by:
        - _on_context_menu() → when user clicks details context menu item

    Triggers:
        - FrameMappingWorkspace → shows frame details dialog
    """

    capture_rename_requested = Signal(str, str)
    """Emitted when user renames a game frame's display name.

    Part of capture organization support.

    Args:
        game_frame_id: ID of the game frame being renamed
        new_display_name: New display name (or empty string to clear)

    Emitted by:
        - _on_context_menu() → after user edits in dialog

    Triggers:
        - FrameMappingWorkspace → updates frame display name
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._game_frames: list[GameFrame] = []
        self._game_frame_previews: dict[str, QPixmap] = {}  # game_frame_id -> preview pixmap
        self._link_status: dict[str, str | None] = {}  # game_frame_id -> ai_frame_id or None
        self._show_unlinked_only = False
        self._search_text: str = ""

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        title = QLabel("Captures Library")
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

        self._count_label = QLabel("No captures")
        self._count_label.setStyleSheet("color: #888; font-size: 10px;")
        filter_layout.addWidget(self._count_label)

        filter_layout.addStretch()

        self._unlinked_filter = QCheckBox("Unlinked")
        self._unlinked_filter.setToolTip("Show only unlinked captures")
        self._unlinked_filter.setStyleSheet("font-size: 10px;")
        self._unlinked_filter.toggled.connect(self._on_filter_changed)
        filter_layout.addWidget(self._unlinked_filter)

        layout.addLayout(filter_layout)

        # Grid/List widget with drag support
        self._list = QListWidget()
        self._list.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self._list.setViewMode(QListWidget.ViewMode.IconMode)  # Grid view
        # Set grid size to prevent overlapping: icon + padding for text label
        self._list.setGridSize(QSize(THUMBNAIL_SIZE + 24, THUMBNAIL_SIZE + 44))
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setSpacing(4)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.setDragEnabled(True)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Enhanced styling for selection visibility (matching AIFramesPane)
        from ui.styles.theme import COLORS

        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS["darker_gray"]};
                border: 1px solid {COLORS["border"]};
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px;
                border-radius: 4px;
                margin: 2px;
            }}
            QListWidget::item:selected {{
                background-color: {COLORS["highlight"]};
                color: white;
                border: 1px solid {COLORS["highlight_border"]};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {COLORS["surface_hover"]};
            }}
        """)
        layout.addWidget(self._list, 1)

        # Override startDrag to provide custom MIME data
        self._list.startDrag = self._start_drag

    def set_game_frames(self, frames: list[GameFrame]) -> None:
        """Set the game frames to display.

        Args:
            frames: List of GameFrame objects
        """
        self._game_frames = frames
        self._refresh_list()

    def set_link_status(self, link_status: dict[str, str | None]) -> None:
        """Set the link status for game frames.

        Args:
            link_status: Mapping of game_frame_id -> ai_frame_id (or None if unlinked)
        """
        self._link_status = link_status
        self._refresh_list()

    def set_game_frames_with_link_status(self, frames: list[GameFrame], link_status: dict[str, str | None]) -> None:
        """Set frames and link status together (single rebuild)."""
        self._game_frames = frames
        self._link_status = link_status
        self._refresh_list()

    def update_single_item_link_status(self, game_frame_id: str, linked_ai_id: str | None) -> None:
        """Update link status for one game frame without full refresh.

        This is more efficient than set_link_status() when only a single
        frame's link has changed (e.g., after mapping creation/removal).

        Args:
            game_frame_id: The game frame ID to update
            linked_ai_id: The linked AI frame ID, or None if unlinked
        """
        # Update internal link status
        self._link_status[game_frame_id] = linked_ai_id

        # Find and update the list item
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == game_frame_id:  # type: ignore[reportUnnecessaryComparison]
                # Get the frame to reconstruct display
                frame = next((f for f in self._game_frames if f.id == game_frame_id), None)
                if frame is None:
                    break

                # Update display text and color based on link status
                display_text = frame.name
                if frame.display_name:
                    tooltip = f"Original ID: {frame.id}"
                else:
                    tooltip = ""

                if linked_ai_id is not None:
                    color = STATUS_COLORS["linked"]
                    item.setText(f"✓ {display_text}")
                    tooltip_suffix = f"Linked to AI frame #{linked_ai_id}"
                    item.setToolTip(f"{tooltip}\n{tooltip_suffix}" if tooltip else tooltip_suffix)
                else:
                    color = STATUS_COLORS["unlinked"]
                    item.setText(display_text)
                    tooltip_suffix = "Unlinked - drag to mapping drawer to link"
                    item.setToolTip(f"{tooltip}\n{tooltip_suffix}" if tooltip else tooltip_suffix)

                item.setForeground(QBrush(color))
                break

    def set_game_frame_previews(self, previews: dict[str, QPixmap]) -> None:
        """Set the preview pixmaps for game frames.

        Uses incremental updates when only preview content changes.
        Falls back to full refresh when structure changes (frames removed).

        Args:
            previews: Mapping of game_frame_id -> preview QPixmap
        """
        # Check if frames were removed (structural change requires full rebuild)
        removed = set(self._game_frame_previews.keys()) - set(previews.keys())

        if removed:
            # Structural change - need full refresh
            self._game_frame_previews = previews
            self._refresh_list()
        else:
            # Incremental update - only update changed/new previews
            for frame_id, pixmap in previews.items():
                old_pixmap = self._game_frame_previews.get(frame_id)
                if old_pixmap is None or old_pixmap is not pixmap:
                    self._game_frame_previews[frame_id] = pixmap
                    self.update_frame_preview(frame_id, pixmap)

    def update_frame_preview(self, frame_id: str, preview: QPixmap) -> None:
        """Update the preview for a single game frame and refresh display.

        Updates only the affected item's icon instead of rebuilding the entire list.

        Args:
            frame_id: The game frame ID
            preview: The new preview QPixmap
        """
        self._game_frame_previews[frame_id] = preview

        logger.debug(f"CapturesLibraryPane.update_frame_preview: {frame_id}, list count={self._list.count()}")

        # Find and update only the affected item
        found = False
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == frame_id:  # type: ignore[reportUnnecessaryComparison]
                found = True
                if not preview.isNull():
                    scaled = preview.scaled(
                        THUMBNAIL_SIZE,
                        THUMBNAIL_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    item.setIcon(QIcon(scaled))
                    logger.debug(f"Set icon for {frame_id}, scaled size={scaled.size()}")
                break

        if not found:
            logger.warning(f"update_frame_preview: Item not found for {frame_id}")

    def get_selected_id(self) -> str | None:
        """Get the currently selected game frame ID."""
        current = self._list.currentItem()
        if current is None:  # type: ignore[reportUnnecessaryComparison]
            return None
        return current.data(Qt.ItemDataRole.UserRole)

    def select_frame(self, frame_id: str) -> None:
        """Programmatically select a game frame by ID.

        Blocks signals to prevent feedback loops.

        Args:
            frame_id: The game frame ID to select
        """
        with block_signals(self._list):
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == frame_id:  # type: ignore[reportUnnecessaryComparison]
                    self._list.setCurrentRow(row)
                    self._list.scrollToItem(item)
                    break

    def clear_selection(self) -> None:
        """Clear the current selection without emitting signals."""
        with block_signals(self._list):
            self._list.clearSelection()
            self._list.setCurrentRow(-1)

    def clear(self) -> None:
        """Clear all game frames."""
        self._game_frames = []
        self._game_frame_previews = {}
        self._link_status = {}
        self._list.clear()
        self._count_label.setText("No captures")

    def get_visible_frame_ids(self) -> list[str]:
        """Get frame IDs of currently visible items in the list.

        Used for prioritizing async preview generation for visible frames.

        Returns:
            List of game frame IDs that are currently visible in the viewport.
        """
        visible_ids: list[str] = []
        viewport = self._list.viewport()
        if viewport is None:  # type: ignore[reportUnnecessaryComparison]
            return visible_ids

        # Get visible rect
        visible_rect = viewport.rect()

        # Iterate through items and check visibility
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is None:  # type: ignore[reportUnnecessaryComparison]
                continue

            item_rect = self._list.visualItemRect(item)
            if visible_rect.intersects(item_rect):
                frame_id = item.data(Qt.ItemDataRole.UserRole)
                if frame_id is not None:
                    visible_ids.append(frame_id)

        return visible_ids

    def get_all_frame_ids(self) -> list[str]:
        """Get all frame IDs in the current filtered list.

        Returns:
            List of all game frame IDs in the list (respecting current filters).
        """
        ids: list[str] = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None:  # type: ignore[reportUnnecessaryComparison]
                frame_id = item.data(Qt.ItemDataRole.UserRole)
                if frame_id is not None:
                    ids.append(frame_id)
        return ids

    @signal_error_boundary()
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._search_text = text.lower()
        self._refresh_list()

    @signal_error_boundary()
    def _on_filter_changed(self, checked: bool) -> None:
        """Handle filter checkbox toggle."""
        self._show_unlinked_only = checked
        self._refresh_list()

    @signal_error_boundary()
    def _on_selection_changed(self, row: int) -> None:
        """Handle game frame selection change."""
        if row < 0:
            # Notify listeners of cleared selection (matches AIFramesPane)
            self.game_frame_selected.emit("")
            return
        item = self._list.item(row)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return
        frame_id = item.data(Qt.ItemDataRole.UserRole)
        if frame_id is not None:
            self.game_frame_selected.emit(frame_id)

    @signal_error_boundary()
    def _on_context_menu(self, pos: object) -> None:
        """Show context menu for captures."""
        if not isinstance(pos, QPoint):
            return

        item = self._list.itemAt(pos)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return

        frame_id = item.data(Qt.ItemDataRole.UserRole)
        if frame_id is None:
            return

        menu = QMenu(self)

        # Find the frame to get its current name
        frame = next((f for f in self._game_frames if f.id == frame_id), None)
        current_name = frame.name if frame else frame_id

        rename_action = menu.addAction("Rename...")
        rename_action.triggered.connect(partial(self._show_rename_dialog, frame_id, current_name))

        menu.addSeparator()

        edit_action = menu.addAction("Edit in Sprite Editor")
        edit_action.triggered.connect(partial(self.edit_in_sprite_editor_requested.emit, frame_id))

        details_action = menu.addAction("Show Details")
        details_action.triggered.connect(partial(self.show_details_requested.emit, frame_id))

        menu.addSeparator()

        delete_action = menu.addAction("Delete Capture")
        # Warn if linked
        linked_ai = self._link_status.get(frame_id)
        if linked_ai is not None:
            delete_action.setText(f"Delete Capture (linked to AI #{linked_ai})")
        delete_action.triggered.connect(partial(self.delete_capture_requested.emit, frame_id))

        menu.exec(self._list.mapToGlobal(pos))

    def _start_drag(self, supported_actions: Qt.DropAction) -> None:
        """Start a drag operation with custom MIME data."""
        item = self._list.currentItem()
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return

        frame_id = item.data(Qt.ItemDataRole.UserRole)
        if frame_id is None:
            return

        drag = QDrag(self._list)
        mime_data = QMimeData()
        mime_data.setData(MIME_GAME_FRAME, frame_id.encode("utf-8"))
        mime_data.setText(frame_id)  # Fallback for debugging
        drag.setMimeData(mime_data)

        # Set drag pixmap
        icon = item.icon()
        if not icon.isNull():
            drag.setPixmap(icon.pixmap(48, 48))
            drag.setHotSpot(QPoint(24, 24))

        drag.exec(Qt.DropAction.CopyAction)

    def _refresh_list(self) -> None:
        """Refresh the list with current filter and search."""
        current_selection = self.get_selected_id()
        selection_restored = False

        with block_signals(self._list):
            self._list.clear()

            visible_count = 0
            total_count = len(self._game_frames)

            for frame in self._game_frames:
                linked_ai = self._link_status.get(frame.id)

                # Apply unlinked filter
                if self._show_unlinked_only and linked_ai is not None:
                    continue

                # Apply search filter (match both display name and original ID)
                if self._search_text:
                    search_target = f"{frame.name.lower()} {frame.id.lower()}"
                    if self._search_text not in search_target:
                        continue

                visible_count += 1

                item = QListWidgetItem()

                # Build display text and tooltip
                display_text = frame.name
                if frame.display_name:
                    # Show display name with original ID in tooltip
                    tooltip = f"Original ID: {frame.id}"
                else:
                    tooltip = ""

                # Add link status badge to text and tooltip
                if linked_ai is not None:
                    color = STATUS_COLORS["linked"]
                    item.setText(f"✓ {display_text}")
                    tooltip_suffix = f"Linked to AI frame #{linked_ai}"
                    item.setToolTip(f"{tooltip}\n{tooltip_suffix}" if tooltip else tooltip_suffix)
                else:
                    color = STATUS_COLORS["unlinked"]
                    item.setText(display_text)
                    tooltip_suffix = "Unlinked - drag to mapping drawer to link"
                    item.setToolTip(f"{tooltip}\n{tooltip_suffix}" if tooltip else tooltip_suffix)

                item.setData(Qt.ItemDataRole.UserRole, frame.id)
                item.setForeground(QBrush(color))

                # Use in-memory preview if available
                if frame.id in self._game_frame_previews:
                    pixmap = self._game_frame_previews[frame.id]
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
            if self._show_unlinked_only or self._search_text:
                self._count_label.setText(f"{visible_count}/{total_count}")
            else:
                self._count_label.setText(f"{total_count} capture{'s' if total_count != 1 else ''}")

            # Restore selection if the previously selected item is still visible
            if current_selection is not None:
                for row in range(self._list.count()):
                    item = self._list.item(row)
                    if item and item.data(Qt.ItemDataRole.UserRole) == current_selection:
                        self._list.setCurrentRow(row)
                        self._list.scrollToItem(item)
                        selection_restored = True
                        break

            if not selection_restored:
                self._list.setCurrentRow(-1)
                self._list.clearSelection()

        # NOTE: Do NOT emit empty string when selection is lost due to filtering.
        # The workspace state manager is the source of truth for selection,
        # and panes should not clear external state when filters hide items.
        # This matches AIFramesPane behavior (see ai_frames_pane.py:636-638).

    def _show_rename_dialog(self, frame_id: str, current_name: str) -> None:
        """Show dialog to rename a capture.

        Args:
            frame_id: ID of the frame to rename
            current_name: Current display name
        """
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Capture",
            "Enter new name (leave empty to use original ID):",
            QLineEdit.EchoMode.Normal,
            current_name,
        )
        if ok:
            self.capture_rename_requested.emit(frame_id, new_name)

    @signal_error_boundary()
    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click to rename a capture."""
        frame_id = item.data(Qt.ItemDataRole.UserRole)
        if frame_id is None:
            return
        # Find the frame to get its current name
        frame = next((f for f in self._game_frames if f.id == frame_id), None)
        current_name = frame.name if frame else frame_id
        self._show_rename_dialog(frame_id, current_name)

    def refresh_frame(self, frame_id: str) -> None:
        """Refresh display for a specific frame (e.g., after rename).

        Updates only the affected item instead of rebuilding the entire list.

        Args:
            frame_id: ID of the frame that changed
        """
        # Find the frame data
        frame = next((f for f in self._game_frames if f.id == frame_id), None)
        if frame is None:
            return

        # Find and update the list item
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == frame_id:  # type: ignore[reportUnnecessaryComparison]
                linked_ai = self._link_status.get(frame_id)

                # Build display text
                display_text = frame.name
                if frame.display_name:
                    tooltip = f"Original ID: {frame.id}"
                else:
                    tooltip = ""

                # Update text based on link status
                if linked_ai is not None:
                    item.setText(f"✓ {display_text}")
                    tooltip_suffix = f"Linked to AI frame #{linked_ai}"
                    item.setToolTip(f"{tooltip}\n{tooltip_suffix}" if tooltip else tooltip_suffix)
                else:
                    item.setText(display_text)
                    tooltip_suffix = "Unlinked - drag to mapping drawer to link"
                    item.setToolTip(f"{tooltip}\n{tooltip_suffix}" if tooltip else tooltip_suffix)

                break

    def remove_game_frame(self, frame_id: str) -> None:
        """Remove a game frame from display and refresh the list.

        Args:
            frame_id: ID of the frame to remove
        """
        self._game_frames = [f for f in self._game_frames if f.id != frame_id]
        self._game_frame_previews.pop(frame_id, None)
        self._link_status.pop(frame_id, None)
        self._refresh_list()

    def add_game_frame(self, frame: GameFrame, linked_ai_id: str | None = None) -> None:
        """Add a single game frame to the display.

        Efficiently adds one frame without rebuilding the entire list.

        Args:
            frame: The GameFrame to add
            linked_ai_id: AI frame ID if already linked, None if unlinked
        """
        # Update internal state
        self._game_frames.append(frame)
        self._link_status[frame.id] = linked_ai_id

        # Check if frame passes current filters
        if self._show_unlinked_only and linked_ai_id is not None:
            # Frame is linked but we're showing unlinked only - don't display
            self._update_count_label()
            return

        if self._search_text:
            search_target = f"{frame.name.lower()} {frame.id.lower()}"
            if self._search_text not in search_target:
                # Frame doesn't match search - don't display
                self._update_count_label()
                return

        # Create and add the item
        item = QListWidgetItem()
        display_text = frame.name

        if frame.display_name:
            tooltip = f"Original ID: {frame.id}"
        else:
            tooltip = ""

        if linked_ai_id is not None:
            color = STATUS_COLORS["linked"]
            item.setText(f"✓ {display_text}")
            tooltip_suffix = f"Linked to AI frame #{linked_ai_id}"
            item.setToolTip(f"{tooltip}\n{tooltip_suffix}" if tooltip else tooltip_suffix)
        else:
            color = STATUS_COLORS["unlinked"]
            item.setText(display_text)
            tooltip_suffix = "Unlinked - drag to mapping drawer to link"
            item.setToolTip(f"{tooltip}\n{tooltip_suffix}" if tooltip else tooltip_suffix)

        item.setData(Qt.ItemDataRole.UserRole, frame.id)
        item.setForeground(QBrush(color))

        # Preview will be added later via update_frame_preview
        self._list.addItem(item)
        self._update_count_label()

    def _update_count_label(self) -> None:
        """Update the count label with current visible/total counts."""
        visible_count = self._list.count()
        total_count = len(self._game_frames)

        if self._show_unlinked_only or self._search_text:
            self._count_label.setText(f"{visible_count}/{total_count}")
        else:
            self._count_label.setText(f"{total_count} capture{'s' if total_count != 1 else ''}")
