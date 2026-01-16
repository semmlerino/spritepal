"""Sprite selector widget for ROM extraction"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QWidget,
)

from core.types import SpritePreset
from ui.common.spacing_constants import EXTRACTION_ACTION_BUTTON_HEIGHT
from ui.styles import get_prominent_action_button_style
from ui.styles.theme import COLORS

from .base_widget import BaseExtractionWidget


class SpriteSelectorWidget(BaseExtractionWidget):
    """Widget for selecting sprites from ROM"""

    # Signals
    sprite_changed = Signal(object)  # Emitted when sprite selection changes (data)
    find_sprites_clicked = Signal()  # Emitted when find sprites button clicked
    manage_presets_clicked = Signal()  # Emitted when manage presets button clicked
    preset_applied = Signal(SpritePreset)  # Emitted when a preset is applied

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _set_offset_label_style(self, color_key: str = "disabled_text") -> None:
        """Apply consistent monospace styling to offset label."""
        self.offset_label.setStyleSheet(f"font-family: monospace; color: {COLORS[color_key]}; font-size: 14px;")

    def _setup_ui(self) -> None:
        """Initialize the user interface"""
        sprite_layout = self._create_vbox_layout()

        # Sprite selection tree
        self.sprite_tree = QTreeWidget()
        self.sprite_tree.setHeaderLabels(["Sprite Name"])
        self.sprite_tree.header().setVisible(False)
        self.sprite_tree.setMinimumHeight(200)
        self.sprite_tree.setAlternatingRowColors(True)
        self.sprite_tree.currentItemChanged.connect(self._on_selection_changed)

        # Style the tree
        self.sprite_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {COLORS["input_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
            }}
            QTreeWidget::item {{
                padding: 4px;
            }}
        """)

        sprite_layout.addWidget(self.sprite_tree)

        # Offset display row (simplified - no button)
        offset_row = self._create_hbox_layout()

        offset_label = self._create_control_label("Offset:")
        offset_row.addWidget(offset_label)

        self.offset_label = QLabel("--")
        self._set_offset_label_style()
        self.offset_label.setMinimumWidth(100)
        offset_row.addWidget(self.offset_label, 1)  # Stretch factor fills space

        sprite_layout.addLayout(offset_row)

        # Button row with Find Sprites (prominent) and Presets (secondary)
        button_row = self._create_hbox_layout()

        # Find Sprites button - primary discovery action
        self.find_sprites_btn = QPushButton("🔍 Find Sprites in ROM (Ctrl+F)")
        self.find_sprites_btn.setMinimumHeight(EXTRACTION_ACTION_BUTTON_HEIGHT)
        self.find_sprites_btn.setShortcut(QKeySequence("Ctrl+F"))
        self.find_sprites_btn.setToolTip("Scan ROM for valid sprite offsets\n\nKeyboard shortcut: Ctrl+F")
        self.find_sprites_btn.setStyleSheet(get_prominent_action_button_style())
        self.find_sprites_btn.clicked.connect(self.find_sprites_clicked.emit)
        self.find_sprites_btn.setEnabled(False)
        button_row.addWidget(self.find_sprites_btn, 1)  # Stretch to take more space

        # Presets button - manage saved sprite presets
        self.presets_btn = QPushButton("📁 Presets")
        self.presets_btn.setMinimumHeight(EXTRACTION_ACTION_BUTTON_HEIGHT)
        self.presets_btn.setMinimumWidth(105)  # Fits "📁 Presets" with emoji
        self.presets_btn.setMaximumWidth(130)  # Keep compact
        self.presets_btn.setToolTip(
            "Manage saved sprite presets\n\n"
            "Save and load known sprite offsets for quick access.\n"
            "Import/export presets to share with the community."
        )
        self.presets_btn.clicked.connect(self.manage_presets_clicked.emit)
        button_row.addWidget(self.presets_btn)

        sprite_layout.addLayout(button_row)

        self._setup_widget_with_group("Sprite Selection", sprite_layout)

    def _on_selection_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        if current:
            data = current.data(0, Qt.ItemDataRole.UserRole)
            # Only emit if data is present (skip category headers)
            if data is not None:
                self.sprite_changed.emit(data)

    def count(self) -> int:
        """Get number of top-level items."""
        return self.sprite_tree.topLevelItemCount()

    def clear(self) -> None:
        """Clear sprite selection"""
        self.sprite_tree.clear()
        self.offset_label.setText("--")
        self._set_offset_label_style()
        self.find_sprites_btn.setEnabled(False)

    def add_sprite(self, name: str, data: object) -> None:
        """Add a sprite to the tree with categorization."""
        if " - " in name:
            category, item_name = name.split(" - ", 1)
            parent = self._get_or_create_category(category)
            item = QTreeWidgetItem(parent)
            item.setText(0, item_name)
        else:
            item = QTreeWidgetItem(self.sprite_tree)
            item.setText(0, name)

        item.setData(0, Qt.ItemDataRole.UserRole, data)

    def _get_or_create_category(self, name: str) -> QTreeWidgetItem:
        # Check existing top-level items
        for i in range(self.sprite_tree.topLevelItemCount()):
            item = self.sprite_tree.topLevelItem(i)
            if item is not None and item.text(0) == name:
                return item

        # Create new category
        item = QTreeWidgetItem(self.sprite_tree)
        item.setText(0, name)
        # Style category item
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        item.setExpanded(True)
        return item

    def insert_separator(self, index: int) -> None:
        """Insert a separator (No-op for tree)."""
        pass

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable the sprite tree"""
        self.sprite_tree.setEnabled(enabled)

    def get_current_data(self) -> None:
        """Get data for current selection"""
        current = self.sprite_tree.currentItem()
        if current:
            return current.data(0, Qt.ItemDataRole.UserRole)
        return None

    def select_item_by_data(self, data: object) -> None:
        """Select item matching data."""
        # Traverse tree
        iterator = QTreeWidgetItemIterator(self.sprite_tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.ItemDataRole.UserRole) == data:
                self.sprite_tree.setCurrentItem(item)
                return
            iterator += 1

    def set_offset_text(self, text: str) -> None:
        """Update the offset label"""
        self.offset_label.setText(text)
        self.offset_label.setEnabled(True)  # Enable when value is set
        # Use highlighted color for actual offset values
        self._set_offset_label_style("border_focus")

    def set_find_button_enabled(self, enabled: bool) -> None:
        """Enable/disable find sprites button"""
        self.find_sprites_btn.setEnabled(enabled)

    def set_find_button_text(self, text: str) -> None:
        """Update find sprites button text"""
        self.find_sprites_btn.setText(text)

    def set_find_button_tooltip(self, tooltip: str) -> None:
        """Update find sprites button tooltip"""
        self.find_sprites_btn.setToolTip(tooltip)

    def set_disabled_state(self, message: str = "Select ROM first") -> None:
        """Show disabled state with explanation message."""
        self.clear()
        item = QTreeWidgetItem(self.sprite_tree)
        item.setText(0, message)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        self.sprite_tree.setEnabled(False)
        self.find_sprites_btn.setEnabled(False)
