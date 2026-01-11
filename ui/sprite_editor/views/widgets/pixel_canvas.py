#!/usr/bin/env python3
"""
Optimized canvas widget for the pixel editor.
Uses controller's models and managers instead of maintaining its own state.
"""

from typing import TYPE_CHECKING, override

import numpy as np
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QEnterEvent, QImage, QMouseEvent, QPainter, QPaintEvent, QPen, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

if TYPE_CHECKING:
    from ...controllers.editing_controller import EditingController


class PixelCanvas(QWidget):
    """Optimized canvas that delegates to controller."""

    # Signals
    pixelPressed = Signal(int, int)  # x, y in image space
    pixelMoved = Signal(int, int)  # x, y in image space
    pixelReleased = Signal(int, int)  # x, y in image space
    zoomRequested = Signal(int)  # new zoom level
    hoverPositionChanged = Signal(int, int)  # x, y in image space (-1, -1 when no position)

    def __init__(self, controller: "EditingController", parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Store controller reference
        self.controller = controller

        # View state (not business logic)
        self.zoom = 4
        self.grid_visible = False
        self.tile_grid_visible = False
        self.greyscale_mode = False
        self.background_type = "checkerboard"
        self.custom_background_color = QColor(Qt.GlobalColor.black)

        # Interaction state
        self.drawing = False
        self.hover_pos: QPoint | None = None
        self.temporary_picker = False  # Track if we're temporarily using picker with right-click
        self.previous_tool: str | None = None  # Store previous tool when using temporary picker
        self.last_draw_pos: QPoint | None = None  # Track last known position during drawing

        # Performance caches
        self._qcolor_cache: dict[int, QColor] = {}
        self._palette_version = 0
        self._cached_palette_version = -1

        # Vectorized rendering optimization
        self._color_lut: np.ndarray | None = None  # Lookup table for color index to RGB conversion
        self._cached_lut_version = -1

        # QImage-based rendering optimization
        self._qimage_buffer: QImage | None = None  # QImage buffer for efficient rendering
        self._qimage_scaled: QImage | None = None  # Cached scaled version of the image
        self._cached_zoom = 0  # Last zoom level used for scaled image
        self._cached_scaled_palette_version = -1  # Last palette version used for scaled image
        self._dirty_rect = QRect()  # Rectangle that needs repainting
        self._image_version = 0  # Track image data changes
        self._cached_image_version = -1

        # Setup
        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

        # Connect to controller signals
        self.controller.imageChanged.connect(self._on_image_changed)
        self.controller.paletteChanged.connect(self._on_palette_changed)
        self.controller.toolChanged.connect(self._on_tool_changed)

        # Install event filter to catch mouse release outside widget
        if parent:
            parent.installEventFilter(self)

        # Set initial cursor for current tool
        current_tool = self.controller.get_current_tool_name()
        self._update_cursor_for_tool(current_tool)

    def _on_image_changed(self) -> None:
        """Handle image change from controller."""
        self._update_size()
        self._palette_version += 1  # Force color cache update
        self._image_version += 1  # Force image buffer update
        self._invalidate_image_cache()
        self.update()

    def _on_palette_changed(self) -> None:
        """Handle palette change from controller."""
        self._palette_version += 1  # Force color cache update
        self._invalidate_color_cache()  # More efficient - only invalidate color cache
        self.update()

    def _on_tool_changed(self, tool_name: str) -> None:
        """Handle tool change from controller."""
        self._update_cursor_for_tool(tool_name)

    def _update_cursor_for_tool(self, tool_name: str) -> None:
        """Update cursor based on the current tool."""
        if tool_name in ("pencil", "eraser"):
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif tool_name == "fill":
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif tool_name == "picker":
            # Use WhatsThisCursor as a dropper cursor substitute
            self.setCursor(Qt.CursorShape.WhatsThisCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _update_size(self) -> None:
        """Update widget size based on image and zoom."""
        size = self.controller.get_image_size()
        if size:
            width, height = size
            new_width = width * self.zoom
            new_height = height * self.zoom
            self.setMinimumSize(new_width, new_height)
            self.updateGeometry()

    @override
    def sizeHint(self) -> QSize:
        """Return the size of the canvas based on image and zoom."""
        if not self.controller or not self.controller.has_image():
            return super().sizeHint()

        size = self.controller.get_image_size()
        if size:
            width, height = size
            return QSize(width * self.zoom, height * self.zoom)
        return super().sizeHint()

    def set_zoom(self, zoom: int, center_on_canvas: bool = True) -> None:
        """Set zoom level.

        Args:
            zoom: New zoom level
            center_on_canvas: Unused (kept for API compatibility)
        """
        new_zoom = max(1, min(64, zoom))
        if new_zoom != self.zoom:
            self.zoom = new_zoom
            self._update_size()
            # Invalidate scaled image cache since zoom changed
            self._invalidate_scaled_cache()
            self.update()

    def set_grid_visible(self, visible: bool) -> None:
        """Toggle grid visibility."""
        self.grid_visible = visible
        self.update()

    def set_tile_grid_visible(self, visible: bool) -> None:
        """Toggle tile grid visibility."""
        self.tile_grid_visible = visible
        self.update()

    def set_background(self, bg_type: str, custom_color: QColor | None = None) -> None:
        """Set the background type.

        Args:
            bg_type: Background type ("checkerboard", "black", "white", "custom")
            custom_color: Custom color for "custom" type
        """
        self.background_type = bg_type.lower()
        if custom_color:
            self.custom_background_color = custom_color
        self.update()

    def set_greyscale_mode(self, greyscale: bool) -> None:
        """Toggle greyscale display mode."""
        self.greyscale_mode = greyscale
        self._palette_version += 1  # Force color cache update
        self._invalidate_color_cache()  # More efficient - only invalidate color cache
        self._invalidate_scaled_cache()  # Also invalidate scaled cache for immediate update
        self.update()

    def _update_qcolor_cache(self) -> None:
        """Update cached QColor objects when palette changes."""
        self._qcolor_cache.clear()

        # Get colors from controller
        colors = self.controller.get_current_colors()

        if self.greyscale_mode:
            # Override with grayscale
            for i in range(16):
                gray = (i * 255) // 15
                if i == 0:
                    # Index 0 is transparent
                    self._qcolor_cache[i] = QColor(gray, gray, gray, 0)
                else:
                    self._qcolor_cache[i] = QColor(gray, gray, gray)
        else:
            # Use actual colors
            for i, rgb in enumerate(colors[:16]):
                if i == 0:
                    # Index 0 is transparent
                    self._qcolor_cache[i] = QColor(rgb[0], rgb[1], rgb[2], 0)
                else:
                    self._qcolor_cache[i] = QColor(*rgb)

        # Add magenta for invalid indices
        self._qcolor_cache[-1] = QColor(255, 0, 255)

        self._cached_palette_version = self._palette_version

        # Invalidate LUT cache since palette changed
        self._cached_lut_version = -1

    def _update_color_lut(self) -> None:
        """Create vectorized color lookup table for fast numpy operations."""
        if self._cached_lut_version == self._palette_version:
            return  # LUT is still valid

        # Update color cache first if needed
        if self._cached_palette_version != self._palette_version:
            self._update_qcolor_cache()

        # Create numpy array for color lookup (256 colors max, RGB format)
        # Using 256 to handle any possible color index safely
        self._color_lut = np.zeros((256, 3), dtype=np.uint8)

        # Fill lookup table with cached colors
        for color_index, qcolor in self._qcolor_cache.items():
            if 0 <= color_index < 256:
                self._color_lut[color_index] = [qcolor.red(), qcolor.green(), qcolor.blue()]

        # Handle invalid indices with magenta
        invalid_color = self._qcolor_cache.get(-1, QColor(255, 0, 255))
        magenta = [invalid_color.red(), invalid_color.green(), invalid_color.blue()]

        # Fill unused slots with magenta
        for i in range(16, 256):
            if i not in self._qcolor_cache:
                self._color_lut[i] = magenta

        self._cached_lut_version = self._palette_version

    def _invalidate_image_cache(self) -> None:
        """Invalidate QImage buffer cache."""
        self._qimage_buffer = None
        self._qimage_scaled = None
        self._cached_zoom = 0
        self._cached_image_version = -1

    def _invalidate_color_cache(self) -> None:
        """Invalidate only color-related caches without affecting image data."""
        self._cached_palette_version = -1
        self._cached_lut_version = -1
        # Only invalidate image buffer, not scaled cache if zoom hasn't changed
        if self._qimage_buffer is not None:
            self._qimage_buffer = None
            self._cached_image_version = -1

    def _invalidate_scaled_cache(self) -> None:
        """Invalidate only the scaled image cache."""
        self._qimage_scaled = None
        self._cached_zoom = 0
        self._cached_scaled_palette_version = -1

    def _update_qimage_buffer(self) -> None:
        """Update QImage buffer from current image data using vectorized numpy operations."""
        if (
            self._qimage_buffer is not None
            and self._cached_image_version == self._image_version
            and self._cached_palette_version == self._palette_version
        ):
            return  # Cache is still valid

        image_model = self.controller.image_model
        height, width = image_model.data.shape

        # Update color lookup table if needed
        self._update_color_lut()

        # Create QImage buffer with alpha support
        self._qimage_buffer = QImage(width, height, QImage.Format.Format_ARGB32)

        # Vectorized color conversion using numpy
        # Clamp indices to valid range to prevent crashes
        image_data = np.clip(image_model.data, 0, 255).astype(np.uint8)

        # Use vectorized lookup to convert entire image at once
        if self._color_lut is not None:
            rgb_data = self._color_lut[image_data]  # Shape: (height, width, 3)
        else:
            rgb_data = np.zeros((height, width, 3), dtype=np.uint8)

        # Convert RGB to ARGB format for QImage (add alpha channel)
        argb_data = np.zeros((height, width, 4), dtype=np.uint8)
        argb_data[:, :, 0] = rgb_data[:, :, 2]  # Blue
        argb_data[:, :, 1] = rgb_data[:, :, 1]  # Green
        argb_data[:, :, 2] = rgb_data[:, :, 0]  # Red

        # Handle transparency for index 0
        mask = image_data == 0
        argb_data[mask, 3] = 0  # Alpha = 0 (transparent)
        argb_data[~mask, 3] = 255  # Alpha = 255 (opaque)

        # Copy data directly to QImage buffer for maximum speed
        # In PySide6, bits() returns a buffer-compatible object.
        # Use memoryview to ensure correct byte-level access without type warnings.
        buffer_ptr = self._qimage_buffer.bits()

        # Convert to bytes and copy to QImage buffer
        argb_bytes = argb_data.tobytes()
        memoryview(buffer_ptr)[: len(argb_bytes)] = argb_bytes

        self._cached_image_version = self._image_version

    def _get_scaled_qimage(self) -> QImage | None:
        """Get scaled QImage for current zoom level using optimized numpy scaling."""
        # Check if cached scaled image is still valid (zoom and palette haven't changed)
        if (
            self._qimage_scaled is not None
            and self._cached_zoom == self.zoom
            and self._cached_scaled_palette_version == self._palette_version
        ):
            return self._qimage_scaled

        image_model = self.controller.image_model

        # Update color lookup table if needed
        self._update_color_lut()

        # Use numpy for efficient nearest-neighbor scaling
        scaled_data = self._scale_image_data_numpy(image_model.data, self.zoom)
        scaled_height, scaled_width = scaled_data.shape

        # Create scaled QImage directly from scaled data with alpha support
        self._qimage_scaled = QImage(scaled_width, scaled_height, QImage.Format.Format_ARGB32)

        # Vectorized color conversion for scaled image
        image_data = np.clip(scaled_data, 0, 255).astype(np.uint8)
        if self._color_lut is not None:
            rgb_data = self._color_lut[image_data]
        else:
            rgb_data = np.zeros((scaled_height, scaled_width, 3), dtype=np.uint8)

        # Convert to ARGB format
        argb_data = np.zeros((scaled_height, scaled_width, 4), dtype=np.uint8)
        argb_data[:, :, 0] = rgb_data[:, :, 2]  # Blue
        argb_data[:, :, 1] = rgb_data[:, :, 1]  # Green
        argb_data[:, :, 2] = rgb_data[:, :, 0]  # Red

        # Handle transparency for index 0
        mask = image_data == 0
        argb_data[mask, 3] = 0  # Alpha = 0 (transparent)
        argb_data[~mask, 3] = 255  # Alpha = 255 (opaque)

        # Copy to QImage buffer
        # In PySide6, bits() returns a buffer-compatible object.
        # Use memoryview to ensure correct byte-level access without type warnings.
        buffer_ptr = self._qimage_scaled.bits()
        argb_bytes = argb_data.tobytes()
        memoryview(buffer_ptr)[: len(argb_bytes)] = argb_bytes

        self._cached_zoom = self.zoom
        self._cached_scaled_palette_version = self._palette_version
        return self._qimage_scaled

    def _scale_image_data_numpy(self, image_data: np.ndarray, zoom: int) -> np.ndarray:
        """Efficient nearest-neighbor scaling using numpy."""
        if zoom == 1:
            return image_data

        # Use numpy's repeat function for efficient nearest-neighbor scaling
        # This is much faster than Qt's scaling for pixel art
        scaled_data = np.repeat(image_data, zoom, axis=0)  # Scale vertically
        scaled_data = np.repeat(scaled_data, zoom, axis=1)  # Scale horizontally

        return scaled_data

    def _update_hover_regions(self, old_pos: QPoint | None, new_pos: QPoint | None) -> None:
        """Update only the regions affected by hover position change."""
        if self.drawing:
            # Skip hover updates during drawing
            return

        # Calculate update regions
        regions_to_update: list[QRect] = []

        # Get brush size to calculate full update area
        brush_size = self.controller.get_brush_size()

        # Account for pen width in highlight drawing (1 pixel)
        pen_width = 1

        # Add old hover position to update list
        if old_pos is not None:
            # Calculate the full brush area that needs updating
            update_rect = QRect(
                old_pos.x() * self.zoom - pen_width,
                old_pos.y() * self.zoom - pen_width,
                brush_size * self.zoom + pen_width * 2,
                brush_size * self.zoom + pen_width * 2,
            )
            regions_to_update.append(update_rect)

        # Add new hover position to update list
        if new_pos is not None:
            # Calculate the full brush area that needs updating
            update_rect = QRect(
                new_pos.x() * self.zoom - pen_width,
                new_pos.y() * self.zoom - pen_width,
                brush_size * self.zoom + pen_width * 2,
                brush_size * self.zoom + pen_width * 2,
            )
            regions_to_update.append(update_rect)

        # Update the regions
        for rect in regions_to_update:
            self.update(rect)

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the canvas using optimized viewport-based rendering."""
        if not self.controller.has_image():
            return

        painter = QPainter(self)

        # Get the visible region for viewport-based rendering
        visible_rect = event.rect()

        # Calculate the visible region in image coordinates
        image_rect = self._calculate_visible_image_region(visible_rect)
        if image_rect.isEmpty():
            return

        # Get scaled QImage
        scaled_qimage = self._get_scaled_qimage()
        if scaled_qimage is None:
            return

        # Set clipping region for efficient rendering
        painter.setClipRect(image_rect)

        # Draw background (only in visible region)
        self._draw_background_viewport(painter, image_rect)

        # Enable composition mode for proper transparency
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Draw only the visible portion of the image
        painter.drawImage(image_rect, scaled_qimage, image_rect)

        # Reset clipping to allow drawing grid lines on the exact edge of the image
        painter.setClipping(False)

        # Draw grid if visible and zoomed in enough (only in visible region)
        if self.grid_visible and self.zoom >= 4:
            self._draw_grid_viewport(painter, image_rect)

        # Draw tile grid if visible (8x8 tiles)
        if self.tile_grid_visible and self.zoom >= 1:
            self._draw_tile_grid_viewport(painter, image_rect)

        # Draw hover highlight without clipping restrictions
        if self.hover_pos and not self.drawing:
            painter.save()  # Save current painter state
            painter.setClipping(False)  # Remove clipping for hover highlight
            self._draw_hover_highlight(painter)
            painter.restore()  # Restore painter state

    def _calculate_visible_image_region(self, widget_rect: QRect) -> QRect:
        """Calculate the visible region in image coordinates."""
        # Note: controller.image_model is typed as always non-None.
        # Caller (paintEvent) checks has_image() before calling this method.
        image_model = self.controller.image_model

        # Get image dimensions
        height, width = image_model.data.shape
        scaled_width = width * self.zoom
        scaled_height = height * self.zoom

        # Intersect with actual image bounds
        image_bounds = QRect(0, 0, scaled_width, scaled_height)
        visible_region = widget_rect.intersected(image_bounds)

        return visible_region

    def _draw_background_viewport(self, painter: QPainter, rect: QRect) -> None:
        """Draw background only in visible region."""
        if self.background_type == "checkerboard":
            self._draw_checkerboard_pattern(painter, rect)
        elif self.background_type == "black":
            painter.fillRect(rect, Qt.GlobalColor.black)
        elif self.background_type == "white":
            painter.fillRect(rect, Qt.GlobalColor.white)
        elif self.background_type == "custom":
            painter.fillRect(rect, self.custom_background_color)

    def _draw_checkerboard_pattern(self, painter: QPainter, rect: QRect) -> None:
        """Draw checkerboard pattern in the given rectangle."""
        checker_size = 8
        light_color = QColor(220, 220, 220)
        dark_color = QColor(180, 180, 180)

        # Calculate checker bounds within visible rect
        start_x = (rect.x() // checker_size) * checker_size
        start_y = (rect.y() // checker_size) * checker_size
        end_x = rect.right() + checker_size
        end_y = rect.bottom() + checker_size

        for y in range(start_y, end_y, checker_size):
            for x in range(start_x, end_x, checker_size):
                # Skip if outside visible area
                if x >= rect.right() or y >= rect.bottom():
                    continue
                if x + checker_size <= rect.x() or y + checker_size <= rect.y():
                    continue

                # Alternate colors in checkerboard pattern
                if (x // checker_size + y // checker_size) % 2 == 0:
                    color = light_color
                else:
                    color = dark_color

                # Draw the checker square, clipped to visible area
                checker_rect = QRect(x, y, checker_size, checker_size)
                clipped_rect = checker_rect.intersected(rect)
                painter.fillRect(clipped_rect, color)

    def _draw_grid_viewport(self, painter: QPainter, rect: QRect) -> None:
        """Draw grid lines only in visible region using optimized batch drawing."""
        painter.setPen(QPen(QColor(64, 64, 64), 1))

        # Calculate grid bounds within visible rect
        start_x = (rect.x() // self.zoom) * self.zoom
        start_y = (rect.y() // self.zoom) * self.zoom
        end_x = rect.right() + self.zoom
        end_y = rect.bottom() + self.zoom

        # Collect all grid lines for batch drawing using QPointF objects
        lines: list[QPointF] = []

        # Vertical lines
        for x in range(start_x, end_x, self.zoom):
            if rect.x() <= x <= rect.right():
                lines.append(QPointF(x, rect.y()))
                lines.append(QPointF(x, rect.bottom()))

        # Horizontal lines
        for y in range(start_y, end_y, self.zoom):
            if rect.y() <= y <= rect.bottom():
                lines.append(QPointF(rect.x(), y))
                lines.append(QPointF(rect.right(), y))

        # Draw all lines at once using QPainter.drawLines() for maximum efficiency
        if lines:
            painter.drawLines(lines)

    def _draw_tile_grid_viewport(self, painter: QPainter, rect: QRect) -> None:
        """Draw 8x8 tile grid lines only in visible region using optimized batch drawing."""
        # Cyan color for tile grid to distinguish from pixel grid
        pen = QPen(QColor(0, 255, 255, 128), 1)
        # pen.setStyle(Qt.PenStyle.DashLine) # Optional: make it dashed
        painter.setPen(pen)

        # Tile size in pixels
        tile_size_px = 8
        scaled_tile_size = tile_size_px * self.zoom

        # Calculate grid bounds within visible rect
        # We add scaled_tile_size to end calculation to ensure we catch the bottom/right edge
        start_x = (rect.x() // scaled_tile_size) * scaled_tile_size
        start_y = (rect.y() // scaled_tile_size) * scaled_tile_size
        end_x = rect.right() + scaled_tile_size + 1
        end_y = rect.bottom() + scaled_tile_size + 1

        # Collect all grid lines for batch drawing using QPointF objects
        lines: list[QPointF] = []

        # Vertical lines
        for x in range(start_x, end_x, scaled_tile_size):
            # Allow drawing on the very edge (right + 1)
            if rect.x() <= x <= rect.right() + 1:
                lines.append(QPointF(x, rect.y()))
                lines.append(QPointF(x, rect.bottom() + 1))

        # Horizontal lines
        for y in range(start_y, end_y, scaled_tile_size):
            # Allow drawing on the very edge (bottom + 1)
            if rect.y() <= y <= rect.bottom() + 1:
                lines.append(QPointF(rect.x(), y))
                lines.append(QPointF(rect.right() + 1, y))

        # Draw all lines at once using QPainter.drawLines() for maximum efficiency
        if lines:
            painter.drawLines(lines)

    def _draw_hover_highlight(self, painter: QPainter) -> None:
        """Draw hover highlight with brush size preview."""
        if not self.hover_pos:
            return

        x, y = self.hover_pos.x(), self.hover_pos.y()

        # Get image dimensions
        image_model = self.controller.image_model
        height, width = image_model.data.shape

        # Get brush pixels from controller
        brush_pixels = self.controller.get_brush_pixels(x, y)

        # Draw highlight for each pixel in the brush area
        # Use a slightly thinner pen to avoid excessive overlap
        painter.setPen(QPen(QColor(255, 255, 0), 1))

        for px, py in brush_pixels:
            if 0 <= px < width and 0 <= py < height:
                # Draw the pixel area (subtract 1 from width/height for correct Qt rectangle)
                painter.drawRect(px * self.zoom, py * self.zoom, self.zoom - 1, self.zoom - 1)

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self._get_pixel_pos(event.position())
            if pos is not None:
                self.drawing = True
                self.last_draw_pos = pos
                self.pixelPressed.emit(pos.x(), pos.y())

        elif event.button() == Qt.MouseButton.RightButton:
            # Temporary color picker
            pos = self._get_pixel_pos(event.position())
            if pos is not None and self.controller.has_image():
                # Store current tool and temporarily switch to picker
                self.previous_tool = self.controller.get_current_tool_name()
                self.temporary_picker = True
                self.controller.set_tool("picker")
                self.pixelPressed.emit(pos.x(), pos.y())

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move with optimized hover updates."""
        # Update hover position with optimized partial repaints
        pos = self._get_pixel_pos(event.position())
        if pos != self.hover_pos:
            old_hover_pos = self.hover_pos
            self.hover_pos = pos

            # Only update the regions that need repainting
            self._update_hover_regions(old_hover_pos, pos)

        # Emit hover position changed signal
        if self.hover_pos is not None:
            self.hoverPositionChanged.emit(self.hover_pos.x(), self.hover_pos.y())

        # Handle drawing
        if self.drawing and pos is not None:
            self.last_draw_pos = pos
            self.pixelMoved.emit(pos.x(), pos.y())

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.drawing:
                self.drawing = False
                pos = self._get_pixel_pos(event.position())
                # Use last known position if release is outside canvas
                if pos is None and self.last_draw_pos is not None:
                    pos = self.last_draw_pos
                if pos is not None:
                    self.pixelReleased.emit(pos.x(), pos.y())
                self.last_draw_pos = None

        elif event.button() == Qt.MouseButton.RightButton and self.temporary_picker and self.previous_tool:
            # Restore previous tool after temporary picker
            self.controller.set_tool(self.previous_tool)
            self.temporary_picker = False
            self.previous_tool = None

    @override
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel for zooming."""
        delta = event.angleDelta().y()

        # Zoom levels
        zoom_levels = [1, 2, 4, 8, 16, 32, 64]

        # Find current index
        current_index = 0
        for i, level in enumerate(zoom_levels):
            if level <= self.zoom:
                current_index = i
            else:
                break

        # Calculate new zoom
        if delta > 0:
            new_index = min(current_index + 1, len(zoom_levels) - 1)
        else:
            new_index = max(current_index - 1, 0)

        new_zoom = zoom_levels[new_index]

        if new_zoom != self.zoom:
            # Update zoom
            self.zoom = new_zoom
            self._update_size()

            # Emit signal for UI update
            self.zoomRequested.emit(new_zoom)
            self.update()

        event.accept()

    @override
    def leaveEvent(self, event: QEvent) -> None:
        """Handle mouse leave event."""
        old_hover_pos = self.hover_pos
        self.hover_pos = None
        self._update_hover_regions(old_hover_pos, None)
        self.hoverPositionChanged.emit(-1, -1)

    def _get_pixel_pos(self, pos: QPointF) -> QPoint | None:
        """Convert mouse position to pixel coordinates."""
        if not self.controller.has_image():
            return None

        x = int(pos.x() // self.zoom)
        y = int(pos.y() // self.zoom)

        size = self.controller.get_image_size()
        if size:
            width, height = size
            if 0 <= x < width and 0 <= y < height:
                return QPoint(x, y)
        return None

    @override
    def enterEvent(self, event: QEnterEvent) -> None:
        """Show tooltip on enter and update cursor."""
        self.setToolTip("Left click: Draw • Right click: Pick color • Wheel: Zoom")
        # Update cursor for current tool
        current_tool = self.controller.get_current_tool_name()
        self._update_cursor_for_tool(current_tool)
        super().enterEvent(event)

    @override
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Event filter to catch mouse release outside widget during drawing."""
        if event.type() == QEvent.Type.MouseButtonRelease:
            mouse_event = event
            if isinstance(mouse_event, QMouseEvent) and mouse_event.button() == Qt.MouseButton.LeftButton:
                if self.drawing:
                    # Mouse released outside canvas during drawing - finalize stroke
                    self.drawing = False
                    # Use last known position
                    if self.last_draw_pos:
                        self.pixelReleased.emit(self.last_draw_pos.x(), self.last_draw_pos.y())
                    self.last_draw_pos = None
        return super().eventFilter(obj, event)
