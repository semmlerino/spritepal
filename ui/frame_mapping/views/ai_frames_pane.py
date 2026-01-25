"""AI Frames Pane for displaying and selecting AI-generated sprite frames."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, override

from PIL import Image
from PySide6.QtCore import QSize, Qt, Signal
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

from core.palette_utils import (
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    quantize_to_palette,
    quantize_with_mappings,
)
from core.services.image_utils import pil_to_qpixmap
from ui.frame_mapping.views.sheet_palette_widget import SheetPaletteWidget
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame

from core.frame_mapping_project import FRAME_TAGS, SheetPalette

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

    ai_frame_selected = Signal(str)  # AI frame ID (filename)
    map_requested = Signal()  # User wants to map selected frames
    auto_advance_changed = Signal(bool)  # Auto-advance toggle state changed
    edit_in_sprite_editor_requested = Signal(str)  # AI frame ID
    edit_frame_palette_requested = Signal(str)  # AI frame ID - open palette index editor
    remove_from_project_requested = Signal(str)  # AI frame ID
    # Sheet palette signals
    palette_edit_requested = Signal()  # User wants to edit sheet palette
    palette_extract_requested = Signal()  # User wants to extract palette from sheet
    palette_clear_requested = Signal()  # User wants to clear sheet palette
    # Sheet palette interactive signals (for bidirectional highlighting)
    palette_index_selected = Signal(int)  # User clicked a swatch
    palette_color_changed = Signal(int, object)  # index, rgb tuple - user edited a color
    palette_swatch_hovered = Signal(object)  # int index or None - user hovered swatch
    # Drag-and-drop / tab signals
    folder_dropped = Signal(object)  # Path - emitted when folder/PNG dropped
    tab_folder_changed = Signal(object)  # Path | None - active tab's folder changed
    # Frame organization signals (V4)
    frame_rename_requested = Signal(str, str)  # frame_id, new_display_name
    frame_tag_toggled = Signal(str, str)  # frame_id, tag

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ai_frames: list[AIFrame] = []
        self._mapping_status: dict[str, str] = {}  # ai_frame_id -> status
        self._show_unmapped_only = False
        self._search_text: str = ""
        self._tag_filter: str = ""  # Empty = show all, or specific tag to filter
        self._sheet_palette: SheetPalette | None = None  # For quantized thumbnails

        # Tab management
        self._tab_folders: list[Path | None] = [None]  # One empty tab initially
        self._suppress_tab_signal: bool = False

        self.setAcceptDrops(True)
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
        self._palette_widget.index_selected.connect(self.palette_index_selected.emit)
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
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.setDragEnabled(False)  # AI frames are not draggable (they ARE rows)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
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

        Args:
            status_map: Dictionary mapping AI frame ID (filename) to status string
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

    def clear(self) -> None:
        """Clear all AI frames and reset tabs."""
        self._ai_frames = []
        self._mapping_status = {}
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
        # Refresh thumbnails to show quantized colors
        self._refresh_list(is_frame_list_change=False)
        # Force Qt to repaint the list viewport to ensure icon updates are visible
        # This fixes a Qt issue where icon caching can prevent visual updates
        self._list.viewport().update()

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

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._search_text = text.lower()
        self._refresh_list()

    def _on_filter_changed(self, checked: bool) -> None:
        """Handle filter checkbox toggle."""
        self._show_unmapped_only = checked
        self._refresh_list()

    def _create_quantized_thumbnail(self, frame_path: Path) -> QPixmap | None:
        """Create a palette-quantized thumbnail for an AI frame.

        If a sheet palette is defined, quantizes the frame image to show
        WYSIWYG colors matching the workbench preview. Otherwise loads
        the raw PNG.

        Args:
            frame_path: Path to the AI frame PNG file

        Returns:
            Scaled QPixmap ready for list item icon, or None on failure
        """
        if not frame_path.exists():
            return None

        # Load original image with PIL
        try:
            pil_image = Image.open(frame_path)
        except Exception:
            logger.warning("Failed to load image: %s", frame_path)
            return None

        # Apply palette quantization if palette is defined
        if self._sheet_palette is not None:
            try:
                # Ensure RGBA for quantization
                if pil_image.mode != "RGBA":
                    pil_image = pil_image.convert("RGBA")

                # Use color_mappings if defined, otherwise simple quantization
                if self._sheet_palette.color_mappings:
                    indexed = quantize_with_mappings(
                        pil_image,
                        self._sheet_palette.colors,
                        self._sheet_palette.color_mappings,
                        transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
                    )
                else:
                    indexed = quantize_to_palette(pil_image, self._sheet_palette.colors)

                # Convert indexed back to RGBA for display (preserves palette colors)
                pil_image = indexed.convert("RGBA")
            except Exception:
                logger.warning("Failed to quantize image: %s", frame_path, exc_info=True)
                # Fall through to use original image

        # Convert to QPixmap
        pixmap = pil_to_qpixmap(pil_image)
        if pixmap is None or pixmap.isNull():
            return None

        # Scale to thumbnail size
        return pixmap.scaled(
            THUMBNAIL_SIZE,
            THUMBNAIL_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

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

        frame_id = item.data(Qt.ItemDataRole.UserRole)
        if frame_id is None:
            return

        # Get frame to check current tags
        frame = next((f for f in self._ai_frames if f.id == frame_id), None)
        current_tags = frame.tags if frame else frozenset()

        menu = QMenu(self)

        # Rename action
        rename_action = menu.addAction("Rename...")
        rename_action.triggered.connect(lambda: self._show_rename_dialog(frame_id))

        # Tags submenu
        tags_menu = menu.addMenu("Tags")
        for tag in sorted(FRAME_TAGS):
            action = tags_menu.addAction(tag.capitalize())
            action.setCheckable(True)
            action.setChecked(tag in current_tags)
            # Capture tag in closure
            action.triggered.connect(lambda checked, t=tag: self.frame_tag_toggled.emit(frame_id, t))

        menu.addSeparator()

        edit_action = menu.addAction("Edit in Sprite Editor")
        edit_action.triggered.connect(lambda: self.edit_in_sprite_editor_requested.emit(frame_id))

        edit_palette_action = menu.addAction("Edit Palette...")

        def emit_edit_palette() -> None:
            logger.info("Edit Palette clicked for frame: %s", frame_id)
            self.edit_frame_palette_requested.emit(frame_id)

        edit_palette_action.triggered.connect(emit_edit_palette)

        menu.addSeparator()

        remove_action = menu.addAction("Remove from Project")
        remove_action.triggered.connect(lambda: self.remove_from_project_requested.emit(frame_id))

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
                color = STATUS_COLORS.get(status, STATUS_COLORS["unmapped"])
                item.setForeground(QBrush(color))

                # Load thumbnail (quantized if palette defined)
                thumbnail = self._create_quantized_thumbnail(frame.path)
                if thumbnail is not None:
                    item.setIcon(QIcon(thumbnail))

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
        finally:
            self._list.blockSignals(False)

        # Phase 2 fix: Notify listeners if selection was silently restored during frame list change
        if is_frame_list_change and selection_restored and restored_id is not None:
            self.ai_frame_selected.emit(restored_id)
        # NOTE: Removed "Bug #1 fix" that emitted empty string when selection was lost.
        # The workspace state manager is now the source of truth for selection,
        # and panes should not clear external state when filters hide items.

    def _on_tag_filter_changed(self, index: int) -> None:
        """Handle tag filter combo box change."""
        self._tag_filter = self._tag_filter_combo.currentData() or ""
        self._refresh_list()

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

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on list item - show rename dialog."""
        frame_id = item.data(Qt.ItemDataRole.UserRole)
        if frame_id:
            self._show_rename_dialog(frame_id)

    def refresh_frame(self, frame_id: str) -> None:
        """Refresh display for a single frame after tag/name change.

        Triggers a full list refresh to reflect the change.

        Args:
            frame_id: ID of the frame that changed
        """
        # For simplicity, refresh the entire list
        # A more optimized approach would update only the affected item
        self._refresh_list(is_frame_list_change=False)

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
        """Handle drop - emit folder_dropped signal."""
        self._list.setStyleSheet("")  # Reset visual feedback

        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            event.ignore()
            return

        for url in mime_data.urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                # If PNG dropped, use parent directory
                if path.is_file() and path.suffix.lower() == ".png":
                    path = path.parent
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

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab selection change."""
        if self._suppress_tab_signal:
            return
        if index < 0 or index >= len(self._tab_folders):
            return
        folder = self._tab_folders[index]
        self.tab_folder_changed.emit(folder)

    def _on_tab_close_requested(self, index: int) -> None:
        """Handle tab close button click."""
        self.close_tab(index)

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
