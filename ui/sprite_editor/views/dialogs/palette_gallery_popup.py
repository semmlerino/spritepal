#!/usr/bin/env python3
"""
Palette gallery popup for quick palette selection.
Shows all 8 sprite palettes (8-15) in a 2x4 grid with color previews.
"""

from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class PaletteGridCell(QFrame):
    """A clickable cell showing a palette's 16 colors in a 4x4 grid."""

    clicked = Signal(int)  # Emits palette index when clicked

    CELL_SIZE = 12  # Size of each color cell
    BORDER_WIDTH = 2

    def __init__(
        self,
        palette_index: int,
        colors: list[tuple[int, int, int]] | None = None,
        is_active: bool = False,
        description: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.palette_index = palette_index
        self.colors = colors if colors else [(64, 64, 64)] * 16
        self.is_active = is_active
        self.description = description

        self._setup_ui()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    def _setup_ui(self) -> None:
        """Set up the cell UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Label with palette number and optional description
        label_text = f"Palette {self.palette_index}"
        if self.is_active:
            label_text = f"\u2605 {label_text}"  # Star for active
        if self.description:
            label_text = f"{label_text}\n{self.description}"

        self._label = QLabel(label_text)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        if self.is_active:
            font = self._label.font()
            font.setBold(True)
            self._label.setFont(font)
        layout.addWidget(self._label)

        # Color grid widget
        self._color_grid = ColorGridWidget(self.colors)
        layout.addWidget(self._color_grid, 1)

        # Set fixed size based on content
        grid_width = 4 * self.CELL_SIZE + 8
        self.setMinimumWidth(grid_width + 16)
        self.setMinimumHeight(grid_width + 50)

    def _update_style(self) -> None:
        """Update visual style based on active state."""
        if self.is_active:
            self.setStyleSheet("""
                PaletteGridCell {
                    background-color: #2D2D2D;
                    border: 2px solid #FFD700;
                    border-radius: 6px;
                }
                PaletteGridCell:hover {
                    background-color: #3D3D3D;
                    border-color: #FFEA00;
                }
            """)
        else:
            self.setStyleSheet("""
                PaletteGridCell {
                    background-color: #2D2D2D;
                    border: 1px solid #555555;
                    border-radius: 6px;
                }
                PaletteGridCell:hover {
                    background-color: #3D3D3D;
                    border-color: #888888;
                }
            """)

    @override
    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        """Handle mouse press to select this palette."""
        if event and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.palette_index)


class ColorGridWidget(QWidget):
    """Widget that paints a 4x4 grid of colors."""

    CELL_SIZE = 12

    def __init__(self, colors: list[tuple[int, int, int]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.colors = colors
        self.setFixedSize(4 * self.CELL_SIZE + 2, 4 * self.CELL_SIZE + 2)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    @override
    def paintEvent(self, event: QPaintEvent | None) -> None:
        """Paint the color grid."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        for i, color in enumerate(self.colors[:16]):
            row = i // 4
            col = i % 4
            x = col * self.CELL_SIZE
            y = row * self.CELL_SIZE

            # Draw checkerboard for transparent color (index 0)
            if i == 0:
                for cy in range(0, self.CELL_SIZE, 4):
                    for cx in range(0, self.CELL_SIZE, 4):
                        is_light = ((cx // 4) + (cy // 4)) % 2 == 0
                        checker_color = QColor(100, 100, 100) if is_light else QColor(70, 70, 70)
                        painter.fillRect(x + cx, y + cy, 4, 4, checker_color)

            # Draw the color
            r, g, b = color
            painter.fillRect(x, y, self.CELL_SIZE, self.CELL_SIZE, QColor(r, g, b))

            # Draw border
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawRect(x, y, self.CELL_SIZE - 1, self.CELL_SIZE - 1)


class PaletteGalleryPopup(QDialog):
    """
    Popup dialog showing all 8 sprite palettes for quick selection.

    Displays palettes 8-15 in a 2x4 grid. Each cell shows:
    - Palette index and optional description
    - 4x4 color grid
    - Star indicator for OAM-active palettes

    Clicking a palette selects it and closes the dialog.
    """

    palette_selected = Signal(int)  # Emits selected palette index

    def __init__(
        self,
        palettes: dict[int, list[tuple[int, int, int]]],
        active_indices: list[int] | None = None,
        descriptions: dict[int, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """
        Initialize the palette gallery popup.

        Args:
            palettes: Dict mapping palette index (8-15) to list of 16 RGB tuples
            active_indices: Optional list of OAM-active palette indices
            descriptions: Optional dict of semantic descriptions per palette index
            parent: Parent widget
        """
        super().__init__(parent)
        self.palettes = palettes
        self.active_indices = set(active_indices) if active_indices else set()
        self.descriptions = descriptions or {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the popup UI."""
        self.setWindowTitle("Select Palette")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Popup)
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
            }
            QLabel {
                color: #CCCCCC;
                font-size: 11px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title
        title = QLabel("Select Sprite Palette")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Grid of palette cells (2 columns x 4 rows)
        grid_container = QWidget()
        grid_layout = QGridLayout(grid_container)
        grid_layout.setSpacing(8)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        # Create cells for palettes 8-15
        for i in range(8):
            palette_index = i + 8
            row = i % 4  # 0-3 for each column
            col = i // 4  # 0-1 for two columns

            colors = self.palettes.get(palette_index)
            is_active = palette_index in self.active_indices
            description = self.descriptions.get(palette_index, "")

            cell = PaletteGridCell(
                palette_index=palette_index,
                colors=colors,
                is_active=is_active,
                description=description,
            )
            cell.clicked.connect(self._on_palette_clicked)
            grid_layout.addWidget(cell, row, col)

        layout.addWidget(grid_container)

        # Hint text
        hint = QLabel("Click a palette to select it")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(hint)

    def _on_palette_clicked(self, palette_index: int) -> None:
        """Handle palette selection."""
        self.palette_selected.emit(palette_index)
        self.accept()
