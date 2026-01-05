#!/usr/bin/env python3
"""
Preview panel for the pixel editor.
Shows current view and color preview of the image.
"""

from typing import TYPE_CHECKING, override

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from ...controllers.editing_controller import EditingController


class PreviewPanel(QWidget):
    """Panel showing preview of the current image."""

    def __init__(
        self,
        controller: "EditingController | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the preview panel UI."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Preview group box
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()

        # Main preview (current image)
        main_preview_label = QLabel("Image Preview:")
        main_preview_label.setStyleSheet("QLabel { font-weight: bold; }")
        preview_layout.addWidget(main_preview_label)

        self.main_preview = QLabel("No image loaded")
        self.main_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_preview.setStyleSheet("QLabel { border: 1px solid #999; background: #222; }")
        self.main_preview.setMinimumHeight(100)
        preview_layout.addWidget(self.main_preview)

        # Color preview (current selected color)
        color_preview_label = QLabel("Selected Color:")
        color_preview_label.setStyleSheet("QLabel { font-weight: bold; }")
        preview_layout.addWidget(color_preview_label)

        self.color_preview = QLabel()
        self.color_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.color_preview.setStyleSheet("QLabel { border: 1px solid #999; background: #222; }")
        self.color_preview.setMinimumHeight(60)
        preview_layout.addWidget(self.color_preview)

        preview_group.setLayout(preview_layout)

        # Add to main layout
        layout.addWidget(preview_group)

    def update_preview(self) -> None:
        """Update the main preview from controller image data."""
        if not self.controller or not self.controller.has_image():
            self.main_preview.clear()
            self.main_preview.setText("No image loaded")
            return

        # Convert indexed image data to QPixmap
        pixmap = self._create_pixmap_from_controller()
        if pixmap and not pixmap.isNull():
            # Scale to fit while maintaining aspect ratio
            scaled = pixmap.scaled(
                self.main_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self.main_preview.setPixmap(scaled)
        else:
            self.main_preview.clear()
            self.main_preview.setText("No image loaded")

    def update_color_preview(self, color_index: int) -> None:
        """Update the color preview to show the selected color."""
        if not self.controller:
            return

        # Get RGB color from palette
        colors = self.controller.palette_model.colors
        if 0 <= color_index < len(colors):
            r, g, b = colors[color_index]
            color = QColor(r, g, b)

            # Create solid color pixmap
            pixmap = QPixmap(self.color_preview.size())
            pixmap.fill(color)
            self.color_preview.setPixmap(pixmap)
        else:
            self.color_preview.clear()

    def _create_pixmap_from_controller(self) -> QPixmap | None:
        """Convert controller's image and palette data to a QPixmap."""
        if not self.controller:
            return None

        image_model = self.controller.image_model
        palette_model = self.controller.palette_model

        # Get image dimensions
        height, width = image_model.data.shape
        if width == 0 or height == 0:
            return None

        # Create color lookup table
        colors = palette_model.colors
        if len(colors) < 16:
            # Pad with black if needed
            colors = list(colors) + [(0, 0, 0)] * (16 - len(colors))

        # Convert indexed data to RGB using numpy
        image_data = np.clip(image_model.data, 0, 15).astype(np.uint8)
        rgb_data = np.zeros((height, width, 3), dtype=np.uint8)

        for i in range(16):
            mask = image_data == i
            if i < len(colors):
                r, g, b = colors[i]
                rgb_data[mask] = [r, g, b]

        # Create QImage with ARGB format for transparency support
        qimage = QImage(width, height, QImage.Format.Format_ARGB32)

        # Convert to ARGB format
        argb_data = np.zeros((height, width, 4), dtype=np.uint8)
        argb_data[:, :, 0] = rgb_data[:, :, 2]  # Blue
        argb_data[:, :, 1] = rgb_data[:, :, 1]  # Green
        argb_data[:, :, 2] = rgb_data[:, :, 0]  # Red

        # Handle transparency for index 0
        mask = image_data == 0
        argb_data[mask, 3] = 0  # Alpha = 0 (transparent)
        argb_data[~mask, 3] = 255  # Alpha = 255 (opaque)

        # Copy to QImage buffer
        buffer_ptr = qimage.bits()
        argb_bytes = argb_data.tobytes()
        buffer_ptr[: len(argb_bytes)] = argb_bytes  # type: ignore[reportIndexIssue]

        return QPixmap.fromImage(qimage)

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize events by updating the preview."""
        super().resizeEvent(event)
        self.update_preview()
