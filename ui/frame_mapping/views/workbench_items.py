"""QGraphicsItem subclasses for the Workbench Canvas.

This module provides specialized graphics items for the interactive
sprite alignment canvas:

- AIFrameItem: Draggable/scalable overlay for the AI frame
- ScaleHandle: Corner handles for uniform scaling
- TileOverlayItem: Displays OAM tile boundaries with touch status
- GridOverlayItem: Optional reference grid (8x8 or 16x16)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import override

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class TileMetadata:
    """Metadata for a single tile in the overlay.

    Attributes:
        rect: The display rectangle for the tile.
        rom_offset: Optional ROM file offset for the tile data.
    """

    rect: QRectF
    rom_offset: int | None = None


# Scale handle size in pixels
HANDLE_SIZE = 12
HANDLE_HALF = HANDLE_SIZE // 2


class ScaleHandle(QGraphicsRectItem):
    """Corner handle for scaling the AI frame.

    Dragging this handle scales the parent AI frame uniformly from center.
    """

    def __init__(
        self,
        corner: str,
        parent: AIFrameItem,
    ) -> None:
        """Initialize a scale handle.

        Args:
            corner: Which corner ("tl", "tr", "bl", "br").
            parent: Parent AIFrameItem.
        """
        super().__init__(-HANDLE_HALF, -HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE, parent)
        self._corner = corner
        self._ai_frame = parent
        self._drag_start_pos: QPointF | None = None
        self._drag_start_scale: float = 1.0

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setAcceptHoverEvents(True)

        self.setBrush(QBrush(QColor(100, 200, 255, 200)))
        self.setPen(QPen(QColor(50, 150, 200), 1))
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if corner in ("tl", "br") else Qt.CursorShape.SizeBDiagCursor)

    def update_position(self) -> None:
        """Update handle position based on parent bounds."""
        bounds = self._ai_frame.boundingRect()
        if self._corner == "tl":
            self.setPos(bounds.topLeft())
        elif self._corner == "tr":
            self.setPos(bounds.topRight())
        elif self._corner == "bl":
            self.setPos(bounds.bottomLeft())
        elif self._corner == "br":
            self.setPos(bounds.bottomRight())

    @override
    def mousePressEvent(self, event: object) -> None:
        """Start scale drag."""
        from PySide6.QtWidgets import QGraphicsSceneMouseEvent

        if isinstance(event, QGraphicsSceneMouseEvent):
            self._drag_start_pos = event.scenePos()
            self._drag_start_scale = self._ai_frame.scale_factor()
            # Set parent drag state for performance optimization
            pos = self._ai_frame.pos()
            self._ai_frame.start_drag(int(pos.x()), int(pos.y()), self._drag_start_scale)
            event.accept()

    @override
    def mouseMoveEvent(self, event: object) -> None:
        """Handle scale drag, preserving center position."""
        from PySide6.QtWidgets import QGraphicsSceneMouseEvent

        if isinstance(event, QGraphicsSceneMouseEvent) and self._drag_start_pos is not None:
            current_pos = event.scenePos()
            center = self._ai_frame.sceneBoundingRect().center()

            # Calculate distance from center
            start_dist = (self._drag_start_pos - center).manhattanLength()
            current_dist = (current_pos - center).manhattanLength()

            if start_dist > 0:
                scale_factor = current_dist / start_dist
                new_scale = self._drag_start_scale * scale_factor
                # Clamp scale
                new_scale = max(0.1, min(1.0, new_scale))

                # Capture center before scaling
                center_before = self._ai_frame.sceneBoundingRect().center()

                # Apply scale
                self._ai_frame.set_scale_factor(new_scale)

                # Reposition to preserve center
                center_after = self._ai_frame.sceneBoundingRect().center()
                delta = center_before - center_after
                self._ai_frame.setPos(self._ai_frame.pos() + delta)

            event.accept()

    @override
    def mouseReleaseEvent(self, event: object) -> None:
        """End scale drag."""
        from PySide6.QtWidgets import QGraphicsSceneMouseEvent

        if isinstance(event, QGraphicsSceneMouseEvent):
            self._drag_start_pos = None
            # End parent drag state
            self._ai_frame.end_drag()
            event.accept()

    @override
    def hoverEnterEvent(self, event: object) -> None:
        """Highlight on hover."""
        self.setBrush(QBrush(QColor(150, 220, 255, 230)))

    @override
    def hoverLeaveEvent(self, event: object) -> None:
        """Remove highlight."""
        self.setBrush(QBrush(QColor(100, 200, 255, 200)))


class AIFrameItem(QGraphicsObject):
    """Draggable and scalable AI frame overlay.

    This item displays the AI frame image and supports:
    - Drag to translate (update offset_x, offset_y)
    - Corner handles for uniform scaling from center
    - Keyboard nudge (arrow keys)

    Signals:
        transform_changed: Emitted when position or scale changes.
            Args: (offset_x: int, offset_y: int, scale: float)
        drag_started: Emitted when a drag operation begins.
        drag_finished: Emitted when a drag operation ends.
    """

    transform_changed = Signal(int, int, float)  # offset_x, offset_y, scale
    drag_started = Signal()
    drag_finished = Signal()

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._scale_factor = 1.0
        self._flip_h = False
        self._flip_v = False
        self._opacity = 0.7
        self._ghost_mode = False

        # Drag state tracking for performance optimization
        self._is_dragging = False
        self._drag_start_alignment: tuple[int, int, float] | None = None  # (x, y, scale)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setAcceptHoverEvents(True)

        # Create scale handles
        self._handles: list[ScaleHandle] = []
        for corner in ("tl", "tr", "bl", "br"):
            handle = ScaleHandle(corner, self)
            handle.setVisible(False)
            self._handles.append(handle)

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        """Set the AI frame pixmap."""
        self.prepareGeometryChange()
        self._pixmap = pixmap
        self._update_handles()
        self.update()

    def set_scale_factor(self, scale: float) -> None:
        """Set the uniform scale factor."""
        scale = max(0.01, min(1.0, scale))
        if abs(scale - self._scale_factor) > 0.001:
            self.prepareGeometryChange()
            self._scale_factor = scale
            self._update_handles()
            self.update()
            self._emit_transform()

    def scale_factor(self) -> float:
        """Get the current scale factor."""
        return self._scale_factor

    def set_flip(self, flip_h: bool, flip_v: bool) -> None:
        """Set horizontal and vertical flip."""
        if self._flip_h != flip_h or self._flip_v != flip_v:
            self._flip_h = flip_h
            self._flip_v = flip_v
            self.update()

    def set_overlay_opacity(self, opacity: float) -> None:
        """Set overlay opacity (0.0 to 1.0)."""
        self._opacity = max(0.0, min(1.0, opacity))
        self.update()

    def set_ghost_mode(self, enabled: bool) -> None:
        """Enable ghost mode (outline only) for preview."""
        self._ghost_mode = enabled
        self.update()

    def show_handles(self, visible: bool) -> None:
        """Show or hide scale handles."""
        for handle in self._handles:
            handle.setVisible(visible)

    def _update_handles(self) -> None:
        """Update handle positions."""
        for handle in self._handles:
            handle.update_position()

    @property
    def is_dragging(self) -> bool:
        """Return True if a drag operation is in progress."""
        return self._is_dragging

    def get_drag_start_alignment(self) -> tuple[int, int, float] | None:
        """Return alignment at drag start, or None if not dragging."""
        return self._drag_start_alignment

    def start_drag(self, start_x: int, start_y: int, start_scale: float) -> None:
        """Mark drag operation as started (called by ScaleHandle too).

        Args:
            start_x: X offset at drag start
            start_y: Y offset at drag start
            start_scale: Scale at drag start
        """
        if not self._is_dragging:
            self._is_dragging = True
            self._drag_start_alignment = (start_x, start_y, start_scale)
            self.drag_started.emit()

    def end_drag(self) -> None:
        """Mark drag operation as ended (called by ScaleHandle too)."""
        if self._is_dragging:
            self._is_dragging = False
            self.drag_finished.emit()
            self._drag_start_alignment = None

    @override
    def mousePressEvent(self, event: object) -> None:
        """Start drag tracking on mouse press."""
        from PySide6.QtWidgets import QGraphicsSceneMouseEvent

        if isinstance(event, QGraphicsSceneMouseEvent):
            pos = self.pos()
            self.start_drag(int(pos.x()), int(pos.y()), self._scale_factor)
            super().mousePressEvent(event)

    @override
    def mouseReleaseEvent(self, event: object) -> None:
        """End drag tracking on mouse release."""
        from PySide6.QtWidgets import QGraphicsSceneMouseEvent

        if isinstance(event, QGraphicsSceneMouseEvent):
            self.end_drag()
            super().mouseReleaseEvent(event)

    def _emit_transform(self) -> None:
        """Emit transform_changed signal with current values."""
        pos = self.pos()
        self.transform_changed.emit(int(pos.x()), int(pos.y()), self._scale_factor)

    @override
    def boundingRect(self) -> QRectF:
        """Return bounding rectangle."""
        if self._pixmap is None:
            return QRectF(0, 0, 64, 64)

        w = self._pixmap.width() * self._scale_factor
        h = self._pixmap.height() * self._scale_factor
        return QRectF(0, 0, w, h)

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the AI frame."""
        if self._pixmap is None:
            return

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        target_rect = self.boundingRect()

        if self._ghost_mode:
            # Ghost mode: no visible rendering (preview mode)
            pass
        else:
            # Normal rendering
            painter.setOpacity(self._opacity)

            # Apply flip transform
            pixmap = self._pixmap
            if self._flip_h or self._flip_v:
                transform = QTransform()
                transform.scale(-1 if self._flip_h else 1, -1 if self._flip_v else 1)
                pixmap = pixmap.transformed(transform)

            # Scale and draw
            painter.drawPixmap(target_rect.toRect(), pixmap)

        painter.setOpacity(1.0)

        # Draw selection border if selected
        if self.isSelected():
            painter.setPen(QPen(QColor(100, 200, 255), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(target_rect)

    @override
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        """Handle item changes."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._emit_transform()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.show_handles(bool(value))
            if value:  # When selected, take focus to receive key events
                self.setFocus()
        return super().itemChange(change, value)

    @override
    def keyPressEvent(self, event: object) -> None:
        """Handle arrow keys for nudging and +/- for scaling."""
        from PySide6.QtGui import QKeyEvent

        if isinstance(event, QKeyEvent):
            shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            nudge_step = 8 if shift_held else 1
            scale_step = 0.05 if shift_held else 0.01  # 5% with Shift, 1% without
            key = event.key()

            if key == Qt.Key.Key_Left:
                self.moveBy(-nudge_step, 0)
                event.accept()
            elif key == Qt.Key.Key_Right:
                self.moveBy(nudge_step, 0)
                event.accept()
            elif key == Qt.Key.Key_Up:
                self.moveBy(0, -nudge_step)
                event.accept()
            elif key == Qt.Key.Key_Down:
                self.moveBy(0, nudge_step)
                event.accept()
            elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                # Scale up (1% default, 5% with Shift)
                self._adjust_scale(scale_step)
                event.accept()
            elif key == Qt.Key.Key_Minus:
                # Scale down (1% default, 5% with Shift)
                self._adjust_scale(-scale_step)
                event.accept()
            elif key == Qt.Key.Key_Escape:
                # Cancel drag and restore original position
                if self._is_dragging and self._drag_start_alignment is not None:
                    start_x, start_y, start_scale = self._drag_start_alignment
                    self.setPos(start_x, start_y)
                    self.set_scale_factor(start_scale)
                    self.end_drag()
                    logger.debug("Drag cancelled via Escape, restored to: %s", self._drag_start_alignment)
                event.accept()
            else:
                event.ignore()

    def _adjust_scale(self, delta: float) -> None:
        """Adjust scale by delta, preserving center position.

        Args:
            delta: Scale change (e.g., 0.05 for +5%, -0.05 for -5%)
        """
        new_scale = self._scale_factor + delta
        new_scale = max(0.01, min(1.0, new_scale))

        if abs(new_scale - self._scale_factor) < 0.001:
            return

        # Capture center before scaling
        center_before = self.sceneBoundingRect().center()

        # Apply scale
        self.set_scale_factor(new_scale)

        # Reposition to preserve center
        center_after = self.sceneBoundingRect().center()
        delta_pos = center_before - center_after
        self.setPos(self.pos() + delta_pos)


class TileOverlayItem(QGraphicsItem):
    """Displays OAM tile boundaries with touched/untouched status.

    Shows the actual tile positions from the Mesen capture,
    color-coded by whether the AI frame covers them:
    - Green: Touched (AI frame fully covers)
    - Gray: Untouched (not covered or partially covered)

    Optionally displays ROM offset addresses on each tile.
    """

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._tiles: list[TileMetadata] = []
        self._touched_indices: set[int] = set()
        self._visible = True
        self._show_addresses = False
        self._bounds = QRectF(0, 0, 64, 64)
        self._selected_index: int | None = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def set_tiles(self, tiles: list[TileMetadata]) -> None:
        """Set the tile metadata list.

        Args:
            tiles: List of TileMetadata with rectangles and optional ROM offsets.
        """
        self.prepareGeometryChange()
        self._tiles = tiles
        self._update_bounds()
        self.update()

    def set_tile_rects(self, rects: list[QRectF]) -> None:
        """Set the OAM tile rectangles (backward compatibility).

        Args:
            rects: List of QRectF tile rectangles.
        """
        tiles = [TileMetadata(rect=r) for r in rects]
        self.set_tiles(tiles)

    def set_touched_indices(self, indices: set[int]) -> None:
        """Set which tiles are touched by the overlay."""
        self._touched_indices = indices
        self.update()

    def set_overlay_visible(self, visible: bool) -> None:
        """Show or hide the tile overlay."""
        self._visible = visible
        self.update()

    def set_show_addresses(self, visible: bool) -> None:
        """Show or hide tile address text."""
        self._show_addresses = visible
        self.update()

    def set_selected_tile(self, index: int | None) -> None:
        """Set the selected tile index for highlighting."""
        if self._selected_index != index:
            self._selected_index = index
            self.update()

    def get_tile_at_point(self, pos: QPointF) -> int | None:
        """Get tile index at scene position, or None if outside all tiles."""
        for i, tile in enumerate(self._tiles):
            if tile.rect.contains(pos):
                return i
        return None

    def get_tile_rom_offset(self, index: int) -> int | None:
        """Get ROM offset for tile by index."""
        if 0 <= index < len(self._tiles):
            return self._tiles[index].rom_offset
        return None

    def _update_bounds(self) -> None:
        """Update bounding rect from tile rects."""
        if not self._tiles:
            self._bounds = QRectF(0, 0, 64, 64)
            return

        min_x = min(t.rect.x() for t in self._tiles)
        min_y = min(t.rect.y() for t in self._tiles)
        max_x = max(t.rect.right() for t in self._tiles)
        max_y = max(t.rect.bottom() for t in self._tiles)
        self._bounds = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    @override
    def boundingRect(self) -> QRectF:
        """Return bounding rectangle."""
        return self._bounds

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint tile boundaries and optional address text."""
        if not self._visible or not self._tiles:
            return

        touched_color = QColor(100, 200, 100, 80)
        touched_border = QColor(100, 200, 100, 180)
        untouched_color = QColor(150, 150, 150, 60)
        untouched_border = QColor(150, 150, 150, 150)

        for i, tile in enumerate(self._tiles):
            rect = tile.rect
            if i in self._touched_indices:
                painter.setBrush(QBrush(touched_color))
                painter.setPen(QPen(touched_border, 1))
            else:
                painter.setBrush(QBrush(untouched_color))
                painter.setPen(QPen(untouched_border, 1))
            painter.drawRect(rect)

            # Draw selection highlight if this tile is selected
            if self._selected_index == i:
                painter.setPen(QPen(QColor(0, 200, 255), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect.adjusted(1, 1, -1, -1))

            # Draw address text if enabled and available
            if self._show_addresses and tile.rom_offset is not None:
                # Format: abbreviated hex (e.g., "1B0" for 0x1B0000)
                text = f"{tile.rom_offset >> 8:X}"
                painter.setFont(QFont("Monospace", 7))
                painter.setPen(Qt.GlobalColor.white)
                # Draw with slight offset from top-left corner
                painter.drawText(
                    rect.adjusted(1, 1, 0, 0),
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                    text,
                )


class ClippingOverlayItem(QGraphicsItem):
    """Shows regions of AI frame that are outside tile injection area.

    Displays semi-transparent red overlays on parts of the AI frame
    content that extend beyond the game sprite's tile boundaries.
    These regions will be clipped (not injected) during ROM injection.
    """

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._clipped_rects: list[QRectF] = []
        self._visible = True
        self._bounds = QRectF(0, 0, 0, 0)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        # Render above tile overlay but below grid
        self.setZValue(50)

    def set_clipped_rects(self, rects: list[QRectF]) -> None:
        """Set the rectangles showing clipped content regions.

        Args:
            rects: List of QRectF in scene coordinates showing overflow areas.
        """
        self.prepareGeometryChange()
        self._clipped_rects = rects
        self._update_bounds()
        self.update()

    def set_overlay_visible(self, visible: bool) -> None:
        """Show or hide the clipping overlay."""
        self._visible = visible
        self.update()

    def _update_bounds(self) -> None:
        """Update bounding rect from clipped rects."""
        if not self._clipped_rects:
            self._bounds = QRectF(0, 0, 0, 0)
            return

        min_x = min(r.x() for r in self._clipped_rects)
        min_y = min(r.y() for r in self._clipped_rects)
        max_x = max(r.right() for r in self._clipped_rects)
        max_y = max(r.bottom() for r in self._clipped_rects)
        self._bounds = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    @override
    def boundingRect(self) -> QRectF:
        """Return bounding rectangle."""
        return self._bounds

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint clipped region overlays."""
        if not self._visible or not self._clipped_rects:
            return

        # Semi-transparent red fill with red dashed border
        fill_color = QColor(220, 53, 69, 77)  # rgba(220, 53, 69, 0.3)
        border_color = QColor(220, 53, 69, 200)

        painter.setBrush(QBrush(fill_color))
        pen = QPen(border_color, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)

        for rect in self._clipped_rects:
            painter.drawRect(rect)


class GridOverlayItem(QGraphicsItem):
    """Optional reference grid overlay (8x8 or 16x16).

    Displays a simple checkerboard grid over the canvas
    to help with tile alignment visualization.
    """

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._cell_size = 8  # Default 8x8
        self._bounds = QRectF(0, 0, 128, 128)
        self._visible = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def set_cell_size(self, size: int) -> None:
        """Set grid cell size (8 or 16)."""
        if size in (8, 16):
            self._cell_size = size
            self.update()

    def set_bounds(self, bounds: QRectF) -> None:
        """Set the grid bounds."""
        self.prepareGeometryChange()
        self._bounds = bounds
        self.update()

    def set_grid_visible(self, visible: bool) -> None:
        """Show or hide the grid."""
        self._visible = visible
        self.update()

    def is_grid_visible(self) -> bool:
        """Check if grid is visible."""
        return self._visible

    @override
    def boundingRect(self) -> QRectF:
        """Return bounding rectangle."""
        return self._bounds

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint grid lines."""
        if not self._visible:
            return

        pen = QPen(QColor(255, 255, 255, 60), 1, Qt.PenStyle.DotLine)
        painter.setPen(pen)

        # Draw vertical lines
        x = self._bounds.left()
        while x <= self._bounds.right():
            painter.drawLine(
                QPointF(x, self._bounds.top()),
                QPointF(x, self._bounds.bottom()),
            )
            x += self._cell_size

        # Draw horizontal lines
        y = self._bounds.top()
        while y <= self._bounds.bottom():
            painter.drawLine(
                QPointF(self._bounds.left(), y),
                QPointF(self._bounds.right(), y),
            )
            y += self._cell_size


class GameFrameItem(QGraphicsPixmapItem):
    """Non-interactive game frame background.

    Displays the captured game sprite as a reference background.
    """

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        # Draw behind other items
        self.setZValue(-10)


class PreviewItem(QGraphicsPixmapItem):
    """In-game preview overlay showing the final composited sprite.

    Displays the quantized, clipped preview of how the sprite will look
    when injected into the ROM. Overlays the game frame when preview mode
    is enabled.
    """

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        # Draw on top of game frame but below AI frame overlay
        self.setZValue(-5)
        self.setVisible(False)  # Hidden by default
