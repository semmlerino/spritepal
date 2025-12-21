from typing import Any

"""Sprite selector widget for ROM extraction"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# UI Spacing Constants (imported from centralized module)
from ui.common.spacing_constants import (
    CONTROL_PANEL_BUTTON_WIDTH,
    CONTROL_PANEL_LABEL_WIDTH,
    EXTRACTION_BUTTON_MIN_HEIGHT as BUTTON_MIN_HEIGHT,
    SPACING_COMPACT_MEDIUM as SPACING_MEDIUM,
)
from ui.styles import get_prominent_action_button_style
from ui.styles.theme import COLORS

from .base_widget import BaseExtractionWidget


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
        sprite_layout = QVBoxLayout()
        sprite_layout.setSpacing(SPACING_MEDIUM)  # Use consistent spacing constant
        sprite_layout.setContentsMargins(0, 0, 0, 0)  # Group box CSS provides padding

        # Sprite selection row
        sprite_row = QHBoxLayout()
        sprite_row.setSpacing(SPACING_MEDIUM)

        sprite_label = QLabel("Sprite:")
        sprite_label.setMinimumWidth(CONTROL_PANEL_LABEL_WIDTH)
        sprite_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sprite_row.addWidget(sprite_label)

        self.sprite_combo = QComboBox()
        self.sprite_combo.setMinimumWidth(300)
        self.sprite_combo.addItem("Select ROM file first...", None)
        self.sprite_combo.setEnabled(False)
        self.sprite_combo.currentIndexChanged.connect(self._on_sprite_changed)
        sprite_row.addWidget(self.sprite_combo, 1)

        # Spacer to align with Find Sprites button in offset row
        sprite_spacer = QWidget()
        sprite_spacer.setFixedWidth(CONTROL_PANEL_BUTTON_WIDTH)
        sprite_row.addWidget(sprite_spacer)

        sprite_layout.addLayout(sprite_row)

        # Offset and Find button row
        offset_row = QHBoxLayout()
        offset_row.setSpacing(SPACING_MEDIUM)

        offset_label = QLabel("Offset:")
        offset_label.setMinimumWidth(CONTROL_PANEL_LABEL_WIDTH)
        offset_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        offset_row.addWidget(offset_label)

        self.offset_label = QLabel("(select sprite)")
        self.offset_label.setStyleSheet(f"font-family: monospace; color: {COLORS['disabled_text']}; font-size: 14px;")
        self.offset_label.setMinimumWidth(100)
        self.offset_label.setEnabled(False)  # Visually disabled until sprite selected
        offset_row.addWidget(self.offset_label, 1)  # Stretch factor fills space

        # Find Sprites button - prominent styling for discoverability
        self.find_sprites_btn = QPushButton("Find Sprites (Ctrl+F)")
        self.find_sprites_btn.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.find_sprites_btn.setFixedWidth(CONTROL_PANEL_BUTTON_WIDTH)
        self.find_sprites_btn.setShortcut(QKeySequence("Ctrl+F"))
        self.find_sprites_btn.setToolTip("Scan ROM for valid sprite offsets\n\nKeyboard shortcut: Ctrl+F")
        self.find_sprites_btn.setStyleSheet(get_prominent_action_button_style())
        _ = self.find_sprites_btn.clicked.connect(self.find_sprites_clicked.emit)
        self.find_sprites_btn.setEnabled(False)
        offset_row.addWidget(self.find_sprites_btn)

        sprite_layout.addLayout(offset_row)

        self._setup_widget_with_group("Sprite Selection", sprite_layout)

    def _on_sprite_changed(self, index: int):
        """Handle internal sprite change"""
        self.sprite_changed.emit(index)

    def clear(self):
        """Clear sprite selection"""
        self.sprite_combo.clear()
        self.sprite_combo.addItem("Select ROM file first...", None)
        self.sprite_combo.setEnabled(False)
        self.offset_label.setText("(select sprite)")
        self.offset_label.setStyleSheet(f"font-family: monospace; color: {COLORS['disabled_text']}; font-size: 14px;")
        self.offset_label.setEnabled(False)  # Visually disabled
        self.find_sprites_btn.setEnabled(False)

    def add_sprite(self, name: str, data: Any):
        """Add a sprite to the combo box"""
        self.sprite_combo.addItem(name, data)

    def insert_separator(self, index: int):
        """Insert a separator at the given index"""
        self.sprite_combo.insertSeparator(index)

    def set_enabled(self, enabled: bool):
        """Enable/disable the sprite combo"""
        self.sprite_combo.setEnabled(enabled)

    def get_current_index(self) -> int:
        """Get current selection index"""
        return self.sprite_combo.currentIndex()

    def get_current_data(self):
        """Get data for current selection"""
        return self.sprite_combo.currentData()

    def set_current_index(self, index: int):
        """Set current selection index"""
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
        self.offset_label.setText(text)
        self.offset_label.setEnabled(True)  # Enable when value is set
        # Use highlighted color for actual offset values
        self.offset_label.setStyleSheet(f"font-family: monospace; color: {COLORS['border_focus']}; font-size: 14px;")

    def set_find_button_enabled(self, enabled: bool):
        """Enable/disable find sprites button"""
        self.find_sprites_btn.setEnabled(enabled)

    def set_find_button_text(self, text: str):
        """Update find sprites button text"""
        self.find_sprites_btn.setText(text)

    def set_find_button_tooltip(self, tooltip: str):
        """Update find sprites button tooltip"""
        self.find_sprites_btn.setToolTip(tooltip)

    def set_disabled_state(self, message: str = "Select ROM first") -> None:
        """Show disabled state with explanation message.

        Use this to clearly indicate why the sprite selector is unavailable.

        Args:
            message: Explanation shown in the combo placeholder
        """
        self.sprite_combo.clear()
        self.sprite_combo.addItem(message, None)
        self.sprite_combo.setEnabled(False)
        self.offset_label.setText("(select sprite)")
        self.offset_label.setStyleSheet(f"font-family: monospace; color: {COLORS['disabled_text']}; font-size: 14px;")
        self.offset_label.setEnabled(False)  # Visually disabled
        self.find_sprites_btn.setEnabled(False)
