"""Frame Browser Panel for displaying AI and Game frames."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame, GameFrame

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


class FrameBrowserPanel(QWidget):
    """Panel for browsing AI and Game frames.

    Displays two lists:
    - AI Frames: PNG files from a directory
    - Game Frames: Captures from Mesen 2

    Signals:
        ai_frame_selected: Emitted when an AI frame is selected (index)
        game_frame_selected: Emitted when a game frame is selected (id)
        map_requested: Emitted when user clicks the Map Selected button
    """

    ai_frame_selected = Signal(int)  # AI frame index
    game_frame_selected = Signal(str)  # Game frame ID
    map_requested = Signal()  # User wants to map selected frames
    auto_advance_changed = Signal(bool)  # Auto-advance toggle state changed

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ai_frames: list[AIFrame] = []
        self._game_frames: list[GameFrame] = []
        self._mapping_status: dict[int, str] = {}  # ai_frame_index -> status
        self._show_unmapped_only = False

        # Search and filter state
        self._ai_search_text: str = ""
        self._game_search_text: str = ""
        self._show_unlinked_only: bool = False
        self._game_link_status: dict[str, int | None] = {}  # game_frame_id -> ai_index or None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # AI Frames section
        ai_group = QGroupBox("AI Frames")
        ai_layout = QVBoxLayout(ai_group)
        ai_layout.setContentsMargins(4, 8, 4, 4)

        # AI search box
        self._ai_search_box = QLineEdit()
        self._ai_search_box.setPlaceholderText("Search AI frames...")
        self._ai_search_box.setStyleSheet("font-size: 11px;")
        self._ai_search_box.setClearButtonEnabled(True)
        self._ai_search_box.textChanged.connect(self._on_ai_search_changed)
        ai_layout.addWidget(self._ai_search_box)

        # Header row with count and filters
        ai_header = QHBoxLayout()
        ai_header.setContentsMargins(0, 0, 0, 0)
        self._ai_count_label = QLabel("No frames loaded")
        self._ai_count_label.setStyleSheet("color: #888; font-size: 11px;")
        ai_header.addWidget(self._ai_count_label)
        ai_header.addStretch()

        self._unmapped_filter = QCheckBox("Unmapped only")
        self._unmapped_filter.setToolTip("Show only unmapped AI frames")
        self._unmapped_filter.setStyleSheet("font-size: 11px;")
        self._unmapped_filter.toggled.connect(self._on_filter_changed)
        ai_header.addWidget(self._unmapped_filter)

        self._auto_advance_checkbox = QCheckBox("Auto-advance")
        self._auto_advance_checkbox.setToolTip("Automatically select the next unmapped AI frame after linking")
        self._auto_advance_checkbox.setStyleSheet("font-size: 11px;")
        self._auto_advance_checkbox.setChecked(False)  # Default OFF per UX spec
        self._auto_advance_checkbox.toggled.connect(self.auto_advance_changed.emit)
        ai_header.addWidget(self._auto_advance_checkbox)

        ai_layout.addLayout(ai_header)

        self._ai_list = QListWidget()
        self._ai_list.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self._ai_list.setViewMode(QListWidget.ViewMode.ListMode)
        self._ai_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._ai_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._ai_list.currentRowChanged.connect(self._on_ai_selection_changed)
        ai_layout.addWidget(self._ai_list)

        layout.addWidget(ai_group)

        # Map Selected button (between lists)
        map_button_layout = QHBoxLayout()
        map_button_layout.setContentsMargins(0, 0, 0, 0)
        self._map_button = QPushButton("Map Selected")
        self._map_button.setToolTip("Link the selected AI frame to the selected game frame")
        self._map_button.setEnabled(False)  # Disabled until both selected
        self._map_button.clicked.connect(self.map_requested.emit)
        map_button_layout.addStretch()
        map_button_layout.addWidget(self._map_button)
        map_button_layout.addStretch()
        layout.addLayout(map_button_layout)

        # Game Frames section
        game_group = QGroupBox("Game Frames")
        game_layout = QVBoxLayout(game_group)
        game_layout.setContentsMargins(4, 8, 4, 4)

        # Game search box
        self._game_search_box = QLineEdit()
        self._game_search_box.setPlaceholderText("Search game frames...")
        self._game_search_box.setStyleSheet("font-size: 11px;")
        self._game_search_box.setClearButtonEnabled(True)
        self._game_search_box.textChanged.connect(self._on_game_search_changed)
        game_layout.addWidget(self._game_search_box)

        # Game header row with count and filter
        game_header = QHBoxLayout()
        game_header.setContentsMargins(0, 0, 0, 0)
        self._game_count_label = QLabel("No captures loaded")
        self._game_count_label.setStyleSheet("color: #888; font-size: 11px;")
        game_header.addWidget(self._game_count_label)
        game_header.addStretch()

        self._unlinked_filter = QCheckBox("Unlinked only")
        self._unlinked_filter.setToolTip("Show only game frames not linked to an AI frame")
        self._unlinked_filter.setStyleSheet("font-size: 11px;")
        self._unlinked_filter.toggled.connect(self._on_game_filter_changed)
        game_header.addWidget(self._unlinked_filter)

        game_layout.addLayout(game_header)

        self._game_list = QListWidget()
        self._game_list.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self._game_list.setViewMode(QListWidget.ViewMode.ListMode)
        self._game_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._game_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._game_list.currentRowChanged.connect(self._on_game_selection_changed)
        game_layout.addWidget(self._game_list)

        layout.addWidget(game_group)

    def set_ai_frames(self, frames: list[AIFrame]) -> None:
        """Set the AI frames to display.

        Args:
            frames: List of AIFrame objects
        """
        self._ai_frames = frames
        self._ai_list.clear()

        for frame in frames:
            item = QListWidgetItem()
            item.setText(frame.path.name)
            item.setData(Qt.ItemDataRole.UserRole, frame.index)

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

            self._ai_list.addItem(item)

        count = len(frames)
        self._ai_count_label.setText(f"{count} frame{'s' if count != 1 else ''}")

    def set_game_frames(self, frames: list[GameFrame]) -> None:
        """Set the game frames to display.

        Args:
            frames: List of GameFrame objects
        """
        self._game_frames = frames
        self._refresh_game_list()

    def add_game_frame(self, frame: GameFrame) -> None:
        """Add a single game frame to the list.

        Args:
            frame: GameFrame to add
        """
        self._game_frames.append(frame)
        self.set_game_frames(self._game_frames)

    def get_selected_ai_frame_index(self) -> int | None:
        """Get the currently selected AI frame index."""
        current = self._ai_list.currentItem()
        if current is None:  # type: ignore[reportUnnecessaryComparison]
            return None
        return current.data(Qt.ItemDataRole.UserRole)

    def get_selected_game_frame_id(self) -> str | None:
        """Get the currently selected game frame ID."""
        current = self._game_list.currentItem()
        if current is None:  # type: ignore[reportUnnecessaryComparison]
            return None
        return current.data(Qt.ItemDataRole.UserRole)

    def clear_ai_frames(self) -> None:
        """Clear all AI frames."""
        self._ai_frames = []
        self._ai_list.clear()
        self._ai_count_label.setText("No frames loaded")

    def clear_game_frames(self) -> None:
        """Clear all game frames."""
        self._game_frames = []
        self._game_list.clear()
        self._game_count_label.setText("No captures loaded")

    def clear_all(self) -> None:
        """Clear both AI and game frames."""
        self.clear_ai_frames()
        self.clear_game_frames()

    def _on_ai_selection_changed(self, row: int) -> None:
        """Handle AI frame selection change."""
        if row < 0:
            return
        item = self._ai_list.item(row)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.ai_frame_selected.emit(index)

    def _on_game_selection_changed(self, row: int) -> None:
        """Handle game frame selection change."""
        if row < 0:
            return
        item = self._game_list.item(row)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return
        frame_id = item.data(Qt.ItemDataRole.UserRole)
        if frame_id is not None:
            self.game_frame_selected.emit(frame_id)

    def select_ai_frame(self, index: int) -> None:
        """Programmatically select an AI frame by index.

        Blocks signals to prevent feedback loops when syncing selection.

        Args:
            index: The AI frame index to select
        """
        self._ai_list.blockSignals(True)
        try:
            for row in range(self._ai_list.count()):
                item = self._ai_list.item(row)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == index:  # type: ignore[reportUnnecessaryComparison]
                    self._ai_list.setCurrentRow(row)
                    break
        finally:
            self._ai_list.blockSignals(False)

    def select_game_frame(self, frame_id: str) -> None:
        """Programmatically select a game frame by ID.

        Blocks signals to prevent feedback loops when syncing selection.

        Args:
            frame_id: The game frame ID to select
        """
        self._game_list.blockSignals(True)
        try:
            for row in range(self._game_list.count()):
                item = self._game_list.item(row)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == frame_id:  # type: ignore[reportUnnecessaryComparison]
                    self._game_list.setCurrentRow(row)
                    break
        finally:
            self._game_list.blockSignals(False)

    def clear_game_selection(self) -> None:
        """Clear the game frame selection without emitting signals.

        Useful when an unmapped AI frame is selected to indicate no
        corresponding game frame.
        """
        self._game_list.blockSignals(True)
        try:
            self._game_list.clearSelection()
            self._game_list.setCurrentRow(-1)
        finally:
            self._game_list.blockSignals(False)

    def set_map_button_enabled(self, enabled: bool) -> None:
        """Set the enabled state of the Map Selected button.

        Args:
            enabled: Whether the button should be enabled
        """
        self._map_button.setEnabled(enabled)

    def _on_filter_changed(self, checked: bool) -> None:
        """Handle filter checkbox toggle."""
        self._show_unmapped_only = checked
        self._refresh_ai_list()

    def _on_ai_search_changed(self, text: str) -> None:
        """Handle AI search text change."""
        self._ai_search_text = text.lower()
        self._refresh_ai_list()

    def _on_game_search_changed(self, text: str) -> None:
        """Handle game search text change."""
        self._game_search_text = text.lower()
        self._refresh_game_list()

    def _on_game_filter_changed(self, checked: bool) -> None:
        """Handle game frame filter checkbox toggle."""
        self._show_unlinked_only = checked
        self._refresh_game_list()

    def set_mapping_status(self, status_map: dict[int, str]) -> None:
        """Update the mapping status for AI frames.

        Args:
            status_map: Dictionary mapping AI frame index to status string
                        (e.g., "unmapped", "mapped", "edited", "injected")
        """
        self._mapping_status = status_map
        self._refresh_ai_list()

    def _refresh_ai_list(self) -> None:
        """Refresh the AI frames list with current status colors, filter, and search."""
        self._ai_list.clear()

        visible_count = 0
        total_count = len(self._ai_frames)

        for frame in self._ai_frames:
            status = self._mapping_status.get(frame.index, "unmapped")

            # Apply unmapped filter
            if self._show_unmapped_only and status != "unmapped":
                continue

            # Apply search filter
            if self._ai_search_text and self._ai_search_text not in frame.path.name.lower():
                continue

            visible_count += 1

            item = QListWidgetItem()
            # Add status indicator to text
            status_indicator = "●" if status != "unmapped" else "○"
            item.setText(f"{status_indicator} {frame.path.name}")
            item.setData(Qt.ItemDataRole.UserRole, frame.index)

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

            self._ai_list.addItem(item)

        # Update count label
        if self._show_unmapped_only or self._ai_search_text:
            self._ai_count_label.setText(f"{visible_count}/{total_count} shown")
        else:
            self._ai_count_label.setText(f"{total_count} frame{'s' if total_count != 1 else ''}")

    def _refresh_game_list(self) -> None:
        """Refresh the game frames list with current filter and search."""
        self._game_list.clear()

        visible_count = 0
        total_count = len(self._game_frames)

        for frame in self._game_frames:
            linked_ai = self._game_link_status.get(frame.id)

            # Apply unlinked filter
            if self._show_unlinked_only and linked_ai is not None:
                continue

            # Apply search filter
            if self._game_search_text and self._game_search_text not in frame.id.lower():
                continue

            visible_count += 1

            item = QListWidgetItem()

            # Add link status indicator
            if linked_ai is not None:
                status_indicator = "●"  # Green linked
                color = STATUS_COLORS["mapped"]
            else:
                status_indicator = "○"  # Gray unlinked
                color = STATUS_COLORS["unmapped"]

            # Format: "● F17987 @0x035000" or "○ F17987 @0x035000"
            if frame.rom_offsets:
                offset_str = f"@0x{frame.rom_offsets[0]:06X}"
            else:
                offset_str = ""
            item.setText(f"{status_indicator} {frame.id} {offset_str}".strip())
            item.setData(Qt.ItemDataRole.UserRole, frame.id)
            item.setForeground(QBrush(color))

            # Set tooltip with link info
            if linked_ai is not None:
                item.setToolTip(f"Linked to AI frame {linked_ai}")
            else:
                item.setToolTip("Unlinked - click to link")

            # Load thumbnail from capture preview if available
            if frame.capture_path and frame.capture_path.exists():
                preview_path = frame.capture_path.with_suffix(".png")
                if preview_path.exists():
                    pixmap = QPixmap(str(preview_path))
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(
                            THUMBNAIL_SIZE,
                            THUMBNAIL_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        item.setIcon(QIcon(scaled))

            self._game_list.addItem(item)

        # Update count label
        if self._show_unlinked_only or self._game_search_text:
            self._game_count_label.setText(f"{visible_count}/{total_count} shown")
        else:
            self._game_count_label.setText(f"{total_count} capture{'s' if total_count != 1 else ''}")

    def set_game_frame_link_status(self, link_status: dict[str, int | None]) -> None:
        """Set the link status for game frames.

        Args:
            link_status: Mapping of game_frame_id -> ai_frame_index (or None if unlinked)
        """
        self._game_link_status = link_status
        self._refresh_game_list()
