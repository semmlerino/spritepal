"""
History tab widget for manual offset dialog.

Manages and displays a history of found sprites for quick navigation.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import (
    COMPACT_BUTTON_HEIGHT,
    GROUP_PADDING,
    SPACING_TINY,
)
from utils.logging_config import get_logger
from utils.sprite_history_manager import SpriteHistoryManager

logger = get_logger(__name__)

class SimpleHistoryTab(QWidget):
    """
    History tab for tracking and navigating to previously found sprites.

    Signals:
        sprite_selected: Emitted when a sprite is selected from history
    """

    sprite_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialize the history tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Use the sprite history manager
        self._history_manager = SpriteHistoryManager()

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up space-efficient history tab UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_TINY)
        layout.setContentsMargins(GROUP_PADDING, GROUP_PADDING, GROUP_PADDING, GROUP_PADDING)

        # Compact title
        title = self._create_section_title("Found Sprites")
        layout.addWidget(title)

        # Sprite list
        self.sprite_list = QListWidget()
        self.sprite_list.itemDoubleClicked.connect(self._on_sprite_double_clicked)
        layout.addWidget(self.sprite_list)

        # Compact controls row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(6)

        clear_button = QPushButton("Clear")
        clear_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        clear_button.setFixedHeight(COMPACT_BUTTON_HEIGHT)
        clear_button.clicked.connect(self.clear_history)
        controls_layout.addWidget(clear_button)

        go_button = QPushButton("Go to Selected")
        go_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        go_button.setFixedHeight(COMPACT_BUTTON_HEIGHT)
        go_button.clicked.connect(self._go_to_selected)
        controls_layout.addWidget(go_button)

        layout.addLayout(controls_layout)

    def _on_sprite_double_clicked(self, item: QListWidgetItem) -> None:
        """
        Handle double-click on sprite item.

        Args:
            item: Clicked list widget item
        """
        try:
            # Extract offset from item text
            text = item.text()
            if "0x" in text:
                offset_str = text.split("0x")[1].split(" ")[0]
                offset = int(offset_str, 16)
                self.sprite_selected.emit(offset)
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to extract offset from item: {e}")

    def _go_to_selected(self) -> None:
        """Go to selected sprite."""
        current_item = self.sprite_list.currentItem()
        if current_item:
            self._on_sprite_double_clicked(current_item)

    def add_sprite(self, offset: int, quality: float = 1.0) -> None:
        """
        Add a sprite to history.

        Args:
            offset: Sprite offset in ROM
            quality: Sprite quality score
        """
        # Use manager to add sprite (handles duplicates and limits)
        if self._history_manager.add_sprite(offset, quality):
            # Only add to UI if successfully added to manager
            item_text = f"0x{offset:06X} - Quality: {quality:.2f}"
            if self.sprite_list:
                self.sprite_list.addItem(item_text)

    def clear_history(self) -> None:
        """Clear sprite history."""
        self._history_manager.clear_history()
        if self.sprite_list:
            self.sprite_list.clear()

    def get_sprites(self) -> list[tuple[int, float]]:
        """
        Get all sprites as (offset, quality) tuples.

        Returns:
            List of (offset, quality) tuples
        """
        return self._history_manager.get_sprites()

    def set_sprites(self, sprites: list[tuple[int, float]]) -> None:
        """
        Set sprites from list.

        Args:
            sprites: List of (offset, quality) tuples
        """
        self.clear_history()
        for offset, quality in sprites:
            self.add_sprite(offset, quality)

    def get_sprite_count(self) -> int:
        """
        Get number of found sprites.

        Returns:
            Number of sprites in history
        """
        return self._history_manager.get_sprite_count()

    def _create_section_title(self, text: str) -> QLabel:
        """
        Create a styled section title label.

        Args:
            text: Title text

        Returns:
            Styled label widget
        """
        title = QLabel(text)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title.setFont(title_font)
        title.setStyleSheet("color: #4488dd; padding: 2px 4px; border-radius: 3px;")
        return title
