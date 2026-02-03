"""Compact widget for displaying and editing sheet-level palette configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette

logger = get_logger(__name__)

# Swatch size for palette display
SWATCH_SIZE = 18
# Colors for visual states
HIGHLIGHT_COLOR = QColor(33, 150, 243)  # Blue glow for hover
SELECTED_COLOR = QColor(255, 193, 7)  # Yellow border for selection


class PaletteSwatchWidget(QWidget):
    """Interactive widget displaying a colored square with click and hover support.

    Signals:
        clicked: Emitted when swatch is clicked (single click)
        double_clicked: Emitted when swatch is double-clicked
        hovered: Emitted when mouse enters (True) or leaves (False)
    """

    clicked = Signal(int)  # index
    double_clicked = Signal(int)  # index
    hovered = Signal(int, bool)  # index, is_hovered

    def __init__(
        self,
        color: tuple[int, int, int],
        index: int,
        size: int = SWATCH_SIZE,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = color
        self._index = index
        self._highlighted = False  # Blue glow from canvas hover
        self._selected = False  # Yellow border from selection
        self.setFixedSize(size, size)
        self.setToolTip(f"[{index}] RGB({color[0]}, {color[1]}, {color[2]})")
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_color(self, color: tuple[int, int, int]) -> None:
        """Update the displayed color."""
        self._color = color
        self.setToolTip(f"[{self._index}] RGB({color[0]}, {color[1]}, {color[2]})")
        self.update()

    def set_highlighted(self, highlighted: bool) -> None:
        """Set the highlighted state (blue glow from canvas hover)."""
        if self._highlighted != highlighted:
            self._highlighted = highlighted
            self.update()

    def set_selected(self, selected: bool) -> None:
        """Set the selected state (yellow border from user selection)."""
        if self._selected != selected:
            self._selected = selected
            self.update()

    def index(self) -> int:
        """Return the palette index of this swatch."""
        return self._index

    def color(self) -> tuple[int, int, int]:
        """Return the current color."""
        return self._color

    @override
    def enterEvent(self, event: object) -> None:
        """Handle mouse entering the swatch."""
        self.hovered.emit(self._index, True)
        super().enterEvent(event)  # type: ignore[arg-type]

    @override
    def leaveEvent(self, event: object) -> None:
        """Handle mouse leaving the swatch."""
        self.hovered.emit(self._index, False)
        super().leaveEvent(event)  # type: ignore[arg-type]

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press (single click)."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)
        super().mousePressEvent(event)

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle mouse double-click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._index)
        super().mouseDoubleClickEvent(event)

    @override
    def paintEvent(self, event: object) -> None:
        """Draw the color swatch with highlight/selection states."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fill with color
        painter.fillRect(self.rect(), QColor(*self._color))

        # Draw border based on state
        if self._selected:
            # Yellow border for selection (3px)
            pen = QPen(SELECTED_COLOR, 3)
            painter.setPen(pen)
            painter.drawRect(1, 1, self.width() - 3, self.height() - 3)
        elif self._highlighted:
            # Blue glow for highlight (2px)
            pen = QPen(HIGHLIGHT_COLOR, 2)
            painter.setPen(pen)
            painter.drawRect(1, 1, self.width() - 3, self.height() - 3)
        else:
            # Normal gray border
            painter.setPen(Qt.GlobalColor.darkGray)
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        # Indicate transparency for index 0
        if self._index == 0:
            painter.setPen(Qt.GlobalColor.red)
            painter.drawLine(0, 0, self.width() - 1, self.height() - 1)

        painter.end()


