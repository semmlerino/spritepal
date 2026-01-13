"""
Grid Graphics View for SpritePal.

Interactive graphics view for grid-based sprite selection with zoom, pan,
marquee selection, and drag-and-drop support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

if TYPE_CHECKING:
    from ui.row_arrangement.grid_arrangement_manager import (
        GridArrangementManager,
        TilePosition,
    )

from PySide6.QtCore import QMimeData, QObject, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFocusEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsView,
    QWidget,
)


# Import TilePosition at runtime to avoid circular imports
def _make_tile_position(row: int, col: int) -> TilePosition:
    """Create a TilePosition-compatible object."""
    from ui.row_arrangement.grid_arrangement_manager import TilePosition

    return TilePosition(row, col)


class GridGraphicsView(QGraphicsView):
    """Custom graphics view for grid-based sprite selection"""

    # Signals
    tile_clicked = Signal(object)  # TilePosition
    tiles_selected = Signal(list)  # list[TilePosition]
    selection_completed = Signal()
    zoom_changed = Signal(float)  # Zoom level changed
    tiles_dropped = Signal(list, object, object, QObject)  # sources, source_anchor, target_anchor, drag_source

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.tile_width = 8
        self.tile_height = 8
        self.grid_cols = 0
        self.grid_rows = 0

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
        self.last_pan_point: QPoint | None = None

        # Marquee selection state
        self._marquee_start: QPointF | None = None
        self._marquee_rect: QGraphicsRectItem | None = None
        self._marquee_active = False
        self._drag_distance = 0
        self._last_mouse_pos: QPointF | None = None

        # Drag state
        self._drag_start_pos: QPoint | None = None
        self._drag_tile: TilePosition | None = None

        # Visual elements
        self.grid_lines: list[QGraphicsLineItem] = []
        self.selection_rects: dict[TilePosition, QGraphicsRectItem] = {}
        self.hover_rect: QGraphicsRectItem | None = None
        self.drop_placeholder: QGraphicsItem | None = None
        self.dimming_overlay: QGraphicsPathItem | None = None
        self.pixmap_item: QGraphicsPixmapItem | None = None  # Set by load_image

        # Colors
        self.grid_color = QColor(128, 128, 128, 64)
        self.selection_color = QColor(255, 255, 0, 128)
        self.hover_color = QColor(0, 255, 255, 64)
        self.arranged_color = QColor(0, 255, 0, 64)
        self.dim_color = QColor(0, 0, 0, 120)  # Semi-transparent black for dimming
        self.keyboard_focus_color = QColor(0, 0, 255, 128)  # Blue border for keyboard focus
        self.marquee_color = QColor(0, 120, 215, 40)  # Windows-style blue
        self.marquee_border_color = QColor(0, 120, 215)
        self.drop_target_color = QColor(255, 255, 255, 128)

        self.group_colors = [
            QColor(255, 0, 0, 64),
            QColor(0, 0, 255, 64),
            QColor(255, 128, 0, 64),
            QColor(128, 0, 255, 64),
        ]

        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        # Enable keyboard focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_grid_dimensions(self, cols: int, rows: int, tile_width: int, tile_height: int):
        """Set the grid dimensions"""
        self.grid_cols = cols
        self.grid_rows = rows
        self.tile_width = tile_width
        self.tile_height = tile_height
        self._update_grid_lines()

    def clear_selection(self):
        """Clear current selection"""
        if self.current_selection:
            self.current_selection.clear()
        scene = self.scene()
        if scene:
            for rect in self.selection_rects.values():
                scene.removeItem(rect)
            if self.drop_placeholder:
                scene.removeItem(self.drop_placeholder)
                self.drop_placeholder = None
            if self.dimming_overlay:
                scene.removeItem(self.dimming_overlay)
                self.dimming_overlay = None
        if self.selection_rects:
            self.selection_rects.clear()

    def highlight_arranged_tiles(
        self,
        tiles: list[TilePosition],
        color: QColor | None = None,
        manager: GridArrangementManager | None = None,
    ):
        """Highlight arranged tiles and show order indices"""
        if color is None:
            color = self.arranged_color

        scene = self.scene()
        if not scene:
            return

        # Track which tiles we've already processed to avoid duplicates
        processed_tiles = set(tiles)

        # Update dimming for unarranged tiles
        self.set_unarranged_opacity(list(processed_tiles))

        # Track which tiles we've already highlighted to avoid duplicate labels
        rendered_tiles: set[TilePosition] = set()

        for tile_pos in tiles:
            if tile_pos in rendered_tiles:
                continue
            rendered_tiles.add(tile_pos)

            if tile_pos not in self.selection_rects:
                rect = self._create_tile_rect(tile_pos, color)
                scene.addItem(rect)
                self.selection_rects[tile_pos] = rect

    def set_unarranged_opacity(self, arranged_tiles: list[TilePosition]):
        """Dim unarranged tiles to make arranged ones pop"""
        scene = self.scene()
        if not scene or not self.pixmap_item:
            return

        # Remove existing dimming
        if self.dimming_overlay:
            scene.removeItem(self.dimming_overlay)
            self.dimming_overlay = None

        if not arranged_tiles:
            return

        # Create a path that covers the whole grid minus the arranged tiles
        full_rect = QRectF(0, 0, self.grid_cols * self.tile_width, self.grid_rows * self.tile_height)
        path = QPainterPath()
        path.addRect(full_rect)

        # Subtract arranged tiles from the path
        for tile in arranged_tiles:
            tile_rect = QRectF(
                tile.col * self.tile_width, tile.row * self.tile_height, self.tile_width, self.tile_height
            )
            # Using addRect with OddEvenFill rule in a single path creates holes
            path.addRect(tile_rect)

        path.setFillRule(Qt.FillRule.OddEvenFill)

        self.dimming_overlay = QGraphicsPathItem(path)
        self.dimming_overlay.setBrush(QBrush(self.dim_color))
        self.dimming_overlay.setPen(Qt.PenStyle.NoPen)
        self.dimming_overlay.setZValue(5)  # Above pixmap, below selections
        scene.addItem(self.dimming_overlay)

    @override
    def mousePressEvent(self, event: QMouseEvent | None):
        """Handle mouse press"""
        if not event:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.pos())
            tile_pos = self._pos_to_tile(pos)

            # Check modifiers
            modifiers = event.modifiers()
            ctrl_pressed = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
            shift_pressed = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

            # Ctrl + Shift + Drag: Marquee selection
            if ctrl_pressed and shift_pressed:
                self._start_marquee_selection(pos)
                return

            # Handle tile interactions
            if tile_pos and self._is_valid_tile(tile_pos):
                if ctrl_pressed:
                    # Ctrl+click: Toggle tile in selection (add/remove)
                    if tile_pos in self.current_selection:
                        self.current_selection.discard(tile_pos)
                    else:
                        self.current_selection.add(tile_pos)
                    self._update_selection_display()
                    self.tiles_selected.emit(list(self.current_selection))
                    self.tile_clicked.emit(tile_pos)
                    # Don't start drag on toggle
                    return

                else:
                    # Normal click: Select single tile (if not already selected)
                    # If clicking on an already selected tile, keep selection to allow dragging multiple
                    if tile_pos not in self.current_selection:
                        self.current_selection.clear()
                        self.current_selection.add(tile_pos)
                        self._update_selection_display()
                        self.tiles_selected.emit(list(self.current_selection))
                    
                    self.tile_clicked.emit(tile_pos)

                    # Prepare for drag
                    self._drag_start_pos = event.pos()
                    self._drag_tile = tile_pos
                    return

            # Click on empty space
            if not ctrl_pressed and not shift_pressed:
                self.clear_selection()
            
            return

        elif event.button() == Qt.MouseButton.MiddleButton:
            # Middle mouse button for panning
            self.is_panning = True
            self.last_pan_point = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent | None):
        """Handle mouse move"""
        if not event:
            return

        if self.is_panning and self.last_pan_point is not None:
            # Pan the view
            delta = event.pos() - self.last_pan_point
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            if h_bar:
                h_bar.setValue(h_bar.value() - delta.x())
            if v_bar:
                v_bar.setValue(v_bar.value() - delta.y())
            self.last_pan_point = event.pos()
            return

        if self._marquee_active:
            # Update marquee selection during drag
            pos = self.mapToScene(event.pos())
            self._update_marquee_selection(pos)
            return

        # Check for drag start
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_start_pos is not None
            and (event.pos() - self._drag_start_pos).manhattanLength() > QApplication.startDragDistance()
        ):
            self._execute_drag()
            return

        pos = self.mapToScene(event.pos())
        tile_pos = self._pos_to_tile(pos)

        # Update hover
        if tile_pos and self._is_valid_tile(tile_pos):
            self._update_hover(tile_pos)

        super().mouseMoveEvent(event)

    def _execute_drag(self):
        """Execute a drag operation for tile reordering"""
        if self._drag_tile is None:
            return

        drag = QDrag(self)
        mime_data = QMimeData()

        # Determine tiles to drag
        drag_tiles = [self._drag_tile]
        if self._drag_tile in self.current_selection:
            drag_tiles = list(self.current_selection)

        # Serialize tiles: "anchor_r,anchor_c|r,c;r,c;..."
        anchor_str = f"{self._drag_tile.row},{self._drag_tile.col}"
        tiles_str = ";".join(f"{t.row},{t.col}" for t in drag_tiles)
        payload = f"{anchor_str}|{tiles_str}"

        mime_data.setText(payload)
        mime_data.setData("application/x-spritepal-tiles", payload.encode())

        drag.setMimeData(mime_data)

        # Create a pixmap for the drag cursor (visual feedback)
        # We'll create a composite pixmap of all dragged tiles

        # Calculate bounding box of dragged tiles
        min_r = min(t.row for t in drag_tiles)
        max_r = max(t.row for t in drag_tiles)
        min_c = min(t.col for t in drag_tiles)
        max_c = max(t.col for t in drag_tiles)

        width_tiles = max_c - min_c + 1
        height_tiles = max_r - min_r + 1

        pixmap = QPixmap(width_tiles * self.tile_width, height_tiles * self.tile_height)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)

        if self.pixmap_item:
            source_pixmap = self.pixmap_item.pixmap()
            for t in drag_tiles:
                # Source rect in pixmap
                src_rect = QRectF(t.col * self.tile_width, t.row * self.tile_height, self.tile_width, self.tile_height)
                # Target rect in drag pixmap
                dst_x = (t.col - min_c) * self.tile_width
                dst_y = (t.row - min_r) * self.tile_height
                dst_rect = QRectF(dst_x, dst_y, self.tile_width, self.tile_height)

                painter.drawPixmap(dst_rect, source_pixmap, src_rect)
        else:
            # Fallback if no source pixmap (e.g. empty canvas)
            # Draw placeholder rects
            painter.setBrush(QBrush(QColor(100, 100, 255, 128)))
            for t in drag_tiles:
                dst_x = (t.col - min_c) * self.tile_width
                dst_y = (t.row - min_r) * self.tile_height
                painter.drawRect(dst_x, dst_y, self.tile_width, self.tile_height)

        painter.end()

        # Scale if too large
        if pixmap.width() > 200 or pixmap.height() > 200:
            pixmap = pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio)

        drag.setPixmap(pixmap)

        # Hotspot should be relative to the anchor tile
        anchor_x = (self._drag_tile.col - min_c) * self.tile_width + self.tile_width // 2
        anchor_y = (self._drag_tile.row - min_r) * self.tile_height + self.tile_height // 2

        # Adjust hotspot for scaling if applied
        if pixmap.width() != width_tiles * self.tile_width:
            scale_x = pixmap.width() / (width_tiles * self.tile_width)
            scale_y = pixmap.height() / (height_tiles * self.tile_height)
            anchor_x *= scale_x
            anchor_y *= scale_y

        drag.setHotSpot(QPoint(int(anchor_x), int(anchor_y)))

        # Reset drag state
        self._marquee_active = False
        self._drag_tile = None

        drag.exec(Qt.DropAction.MoveAction)

    @override
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter"""
        if event.mimeData().hasFormat("application/x-spritepal-tiles"):
            event.acceptProposedAction()

    @override
    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Handle drag move with placeholder feedback"""
        if event.mimeData().hasFormat("application/x-spritepal-tiles"):
            event.acceptProposedAction()

            # Update drop placeholder
            pos = self.mapToScene(event.pos())
            target_tile = self._pos_to_tile(pos)

            scene = self.scene()
            if not scene:
                return

            if target_tile and self._is_valid_tile(target_tile):
                # Parse mime data to get relative offsets
                data = str(event.mimeData().data("application/x-spritepal-tiles").data(), encoding="utf-8")
                anchor_str, tiles_str = data.split("|")
                ar, ac = map(int, anchor_str.split(","))
                anchor = _make_tile_position(ar, ac)

                tiles = []
                for t_str in tiles_str.split(";"):
                    r, c = map(int, t_str.split(","))
                    tiles.append(_make_tile_position(r, c))

                # Calculate placeholder shape
                path = QPainterPath()
                for t in tiles:
                    # Calculate target position for this tile
                    # offset from anchor
                    dr = t.row - anchor.row
                    dc = t.col - anchor.col

                    target_r = target_tile.row + dr
                    target_c = target_tile.col + dc

                    # Add rect if within bounds
                    if 0 <= target_r < self.grid_rows and 0 <= target_c < self.grid_cols:
                        x = target_c * self.tile_width
                        y = target_r * self.tile_height
                        path.addRect(QRectF(x, y, self.tile_width, self.tile_height))

                if self.drop_placeholder is None:
                    self.drop_placeholder = QGraphicsPathItem()
                    self.drop_placeholder.setPen(QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.DashLine))
                    self.drop_placeholder.setBrush(QBrush(self.drop_target_color))
                    self.drop_placeholder.setZValue(100)
                    scene.addItem(self.drop_placeholder)

                if isinstance(self.drop_placeholder, QGraphicsPathItem):
                    self.drop_placeholder.setPath(path)

            elif self.drop_placeholder:
                scene.removeItem(self.drop_placeholder)
                self.drop_placeholder = None

    @override
    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        """Clean up placeholder when drag leaves"""
        if self.drop_placeholder:
            scene = self.scene()
            if scene:
                scene.removeItem(self.drop_placeholder)
            self.drop_placeholder = None
        super().dragLeaveEvent(event)

    @override
    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop for reordering and insertion"""
        if self.drop_placeholder:
            scene = self.scene()
            if scene:
                scene.removeItem(self.drop_placeholder)
            self.drop_placeholder = None

        if event.mimeData().hasFormat("application/x-spritepal-tiles"):
            pos = self.mapToScene(event.pos())
            target_tile = self._pos_to_tile(pos)

            if target_tile and self._is_valid_tile(target_tile):
                data = str(event.mimeData().data("application/x-spritepal-tiles").data(), encoding="utf-8")
                anchor_str, tiles_str = data.split("|")
                # We don't need anchor here if we pass the whole list and target
                # But for reordering logic in dialog, knowing the structure matters.
                # Let's pass the source tiles list and the target anchor position.

                source_tiles = []
                for t_str in tiles_str.split(";"):
                    r, c = map(int, t_str.split(","))
                    source_tiles.append(_make_tile_position(r, c))

                # Also pass the anchor from the source
                ar, ac = map(int, anchor_str.split(","))
                anchor = _make_tile_position(ar, ac)

                self.tiles_dropped.emit(source_tiles, anchor, target_tile, event.source())
                event.acceptProposedAction()

    @override
    def wheelEvent(self, event: QWheelEvent | None):
        """Handle mouse wheel for zooming (no modifier required)"""
        if event:
            delta = event.angleDelta().y()
            if delta == 0:
                return
            # Always zoom on wheel - standard graphics editor behavior
            zoom_factor = 1.15 if delta > 0 else 1.0 / 1.15
            self._zoom_at_point(event.position().toPoint(), zoom_factor)
            event.accept()

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
            self._set_keyboard_focus(_make_tile_position(0, 0))
        elif a0.key() == Qt.Key.Key_End:
            # Go to last tile
            if self.grid_rows > 0 and self.grid_cols > 0:
                self._set_keyboard_focus(_make_tile_position(self.grid_rows - 1, self.grid_cols - 1))

        # Page Up/Down for larger movements
        elif a0.key() == Qt.Key.Key_PageUp:
            if self.keyboard_focus_pos:
                new_row = max(0, self.keyboard_focus_pos.row - 5)
                self._set_keyboard_focus(_make_tile_position(new_row, self.keyboard_focus_pos.col))
        elif a0.key() == Qt.Key.Key_PageDown:
            if self.keyboard_focus_pos:
                new_row = min(self.grid_rows - 1, self.keyboard_focus_pos.row + 5)
                self._set_keyboard_focus(_make_tile_position(new_row, self.keyboard_focus_pos.col))

        # Escape to clear selection
        elif a0.key() == Qt.Key.Key_Escape:
            self.clear_selection()
            self._clear_keyboard_focus()

        else:
            super().keyPressEvent(a0)

    def _zoom_at_point(self, point: Any, zoom_factor: float) -> None:  # pyright: ignore[reportExplicitAny]
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
                h_bar.setValue(h_bar.value() - delta.x())
            if v_bar:
                v_bar.setValue(v_bar.value() - delta.y())

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
                self.fitInView(scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

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
            if self._marquee_active:
                # Finish marquee selection
                # Shift held = add to existing selection
                add_to = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                pos = self.mapToScene(event.pos())
                self._finish_marquee_selection(pos, add_to)
                return

            # Clear drag state if drag didn't trigger
            self._drag_tile = None
            self._drag_start_pos = None

        if event and event.button() == Qt.MouseButton.MiddleButton and self.is_panning:
            self.is_panning = False
            self.last_pan_point = None
            self.setCursor(Qt.CursorShape.CrossCursor)

        if event:
            super().mouseReleaseEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # Marquee selection methods
    # ─────────────────────────────────────────────────────────────────────────

    def _start_marquee_selection(self, pos: QPointF) -> None:
        """Begin marquee selection at scene position."""
        self._marquee_start = pos
        self._marquee_active = True
        self._drag_distance = 0
        self._last_mouse_pos = pos
        # Don't create visual rect yet - wait for drag threshold

    def _update_marquee_selection(self, current_pos: QPointF) -> None:
        """Update marquee rect during drag."""
        if self._marquee_start is None or self._last_mouse_pos is None:
            return

        # Track drag distance
        delta = current_pos - self._last_mouse_pos
        self._drag_distance += abs(delta.x()) + abs(delta.y())
        self._last_mouse_pos = current_pos

        # Only show marquee after threshold (5 scene units)
        if self._drag_distance < 5:
            return

        scene = self.scene()
        if not scene:
            return

        # Create marquee rect if not exists
        if self._marquee_rect is None:
            self._marquee_rect = scene.addRect(
                self._marquee_start.x(),
                self._marquee_start.y(),
                0,
                0,
                QPen(self.marquee_border_color, 1, Qt.PenStyle.DashLine),
                QBrush(self.marquee_color),
            )
            self._marquee_rect.setZValue(1000)  # Above tiles

        # Update rect geometry
        x = min(self._marquee_start.x(), current_pos.x())
        y = min(self._marquee_start.y(), current_pos.y())
        w = abs(current_pos.x() - self._marquee_start.x())
        h = abs(current_pos.y() - self._marquee_start.y())
        self._marquee_rect.setRect(x, y, w, h)

        # Preview selection (highlight tiles in marquee)
        self._preview_marquee_selection(QRectF(x, y, w, h))

    def _preview_marquee_selection(self, rect: QRectF) -> None:
        """Preview tiles that would be selected by current marquee."""
        # Calculate tiles in rect
        tiles = self._get_tiles_in_rect(rect)
        # Update visual selection preview
        self.current_selection = tiles
        self._update_selection_display()

    def _finish_marquee_selection(self, end_pos: QPointF, add_to_existing: bool = False) -> None:
        """Complete marquee selection."""
        if self._marquee_start is None:
            self._cleanup_marquee()
            return

        # If no significant drag, treat as single click
        if self._drag_distance < 5:
            tile_pos = self._pos_to_tile(end_pos)
            if tile_pos and self._is_valid_tile(tile_pos):
                if not add_to_existing:
                    self.current_selection.clear()
                self.current_selection.add(tile_pos)
                self._update_selection_display()
                self.tiles_selected.emit(list(self.current_selection))
                self.tile_clicked.emit(tile_pos)
            self._cleanup_marquee()
            return

        # Calculate selected tiles from marquee rect
        x = min(self._marquee_start.x(), end_pos.x())
        y = min(self._marquee_start.y(), end_pos.y())
        w = abs(end_pos.x() - self._marquee_start.x())
        h = abs(end_pos.y() - self._marquee_start.y())
        selected = self._get_tiles_in_rect(QRectF(x, y, w, h))

        # Update selection
        if add_to_existing:
            self.current_selection.update(selected)
        else:
            self.current_selection = selected

        self._update_selection_display()
        self.tiles_selected.emit(list(self.current_selection))
        if self.current_selection:
            self.selection_completed.emit()

        self._cleanup_marquee()

    def _get_tiles_in_rect(self, rect: QRectF) -> set[TilePosition]:
        """Get all tiles intersecting the given scene rect."""
        tiles: set[TilePosition] = set()

        # Convert scene coords to tile coords
        start_col = max(0, int(rect.x() / self.tile_width))
        start_row = max(0, int(rect.y() / self.tile_height))
        end_col = min(self.grid_cols - 1, int((rect.x() + rect.width()) / self.tile_width))
        end_row = min(self.grid_rows - 1, int((rect.y() + rect.height()) / self.tile_height))

        for row in range(start_row, end_row + 1):
            for col in range(start_col, end_col + 1):
                tiles.add(_make_tile_position(row, col))

        return tiles

    def _cleanup_marquee(self) -> None:
        """Clean up marquee visual and state."""
        if self._marquee_rect is not None:
            scene = self.scene()
            if scene and self._marquee_rect.scene():
                scene.removeItem(self._marquee_rect)
            self._marquee_rect = None
        self._marquee_start = None
        self._marquee_active = False
        self._drag_distance = 0
        self._last_mouse_pos = None

    def _pos_to_tile(self, pos: QPointF) -> TilePosition | None:
        """Convert scene position to tile position"""
        if pos.x() < 0 or pos.y() < 0:
            return None

        col = int(pos.x() // self.tile_width)
        row = int(pos.y() // self.tile_height)

        return _make_tile_position(row, col)

    def _is_valid_tile(self, tile_pos: TilePosition) -> bool:
        """Check if tile position is valid"""
        return 0 <= tile_pos.row < self.grid_rows and 0 <= tile_pos.col < self.grid_cols

    def _create_tile_rect(self, tile_pos: TilePosition, color: QColor) -> QGraphicsRectItem:
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
            self._set_keyboard_focus(_make_tile_position(0, 0))
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

        new_pos = _make_tile_position(row, col)

        # Handle selection extension with Shift
        if shift_pressed:
            # Extend selection from start position to new position
            if not self.selection_start:
                self.selection_start = self.keyboard_focus_pos

            # Select rectangle from start to new position
            min_row = min(self.selection_start.row, new_pos.row)
            max_row = max(self.selection_start.row, new_pos.row)
            min_col = min(self.selection_start.col, new_pos.col)
            max_col = max(self.selection_start.col, new_pos.col)

            self.current_selection = {
                _make_tile_position(r, c) for r in range(min_row, max_row + 1) for c in range(min_col, max_col + 1)
            }

            self._update_selection_display()
            self.tiles_selected.emit(list(self.current_selection))
        else:
            # Reset selection start if shift not pressed
            self.selection_start = None

        # Move focus to new position
        self._set_keyboard_focus(new_pos)

    def _handle_tile_selection_key(self):
        """Handle Space/Enter key for tile selection"""
        if not self.keyboard_focus_pos:
            return

        # Emit tile clicked signal
        self.tile_clicked.emit(self.keyboard_focus_pos)

        # Toggle selection
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

        self.keyboard_focus_rect = QGraphicsRectItem(x, y, self.tile_width, self.tile_height)
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

    @override
    def focusInEvent(self, event: QFocusEvent | None) -> None:
        """Handle focus in event"""
        if event:
            super().focusInEvent(event)

        # If no keyboard focus set, initialize at (0,0)
        if not self.keyboard_focus_pos and self.grid_rows > 0 and self.grid_cols > 0:
            self._set_keyboard_focus(_make_tile_position(0, 0))

    @override
    def focusOutEvent(self, event: QFocusEvent | None) -> None:
        """Handle focus out event"""
        if event:
            super().focusOutEvent(event)

        # Keep focus indicator visible but maybe dim it
        # This allows users to see where they were when returning focus

    def update_grid(self):
        """Public method to refresh the grid line display"""
        self._update_grid_lines()

    def _update_grid_lines(self):
        """Update grid line display"""
        # Clear existing grid lines
        scene = self.scene()
        if scene:
            for line in self.grid_lines:
                try:
                    if line.scene():
                        scene.removeItem(line)
                except RuntimeError:
                    # Item already deleted (e.g. by scene clear)
                    pass
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

    def _update_rectangle_selection(self, start: TilePosition, end: TilePosition):
        """Update rectangle selection"""
        min_row = min(start.row, end.row)
        max_row = max(start.row, end.row)
        min_col = min(start.col, end.col)
        max_col = max(start.col, end.col)

        self.current_selection = {
            _make_tile_position(row, col) for row in range(min_row, max_row + 1) for col in range(min_col, max_col + 1)
        }
        self._update_selection_display()

    def _update_selection_display(self):
        """Update visual display of selection"""
        # Clear existing selection rects
        scene = self.scene()
        if scene:
            for rect in self.selection_rects.values():
                try:
                    if rect.scene():
                        scene.removeItem(rect)
                except RuntimeError:
                    # Item already deleted (e.g. by scene clear)
                    pass
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
            try:
                if self.hover_rect.scene() and scene:
                    scene.removeItem(self.hover_rect)
            except RuntimeError:
                # Item already deleted (e.g. by scene clear)
                pass
            self.hover_rect = None

        if tile_pos not in self.current_selection and scene:
            try:
                self.hover_rect = self._create_tile_rect(tile_pos, self.hover_color)
                self.hover_rect.setZValue(0.5)  # Below selection
                scene.addItem(self.hover_rect)
            except RuntimeError:
                # Scene might be in an inconsistent state during clear
                self.hover_rect = None


__all__ = ["GridGraphicsView"]
