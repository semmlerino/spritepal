"""Base overlay canvas for frame mapping views.

Provides shared rendering logic for displaying game frames with AI frame overlays.
Subclasses implement specific interaction behaviors (drag, keyboard, read-only).
"""

from __future__ import annotations

from typing import override

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from ui.frame_mapping.views.canvas_utils import draw_checkerboard


class BaseOverlayCanvas(QWidget):
    """Base class for overlay canvas widgets.

    Provides common rendering logic for displaying a game frame with an AI frame
    overlaid at a specified offset with flip and opacity transforms.

    Subclasses should:
    - Call super().__init__() with appropriate parameters
    - Optionally override _get_empty_message() for custom placeholder text
    - Optionally override paintEvent() to add extra visual elements (call super first)
    """

    def __init__(
        self,
        canvas_size: int,
        display_scale: int,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the overlay canvas.

        Args:
            canvas_size: Minimum size of the canvas (both width and height)
            display_scale: Scale factor for display (e.g., 4 = 4x zoom)
            parent: Parent widget
        """
        super().__init__(parent)
        self._canvas_size = canvas_size
        self._display_scale = display_scale
        self._game_pixmap: QPixmap | None = None
        self._ai_pixmap: QPixmap | None = None
        self._offset_x = 0
        self._offset_y = 0
        self._flip_h = False
        self._flip_v = False
        self._opacity = 0.5

        self.setMinimumSize(canvas_size, canvas_size)
        self.setStyleSheet("background-color: #1a1a1a;")

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_game_frame(self, pixmap: QPixmap | None) -> None:
        """Set the game frame (background).

        Args:
            pixmap: QPixmap to display as background, or None to clear
        """
        self._game_pixmap = pixmap
        self.update()

    def set_ai_frame(self, pixmap: QPixmap | None) -> None:
        """Set the AI frame (overlay).

        Args:
            pixmap: QPixmap to display as overlay, or None to clear
        """
        self._ai_pixmap = pixmap
        self.update()

    def set_offset(self, x: int, y: int) -> None:
        """Set the offset for the AI frame overlay.

        Args:
            x: Horizontal offset in sprite pixels
            y: Vertical offset in sprite pixels
        """
        self._offset_x = x
        self._offset_y = y
        self.update()

    def set_flip(self, flip_h: bool, flip_v: bool) -> None:
        """Set the flip state for the AI frame overlay.

        Args:
            flip_h: Whether to flip horizontally
            flip_v: Whether to flip vertically
        """
        self._flip_h = flip_h
        self._flip_v = flip_v
        self.update()

    def set_opacity(self, opacity: float) -> None:
        """Set the opacity for the AI frame overlay.

        Args:
            opacity: Opacity value from 0.0 (transparent) to 1.0 (opaque)
        """
        self._opacity = max(0.0, min(1.0, opacity))
        self.update()

    def get_offset(self) -> tuple[int, int]:
        """Get the current offset.

        Returns:
            Tuple of (offset_x, offset_y)
        """
        return self._offset_x, self._offset_y

    # -------------------------------------------------------------------------
    # Protected API for Subclasses
    # -------------------------------------------------------------------------

    def _get_empty_message(self) -> str:
        """Get the message to display when no frames are loaded.

        Override in subclasses for custom placeholder text.

        Returns:
            Message string to display
        """
        return "No frames loaded"

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    @override
    def paintEvent(self, event: object) -> None:
        """Paint the overlay composite.

        Draws checkerboard background, game frame, AI frame with transforms,
        and frame border. Subclasses can override to add additional elements
        (e.g., focus indicator) after calling super().
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        canvas_center_x = self.width() // 2
        canvas_center_y = self.height() // 2

        # Draw checkerboard background
        draw_checkerboard(painter, self.width(), self.height())

        # Handle empty state
        if self._game_pixmap is None and self._ai_pixmap is None:
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._get_empty_message())
            return

        # Determine frame size (prefer game frame dimensions)
        if self._game_pixmap is not None:
            frame_width = self._game_pixmap.width()
            frame_height = self._game_pixmap.height()
        elif self._ai_pixmap is not None:
            frame_width = self._ai_pixmap.width()
            frame_height = self._ai_pixmap.height()
        else:
            return

        scaled_width = frame_width * self._display_scale
        scaled_height = frame_height * self._display_scale

        x_start = canvas_center_x - scaled_width // 2
        y_start = canvas_center_y - scaled_height // 2

        # Draw game frame (background)
        if self._game_pixmap is not None:
            scaled_game = self._game_pixmap.scaled(
                scaled_width,
                scaled_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            painter.drawPixmap(x_start, y_start, scaled_game)

        # Draw AI frame (overlay with offset and flip)
        if self._ai_pixmap is not None:
            ai_pixmap = self._ai_pixmap

            # Apply flips
            if self._flip_h or self._flip_v:
                transform = QTransform()
                transform.scale(-1 if self._flip_h else 1, -1 if self._flip_v else 1)
                ai_pixmap = ai_pixmap.transformed(transform)

            # Scale AI frame at its natural size
            ai_scaled_width = ai_pixmap.width() * self._display_scale
            ai_scaled_height = ai_pixmap.height() * self._display_scale
            scaled_ai = ai_pixmap.scaled(
                ai_scaled_width,
                ai_scaled_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )

            # Apply offset (scaled)
            offset_x_scaled = self._offset_x * self._display_scale
            offset_y_scaled = self._offset_y * self._display_scale

            painter.setOpacity(self._opacity)
            painter.drawPixmap(x_start + offset_x_scaled, y_start + offset_y_scaled, scaled_ai)
            painter.setOpacity(1.0)

        # Draw frame border
        painter.setPen(Qt.GlobalColor.darkGray)
        painter.drawRect(x_start - 1, y_start - 1, scaled_width + 1, scaled_height + 1)
