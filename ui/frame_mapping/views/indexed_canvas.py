#!/usr/bin/env python3
"""
Indexed image canvas for palette-based pixel editing.

Provides a zoomable, pannable canvas for displaying and editing
indexed palette images with selection overlay support.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.editing import SelectionMask
    from core.frame_mapping_project import SheetPalette


logger = logging.getLogger(__name__)

# Canvas display constants
CANVAS_MIN_SIZE = 300
MIN_ZOOM = 0.25
MAX_ZOOM = 16.0
DEFAULT_ZOOM = 4.0  # Start at 4x zoom for pixel editing


class IndexedCanvasView(QGraphicsView):
    """Custom QGraphicsView with checkerboard background, zoom, pan, and pixel editing.

    Signals:
        pixel_hovered: Emitted when mouse hovers over a pixel (x, y, in image coords)
        pixel_clicked: Emitted when a pixel is clicked (x, y, in image coords)
        pixel_dragged: Emitted during drag over pixels (x, y, in image coords)
        mouse_left: Emitted when mouse leaves the canvas
    """

    pixel_hovered = Signal(int, int)  # image x, y
    pixel_clicked = Signal(int, int, int)  # image x, y, button (0=left, 1=right, 2=middle)
    pixel_dragged = Signal(int, int)  # image x, y
    drag_ended = Signal()
    mouse_left = Signal()
    brush_size_changed = Signal(int)  # new brush size

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self._setup_view()
        self._image_width = 1
        self._image_height = 1
        self._is_panning = False
        self._pan_start: QPointF | None = None
        self._is_space_pressed = False
        self._is_dragging = False
        self._brush_size = 1
        self._brush_cursor: QCursor | None = None
        # Brush resize drag state (Ctrl+RMB)
        self._is_resizing_brush = False
        self._resize_start_x: float = 0
        self._resize_start_size: int = 1

    def _setup_view(self) -> None:
        """Configure view settings."""
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(40, 40, 40)))
        self.setMinimumSize(CANVAS_MIN_SIZE, CANVAS_MIN_SIZE)
        self.setStyleSheet("border: 1px solid #444;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Set initial zoom
        self.resetTransform()
        self.scale(DEFAULT_ZOOM, DEFAULT_ZOOM)

    def set_image_size(self, width: int, height: int) -> None:
        """Set the image dimensions for coordinate calculations."""
        self._image_width = max(1, width)
        self._image_height = max(1, height)

    def set_brush_size(self, size: int) -> None:
        """Set the brush size and update cursor.

        Args:
            size: Brush size (1-5)
        """
        self._brush_size = max(1, min(5, size))
        self._update_brush_cursor()

    def _update_brush_cursor(self) -> None:
        """Create and set a cursor showing the brush size."""
        # Get current zoom level
        zoom = self.transform().m11()  # Scale factor

        # Calculate cursor size based on brush and zoom
        # Make the cursor visible at different zoom levels
        cursor_size = max(16, int(self._brush_size * zoom * 2))

        # Create pixmap for cursor
        pixmap = QPixmap(cursor_size + 2, cursor_size + 2)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Draw outline square showing brush size
        pen = QPen(QColor(255, 255, 255), 1)
        painter.setPen(pen)
        rect_size = int(self._brush_size * zoom)
        offset = (cursor_size - rect_size) // 2
        painter.drawRect(offset, offset, rect_size, rect_size)

        # Draw inner square for visibility on light backgrounds
        pen.setColor(QColor(0, 0, 0))
        painter.setPen(pen)
        painter.drawRect(offset + 1, offset + 1, rect_size - 2, rect_size - 2)

        painter.end()

        # Create cursor with hotspot at center
        hotspot = cursor_size // 2
        self._brush_cursor = QCursor(pixmap, hotspot, hotspot)
        self.setCursor(self._brush_cursor)

    def get_zoom(self) -> float:
        """Get current zoom level."""
        return self.transform().m11()

    def set_zoom(self, zoom: float) -> None:
        """Set zoom level."""
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self.resetTransform()
        self.scale(zoom, zoom)
        # Update brush cursor for new zoom level
        self._update_brush_cursor()

    @override
    def drawBackground(self, painter: QPainter, rect: QRectF | QRect) -> None:
        """Draw checkerboard background for transparency."""
        super().drawBackground(painter, rect)

        cell_size = 8
        colors = [QColor(60, 60, 60), QColor(80, 80, 80)]

        # Get visible rect in scene coordinates
        visible = self.mapToScene(self.viewport().rect()).boundingRect()

        start_x = int(visible.left() // cell_size) * cell_size
        start_y = int(visible.top() // cell_size) * cell_size

        y = start_y
        while y < visible.bottom():
            x = start_x
            while x < visible.right():
                color_index = (int(x // cell_size) + int(y // cell_size)) % 2
                painter.fillRect(
                    QRectF(x, y, cell_size, cell_size),
                    colors[color_index],
                )
                x += cell_size
            y += cell_size

    @override
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel for zoom (Ctrl+wheel) or scroll."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            zoom_factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
            current_scale = self.transform().m11()

            # Clamp zoom
            new_scale = current_scale * zoom_factor
            if MIN_ZOOM <= new_scale <= MAX_ZOOM:
                # Zoom centered on mouse position
                self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
                self.scale(zoom_factor, zoom_factor)
                self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
            event.accept()
        else:
            super().wheelEvent(event)

    @override
    def keyPressEvent(self, event: object) -> None:
        """Handle key press for space-drag panning."""
        from PySide6.QtGui import QKeyEvent

        if isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
                self._is_space_pressed = True
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                event.accept()
                return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    @override
    def keyReleaseEvent(self, event: object) -> None:
        """Handle key release for space-drag panning."""
        from PySide6.QtGui import QKeyEvent

        if isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
                self._is_space_pressed = False
                if not self._is_panning:
                    self.unsetCursor()
                event.accept()
                return
        super().keyReleaseEvent(event)  # type: ignore[arg-type]

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press for panning, painting, and brush resize."""
        # Ctrl+RMB starts brush resize
        if event.button() == Qt.MouseButton.RightButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._is_resizing_brush = True
            self._resize_start_x = event.position().x()
            self._resize_start_size = self._brush_size
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            event.accept()
            return

        # Middle button or space+left button starts panning
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._is_space_pressed
        ):
            self._is_panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        # Get image coordinates
        scene_pos = self.mapToScene(event.position().toPoint())
        img_x, img_y = self._scene_to_image_coords(scene_pos)

        if 0 <= img_x < self._image_width and 0 <= img_y < self._image_height:
            button = 0 if event.button() == Qt.MouseButton.LeftButton else 1
            self.pixel_clicked.emit(img_x, img_y, button)
            self._is_dragging = True
            event.accept()
        else:
            super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move for panning, dragging, brush resize, and hover."""
        # Handle brush resize drag
        if self._is_resizing_brush:
            delta_x = event.position().x() - self._resize_start_x
            # 20 pixels of movement = 1 size change
            size_delta = int(delta_x / 20)
            new_size = max(1, min(5, self._resize_start_size + size_delta))
            if new_size != self._brush_size:
                self._brush_size = new_size
                self._update_brush_cursor()
                self.brush_size_changed.emit(new_size)
            event.accept()
            return

        # Handle panning
        if self._is_panning and self._pan_start is not None:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return

        # Get image coordinates
        scene_pos = self.mapToScene(event.position().toPoint())
        img_x, img_y = self._scene_to_image_coords(scene_pos)

        if 0 <= img_x < self._image_width and 0 <= img_y < self._image_height:
            # Emit drag if left button is held
            if self._is_dragging:
                self.pixel_dragged.emit(img_x, img_y)
            else:
                self.pixel_hovered.emit(img_x, img_y)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release."""
        # End brush resize
        if event.button() == Qt.MouseButton.RightButton and self._is_resizing_brush:
            self._is_resizing_brush = False
            self._update_brush_cursor()  # Restore brush cursor
            event.accept()
            return

        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._is_panning
        ):
            self._is_panning = False
            self._pan_start = None
            if self._is_space_pressed:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            event.accept()
            return

        if self._is_dragging:
            self._is_dragging = False
            self.drag_ended.emit()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    @override
    def leaveEvent(self, event: object) -> None:
        """Handle mouse leaving the viewport."""
        self.mouse_left.emit()
        super().leaveEvent(event)  # type: ignore[arg-type]

    def _scene_to_image_coords(self, scene_pos: QPointF) -> tuple[int, int]:
        """Convert scene coordinates to image pixel coordinates."""
        return int(scene_pos.x()), int(scene_pos.y())


