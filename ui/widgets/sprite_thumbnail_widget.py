"""
Sprite thumbnail widget for gallery display.
Compact version of SpritePreviewWidget optimized for grid layouts.
"""

from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QEnterEvent, QFont, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.common.spacing_constants import SPACING_SMALL, SPACING_TINY
from ui.styles.theme import COLORS
from utils.logging_config import get_logger

logger = get_logger(__name__)


class SpriteThumbnailWidget(QWidget):
    """Compact sprite thumbnail for gallery display."""

    # Signals
    clicked = Signal(int)  # offset
    double_clicked = Signal(int)  # offset
    selected = Signal(bool)  # selection state

    def __init__(self, offset: int = 0, size: int = 384, parent: QWidget | None = None):
        """
        Initialize sprite thumbnail widget.

        Args:
            offset: ROM offset of the sprite
            size: Size of the thumbnail (square)
            parent: Parent widget
        """
        super().__init__(parent)

        self.offset = offset
        self.thumbnail_size = size
        self.sprite_pixmap: QPixmap | None = None
        self.is_selected = False
        self.is_hovered = False
        self.sprite_info: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny] - sprite metadata

        # Thumbnail display label
        self.thumbnail_label: QLabel | None = None

        # Info text
        self.offset_text = f"0x{offset:06X}"
        self.sprite_name = ""  # User-friendly name
        self.size_text = ""
        self.compression_text = ""

        self._setup_ui()

    def _setup_ui(self):
        """Setup the thumbnail UI."""
        # Adjust label height based on thumbnail size
        label_height = 40 if self.thumbnail_size >= 256 else 30

        self.setFixedSize(self.thumbnail_size, self.thumbnail_size + label_height)

        # Main layout with spacing from constants
        layout = QVBoxLayout()
        margin = SPACING_TINY if self.thumbnail_size >= 256 else SPACING_TINY // 2
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(SPACING_TINY)

        # Thumbnail display - leave room for label
        self.thumbnail_label = QLabel()
        thumb_width = self.thumbnail_size - (margin * 2)
        thumb_height = self.thumbnail_size - label_height - SPACING_TINY
        self.thumbnail_label.setFixedSize(thumb_width, thumb_height)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setStyleSheet(f"""
            QLabel {{
                background-color: {COLORS["input_background"]};
                border: 2px solid {COLORS["border"]};
                border-radius: {SPACING_TINY}px;
            }}
        """)
        # Don't use setScaledContents - it stretches and distorts sprites
        # We'll scale properly in set_sprite_data() with aspect ratio preserved
        self.thumbnail_label.setScaledContents(False)
        layout.addWidget(self.thumbnail_label)

        # Offset label - bigger font for larger thumbnails
        self.info_label = QLabel(self.offset_text)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font_size = "12px" if self.thumbnail_size >= 256 else "10px"
        self.info_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_secondary"]};
                font-size: {font_size};
                font-family: monospace;
                font-weight: bold;
            }}
        """)
        self.info_label.setMinimumHeight(label_height - SPACING_SMALL)
        layout.addWidget(self.info_label)

        self.setLayout(layout)

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        self.thumbnail_label.setMouseTracking(True)

        # Set tooltip
        self.setToolTip(f"Offset: {self.offset_text}")

    def set_sprite_data(self, pixmap: QPixmap, sprite_info: dict[str, object] | None = None):
        """
        Set the sprite thumbnail data.

        Args:
            pixmap: Sprite pixmap to display
            sprite_info: Optional sprite metadata
        """
        self.sprite_pixmap = pixmap

        if sprite_info:
            self.sprite_info = sprite_info
            self._update_info_display()

        # Scale pixmap to fit thumbnail
        if pixmap and not pixmap.isNull():
            label_size = self.thumbnail_label.size() if self.thumbnail_label else QSize(384, 384)
            scaled = pixmap.scaled(
                label_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            if self.thumbnail_label:
                self.thumbnail_label.setPixmap(scaled)
        else:
            # Show placeholder
            self._show_placeholder()

    def _show_placeholder(self):
        """Show a placeholder when no sprite is loaded."""
        label_size = self.thumbnail_label.size() if self.thumbnail_label else QSize(384, 384)
        placeholder = QPixmap(label_size)
        placeholder.fill(QColor(35, 35, 35))

        painter = QPainter(placeholder)

        # Draw a sprite icon pattern instead of "Loading..."
        center_x = placeholder.width() // 2
        center_y = placeholder.height() // 2

        # Draw pixel art style grid pattern
        grid_size = 8
        grid_color = QColor(50, 50, 50)
        painter.setPen(QPen(grid_color, 1))

        # Draw grid lines
        for i in range(0, placeholder.width(), grid_size):
            painter.drawLine(i, 0, i, placeholder.height())
        for i in range(0, placeholder.height(), grid_size):
            painter.drawLine(0, i, placeholder.width(), i)

        # Draw sprite icon in center
        icon_size = min(placeholder.width(), placeholder.height()) // 3
        painter.setPen(QPen(QColor(80, 80, 80), 2))
        painter.drawRect(center_x - icon_size // 2, center_y - icon_size // 2, icon_size, icon_size)

        # Draw "SPRITE" text
        painter.setPen(QPen(QColor(100, 100, 100)))
        font_size = max(8, min(14, placeholder.height() // 20))
        painter.setFont(QFont("Arial", font_size))
        painter.drawText(placeholder.rect(), Qt.AlignmentFlag.AlignCenter, "SPRITE")
        painter.end()

        if self.thumbnail_label:
            self.thumbnail_label.setPixmap(placeholder)

    def _update_info_display(self):
        """Update the info display based on sprite metadata."""
        if not self.sprite_info:
            return

        # Get sprite name if available
        if "name" in self.sprite_info:
            self.sprite_name = self.sprite_info["name"]
            # Show name as primary label with offset as secondary
            display_text = f"{self.sprite_name}\n{self.offset_text}"
        else:
            # Fall back to just offset
            display_text = self.offset_text

        if self.info_label:
            self.info_label.setText(display_text)

        # Update size text
        if "decompressed_size" in self.sprite_info:
            size_kb = self.sprite_info["decompressed_size"] / 1024
            self.size_text = f"{size_kb:.1f}KB"
        elif "size" in self.sprite_info:
            size_bytes = self.sprite_info["size"]
            if size_bytes > 1024:
                self.size_text = f"{size_bytes / 1024:.1f}KB"
            else:
                self.size_text = f"{size_bytes}B"

        # Update compression status
        if self.sprite_info.get("compressed", False):
            self.compression_text = "HAL"
        else:
            self.compression_text = "Raw"

        # Update tooltip with more details
        tooltip_parts = [
            f"Name: {self.sprite_name}" if self.sprite_name else "",
            f"Offset: {self.offset_text}",
            f"Size: {self.size_text}" if self.size_text else "",
            f"Type: {self.compression_text}" if self.compression_text else "",
        ]

        if "tile_count" in self.sprite_info:
            tooltip_parts.append(f"Tiles: {self.sprite_info['tile_count']}")

        if "width" in self.sprite_info and "height" in self.sprite_info:
            tooltip_parts.append(f"Dimensions: {self.sprite_info['width']}x{self.sprite_info['height']}")

        self.setToolTip("\n".join(filter(None, tooltip_parts)))

    def set_selected(self, selected: bool):
        """
        Set the selection state of the thumbnail.

        Args:
            selected: Whether the thumbnail is selected
        """
        self.is_selected = selected
        self._update_style()
        self.selected.emit(selected)

    def _update_style(self):
        """Update the visual style based on state."""
        if self.is_selected:
            border_color = COLORS["border_focus"]
            border_width = "2px"
            bg_color = COLORS["focus_background_subtle"]
        elif self.is_hovered:
            border_color = COLORS["text_muted"]
            border_width = "1px"
            bg_color = COLORS["panel_background"]
        else:
            border_color = COLORS["border"]
            border_width = "1px"
            bg_color = COLORS["input_background"]

        if self.thumbnail_label:
            self.thumbnail_label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                border: {border_width} solid {border_color};
                border-radius: 2px;
            }}
        """)

    @override
    def enterEvent(self, event: QEnterEvent) -> None:
        """Handle mouse enter event."""
        self.is_hovered = True
        self._update_style()
        super().enterEvent(event)

    @override
    def leaveEvent(self, event: QEvent) -> None:
        """Handle mouse leave event."""
        self.is_hovered = False
        self._update_style()
        super().leaveEvent(event)

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press event."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.offset)
            # Toggle selection on click
            self.set_selected(not self.is_selected)
        super().mousePressEvent(event)

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle double click event."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.offset)
        super().mouseDoubleClickEvent(event)

    def get_offset(self) -> int:
        """Get the sprite offset."""
        return self.offset

    def get_sprite_info(self) -> dict[str, object]:
        """Get the sprite metadata."""
        return self.sprite_info
