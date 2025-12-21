"""
Zoomable sprite preview widget for SpritePal
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from PySide6.QtCore import QPointF, QRectF, QSize, Qt

if TYPE_CHECKING:
    from PySide6.QtGui import (
        QColor,
        QMouseEvent,
        QPainter,
        QPen,
        QPixmap,
        QTransform,
        QWheelEvent,
    )
else:
    from PySide6.QtGui import (
        QColor,
        QMouseEvent,
        QPainter,
        QPen,
        QPixmap,
        QTransform,
        QWheelEvent,
    )
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.services.image_utils import pil_to_qpixmap
from ui.common.spacing_constants import (
    BORDER_THIN,
    MAX_ZOOM,
    PALETTE_SELECTOR_MIN_WIDTH,
    PREVIEW_MIN_SIZE,
    TILE_GRID_THICKNESS,
)
from ui.styles.theme import COLORS
from utils.constants import (
    MAX_BYTE_VALUE,
    PREVIEW_SCALE_FACTOR,
    TILE_WIDTH,
)

from .row_arrangement.palette_colorizer import PaletteColorizer


class ZoomablePreviewWidget(QWidget):
    """Widget for previewing sprites with zoom and pan functionality"""

    def __init__(self) -> None:
        super().__init__()
        self._pixmap = None
        self._tile_count = 0
        self._tiles_per_row = 0

        # Zoom and pan state
        self._zoom = 1.0
        self._min_zoom = 0.1
        self._max_zoom = MAX_ZOOM
        self._pan_offset = QPointF(0, 0)
        self._last_mouse_pos = None
        self._is_panning = False
        self._grid_visible = True

        self.setMinimumSize(QSize(PREVIEW_MIN_SIZE, PREVIEW_MIN_SIZE))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Set size policy to expand and fill available space
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.setStyleSheet(
            f"""
            ZoomablePreviewWidget {{
                background-color: {COLORS["preview_background"]};
                border: 1px solid {COLORS["border"]};
            }}
        """
        )

    @override
    def paintEvent(self, a0: Any) -> None:
        """Paint the preview with zoom and pan"""
        painter = QPainter(self)
        # Use a dark background for better contrast with sprites in dark theme
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        # Guard against null/zero-dimension pixmaps
        if self._pixmap is not None and self._pixmap.width() > 0 and self._pixmap.height() > 0:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            # Apply transformations
            transform = QTransform()

            # Center the image
            center_x = self.width() / 2
            center_y = self.height() / 2

            # Apply pan and zoom around center
            transform.translate(
                center_x + self._pan_offset.x(), center_y + self._pan_offset.y()
            )
            transform.scale(self._zoom, self._zoom)
            transform.translate(-self._pixmap.width() / 2, -self._pixmap.height() / 2)

            painter.setTransform(transform)

            # Draw checkerboard background for transparency visibility
            self._draw_checkerboard(painter, transform)

            painter.drawPixmap(0, 0, self._pixmap)

            # Reset transform for UI elements
            painter.resetTransform()

            # Draw zoom level indicator
            # Light gray text for visibility on dark background
            painter.setPen(QPen(QColor(200, 200, 200), BORDER_THIN))
            painter.setFont(painter.font())
            zoom_text = f"Zoom: {self._zoom:.1f}x"
            painter.drawText(10, 20, zoom_text)

            # Draw grid if zoomed in enough and grid is visible
            if self._zoom > 4.0 and self._grid_visible:
                self._draw_pixel_grid(painter, transform)

        else:
            # Draw helpful empty state placeholder
            # Muted text for visibility on dark background
            painter.setPen(QPen(QColor(100, 100, 100), PREVIEW_SCALE_FACTOR))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No sprites loaded",
            )

    def _draw_checkerboard(self, painter: Any, transform: Any) -> None:
        """Draw a checkerboard background for transparency visibility"""
        if self._pixmap is None:
            return

        # Create inverse transform to get visible area in image coordinates
        inv_transform, _ = transform.inverted()

        # Get visible rectangle in image coordinates
        visible_rect = inv_transform.mapRect(QRectF(self.rect()))

        # Limit drawing to visible area
        left = max(0, int(visible_rect.left()))
        right = min(self._pixmap.width(), int(visible_rect.right()) + 1)
        top = max(0, int(visible_rect.top()))
        bottom = min(self._pixmap.height(), int(visible_rect.bottom()) + 1)

        # Draw checkerboard pattern
        tile_size = max(1, int(TILE_WIDTH / self._zoom))  # Adjust tile size based on zoom

        for y in range(top, bottom, tile_size):
            for x in range(left, right, tile_size):
                # Alternate colors - use white and light gray for better contrast
                if (x // tile_size + y // tile_size) % 2 == 0:
                    painter.fillRect(x, y, tile_size, tile_size, QColor(255, 255, 255))
                else:
                    painter.fillRect(x, y, tile_size, tile_size, QColor(220, 220, 220))

    def _draw_pixel_grid(self, painter: Any, transform: Any) -> None:
        """Draw a pixel grid when zoomed in"""
        if self._pixmap is None:
            return

        # Create inverse transform to get visible area in image coordinates
        inv_transform, _ = transform.inverted()

        # Get visible rectangle in image coordinates
        visible_rect = inv_transform.mapRect(QRectF(self.rect()))

        # Limit grid drawing to visible area
        left = max(0, int(visible_rect.left()))
        right = min(self._pixmap.width(), int(visible_rect.right()) + 1)
        top = max(0, int(visible_rect.top()))
        bottom = min(self._pixmap.height(), int(visible_rect.bottom()) + 1)

        # Draw grid - use lighter color for better visibility on dark background
        painter.setPen(QPen(QColor(120, 120, 120), TILE_GRID_THICKNESS))

        # Vertical lines
        for x in range(left, right + 1):
            p1 = transform.map(QPointF(x, top))
            p2 = transform.map(QPointF(x, bottom))
            painter.drawLine(p1, p2)

        # Horizontal lines
        for y in range(top, bottom + 1):
            p1 = transform.map(QPointF(left, y))
            p2 = transform.map(QPointF(right, y))
            painter.drawLine(p1, p2)

    @override
    def wheelEvent(self, a0: QWheelEvent | None) -> None:
        """Handle mouse wheel for zooming"""
        if self._pixmap is None or not a0:
            return

        # Get mouse position in widget coordinates
        mouse_pos = a0.position()

        # Calculate zoom factor
        zoom_factor = 1.1 if a0.angleDelta().y() > 0 else 0.9
        new_zoom = self._zoom * zoom_factor

        # Clamp zoom
        new_zoom = max(self._min_zoom, min(self._max_zoom, new_zoom))

        if new_zoom != self._zoom:
            # Get the current transformation matrix
            center_x = self.width() / 2
            center_y = self.height() / 2

            # Create the current transform
            current_transform = QTransform()
            current_transform.translate(
                center_x + self._pan_offset.x(), center_y + self._pan_offset.y()
            )
            current_transform.scale(self._zoom, self._zoom)
            current_transform.translate(
                -self._pixmap.width() / 2, -self._pixmap.height() / 2
            )

            # Transform mouse position to image coordinates
            inv_transform, _ = current_transform.inverted()
            image_pos = inv_transform.map(mouse_pos)

            # Apply new zoom
            self._zoom = new_zoom

            # Create new transform with updated zoom
            new_transform = QTransform()
            new_transform.translate(
                center_x + self._pan_offset.x(), center_y + self._pan_offset.y()
            )
            new_transform.scale(self._zoom, self._zoom)
            new_transform.translate(
                -self._pixmap.width() / 2, -self._pixmap.height() / 2
            )

            # Find where the image point would be with new transform
            new_widget_pos = new_transform.map(image_pos)

            # Adjust pan offset to keep image point under cursor
            self._pan_offset.setX(
                self._pan_offset.x() + mouse_pos.x() - new_widget_pos.x()
            )
            self._pan_offset.setY(
                self._pan_offset.y() + mouse_pos.y() - new_widget_pos.y()
            )

            self.update()

    @override
    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        """Handle mouse press for panning"""
        if a0 and a0.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._is_panning = True
            self._last_mouse_pos = a0.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif a0 and a0.button() == Qt.MouseButton.RightButton:
            # Right click to reset view
            self.reset_view()

    @override
    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        """Handle mouse release"""
        if a0 and a0.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._is_panning = False
            self.setCursor(Qt.CursorShape.CrossCursor)

    @override
    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        """Handle mouse move for panning"""
        if a0 and self._is_panning and self._last_mouse_pos is not None:
            delta = a0.position() - self._last_mouse_pos
            self._pan_offset += delta
            self._last_mouse_pos = a0.position()
            self.update()

    @override
    def keyPressEvent(self, a0: Any) -> None:
        """Handle keyboard input"""
        if a0.key() == Qt.Key.Key_G:
            self._grid_visible = not self._grid_visible
            self.update()
        elif a0.key() == Qt.Key.Key_F:
            # F: Zoom to fit
            self.zoom_to_fit()
        elif a0.key() == Qt.Key.Key_0:
            if a0.modifiers() == Qt.KeyboardModifier.ControlModifier:
                # Ctrl+0: Reset zoom to default (4x zoom for pixel art)
                self._zoom = 4.0
                self._pan_offset = QPointF(0, 0)
                self.update()
            elif a0.modifiers() == (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
            ):
                # Ctrl+Shift+0: Zoom to fit
                self.zoom_to_fit()
        else:
            super().keyPressEvent(a0)

    def set_preview(
        self, pixmap: Any, tile_count: int = 0, tiles_per_row: int = 0
    ) -> None:
        """Set the preview pixmap"""
        self._pixmap = pixmap
        self._tile_count = tile_count
        self._tiles_per_row = tiles_per_row
        self.reset_view()

    def update_pixmap(self, pixmap: Any) -> None:
        """Update the preview pixmap without resetting view"""
        self._pixmap = pixmap
        self.update()

    def set_preview_from_file(self, file_path: str) -> None:
        """Load preview from file"""
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            self.set_preview(pixmap)

    def clear(self) -> None:
        """Clear the preview"""
        self._pixmap = None
        self._tile_count = 0
        self._tiles_per_row = 0
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self.update()

    def get_tile_info(self) -> tuple[int, int]:
        """Get tile information"""
        return self._tile_count, self._tiles_per_row

    def reset_view(self) -> None:
        """Reset zoom and pan to default"""
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self.update()

    def zoom_to_fit(self) -> None:
        """Zoom to fit the image in the widget"""
        # Guard against null/zero-dimension pixmaps
        if self._pixmap is None or self._pixmap.width() == 0 or self._pixmap.height() == 0:
            return

        # Calculate scale to fit
        scale_x = self.width() / self._pixmap.width()
        scale_y = self.height() / self._pixmap.height()
        self._zoom = min(scale_x, scale_y) * 0.9  # 90% to leave some margin
        self._pan_offset = QPointF(0, 0)
        self.update()

class PreviewPanel(QWidget):
    """Panel containing the zoomable preview with controls"""

    def __init__(self) -> None:
        super().__init__()
        self._grayscale_image = None
        self._colorized_image = None
        self._apply_transparency = True  # Toggle for transparency

        # Initialize colorizer component
        self.colorizer = PaletteColorizer()

        # Connect colorizer signals
        _ = self.colorizer.palette_mode_changed.connect(
            self._on_colorizer_palette_mode_changed
        )
        _ = self.colorizer.palette_index_changed.connect(
            self._on_colorizer_palette_index_changed
        )

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Set size policy to expand and fill available space
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Preview widget
        self.preview = ZoomablePreviewWidget()
        layout.addWidget(self.preview, 1)  # Give stretch factor of 1 to expand

        # Control buttons
        controls = QHBoxLayout()
        controls.setContentsMargins(5, 5, 5, 5)

        # Palette application controls
        self.palette_toggle = QCheckBox("Apply Palette")
        if self.palette_toggle:
            self.palette_toggle.setChecked(False)
        _ = self.palette_toggle.toggled.connect(self._on_palette_toggle)

        # Transparency toggle
        self.transparency_toggle = QCheckBox("Transparency")
        if self.transparency_toggle:
            self.transparency_toggle.setChecked(True)
        self.transparency_toggle.setToolTip("Toggle transparency for palette index 0")
        _ = self.transparency_toggle.toggled.connect(self._on_transparency_toggle)

        self.palette_selector = QComboBox(self)
        self.palette_selector.setMinimumWidth(PALETTE_SELECTOR_MIN_WIDTH)
        if self.palette_selector:
            self.palette_selector.setEnabled(False)
        _ = self.palette_selector.currentTextChanged.connect(self._on_palette_changed)

        # Populate palette selector
        for i in range(8, 16):
            if self.palette_selector:
                self.palette_selector.addItem(f"Palette {i}", i)

        # Zoom controls
        self.zoom_fit_btn = QPushButton("Fit")
        _ = self.zoom_fit_btn.clicked.connect(self.preview.zoom_to_fit)
        self.zoom_fit_btn.setMaximumWidth(60)

        self.zoom_reset_btn = QPushButton("1:1")
        _ = self.zoom_reset_btn.clicked.connect(self.preview.reset_view)
        self.zoom_reset_btn.setMaximumWidth(60)

        # Help text - slightly larger for readability
        help_label = QLabel(
            "Scroll: Zoom | Drag/MMB: Pan | Right-click: Reset | G: Grid | C: Palette | Ctrl+0: 4x | Ctrl+Shift+0: Fit"
        )
        help_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")

        controls.addWidget(self.palette_toggle)
        controls.addWidget(self.palette_selector)
        controls.addWidget(self.transparency_toggle)
        controls.addWidget(QLabel("|"))  # Separator
        controls.addWidget(self.zoom_fit_btn)
        controls.addWidget(self.zoom_reset_btn)
        controls.addWidget(help_label)
        controls.addStretch()

        layout.addLayout(controls)

    def _on_palette_toggle(self, checked: bool) -> None:
        """Handle palette toggle"""
        # Only toggle if the state differs from colorizer
        if checked != self.colorizer.is_palette_mode():
            self.colorizer.toggle_palette_mode()

        if self.palette_selector:
            self.palette_selector.setEnabled(checked)

        if checked and self._grayscale_image and self.colorizer.has_palettes():
            self._apply_current_palette()
        elif not checked:
            self._show_grayscale()

    def _on_transparency_toggle(self, checked: bool) -> None:
        """Handle transparency toggle"""
        self._apply_transparency = checked
        # Refresh the display with new transparency setting
        if self.palette_toggle.isChecked() and self._grayscale_image:
            self._apply_current_palette()
        elif self._grayscale_image:
            self._show_grayscale()

    def _on_palette_changed(self, palette_name: str) -> None:
        """Handle palette selection change"""
        if (
            self.palette_toggle.isChecked()
            and self._grayscale_image
            and self.colorizer.has_palettes()
        ):
            # Update colorizer's selected palette
            palette_index = self.palette_selector.currentData()
            if palette_index:
                self.colorizer.set_selected_palette(palette_index)
                self._apply_current_palette()

    def _apply_current_palette(self) -> None:
        """Apply the currently selected palette to the grayscale image"""
        if not self._grayscale_image or not self.colorizer.has_palettes():
            return

        # Get colorized image from colorizer
        self._colorized_image = self.colorizer.get_display_image(
            0, self._grayscale_image
        )

        # Update preview with colorized image
        if self._colorized_image:
            pixmap = self._pil_to_pixmap(self._colorized_image)
            self.preview.update_pixmap(pixmap)

    def _show_grayscale(self) -> None:
        """Show the grayscale version of the image"""
        if self._grayscale_image:
            # Convert grayscale to RGBA for transparency
            rgba_image = self._grayscale_image.convert("RGBA")
            pixels = rgba_image.load()
            width, height = rgba_image.size

            # Make palette index 0 transparent
            for y in range(height):
                for x in range(width):
                    pixel_value = self._grayscale_image.getpixel((x, y))
                    # For palette mode images, pixel value is already the palette index
                    if self._grayscale_image.mode == "P":
                        palette_index = pixel_value
                    else:
                        # For grayscale images, map to palette index
                        palette_index = min(15, pixel_value // 16)

                    if palette_index == 0 and self._apply_transparency:
                        # Set transparent pixel only if transparency is enabled
                        pixels[x, y] = (0, 0, 0, 0)
                    else:
                        # Keep grayscale value with full alpha
                        gray_value = (
                            pixel_value
                            if self._grayscale_image.mode != "P"
                            else (pixel_value * MAX_BYTE_VALUE) // 15
                        )
                        # Ensure non-zero pixels are visible even if index is 0
                        if palette_index == 0 and not self._apply_transparency:
                            # Show palette 0 as dark gray instead of transparent
                            pixels[x, y] = (64, 64, 64, MAX_BYTE_VALUE)
                        else:
                            pixels[x, y] = (gray_value, gray_value, gray_value, MAX_BYTE_VALUE)

            pixmap = self._pil_to_pixmap(rgba_image)
            self.preview.update_pixmap(pixmap)

    def set_preview(
        self, pixmap: Any, tile_count: int = 0, tiles_per_row: int = 0
    ) -> None:
        """Set the preview pixmap"""
        self.preview.set_preview(pixmap, tile_count, tiles_per_row)

    def update_preview(
        self, pixmap: Any, tile_count: int = 0, tiles_per_row: int = 0
    ) -> None:
        """Update the preview pixmap without resetting view (for real-time updates)"""
        self.preview.update_pixmap(pixmap)
        # Update tile info if provided
        if tile_count > 0:
            self.preview._tile_count = tile_count
        if tiles_per_row > 0:
            self.preview._tiles_per_row = tiles_per_row

    def set_preview_from_file(self, file_path: str) -> None:
        """Load preview from file"""
        self.preview.set_preview_from_file(file_path)

    def clear(self) -> None:
        """Clear the preview"""
        self._grayscale_image = None
        self._colorized_image = None
        self.colorizer.set_palettes({})  # Clear palettes
        if self.colorizer.is_palette_mode():
            self.colorizer.toggle_palette_mode()  # Turn off palette mode
        if self.palette_toggle:
            self.palette_toggle.setChecked(False)
        if self.palette_selector:
            self.palette_selector.setEnabled(False)
        if self.preview:
            self.preview.clear()

    def clear_preview(self) -> None:
        """Clear the preview (alias for clear)"""
        self.clear()

    def get_tile_info(self) -> tuple[int, int]:
        """Get tile information from the preview widget"""
        return self.preview.get_tile_info()

    def set_grayscale_image(self, pil_image: Any) -> None:
        """Set the grayscale PIL image for palette application"""
        self._grayscale_image = pil_image

    def set_palettes(self, palettes_dict: Any) -> None:
        """Set the available palettes"""
        self.colorizer.set_palettes(palettes_dict)

        # Enable palette controls if we have both image and palettes
        has_data = self._grayscale_image is not None and self.colorizer.has_palettes()
        if self.palette_toggle:
            self.palette_toggle.setEnabled(has_data)

        if self.palette_toggle.isChecked() and has_data:
            self._apply_current_palette()

    def _pil_to_pixmap(self, pil_image: Any) -> Any | None:
        """Convert PIL image to QPixmap using enhanced utility function"""
        return pil_to_qpixmap(pil_image)

    @override
    def keyPressEvent(self, a0: Any) -> None:
        """Handle keyboard input"""
        if a0.key() == Qt.Key.Key_C:
            # Toggle palette application
            if self.palette_toggle:
                self.palette_toggle.setChecked(not self.palette_toggle.isChecked())
        else:
            super().keyPressEvent(a0)

    def _on_colorizer_palette_mode_changed(self, enabled: bool) -> None:
        """Handle palette mode change from colorizer"""
        # Update UI to reflect colorizer state
        if self.palette_toggle:
            self.palette_toggle.setChecked(enabled)
        if self.palette_selector:
            self.palette_selector.setEnabled(enabled)

    def _on_colorizer_palette_index_changed(self, index: int) -> None:
        """Handle palette index change from colorizer"""
        # Update selector to match colorizer state
        for i in range(self.palette_selector.count()):
            if self.palette_selector.itemData(i) == index:
                self.palette_selector.setCurrentIndex(i)
                break

    @override
    def mousePressEvent(self, a0: Any) -> None:
        """Handle mouse press to ensure focus"""
        self.setFocus()
        super().mousePressEvent(a0)

    def get_palettes(self) -> dict[int, list[tuple[int, int, int]]]:
        """Get the current palette data

        Returns:
            Dictionary mapping palette index to RGB color lists
        """
        return self.colorizer.get_palettes() if self.colorizer else {}