class IndexedCanvas(QWidget):
    """Main indexed image canvas widget.

    Provides a complete canvas for displaying and editing indexed images
    with zoom, pan, grid overlay, and selection support.

    Signals:
        pixel_hovered: (x, y) - Mouse is over a pixel
        pixel_clicked: (x, y, button) - Pixel was clicked
        pixel_dragged: (x, y) - Mouse dragged over pixel
        drag_ended: Drag operation completed
        mouse_left: Mouse left the canvas
    """

    pixel_hovered = Signal(int, int)
    pixel_clicked = Signal(int, int, int)
    pixel_dragged = Signal(int, int)
    drag_ended = Signal()
    mouse_left = Signal()
    brush_size_changed = Signal(int)  # new brush size from Ctrl+RMB drag

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._indexed_data: np.ndarray | None = None
        self._palette: SheetPalette | None = None
        self._selection_mask: SelectionMask | None = None
        self._highlight_index: int | None = None  # Palette index to highlight
        self._show_grid = False
        self._grid_size = 8

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create graphics scene and view
        self._scene = QGraphicsScene(self)
        self._view = IndexedCanvasView(self._scene, self)

        # Add pixmap item for the image
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)

        # Add palette highlight overlay (shows pixels using selected index)
        self._highlight_item = QGraphicsPixmapItem()
        self._highlight_item.setZValue(0.5)  # Between image and selection
        self._scene.addItem(self._highlight_item)

        # Add selection overlay item (on top of image)
        self._selection_item = QGraphicsPixmapItem()
        self._selection_item.setZValue(1)
        self._scene.addItem(self._selection_item)

        # Add grid overlay item
        self._grid_item = QGraphicsPixmapItem()
        self._grid_item.setZValue(2)
        self._grid_item.setVisible(False)
        self._scene.addItem(self._grid_item)

        # Container frame
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.Box)
        frame.setStyleSheet("QFrame { border: 1px solid #555; }")
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.addWidget(self._view)

        layout.addWidget(frame)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._view.pixel_hovered.connect(self.pixel_hovered)
        self._view.pixel_clicked.connect(self.pixel_clicked)
        self._view.pixel_dragged.connect(self.pixel_dragged)
        self._view.drag_ended.connect(self.drag_ended)
        self._view.mouse_left.connect(self.mouse_left)
        self._view.brush_size_changed.connect(self.brush_size_changed)

    def set_image(self, indexed_data: np.ndarray, palette: SheetPalette) -> None:
        """Set the indexed image data and palette.

        Args:
            indexed_data: 2D numpy array of palette indices (H, W)
            palette: SheetPalette with colors
        """
        self._indexed_data = indexed_data
        self._palette = palette
        self._view.set_image_size(indexed_data.shape[1], indexed_data.shape[0])
        self._render_image()
        self._update_grid_overlay()

    def refresh_palette(self) -> None:
        """Re-render the image with the current palette.

        Call this when palette colors have changed but the indexed data
        hasn't changed. This re-reads colors from the palette and re-renders.
        """
        self._render_image()
        self._update_highlight_overlay()

    def _render_image(self) -> None:
        """Render the indexed data to a pixmap."""
        if self._indexed_data is None or self._palette is None:
            return

        height, width = self._indexed_data.shape

        # Create color lookup table from palette (16 colors + alpha)
        lut = np.zeros((16, 4), dtype=np.uint8)
        lut[0] = (0, 0, 0, 0)  # Index 0 = transparent
        for i in range(1, min(16, len(self._palette.colors))):
            r, g, b = self._palette.colors[i]
            lut[i] = (r, g, b, 255)

        # Vectorized lookup - much faster than nested loops
        indices = np.clip(self._indexed_data, 0, 15)
        rgba = lut[indices]

        # Convert to QImage
        qimage = QImage(
            rgba.data,
            width,
            height,
            width * 4,
            QImage.Format.Format_RGBA8888,
        )
        # Make a copy since numpy array may be modified
        qimage = qimage.copy()

        pixmap = QPixmap.fromImage(qimage)
        self._pixmap_item.setPixmap(pixmap)

        # Update scene rect
        self._scene.setSceneRect(0, 0, width, height)

    def set_selection_mask(self, mask: SelectionMask | None) -> None:
        """Set the selection mask for overlay display.

        Args:
            mask: SelectionMask to display, or None to clear
        """
        self._selection_mask = mask
        self._update_selection_overlay()

    def set_highlight_index(self, index: int | None) -> None:
        """Highlight all pixels using the specified palette index.

        Args:
            index: Palette index to highlight (0-15), or None to clear
        """
        self._highlight_index = index
        self._update_highlight_overlay()

    def _update_highlight_overlay(self) -> None:
        """Update the highlight overlay showing pixels with selected index."""
        if self._indexed_data is None or self._highlight_index is None:
            self._highlight_item.setPixmap(QPixmap())
            return

        height, width = self._indexed_data.shape

        # Create mask of pixels matching the highlight index
        mask = self._indexed_data == self._highlight_index

        # Create semi-transparent green overlay for highlighted pixels
        overlay = np.zeros((height, width, 4), dtype=np.uint8)
        overlay[mask] = (0, 200, 0, 100)  # Green with alpha

        qimage = QImage(
            overlay.data,
            width,
            height,
            width * 4,
            QImage.Format.Format_RGBA8888,
        )
        qimage = qimage.copy()

        self._highlight_item.setPixmap(QPixmap.fromImage(qimage))

    def _update_selection_overlay(self) -> None:
        """Update the selection overlay pixmap."""
        if self._indexed_data is None:
            self._selection_item.setPixmap(QPixmap())
            return

        height, width = self._indexed_data.shape

        if self._selection_mask is None or not self._selection_mask.has_selection():
            self._selection_item.setPixmap(QPixmap())
            return

        # Create semi-transparent green overlay for selected pixels
        overlay = np.zeros((height, width, 4), dtype=np.uint8)

        for x, y in self._selection_mask.get_selected_pixels():
            if 0 <= x < width and 0 <= y < height:
                overlay[y, x] = (0, 255, 0, 120)  # Green with alpha

        qimage = QImage(
            overlay.data,
            width,
            height,
            width * 4,
            QImage.Format.Format_RGBA8888,
        )
        qimage = qimage.copy()

        self._selection_item.setPixmap(QPixmap.fromImage(qimage))

    def set_show_grid(self, show: bool) -> None:
        """Toggle grid overlay visibility."""
        self._show_grid = show
        self._grid_item.setVisible(show)
        if show:
            self._update_grid_overlay()

    def set_brush_size(self, size: int) -> None:
        """Set the brush size cursor.

        Args:
            size: Brush size (1-5)
        """
        self._view.set_brush_size(size)

    def set_grid_size(self, size: int) -> None:
        """Set the grid cell size."""
        self._grid_size = size
        if self._show_grid:
            self._update_grid_overlay()

    def _update_grid_overlay(self) -> None:
        """Update the grid overlay pixmap."""
        if self._indexed_data is None or not self._show_grid:
            return

        height, width = self._indexed_data.shape

        # Create transparent image with grid lines
        grid_image = QImage(width, height, QImage.Format.Format_ARGB32)
        grid_image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(grid_image)
        pen = QPen(QColor(255, 255, 255, 80))  # Semi-transparent white
        pen.setWidth(0)  # Hairline
        painter.setPen(pen)

        # Draw vertical lines
        for x in range(0, width, self._grid_size):
            painter.drawLine(x, 0, x, height)

        # Draw horizontal lines
        for y in range(0, height, self._grid_size):
            painter.drawLine(0, y, width, y)

        painter.end()

        self._grid_item.setPixmap(QPixmap.fromImage(grid_image))

    def refresh(self) -> None:
        """Refresh the display (re-render image and selection)."""
        self._render_image()
        self._update_selection_overlay()

    def get_zoom(self) -> float:
        """Get current zoom level."""
        return self._view.get_zoom()

    def set_zoom(self, zoom: float) -> None:
        """Set zoom level."""
        self._view.set_zoom(zoom)

    def zoom_in(self) -> None:
        """Increase zoom by one step."""
        self.set_zoom(self.get_zoom() * 1.5)

    def zoom_out(self) -> None:
        """Decrease zoom by one step."""
        self.set_zoom(self.get_zoom() / 1.5)

    def zoom_fit(self) -> None:
        """Fit the image in the view."""
        self._view.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_100(self) -> None:
        """Reset to 100% zoom (1:1 pixels)."""
        self.set_zoom(1.0)

    def focus_canvas(self) -> None:
        """Give keyboard focus to the canvas."""
        self._view.setFocus()

    def get_image_size(self) -> tuple[int, int]:
        """Get the current image dimensions.

        Returns:
            Tuple of (width, height)
        """
        if self._indexed_data is None:
            return (0, 0)
        return (self._indexed_data.shape[1], self._indexed_data.shape[0])
