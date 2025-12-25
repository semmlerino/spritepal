"""
Row-related widgets for SpritePal row arrangement dialog
"""
from __future__ import annotations

from typing import override

from PIL import Image
from PySide6.QtCore import QEvent, QMimeData, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDrag,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QEnterEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QListWidget, QSizePolicy, QWidget

from core.services.image_utils import pil_to_qpixmap

# Row widget constants
ROW_WIDGET_HEIGHT = 85  # Height for row preview widgets
ROW_WIDGET_MIN_WIDTH = 350  # Minimum width for row widgets


class RowPreviewWidget(QWidget):
    """Enhanced widget displaying a thumbnail preview of a sprite row"""

    def __init__(
        self,
        row_index: int,
        row_image: Image.Image,
        tiles_per_row: int,
        is_selected: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.row_index = row_index
        self.row_image = row_image
        self.tiles_per_row = tiles_per_row
        self.is_selected = is_selected
        self.is_hovered = False
        # Use minimum height + policy for better Qt layout compatibility
        self.setMinimumHeight(ROW_WIDGET_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumWidth(ROW_WIDGET_MIN_WIDTH)
        self.setMouseTracking(True)

    def update_image(self, new_image: Image.Image) -> None:
        """Update the row image for display"""
        self.row_image = new_image
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the row thumbnail with enhanced visuals"""
        painter = QPainter(self)

        # Draw main background
        if self.is_selected:
            painter.fillRect(self.rect(), QColor(50, 50, 50))  # Lighter for selected
        elif self.is_hovered:
            painter.fillRect(self.rect(), QColor(46, 46, 46))  # More noticeable hover
        else:
            painter.fillRect(self.rect(), QColor(40, 40, 40))

        # Draw prominent selection border
        if self.is_selected:
            painter.setPen(
                QPen(QColor(70, 140, 200), 4)
            )  # Thicker blue selection border
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        elif self.is_hovered:
            painter.setPen(QPen(QColor(100, 100, 100), 2))  # More visible hover border
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        else:
            painter.setPen(QPen(QColor(70, 70, 70), 1))  # Normal border
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # Create light image background well
        image_well_rect = self.rect().adjusted(6, 6, -6, -6)
        image_well_rect.setHeight(72)  # Increased to match new widget height
        painter.fillRect(
            image_well_rect, QColor(30, 30, 30)
        )  # Dark background for enhanced sprites

        # Draw subtle inset border for image well
        painter.setPen(QPen(QColor(20, 20, 20), 1))
        painter.drawRect(image_well_rect.adjusted(0, 0, -1, -1))

        # Convert PIL image to QPixmap for display
        image_end_x = 10  # Default position if no image

        if self.row_image:
            # Scale to fit within both width and height constraints
            target_height = 70  # Maximum height for the image (fits within 72px well)
            max_width = 320  # Maximum width to leave room for labels

            # Calculate scale factors for both dimensions
            height_scale = target_height / self.row_image.height
            width_scale = max_width / self.row_image.width

            # Use the smaller scale factor to maintain aspect ratio
            scale_factor = min(height_scale, width_scale)

            # Ensure at least 1x scaling and use integer scaling for pixel art
            # Use minimum scale of 2 for better visibility in thumbnails
            scale_factor = max(2, int(scale_factor))

            scaled_width = self.row_image.width * scale_factor
            scaled_height = self.row_image.height * scale_factor

            scaled_image = self.row_image.resize(
                (scaled_width, scaled_height), Image.Resampling.NEAREST
            )

            # Handle different image modes
            if scaled_image.mode == "RGBA":
                # For RGBA images (colorized), keep as is
                pass
            elif scaled_image.mode != "L":
                # For other modes, convert to grayscale
                scaled_image = scaled_image.convert("L")

            # Convert to QPixmap using enhanced utility function
            pixmap = pil_to_qpixmap(scaled_image)

            if pixmap:
                # Draw scaled thumbnail centered in the well
                draw_x = image_well_rect.x() + 1
                draw_y = image_well_rect.y() + 1
                painter.drawPixmap(draw_x, draw_y, pixmap)

                # Update image end position for label placement
                image_end_x = draw_x + pixmap.width() + 10

        # Draw row label with better formatting
        painter.setPen(QColor(220, 220, 220))
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        # Position label after the image with some padding
        painter.drawText(image_end_x, 30, f"Row {self.row_index}")

        # Draw tile count
        painter.setPen(QColor(180, 180, 180))
        font.setBold(False)
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(image_end_x, 50, f"{self.tiles_per_row} tiles")

        # Draw selection indicator with better styling
        if self.is_selected:
            painter.setPen(QColor(70, 140, 200))  # Match border color
            painter.drawText(image_end_x, 70, "● Selected")

    @override
    def enterEvent(self, event: QEnterEvent) -> None:
        """Handle mouse enter"""
        self.is_hovered = True
        self.update()

    @override
    def leaveEvent(self, event: QEvent) -> None:
        """Handle mouse leave"""
        self.is_hovered = False
        self.update()

    def set_selected(self, selected: bool) -> None:
        """Set selection state"""
        self.is_selected = selected
        self.update()

class DragDropListWidget(QListWidget):
    """List widget with enhanced drag-and-drop support"""

    item_dropped = Signal(int, int)  # from_index, to_index
    external_drop = Signal(object)  # dropped item data

    def __init__(self, accept_external_drops: bool = False):
        super().__init__()
        self.accept_external_drops = accept_external_drops
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

    @override
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter"""
        mime_data = event.mimeData()
        if mime_data and mime_data.hasText() and self.accept_external_drops:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    @override
    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Handle drag move"""
        mime_data = event.mimeData()
        if mime_data and mime_data.hasText() and self.accept_external_drops:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    @override
    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop events"""
        mime_data = event.mimeData()
        if mime_data and mime_data.hasText() and self.accept_external_drops:
            # Handle external drop
            try:
                text = mime_data.text()
                if text:
                    row_index = int(text)
                    self.external_drop.emit(row_index)
                    event.acceptProposedAction()
            except ValueError:
                pass
        else:
            # Handle internal reordering
            super().dropEvent(event)
            self.item_dropped.emit(0, 0)  # Signal for refresh

    @override
    def startDrag(self, supportedActions: Qt.DropAction) -> None:
        """Start drag operation"""
        item = self.currentItem()
        if item:
            drag = QDrag(self)
            mime_data = QMimeData()

            # Store the row index for external drops
            row_data = item.data(Qt.ItemDataRole.UserRole)
            if row_data is not None:
                mime_data.setText(str(row_data))

            drag.setMimeData(mime_data)
            drag.exec(Qt.DropAction.MoveAction)
