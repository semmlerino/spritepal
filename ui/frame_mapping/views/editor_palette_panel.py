#!/usr/bin/env python3
"""
Palette panel for the indexed image editor.

Displays a 4x4 grid of 16 palette colors with selection and hover feedback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette

logger = logging.getLogger(__name__)

SWATCH_SIZE = 32
GRID_COLS = 4


class ColorSwatch(QFrame):
    """Individual color swatch with selection indicator."""

    clicked = Signal(int)  # palette index
    hovered = Signal(int)  # palette index

    def __init__(
        self,
        index: int,
        color: tuple[int, int, int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._index = index
        self._color = color
        self._is_selected = False
        self._is_hovered = False

        self.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
        self.setMouseTracking(True)
        self._update_style()

    def set_color(self, color: tuple[int, int, int]) -> None:
        """Set the swatch color."""
        self._color = color
        self._update_style()

    def set_selected(self, selected: bool) -> None:
        """Set selection state."""
        self._is_selected = selected
        self._update_style()

    def _update_style(self) -> None:
        """Update widget style based on state."""
        r, g, b = self._color

        if self._index == 0:
            # Transparent - checkerboard pattern
            style = """
                QFrame {
                    background-color: qlineargradient(spread:repeat, x1:0, y1:0, x2:0.5, y2:0.5,
                        stop:0 #666666, stop:0.5 #666666, stop:0.5 #888888, stop:1 #888888);
                    border: 2px solid %s;
                }
            """
        else:
            style = """
                QFrame {
                    background-color: rgb(%d, %d, %d);
                    border: 2px solid %s;
                }
            """

        border_color = "#FFFF00" if self._is_selected else ("#888" if self._is_hovered else "#444")

        if self._index == 0:
            self.setStyleSheet(style % border_color)
        else:
            self.setStyleSheet(style % (r, g, b, border_color))

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle click to select color."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)
        super().mousePressEvent(event)

    @override
    def enterEvent(self, event: object) -> None:
        """Handle mouse enter."""
        self._is_hovered = True
        self._update_style()
        self.hovered.emit(self._index)
        super().enterEvent(event)  # type: ignore[arg-type]

    @override
    def leaveEvent(self, event: object) -> None:
        """Handle mouse leave."""
        self._is_hovered = False
        self._update_style()
        super().leaveEvent(event)  # type: ignore[arg-type]

    @override
    def paintEvent(self, event: object) -> None:
        """Paint with index number overlay."""
        super().paintEvent(event)  # type: ignore[arg-type]

        painter = QPainter(self)

        # Draw index number in corner
        if self._is_selected:
            painter.setPen(QPen(QColor(0, 0, 0)))
        else:
            painter.setPen(QPen(QColor(255, 255, 255, 180)))

        font = painter.font()
        font.setPixelSize(10)
        font.setBold(self._is_selected)
        painter.setFont(font)

        # Draw index in bottom-right corner
        text = str(self._index)
        rect = self.rect().adjusted(2, 2, -3, -3)
        painter.drawText(rect, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight, text)

        painter.end()


class EditorPalettePanel(QWidget):
    """Panel showing 16-color palette for index selection.

    Signals:
        index_selected: (index) - User selected a palette index
        index_hovered: (index) - User is hovering over a palette index
    """

    index_selected = Signal(int)
    index_hovered = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._swatches: list[ColorSwatch] = []
        self._active_index = 1
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        title = QLabel("Palette")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold; color: #AAA;")
        layout.addWidget(title)

        # Swatch grid
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(2)
        grid.setContentsMargins(0, 0, 0, 0)

        # Create 16 swatches (4x4 grid)
        for i in range(16):
            row = i // GRID_COLS
            col = i % GRID_COLS

            # Default gray colors
            color = (128, 128, 128) if i > 0 else (0, 0, 0)
            swatch = ColorSwatch(i, color, self)
            swatch.clicked.connect(self._on_swatch_clicked)
            swatch.hovered.connect(self._on_swatch_hovered)
            self._swatches.append(swatch)
            grid.addWidget(swatch, row, col)

        layout.addWidget(grid_widget)

        # Active index label
        self._active_label = QLabel("Active: 1")
        self._active_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._active_label.setStyleSheet("color: #888;")
        layout.addWidget(self._active_label)

        # Hover info label
        self._hover_label = QLabel(" ")
        self._hover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hover_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self._hover_label)

        layout.addStretch()

        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

    def set_palette(self, palette: SheetPalette) -> None:
        """Set the palette colors.

        Args:
            palette: SheetPalette with 16 colors
        """
        for i, swatch in enumerate(self._swatches):
            if i < len(palette.colors):
                swatch.set_color(palette.colors[i])

    def set_active_index(self, index: int) -> None:
        """Set the currently active (selected) palette index.

        Args:
            index: Palette index (0-15)
        """
        if not 0 <= index <= 15:
            return

        # Update selection state
        for i, swatch in enumerate(self._swatches):
            swatch.set_selected(i == index)

        self._active_index = index
        self._active_label.setText(f"Active: {index}")

    def get_active_index(self) -> int:
        """Get the currently active palette index."""
        return self._active_index

    def _on_swatch_clicked(self, index: int) -> None:
        """Handle swatch click."""
        self.set_active_index(index)
        self.index_selected.emit(index)

    def _on_swatch_hovered(self, index: int) -> None:
        """Handle swatch hover."""
        # Show RGB info
        if index < len(self._swatches):
            swatch = self._swatches[index]
            r, g, b = swatch._color
            if index == 0:
                self._hover_label.setText("0: Transparent")
            else:
                self._hover_label.setText(f"{index}: RGB({r}, {g}, {b})")
        self.index_hovered.emit(index)

    @override
    def sizeHint(self) -> QSize:
        """Return preferred size."""
        return QSize(SWATCH_SIZE * GRID_COLS + 16, 300)
