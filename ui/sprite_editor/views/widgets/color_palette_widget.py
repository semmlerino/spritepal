#!/usr/bin/env python3
"""
Color palette widget for the pixel editor.
Displays and manages 16-color palettes for indexed pixel editing.
"""

from typing import override

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QPolygon
from PySide6.QtWidgets import QMenu, QWidget

from .pixel_canvas import PixelCanvas


def _validate_rgb_color(color: object) -> tuple[int, int, int]:
    """Validate and normalize RGB color to tuple of ints."""
    if isinstance(color, list | tuple) and len(color) >= 3:
        return (int(color[0]), int(color[1]), int(color[2]))
    return (0, 0, 0)


def _should_use_white_text(color: tuple[int, int, int]) -> bool:
    """Determine if white text should be used on a given background color."""
    r, g, b = color
    # Calculate perceived brightness using standard formula
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    return brightness < 128


# Default color palette for the editor
DEFAULT_COLOR_PALETTE: list[tuple[int, int, int]] = [
    (0, 0, 0),  # 0: Black (transparent)
    (255, 255, 255),  # 1: White
    (255, 0, 0),  # 2: Red
    (0, 255, 0),  # 3: Green
    (0, 0, 255),  # 4: Blue
    (255, 255, 0),  # 5: Yellow
    (255, 0, 255),  # 6: Magenta
    (0, 255, 255),  # 7: Cyan
    (128, 0, 0),  # 8: Dark Red
    (0, 128, 0),  # 9: Dark Green
    (0, 0, 128),  # 10: Dark Blue
    (128, 128, 0),  # 11: Olive
    (128, 0, 128),  # 12: Purple
    (0, 128, 128),  # 13: Teal
    (192, 192, 192),  # 14: Silver
    (128, 128, 128),  # 15: Gray
]


