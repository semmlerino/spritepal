"""
Grid Arrangement Dialog for SpritePal
Flexible sprite arrangement supporting rows, columns, and custom tile groups
"""

from __future__ import annotations

import warnings
from enum import Enum
from pathlib import Path
from typing import Any, override

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QFocusEvent,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .components import SplitterDialog
from .row_arrangement import PaletteColorizer
from .row_arrangement.grid_arrangement_manager import (
    ArrangementType,
    GridArrangementManager,
    TileGroup,
    TilePosition,
)
from .row_arrangement.grid_image_processor import GridImageProcessor
from .row_arrangement.grid_preview_generator import GridPreviewGenerator
from .row_arrangement.undo_redo import (
    AddGroupCommand,
    AddMultipleTilesCommand,
    AddRowTilesCommand,
    AddColumnTilesCommand,
    ClearGridCommand,
    RemoveMultipleTilesCommand,
    UndoRedoStack,
)
from .utils.accessibility import AccessibilityHelper


class SelectionMode(Enum):
    """Selection modes for grid interaction"""

    TILE = "tile"
    ROW = "row"
    COLUMN = "column"
    RECTANGLE = "rectangle"

class GridGraphicsView(QGraphicsView):
    """Custom graphics view for grid-based sprite selection"""

    # Signals
    tile_clicked = Signal(object)  # TilePosition
    tiles_selected = Signal(list)  # List of TilePosition
    selection_completed = Signal()
    zoom_changed = Signal(float)  # Zoom level changed

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.tile_width = 8
        self.tile_height = 8
        self.grid_cols = 0
        self.grid_rows = 0

        self.selection_mode = SelectionMode.TILE
        self.selecting = False
        self.selection_start: TilePosition | None = None
        self.current_selection: set[TilePosition] = set()

        # Keyboard navigation state
        self.keyboard_focus_pos: TilePosition | None = None
        self.keyboard_focus_rect: QGraphicsRectItem | None = None
        self.keyboard_nav_active = False

        # Zoom and pan state
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 20.0
        self.is_panning = False
        self.last_pan_point = None

        # Visual elements
        self.grid_lines: list[QGraphicsLineItem] = []
        self.selection_rects: dict[TilePosition, QGraphicsRectItem] = {}
        self.hover_rect: QGraphicsRectItem | None = None

        # Colors
        self.grid_color = QColor(128, 128, 128, 64)
        self.selection_color = QColor(255, 255, 0, 128)
        self.hover_color = QColor(0, 255, 255, 64)
        self.arranged_color = QColor(0, 255, 0, 64)
        self.keyboard_focus_color = QColor(0, 0, 255, 128)  # Blue border for keyboard focus
        self.group_colors = [
            QColor(255, 0, 0, 64),
            QColor(0, 0, 255, 64),
            QColor(255, 128, 0, 64),
            QColor(128, 0, 255, 64),
        ]

        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        # Enable keyboard focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_grid_dimensions(
        self, cols: int, rows: int, tile_width: int, tile_height: int
    ):
        """Set the grid dimensions"""
        self.grid_cols = cols
        self.grid_rows = rows
        self.tile_width = tile_width
        self.tile_height = tile_height
        self._update_grid_lines()

    def set_selection_mode(self, mode: SelectionMode):
        """Set the selection mode"""
        self.selection_mode = mode
        self.clear_selection()

    def clear_selection(self):
        """Clear current selection"""
        if self.current_selection:
            self.current_selection.clear()
        scene = self.scene()
        if scene:
            for rect in self.selection_rects.values():
                scene.removeItem(rect)
        if self.selection_rects:
            self.selection_rects.clear()

    def highlight_arranged_tiles(
        self, tiles: list[TilePosition], color: QColor | None = None
    ):
        """Highlight arranged tiles"""
        if color is None:
            color = self.arranged_color

        scene = self.scene()
        if scene:
            for tile_pos in tiles:
                if tile_pos not in self.selection_rects:
                    rect = self._create_tile_rect(tile_pos, color)
                    scene.addItem(rect)
                    self.selection_rects[tile_pos] = rect

    @override
    def mousePressEvent(self, event: QMouseEvent | None):
        """Handle mouse press"""
        if event and event.button() == Qt.MouseButton.LeftButton:
            # Check if we should pan instead of select
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.is_panning = True
                self.last_pan_point = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            else:
                pos = self.mapToScene(event.pos())
                tile_pos = self._pos_to_tile(pos)

                if tile_pos and self._is_valid_tile(tile_pos):
                    self.selecting = True
                    self.selection_start = tile_pos

                    if self.selection_mode == SelectionMode.TILE:
                        self.current_selection = {tile_pos}
                        self.tile_clicked.emit(tile_pos)
                    elif self.selection_mode == SelectionMode.ROW:
                        self._select_row(tile_pos.row)
                    elif self.selection_mode == SelectionMode.COLUMN:
                        self._select_column(tile_pos.col)
                    elif self.selection_mode == SelectionMode.RECTANGLE:
                        self.current_selection = {tile_pos}

                    self._update_selection_display()
        elif event and event.button() == Qt.MouseButton.MiddleButton:
            # Middle mouse button for panning
            self.is_panning = True
            self.last_pan_point = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        if event:
            super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent | None):
        """Handle mouse move"""
        if event and self.is_panning and self.last_pan_point is not None:
            # Pan the view
            delta = event.pos() - self.last_pan_point
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            if h_bar:
                h_bar.setValue(h_bar.value() - delta.x())
            if v_bar:
                v_bar.setValue(v_bar.value() - delta.y())
            self.last_pan_point = event.pos()
        elif event:
            pos = self.mapToScene(event.pos())
            tile_pos = self._pos_to_tile(pos)

            # Update hover
            if tile_pos and self._is_valid_tile(tile_pos):
                self._update_hover(tile_pos)

            # Update rectangle selection
            if (self.selecting and self.selection_mode == SelectionMode.RECTANGLE and
                tile_pos and self._is_valid_tile(tile_pos) and self.selection_start):
                self._update_rectangle_selection(self.selection_start, tile_pos)

        if event:
            super().mouseMoveEvent(event)

    @override
    def wheelEvent(self, event: QWheelEvent | None):
        """Handle mouse wheel for zooming"""
        if event and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom with Ctrl+Wheel
            zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            self._zoom_at_point(event.position().toPoint(), zoom_factor)
        elif event:
            # Default scroll behavior
            super().wheelEvent(event)

    @override
    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        """Handle keyboard navigation and shortcuts"""
        if not a0:
            return

        # Zoom shortcuts (existing functionality)
        if a0.key() == Qt.Key.Key_F:
            # F: Zoom to fit
            self.zoom_to_fit()
        elif a0.key() == Qt.Key.Key_0 and a0.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+0: Reset zoom
            self.reset_zoom()
        elif a0.key() == Qt.Key.Key_Plus and a0.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl++: Zoom in
            self.zoom_in()
        elif a0.key() == Qt.Key.Key_Minus and a0.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+-: Zoom out
            self.zoom_out()

        # Tile navigation with arrow keys
        elif a0.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._handle_arrow_key_navigation(a0)

        # Tile selection with Space/Enter
        elif a0.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._handle_tile_selection_key()

        # Home/End keys for navigation
        elif a0.key() == Qt.Key.Key_Home:
            # Go to first tile
            self._set_keyboard_focus(TilePosition(0, 0))
        elif a0.key() == Qt.Key.Key_End:
            # Go to last tile
            if self.grid_rows > 0 and self.grid_cols > 0:
                self._set_keyboard_focus(TilePosition(self.grid_rows - 1, self.grid_cols - 1))

        # Page Up/Down for larger movements
        elif a0.key() == Qt.Key.Key_PageUp:
            if self.keyboard_focus_pos:
                new_row = max(0, self.keyboard_focus_pos.row - 5)
                self._set_keyboard_focus(TilePosition(new_row, self.keyboard_focus_pos.col))
        elif a0.key() == Qt.Key.Key_PageDown:
            if self.keyboard_focus_pos:
                new_row = min(self.grid_rows - 1, self.keyboard_focus_pos.row + 5)
                self._set_keyboard_focus(TilePosition(new_row, self.keyboard_focus_pos.col))

        # Escape to clear selection
        elif a0.key() == Qt.Key.Key_Escape:
            self.clear_selection()
            self._clear_keyboard_focus()

        else:
            super().keyPressEvent(a0)

    def _zoom_at_point(self, point: Any, zoom_factor: float) -> None:  # pyright: ignore[reportExplicitAny] - Qt point type
        """Zoom at a specific point"""
        # Calculate new zoom level
        new_zoom = self.zoom_level * zoom_factor
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))

        if new_zoom != self.zoom_level:
            # Convert point to QPoint if needed
            point_as_qpoint = point.toPoint() if hasattr(point, "toPoint") else point

            # Get the scene position before zoom
            scene_pos = self.mapToScene(point_as_qpoint)

            # Apply zoom
            zoom_change = new_zoom / self.zoom_level
            self.scale(zoom_change, zoom_change)
            self.zoom_level = new_zoom

            # Adjust view to keep the point under cursor
            new_viewport_pos = self.mapFromScene(scene_pos)
            delta = point_as_qpoint - new_viewport_pos
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            if h_bar:
                h_bar.setValue(h_bar - delta.x())
            if v_bar:
                v_bar.setValue(v_bar - delta.y())

            # Emit zoom change signal
            self.zoom_changed.emit(self.zoom_level)

    def zoom_in(self):
        """Zoom in by a fixed factor"""
        viewport = self.viewport()
        if viewport:
            center = viewport.rect().center()
            self._zoom_at_point(center, 1.25)

    def zoom_out(self):
        """Zoom out by a fixed factor"""
        viewport = self.viewport()
        if viewport:
            center = viewport.rect().center()
            self._zoom_at_point(center, 0.8)

    def zoom_to_fit(self):
        """Zoom to fit the scene content"""
        if self.scene():
            # Reset zoom first
            self.resetTransform()
            self.zoom_level = 1.0

            # Fit the scene in view
            scene = self.scene()
            if scene:
                self.fitInView(
                    scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio
                )

            # Calculate the actual zoom level
            transform = self.transform()
            self.zoom_level = transform.m11()  # Get scale factor

            # Emit zoom change signal
            self.zoom_changed.emit(self.zoom_level)

    def reset_zoom(self):
        """Reset zoom to 1:1"""
        self.resetTransform()
        self.zoom_level = 1.0

        # Emit zoom change signal
        self.zoom_changed.emit(self.zoom_level)

    def get_zoom_level(self):
        """Get current zoom level"""
        return self.zoom_level

    @override
    def mouseReleaseEvent(self, event: QMouseEvent | None):
        """Handle mouse release"""
        if event and event.button() == Qt.MouseButton.LeftButton:
            if self.is_panning:
                self.is_panning = False
                self.last_pan_point = None
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif self.selecting:
                self.selecting = False
                if self.current_selection:
                    self.tiles_selected.emit(list(self.current_selection))
                    self.selection_completed.emit()
        elif event and event.button() == Qt.MouseButton.MiddleButton and self.is_panning:
            self.is_panning = False
            self.last_pan_point = None
            self.setCursor(Qt.CursorShape.CrossCursor)

        if event:
            super().mouseReleaseEvent(event)

    def _pos_to_tile(self, pos: QPointF) -> TilePosition | None:
        """Convert scene position to tile position"""
        if pos.x() < 0 or pos.y() < 0:
            return None

        col = int(pos.x() // self.tile_width)
        row = int(pos.y() // self.tile_height)

        return TilePosition(row, col)

    def _is_valid_tile(self, tile_pos: TilePosition) -> bool:
        """Check if tile position is valid"""
        return 0 <= tile_pos.row < self.grid_rows and 0 <= tile_pos.col < self.grid_cols

    def _create_tile_rect(
        self, tile_pos: TilePosition, color: QColor
    ) -> QGraphicsRectItem:
        """Create a rectangle for a tile"""
        x = tile_pos.col * self.tile_width
        y = tile_pos.row * self.tile_height
        rect = QGraphicsRectItem(x, y, self.tile_width, self.tile_height)
        rect.setPen(QPen(Qt.PenStyle.NoPen))
        rect.setBrush(QBrush(color))
        rect.setZValue(1)  # Above grid lines
        return rect

    def _handle_arrow_key_navigation(self, event: QKeyEvent) -> None:
        """Handle arrow key navigation between tiles"""
        if not self.keyboard_focus_pos:
            # Initialize focus at top-left if not set
            self._set_keyboard_focus(TilePosition(0, 0))
            return

        row, col = self.keyboard_focus_pos.row, self.keyboard_focus_pos.col
        shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        # Calculate new position based on key
        if event.key() == Qt.Key.Key_Left:
            col = max(0, col - 1)
        elif event.key() == Qt.Key.Key_Right:
            col = min(self.grid_cols - 1, col + 1)
        elif event.key() == Qt.Key.Key_Up:
            row = max(0, row - 1)
        elif event.key() == Qt.Key.Key_Down:
            row = min(self.grid_rows - 1, row + 1)

        new_pos = TilePosition(row, col)

        # Handle selection extension with Shift
        if shift_pressed and self.selection_mode != SelectionMode.TILE:
            # Extend selection from start position to new position
            if not self.selection_start:
                self.selection_start = self.keyboard_focus_pos

            # Calculate selection based on mode
            if self.selection_mode == SelectionMode.ROW:
                self.current_selection = {
                    TilePosition(new_pos.row, c) for c in range(self.grid_cols)
                }
            elif self.selection_mode == SelectionMode.COLUMN:
                self.current_selection = {
                    TilePosition(r, new_pos.col) for r in range(self.grid_rows)
                }
            elif self.selection_mode == SelectionMode.RECTANGLE:
                # Select rectangle from start to new position
                min_row = min(self.selection_start.row, new_pos.row)
                max_row = max(self.selection_start.row, new_pos.row)
                min_col = min(self.selection_start.col, new_pos.col)
                max_col = max(self.selection_start.col, new_pos.col)

                self.current_selection = {
                    TilePosition(r, c)
                    for r in range(min_row, max_row + 1)
                    for c in range(min_col, max_col + 1)
                }

            self._update_selection_display()
            self.tiles_selected.emit(list(self.current_selection))

        # Move focus to new position
        self._set_keyboard_focus(new_pos)

    def _handle_tile_selection_key(self):
        """Handle Space/Enter key for tile selection"""
        if not self.keyboard_focus_pos:
            return

        # Emit tile clicked signal
        self.tile_clicked.emit(self.keyboard_focus_pos)

        # In tile mode, toggle selection
        if self.selection_mode == SelectionMode.TILE:
            if self.keyboard_focus_pos in self.current_selection:
                self.current_selection.remove(self.keyboard_focus_pos)
            else:
                self.current_selection.add(self.keyboard_focus_pos)

            self._update_selection_display()
            self.tiles_selected.emit(list(self.current_selection))

    def _set_keyboard_focus(self, tile_pos: TilePosition):
        """Set keyboard focus to a specific tile"""
        if not self._is_valid_tile(tile_pos):
            return

        self.keyboard_focus_pos = tile_pos
        self.keyboard_nav_active = True

        # Update visual focus indicator
        self._update_keyboard_focus_display()

        # Ensure the focused tile is visible
        self._ensure_tile_visible(tile_pos)

    def _clear_keyboard_focus(self):
        """Clear keyboard focus"""
        self.keyboard_focus_pos = None
        self.keyboard_nav_active = False

        # Remove focus indicator
        if self.keyboard_focus_rect:
            scene = self.scene()
            if scene and self.keyboard_focus_rect.scene():
                scene.removeItem(self.keyboard_focus_rect)
            self.keyboard_focus_rect = None

    def _update_keyboard_focus_display(self):
        """Update visual display of keyboard focus"""
        scene = self.scene()
        if not scene or not self.keyboard_focus_pos:
            return

        # Remove old focus rect
        if self.keyboard_focus_rect:
            if self.keyboard_focus_rect.scene():
                scene.removeItem(self.keyboard_focus_rect)
            self.keyboard_focus_rect = None

        # Create new focus rect with a border
        x = self.keyboard_focus_pos.col * self.tile_width
        y = self.keyboard_focus_pos.row * self.tile_height

        self.keyboard_focus_rect = QGraphicsRectItem(
            x, y, self.tile_width, self.tile_height
        )
        self.keyboard_focus_rect.setPen(QPen(self.keyboard_focus_color, 2))  # 2px blue border
        self.keyboard_focus_rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))  # Transparent fill
        self.keyboard_focus_rect.setZValue(10)  # Above other elements
        scene.addItem(self.keyboard_focus_rect)

    def _ensure_tile_visible(self, tile_pos: TilePosition):
        """Ensure a tile is visible in the viewport"""
        x = tile_pos.col * self.tile_width
        y = tile_pos.row * self.tile_height

        # Create a rect for the tile and ensure it's visible
        tile_rect = QRectF(x, y, self.tile_width, self.tile_height)
        self.ensureVisible(tile_rect, 50, 50)  # 50px margin

    def _update_selection_display_duplicate(self):
        """Update the visual display of selected tiles - DUPLICATE TO BE REMOVED"""
        scene = self.scene()
        if not scene:
            return

        # Clear old selection rects
        for rect in self.selection_rects.values():
            if rect.scene():
                scene.removeItem(rect)
        if self.selection_rects:
            self.selection_rects.clear()

        # Add new selection rects
        for tile_pos in self.current_selection:
            rect = self._create_tile_rect(tile_pos, self.selection_color)
            scene.addItem(rect)
            self.selection_rects[tile_pos] = rect

    @override
    def focusInEvent(self, event: QFocusEvent | None) -> None:
        """Handle focus in event"""
        if event:
            super().focusInEvent(event)

        # If no keyboard focus set, initialize at (0,0)
        if not self.keyboard_focus_pos and self.grid_rows > 0 and self.grid_cols > 0:
            self._set_keyboard_focus(TilePosition(0, 0))

    @override
    def focusOutEvent(self, event: QFocusEvent | None) -> None:
        """Handle focus out event"""
        if event:
            super().focusOutEvent(event)

        # Keep focus indicator visible but maybe dim it
        # This allows users to see where they were when returning focus

    def _update_grid_lines(self):
        """Update grid line display"""
        # Clear existing grid lines
        scene = self.scene()
        if scene:
            for line in self.grid_lines:
                if line.scene():
                    scene.removeItem(line)
        if self.grid_lines:
            self.grid_lines.clear()

        if not scene:
            return

        pen = QPen(self.grid_color, 1)

        # Vertical lines
        for col in range(self.grid_cols + 1):
            x = col * self.tile_width
            line = scene.addLine(x, 0, x, self.grid_rows * self.tile_height, pen)
            if line:
                self.grid_lines.append(line)

        # Horizontal lines
        for row in range(self.grid_rows + 1):
            y = row * self.tile_height
            line = scene.addLine(0, y, self.grid_cols * self.tile_width, y, pen)
            if line:
                self.grid_lines.append(line)

    def _select_row(self, row: int):
        """Select an entire row"""
        self.current_selection = {
            TilePosition(row, col) for col in range(self.grid_cols)
        }

    def _select_column(self, col: int):
        """Select an entire column"""
        self.current_selection = {
            TilePosition(row, col) for row in range(self.grid_rows)
        }

    def _update_rectangle_selection(self, start: TilePosition, end: TilePosition):
        """Update rectangle selection"""
        min_row = min(start.row, end.row)
        max_row = max(start.row, end.row)
        min_col = min(start.col, end.col)
        max_col = max(start.col, end.col)

        self.current_selection = {
            TilePosition(row, col)
            for row in range(min_row, max_row + 1)
            for col in range(min_col, max_col + 1)
        }
        self._update_selection_display()

    def _update_selection_display(self):
        """Update visual display of selection"""
        # Clear existing selection rects
        scene = self.scene()
        if scene:
            for rect in self.selection_rects.values():
                if rect.scene():
                    scene.removeItem(rect)
        if self.selection_rects:
            self.selection_rects.clear()

        # Add new selection rects
        if scene:
            for tile_pos in self.current_selection:
                rect = self._create_tile_rect(tile_pos, self.selection_color)
                scene.addItem(rect)
                self.selection_rects[tile_pos] = rect

    def _update_hover(self, tile_pos: TilePosition):
        """Update hover display"""
        scene = self.scene()
        if self.hover_rect is not None:
            if self.hover_rect.scene() and scene:
                scene.removeItem(self.hover_rect)
            self.hover_rect = None

        if tile_pos not in self.current_selection and scene:
            self.hover_rect = self._create_tile_rect(tile_pos, self.hover_color)
            self.hover_rect.setZValue(0.5)  # Below selection
            scene.addItem(self.hover_rect)

