#!/usr/bin/env python3
"""
Contextual preview widget for the sprite editor.
Displays sprite preview with configurable background options.
"""

from typing import override

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QResizeEvent
from PySide6.QtWidgets import QColorDialog, QComboBox, QLabel, QSizePolicy, QVBoxLayout, QWidget


class ContextualPreview(QWidget):
    """Preview widget with configurable background options."""

    # Signals
    backgroundChanged = Signal(str)  # "checkerboard", "black", "white", "custom"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # State
        self._current_image: QImage | None = None
        self._background_type = "checkerboard"
        self._custom_color = QColor(128, 128, 128)  # Default gray
        self._checkerboard_pattern: QPixmap | None = None

        # Setup UI
        self._setup_ui()

        # Generate checkerboard pattern
        self._create_checkerboard_pattern()

    def _setup_ui(self) -> None:
        """Setup the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Background selector dropdown
        self._background_combo = QComboBox()
        self._background_combo.addItems(["Checkerboard", "Black", "White", "Custom..."])
        self._background_combo.setCurrentIndex(0)
        self._background_combo.currentTextChanged.connect(self._on_background_changed)
        layout.addWidget(self._background_combo)

        # Preview area
        self._preview_label = QLabel()
        self._preview_label.setMinimumSize(200, 200)
        self._preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("QLabel { border: 1px solid #808080; background-color: #404040; }")
        layout.addWidget(self._preview_label)

        # Initial state
        self.clear_preview()

    def _create_checkerboard_pattern(self) -> None:
        """Create the checkerboard pattern pixmap."""
        checker_size = 8
        light_color = QColor(192, 192, 192)  # #C0C0C0
        dark_color = QColor(128, 128, 128)  # #808080

        # Create a small tile that we can repeat
        tile_size = checker_size * 2
        self._checkerboard_pattern = QPixmap(tile_size, tile_size)

        painter = QPainter(self._checkerboard_pattern)
        painter.fillRect(0, 0, checker_size, checker_size, light_color)
        painter.fillRect(checker_size, 0, checker_size, checker_size, dark_color)
        painter.fillRect(0, checker_size, checker_size, checker_size, dark_color)
        painter.fillRect(checker_size, checker_size, checker_size, checker_size, light_color)
        painter.end()

    def _on_background_changed(self, text: str) -> None:
        """Handle background selection change."""
        if text == "Custom...":
            # Show color dialog
            color = QColorDialog.getColor(self._custom_color, self, "Select Background Color")
            if color.isValid():
                self._custom_color = color
                self._background_type = "custom"
                self.backgroundChanged.emit("custom")
            else:
                # User cancelled - revert to previous selection
                if self._background_type == "checkerboard":
                    self._background_combo.setCurrentIndex(0)
                elif self._background_type == "black":
                    self._background_combo.setCurrentIndex(1)
                elif self._background_type == "white":
                    self._background_combo.setCurrentIndex(2)
                return
        else:
            bg_type = text.lower()
            self._background_type = bg_type
            self.backgroundChanged.emit(bg_type)

        # Update preview with current image
        if self._current_image:
            self.update_preview(self._current_image)

    def set_background(self, bg_type: str, custom_color: QColor | None = None) -> None:
        """Set the background type programmatically.

        Args:
            bg_type: One of "checkerboard", "black", "white", "custom"
            custom_color: Custom background color (required if bg_type is "custom")
        """
        self._background_type = bg_type.lower()

        if self._background_type == "custom" and custom_color:
            self._custom_color = custom_color

        # Update combo box without triggering signal
        self._background_combo.blockSignals(True)
        if self._background_type == "checkerboard":
            self._background_combo.setCurrentIndex(0)
        elif self._background_type == "black":
            self._background_combo.setCurrentIndex(1)
        elif self._background_type == "white":
            self._background_combo.setCurrentIndex(2)
        elif self._background_type == "custom":
            self._background_combo.setCurrentIndex(3)
        self._background_combo.blockSignals(False)

        # Update preview with current image
        if self._current_image:
            self.update_preview(self._current_image)

    def get_background_type(self) -> str:
        """Get the current background type.

        Returns:
            One of "checkerboard", "black", "white", "custom"
        """
        return self._background_type

    def update_preview(self, image: QImage | None) -> None:
        """Update the preview with a new image.

        Args:
            image: The image to display in the preview
        """
        if image is None or image.isNull():
            self.clear_preview()
            return

        self._current_image = image.copy()

        # Get preview area size
        preview_size = self._preview_label.size()
        if preview_size.width() <= 0 or preview_size.height() <= 0:
            preview_size = QSize(200, 200)

        # Calculate scaled size while preserving aspect ratio
        scaled_size = image.size().scaled(preview_size, Qt.AspectRatioMode.KeepAspectRatio)

        # Create a pixmap for the preview
        preview_pixmap = QPixmap(scaled_size)
        preview_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(preview_pixmap)

        # Draw background
        self._draw_background(painter, scaled_size)

        # Scale and draw the image on top
        scaled_image = image.scaled(
            scaled_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
        )

        # Center the image in the preview area
        x_offset = (scaled_size.width() - scaled_image.width()) // 2
        y_offset = (scaled_size.height() - scaled_image.height()) // 2
        painter.drawImage(x_offset, y_offset, scaled_image)

        painter.end()

        # Set the pixmap to the label
        self._preview_label.setPixmap(preview_pixmap)

    def _draw_background(self, painter: QPainter, size: QSize) -> None:
        """Draw the background pattern.

        Args:
            painter: The painter to draw with
            size: The size of the area to fill
        """
        if self._background_type == "checkerboard":
            # Draw tiled checkerboard pattern
            if self._checkerboard_pattern:
                # Use tiled drawing for efficiency
                for y in range(0, size.height(), self._checkerboard_pattern.height()):
                    for x in range(0, size.width(), self._checkerboard_pattern.width()):
                        painter.drawPixmap(x, y, self._checkerboard_pattern)
        elif self._background_type == "black":
            painter.fillRect(0, 0, size.width(), size.height(), Qt.GlobalColor.black)
        elif self._background_type == "white":
            painter.fillRect(0, 0, size.width(), size.height(), Qt.GlobalColor.white)
        elif self._background_type == "custom":
            painter.fillRect(0, 0, size.width(), size.height(), self._custom_color)

    def clear_preview(self) -> None:
        """Clear the preview and show placeholder text."""
        self._current_image = None
        self._preview_label.clear()
        self._preview_label.setText("No Preview")
        self._preview_label.setStyleSheet(
            "QLabel { border: 1px solid #808080; background-color: #404040; color: #C0C0C0; }"
        )

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize events to update the preview."""
        super().resizeEvent(event)
        # Re-render preview with new size
        if self._current_image:
            self.update_preview(self._current_image)
