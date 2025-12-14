from typing import Any

"""Sprite selector widget for ROM extraction"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.styles import get_prominent_action_button_style
from ui.styles.theme import COLORS

from .base_widget import BaseExtractionWidget

# UI Spacing Constants (matching main panel)
SPACING_SMALL = 6
SPACING_MEDIUM = 10
SPACING_LARGE = 16
SPACING_XLARGE = 20
BUTTON_MIN_HEIGHT = 32
COMBO_MIN_WIDTH = 200
BUTTON_MAX_WIDTH = 150
LABEL_MIN_WIDTH = 120

class SpriteSelectorWidget(BaseExtractionWidget):
    """Widget for selecting sprites from ROM"""

    # Signals
    sprite_changed = Signal(int)  # Emitted when sprite selection changes
    find_sprites_clicked = Signal()  # Emitted when find sprites button clicked

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Sprite location selection with compact layout
        sprite_group = self._create_group_box("Sprite Selection")
        sprite_layout = QVBoxLayout()
        sprite_layout.setSpacing(4)  # Reduce spacing
        sprite_layout.setContentsMargins(8, 8, 8, 8)  # Reduce margins

        # Sprite selection row
        sprite_row = QHBoxLayout()
        sprite_row.setSpacing(SPACING_MEDIUM)

        sprite_label = QLabel("Sprite:")
        sprite_label.setMinimumWidth(60)
        sprite_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sprite_row.addWidget(sprite_label)

        self.sprite_combo = QComboBox()
        self.sprite_combo.setMinimumWidth(300)
        if self.sprite_combo:
            self.sprite_combo.addItem("Select ROM file first...", None)
        if self.sprite_combo:
            self.sprite_combo.setEnabled(False)
        self.sprite_combo.currentIndexChanged.connect(self._on_sprite_changed)
        sprite_row.addWidget(self.sprite_combo, 1)

        sprite_layout.addLayout(sprite_row)

        # Offset and Find button row
        offset_row = QHBoxLayout()
        offset_row.setSpacing(SPACING_MEDIUM)

        offset_label = QLabel("Offset:")
        offset_label.setMinimumWidth(60)
        offset_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        offset_row.addWidget(offset_label)

        self.offset_label = QLabel("--")
        if self.offset_label:
            self.offset_label.setStyleSheet(f"font-family: monospace; color: {COLORS['border_focus']}; font-size: 14px;")
        self.offset_label.setMinimumWidth(100)
        offset_row.addWidget(self.offset_label)

        offset_row.addStretch()

        # Find Sprites button - prominent styling for discoverability
        self.find_sprites_btn = QPushButton("Find Sprites (Ctrl+F)")
        self.find_sprites_btn.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.find_sprites_btn.setFixedWidth(BUTTON_MAX_WIDTH + 30)  # Slightly wider for shortcut text
        self.find_sprites_btn.setShortcut(QKeySequence("Ctrl+F"))
        self.find_sprites_btn.setToolTip("Scan ROM for valid sprite offsets\n\nKeyboard shortcut: Ctrl+F")
        self.find_sprites_btn.setStyleSheet(get_prominent_action_button_style())
        _ = self.find_sprites_btn.clicked.connect(self.find_sprites_clicked.emit)
        if self.find_sprites_btn:
            self.find_sprites_btn.setEnabled(False)
        offset_row.addWidget(self.find_sprites_btn)

        sprite_layout.addLayout(offset_row)
        sprite_group.setLayout(sprite_layout)

        layout.addWidget(sprite_group)
        self.setLayout(layout)

    def _on_sprite_changed(self, index: int):
        """Handle internal sprite change"""
        self.sprite_changed.emit(index)

    def clear(self):
        """Clear sprite selection"""
        if self.sprite_combo:
            self.sprite_combo.clear()
        if self.sprite_combo:
            self.sprite_combo.addItem("Select ROM file first...", None)
        if self.sprite_combo:
            self.sprite_combo.setEnabled(False)
        if self.offset_label:
            self.offset_label.setText("--")
        if self.find_sprites_btn:
            self.find_sprites_btn.setEnabled(False)

    def add_sprite(self, name: str, data: Any):
        """Add a sprite to the combo box"""
        if self.sprite_combo:
            self.sprite_combo.addItem(name, data)

    def insert_separator(self, index: int):
        """Insert a separator at the given index"""
        self.sprite_combo.insertSeparator(index)

    def set_enabled(self, enabled: bool):
        """Enable/disable the sprite combo"""
        if self.sprite_combo:
            self.sprite_combo.setEnabled(enabled)

    def get_current_index(self) -> int:
        """Get current selection index"""
        return self.sprite_combo.currentIndex()

    def get_current_data(self):
        """Get data for current selection"""
        return self.sprite_combo.currentData()

    def set_current_index(self, index: int):
        """Set current selection index"""
        if self.sprite_combo:
            self.sprite_combo.setCurrentIndex(index)

    def count(self) -> int:
        """Get number of items"""
        return self.sprite_combo.count()

    def item_data(self, index: int):
        """Get data at specific index"""
        return self.sprite_combo.itemData(index)

    def item_text(self, index: int) -> str:
        """Get text at specific index"""
        return self.sprite_combo.itemText(index)

    def set_offset_text(self, text: str):
        """Update the offset label"""
        if self.offset_label:
            self.offset_label.setText(text)

    def set_find_button_enabled(self, enabled: bool):
        """Enable/disable find sprites button"""
        if self.find_sprites_btn:
            self.find_sprites_btn.setEnabled(enabled)

    def set_find_button_text(self, text: str):
        """Update find sprites button text"""
        if self.find_sprites_btn:
            self.find_sprites_btn.setText(text)

    def set_find_button_tooltip(self, tooltip: str):
        """Update find sprites button tooltip"""
        self.find_sprites_btn.setToolTip(tooltip)
