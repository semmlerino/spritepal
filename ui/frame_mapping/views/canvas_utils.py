"""Shared canvas utilities for frame mapping views."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter


def draw_checkerboard(painter: QPainter, width: int, height: int, cell_size: int = 16) -> None:
    """Draw checkerboard background pattern for transparency visualization.

    Args:
        painter: QPainter to draw with
        width: Canvas width
        height: Canvas height
        cell_size: Size of each checkerboard cell (default 16)
    """
    colors = [Qt.GlobalColor.darkGray, Qt.GlobalColor.gray]

    for y in range(0, height, cell_size):
        for x in range(0, width, cell_size):
            color_index = ((x // cell_size) + (y // cell_size)) % 2
            painter.fillRect(x, y, cell_size, cell_size, colors[color_index])
