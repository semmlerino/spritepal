"""AI Frames Pane for displaying and selecting AI-generated sprite frames."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, override

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDragEnterEvent, QDragLeaveEvent, QDropEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ui.frame_mapping.services.thumbnail_service import (
    DEFAULT_THUMBNAIL_SIZE,
    AsyncThumbnailLoader,
)
from ui.frame_mapping.signal_error_handling import signal_error_boundary
from ui.frame_mapping.utils.signal_utils import block_signals
from ui.frame_mapping.views.sheet_palette_widget import SheetPaletteWidget
from ui.frame_mapping.views.status_colors import get_status_color
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame

from core.frame_mapping_project import FRAME_TAGS, SheetPalette

logger = get_logger(__name__)

# Thumbnail size for list items
THUMBNAIL_SIZE = DEFAULT_THUMBNAIL_SIZE

# Tag colors for frame organization
TAG_COLORS = {
    "keep": QColor(76, 175, 80),  # Green
    "discard": QColor(244, 67, 54),  # Red
    "wip": QColor(255, 193, 7),  # Amber
    "final": QColor(156, 39, 176),  # Purple
    "review": QColor(33, 150, 243),  # Blue
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

    ai_frame_selected = Signal(str)
    """Emitted when user selects an AI frame in the list.

    Args:
        ai_frame_id: ID of the selected AI frame (filename)

    Emitted by:
        - _on_frame_selected() → when user clicks list item

    Triggers:
        - FrameMappingWorkspace → updates workbench and mapping panel
    """

    map_requested = Signal()
    """Emitted when user clicks the "Map Selected" button.

    Signals intent to create a mapping between the selected AI frame
    and the selected game frame (in captures pane).

    Args:
        (none)

    Emitted by:
        - _on_map_requested() → when user clicks Map button

    Triggers:
        - FrameMappingWorkspace → initiates mapping creation
    """

    auto_advance_changed = Signal(bool)
    """Emitted when auto-advance toggle state changes.

    Auto-advance enables automatic selection of next frame after mapping.

    Args:
        enabled: True if auto-advance is enabled

    Emitted by:
        - _on_auto_advance_toggled() → when user toggles checkbox

    Triggers:
        - FrameMappingWorkspace → updates auto-advance setting
    """

    edit_in_sprite_editor_requested = Signal(str)
    """Emitted when user requests to open AI frame in sprite editor.

    Args:
        ai_frame_id: ID of the AI frame to edit

    Emitted by:
        - _on_edit_in_sprite_editor_clicked() → when user clicks context menu item

    Triggers:
        - FrameMappingWorkspace → opens sprite editor with frame
    """

    edit_frame_palette_requested = Signal(str)
    """Emitted when user wants to edit palette indices for an AI frame.

    Args:
        ai_frame_id: ID of the AI frame

    Emitted by:
        - _on_edit_frame_palette_requested() → when user clicks context menu item

    Triggers:
        - FrameMappingWorkspace → opens palette index editor
    """

    remove_from_project_requested = Signal(str)
    """Emitted when user requests to remove an AI frame from the project.

    Args:
        ai_frame_id: ID of the AI frame to remove

    Emitted by:
        - _on_remove_clicked() → when user clicks context menu item

    Triggers:
        - FrameMappingWorkspace → removes frame after confirmation
    """

    remove_batch_from_project_requested = Signal(list)
    """Emitted when user requests to remove multiple AI frames from the project.

    Args:
        ai_frame_ids: List of IDs of the AI frames to remove

    Emitted by:
        - _on_remove_batch_clicked() → when user clicks context menu item

    Triggers:
        - FrameMappingWorkspace → removes frames after confirmation
    """

    palette_edit_requested = Signal()
    """Emitted when user clicks "Edit Palette" button in sheet palette widget.

    Args:
        (none)

    Emitted by:
        - SheetPaletteWidget.palette_edit_requested (relayed)

    Triggers:
        - FrameMappingWorkspace → opens palette editor dialog
    """

    palette_extract_requested = Signal()
    """Emitted when user clicks "Extract Colors" in sheet palette widget.

    Triggers palette generation from AI frame colors.

    Args:
        (none)

    Emitted by:
        - SheetPaletteWidget.palette_extract_requested (relayed)

    Triggers:
        - FrameMappingWorkspace → extracts and generates palette
    """

    palette_clear_requested = Signal()
    """Emitted when user clicks "Clear" in sheet palette widget.

    Args:
        (none)

    Emitted by:
        - SheetPaletteWidget.palette_clear_requested (relayed)

    Triggers:
        - FrameMappingWorkspace → clears sheet palette
    """

    palette_color_changed = Signal(int, object)
    """Emitted when user edits a palette color in the sheet palette widget.

    Args:
        index: Palette index (0-15) that was edited
        rgb_tuple: (r, g, b) color tuple

    Emitted by:
        - SheetPaletteWidget.palette_color_changed (relayed)

    Triggers:
        - FrameMappingWorkspace → updates palette in project
    """

    palette_swatch_hovered = Signal(object)
    """Emitted when user hovers over a palette swatch.

    Used for visual feedback (highlighting palette indices in AI frames).

    Args:
        index: Palette index if hovering, None if left the swatch

    Emitted by:
        - SheetPaletteWidget.palette_swatch_hovered (relayed)

    Triggers:
        - FrameMappingWorkspace → highlights/unhighlights palette indices
    """

    folder_dropped = Signal(object)
    """Emitted when user drops a folder onto the pane.

    Args:
        path: Path object pointing to the dropped folder

    Emitted by:
        - dropEvent() → when folder drop is detected

    Triggers:
        - FrameMappingWorkspace → loads AI frames from folder
    """

    file_dropped = Signal(object)
    """Emitted when user drops a single PNG file onto the pane.

    Args:
        path: Path object pointing to the dropped file

    Emitted by:
        - dropEvent() → when single file drop is detected

    Triggers:
        - FrameMappingWorkspace → adds AI frame from file
    """

    tab_folder_changed = Signal(object)
    """Emitted when the active tab's folder changes.

    Signals the current tab's folder context, used to populate open dialogs.

    Args:
        path: Path object pointing to folder, or None if no folder set

    Emitted by:
        - _on_tab_changed() → when user switches tabs

    Triggers:
        - FrameMappingWorkspace → updates file browser context
    """

    frame_rename_requested = Signal(str, str)
    """Emitted when user renames an AI frame's display name.

    Part of frame organization support (V4).

    Args:
        ai_frame_id: ID of the frame being renamed
        new_display_name: New display name (or empty string to clear)

    Emitted by:
        - _on_rename_frame_requested() → after user edits in dialog

    Triggers:
        - FrameMappingWorkspace → updates frame display name
    """

    frame_tag_toggled = Signal(str, str)
    """Emitted when user toggles a tag on an AI frame.

    Part of frame organization support (V4). Tags are toggled via context menu.

    Args:
        ai_frame_id: ID of the frame being tagged
        tag: Tag name that was toggled

    Emitted by:
        - _on_tag_toggled() → when user selects tag in context menu

    Triggers:
        - FrameMappingWorkspace → updates frame tags
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ai_frames: list[AIFrame] = []
        self._mapping_status: dict[str, str] = {}  # ai_frame_id -> status
        self._id_to_row: dict[str, int] = {}  # ai_frame_id -> list row (O(1) lookup)
        self._show_unmapped_only = False
        self._search_text: str = ""
        self._tag_filter: str = ""  # Empty = show all, or specific tag to filter
        self._sheet_palette: SheetPalette | None = None  # For quantized thumbnails

        # Tab management
        self._tab_folders: list[Path | None] = [None]  # One empty tab initially
        self._suppress_tab_signal: bool = False

        # Async thumbnail loading (prevents UI freeze when loading many frames)
        self._thumbnail_loader = AsyncThumbnailLoader(self)
        self._thumbnail_loader.thumbnail_ready.connect(self._on_thumbnail_ready)

        self.setAcceptDrops(True)
        self._setup_ui()

    @override
    def deleteLater(self) -> None:
        self.shutdown_async_services()
        super().deleteLater()

    def shutdown_async_services(self) -> None:
        """Stop background thumbnail loading to avoid QThread leaks."""
        self._thumbnail_loader.shutdown()

    @override
    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Destroy:
            self.shutdown_async_services()
        return super().event(event)

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        title = QLabel("AI Frames")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(title)

        # Tab bar for multiple folders
        tab_container = QHBoxLayout()
        tab_container.setContentsMargins(0, 0, 0, 0)
        tab_container.setSpacing(2)

        self._tab_bar = QTabBar()
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setMovable(False)
        self._tab_bar.setExpanding(False)
        self._tab_bar.setDocumentMode(True)
        self._tab_bar.addTab("New")  # Initial empty tab
        self._tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        tab_container.addWidget(self._tab_bar, 1)

        self._add_tab_btn = QPushButton("+")
        self._add_tab_btn.setFixedSize(24, 24)
        self._add_tab_btn.setToolTip("Add new tab")
        self._add_tab_btn.clicked.connect(self._on_add_tab_clicked)
        tab_container.addWidget(self._add_tab_btn)

        layout.addLayout(tab_container)

        # Sheet palette widget (collapsible section)
        self._palette_widget = SheetPaletteWidget()
        self._palette_widget.edit_requested.connect(self.palette_edit_requested.emit)
        self._palette_widget.extract_requested.connect(self.palette_extract_requested.emit)
        self._palette_widget.clear_requested.connect(self.palette_clear_requested.emit)
        # Interactive signals for bidirectional highlighting
        self._palette_widget.color_changed.connect(self.palette_color_changed.emit)
        self._palette_widget.swatch_hovered.connect(self.palette_swatch_hovered.emit)
        self._palette_widget.set_buttons_enabled(False)  # Disabled until frames are loaded
        layout.addWidget(self._palette_widget)

        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

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

        # Tag filter dropdown
        self._tag_filter_combo = QComboBox()
        self._tag_filter_combo.setStyleSheet("font-size: 10px;")
        self._tag_filter_combo.setToolTip("Filter by tag")
        self._tag_filter_combo.addItem("All Tags", "")
        for tag in sorted(FRAME_TAGS):
            self._tag_filter_combo.addItem(tag.capitalize(), tag)
        self._tag_filter_combo.currentIndexChanged.connect(self._on_tag_filter_changed)
        filter_layout.addWidget(self._tag_filter_combo)

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
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.setDragEnabled(False)  # AI frames are not draggable (they ARE rows)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Enhanced styling for selection visibility
        from ui.styles.theme import COLORS

        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS["darker_gray"]};
                border: 1px solid {COLORS["border"]};
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px;
                border-bottom: 1px solid {COLORS["dark_gray"]};
            }}
            QListWidget::item:selected {{
                background-color: {COLORS["highlight"]};
                color: white;
            }}
            QListWidget::item:hover:!selected {{
                background-color: {COLORS["surface_hover"]};
            }}
        """)
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
        # Enable palette buttons when frames are loaded
        self._palette_widget.set_buttons_enabled(len(frames) > 0)

    def set_mapping_status(self, status_map: dict[str, str]) -> None:
        """Update the mapping status for AI frames.

        Uses incremental updates for changed items instead of full list rebuild,
        avoiding redundant thumbnail loading.

        Args:
            status_map: Dictionary mapping AI frame ID (filename) to status string
        """
        # Detect which frames have changed status
        changed = [
            (frame_id, status)
            for frame_id, status in status_map.items()
            if self._mapping_status.get(frame_id) != status
        ]

        # Update internal state
        self._mapping_status = status_map

        # Only update changed items (avoids full rebuild and thumbnail reload)
        for frame_id, status in changed:
            self.update_single_item_status(frame_id, status)

    def update_single_item_status(self, ai_frame_id: str, status: str) -> None:
        """Update status indicator for one AI frame without full refresh.

        This is more efficient than set_mapping_status() when only a single
        frame's status has changed (e.g., after alignment edit or mapping creation).

        Args:
            ai_frame_id: The AI frame ID (filename) to update
            status: New status string ("unmapped", "mapped", "edited", "injected")
        """
        # Update internal status map
        self._mapping_status[ai_frame_id] = status

        # Find the list item using O(1) lookup
        row = self._id_to_row.get(ai_frame_id)
        if row is None:
            return

        item = self._list.item(row)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return

        # Get the frame to reconstruct display text
        frame = next((f for f in self._ai_frames if f.id == ai_frame_id), None)
        if frame is None:
            return

        # Update status indicator and text
        status_indicator = "●" if status != "unmapped" else "○"
        display_text = frame.name

        # Add tag chips as suffix
        if frame.tags:
            tag_str = " ".join(f"[{t}]" for t in sorted(frame.tags))
            display_text = f"{display_text}  {tag_str}"

        item.setText(f"{status_indicator} {display_text}")

        # Update color
        color = get_status_color(status)
        item.setForeground(QBrush(color))

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
        Returns the ID of the current item (the one with focus/last clicked).
        """
        current = self._list.currentItem()
        if current is None:  # type: ignore[reportUnnecessaryComparison]
            return None
        return current.data(Qt.ItemDataRole.UserRole)

    def get_selected_ids(self) -> list[str]:
        """Get IDs of all selected AI frames.

        Returns:
            List of selected frame IDs (filenames).
        """
        selected_items = self._list.selectedItems()
        ids = []
        for item in selected_items:
            frame_id = item.data(Qt.ItemDataRole.UserRole)
            if frame_id is not None:
                ids.append(frame_id)
        return ids

    def select_frame(self, index: int, *, emit_signal: bool = False) -> None:
        """Programmatically select an AI frame by index.

        Blocks signals during selection to prevent feedback loops.
        Note: Prefer select_frame_by_id() for stable references across reloads.

        Args:
            index: The AI frame index to select
            emit_signal: If True, emit ai_frame_selected after selection.
                        This provides a unified pattern for callers that need
                        the handler to run (instead of manually calling it).
        """
        self._list.blockSignals(True)
        selected_id: str | None = None
        try:
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item is not None and item.data(Qt.ItemDataRole.UserRole + 1) == index:  # type: ignore[reportUnnecessaryComparison]
                    self._list.setCurrentRow(row)
                    self._list.scrollToItem(item)
                    selected_id = item.data(Qt.ItemDataRole.UserRole)
                    break
        finally:
            self._list.blockSignals(False)

        if emit_signal and selected_id is not None:
            self.ai_frame_selected.emit(selected_id)

    def select_frame_by_id(self, frame_id: str, *, emit_signal: bool = False) -> None:
        """Programmatically select an AI frame by ID (filename).

        Blocks signals during selection to prevent feedback loops.
        This is the preferred method as IDs are stable across reloads/reordering.

        Args:
            frame_id: The AI frame ID (filename) to select
            emit_signal: If True, emit ai_frame_selected after selection.
                        This provides a unified pattern for callers that need
                        the handler to run (instead of manually calling it).
        """
        self._list.blockSignals(True)
        selected_id: str | None = None
        try:
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == frame_id:  # type: ignore[reportUnnecessaryComparison]
                    self._list.setCurrentRow(row)
                    self._list.scrollToItem(item)
                    selected_id = frame_id
                    break
        finally:
            self._list.blockSignals(False)

        if emit_signal and selected_id is not None:
            self.ai_frame_selected.emit(selected_id)

    def clear_selection(self) -> None:
        """Clear the current AI frame selection.

        Blocks signals during clearing to prevent feedback loops.
        """
        with block_signals(self._list):
            self._list.setCurrentRow(-1)
            self._list.clearSelection()

    def has_visible_item(self, frame_id: str) -> bool:
        """Check if a frame is visible in the filtered list.

        Used to verify that a selected frame is actually visible and not
        hidden by active filters (unmapped-only, search, tag).

        Args:
            frame_id: The AI frame ID to check

        Returns:
            True if the frame has a visible list item, False if filtered out
        """
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == frame_id:  # type: ignore[reportUnnecessaryComparison]
                return True
        return False

    def clear(self) -> None:
        """Clear all AI frames and reset tabs."""
        self._ai_frames = []
        self._mapping_status = {}
        self._id_to_row.clear()
        self._list.clear()
        self._count_label.setText("No frames")
        self._palette_widget.set_palette(None)
        self._palette_widget.set_buttons_enabled(False)

        # Reset tabs to single empty tab
        self._suppress_tab_signal = True
        try:
            while self._tab_bar.count() > 0:
                self._tab_bar.removeTab(0)
            self._tab_bar.addTab("New")
            self._tab_folders = [None]
        finally:
            self._suppress_tab_signal = False

    def set_map_button_enabled(self, enabled: bool) -> None:
        """Set the enabled state of the Map Selected button."""
        self._map_button.setEnabled(enabled)

    def set_sheet_palette(self, palette: SheetPalette | None) -> None:
        """Set the sheet palette to display.

        Updates the palette widget and refreshes all thumbnails to show
        quantized colors matching the new palette.

        Args:
            palette: SheetPalette to display, or None to clear
        """
        self._sheet_palette = palette
        self._palette_widget.set_palette(palette)
        # Refresh thumbnails only - no list rebuild needed for palette change
        self.refresh_thumbnails_only()
        # Force Qt to repaint the list viewport to ensure icon updates are visible
        # This fixes a Qt issue where icon caching can prevent visual updates
        self._list.viewport().update()

    def refresh_thumbnails_only(self) -> None:
        """Refresh only the thumbnails for existing list items.

        More efficient than _refresh_list() when only the palette changed -
        keeps items, selection, and scroll position, just re-loads icons.
        """
        # Collect thumbnail requests for all current items
        thumbnail_requests: list[tuple[str, Path]] = []

        for frame in self._ai_frames:
            # Check if item is visible in list (passes filters)
            if frame.id in self._id_to_row:
                thumbnail_requests.append((frame.id, frame.path))

        # Start async thumbnail loading with new palette
        if thumbnail_requests:
            self._thumbnail_loader.load_thumbnails(thumbnail_requests, self._sheet_palette, THUMBNAIL_SIZE)

    def get_sheet_palette(self) -> SheetPalette | None:
        """Get the current sheet palette.

        Returns:
            SheetPalette if defined, None otherwise
        """
        return self._palette_widget.get_palette()

    def highlight_palette_index(self, index: int | None) -> None:
        """Highlight a palette swatch (from canvas pixel hover).

        Args:
            index: Palette index to highlight, or None to clear
        """
        self._palette_widget.highlight_index(index)

    def select_palette_index(self, index: int) -> None:
        """Select a palette swatch (from eyedropper pick).

        Args:
            index: Palette index to select
        """
        self._palette_widget.select_index(index)

    def set_capture_palette_info(self, palette_indices: set[int] | None) -> None:
        """Set capture palette info for status display.

        Args:
            palette_indices: Set of palette indices in use, or None to clear
        """
        self._palette_widget.set_capture_palette_info(palette_indices)

    def set_current_frame_palette_index(self, index: int | None) -> None:
        """Set the palette index used by the currently selected frame.

        Args:
            index: Palette index (0-7) for the current frame, or None to clear
        """
        self._palette_widget.set_current_frame_palette_index(index)

    @signal_error_boundary()
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._search_text = text.lower()
        self._refresh_list()

    @signal_error_boundary()
    def _on_filter_changed(self, checked: bool) -> None:
        """Handle filter checkbox toggle."""
        self._show_unmapped_only = checked
        self._refresh_list()

    @signal_error_boundary()
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

    @signal_error_boundary()
    def _on_context_menu(self, pos: object) -> None:
        """Show context menu for AI frames."""
        from PySide6.QtCore import QPoint

        if not isinstance(pos, QPoint):
            return

        item = self._list.itemAt(pos)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return

        frame_id = item.data(Qt.ItemDataRole.UserRole)
        if frame_id is None:
            return

        # Get currently selected frames
        selected_ids = self.get_selected_ids()
        is_multi_selection = len(selected_ids) > 1
        num_selected = len(selected_ids)
        target_frame_id = frame_id  # The frame under the cursor

        # Get frame to check current tags
        frame = next((f for f in self._ai_frames if f.id == target_frame_id), None)
        current_tags = frame.tags if frame else frozenset()

        menu = QMenu(self)

        # Rename action
        rename_action = menu.addAction("Rename...")
        rename_action.triggered.connect(partial(self._show_rename_dialog, target_frame_id))

        # Tags submenu
        tags_menu = menu.addMenu("Tags")
        for tag in sorted(FRAME_TAGS):
            action = tags_menu.addAction(tag.capitalize())
            action.setCheckable(True)
            action.setChecked(tag in current_tags)
            # Use partial with captured tag - triggered signal passes checked as first arg
            action.triggered.connect(partial(self._emit_tag_toggled, target_frame_id, tag))

        menu.addSeparator()

        edit_action = menu.addAction("Edit in Sprite Editor")
        edit_action.triggered.connect(partial(self.edit_in_sprite_editor_requested.emit, target_frame_id))

        edit_palette_action = menu.addAction("Edit Palette Indices...")
        edit_palette_action.triggered.connect(partial(self._emit_edit_palette, target_frame_id))

        menu.addSeparator()

        # Removal action - adapt text and signal based on selection
        if is_multi_selection:
            # Use target_frame_id if it's among selected, otherwise fallback to first selected
            # This logic isn't strictly needed for batch but good for consistency
            remove_text = f"Remove {num_selected} frames"
            remove_action = menu.addAction(remove_text)
            remove_action.triggered.connect(lambda: self.remove_batch_from_project_requested.emit(selected_ids))
        else:
            remove_text = "Remove from Project"
            remove_action = menu.addAction(remove_text)

            def emit_remove(fid: str) -> None:
                logger.info("Remove action triggered for frame_id: %s", fid)
                self.remove_from_project_requested.emit(fid)

            remove_action.triggered.connect(partial(emit_remove, target_frame_id))

        menu.exec(self._list.mapToGlobal(pos))

    def _emit_tag_toggled(self, frame_id: str, tag: str, checked: bool) -> None:
        """Emit tag toggled signal (helper for partial)."""
        self.frame_tag_toggled.emit(frame_id, tag)

    def _emit_edit_palette(self, frame_id: str) -> None:
        """Emit edit palette signal (helper for partial with logging)."""
        logger.info("Edit Palette clicked for frame: %s", frame_id)
        self.edit_frame_palette_requested.emit(frame_id)

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

        # Collect thumbnail requests for async loading
        thumbnail_requests: list[tuple[str, Path]] = []

        with block_signals(self._list):
            self._list.clear()

            visible_count = 0
            total_count = len(self._ai_frames)

            for frame in self._ai_frames:
                # Use ID-based lookup for status (stable across reloads/reordering)
                status = self._mapping_status.get(frame.id, "unmapped")

                # Apply unmapped filter
                if self._show_unmapped_only and status != "unmapped":
                    continue

                # Apply tag filter
                if self._tag_filter and self._tag_filter not in frame.tags:
                    continue

                # Apply search filter - search both display name and filename
                if self._search_text:
                    search_target = frame.name.lower()  # Uses display_name if set
                    if self._search_text not in search_target and self._search_text not in frame.path.name.lower():
                        continue

                visible_count += 1

                item = QListWidgetItem()
                # Add status indicator and display name
                status_indicator = "●" if status != "unmapped" else "○"
                display_text = frame.name  # Uses display_name if set, else filename

                # Add tag chips as suffix
                if frame.tags:
                    tag_str = " ".join(f"[{t}]" for t in sorted(frame.tags))
                    display_text = f"{display_text}  {tag_str}"

                item.setText(f"{status_indicator} {display_text}")

                # Set tooltip with filename if display_name is set
                if frame.display_name:
                    item.setToolTip(f"File: {frame.path.name}")

                # Store frame ID in UserRole (primary), index in UserRole+1 (backward compat)
                item.setData(Qt.ItemDataRole.UserRole, frame.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, frame.index)

                # Apply status color
                color = get_status_color(status)
                item.setForeground(QBrush(color))

                # Queue thumbnail for async loading (prevents UI freeze)
                thumbnail_requests.append((frame.id, frame.path))

                self._list.addItem(item)

            # Update count label
            if self._show_unmapped_only or self._search_text or self._tag_filter:
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

            # Rebuild ID-to-row lookup after populating the list
            self._id_to_row = {}
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item is not None:  # type: ignore[reportUnnecessaryComparison]
                    frame_id = item.data(Qt.ItemDataRole.UserRole)
                    if frame_id is not None:
                        self._id_to_row[frame_id] = row

        # Start async thumbnail loading (UI remains responsive)
        self._thumbnail_loader.load_thumbnails(thumbnail_requests, self._sheet_palette, THUMBNAIL_SIZE)

        # Notify listeners about selection changes during frame list changes (add/remove frames)
        if is_frame_list_change:
            if selection_restored and restored_id is not None:
                # Selection restored to same frame (still exists after change)
                self.ai_frame_selected.emit(restored_id)
            elif current_selection_id is not None:
                # Previously selected frame no longer exists (was deleted) - notify to clear state
                # This is different from filtering: filters hide items but they still exist,
                # so state manager preserves selection. Deletion removes items completely,
                # so state manager must be notified to clear the stale selection.
                self.ai_frame_selected.emit("")

    @signal_error_boundary()
    def _on_tag_filter_changed(self, index: int) -> None:
        """Handle tag filter combo box change."""
        self._tag_filter = self._tag_filter_combo.currentData() or ""
        self._refresh_list()

    @signal_error_boundary()
    def _on_thumbnail_ready(self, frame_id: str, pixmap: QPixmap) -> None:
        """Update list item icon when async thumbnail is ready.

        Args:
            frame_id: The AI frame ID
            pixmap: The loaded thumbnail pixmap
        """
        # Find ALL list items with this frame ID and update their icons
        # (handles duplicate filenames in the project)
        found = False
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == frame_id:
                item.setIcon(QIcon(pixmap))
                logger.debug("AIFramesPane: set icon for %s at row %d", frame_id, row)
                found = True
                # Don't break - continue to find all duplicates
        if not found:
            logger.debug(
                "AIFramesPane: no item found for frame_id=%s (list has %d items)", frame_id, self._list.count()
            )

    def _show_rename_dialog(self, frame_id: str) -> None:
        """Show rename dialog for a frame."""
        frame = next((f for f in self._ai_frames if f.id == frame_id), None)
        if frame is None:
            return

        current_name = frame.display_name or frame.path.stem  # Stem = filename without extension
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Frame",
            f"Enter display name for {frame.path.name}:",
            QLineEdit.EchoMode.Normal,
            current_name,
        )
        if ok and new_name != current_name:
            # Empty string clears display name (reverts to filename)
            display_name = new_name.strip() if new_name.strip() else None
            self.frame_rename_requested.emit(frame_id, display_name or "")

    @signal_error_boundary()
    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on list item - show rename dialog."""
        frame_id = item.data(Qt.ItemDataRole.UserRole)
        if frame_id:
            self._show_rename_dialog(frame_id)

    def refresh_frame(self, frame_id: str) -> None:
        """Refresh display for a single frame after tag/name change.

        Updates only the affected item instead of rebuilding the entire list.

        Args:
            frame_id: ID of the frame that changed
        """
        # Find the frame data
        frame = next((f for f in self._ai_frames if f.id == frame_id), None)
        if frame is None:
            return

        # Find the list item for this frame
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is None:  # type: ignore[reportUnnecessaryComparison]
                continue
            if item.data(Qt.ItemDataRole.UserRole) == frame_id:
                # Get current status for the indicator
                status = self._mapping_status.get(frame_id, "unmapped")
                status_indicator = "●" if status != "unmapped" else "○"

                # Build display text
                display_text = frame.name  # Uses display_name if set, else filename
                if frame.tags:
                    tag_str = " ".join(f"[{t}]" for t in sorted(frame.tags))
                    display_text = f"{display_text}  {tag_str}"

                item.setText(f"{status_indicator} {display_text}")

                # Update tooltip
                if frame.display_name:
                    item.setToolTip(f"File: {frame.path.name}")
                else:
                    item.setToolTip("")

                break

    def move_item(self, from_index: int, to_index: int) -> None:
        """Move an item in the list without regenerating thumbnails.

        This is much faster than set_ai_frames() + full refresh as it only
        moves Qt list items rather than rebuilding everything.

        Args:
            from_index: Current item position (0-based)
            to_index: Target item position (0-based)
        """
        if from_index == to_index:
            return

        item_count = self._list.count()
        if from_index < 0 or from_index >= item_count:
            return
        if to_index < 0 or to_index >= item_count:
            return

        with block_signals(self._list):
            # Take the item from its current position
            item = self._list.takeItem(from_index)
            if item is None:  # type: ignore[reportUnnecessaryComparison]
                return

            # Insert at the new position
            self._list.insertItem(to_index, item)

            # Update index metadata for all affected items
            # After move, positions between min/max indices have shifted
            start = min(from_index, to_index)
            end = max(from_index, to_index)
            for row in range(start, end + 1):
                affected_item = self._list.item(row)
                if affected_item is not None:  # type: ignore[reportUnnecessaryComparison]
                    affected_item.setData(Qt.ItemDataRole.UserRole + 1, row)

            # Update ID-to-row lookup for affected range
            for row in range(start, end + 1):
                affected_item = self._list.item(row)
                if affected_item is not None:  # type: ignore[reportUnnecessaryComparison]
                    frame_id = affected_item.data(Qt.ItemDataRole.UserRole)
                    if frame_id is not None:
                        self._id_to_row[frame_id] = row

            # Select the moved item
            self._list.setCurrentRow(to_index)

    def add_single_item(self, frame: AIFrame) -> None:
        """Add a single AI frame to the list without full refresh.

        This is much faster than set_ai_frames() as it only adds one item
        and requests one thumbnail, rather than rebuilding everything.

        Args:
            frame: The AIFrame to add
        """
        # Add to our internal list
        self._ai_frames.append(frame)

        # Check filters - skip if filtered out
        status = self._mapping_status.get(frame.id, "unmapped")

        if self._show_unmapped_only and status != "unmapped":
            # Frame is filtered out, just update count
            self._update_count_label()
            return

        if self._tag_filter and self._tag_filter not in frame.tags:
            # Frame is filtered out, just update count
            self._update_count_label()
            return

        if self._search_text:
            search_target = frame.name.lower()
            if self._search_text not in search_target and self._search_text not in frame.path.name.lower():
                # Frame is filtered out, just update count
                self._update_count_label()
                return

        # Create list item (same logic as _refresh_list)
        item = QListWidgetItem()
        status_indicator = "●" if status != "unmapped" else "○"
        display_text = frame.name

        if frame.tags:
            tag_str = " ".join(f"[{t}]" for t in sorted(frame.tags))
            display_text = f"{display_text}  {tag_str}"

        item.setText(f"{status_indicator} {display_text}")

        if frame.display_name:
            item.setToolTip(f"File: {frame.path.name}")

        item.setData(Qt.ItemDataRole.UserRole, frame.id)
        item.setData(Qt.ItemDataRole.UserRole + 1, frame.index)

        color = get_status_color(status)
        item.setForeground(QBrush(color))

        self._list.addItem(item)

        # Update ID-to-row lookup with the newly added row
        row = self._list.count() - 1
        self._id_to_row[frame.id] = row

        # Request thumbnail for async loading
        self._thumbnail_loader.load_thumbnails([(frame.id, frame.path)], self._sheet_palette, THUMBNAIL_SIZE)

        # Update count label
        self._update_count_label()

    def _update_count_label(self) -> None:
        """Update the count label based on current filter state."""
        total_count = len(self._ai_frames)
        if self._show_unmapped_only or self._search_text or self._tag_filter:
            visible_count = self._list.count()
            self._count_label.setText(f"{visible_count}/{total_count}")
        else:
            self._count_label.setText(f"{total_count} frame{'s' if total_count != 1 else ''}")

    # ─── Drag and Drop ────────────────────────────────────────────────────────

    @override
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept drag if URLs contain a folder or PNG file."""
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.is_dir() or (path.is_file() and path.suffix.lower() == ".png"):
                        event.acceptProposedAction()
                        # Visual feedback - dashed border on list
                        self._list.setStyleSheet("QListWidget { border: 2px dashed #4CAF50; }")
                        return
        event.ignore()

    @override
    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        """Reset visual feedback when drag leaves."""
        self._list.setStyleSheet("")
        event.accept()

    @override
    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop - emit folder_dropped or file_dropped signal."""
        self._list.setStyleSheet("")  # Reset visual feedback

        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            event.ignore()
            return

        for url in mime_data.urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                # Emit appropriate signal based on what was dropped
                if path.is_file() and path.suffix.lower() == ".png":
                    logger.info("File dropped: %s", path)
                    self.file_dropped.emit(path)
                    event.acceptProposedAction()
                    return
                if path.is_dir():
                    logger.info("Folder dropped: %s", path)
                    self.folder_dropped.emit(path)
                    event.acceptProposedAction()
                    return

        event.ignore()

    # ─── Tab Management ───────────────────────────────────────────────────────

    def add_folder_tab(self, folder_path: Path) -> int:
        """Add a new tab with folder name and switch to it.

        Args:
            folder_path: Path to the folder

        Returns:
            Index of the new tab
        """
        self._suppress_tab_signal = True
        try:
            tab_name = folder_path.name or str(folder_path)
            index = self._tab_bar.addTab(tab_name)
            self._tab_folders.append(folder_path)
            self._tab_bar.setCurrentIndex(index)
        finally:
            self._suppress_tab_signal = False

        # Emit signal for the new tab
        self.tab_folder_changed.emit(folder_path)
        return index

    def close_tab(self, index: int) -> None:
        """Close tab at given index.

        If closing the last tab, reset to a single empty tab.

        Args:
            index: Tab index to close
        """
        if index < 0 or index >= self._tab_bar.count():
            return

        self._suppress_tab_signal = True
        try:
            self._tab_bar.removeTab(index)
            del self._tab_folders[index]

            # If no tabs left, add an empty one
            if self._tab_bar.count() == 0:
                self._tab_bar.addTab("New")
                self._tab_folders = [None]
        finally:
            self._suppress_tab_signal = False

        # Emit signal for the now-current tab
        current_folder = self.get_current_tab_folder()
        self.tab_folder_changed.emit(current_folder)

    def set_current_tab_folder(self, folder_path: Path) -> None:
        """Associate a folder with the current tab.

        Updates the tab label to show the folder name.

        Args:
            folder_path: Path to associate with current tab
        """
        index = self._tab_bar.currentIndex()
        if index < 0 or index >= len(self._tab_folders):
            return

        self._tab_folders[index] = folder_path
        tab_name = folder_path.name or str(folder_path)
        self._tab_bar.setTabText(index, tab_name)

    def get_current_tab_folder(self) -> Path | None:
        """Get the folder associated with the current tab.

        Returns:
            Path if tab has folder, None for empty tabs
        """
        index = self._tab_bar.currentIndex()
        if index < 0 or index >= len(self._tab_folders):
            return None
        return self._tab_folders[index]

    @signal_error_boundary()
    def _on_tab_changed(self, index: int) -> None:
        """Handle tab selection change."""
        if self._suppress_tab_signal:
            return
        if index < 0 or index >= len(self._tab_folders):
            return
        folder = self._tab_folders[index]
        self.tab_folder_changed.emit(folder)

    @signal_error_boundary()
    def _on_tab_close_requested(self, index: int) -> None:
        """Handle tab close button click."""
        self.close_tab(index)

    @signal_error_boundary()
    def _on_add_tab_clicked(self) -> None:
        """Handle add tab button click."""
        self._suppress_tab_signal = True
        try:
            index = self._tab_bar.addTab("New")
            self._tab_folders.append(None)
            self._tab_bar.setCurrentIndex(index)
        finally:
            self._suppress_tab_signal = False
        # Emit signal for the new empty tab
        self.tab_folder_changed.emit(None)

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def cleanup(self) -> None:
        """Shut down async services and release resources.

        Called during application close to properly stop background threads
        before Qt objects are destroyed.
        """
        self._thumbnail_loader.cancel()