class ColorPaletteWidget(QWidget):
    """Widget for displaying and selecting colors from the palette."""

    colorSelected = Signal(int)  # Emits the color index

    def __init__(self) -> None:
        super().__init__()
        # Use default palettes from utilities
        self.default_grayscale: list[tuple[int, int, int]] = [(i * 17, i * 17, i * 17) for i in range(16)]
        self.default_colors = DEFAULT_COLOR_PALETTE.copy()

        # Start with grayscale palette by default
        self.colors: list[tuple[int, int, int]] = self.default_grayscale.copy()
        self.selected_index = 1
        self.cell_size = 32
        self.is_grayscale_mode = True

        # External palette tracking
        self.is_external_palette = False
        self.palette_source = "Default Grayscale Palette"

        # Connected canvas for automatic updates
        self._connected_canvas: PixelCanvas | None = None

        self.setFixedSize(4 * self.cell_size + 10, 4 * self.cell_size + 10)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Set initial tooltip
        self._update_tooltip()

    def set_palette(self, colors: list[tuple[int, int, int]], source: str = "External Palette") -> None:
        """Set the palette colors."""
        if len(colors) >= 16:
            # Ensure we have valid tuples
            self.colors = []
            for i in range(16):
                if i < len(colors):
                    c = colors[i]
                    self.colors.append(_validate_rgb_color(c))
                else:
                    self.colors.append((0, 0, 0))

            self.is_external_palette = True
            self.palette_source = source
            self._update_tooltip()
            self.update()
            self.repaint()  # Force immediate repaint

            # Signal that colors have changed
            self.colors_changed()

    def reset_to_default(self) -> None:
        """Reset to default grayscale palette."""
        self.colors = self.default_grayscale.copy()
        self.is_external_palette = False
        self.is_grayscale_mode = True
        self.palette_source = "Default Grayscale Palette"
        self._update_tooltip()
        self.update()

        # Signal that colors have changed
        self.colors_changed()

    def set_color_mode(self, use_colors: bool) -> None:
        """Switch between grayscale and color default palettes."""
        if not self.is_external_palette:
            if use_colors:
                self.colors = self.default_colors.copy()
                self.palette_source = "Default Color Palette"
                self.is_grayscale_mode = False
            else:
                self.colors = self.default_grayscale.copy()
                self.palette_source = "Default Grayscale Palette"
                self.is_grayscale_mode = True
            self._update_tooltip()
            self.update()

    def get_palette(self) -> list[tuple[int, int, int]]:
        """Get the current palette colors."""
        return self.colors.copy()

    @property
    def current_color(self) -> int:
        """Get currently selected color index."""
        return self.selected_index

    @current_color.setter
    def current_color(self, value: int) -> None:
        """Set currently selected color index."""
        if 0 <= value < 16:
            self.selected_index = value
            self.update()

    def colors_changed(self) -> None:
        """Signal that colors have changed - used by canvas for cache invalidation."""
        # Notify connected canvas to update its color cache
        if self._connected_canvas is not None:
            self._connected_canvas._palette_version += 1
            self._connected_canvas.update()

    def connect_canvas(self, canvas: PixelCanvas) -> None:
        """Connect a canvas widget to receive palette updates."""
        self._connected_canvas = canvas

    def _update_tooltip(self) -> None:
        """Update the tooltip to show current palette information."""
        if self.is_external_palette:
            tooltip = f"External Palette: {self.palette_source}\nRight-click to reset to default"
        else:
            tooltip = "Default Editor Palette\n16 colors for sprite editing"
        self.setToolTip(tooltip)

    def _show_context_menu(self, position: QPoint) -> None:
        """Show context menu for palette operations."""
        menu = QMenu(self)

        if self.is_external_palette:
            reset_action = menu.addAction("Reset to Default Palette")
            if reset_action:
                reset_action.triggered.connect(self.reset_to_default)

        info_action = menu.addAction(f"Palette Source: {self.palette_source}")
        if info_action:
            info_action.setEnabled(False)

        if menu.actions():
            menu.exec(self.mapToGlobal(position))

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the palette widget."""
        painter = QPainter(self)

        # Draw external palette indicator border
        if self.is_external_palette:
            painter.setPen(QPen(Qt.GlobalColor.green, 2))
            painter.drawRect(1, 1, self.width() - 2, self.height() - 2)

        for i in range(16):
            row = i // 4
            col = i % 4
            x = col * self.cell_size + 5
            y = row * self.cell_size + 5

            # Draw color swatch - ensure we have valid colors
            if i < len(self.colors):
                rgb = _validate_rgb_color(self.colors[i])
                color = QColor(*rgb)
            else:
                color = QColor(0, 0, 0)

            painter.fillRect(x, y, self.cell_size - 2, self.cell_size - 2, color)

            # Draw external palette indicator on first cell
            if self.is_external_palette and i == 0:
                # Small green indicator triangle in top-left corner
                painter.setBrush(QBrush(Qt.GlobalColor.green))
                painter.setPen(QPen(Qt.GlobalColor.green))
                triangle = QPolygon([QPoint(x, y), QPoint(x + 8, y), QPoint(x, y + 8)])
                painter.drawPolygon(triangle)

            # Draw selection border
            if i == self.selected_index:
                painter.setPen(QPen(Qt.GlobalColor.yellow, 3))
                painter.drawRect(x - 1, y - 1, self.cell_size, self.cell_size)

            # Draw index number
            if i < len(self.colors):
                painter.setPen(Qt.GlobalColor.white if _should_use_white_text(self.colors[i]) else Qt.GlobalColor.black)
            else:
                painter.setPen(Qt.GlobalColor.white)
            painter.drawText(
                QRect(x, y, self.cell_size - 2, self.cell_size - 2),
                Qt.AlignmentFlag.AlignCenter,
                str(i),
            )

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press to select color."""
        if event and event.button() == Qt.MouseButton.LeftButton:
            x = int((event.position().x() - 5) // self.cell_size)
            y = int((event.position().y() - 5) // self.cell_size)
            if 0 <= x < 4 and 0 <= y < 4:
                index = y * 4 + x
                if 0 <= index < 16:
                    self.selected_index = index
                    self.colorSelected.emit(index)
                    self.update()
                    # Notify any connected canvas that palette changed
                    self.colors_changed()