class GridArrangementDialog(SplitterDialog):
    """Dialog for grid-based sprite arrangement with row and column support"""

    def __init__(self, sprite_path: str, tiles_per_row: int = 16, parent: QWidget | None = None) -> None:
        # Step 1: Declare instance variables BEFORE super().__init__()
        self.sprite_path = sprite_path
        self.tiles_per_row = tiles_per_row
        self.output_path = None

        # Initialize components
        self.processor = GridImageProcessor()
        self.colorizer = PaletteColorizer()
        self.preview_generator = GridPreviewGenerator(self.colorizer)

        # Initialize UI components that will be created in _setup_ui
        self.source_grid: QWidget | None = None
        self.arranged_grid: QWidget | None = None
        self.original_image: Image.Image | None = None
        self.tiles: dict[TilePosition, Image.Image] = {}

        # Load and process sprite before UI setup
        try:
            self.original_image, self.tiles = (
                self.processor.process_sprite_sheet_as_grid(sprite_path, tiles_per_row)
            )
        except (OSError, ValueError, RuntimeError) as e:
            # Show error dialog and close
            _ = QMessageBox.critical(
                parent, "Error Loading Sprite", f"Failed to load sprite file:\n{e!s}"
            )
            # Set up minimal state to prevent crashes
            self.original_image = None
            self.tiles = {}
            self.processor.grid_rows = 1
            self.processor.grid_cols = 1
            # Don't return here - continue with dialog setup but in error state

        # Create arrangement manager
        self.arrangement_manager = GridArrangementManager(
            self.processor.grid_rows, self.processor.grid_cols
        )

        # Create undo/redo stack
        self.undo_stack = UndoRedoStack()

        # Step 2: Call parent init (this will call _setup_ui)
        super().__init__(
            parent=parent,
            title="Grid-Based Sprite Arrangement",
            modal=True,
            size=(1600, 900),
            with_status_bar=True,
            # Don't use automatic splitter creation - create explicitly in _setup_ui
            orientation=None,  # type: ignore[arg-type]
            splitter_handle_width=8,
        )

        # Connect signals after UI is created
        self.arrangement_manager.arrangement_changed.connect(
            self._on_arrangement_changed
        )
        self.colorizer.palette_mode_changed.connect(self._on_palette_mode_changed)

        # Initial update (only if we have valid data)
        if self.original_image is not None:
            self._update_displays()
            self.update_status(
                "Select tiles, rows, or columns to arrange. Ctrl+Wheel or F to zoom."
            )
        else:
            self.update_status("Error: Unable to load sprite file")

    @override
    def _setup_ui(self):
        """Set up the dialog UI using SplitterDialog panels"""
        # Call parent _setup_ui first to initialize the main splitter
        super()._setup_ui()

        # Apply accessibility enhancements
        self._apply_accessibility_enhancements()

        # Create horizontal splitter for left and right panels
        self.main_splitter = self.add_horizontal_splitter(handle_width=8)

        # Create left and right panels
        left_widget = self._create_left_panel()
        right_widget = self._create_right_panel()

        # Add panels to main horizontal splitter
        self.main_splitter.addWidget(left_widget)
        self.main_splitter.setStretchFactor(0, 2)    # 67% for left panel
        self.main_splitter.addWidget(right_widget)
        self.main_splitter.setStretchFactor(1, 1)   # 33% for right panel

        # Add custom buttons using SplitterDialog's button system
        self.export_btn = self.add_button("&Export Arrangement", callback=self._export_arrangement)
        if self.export_btn:
            self.export_btn.setEnabled(False)
        AccessibilityHelper.make_accessible(
            self.export_btn,
            "Export Arrangement",
            "Export the arranged sprites to a new file",
            "Ctrl+E"
        )

    def _create_left_panel(self) -> QWidget:
        """Create the left panel containing grid view and controls.

        Returns:
            QWidget: The configured left panel widget
        """
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)

        # Add selection mode controls
        mode_group = self._create_selection_mode_group(left_widget)
        left_layout.addWidget(mode_group)

        # Add grid view
        grid_group = self._create_grid_view_group(left_widget)
        left_layout.addWidget(grid_group, 1)

        # Add action buttons
        actions_group = self._create_actions_group(left_widget)
        left_layout.addWidget(actions_group)

        return left_widget

    def _create_right_panel(self) -> QWidget:
        """Create the right panel containing arrangement list and preview.

        Returns:
            QWidget: The configured right panel widget
        """
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)

        # Add arrangement list
        list_group = self._create_arrangement_list_group(right_widget)
        right_layout.addWidget(list_group)

        # Add preview
        preview_group = self._create_preview_group(right_widget)
        right_layout.addWidget(preview_group, 1)

        return right_widget

    def _apply_accessibility_enhancements(self) -> None:
        """Apply comprehensive accessibility enhancements to the dialog"""
        # Set dialog accessible name and description
        AccessibilityHelper.make_accessible(
            self,
            "Grid Arrangement Dialog",
            "Arrange sprites in a grid layout with row and column support"
        )

        # Add focus indicators
        AccessibilityHelper.add_focus_indicators(self)

        # Add keyboard shortcuts
        from PySide6.QtGui import QKeySequence, QShortcut

        # Ctrl+E for export
        export_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        export_shortcut.activated.connect(self._export_arrangement)

        # Ctrl+Z for undo (placeholder - not yet implemented)
        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self._on_undo)

        # Ctrl+Y for redo (placeholder - not yet implemented)
        redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        redo_shortcut.activated.connect(self._on_redo)

        # Del for clear selection
        delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        delete_shortcut.activated.connect(self._on_delete_selection)

    def _create_selection_mode_group(self, parent: QWidget) -> QGroupBox:
        """Create the selection mode controls group.

        Args:
            parent: Parent widget for the group

        Returns:
            QGroupBox: The configured selection mode group
        """
        mode_group = QGroupBox("&Selection Mode", parent)
        AccessibilityHelper.add_group_box_navigation(mode_group)
        mode_layout = QHBoxLayout()

        self.mode_buttons = QButtonGroup()

        # Create radio buttons with mnemonics and accessibility
        mode_shortcuts = {
            SelectionMode.TILE: ("&Tile", "T", "Select individual tiles"),
            SelectionMode.ROW: ("&Row", "R", "Select entire rows"),
            SelectionMode.COLUMN: ("&Column", "C", "Select entire columns"),
            SelectionMode.RECTANGLE: ("Rectan&gle", "G", "Select rectangular regions")
        }

        for mode in SelectionMode:
            text, shortcut_key, description = mode_shortcuts.get(mode, (mode.value.capitalize(), "", ""))
            btn = QRadioButton(text)
            btn.setProperty("mode", mode)
            AccessibilityHelper.make_accessible(
                btn,
                f"{mode.value.capitalize()} Selection",
                description,
                f"Alt+{shortcut_key}" if shortcut_key else None
            )
            self.mode_buttons.addButton(btn)
            mode_layout.addWidget(btn)
            if mode == SelectionMode.TILE:
                btn.setChecked(True)

        self.mode_buttons.buttonClicked.connect(self._on_mode_changed)
        mode_group.setLayout(mode_layout)
        return mode_group

    def _create_grid_view_group(self, parent: QWidget) -> QGroupBox:
        """Create the grid view group with graphics scene.

        Args:
            parent: Parent widget for the group

        Returns:
            QGroupBox: The configured grid view group
        """
        grid_group = QGroupBox("Sprite Grid", parent)
        grid_layout = QVBoxLayout()

        # Create graphics scene and view
        self.scene = QGraphicsScene(self)
        self.grid_view = GridGraphicsView(self)
        self.grid_view.setScene(self.scene)

        # Initialize grid view
        self._initialize_grid_view()

        # Connect grid view signals
        self._connect_grid_view_signals()

        grid_layout.addWidget(self.grid_view)
        grid_group.setLayout(grid_layout)
        return grid_group

    def _initialize_grid_view(self):
        """Initialize the grid view with image data if available."""
        if self.original_image is not None:
            pixmap = self._create_pixmap_from_image(self.original_image)
            self.pixmap_item = self.scene.addPixmap(pixmap)
            self.grid_view.set_grid_dimensions(
                self.processor.grid_cols,
                self.processor.grid_rows,
                self.processor.tile_width,
                self.processor.tile_height,
            )
        else:
            # Create placeholder for error state
            self.pixmap_item = None

    def _connect_grid_view_signals(self):
        """Connect all grid view signals."""
        self.grid_view.tile_clicked.connect(self._on_tile_clicked)
        self.grid_view.tiles_selected.connect(self._on_tiles_selected)
        self.grid_view.zoom_changed.connect(self._on_zoom_changed)
        self._update_zoom_level_display()

    def _create_actions_group(self, parent: QWidget) -> QGroupBox:
        """Create the actions group with buttons and zoom controls.

        Args:
            parent: Parent widget for the group

        Returns:
            QGroupBox: The configured actions group
        """
        actions_group = QGroupBox("Actions", parent)
        actions_layout = QHBoxLayout()

        # Add action buttons
        self._add_action_buttons(actions_layout)

        # Add separator
        actions_layout.addWidget(QLabel("|", self))

        # Add zoom controls
        self._add_zoom_controls(actions_layout)

        actions_group.setLayout(actions_layout)
        return actions_group

    def _add_action_buttons(self, layout: QHBoxLayout):
        """Add action buttons to the given layout.

        Args:
            layout: Layout to add buttons to
        """
        self.add_btn = QPushButton("Add Selection", self)
        _ = self.add_btn.clicked.connect(self._add_selection)
        layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("Remove Selection", self)
        _ = self.remove_btn.clicked.connect(self._remove_selection)
        layout.addWidget(self.remove_btn)

        self.create_group_btn = QPushButton("Create Group", self)
        _ = self.create_group_btn.clicked.connect(self._create_group)
        layout.addWidget(self.create_group_btn)

        self.clear_btn = QPushButton("Clear All", self)
        _ = self.clear_btn.clicked.connect(self._clear_arrangement)
        layout.addWidget(self.clear_btn)

    def _add_zoom_controls(self, layout: QHBoxLayout):
        """Add zoom control buttons to the given layout.

        Args:
            layout: Layout to add zoom controls to
        """
        self.zoom_out_btn = QPushButton("-", self)
        _ = self.zoom_out_btn.clicked.connect(self.grid_view.zoom_out)
        self.zoom_out_btn.setMaximumWidth(30)
        layout.addWidget(self.zoom_out_btn)

        self.zoom_level_label = QLabel("100%", self)
        self.zoom_level_label.setMinimumWidth(50)
        self.zoom_level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.zoom_level_label)

        self.zoom_in_btn = QPushButton("+", self)
        _ = self.zoom_in_btn.clicked.connect(self.grid_view.zoom_in)
        self.zoom_in_btn.setMaximumWidth(30)
        layout.addWidget(self.zoom_in_btn)

        self.zoom_fit_btn = QPushButton("Fit", self)
        _ = self.zoom_fit_btn.clicked.connect(self.grid_view.zoom_to_fit)
        self.zoom_fit_btn.setMaximumWidth(40)
        layout.addWidget(self.zoom_fit_btn)

        self.zoom_reset_btn = QPushButton("1:1", self)
        _ = self.zoom_reset_btn.clicked.connect(self.grid_view.reset_zoom)
        self.zoom_reset_btn.setMaximumWidth(40)
        layout.addWidget(self.zoom_reset_btn)

    def _create_arrangement_list_group(self, parent: QWidget) -> QGroupBox:
        """Create the arrangement list group.

        Args:
            parent: Parent widget for the group

        Returns:
            QGroupBox: The configured arrangement list group
        """
        list_group = QGroupBox("Current Arrangement", parent)
        list_layout = QVBoxLayout()

        self.arrangement_list: QListWidget = QListWidget(self)
        list_layout.addWidget(self.arrangement_list)

        list_group.setLayout(list_layout)
        return list_group

    def _create_preview_group(self, parent: QWidget) -> QGroupBox:
        """Create the preview group with scrollable area.

        Args:
            parent: Parent widget for the group

        Returns:
            QGroupBox: The configured preview group
        """
        preview_group = QGroupBox("Arrangement Preview", parent)
        preview_layout = QVBoxLayout()

        scroll_area = QScrollArea(self)
        self.preview_label = QLabel(self)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_area.setWidget(self.preview_label)
        scroll_area.setWidgetResizable(True)
        preview_layout.addWidget(scroll_area)

        preview_group.setLayout(preview_layout)
        return preview_group

    def _on_undo(self) -> None:
        """Handle undo shortcut."""
        description = self.undo_stack.undo()
        if description:
            self._update_displays()
            self._update_status(f"Undo: {description}")

    def _on_redo(self) -> None:
        """Handle redo shortcut."""
        description = self.undo_stack.redo()
        if description:
            self._update_displays()
            self._update_status(f"Redo: {description}")

    def _on_delete_selection(self) -> None:
        """Handle delete shortcut to clear selection."""
        if hasattr(self, "grid_view") and self.grid_view:
            self.grid_view.clear_selection()

    def _on_mode_changed(self, button: QRadioButton) -> None:
        """Handle selection mode change"""
        mode = button.property("mode")
        self.grid_view.set_selection_mode(mode)
        self._update_status(f"Selection mode: {mode.value}")

    def _on_tile_clicked(self, tile_pos: TilePosition) -> None:
        """Handle single tile click"""
        # In tile mode, immediately add/remove the tile
        if self.grid_view.selection_mode == SelectionMode.TILE:
            if self.arrangement_manager.is_tile_arranged(tile_pos):
                self.arrangement_manager.remove_tile(tile_pos)
            else:
                self.arrangement_manager.add_tile(tile_pos)

    def _on_tiles_selected(self, tiles: list[TilePosition]) -> None:
        """Handle tile selection"""
        self._update_status(f"Selected {len(tiles)} tiles")

    def _add_selection(self):
        """Add current selection to arrangement"""
        selection = list(self.grid_view.current_selection)

        if not selection:
            return

        if self.grid_view.selection_mode == SelectionMode.ROW:
            # Add as row - find tiles that aren't already arranged
            row = selection[0].row
            tiles_to_add = [
                TilePosition(row, col)
                for col in range(self.arrangement_manager.total_cols)
                if not self.arrangement_manager.is_tile_arranged(TilePosition(row, col))
            ]
            if tiles_to_add:
                command = AddRowTilesCommand(
                    manager=self.arrangement_manager,
                    row=row,
                    tiles_added=tiles_to_add,
                )
                self.undo_stack.push(command)

        elif self.grid_view.selection_mode == SelectionMode.COLUMN:
            # Add as column - find tiles that aren't already arranged
            col = selection[0].col
            tiles_to_add = [
                TilePosition(row, col)
                for row in range(self.arrangement_manager.total_rows)
                if not self.arrangement_manager.is_tile_arranged(TilePosition(row, col))
            ]
            if tiles_to_add:
                command = AddColumnTilesCommand(
                    manager=self.arrangement_manager,
                    col=col,
                    tiles_added=tiles_to_add,
                )
                self.undo_stack.push(command)

        else:
            # Add individual tiles - filter out already arranged ones
            tiles_to_add = [
                tile for tile in selection
                if not self.arrangement_manager.is_tile_arranged(tile)
            ]
            if tiles_to_add:
                command = AddMultipleTilesCommand(
                    manager=self.arrangement_manager,
                    tiles=tiles_to_add,
                )
                self.undo_stack.push(command)

        self.grid_view.clear_selection()

    def _remove_selection(self):
        """Remove current selection from arrangement"""
        selection = list(self.grid_view.current_selection)

        if not selection:
            return

        # Filter to only tiles that are arranged and not part of groups
        tiles_to_remove: list[tuple[TilePosition, int]] = []
        for tile in selection:
            if self.arrangement_manager.is_tile_arranged(tile):
                # Skip tiles that are part of groups (those need group removal)
                if self.arrangement_manager.get_tile_group(tile) is None:
                    position = self.arrangement_manager.get_tile_position(tile)
                    tiles_to_remove.append((tile, position))

        if tiles_to_remove:
            command = RemoveMultipleTilesCommand(
                manager=self.arrangement_manager,
                tiles_with_positions=tiles_to_remove,
            )
            self.undo_stack.push(command)

        self.grid_view.clear_selection()

    def _create_group(self):
        """Create a group from current selection"""
        selection = list(self.grid_view.current_selection)

        if len(selection) < 2:
            self._update_status("Select at least 2 tiles to create a group")
            return

        # Check if any tile is already arranged
        for tile in selection:
            if self.arrangement_manager.is_tile_arranged(tile):
                self._update_status("Some tiles are already arranged")
                return

        # Generate group ID
        group_id = f"group_{len(self.arrangement_manager.get_groups())}"
        group_name = f"Custom Group {len(self.arrangement_manager.get_groups()) + 1}"

        # Calculate bounding box
        min_row = min(t.row for t in selection)
        max_row = max(t.row for t in selection)
        min_col = min(t.col for t in selection)
        max_col = max(t.col for t in selection)

        width = max_col - min_col + 1
        height = max_row - min_row + 1

        # Create group
        group = TileGroup(
            id=group_id,
            tiles=selection,
            width=width,
            height=height,
            name=group_name,
        )

        command = AddGroupCommand(
            manager=self.arrangement_manager,
            group=group,
        )
        self.undo_stack.push(command)

        self._update_status(f"Created group with {len(selection)} tiles")
        self.grid_view.clear_selection()

    def _clear_arrangement(self):
        """Clear all arrangements"""
        if not self.arrangement_manager:
            return

        # Check if there's anything to clear
        if not self.arrangement_manager.get_arranged_tiles():
            self._update_status("Nothing to clear")
            return

        # Capture current state for undo
        tiles, groups, tile_to_group, order = self.arrangement_manager.get_state_snapshot()

        command = ClearGridCommand(
            manager=self.arrangement_manager,
            previous_tiles=tiles,
            previous_groups=groups,
            previous_tile_to_group=tile_to_group,
            previous_order=order,
        )
        self.undo_stack.push(command)

        self.grid_view.clear_selection()
        self._update_status("Cleared all arrangements")

    def _on_arrangement_changed(self):
        """Handle arrangement change"""
        self._update_displays()
        if self.export_btn:
            self.export_btn.setEnabled(self.arrangement_manager.get_arranged_count() > 0)

    def _on_palette_mode_changed(self, enabled: bool):
        """Handle palette mode change"""
        self._update_displays()

    def _update_displays(self):
        """Update all display elements"""
        # Update grid view highlights
        arranged_tiles = self.arrangement_manager.get_arranged_tiles()
        self.grid_view.highlight_arranged_tiles(arranged_tiles)

        # Update arrangement list
        self._update_arrangement_list()

        # Update preview
        self._update_preview()

    def _update_arrangement_list(self):
        """Update the arrangement list widget"""
        if self.arrangement_list:
            self.arrangement_list.clear()

        for arr_type, key in self.arrangement_manager.get_arrangement_order():
            if arr_type == ArrangementType.ROW:
                item_text = f"Row {key}"
            elif arr_type == ArrangementType.COLUMN:
                item_text = f"Column {key}"
            elif arr_type == ArrangementType.TILE:
                row, col = key.split(",")
                item_text = f"Tile ({row}, {col})"
            elif arr_type == ArrangementType.GROUP:
                group = self.arrangement_manager.get_groups().get(key)
                item_text = group.name if group else f"Group {key}"
            else:
                item_text = str(key)

            if self.arrangement_list and item_text:
                self.arrangement_list.addItem(item_text)

    def _update_preview(self):
        """Update the arrangement preview"""
        arranged_image = self.preview_generator.create_grid_arranged_image(
            self.processor, self.arrangement_manager, spacing=2
        )

        if arranged_image:
            pixmap = self._create_pixmap_from_image(arranged_image)
            # Scale for preview
            scaled = pixmap.scaled(
                pixmap.width() * 2,
                pixmap.height() * 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            if self.preview_label:
                self.preview_label.setPixmap(scaled)
        else:
            if self.preview_label:
                self.preview_label.clear()
            if self.preview_label:
                self.preview_label.setText("No arrangement")

    def _create_pixmap_from_image(self, image: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap"""
        if image.mode == "RGBA":
            qimage = QImage(
                image.tobytes(),
                image.width,
                image.height,
                image.width * 4,
                QImage.Format.Format_RGBA8888,
            )
        elif image.mode == "RGB":
            qimage = QImage(
                image.tobytes(),
                image.width,
                image.height,
                image.width * 3,
                QImage.Format.Format_RGB888,
            )
        elif image.mode == "L":
            qimage = QImage(
                image.tobytes(),
                image.width,
                image.height,
                image.width,
                QImage.Format.Format_Grayscale8,
            )
        elif image.mode == "P":
            # Convert palette mode to RGB
            rgb_image = image.convert("RGB")
            qimage = QImage(
                rgb_image.tobytes(),
                rgb_image.width,
                rgb_image.height,
                rgb_image.width * 3,
                QImage.Format.Format_RGB888,
            )
        else:
            # Fallback conversion
            rgb_image = image.convert("RGB")
            qimage = QImage(
                rgb_image.tobytes(),
                rgb_image.width,
                rgb_image.height,
                rgb_image.width * 3,
                QImage.Format.Format_RGB888,
            )

        return QPixmap.fromImage(qimage)

    def _export_arrangement(self):
        """Export the current arrangement"""
        if self.arrangement_manager.get_arranged_count() == 0:
            self._update_status("No tiles arranged for export")
            return

        # Check if we have valid data
        if self.original_image is None:
            self._update_status("Cannot export: No valid sprite data")
            return

        try:
            # Create arranged image
            arranged_image = self.preview_generator.create_grid_arranged_image(
                self.processor, self.arrangement_manager
            )

            if arranged_image:
                self.output_path = self.preview_generator.export_grid_arrangement(
                    self.sprite_path, arranged_image, "grid"
                )

                # Save arrangement data
                self.preview_generator.create_arrangement_preview_data(
                    self.arrangement_manager, self.processor
                )

                self._update_status(f"Exported to {Path(self.output_path).name}")
                self.accept()
            else:
                self._update_status("Error: Failed to create arranged image")

        except (OSError, ValueError, RuntimeError) as e:
            self._update_status(f"Export failed: {e!s}")
            _ = QMessageBox.warning(
                self, "Export Error", f"Failed to export arrangement:\n{e!s}"
            )

    def _update_status(self, message: str):
        """Update status bar message"""
        self.update_status(message)

    def _update_zoom_level_display(self):
        """Update the zoom level display"""
        if hasattr(self, "zoom_level_label"):
            zoom_percent = int(self.grid_view.get_zoom_level() * 100)
            if self.zoom_level_label:
                self.zoom_level_label.setText(f"{zoom_percent}%")

    def _on_zoom_changed(self, zoom_level: int):
        """Handle zoom level change"""
        self._update_zoom_level_display()

    @override
    def keyPressEvent(self, a0: QKeyEvent | None):
        """Handle keyboard shortcuts"""
        if not a0:
            return

        modifiers = a0.modifiers()
        key = a0.key()

        # Undo/Redo shortcuts
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_Z:
                self._on_undo()
                return
            elif key == Qt.Key.Key_Y:
                self._on_redo()
                return
        elif modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if key == Qt.Key.Key_Z:
                self._on_redo()
                return

        # Other shortcuts
        if key == Qt.Key.Key_G:
            # Toggle grid (already handled by view)
            pass
        elif key == Qt.Key.Key_C:
            # Toggle palette
            self.colorizer.toggle_palette_mode()
        elif key == Qt.Key.Key_P and self.colorizer.is_palette_mode():
            # Cycle palette
            self.colorizer.cycle_palette()
        elif key == Qt.Key.Key_Delete:
            # Remove selection
            self._remove_selection()
        elif key == Qt.Key.Key_Escape:
            # Clear selection
            self.grid_view.clear_selection()
        else:
            # Let the grid view handle zoom shortcuts
            self.grid_view.keyPressEvent(a0)
            self._update_zoom_level_display()
            super().keyPressEvent(a0)

    def set_palettes(self, palettes_dict: dict[int, Any]):  # pyright: ignore[reportExplicitAny] - palette data
        """Set available palettes for colorization"""
        self.colorizer.set_palettes(palettes_dict)
        self._update_displays()

    def get_arranged_path(self) -> str | None:
        """Get the path to the exported arrangement"""
        return self.output_path

    @override
    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Handle dialog close event with proper cleanup"""
        self._cleanup_resources()
        if a0:
            super().closeEvent(a0)

    def _disconnect_signals(self) -> None:
        """Disconnect all signals to prevent memory leaks."""
        disconnect_errors = (RuntimeError, TypeError, AttributeError)

        # Suppress RuntimeWarning from PySide6 when disconnecting signals with no connections
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*disconnect.*")

            # Disconnect arrangement manager signals
            if hasattr(self, "arrangement_manager") and self.arrangement_manager:
                try:
                    self.arrangement_manager.arrangement_changed.disconnect()
                except disconnect_errors:
                    pass

            # Disconnect colorizer signals
            if hasattr(self, "colorizer"):
                try:
                    self.colorizer.palette_mode_changed.disconnect()
                except disconnect_errors:
                    pass

            # Disconnect mode button signals
            if hasattr(self, "mode_buttons"):
                try:
                    self.mode_buttons.buttonClicked.disconnect()
                except disconnect_errors:
                    pass

            # Disconnect grid view signals
            if hasattr(self, "grid_view"):
                for signal_name in ("tile_clicked", "tiles_selected", "zoom_changed"):
                    try:
                        getattr(self.grid_view, signal_name).disconnect()
                    except disconnect_errors:
                        pass

            # Disconnect button signals
            for btn_name in ("add_btn", "remove_btn", "create_group_btn", "clear_btn",
                             "zoom_out_btn", "zoom_in_btn", "zoom_fit_btn", "zoom_reset_btn"):
                if hasattr(self, btn_name):
                    try:
                        getattr(self, btn_name).clicked.disconnect()
                    except disconnect_errors:
                        pass

    def _cleanup_resources(self) -> None:
        """Clean up resources to prevent memory leaks"""
        # Disconnect signals first
        self._disconnect_signals()

        # Clear colorizer cache
        if hasattr(self, "colorizer"):
            self.colorizer.clear_cache()

        # Clear graphics scene items
        if hasattr(self, "scene") and self.scene:
            self.scene.clear()

        # Clear grid view selections
        if hasattr(self, "grid_view"):
            self.grid_view.clear_selection()
            if hasattr(self.grid_view, "selection_rects"):
                self.grid_view.selection_rects.clear()

        # Clear processor data
        if hasattr(self, "processor"):
            self.processor.tiles.clear()
            self.processor.original_image = None

        # Clear arrangement manager
        if hasattr(self, "arrangement_manager") and self.arrangement_manager:
            self.arrangement_manager.clear()
