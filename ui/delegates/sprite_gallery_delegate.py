"""
Sprite gallery delegate for custom rendering in QListView.
Handles efficient painting of sprites with selection and hover effects.
"""

from __future__ import annotations

from typing import cast, override

from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRect,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ui.models.sprite_gallery_model import SpriteGalleryModel
from utils.logging_config import get_logger

logger = get_logger(__name__)


class SpriteGalleryDelegate(QStyledItemDelegate):
    """Custom delegate for rendering sprites in gallery view."""

    def __init__(self, parent: QObject | None = None):
        """Initialize the sprite gallery delegate."""
        super().__init__(parent)

        # Display settings
        self._thumbnail_size = 768
        self._spacing = 8
        self._label_height = 40

        # Colors for dark theme
        self._bg_color = QColor(43, 43, 43)
        self._bg_hover_color = QColor(51, 51, 51)
        self._bg_selected_color = QColor(58, 58, 74)
        self._border_color = QColor(68, 68, 68)
        self._border_hover_color = QColor(102, 102, 102)
        self._border_selected_color = QColor(74, 158, 255)
        self._text_color = QColor(170, 170, 170)
        self._text_selected_color = QColor(255, 255, 255)

        # Placeholder colors
        self._placeholder_bg = QColor(35, 35, 35)
        self._placeholder_grid = QColor(50, 50, 50)
        self._placeholder_text = QColor(100, 100, 100)

        # Fonts
        self._offset_font = QFont("monospace", 10)
        self._offset_font.setBold(True)
        self._info_font = QFont("Arial", 9)

    @override
    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        """
        Paint the sprite thumbnail.

        Args:
            painter: QPainter to use
            option: Style options
            index: Model index to paint
        """
        if not index.isValid():
            return

        painter.save()

        # Get item data from model
        offset = index.data(SpriteGalleryModel.OffsetRole)
        pixmap = index.data(SpriteGalleryModel.PixmapRole)
        sprite_info = index.data(SpriteGalleryModel.InfoRole)
        is_selected = index.data(SpriteGalleryModel.SelectedRole)

        # Calculate rectangles
        item_rect = option.rect  # type: ignore[attr-defined] - PySide6 QStyleOption stubs incomplete
        thumbnail_rect = QRect(
            item_rect.x() + self._spacing,
            item_rect.y() + self._spacing,
            item_rect.width() - 2 * self._spacing,
            item_rect.height() - self._label_height - 2 * self._spacing,
        )
        label_rect = QRect(
            item_rect.x() + self._spacing,
            thumbnail_rect.bottom() + 4,
            item_rect.width() - 2 * self._spacing,
            self._label_height - 8,
        )

        # Determine colors based on state
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)  # type: ignore[attr-defined] - PySide6 QStyleOption stubs incomplete

        if is_selected:
            bg_color = self._bg_selected_color
            border_color = self._border_selected_color
            text_color = self._text_selected_color
            border_width = 2
        elif is_hovered:
            bg_color = self._bg_hover_color
            border_color = self._border_hover_color
            text_color = self._text_color
            border_width = 1
        else:
            bg_color = self._bg_color
            border_color = self._border_color
            text_color = self._text_color
            border_width = 1

        # Draw background
        painter.fillRect(thumbnail_rect, bg_color)

        # Draw border
        painter.setPen(QPen(border_color, border_width))
        painter.drawRect(thumbnail_rect.adjusted(0, 0, -1, -1))

        # Draw thumbnail or placeholder
        if pixmap and not pixmap.isNull():
            # Scale pixmap to fit while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                thumbnail_rect.size() - QSize(4, 4),  # Leave margin
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # Center the pixmap in the rectangle
            pixmap_x = thumbnail_rect.x() + (thumbnail_rect.width() - scaled_pixmap.width()) // 2
            pixmap_y = thumbnail_rect.y() + (thumbnail_rect.height() - scaled_pixmap.height()) // 2

            painter.drawPixmap(pixmap_x, pixmap_y, scaled_pixmap)
        else:
            # Draw placeholder
            self._draw_placeholder(painter, thumbnail_rect)

        # Draw text labels
        painter.setPen(text_color)

        # Offset text
        offset_text = f"0x{offset:06X}" if offset is not None else "Loading..."
        painter.setFont(self._offset_font)

        # Draw centered offset
        text_rect = QRectF(label_rect)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, offset_text)

        # Draw additional info if available
        if sprite_info:
            info_parts = []

            # Add compression status
            if sprite_info.get("compressed", False):
                info_parts.append("HAL")

            # Add size
            size = sprite_info.get("decompressed_size", sprite_info.get("size", 0))
            if size > 0:
                if size > 1024:
                    info_parts.append(f"{size / 1024:.1f}KB")
                else:
                    info_parts.append(f"{size}B")

            # Add tile count
            tile_count = sprite_info.get("tile_count", 0)
            if tile_count > 0:
                info_parts.append(f"{tile_count} tiles")

            if info_parts:
                info_text = " | ".join(info_parts)
                painter.setFont(self._info_font)

                # Draw below offset with smaller font
                info_rect = QRectF(label_rect.x(), label_rect.y() + 16, label_rect.width(), label_rect.height() - 16)
                painter.setPen(QColor(150, 150, 150))
                painter.drawText(info_rect, Qt.AlignmentFlag.AlignCenter, info_text)

        painter.restore()

    def _draw_placeholder(self, painter: QPainter, rect: QRect) -> None:
        """
        Draw a placeholder for sprites that haven't loaded yet.

        Args:
            painter: QPainter to use
            rect: Rectangle to draw in
        """
        # Fill with placeholder background
        painter.fillRect(rect, self._placeholder_bg)

        # Draw grid pattern
        painter.setPen(QPen(self._placeholder_grid, 1))
        grid_size = 8

        # Vertical lines
        for x in range(rect.x(), rect.right(), grid_size):
            painter.drawLine(x, rect.y(), x, rect.bottom())

        # Horizontal lines
        for y in range(rect.y(), rect.bottom(), grid_size):
            painter.drawLine(rect.x(), y, rect.right(), y)

        # Draw "SPRITE" text in center
        painter.setPen(self._placeholder_text)
        painter.setFont(QFont("Arial", 12))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "SPRITE")

    @override
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        """
        Return size hint for the item.

        Args:
            option: Style options
            index: Model index

        Returns:
            Size hint for the item
        """
        # Use size from model if available
        size_hint = index.data(Qt.ItemDataRole.SizeHintRole)
        if size_hint:
            return size_hint

        # Default size
        return QSize(self._thumbnail_size, self._thumbnail_size + self._label_height)

    def set_thumbnail_size(self, size: int) -> None:
        """
        Set the thumbnail size.

        Args:
            size: New thumbnail size in pixels
        """
        self._thumbnail_size = size

        # Adjust label height based on size
        if size >= 256:
            self._label_height = 40
            self._offset_font.setPointSize(12)
            self._info_font.setPointSize(10)
        else:
            self._label_height = 30
            self._offset_font.setPointSize(10)
            self._info_font.setPointSize(9)

    @override
    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """
        Handle editor events for selection.

        Args:
            event: The event
            model: The model
            option: Style options
            index: Model index

        Returns:
            True if event was handled
        """
        # Handle mouse clicks for selection
        if event.type() == event.Type.MouseButtonPress:
            mouse_event = cast(QMouseEvent, event)
            if mouse_event.button() == Qt.MouseButton.LeftButton:
                # Toggle selection
                current_selection = index.data(SpriteGalleryModel.SelectedRole)
                model.setData(index, not current_selection, SpriteGalleryModel.SelectedRole)
                return True

        return super().editorEvent(event, model, option, index)
