"""
Sprite gallery model for efficient handling of large sprite collections.
Implements virtual scrolling through QAbstractListModel.
"""
from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPersistentModelIndex,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QPixmap

from utils.logging_config import get_logger

logger = get_logger(__name__)

class SpriteGalleryModel(QAbstractListModel):
    """Model for sprite gallery using virtual item view."""

    # Custom roles for sprite data
    OffsetRole = Qt.ItemDataRole.UserRole + 1
    PixmapRole = Qt.ItemDataRole.UserRole + 2
    InfoRole = Qt.ItemDataRole.UserRole + 3
    SelectedRole = Qt.ItemDataRole.UserRole + 4
    CompressedRole = Qt.ItemDataRole.UserRole + 5
    SizeRole = Qt.ItemDataRole.UserRole + 6
    TileCountRole = Qt.ItemDataRole.UserRole + 7

    # Signals
    thumbnail_needed = Signal(int, int)  # offset, priority
    selection_changed = Signal(list)  # list of selected offsets

    def __init__(self, parent: object | None = None):
        """Initialize the sprite gallery model."""
        super().__init__(parent)  # type: ignore[arg-type]

        # Sprite data storage
        self._sprites: list[dict[str, Any]] = []  # pyright: ignore[reportExplicitAny] - sprite data
        self._filtered_sprites: list[dict[str, Any]] = []  # pyright: ignore[reportExplicitAny] - sprite data
        self._thumbnails: dict[int, QPixmap] = {}  # offset -> pixmap cache
        self._selected_offsets: set[int] = set()

        # Display settings
        self._thumbnail_size = 256
        self._columns = 4

        # Filter settings
        self._filter_text = ""
        self._filter_compressed_only = False
        self._use_filtering = False

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        """Return number of sprites (for virtual view)."""
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        sprites = self._filtered_sprites if self._use_filtering else self._sprites
        return len(sprites)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        """Return number of columns for grid layout."""
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        return self._columns

    @override
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        """Return data for the given index and role."""
        if not index.isValid():
            return None

        row = index.row()
        sprites = self._filtered_sprites if self._use_filtering else self._sprites

        if row < 0 or row >= len(sprites):
            return None

        sprite = sprites[row]
        offset = self._get_offset(sprite)

        if role == Qt.ItemDataRole.DisplayRole:
            # Return offset text for display
            return f"0x{offset:06X}"

        if role == self.OffsetRole:
            return offset

        if role == self.PixmapRole:
            # Return cached thumbnail or None if not loaded
            if offset in self._thumbnails:
                return self._thumbnails[offset]
            # Request thumbnail generation with priority based on position
            # Lower row = higher priority (visible items first)
            priority = row
            self.thumbnail_needed.emit(offset, priority)
            return None

        if role == self.InfoRole:
            return sprite

        if role == self.SelectedRole:
            return offset in self._selected_offsets

        if role == self.CompressedRole:
            return sprite.get('compressed', False)

        if role == self.SizeRole:
            return sprite.get('decompressed_size', sprite.get('size', 0))

        if role == self.TileCountRole:
            return sprite.get('tile_count', 0)

        if role == Qt.ItemDataRole.SizeHintRole:
            # Return size hint for item
            return QSize(self._thumbnail_size, self._thumbnail_size + 40)

        return None

    @override
    def setData(self, index: QModelIndex | QPersistentModelIndex, value: object, role: int = Qt.ItemDataRole.EditRole) -> bool:
        """Set data for the given index and role."""
        if not index.isValid():
            return False

        row = index.row()
        sprites = self._filtered_sprites if self._use_filtering else self._sprites

        if row < 0 or row >= len(sprites):
            return False

        sprite = sprites[row]
        offset = self._get_offset(sprite)

        if role == self.SelectedRole:
            # Update selection state
            if value:
                self._selected_offsets.add(offset)
            else:
                self._selected_offsets.discard(offset)

            self.dataChanged.emit(index, index, [self.SelectedRole])
            self.selection_changed.emit(list(self._selected_offsets))
            return True

        return False

    @override
    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        """Return item flags for the given index."""
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_sprites(self, sprites: list[dict[str, Any]]):  # pyright: ignore[reportExplicitAny] - sprite data
        """
        Set the sprite data for the model.

        Args:
            sprites: List of sprite dictionaries
        """
        self.beginResetModel()

        self._sprites = sprites
        self._filtered_sprites = sprites.copy()
        if self._thumbnails:
            self._thumbnails.clear()
        if self._selected_offsets:
            self._selected_offsets.clear()
        self._use_filtering = False

        self.endResetModel()

        logger.info(f"Model populated with {len(sprites)} sprites")

    def set_thumbnail(self, offset: int, pixmap: QPixmap):
        """
        Set thumbnail for a sprite.

        Args:
            offset: Sprite offset
            pixmap: Thumbnail pixmap
        """
        self._thumbnails[offset] = pixmap

        # Find the sprite row and emit dataChanged
        sprites = self._filtered_sprites if self._use_filtering else self._sprites
        for row, sprite in enumerate(sprites):
            if self._get_offset(sprite) == offset:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, [self.PixmapRole])
                break

    def apply_filter(self, text: str = "", compressed_only: bool = False):
        """
        Apply filtering to the sprite list.

        Args:
            text: Filter text (searches offset)
            compressed_only: Only show compressed sprites
        """
        self._filter_text = text.lower()
        self._filter_compressed_only = compressed_only

        self.beginResetModel()

        if not text and not compressed_only:
            # No filtering
            self._filtered_sprites = self._sprites.copy()
            self._use_filtering = False
        else:
            # Apply filters
            self._filtered_sprites = []
            for sprite in self._sprites:
                # Check text filter
                if text:
                    offset = self._get_offset(sprite)
                    offset_str = f"0x{offset:06x}".lower()
                    if text not in offset_str:
                        continue

                # Check compression filter
                if compressed_only and not sprite.get('compressed', False):
                    continue

                self._filtered_sprites.append(sprite)

            self._use_filtering = True

        self.endResetModel()

        logger.debug(f"Filter applied: {len(self._filtered_sprites)}/{len(self._sprites)} sprites shown")

    def sort_sprites(self, sort_key: str):
        """
        Sort sprites by the given key.

        Args:
            sort_key: Sort key ("Offset", "Size", "Tiles")
        """
        self.beginResetModel()

        if sort_key == "Offset":
            self._sprites.sort(key=lambda x: self._get_offset(x))
        elif sort_key == "Size":
            self._sprites.sort(key=lambda x: x.get('decompressed_size', x.get('size', 0)), reverse=True)
        elif sort_key == "Tiles":
            self._sprites.sort(key=lambda x: x.get('tile_count', 0), reverse=True)

        # Re-apply filter after sorting
        if self._use_filtering:
            self.apply_filter(self._filter_text, self._filter_compressed_only)
        else:
            self._filtered_sprites = self._sprites.copy()

        self.endResetModel()

    def get_sprite_at_row(self, row: int) -> dict[str, Any] | None:  # pyright: ignore[reportExplicitAny] - sprite data
        """Get sprite data at the given row."""
        sprites = self._filtered_sprites if self._use_filtering else self._sprites
        if 0 <= row < len(sprites):
            return sprites[row]
        return None

    def get_selected_sprites(self) -> list[dict[str, Any]]:  # pyright: ignore[reportExplicitAny] - sprite data
        """Get all selected sprites."""
        selected = []
        for sprite in self._sprites:
            if self._get_offset(sprite) in self._selected_offsets:
                selected.append(sprite)
        return selected

    def select_all(self):
        """Select all visible sprites."""
        sprites = self._filtered_sprites if self._use_filtering else self._sprites

        if self._selected_offsets:
            self._selected_offsets.clear()
        for sprite in sprites:
            self._selected_offsets.add(self._get_offset(sprite))

        # Emit dataChanged for all items
        if sprites:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(sprites) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [self.SelectedRole])

        self.selection_changed.emit(list(self._selected_offsets))

    def clear_selection(self):
        """Clear all selections."""
        had_selection = bool(self._selected_offsets)
        if self._selected_offsets:
            self._selected_offsets.clear()

        if had_selection:
            sprites = self._filtered_sprites if self._use_filtering else self._sprites
            if sprites:
                top_left = self.index(0, 0)
                bottom_right = self.index(len(sprites) - 1, 0)
                self.dataChanged.emit(top_left, bottom_right, [self.SelectedRole])

        self.selection_changed.emit([])

    def toggle_selection(self, offset: int):
        """Toggle selection for a sprite."""
        if offset in self._selected_offsets:
            self._selected_offsets.discard(offset)
        else:
            self._selected_offsets.add(offset)

        # Find and update the sprite
        sprites = self._filtered_sprites if self._use_filtering else self._sprites
        for row, sprite in enumerate(sprites):
            if self._get_offset(sprite) == offset:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, [self.SelectedRole])
                break

        self.selection_changed.emit(list(self._selected_offsets))

    def set_thumbnail_size(self, size: int):
        """Set the thumbnail size."""
        self._thumbnail_size = size
        # Emit size hint changed for all items
        if self._sprites:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, 0),
                [Qt.ItemDataRole.SizeHintRole]
            )

    def set_columns(self, columns: int):
        """Set the number of columns for grid layout."""
        self._columns = max(1, columns)

    def get_visible_range(self, first_visible: int, last_visible: int) -> list[int]:
        """
        Get offsets of sprites in the visible range.

        Args:
            first_visible: First visible row
            last_visible: Last visible row

        Returns:
            List of offsets that need thumbnails
        """
        offsets = []
        sprites = self._filtered_sprites if self._use_filtering else self._sprites

        for row in range(max(0, first_visible), min(len(sprites), last_visible + 1)):
            sprite = sprites[row]
            offset = self._get_offset(sprite)

            # Only request if not already cached
            if offset not in self._thumbnails:
                offsets.append(offset)

        return offsets

    def clear_thumbnail_cache(self):
        """Clear the thumbnail cache."""
        if self._thumbnails:
            self._thumbnails.clear()

        # Notify view that all pixmaps need refresh
        if self._sprites:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, 0),
                [self.PixmapRole]
            )

    @staticmethod
    def _get_offset(sprite: dict[str, Any]) -> int:  # pyright: ignore[reportExplicitAny] - sprite data
        """Extract offset from sprite data."""
        offset = sprite.get('offset', 0)
        if isinstance(offset, str):
            return int(offset, 16) if offset.startswith('0x') else int(offset)
        return offset

    def get_sprite_count_info(self) -> tuple[int, int, int]:
        """
        Get sprite count information.

        Returns:
            Tuple of (visible_count, total_count, selected_count)
        """
        visible_count = len(self._filtered_sprites) if self._use_filtering else len(self._sprites)
        total_count = len(self._sprites)
        selected_count = len(self._selected_offsets)

        return visible_count, total_count, selected_count

    def get_sprite_pixmap(self, offset: int) -> QPixmap | None:
        """
        Get the cached pixmap for a sprite at the given offset.

        Args:
            offset: Sprite offset

        Returns:
            QPixmap if cached, None otherwise
        """
        return self._thumbnails.get(offset)