class SheetPaletteWidget(QWidget):
    """Compact widget showing sheet palette with Edit and Extract buttons.

    Displays a row of 16 interactive color swatches and provides buttons to edit the
    palette mapping or extract colors from the loaded AI frames.

    Signals:
        edit_requested: Emitted when user clicks "Edit Palette..."
        extract_requested: Emitted when user clicks "Extract from Sheet"
        clear_requested: Emitted when user clicks "Clear" to remove palette
        index_selected: Emitted when user clicks a swatch (index)
        color_edit_requested: Emitted when user double-clicks a swatch (index)
        color_changed: Emitted when a color is edited (index, rgb_tuple)
        swatch_hovered: Emitted when mouse enters/leaves a swatch (index or None)
    """

    edit_requested = Signal()
    extract_requested = Signal()
    clear_requested = Signal()
    index_selected = Signal(int)  # user clicked a swatch
    color_edit_requested = Signal(int)  # user double-clicked a swatch
    color_changed = Signal(int, object)  # index, rgb tuple
    swatch_hovered = Signal(object)  # int index or None when mouse leaves

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sheet_palette: SheetPalette | None = None
        self._swatches: list[PaletteSwatchWidget] = []
        self._highlighted_index: int | None = None
        self._selected_index: int | None = None
        self._capture_palette_indices: set[int] | None = None
        self._current_frame_palette_index: int | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header with title and clear button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        title = QLabel("Sheet Palette")
        title.setStyleSheet("font-weight: bold; font-size: 11px;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self._clear_button = QPushButton("Clear")
        self._clear_button.setToolTip("Remove sheet palette (use capture palettes instead)")
        self._clear_button.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        self._clear_button.setFixedHeight(20)
        self._clear_button.clicked.connect(self.clear_requested.emit)
        self._clear_button.setVisible(False)  # Hidden until palette is set
        header_layout.addWidget(self._clear_button)

        layout.addLayout(header_layout)

        # Palette swatches row
        swatches_layout = QHBoxLayout()
        swatches_layout.setContentsMargins(0, 0, 0, 0)
        swatches_layout.setSpacing(1)

        # Create 16 swatches (initially all black/empty)
        for i in range(16):
            swatch = PaletteSwatchWidget((0, 0, 0), i)
            if i == 0:
                swatch.setToolTip("[0] Transparent - cannot be edited")
            # Wire swatch signals
            swatch.clicked.connect(self._on_swatch_clicked)
            swatch.double_clicked.connect(self._on_swatch_double_clicked)
            swatch.hovered.connect(self._on_swatch_hovered)
            self._swatches.append(swatch)
            swatches_layout.addWidget(swatch)

        swatches_layout.addStretch()
        layout.addLayout(swatches_layout)

        # Info label showing current hover/selection
        self._info_label = QLabel("--")
        self._info_label.setStyleSheet("font-size: 10px; font-family: monospace; color: #666;")
        layout.addWidget(self._info_label)

        # Buttons row
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(4)

        self._extract_button = QPushButton("Extract from Sheet...")
        self._extract_button.setToolTip("Generate 16-color palette from all AI frames")
        self._extract_button.setStyleSheet("font-size: 10px;")
        self._extract_button.clicked.connect(self.extract_requested.emit)
        buttons_layout.addWidget(self._extract_button)

        self._edit_button = QPushButton("Map Colors...")
        self._edit_button.setToolTip("Map AI sheet colors to palette indices (global for all frames)")
        self._edit_button.setStyleSheet("font-size: 10px;")
        self._edit_button.clicked.connect(self.edit_requested.emit)
        buttons_layout.addWidget(self._edit_button)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        # Status label
        self._status_label = QLabel("No palette defined - using capture palettes")
        self._status_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self._status_label)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _on_swatch_clicked(self, index: int) -> None:
        """Handle swatch click - select it."""
        self.select_index(index)
        self.index_selected.emit(index)

    def _on_swatch_double_clicked(self, index: int) -> None:
        """Handle swatch double-click - open color editor."""
        if index == 0:
            # Index 0 is always transparent - don't allow editing
            return
        self.color_edit_requested.emit(index)
        self._open_color_editor(index)

    def _on_swatch_hovered(self, index: int, is_hovered: bool) -> None:
        """Handle swatch hover - emit swatch_hovered signal."""
        if is_hovered:
            self.swatch_hovered.emit(index)
            # Update info label with hover info
            if index < len(self._swatches):
                color = self._swatches[index].color()
                self._info_label.setText(f"Index [{index}] • RGB({color[0]}, {color[1]}, {color[2]})")
        else:
            self.swatch_hovered.emit(None)
            # Revert to selected info or clear
            if self._selected_index is not None:
                color = self._swatches[self._selected_index].color()
                self._info_label.setText(f"Selected [{self._selected_index}] • RGB({color[0]}, {color[1]}, {color[2]})")
            else:
                self._info_label.setText("--")

    def _open_color_editor(self, index: int) -> None:
        """Open QColorDialog to edit a color at the given index."""
        if index == 0:
            return  # Index 0 is transparent, not editable
        if self._sheet_palette is None:
            return

        if index >= len(self._swatches):
            return

        current_color = self._swatches[index].color()
        qcolor = QColor(*current_color)

        new_qcolor = QColorDialog.getColor(
            qcolor,
            self,
            f"Edit Palette Color [{index}]",
        )

        if new_qcolor.isValid():
            new_rgb = (new_qcolor.red(), new_qcolor.green(), new_qcolor.blue())
            # Update swatch immediately
            self._swatches[index].set_color(new_rgb)
            # Emit signal for controller to update palette
            self.color_changed.emit(index, new_rgb)

    def highlight_index(self, index: int | None) -> None:
        """Highlight a swatch (blue glow) from canvas hover.

        Args:
            index: Palette index to highlight, or None to clear highlight
        """
        if self._highlighted_index == index:
            return

        # Clear previous highlight
        if self._highlighted_index is not None and 0 <= self._highlighted_index < len(self._swatches):
            self._swatches[self._highlighted_index].set_highlighted(False)

        self._highlighted_index = index

        # Set new highlight (bounds check prevents negative indexing)
        if index is not None and 0 <= index < len(self._swatches):
            self._swatches[index].set_highlighted(True)
            # Update info label
            color = self._swatches[index].color()
            self._info_label.setText(f"Index [{index}] • RGB({color[0]}, {color[1]}, {color[2]})")

    def select_index(self, index: int) -> None:
        """Select a swatch (yellow border) from user selection or eyedropper.

        Args:
            index: Palette index to select
        """
        if self._selected_index == index:
            return

        # Clear previous selection
        if self._selected_index is not None and 0 <= self._selected_index < len(self._swatches):
            self._swatches[self._selected_index].set_selected(False)

        self._selected_index = index

        # Set new selection (bounds check prevents negative indexing)
        if 0 <= index < len(self._swatches):
            self._swatches[index].set_selected(True)
            # Update info label
            color = self._swatches[index].color()
            self._info_label.setText(f"Selected [{index}] • RGB({color[0]}, {color[1]}, {color[2]})")

    def clear_selection(self) -> None:
        """Clear the current selection."""
        if self._selected_index is not None and self._selected_index < len(self._swatches):
            self._swatches[self._selected_index].set_selected(False)
        self._selected_index = None
        if self._highlighted_index is None:
            self._info_label.setText("--")

    def set_palette(self, palette: SheetPalette | None) -> None:
        """Set the sheet palette to display.

        Args:
            palette: SheetPalette to display, or None to clear
        """
        self._sheet_palette = palette

        if palette is not None:
            # Update swatch colors
            for i, swatch in enumerate(self._swatches):
                if i < len(palette.colors):
                    swatch.set_color(palette.colors[i])
                else:
                    swatch.set_color((0, 0, 0))

            self._clear_button.setVisible(True)
        else:
            # Reset to black
            for swatch in self._swatches:
                swatch.set_color((0, 0, 0))
            self._clear_button.setVisible(False)

        # Update status label (uses both palette and capture info)
        self._update_status_label()

        # Clear selection when palette changes
        self.clear_selection()

    def get_palette(self) -> SheetPalette | None:
        """Get the current sheet palette."""
        return self._sheet_palette

    def set_capture_palette_info(self, palette_indices: set[int] | None) -> None:
        """Set which capture palettes are in use (for status display).

        Args:
            palette_indices: Set of palette indices in use, or None to clear
        """
        self._capture_palette_indices = palette_indices
        self._update_status_label()

    def set_current_frame_palette_index(self, index: int | None) -> None:
        """Set the palette index used by the currently selected frame.

        Args:
            index: Palette index (0-7) for the current frame, or None to clear
        """
        self._current_frame_palette_index = index
        self._update_status_label()

    def _update_status_label(self) -> None:
        """Update status label based on current state."""
        if self._sheet_palette is not None:
            # Sheet palette defined - build status parts
            parts: list[str] = []

            # Mapping count
            mapping_count = len(self._sheet_palette.color_mappings)
            if mapping_count > 0:
                parts.append(f"Palette ({mapping_count} mappings)")
            else:
                parts.append("Palette defined")

            # Background removal indicator
            bg = self._sheet_palette.background_color
            if bg is not None and len(bg) == 3:
                r, g, b = bg
                tol = self._sheet_palette.background_tolerance
                parts.append(f"BG: RGB({r},{g},{b}) ±{tol}")

            self._status_label.setText(" • ".join(parts))
        elif self._current_frame_palette_index is not None:
            # No sheet palette but have current frame - show its specific palette index
            self._status_label.setText(f"Current frame uses palette {self._current_frame_palette_index}")
        elif self._capture_palette_indices:
            # No sheet palette, no current frame - show all capture palette indices
            indices_str = ", ".join(str(i) for i in sorted(self._capture_palette_indices))
            if len(self._capture_palette_indices) > 1:
                self._status_label.setText(f"No sheet palette - using capture palettes {indices_str} ⚠")
            else:
                self._status_label.setText(f"No sheet palette - using capture palette {indices_str}")
        else:
            self._status_label.setText("No palette defined - using capture palettes")

    def set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable the buttons (when no AI frames are loaded)."""
        self._extract_button.setEnabled(enabled)
        self._edit_button.setEnabled(enabled)
