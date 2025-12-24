"""
Palette preview widget for SpritePal

Features collapsible palette rows - expanded palette shows full 4x4 grid,
collapsed palettes show compact single-row previews.
"""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.common.spacing_constants import (
    BORDER_THIN,
    COMPACT_ROW_MARGIN,
    PALETTE_LABEL_HEIGHT,
    PALETTE_PREVIEW_SIZE,
    SPACING_TINY,
)
from ui.styles.theme import COLORS

# Constants for collapsed view
COLLAPSED_SWATCH_SIZE = 12  # Smaller swatches for collapsed rows
EXPANDED_SWATCH_SIZE = PALETTE_PREVIEW_SIZE  # Full size for expanded palette


def _update_color_widgets(
    color_widgets: list[PaletteColorWidget], colors: list[tuple[int, int, int]]
) -> None:
    """Update color widgets with the given colors.

    Args:
        color_widgets: List of PaletteColorWidget to update
        colors: List of RGB tuples (up to 16 colors)
    """
    for i, color in enumerate(colors[:16]):
        color_widgets[i].set_color(color)


class PaletteColorWidget(QWidget):
    """Widget for displaying a single palette color"""

    clicked = Signal(int)  # color index

    # Default placeholder color (dark gray instead of black for uninitialized state)
    DEFAULT_COLOR = (64, 64, 64)

    def __init__(self, index: int, color: tuple[int, int, int] = DEFAULT_COLOR, size: int = PALETTE_PREVIEW_SIZE) -> None:
        super().__init__()
        self.index = index
        self.color = QColor(*color)
        self._size = size
        self.setFixedSize(QSize(size, size))
        self.setToolTip(f"Color {index}: RGB({color[0]}, {color[1]}, {color[2]})")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Ensure proper repaint behavior - prevents ghosting artifacts
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

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
                checker_size = max(4, self._size // 4)
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

            # Draw index number only for larger swatches
            if self._size >= 20:
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

    def set_color(self, color: tuple[int, int, int] | None):
        """Set the color with validation"""
        # Validate color - use default if invalid
        if color is None or len(color) != 3 or not all(0 <= c <= 255 for c in color):
            color = self.DEFAULT_COLOR
        self.color = QColor(*color)
        self.setToolTip(f"Color {self.index}: RGB({color[0]}, {color[1]}, {color[2]})")
        self.update()


class PaletteWidget(QFrame):
    """Widget for displaying a single palette (expanded view)"""

    def __init__(self, palette_index: int, name: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette_index = palette_index
        self.name = name
        self.colors: list[tuple[int, int, int]] = []
        # Note: Don't use setFrameStyle - it conflicts with stylesheet borders
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

        # Layout - no spacing for seamless color grid
        layout = QGridLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(SPACING_TINY, SPACING_TINY, SPACING_TINY, SPACING_TINY)

        # Palette label - fixed height prevents overlap with color grid
        self.label = QLabel(f"{palette_index}", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFixedHeight(PALETTE_LABEL_HEIGHT)
        self.label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_secondary']};")
        layout.addWidget(self.label, 0, 0, 1, 4)

        # Color swatches
        self.color_widgets: list[PaletteColorWidget] = []
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
        _update_color_widgets(self.color_widgets, colors)

    def clear(self):
        """Clear the palette to default placeholder color"""
        self.colors = []
        for widget in self.color_widgets:
            widget.set_color(PaletteColorWidget.DEFAULT_COLOR)

    def set_name(self, name: str):
        """Set the palette name"""
        self.name = name
        if name:
            if self.label:
                self.label.setText(f"{self.palette_index}: {name}")
        elif self.label:
            self.label.setText(f"{self.palette_index}")


class CollapsedPaletteRow(QFrame):
    """Compact single-row palette display for collapsed state"""

    clicked = Signal(int)  # palette_index when row is clicked

    def __init__(self, palette_index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette_index = palette_index
        self.colors: list[tuple[int, int, int]] = []
        # Note: Don't use setFrameStyle - it conflicts with stylesheet borders
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style(highlighted=False)

        # Horizontal layout for collapsed view - no spacing for seamless swatches
        layout = QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(SPACING_TINY, COMPACT_ROW_MARGIN, SPACING_TINY, COMPACT_ROW_MARGIN)

        # Palette number label
        self.label = QLabel(f"{palette_index}:")
        self.label.setFixedWidth(24)
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_muted']}; font-size: 11px;")
        layout.addWidget(self.label)

        # Mini color swatches in a row
        self.color_widgets: list[PaletteColorWidget] = []
        for i in range(16):
            color_widget = PaletteColorWidget(i, size=COLLAPSED_SWATCH_SIZE)
            layout.addWidget(color_widget)
            self.color_widgets.append(color_widget)

        layout.addStretch()
        self.setLayout(layout)

    def _update_style(self, highlighted: bool = False) -> None:
        """Update the visual style based on highlight state"""
        border_color = COLORS["border_focus"] if highlighted else COLORS["border"]
        border_width = 2 if highlighted else BORDER_THIN
        self.setStyleSheet(
            f"""
            CollapsedPaletteRow {{
                background-color: {COLORS["input_background"]};
                border: {border_width}px solid {border_color};
                border-radius: 3px;
            }}
            CollapsedPaletteRow:hover {{
                background-color: {COLORS["panel_background"]};
                border-color: {COLORS["border_focus"]};
            }}
        """
        )
        self.update()  # Force repaint after style change

    def set_palette(self, colors: list[tuple[int, int, int]]) -> None:
        """Set the palette colors"""
        self.colors = colors
        _update_color_widgets(self.color_widgets, colors)

    def clear(self):
        """Clear the palette to default placeholder color"""
        self.colors = []
        for widget in self.color_widgets:
            widget.set_color(PaletteColorWidget.DEFAULT_COLOR)

    def set_highlighted(self, highlighted: bool) -> None:
        """Set highlight state"""
        self._update_style(highlighted)

    @override
    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        """Handle click to expand this palette"""
        if event and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.palette_index)
        if event is not None:
            super().mousePressEvent(event)


class PalettePreviewWidget(QWidget):
    """Widget for previewing multiple palettes with collapsible rows

    Features:
    - One palette expanded at a time (full 4x4 grid)
    - Other palettes shown as collapsed single-row thumbnails
    - Click collapsed row to expand it
    """

    palette_expanded = Signal(int)  # Emitted when a palette is expanded

    def __init__(self):
        super().__init__()
        self._expanded_index = 8  # Default to first palette (index 8)
        self._active_indices: list[int] = []  # Palettes marked as active
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI with expandable layout"""
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setSpacing(SPACING_TINY)
        self._main_layout.setContentsMargins(0, 0, 0, 0)

        # Expanded palette widget (shows full grid)
        self._expanded_widget = PaletteWidget(self._expanded_index, "", self)
        self._main_layout.addWidget(self._expanded_widget)

        # Container for collapsed palette rows
        self._collapsed_container = QWidget(self)
        self._collapsed_layout = QVBoxLayout(self._collapsed_container)
        self._collapsed_layout.setSpacing(COMPACT_ROW_MARGIN)
        self._collapsed_layout.setContentsMargins(0, 0, 0, 0)

        # Create collapsed rows for all palettes
        self._collapsed_rows: dict[int, CollapsedPaletteRow] = {}
        self._expanded_widgets: dict[int, PaletteWidget] = {}

        for i in range(8):
            palette_index = i + 8

            # Create expanded widget (only shown when this palette is expanded)
            expanded = PaletteWidget(palette_index, "", self)
            expanded.setVisible(palette_index == self._expanded_index)
            self._expanded_widgets[palette_index] = expanded

            # Create collapsed row
            collapsed = CollapsedPaletteRow(palette_index, self)
            collapsed.setVisible(palette_index != self._expanded_index)
            collapsed.clicked.connect(self._on_collapsed_clicked)
            self._collapsed_rows[palette_index] = collapsed
            self._collapsed_layout.addWidget(collapsed)

        self._main_layout.addWidget(self._collapsed_container)
        self.setLayout(self._main_layout)

        # Initialize expanded view
        self._update_expanded_view()

    def _on_collapsed_clicked(self, palette_index: int) -> None:
        """Handle click on a collapsed palette row"""
        if palette_index != self._expanded_index:
            self._set_expanded(palette_index)

    def _set_expanded(self, palette_index: int) -> None:
        """Set which palette is expanded"""
        if palette_index == self._expanded_index:
            return

        old_index = self._expanded_index
        self._expanded_index = palette_index

        # Update visibility of collapsed rows
        if old_index in self._collapsed_rows:
            self._collapsed_rows[old_index].setVisible(True)
        if palette_index in self._collapsed_rows:
            self._collapsed_rows[palette_index].setVisible(False)

        self._update_expanded_view()
        self.palette_expanded.emit(palette_index)

    def _update_expanded_view(self) -> None:
        """Update the expanded widget to show current expanded palette"""
        # Copy data from the stored expanded widget to the displayed one
        if self._expanded_index in self._expanded_widgets:
            source = self._expanded_widgets[self._expanded_index]
            self._expanded_widget.palette_index = self._expanded_index
            self._expanded_widget.set_name(source.name)
            if source.colors:
                self._expanded_widget.set_palette(source.colors)
            # Update label
            if self._expanded_widget.label:
                self._expanded_widget.label.setText(
                    f"Palette {self._expanded_index}" +
                    (f": {source.name}" if source.name else "")
                )

        # Update highlight on expanded widget
        is_active = self._expanded_index in self._active_indices
        self._update_expanded_highlight(is_active)

    def _update_expanded_highlight(self, is_active: bool) -> None:
        """Update the expanded widget's highlight state"""
        if is_active:
            self._expanded_widget.setStyleSheet(
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
            self._expanded_widget.setStyleSheet(
                f"""
                PaletteWidget {{
                    background-color: {COLORS["input_background"]};
                    border: {BORDER_THIN}px solid {COLORS["border"]};
                    border-radius: 4px;
                    padding: 4px;
                }}
            """
            )
        self._expanded_widget.update()  # Force repaint after style change

    def set_palette(self, palette_index: int, colors: list[tuple[int, int, int]], name: str = "") -> None:
        """Set a specific palette's colors"""
        # Update the stored expanded widget
        if palette_index in self._expanded_widgets:
            self._expanded_widgets[palette_index].set_palette(colors)
            if name:
                self._expanded_widgets[palette_index].set_name(name)

        # Update collapsed row
        if palette_index in self._collapsed_rows:
            self._collapsed_rows[palette_index].set_palette(colors)

        # If this is the currently expanded palette, update the display
        if palette_index == self._expanded_index:
            self._update_expanded_view()

    def set_all_palettes(self, palettes_dict: dict[int, list[tuple[int, int, int]]]) -> None:
        """Set all palettes from a dictionary"""
        for palette_index, colors in palettes_dict.items():
            self.set_palette(palette_index, colors)

    def clear(self):
        """Clear all palettes"""
        for widget in self._expanded_widgets.values():
            widget.clear()
        for row in self._collapsed_rows.values():
            row.clear()
        self._expanded_widget.clear()

    def highlight_palette(self, palette_index: int, highlight: bool = True) -> None:
        """Highlight a specific palette"""
        if highlight:
            if palette_index not in self._active_indices:
                self._active_indices.append(palette_index)
        elif palette_index in self._active_indices:
            self._active_indices.remove(palette_index)

        # Update collapsed row highlight
        if palette_index in self._collapsed_rows:
            self._collapsed_rows[palette_index].set_highlighted(highlight)

        # Update expanded view if this is the expanded palette
        if palette_index == self._expanded_index:
            self._update_expanded_highlight(highlight)

    def highlight_active_palettes(self, active_indices: list[int]) -> None:
        """Highlight multiple active palettes"""
        # Clear all highlights first
        for idx in range(8, 16):
            self.highlight_palette(idx, False)

        # Highlight active ones
        for idx in active_indices:
            self.highlight_palette(idx, True)

        # Auto-expand the first active palette if available
        if active_indices and active_indices[0] != self._expanded_index:
            self._set_expanded(active_indices[0])

