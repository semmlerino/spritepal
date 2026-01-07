#!/usr/bin/env python3
"""
Preview panel for the pixel editor.
Shows current sprite preview with configurable background options.
"""

from typing import TYPE_CHECKING, override

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtGui import QImage, QResizeEvent
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget

from ..widgets.contextual_preview import ContextualPreview

if TYPE_CHECKING:
    from ...controllers.editing_controller import EditingController


class PreviewPanel(QWidget):
    """Panel showing preview of the current image with background options."""

    # Signals
    backgroundChanged = Signal(str)  # "checkerboard", "black", "white", "custom"

    def __init__(
        self,
        controller: "EditingController | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._preview_widget: ContextualPreview | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the preview panel UI."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Preview group box
        preview_group = QGroupBox("REAL-TIME PREVIEW")
        preview_layout = QVBoxLayout()

        # Create ContextualPreview widget
        self._preview_widget = ContextualPreview()
        self._preview_widget.setMinimumHeight(220)
        preview_layout.addWidget(self._preview_widget)

        # Forward the backgroundChanged signal
        self._preview_widget.backgroundChanged.connect(self.backgroundChanged.emit)

        preview_group.setLayout(preview_layout)

        # Add to main layout
        layout.addWidget(preview_group)

    def update_preview(self) -> None:
        """Update the main preview from controller image data."""
        if not self._preview_widget:
            return

        if not self.controller or not self.controller.has_image():
            self._preview_widget.clear_preview()
            return

        # Convert indexed image data to QImage
        qimage = self._create_qimage_from_controller()
        if qimage and not qimage.isNull():
            self._preview_widget.update_preview(qimage)
        else:
            self._preview_widget.clear_preview()

    def _create_qimage_from_controller(self) -> QImage | None:
        """Convert controller's image and palette data to a QImage.

        Returns:
            QImage with ARGB format, or None if no valid image data
        """
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

        return qimage

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize events by updating the preview."""
        super().resizeEvent(event)
        self.update_preview()
