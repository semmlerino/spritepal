"""
Palette preview widget for SpritePal
"""

from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QWidget

from ui.common.spacing_constants import BORDER_THIN, PALETTE_PREVIEW_SIZE
from ui.styles.theme import COLORS


class PaletteColorWidget(QWidget):
    """Widget for displaying a single palette color"""

    clicked = Signal(int)  # color index

    def __init__(self, index: int, color: tuple[int, int, int] = (0, 0, 0)) -> None:
        super().__init__()
        self.index = index
        self.color = QColor(*color)
        self.setFixedSize(QSize(PALETTE_PREVIEW_SIZE, PALETTE_PREVIEW_SIZE))
        self.setToolTip(f"Color {index}: RGB({color[0]}, {color[1]}, {color[2]})")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @override
    def paintEvent(self, a0: QPaintEvent | None) -> None:
        """Paint the color swatch"""
        # Guard against paint events during widget destruction
        # shiboken6.isValid() checks if the underlying C++ object still exists
        from PySide6.QtWidgets import QApplication

        try:
            import shiboken6
            if not shiboken6.isValid(self):
                return
        except ImportError:
            pass  # Continue without check if shiboken6 not available

        if QApplication.instance() is None:
            return

        try:
            # Check if the widget is still valid
            _ = self.isVisible()

            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Draw background for transparency
            if self.index == 0:
                # Draw checkerboard for transparent color
                checker_size = 8
                for y in range(0, self.height(), checker_size):
                    for x in range(0, self.width(), checker_size):
                        if (x // checker_size + y // checker_size) % 2:
                            painter.fillRect(
                                x, y, checker_size, checker_size, QColor(80, 80, 80)
                            )
                        else:
                            painter.fillRect(
                                x, y, checker_size, checker_size, QColor(100, 100, 100)
                            )

            # Draw color
            painter.fillRect(self.rect(), self.color)

            # Draw border
            painter.setPen(QPen(QColor(100, 100, 100), BORDER_THIN))
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

            # Draw index number
            painter.setPen(
                QPen(
                    (
                        Qt.GlobalColor.white
                        if self.color.lightness() < 128
                        else Qt.GlobalColor.black
                    ),
                    1,
                )
            )
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self.index))
        except RuntimeError:
            # Widget's C++ object has been deleted
            pass

    @override
    def mousePressEvent(self, a0: QMouseEvent | None):
        """Handle mouse press"""
        if a0 and a0.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)

    def set_color(self, color: tuple[int, int, int]):
        """Set the color"""
        self.color = QColor(*color)
        self.setToolTip(f"Color {self.index}: RGB({color[0]}, {color[1]}, {color[2]})")
        self.update()

class PaletteWidget(QFrame):
    """Widget for displaying a single palette"""

    def __init__(self, palette_index: int, name: str = "", parent: Any | None = None) -> None:
        super().__init__(parent)
        self.palette_index = palette_index
        self.name = name
        self.colors = []
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"""
            PaletteWidget {{
                background-color: {COLORS["input_background"]};
                border: {BORDER_THIN}px solid {COLORS["border"]};
                border-radius: 4px;
                padding: 4px;
            }}
        """
        )

        # Layout
        layout = QGridLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        # Palette label
        self.label = QLabel(f"{palette_index}", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.label:
            self.label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_secondary']};")
        layout.addWidget(self.label, 0, 0, 1, 4)

        # Color swatches
        self.color_widgets = []
        for i in range(16):
            color_widget = PaletteColorWidget(i)
            row = (i // 4) + 1
            col = i % 4
            layout.addWidget(color_widget, row, col)
            self.color_widgets.append(color_widget)

        self.setLayout(layout)

    def set_palette(self, colors: list[tuple[int, int, int]]) -> None:
        """Set the palette colors"""
        self.colors = colors
        for i, color in enumerate(colors[:16]):
            self.color_widgets[i].set_color(color)

    def clear(self):
        """Clear the palette"""
        self.colors = []
        for widget in self.color_widgets:
            widget.set_color((0, 0, 0))

    def set_name(self, name: str):
        """Set the palette name"""
        self.name = name
        if name:
            if self.label:
                self.label.setText(f"{self.palette_index}: {name}")
        elif self.label:
            self.label.setText(f"{self.palette_index}")

class PalettePreviewWidget(QWidget):
    """Widget for previewing multiple palettes"""

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI"""
        layout = QGridLayout(self)
        layout.setSpacing(8)

        # Create palette widgets for palettes 8-15
        self.palette_widgets = {}
        for i in range(8):
            palette_index = i + 8
            palette_widget = PaletteWidget(palette_index, "", self)

            row = i // 4
            col = i % 4
            layout.addWidget(palette_widget, row, col)

            self.palette_widgets[palette_index] = palette_widget

        self.setLayout(layout)

    def set_palette(self, palette_index: int, colors: list[tuple[int, int, int]], name: str = "") -> None:
        """Set a specific palette"""
        if palette_index in self.palette_widgets:
            self.palette_widgets[palette_index].set_palette(colors)
            if name:
                self.palette_widgets[palette_index].set_name(name)

    def set_all_palettes(self, palettes_dict: dict[int, list[tuple[int, int, int]]]) -> None:
        """Set all palettes from a dictionary"""
        for palette_index, colors in palettes_dict.items():
            self.set_palette(palette_index, colors)

    def clear(self):
        """Clear all palettes"""
        for widget in self.palette_widgets.values():
            widget.clear()

    def highlight_palette(self, palette_index: int, highlight: bool = True) -> None:
        """Highlight a specific palette"""
        if palette_index in self.palette_widgets:
            widget = self.palette_widgets[palette_index]
            if highlight:
                widget.setStyleSheet(
                    f"""
                    PaletteWidget {{
                        background-color: {COLORS["input_background"]};
                        border: 2px solid {COLORS["border_focus"]};
                        border-radius: 4px;
                        padding: 4px;
                    }}
                """
                )
            else:
                widget.setStyleSheet(
                    f"""
                    PaletteWidget {{
                        background-color: {COLORS["input_background"]};
                        border: {BORDER_THIN}px solid {COLORS["border"]};
                        border-radius: 4px;
                        padding: 4px;
                    }}
                """
                )

    def highlight_active_palettes(self, active_indices: list[int]) -> None:
        """Highlight multiple active palettes"""
        # Clear all highlights first
        for idx in range(8, 16):
            self.highlight_palette(idx, False)

        # Highlight active ones
        for idx in active_indices:
            self.highlight_palette(idx, True)
