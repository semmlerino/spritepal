"""Dialog for adjusting overlay alignment between AI and game frames."""

from __future__ import annotations

from pathlib import Path
from typing import override

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.components.base.dialog_base import DialogBase
from ui.frame_mapping.views.base_overlay_canvas import BaseOverlayCanvas

# Preview canvas size
CANVAS_SIZE = 400
# Scale factor for display
DISPLAY_SCALE = 4


class OverlayCanvas(BaseOverlayCanvas):
    """Canvas widget for alignment dialog with drag-to-adjust.

    Supports drag-to-adjust: click and drag the AI frame overlay to adjust its position.

    Signals:
        offset_changed: Emitted when offset changes via drag (offset_x, offset_y)
    """

    offset_changed = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(CANVAS_SIZE, DISPLAY_SCALE, parent)

        # Drag state
        self._dragging = False
        self._drag_start: QPoint | None = None
        self._drag_start_offset_x = 0
        self._drag_start_offset_y = 0

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # -------------------------------------------------------------------------
    # Test/Inspection Properties
    # -------------------------------------------------------------------------

    @property
    def offset_x(self) -> int:
        """Get current X offset."""
        return self._offset_x

    @property
    def offset_y(self) -> int:
        """Get current Y offset."""
        return self._offset_y

    @property
    def flip_h(self) -> bool:
        """Get horizontal flip state."""
        return self._flip_h

    @property
    def flip_v(self) -> bool:
        """Get vertical flip state."""
        return self._flip_v

    @property
    def opacity(self) -> float:
        """Get current opacity (0.0-1.0)."""
        return self._opacity

    @property
    def is_dragging(self) -> bool:
        """Check if currently dragging."""
        return self._dragging

    def has_game_frame(self) -> bool:
        """Check if a game frame is loaded."""
        return self._game_pixmap is not None

    def has_ai_frame(self) -> bool:
        """Check if an AI frame is loaded."""
        return self._ai_pixmap is not None

    def get_game_frame_size(self) -> tuple[int, int] | None:
        """Get the game frame dimensions, or None if no frame."""
        if self._game_pixmap is None:
            return None
        return (self._game_pixmap.width(), self._game_pixmap.height())

    def get_ai_frame_size(self) -> tuple[int, int] | None:
        """Get the AI frame dimensions, or None if no frame."""
        if self._ai_pixmap is None:
            return None
        return (self._ai_pixmap.width(), self._ai_pixmap.height())

    # -------------------------------------------------------------------------
    # Drag-to-Adjust Functionality
    # -------------------------------------------------------------------------

    def start_drag(self, start_pos: QPoint, start_offset_x: int = 0, start_offset_y: int = 0) -> None:
        """Start a drag operation (public API for testing)."""
        self._dragging = True
        self._drag_start = start_pos
        self._drag_start_offset_x = start_offset_x
        self._drag_start_offset_y = start_offset_y
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Start dragging on left mouse button press."""
        if event.button() == Qt.MouseButton.LeftButton and self._ai_pixmap is not None:
            self._dragging = True
            self._drag_start = event.pos()
            self._drag_start_offset_x = self._offset_x
            self._drag_start_offset_y = self._offset_y
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Update offset while dragging."""
        if self._dragging and self._drag_start is not None:
            delta = event.pos() - self._drag_start
            # Convert screen pixels to sprite pixels
            new_offset_x = self._drag_start_offset_x + delta.x() // DISPLAY_SCALE
            new_offset_y = self._drag_start_offset_y + delta.y() // DISPLAY_SCALE

            # Clamp to reasonable range
            new_offset_x = max(-128, min(128, new_offset_x))
            new_offset_y = max(-128, min(128, new_offset_y))

            if new_offset_x != self._offset_x or new_offset_y != self._offset_y:
                self._offset_x = new_offset_x
                self._offset_y = new_offset_y
                self.offset_changed.emit(self._offset_x, self._offset_y)
                self.update()

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Stop dragging on mouse button release."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)


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

        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QHBoxLayout(actions_group)

        self._reset_button = QPushButton("Reset")
        self._reset_button.setToolTip("Reset offset to (0, 0)")
        self._reset_button.clicked.connect(self._on_reset_clicked)
        actions_layout.addWidget(self._reset_button)

        self._center_button = QPushButton("Center")
        self._center_button.setToolTip("Center AI frame over game frame")
        self._center_button.clicked.connect(self._on_center_clicked)
        actions_layout.addWidget(self._center_button)

        control_layout.addWidget(actions_group)

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
            "Drag overlay or use arrow keys to adjust.\n"
            "Shift+arrow: 8px nudge.\n"
            "AI frame shown at actual relative size."
        )
        info_label.setStyleSheet("color: #888; font-size: 11px;")
        info_label.setWordWrap(True)
        control_layout.addWidget(info_label)

        control_layout.addStretch()
        layout.addWidget(control_panel)

        # Apply initial values to canvas
        self._canvas.set_offset(self._initial_offset_x, self._initial_offset_y)
        self._canvas.set_flip(self._initial_flip_h, self._initial_flip_v)

        # Connect canvas drag signal to update spinboxes
        self._canvas.offset_changed.connect(self._on_canvas_offset_changed)

    def _on_canvas_offset_changed(self, x: int, y: int) -> None:
        """Handle offset changes from canvas drag."""
        # Block signals to prevent feedback loop
        self._offset_x_spin.blockSignals(True)
        self._offset_y_spin.blockSignals(True)
        self._offset_x_spin.setValue(x)
        self._offset_y_spin.setValue(y)
        self._offset_x_spin.blockSignals(False)
        self._offset_y_spin.blockSignals(False)
        self._emit_alignment_changed()

    def _on_reset_clicked(self) -> None:
        """Handle Reset button click."""
        self._offset_x_spin.setValue(0)
        self._offset_y_spin.setValue(0)

    def _on_center_clicked(self) -> None:
        """Handle Center button click.

        Calculates offset to center AI frame over game frame based on
        their respective dimensions.
        """
        if self._game_pixmap is None or self._ai_pixmap is None:
            return

        game_w = self._game_pixmap.width()
        game_h = self._game_pixmap.height()
        ai_w = self._ai_pixmap.width()
        ai_h = self._ai_pixmap.height()

        # Calculate offset to center AI frame within game frame bounds
        center_x = (game_w - ai_w) // 2
        center_y = (game_h - ai_h) // 2

        self._offset_x_spin.setValue(center_x)
        self._offset_y_spin.setValue(center_y)

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard input for arrow key nudges."""
        key = event.key()
        shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        nudge = 8 if shift_held else 1

        if key == Qt.Key.Key_Left:
            self._offset_x_spin.setValue(self._offset_x_spin.value() - nudge)
        elif key == Qt.Key.Key_Right:
            self._offset_x_spin.setValue(self._offset_x_spin.value() + nudge)
        elif key == Qt.Key.Key_Up:
            self._offset_y_spin.setValue(self._offset_y_spin.value() - nudge)
        elif key == Qt.Key.Key_Down:
            self._offset_y_spin.setValue(self._offset_y_spin.value() + nudge)
        else:
            # Pass other keys to parent (for dialog buttons like Enter/Escape)
            super().keyPressEvent(event)

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

    def set_offset_x(self, value: int) -> None:
        """Set the X offset value."""
        self._offset_x_spin.setValue(value)

    def set_offset_y(self, value: int) -> None:
        """Set the Y offset value."""
        self._offset_y_spin.setValue(value)

    def set_flip_h(self, checked: bool) -> None:
        """Set the horizontal flip state."""
        self._flip_h_check.setChecked(checked)

    def set_flip_v(self, checked: bool) -> None:
        """Set the vertical flip state."""
        self._flip_v_check.setChecked(checked)

    def set_opacity(self, percent: int) -> None:
        """Set the opacity slider value (0-100)."""
        self._opacity_slider.setValue(percent)

    def get_opacity_percent(self) -> int:
        """Get the opacity slider value (0-100)."""
        return self._opacity_slider.value()

    def get_opacity_label_text(self) -> str:
        """Get the opacity label text."""
        return self._opacity_label.text()

    @property
    def canvas(self) -> OverlayCanvas:
        """Get the overlay canvas (for testing)."""
        return self._canvas

    def emit_canvas_offset(self, x: int, y: int) -> None:
        """Emit a canvas offset_changed signal (for testing)."""
        self._canvas.offset_changed.emit(x, y)
