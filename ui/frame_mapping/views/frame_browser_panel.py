"""Frame Browser Panel for displaying AI and Game frames."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame, GameFrame

logger = logging.getLogger(__name__)

# Thumbnail size for list items
THUMBNAIL_SIZE = 64


class FrameBrowserPanel(QWidget):
    """Panel for browsing AI and Game frames.

    Displays two lists:
    - AI Frames: PNG files from a directory
    - Game Frames: Captures from Mesen 2

    Signals:
        ai_frame_selected: Emitted when an AI frame is selected (index)
        game_frame_selected: Emitted when a game frame is selected (id)
    """

    ai_frame_selected = Signal(int)  # AI frame index
    game_frame_selected = Signal(str)  # Game frame ID

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ai_frames: list[AIFrame] = []
        self._game_frames: list[GameFrame] = []
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

        self._ai_count_label = QLabel("No frames loaded")
        self._ai_count_label.setStyleSheet("color: #888; font-size: 11px;")
        ai_layout.addWidget(self._ai_count_label)

        self._ai_list = QListWidget()
        self._ai_list.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self._ai_list.setViewMode(QListWidget.ViewMode.ListMode)
        self._ai_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._ai_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._ai_list.currentRowChanged.connect(self._on_ai_selection_changed)
        ai_layout.addWidget(self._ai_list)

        layout.addWidget(ai_group)

        # Game Frames section
        game_group = QGroupBox("Game Frames")
        game_layout = QVBoxLayout(game_group)
        game_layout.setContentsMargins(4, 8, 4, 4)

        self._game_count_label = QLabel("No captures loaded")
        self._game_count_label.setStyleSheet("color: #888; font-size: 11px;")
        game_layout.addWidget(self._game_count_label)

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
        logger.debug("Loaded %d AI frames into browser", count)

    def set_game_frames(self, frames: list[GameFrame]) -> None:
        """Set the game frames to display.

        Args:
            frames: List of GameFrame objects
        """
        self._game_frames = frames
        self._game_list.clear()

        for frame in frames:
            item = QListWidgetItem()

            # Format: "F17987 @0x035000"
            if frame.rom_offsets:
                offset_str = f"@0x{frame.rom_offsets[0]:06X}"
            else:
                offset_str = ""
            item.setText(f"{frame.id} {offset_str}".strip())
            item.setData(Qt.ItemDataRole.UserRole, frame.id)

            # Load thumbnail from capture preview if available
            if frame.capture_path and frame.capture_path.exists():
                # Check for a rendered preview image
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

        count = len(frames)
        self._game_count_label.setText(f"{count} capture{'s' if count != 1 else ''}")
        logger.debug("Loaded %d game frames into browser", count)

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
