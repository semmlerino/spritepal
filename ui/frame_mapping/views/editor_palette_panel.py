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
    QCheckBox,
    QColorDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QMessageBox,
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
    ctrl_clicked = Signal(int)  # palette index (for merge target selection)
    hovered = Signal(int)  # palette index
    color_change_requested = Signal(int, object)  # (index, (r, g, b)) - use object for tuple

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
        self._is_highlighted = False
        self._is_merge_target = False
        self._is_free = False
        self._is_locked = False  # Palette lock state from parent

        self.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
        self.setMouseTracking(True)
        self._update_style()
        self._update_tooltip()

    def set_color(self, color: tuple[int, int, int]) -> None:
        """Set the swatch color."""
        self._color = color
        self._update_style()
        self._update_tooltip()

    def set_selected(self, selected: bool) -> None:
        """Set selection state."""
        self._is_selected = selected
        self._update_style()

    def set_highlighted(self, highlighted: bool) -> None:
        """Set highlight state (from canvas hover)."""
        self._is_highlighted = highlighted
        self._update_style()

    def set_merge_target(self, is_target: bool) -> None:
        """Set merge target state (Ctrl+click selection for merging)."""
        self._is_merge_target = is_target
        self._update_style()

    def set_free(self, is_free: bool) -> None:
        """Set free slot state (after merge, slot becomes unused)."""
        self._is_free = is_free
        self._update_style()
        self._update_tooltip()

    def set_locked(self, locked: bool) -> None:
        """Set locked state (prevents color editing)."""
        self._is_locked = locked
        self._update_tooltip()

    def is_free(self) -> bool:
        """Check if this slot is marked as free."""
        return self._is_free

    def get_display_text(self) -> str:
        """Get the text to display on this swatch.

        Returns:
            'T' for index 0 (transparent), otherwise the index number.
        """
        if self._index == 0:
            return "T"
        return str(self._index)

    def _update_style(self) -> None:
        """Update widget style based on state."""
        r, g, b = self._color

        # Free slot - show as dark purple
        if self._is_free and self._index != 0:
            style = """
                QFrame {
                    background-color: rgb(48, 16, 64);
                    border: 3px solid %s;
                }
            """
            # Free slots still show border based on state
            if self._is_merge_target:
                border_color = "#00FFFF"  # Cyan for merge target
            elif self._is_hovered:
                border_color = "#888"
            else:
                border_color = "#333"
            self.setStyleSheet(style % border_color)
            return

        if self._index == 0:
            # Transparent - checkerboard pattern
            style = """
                QFrame {
                    background-color: qlineargradient(spread:repeat, x1:0, y1:0, x2:0.5, y2:0.5,
                        stop:0 #666666, stop:0.5 #666666, stop:0.5 #888888, stop:1 #888888);
                    border: 3px solid %s;
                }
            """
        else:
            style = """
                QFrame {
                    background-color: rgb(%d, %d, %d);
                    border: 3px solid %s;
                }
            """

        # Priority: selected (yellow) > merge_target (cyan) > highlighted (green) > hovered (gray) > default
        if self._is_selected:
            border_color = "#FFFF00"  # Yellow for selected
        elif self._is_merge_target:
            border_color = "#00FFFF"  # Cyan for merge target
        elif self._is_highlighted:
            border_color = "#00FF00"  # Green for highlighted from canvas
        elif self._is_hovered:
            border_color = "#888"
        else:
            border_color = "#444"

        if self._index == 0:
            self.setStyleSheet(style % border_color)
        else:
            self.setStyleSheet(style % (r, g, b, border_color))

    def _update_tooltip(self) -> None:
        """Update tooltip based on swatch state."""
        if self._index == 0:
            self.setToolTip("Index 0: Transparent\nPixels with this index are fully transparent.\nCannot be edited.")
        elif self._is_locked:
            r, g, b = self._color
            self.setToolTip(f"Index {self._index}: RGB({r}, {g}, {b})\n🔒 Palette is locked\nClick: Select as active")
        elif self._is_free:
            self.setToolTip(
                f"Index {self._index}: Free slot\nThis slot is unused after merge.\nRight-click to assign a new color."
            )
        else:
            r, g, b = self._color
            self.setToolTip(
                f"Index {self._index}: RGB({r}, {g}, {b})\n"
                "Click: Select as active\n"
                "Ctrl+Click: Merge into active\n"
                "Right-click: Change color"
            )

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle click to select color, Ctrl+click for merge, right-click to change color."""
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # Ctrl+click for merge target selection
                self.ctrl_clicked.emit(self._index)
            else:
                self.clicked.emit(self._index)
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_color_picker()
        super().mousePressEvent(event)

    def _show_color_picker(self) -> None:
        """Show color picker dialog to change this swatch's color."""
        # Don't allow changing index 0 (transparent)
        if self._index == 0:
            return

        # Don't allow changing when locked
        if self._is_locked:
            return

        r, g, b = self._color
        initial_color = QColor(r, g, b)

        color = QColorDialog.getColor(
            initial_color,
            self,
            f"Choose color for index {self._index}",
        )

        if color.isValid():
            new_color = (color.red(), color.green(), color.blue())
            self.color_change_requested.emit(self._index, new_color)

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
        """Paint with index number/transparency overlay."""
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

        # Draw index/transparency indicator in bottom-right corner
        text = self.get_display_text()
        rect = self.rect().adjusted(2, 2, -3, -3)
        painter.drawText(rect, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight, text)

        painter.end()


