"""
Sprite asset browser widget for the sprite editor.

Provides a searchable tree view of available sprites from ROM, Mesen2 captures,
and local files with thumbnail previews and context menu actions.
"""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QLineEdit,
    QMenu,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import SPACING_SMALL
from ui.styles.theme import COLORS


class ThumbnailDelegate(QStyledItemDelegate):
    """Delegate for rendering thumbnails in tree items."""

    THUMBNAIL_SIZE = 32

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the thumbnail delegate."""
        super().__init__(parent)
        self._placeholder_bg = QColor(COLORS["darker_gray"])
        self._placeholder_grid = QColor(COLORS["border"])
        self._placeholder_text = QColor(COLORS["text_muted"])

    @override
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        """
        Paint the tree item with thumbnail.

        Args:
            painter: QPainter to use
            option: Style options
            index: Model index to paint
        """
        # Let default paint handle selection/hover effects
        super().paint(painter, option, index)

        # Get item data
        item_data = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, dict):
            return

        # Skip category items (they have no offset)
        if "offset" not in item_data and "path" not in item_data:
            return

        painter.save()

        # Calculate thumbnail rectangle (left side of item)
        item_rect = option.rect  # type: ignore[attr-defined]  # PySide6 QStyleOption stubs incomplete
        thumbnail_rect = QRect(
            item_rect.x() + 4,
            item_rect.y() + 2,
            self.THUMBNAIL_SIZE,
            self.THUMBNAIL_SIZE,
        )

        # Draw thumbnail or placeholder
        thumbnail = item_data.get("thumbnail")
        if thumbnail and isinstance(thumbnail, QPixmap) and not thumbnail.isNull():
            # Scale to fit
            scaled = thumbnail.scaled(
                thumbnail_rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Center in rectangle
            x = thumbnail_rect.x() + (thumbnail_rect.width() - scaled.width()) // 2
            y = thumbnail_rect.y() + (thumbnail_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # Draw placeholder
            self._draw_placeholder(painter, thumbnail_rect)

        painter.restore()

    def _draw_placeholder(self, painter: QPainter, rect: QRect) -> None:
        """
        Draw a placeholder for items without thumbnails.

        Args:
            painter: QPainter to use
            rect: Rectangle to draw in
        """
        # Fill background
        painter.fillRect(rect, self._placeholder_bg)

        # Draw border
        painter.setPen(QPen(self._placeholder_grid, 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        # Draw grid pattern
        grid_size = 8
        for x in range(rect.x(), rect.right(), grid_size):
            painter.drawLine(x, rect.y(), x, rect.bottom())
        for y in range(rect.y(), rect.bottom(), grid_size):
            painter.drawLine(rect.x(), y, rect.right(), y)

    @override
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        """
        Return size hint for the item.

        Args:
            option: Style options
            index: Model index

        Returns:
            Size hint with enough height for thumbnail
        """
        # Ensure enough height for thumbnail + padding
        return QSize(option.rect.width(), self.THUMBNAIL_SIZE + 4)  # type: ignore[attr-defined]  # PySide6 QStyleOption stubs incomplete


class SpriteAssetBrowser(QWidget):
    """
    Asset browser widget for sprite editor.

    Displays available sprites from ROM, Mesen2 captures, and local files
    in a searchable tree view with thumbnails and context menu actions.
    """

    # Signals
    sprite_selected = Signal(int, str)  # offset, source_type
    sprite_activated = Signal(int, str)  # double-click -> offset, source_type
    rename_requested = Signal(int, str)  # offset, new_name
    delete_requested = Signal(int, str)  # offset, source_type

    # Category names
    CATEGORY_ROM = "ROM Sprites"
    CATEGORY_MESEN = "Mesen2 Captures"
    CATEGORY_LOCAL = "Local Files"

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the sprite asset browser."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING_SMALL)

        # Search bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search sprites...")
        self.search_edit.textChanged.connect(self.filter_items)
        layout.addWidget(self.search_edit)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name"])
        self.tree.header().setVisible(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.setIndentation(20)
        self.tree.setUniformRowHeights(False)  # Allow custom row heights

        # Set custom delegate for thumbnail rendering
        self.delegate = ThumbnailDelegate(self.tree)
        self.tree.setItemDelegate(self.delegate)

        # Connect signals
        self.tree.currentItemChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_activated)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)

        # Style the tree
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {COLORS["input_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
            }}
            QTreeWidget::item {{
                padding: 4px 4px 4px {ThumbnailDelegate.THUMBNAIL_SIZE + 8}px;
                min-height: {ThumbnailDelegate.THUMBNAIL_SIZE + 4}px;
            }}
            QTreeWidget::item:selected {{
                background-color: {COLORS["surface_selected"]};
            }}
            QTreeWidget::item:hover:!selected {{
                background-color: {COLORS["surface_hover"]};
            }}
        """)

        layout.addWidget(self.tree)

        # Create categories
        self._rom_category = self._create_category(self.CATEGORY_ROM)
        self._mesen_category = self._create_category(self.CATEGORY_MESEN)
        self._local_category = self._create_category(self.CATEGORY_LOCAL)

    def _create_category(self, name: str) -> QTreeWidgetItem:
        """
        Create a top-level category item.

        Args:
            name: Category name

        Returns:
            Category tree item
        """
        item = QTreeWidgetItem(self.tree)
        item.setText(0, name)

        # Style as category (bold, not selectable)
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        item.setExpanded(True)

        # Store empty dict to identify as category
        item.setData(0, Qt.ItemDataRole.UserRole, {})

        return item

    def _get_or_create_category(self, name: str) -> QTreeWidgetItem:
        """
        Get existing category or create if it doesn't exist.

        Args:
            name: Category name

        Returns:
            Category tree item
        """
        if name == self.CATEGORY_ROM:
            return self._rom_category
        elif name == self.CATEGORY_MESEN:
            return self._mesen_category
        elif name == self.CATEGORY_LOCAL:
            return self._local_category
        else:
            # Create new category if needed
            return self._create_category(name)

    def _on_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        """
        Handle tree selection changes.

        Args:
            current: Currently selected item
            previous: Previously selected item
        """
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return

        # Skip category items
        if "offset" not in data and "path" not in data:
            return

        # Emit signal with offset and source type
        if "offset" in data:
            offset = data["offset"]
            source_type = data["source_type"]
            self.sprite_selected.emit(offset, source_type)

    def _on_item_activated(self, item: QTreeWidgetItem, column: int) -> None:
        """
        Handle item double-click.

        Args:
            item: Activated item
            column: Column index
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return

        # Skip category items
        if "offset" not in data and "path" not in data:
            return

        # Emit activation signal
        if "offset" in data:
            offset = data["offset"]
            source_type = data["source_type"]
            self.sprite_activated.emit(offset, source_type)

    def _show_context_menu(self, position: QPoint) -> None:
        """
        Show context menu for tree items.

        Args:
            position: Menu position in widget coordinates
        """
        item = self.tree.itemAt(position)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return

        # Skip category items
        if "offset" not in data and "path" not in data:
            return

        # Create context menu
        menu = QMenu(self)

        # Rename action
        rename_action = QAction("Rename", self)
        rename_action.triggered.connect(lambda: self._rename_item(item))
        menu.addAction(rename_action)

        # Delete action
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(lambda: self._delete_item(item))
        menu.addAction(delete_action)

        # Copy offset action (only for ROM/Mesen sprites)
        if "offset" in data:
            menu.addSeparator()
            copy_action = QAction("Copy Offset", self)
            copy_action.triggered.connect(lambda: self._copy_offset(item))
            menu.addAction(copy_action)

        # Show menu
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _rename_item(self, item: QTreeWidgetItem) -> None:
        """
        Start inline editing for item rename.

        Args:
            item: Item to rename
        """
        # Enable editing
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.tree.editItem(item, 0)

        # Connect to capture new name
        def on_item_changed(changed_item: QTreeWidgetItem, column: int) -> None:
            if changed_item == item:
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and "offset" in data:
                    new_name = item.text(0)
                    offset = data["offset"]
                    self.rename_requested.emit(offset, new_name)

                # Disable editing after rename
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tree.itemChanged.disconnect(on_item_changed)

        self.tree.itemChanged.connect(on_item_changed)

    def _delete_item(self, item: QTreeWidgetItem) -> None:
        """
        Request deletion of item.

        Args:
            item: Item to delete
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict):
            if "offset" in data:
                offset = data["offset"]
                source_type = data["source_type"]
                self.delete_requested.emit(offset, source_type)
            elif "path" in data:
                # For local files, use path as identifier
                path = data["path"]
                self.delete_requested.emit(-1, path)

    def _copy_offset(self, item: QTreeWidgetItem) -> None:
        """
        Copy offset to clipboard.

        Args:
            item: Item with offset to copy
        """
        from PySide6.QtWidgets import QApplication

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and "offset" in data:
            offset = data["offset"]
            offset_text = f"0x{offset:06X}"
            QApplication.clipboard().setText(offset_text)

    def add_rom_sprite(self, name: str, offset: int, thumbnail: QPixmap | None = None) -> None:
        """
        Add a ROM sprite to the browser.

        Args:
            name: Sprite name
            offset: ROM offset
            thumbnail: Optional thumbnail pixmap
        """
        item = QTreeWidgetItem(self._rom_category)
        item.setText(0, name)

        # Store data
        data = {
            "name": name,
            "offset": offset,
            "source_type": "rom",
            "thumbnail": thumbnail,
        }
        item.setData(0, Qt.ItemDataRole.UserRole, data)

    def add_mesen_capture(self, name: str, offset: int, thumbnail: QPixmap | None = None) -> None:
        """
        Add a Mesen2 capture to the browser.

        Args:
            name: Sprite name
            offset: ROM offset
            thumbnail: Optional thumbnail pixmap
        """
        item = QTreeWidgetItem(self._mesen_category)
        item.setText(0, name)

        # Store data
        data = {
            "name": name,
            "offset": offset,
            "source_type": "mesen",
            "thumbnail": thumbnail,
        }
        item.setData(0, Qt.ItemDataRole.UserRole, data)

    def add_local_file(self, name: str, path: str, thumbnail: QPixmap | None = None) -> None:
        """
        Add a local file to the browser.

        Args:
            name: File name
            path: File path
            thumbnail: Optional thumbnail pixmap
        """
        item = QTreeWidgetItem(self._local_category)
        item.setText(0, name)

        # Store data
        data = {
            "name": name,
            "path": path,
            "source_type": "local",
            "thumbnail": thumbnail,
        }
        item.setData(0, Qt.ItemDataRole.UserRole, data)

    def clear_category(self, category: str) -> None:
        """
        Clear all items from a category.

        Args:
            category: Category name (use CATEGORY_* constants)
        """
        category_item = self._get_or_create_category(category)
        category_item.takeChildren()

    def clear_all(self) -> None:
        """Clear all items from all categories."""
        self._rom_category.takeChildren()
        self._mesen_category.takeChildren()
        self._local_category.takeChildren()

    def set_thumbnail(self, offset: int, thumbnail: QPixmap) -> None:
        """
        Set or update thumbnail for a sprite.

        Args:
            offset: ROM offset
            thumbnail: Thumbnail pixmap
        """
        # Find item with matching offset
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("offset") == offset:
                data["thumbnail"] = thumbnail
                item.setData(0, Qt.ItemDataRole.UserRole, data)
                # Force repaint
                self.tree.viewport().update()
                return
            iterator += 1

    def filter_items(self, text: str) -> None:
        """
        Filter visible items by search text.

        Args:
            text: Search text (case-insensitive)
        """
        search_text = text.lower()

        # If empty, show all
        if not search_text:
            iterator = QTreeWidgetItemIterator(self.tree)
            while iterator.value():
                item = iterator.value()
                item.setHidden(False)
                iterator += 1
            return

        # Hide non-matching items
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)

            # Always show categories
            if isinstance(data, dict) and not data:  # Empty dict = category
                item.setHidden(False)
                iterator += 1
                continue

            # Check if item matches search
            item_text = item.text(0).lower()
            matches = search_text in item_text

            # Also check offset if present
            if not matches and isinstance(data, dict) and "offset" in data:
                offset = data["offset"]
                offset_text = f"{offset:06x}"
                matches = search_text in offset_text

            item.setHidden(not matches)
            iterator += 1

    def get_item_count(self) -> dict[str, int]:
        """
        Get count of items in each category.

        Returns:
            Dict mapping category name to item count
        """
        return {
            self.CATEGORY_ROM: self._rom_category.childCount(),
            self.CATEGORY_MESEN: self._mesen_category.childCount(),
            self.CATEGORY_LOCAL: self._local_category.childCount(),
        }

    def select_sprite_by_offset(self, offset: int) -> bool:
        """
        Select sprite by ROM offset.

        Args:
            offset: ROM offset to select

        Returns:
            True if sprite was found and selected
        """
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("offset") == offset:
                self.tree.setCurrentItem(item)
                return True
            iterator += 1
        return False
