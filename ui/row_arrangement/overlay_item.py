"""
Interactive overlay graphics item for sprite rearrangement.

Supports dragging with the mouse and synchronizes position with OverlayLayer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import QPointF, Qt

from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsSceneMouseEvent



if TYPE_CHECKING:

    from ui.row_arrangement.overlay_layer import OverlayLayer




class OverlayGraphicsItem(QGraphicsPixmapItem):
    """Graphics item for the overlay image that supports dragging.

    Synchronizes its position with an OverlayLayer instance.
    """

    def __init__(self, overlay_layer: OverlayLayer, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._overlay_layer = overlay_layer
        self._is_dragging = False

        # Set flags for interactivity
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

        # Ensure it's on top of tiles
        self.setZValue(1000)
        
        # Cross-hair cursor for moving
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        # Initial state from layer
        self._update_from_layer()

    @property
    def is_dragging(self) -> bool:
        """Whether the item is currently being dragged by the mouse."""
        return self._is_dragging

    def _update_from_layer(self) -> None:
        """Update item properties from the overlay layer."""
        self.setPos(QPointF(float(self._overlay_layer.x), float(self._overlay_layer.y)))
        self.setOpacity(self._overlay_layer.opacity)
        self.setScale(self._overlay_layer.scale)
        self.setVisible(self._overlay_layer.visible)

    @override
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        """Handle position changes to sync back to the layer."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value
            if isinstance(new_pos, QPointF):
                # Update layer position
                self._overlay_layer.set_position(int(new_pos.x()), int(new_pos.y()))

        return super().itemChange(change, value)

    @override
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse press."""
        self._is_dragging = True
        super().mousePressEvent(event)

    @override
    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse release."""
        self._is_dragging = False
        super().mouseReleaseEvent(event)
