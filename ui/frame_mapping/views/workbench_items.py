"""QGraphicsItem subclasses for the Workbench Canvas.

This module provides specialized graphics items for the interactive
sprite alignment canvas:

- AIFrameItem: Draggable/scalable overlay for the AI frame
- ScaleHandle: Corner handles for uniform scaling
- TileOverlayItem: Displays OAM tile boundaries with touch status
- GridOverlayItem: Optional reference grid (8x8 or 16x16)
"""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QTransform
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
                new_scale = max(0.1, min(10.0, new_scale))

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
    """

    transform_changed = Signal(int, int, float)  # offset_x, offset_y, scale

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._scale_factor = 1.0
        self._flip_h = False
        self._flip_v = False
        self._opacity = 0.7
        self._ghost_mode = False

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
        scale = max(0.1, min(10.0, scale))
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
            # Ghost mode: dashed yellow outline with corner markers
            painter.setOpacity(0.5)
            pen = QPen(QColor(255, 255, 0, 200))
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(target_rect)
            # Corner markers for grabbing
            marker_size = 6
            painter.setBrush(QColor(255, 255, 0, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            for corner in [
                target_rect.topLeft(),
                target_rect.topRight(),
                target_rect.bottomLeft(),
                target_rect.bottomRight(),
            ]:
                painter.drawEllipse(corner, marker_size, marker_size)
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
        """Handle arrow keys for nudging."""
        from PySide6.QtGui import QKeyEvent

        if isinstance(event, QKeyEvent):
            step = 8 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            key = event.key()

            if key == Qt.Key.Key_Left:
                self.moveBy(-step, 0)
                event.accept()
            elif key == Qt.Key.Key_Right:
                self.moveBy(step, 0)
                event.accept()
            elif key == Qt.Key.Key_Up:
                self.moveBy(0, -step)
                event.accept()
            elif key == Qt.Key.Key_Down:
                self.moveBy(0, step)
                event.accept()
            else:
                event.ignore()


class TileOverlayItem(QGraphicsItem):
    """Displays OAM tile boundaries with touched/untouched status.

    Shows the actual tile positions from the Mesen capture,
    color-coded by whether the AI frame covers them:
    - Green: Touched (AI frame fully covers)
    - Gray: Untouched (not covered or partially covered)
    """

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._tile_rects: list[QRectF] = []
        self._touched_indices: set[int] = set()
        self._visible = True
        self._bounds = QRectF(0, 0, 64, 64)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def set_tile_rects(self, rects: list[QRectF]) -> None:
        """Set the OAM tile rectangles."""
        self.prepareGeometryChange()
        self._tile_rects = rects
        self._update_bounds()
        self.update()

    def set_touched_indices(self, indices: set[int]) -> None:
        """Set which tiles are touched by the overlay."""
        self._touched_indices = indices
        self.update()

    def set_overlay_visible(self, visible: bool) -> None:
        """Show or hide the tile overlay."""
        self._visible = visible
        self.update()

    def _update_bounds(self) -> None:
        """Update bounding rect from tile rects."""
        if not self._tile_rects:
            self._bounds = QRectF(0, 0, 64, 64)
            return

        min_x = min(r.x() for r in self._tile_rects)
        min_y = min(r.y() for r in self._tile_rects)
        max_x = max(r.right() for r in self._tile_rects)
        max_y = max(r.bottom() for r in self._tile_rects)
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
        """Paint tile boundaries."""
        if not self._visible or not self._tile_rects:
            return

        touched_color = QColor(100, 200, 100, 80)
        touched_border = QColor(100, 200, 100, 180)
        untouched_color = QColor(150, 150, 150, 60)
        untouched_border = QColor(150, 150, 150, 150)

        for i, rect in enumerate(self._tile_rects):
            if i in self._touched_indices:
                painter.setBrush(QBrush(touched_color))
                painter.setPen(QPen(touched_border, 1))
            else:
                painter.setBrush(QBrush(untouched_color))
                painter.setPen(QPen(untouched_border, 1))
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
