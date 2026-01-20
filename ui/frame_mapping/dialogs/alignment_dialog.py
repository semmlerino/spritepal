"""Dialog for adjusting overlay alignment between AI and game frames."""

from __future__ import annotations

from pathlib import Path
from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.components.base.dialog_base import DialogBase

# Preview canvas size
CANVAS_SIZE = 400
# Scale factor for display
DISPLAY_SCALE = 4


class OverlayCanvas(QWidget):
    """Canvas widget that displays game frame with AI frame overlaid."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._game_pixmap: QPixmap | None = None
        self._ai_pixmap: QPixmap | None = None
        self._offset_x = 0
        self._offset_y = 0
        self._flip_h = False
        self._flip_v = False
        self._opacity = 0.5
        self.setMinimumSize(CANVAS_SIZE, CANVAS_SIZE)
        self.setStyleSheet("background-color: #1a1a1a;")

    def set_game_frame(self, pixmap: QPixmap | None) -> None:
        """Set the game frame (background)."""
        self._game_pixmap = pixmap
        self.update()

    def set_ai_frame(self, pixmap: QPixmap | None) -> None:
        """Set the AI frame (overlay)."""
        self._ai_pixmap = pixmap
        self.update()

    def set_offset(self, x: int, y: int) -> None:
        """Set the offset for the AI frame overlay."""
        self._offset_x = x
        self._offset_y = y
        self.update()

    def set_flip(self, flip_h: bool, flip_v: bool) -> None:
        """Set the flip state for the AI frame overlay."""
        self._flip_h = flip_h
        self._flip_v = flip_v
        self.update()

    def set_opacity(self, opacity: float) -> None:
        """Set the opacity for the AI frame overlay (0.0 to 1.0)."""
        self._opacity = max(0.0, min(1.0, opacity))
        self.update()

    @override
    def paintEvent(self, event: object) -> None:
        """Paint the overlay composite."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        # Calculate centering offset
        canvas_center_x = self.width() // 2
        canvas_center_y = self.height() // 2

        # Draw checkerboard background
        self._draw_checkerboard(painter)

        if self._game_pixmap is None and self._ai_pixmap is None:
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No frames loaded")
            return

        # Determine the frame size (prefer game frame dimensions)
        if self._game_pixmap is not None:
            frame_width = self._game_pixmap.width()
            frame_height = self._game_pixmap.height()
        elif self._ai_pixmap is not None:
            frame_width = self._ai_pixmap.width()
            frame_height = self._ai_pixmap.height()
        else:
            return

        # Scale up for visibility
        scaled_width = frame_width * DISPLAY_SCALE
        scaled_height = frame_height * DISPLAY_SCALE

        # Calculate top-left position to center the frame
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

            scaled_ai = ai_pixmap.scaled(
                scaled_width,
                scaled_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )

            # Apply offset (scaled)
            offset_x_scaled = self._offset_x * DISPLAY_SCALE
            offset_y_scaled = self._offset_y * DISPLAY_SCALE

            painter.setOpacity(self._opacity)
            painter.drawPixmap(x_start + offset_x_scaled, y_start + offset_y_scaled, scaled_ai)
            painter.setOpacity(1.0)

        # Draw frame border
        painter.setPen(Qt.GlobalColor.darkGray)
        painter.drawRect(x_start - 1, y_start - 1, scaled_width + 1, scaled_height + 1)

    def _draw_checkerboard(self, painter: QPainter) -> None:
        """Draw a checkerboard background pattern."""
        cell_size = 16
        colors = [Qt.GlobalColor.darkGray, Qt.GlobalColor.gray]

        for y in range(0, self.height(), cell_size):
            for x in range(0, self.width(), cell_size):
                color_index = ((x // cell_size) + (y // cell_size)) % 2
                painter.fillRect(x, y, cell_size, cell_size, colors[color_index])


class AlignmentDialog(DialogBase):
    """Dialog for adjusting overlay alignment between AI and game frames.

    Allows the user to adjust the position and flip state of an AI frame
    relative to a game frame for deterministic sprite replacement.

    Signals:
        alignment_changed: Emitted when alignment values change (offset_x, offset_y, flip_h, flip_v)
    """

    alignment_changed = Signal(int, int, bool, bool)

    def __init__(
        self,
        game_frame_pixmap: QPixmap | None,
        ai_frame_path: Path | None,
        initial_offset_x: int = 0,
        initial_offset_y: int = 0,
        initial_flip_h: bool = False,
        initial_flip_v: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the alignment dialog.

        Args:
            game_frame_pixmap: QPixmap of the game frame (background)
            ai_frame_path: Path to the AI frame image (overlay)
            initial_offset_x: Initial X offset value
            initial_offset_y: Initial Y offset value
            initial_flip_h: Initial horizontal flip state
            initial_flip_v: Initial vertical flip state
            parent: Parent widget
        """
        self._game_pixmap = game_frame_pixmap
        self._ai_pixmap: QPixmap | None = None
        if ai_frame_path is not None and ai_frame_path.exists():
            self._ai_pixmap = QPixmap(str(ai_frame_path))
            if self._ai_pixmap.isNull():
                self._ai_pixmap = None

        self._initial_offset_x = initial_offset_x
        self._initial_offset_y = initial_offset_y
        self._initial_flip_h = initial_flip_h
        self._initial_flip_v = initial_flip_v

        super().__init__(
            parent=parent,
            title="Adjust Alignment",
            modal=True,
            min_size=(600, 500),
            with_button_box=True,
        )

    @override
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        # Main horizontal layout: canvas on left, controls on right
        layout = QHBoxLayout()
        self.content_widget.setLayout(layout)

        # Overlay canvas
        self._canvas = OverlayCanvas()
        self._canvas.set_game_frame(self._game_pixmap)
        self._canvas.set_ai_frame(self._ai_pixmap)
        layout.addWidget(self._canvas, 1)

        # Control panel
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(8, 0, 0, 0)

        # Position controls
        position_group = QGroupBox("Position")
        position_layout = QFormLayout(position_group)

        self._offset_x_spin = QSpinBox()
        self._offset_x_spin.setRange(-128, 128)
        self._offset_x_spin.setValue(self._initial_offset_x)
        self._offset_x_spin.setSuffix(" px")
        self._offset_x_spin.valueChanged.connect(self._on_offset_changed)
        position_layout.addRow("X Offset:", self._offset_x_spin)

        self._offset_y_spin = QSpinBox()
        self._offset_y_spin.setRange(-128, 128)
        self._offset_y_spin.setValue(self._initial_offset_y)
        self._offset_y_spin.setSuffix(" px")
        self._offset_y_spin.valueChanged.connect(self._on_offset_changed)
        position_layout.addRow("Y Offset:", self._offset_y_spin)

        control_layout.addWidget(position_group)

        # Flip controls
        flip_group = QGroupBox("Flip")
        flip_layout = QVBoxLayout(flip_group)

        self._flip_h_check = QCheckBox("Horizontal")
        self._flip_h_check.setChecked(self._initial_flip_h)
        self._flip_h_check.toggled.connect(self._on_flip_changed)
        flip_layout.addWidget(self._flip_h_check)

        self._flip_v_check = QCheckBox("Vertical")
        self._flip_v_check.setChecked(self._initial_flip_v)
        self._flip_v_check.toggled.connect(self._on_flip_changed)
        flip_layout.addWidget(self._flip_v_check)

        control_layout.addWidget(flip_group)

        # Opacity control
        opacity_group = QGroupBox("Overlay Opacity")
        opacity_layout = QVBoxLayout(opacity_group)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(50)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self._opacity_slider)

        self._opacity_label = QLabel("50%")
        self._opacity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        opacity_layout.addWidget(self._opacity_label)

        control_layout.addWidget(opacity_group)

        # Info label
        info_label = QLabel(
            "Adjust the position and flip state of the AI frame\nto align with the game frame for replacement."
        )
        info_label.setStyleSheet("color: #888; font-size: 11px;")
        info_label.setWordWrap(True)
        control_layout.addWidget(info_label)

        control_layout.addStretch()
        layout.addWidget(control_panel)

        # Apply initial values to canvas
        self._canvas.set_offset(self._initial_offset_x, self._initial_offset_y)
        self._canvas.set_flip(self._initial_flip_h, self._initial_flip_v)

    def _on_offset_changed(self) -> None:
        """Handle offset spinbox value changes."""
        x = self._offset_x_spin.value()
        y = self._offset_y_spin.value()
        self._canvas.set_offset(x, y)
        self._emit_alignment_changed()

    def _on_flip_changed(self) -> None:
        """Handle flip checkbox changes."""
        flip_h = self._flip_h_check.isChecked()
        flip_v = self._flip_v_check.isChecked()
        self._canvas.set_flip(flip_h, flip_v)
        self._emit_alignment_changed()

    def _on_opacity_changed(self, value: int) -> None:
        """Handle opacity slider changes."""
        self._opacity_label.setText(f"{value}%")
        self._canvas.set_opacity(value / 100.0)

    def _emit_alignment_changed(self) -> None:
        """Emit the alignment_changed signal with current values."""
        self.alignment_changed.emit(
            self._offset_x_spin.value(),
            self._offset_y_spin.value(),
            self._flip_h_check.isChecked(),
            self._flip_v_check.isChecked(),
        )

    @property
    def offset_x(self) -> int:
        """Get the current X offset value."""
        return self._offset_x_spin.value()

    @property
    def offset_y(self) -> int:
        """Get the current Y offset value."""
        return self._offset_y_spin.value()

    @property
    def flip_h(self) -> bool:
        """Get the current horizontal flip state."""
        return self._flip_h_check.isChecked()

    @property
    def flip_v(self) -> bool:
        """Get the current vertical flip state."""
        return self._flip_v_check.isChecked()

    def get_alignment(self) -> tuple[int, int, bool, bool]:
        """Get the current alignment values.

        Returns:
            Tuple of (offset_x, offset_y, flip_h, flip_v)
        """
        return (self.offset_x, self.offset_y, self.flip_h, self.flip_v)