class EditorPalettePanel(QWidget):
    """Panel showing 16-color palette for index selection.

    Signals:
        index_selected: (index) - User selected a palette index
        index_hovered: (index) - User is hovering over a palette index
        color_changed: (index, (r, g, b)) - User changed a color via right-click
        merge_requested: (primary_index, merge_index) - User wants to merge two palettes
    """

    index_selected = Signal(int)
    index_hovered = Signal(int)
    color_changed = Signal(int, object)  # (index, (r, g, b)) - use object for tuple
    merge_requested = Signal(int, int)  # (primary_index, merge_index)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._swatches: list[ColorSwatch] = []
        self._active_index = 1
        self._merge_target_index: int | None = None
        self._free_slots: set[int] = set()
        self._palette_locked = False
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
            swatch.ctrl_clicked.connect(self._on_swatch_ctrl_clicked)
            swatch.hovered.connect(self._on_swatch_hovered)
            swatch.color_change_requested.connect(self._on_color_change_requested)
            self._swatches.append(swatch)
            grid.addWidget(swatch, row, col)

        layout.addWidget(grid_widget)

        # Transparency note
        self._transparency_note = QLabel("Index 0 (T) = Transparent")
        self._transparency_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._transparency_note.setStyleSheet("color: #666; font-size: 9px; font-style: italic;")
        layout.addWidget(self._transparency_note)

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

        # Lock palette checkbox
        self._lock_checkbox = QCheckBox("Lock Palette")
        self._lock_checkbox.setToolTip(
            "When locked, palette colors cannot be changed.\nPrevents accidental edits via right-click or merge."
        )
        self._lock_checkbox.setStyleSheet("color: #888; font-size: 10px;")
        self._lock_checkbox.toggled.connect(self._on_lock_toggled)
        layout.addWidget(self._lock_checkbox)

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

    def sync_palette(self, palette: SheetPalette) -> None:
        """Sync palette colors from a SheetPalette, preserving free slot state.

        Unlike set_palette(), this preserves the visual state of free slots.

        Args:
            palette: SheetPalette with 16 colors
        """
        for i, swatch in enumerate(self._swatches):
            if i < len(palette.colors):
                # Only update color if not a free slot
                if i not in self._free_slots:
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

    def highlight_index(self, index: int | None) -> None:
        """Highlight a palette index (from canvas hover).

        Args:
            index: Palette index to highlight, or None to clear
        """
        for i, swatch in enumerate(self._swatches):
            swatch.set_highlighted(index is not None and i == index)

    def _on_swatch_clicked(self, index: int) -> None:
        """Handle swatch click."""
        # Clear any merge target on regular click
        self.clear_merge_target()
        self.set_active_index(index)
        self.index_selected.emit(index)

    def _on_swatch_ctrl_clicked(self, index: int) -> None:
        """Handle Ctrl+click for merge target selection.

        When Ctrl+click is used on a second palette:
        - If same as active: do nothing
        - If no active selection: do nothing
        - If index 0: do nothing (can't merge with transparent)
        - If palette is locked: do nothing
        - Otherwise: show confirmation and emit merge_requested signal
        """
        # Can't merge if palette is locked
        if self._palette_locked:
            QMessageBox.information(
                self,
                "Palette Locked",
                "Cannot merge indices while palette is locked.\nUncheck 'Lock Palette' to enable merging.",
            )
            return

        # Can't merge with transparent
        if index == 0:
            return

        # Can't merge same index
        if index == self._active_index:
            return

        # Can't merge with index 0 as primary
        if self._active_index == 0:
            return

        # Can't merge if primary is free
        if self._active_index in self._free_slots:
            return

        # Show confirmation dialog
        result = QMessageBox.question(
            self,
            "Merge Palette Indices",
            f"Merge index {index} into index {self._active_index}?\n\n"
            f"All pixels using index {index} will be changed to index {self._active_index}.\n"
            f"This action can be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        # Set as merge target and emit signal
        self._set_merge_target(index)

        # Emit merge signal: primary stays, merge_index gets absorbed
        self.merge_requested.emit(self._active_index, index)

    def _set_merge_target(self, index: int | None) -> None:
        """Set the merge target index with visual indicator."""
        # Clear previous target
        if self._merge_target_index is not None and self._merge_target_index < len(self._swatches):
            self._swatches[self._merge_target_index].set_merge_target(False)

        self._merge_target_index = index

        # Set new target
        if index is not None and index < len(self._swatches):
            self._swatches[index].set_merge_target(True)

    def clear_merge_target(self) -> None:
        """Clear the merge target selection."""
        self._set_merge_target(None)

    def mark_slot_free(self, index: int) -> None:
        """Mark a palette slot as free (after merge).

        Args:
            index: Palette index to mark as free (1-15)
        """
        if not 0 < index < len(self._swatches):
            return

        self._free_slots.add(index)
        self._swatches[index].set_free(True)
        self.clear_merge_target()

    def is_slot_free(self, index: int) -> bool:
        """Check if a slot is marked as free."""
        return index in self._free_slots

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

    def _on_lock_toggled(self, locked: bool) -> None:
        """Handle lock checkbox toggle."""
        self._palette_locked = locked
        # Propagate lock state to all swatches for tooltip updates
        for swatch in self._swatches:
            swatch.set_locked(locked)

    def is_palette_locked(self) -> bool:
        """Check if palette editing is locked."""
        return self._palette_locked

    def set_palette_locked(self, locked: bool) -> None:
        """Set the palette lock state.

        Args:
            locked: True to lock palette editing
        """
        self._palette_locked = locked
        self._lock_checkbox.setChecked(locked)
        # Propagate lock state to all swatches
        for swatch in self._swatches:
            swatch.set_locked(locked)

    def _on_color_change_requested(self, index: int, color: tuple[int, int, int]) -> None:
        """Handle color change from right-click."""
        # Check lock state
        if self._palette_locked:
            QMessageBox.information(
                self,
                "Palette Locked",
                "Cannot change colors while palette is locked.\nUncheck 'Lock Palette' to enable editing.",
            )
            return

        if 0 < index < len(self._swatches):
            self._swatches[index].set_color(color)
            self.color_changed.emit(index, color)
        else:
            logger.warning(f"Invalid index {index} for color change")

    @override
    def sizeHint(self) -> QSize:
        """Return preferred size."""
        return QSize(SWATCH_SIZE * GRID_COLS + 16, 300)
