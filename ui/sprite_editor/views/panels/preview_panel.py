#!/usr/bin/env python3
"""
Preview panel for the pixel editor.
Shows current view and color preview of the image.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget


class PreviewPanel(QWidget):
    """Panel showing preview of the current image."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the preview panel UI."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Preview group box
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()

        # Main preview (changes based on mode)
        main_preview_label = QLabel("Current View:")
        main_preview_label.setStyleSheet("QLabel { font-weight: bold; }")
        preview_layout.addWidget(main_preview_label)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("QLabel { background-color: #202020; }")
        self.preview_label.setMinimumHeight(100)
        preview_layout.addWidget(self.preview_label)

        # Color preview (always shows colored version)
        color_preview_label = QLabel("With Colors:")
        color_preview_label.setStyleSheet("QLabel { font-weight: bold; }")
        preview_layout.addWidget(color_preview_label)

        self.color_preview_label = QLabel()
        self.color_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.color_preview_label.setStyleSheet(
            "QLabel { background-color: #202020; border: 2px solid #666; }"
        )
        self.color_preview_label.setMinimumHeight(100)
        preview_layout.addWidget(self.color_preview_label)

        preview_group.setLayout(preview_layout)

        # Add to main layout
        layout.addWidget(preview_group)

    def set_main_preview(self, pixmap: QPixmap) -> None:
        """Set the main preview image."""
        if pixmap and not pixmap.isNull():
            # Scale to fit while maintaining aspect ratio
            scaled = pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self.preview_label.setPixmap(scaled)
        else:
            self.preview_label.clear()

    def set_color_preview(self, pixmap: QPixmap) -> None:
        """Set the color preview image."""
        if pixmap and not pixmap.isNull():
            # Scale to fit while maintaining aspect ratio
            scaled = pixmap.scaled(
                self.color_preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self.color_preview_label.setPixmap(scaled)
        else:
            self.color_preview_label.clear()

    def clear_previews(self) -> None:
        """Clear both preview images."""
        self.preview_label.clear()
        self.color_preview_label.clear()
