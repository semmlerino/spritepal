#!/usr/bin/env python3
"""
Custom delegate for rendering palette color swatches in QComboBox items.
Shows 4 color swatches alongside the palette name, with optional active indicator.
"""

from typing import override

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

# Data roles for palette metadata
PALETTE_COLORS_ROLE = Qt.ItemDataRole.UserRole
PALETTE_IS_ACTIVE_ROLE = Qt.ItemDataRole.UserRole + 1

# Layout constants
SWATCH_SIZE = 12  # Size of each color swatch in pixels
SWATCH_SPACING = 2  # Space between swatches
SWATCH_COUNT = 4  # Number of colors to show
STAR_WIDTH = 16  # Space for star indicator
ITEM_HEIGHT = 24  # Total height of dropdown item
TEXT_SWATCH_MARGIN = 8  # Space between text and swatches


class PalettePreviewDelegate(QStyledItemDelegate):
    """
    Custom delegate for QComboBox items that renders palette color swatches.

    Each item displays:
    - Optional star icon (star) for OAM-active palettes
    - Text label (e.g., "ROM Palette 8" or "ROM Palette 8 - Kirby (pink)")
    - 4 color swatches from the palette

    Item data roles:
    - Qt.DisplayRole: Text label
    - PALETTE_COLORS_ROLE: list of 4 RGB tuples [(r,g,b), ...]
    - PALETTE_IS_ACTIVE_ROLE: bool indicating if palette is OAM-active
    """

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint the dropdown item with text and color swatches."""
        painter.save()

        # Get item data
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        colors = index.data(PALETTE_COLORS_ROLE)  # list of RGB tuples or None
        is_active = index.data(PALETTE_IS_ACTIVE_ROLE) or False

        # Access QStyleOptionViewItem fields - these are available at runtime
        state = option.state  # type: ignore[union-attr]
        rect: QRect = option.rect  # type: ignore[union-attr]
        palette = option.palette  # type: ignore[union-attr]

        # Draw selection/hover background
        if state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, palette.highlight())
            text_color = palette.highlightedText().color()
        elif state & QStyle.StateFlag.State_MouseOver:
            # Lighter highlight for hover
            hover_color = palette.highlight().color()
            hover_color.setAlpha(80)
            painter.fillRect(rect, hover_color)
            text_color = palette.text().color()
        else:
            text_color = palette.text().color()

        # Calculate layout
        x = rect.left() + 4
        y = rect.top()
        height = rect.height()

        # Draw star for active palettes
        if is_active:
            star_rect = QRect(x, y, STAR_WIDTH, height)
            painter.setPen(QPen(QColor(255, 200, 50)))  # Gold color
            font = painter.font()
            painter.setFont(font)
            painter.drawText(star_rect, Qt.AlignmentFlag.AlignVCenter, "\u2605")
            x += STAR_WIDTH

        # Draw text (potentially bold for active)
        if is_active:
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)

        painter.setPen(QPen(text_color))
        text_rect = QRect(x, y, rect.width() - x - self._swatch_block_width() - 8, height)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        # Draw color swatches on the right
        if colors:
            self._paint_swatches(painter, rect, colors)

        painter.restore()

    def _swatch_block_width(self) -> int:
        """Calculate total width of the swatch block."""
        return SWATCH_COUNT * SWATCH_SIZE + (SWATCH_COUNT - 1) * SWATCH_SPACING

    def _paint_swatches(
        self,
        painter: QPainter,
        rect: QRect,
        colors: list[tuple[int, int, int]],
    ) -> None:
        """Paint 4 color swatches on the right side of the item."""
        swatch_block_width = self._swatch_block_width()
        x = rect.right() - swatch_block_width - 6
        y_center = rect.center().y()
        y = y_center - SWATCH_SIZE // 2

        for i, color in enumerate(colors[:SWATCH_COUNT]):
            # Validate color format (can be any type from item data)
            if not hasattr(color, "__len__") or len(color) < 3:
                continue

            r, g, b = int(color[0]), int(color[1]), int(color[2])
            swatch_x = x + i * (SWATCH_SIZE + SWATCH_SPACING)

            # Draw swatch background (for transparency indicator on index 0)
            if i == 0:
                # Checkerboard for transparent color
                checker_size = 4
                for cy in range(0, SWATCH_SIZE, checker_size):
                    for cx in range(0, SWATCH_SIZE, checker_size):
                        is_light = ((cx // checker_size) + (cy // checker_size)) % 2 == 0
                        checker_color = QColor(100, 100, 100) if is_light else QColor(80, 80, 80)
                        painter.fillRect(swatch_x + cx, y + cy, checker_size, checker_size, checker_color)

            # Draw the color
            painter.fillRect(swatch_x, y, SWATCH_SIZE, SWATCH_SIZE, QColor(r, g, b))

            # Draw border
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.drawRect(swatch_x, y, SWATCH_SIZE - 1, SWATCH_SIZE - 1)

    @override
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        """Return the size hint for items."""
        # Get default width from base class
        base_size = super().sizeHint(option, index)

        # Calculate minimum width needed
        min_width = STAR_WIDTH + 150 + TEXT_SWATCH_MARGIN + self._swatch_block_width() + 16

        return QSize(max(base_size.width(), min_width), ITEM_HEIGHT)
