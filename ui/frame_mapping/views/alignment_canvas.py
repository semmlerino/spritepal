"""Alignment Canvas for inline frame alignment editing."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui.frame_mapping.services.canvas_config_service import CanvasConfig
from ui.frame_mapping.views.base_overlay_canvas import BaseOverlayCanvas
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame, GameFrame

logger = get_logger(__name__)


class OverlayCanvasWidget(BaseOverlayCanvas):
    """Canvas widget for alignment editing with keyboard support.

    Supports keyboard input for nudging alignment when focused.
    Arrow keys nudge by 1 pixel, Shift+Arrow nudges by 8 pixels.

    Signals:
        offset_changed: Emitted when offset changes via keyboard (x, y)
    """

    offset_changed = Signal(int, int)  # new offset_x, offset_y

    def __init__(self, canvas_size: int, display_scale: int, parent: QWidget | None = None) -> None:
        super().__init__(canvas_size, display_scale, parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @override
    def _get_empty_message(self) -> str:
        """Return custom empty message for alignment canvas."""
        return "Select a mapped AI frame\nto preview alignment"

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle arrow key presses for nudging."""
        step = 8 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1

        key = event.key()
        if key == Qt.Key.Key_Left:
            self._offset_x -= step
            self.offset_changed.emit(self._offset_x, self._offset_y)
            self.update()
        elif key == Qt.Key.Key_Right:
            self._offset_x += step
            self.offset_changed.emit(self._offset_x, self._offset_y)
            self.update()
        elif key == Qt.Key.Key_Up:
            self._offset_y -= step
            self.offset_changed.emit(self._offset_x, self._offset_y)
            self.update()
        elif key == Qt.Key.Key_Down:
            self._offset_y += step
            self.offset_changed.emit(self._offset_x, self._offset_y)
            self.update()
        else:
            super().keyPressEvent(event)

    @override
    def paintEvent(self, event: object) -> None:
        """Paint the overlay composite with focus indicator."""
        super().paintEvent(event)

        # Draw focus indicator
        if self.hasFocus():
            painter = QPainter(self)
            painter.setPen(Qt.GlobalColor.cyan)
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)


class AlignmentCanvas(QWidget):
    """Inline alignment canvas with controls.

    Provides a canvas for overlaying AI frame on game frame, plus
    controls for adjusting offset, flip, and opacity.

    Changes are auto-saved when:
    - A different row is selected (detected by workspace)
    - Focus leaves the canvas area

    Signals:
        alignment_changed: Emitted when alignment values change (x, y, flip_h, flip_v)
        focus_lost: Emitted when focus leaves this widget (for auto-save)
    """

    alignment_changed = Signal(int, int, bool, bool)  # offset_x, offset_y, flip_h, flip_v
    focus_lost = Signal()

    def __init__(self, parent: QWidget | None = None, config: CanvasConfig | None = None) -> None:
        super().__init__(parent)

        # Configuration (with defaults if not provided)
        if config is None:
            config = CanvasConfig(size=320, display_scale=4)
        self._config = config

        self._current_ai_frame: AIFrame | None = None
        self._current_game_frame: GameFrame | None = None
        self._game_pixmap: QPixmap | None = None
        self._ai_pixmap: QPixmap | None = None
        self._has_mapping = False

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        title_layout = QHBoxLayout()
        title = QLabel("Alignment Canvas")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        title_layout.addWidget(title)

        title_layout.addStretch()

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; font-size: 10px;")
        title_layout.addWidget(self._status_label)

        layout.addLayout(title_layout)

        # Canvas (centered)
        canvas_layout = QHBoxLayout()
        canvas_layout.addStretch()
        self._canvas = OverlayCanvasWidget(self._config.size, self._config.display_scale)
        canvas_layout.addWidget(self._canvas)
        canvas_layout.addStretch()
        layout.addLayout(canvas_layout, 1)

        # Controls row
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        # Opacity control
        opacity_label = QLabel("Opacity:")
        opacity_label.setStyleSheet("font-size: 11px;")
        controls_layout.addWidget(opacity_label)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(50)
        self._opacity_slider.setMaximumWidth(100)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        controls_layout.addWidget(self._opacity_slider)

        self._opacity_value = QLabel("50%")
        self._opacity_value.setStyleSheet("font-size: 11px;")
        self._opacity_value.setMinimumWidth(35)
        controls_layout.addWidget(self._opacity_value)

        controls_layout.addStretch()

        # Nudge buttons
        nudge_label = QLabel("Nudge:")
        nudge_label.setStyleSheet("font-size: 11px;")
        controls_layout.addWidget(nudge_label)

        self._left_btn = QPushButton("◄")
        self._left_btn.setMaximumWidth(30)
        self._left_btn.setToolTip("Move left (←)")
        self._left_btn.clicked.connect(lambda: self._nudge(-1, 0))
        controls_layout.addWidget(self._left_btn)

        vert_btns = QVBoxLayout()
        vert_btns.setSpacing(0)
        vert_btns.setContentsMargins(0, 0, 0, 0)
        self._up_btn = QPushButton("▲")
        self._up_btn.setMaximumWidth(30)
        self._up_btn.setMaximumHeight(20)
        self._up_btn.setToolTip("Move up (↑)")
        self._up_btn.clicked.connect(lambda: self._nudge(0, -1))
        vert_btns.addWidget(self._up_btn)
        self._down_btn = QPushButton("▼")
        self._down_btn.setMaximumWidth(30)
        self._down_btn.setMaximumHeight(20)
        self._down_btn.setToolTip("Move down (↓)")
        self._down_btn.clicked.connect(lambda: self._nudge(0, 1))
        vert_btns.addWidget(self._down_btn)
        controls_layout.addLayout(vert_btns)

        self._right_btn = QPushButton("►")
        self._right_btn.setMaximumWidth(30)
        self._right_btn.setToolTip("Move right (→)")
        self._right_btn.clicked.connect(lambda: self._nudge(1, 0))
        controls_layout.addWidget(self._right_btn)

        controls_layout.addStretch()

        # Offset display
        self._offset_label = QLabel("Offset: (0, 0)")
        self._offset_label.setStyleSheet("font-size: 11px;")
        controls_layout.addWidget(self._offset_label)

        controls_layout.addStretch()

        # Flip controls
        self._flip_h_checkbox = QCheckBox("H-Flip")
        self._flip_h_checkbox.setStyleSheet("font-size: 11px;")
        self._flip_h_checkbox.toggled.connect(self._on_flip_changed)
        controls_layout.addWidget(self._flip_h_checkbox)

        self._flip_v_checkbox = QCheckBox("V-Flip")
        self._flip_v_checkbox.setStyleSheet("font-size: 11px;")
        self._flip_v_checkbox.toggled.connect(self._on_flip_changed)
        controls_layout.addWidget(self._flip_v_checkbox)

        layout.addLayout(controls_layout)

        # Set initial enabled state
        self._set_controls_enabled(False)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._canvas.offset_changed.connect(self._on_canvas_offset_changed)

    def set_game_frame(self, frame: GameFrame | None, preview_pixmap: QPixmap | None = None) -> None:
        """Set the game frame (background).

        Args:
            frame: GameFrame to display, or None to clear
            preview_pixmap: Optional pre-rendered preview pixmap
        """
        self._current_game_frame = frame

        if frame is None:
            self._game_pixmap = None
            self._canvas.set_game_frame(None)
            return

        if preview_pixmap is not None:
            self._game_pixmap = preview_pixmap
        elif frame.capture_path:
            preview_path = frame.capture_path.with_suffix(".png")
            if preview_path.exists():
                self._game_pixmap = QPixmap(str(preview_path))
            else:
                self._game_pixmap = None
        else:
            self._game_pixmap = None

        self._canvas.set_game_frame(self._game_pixmap)
        self._update_status()

    def set_ai_frame(self, frame: AIFrame | None) -> None:
        """Set the AI frame (overlay).

        Args:
            frame: AIFrame to display, or None to clear
        """
        self._current_ai_frame = frame

        if frame is None:
            self._ai_pixmap = None
            self._canvas.set_ai_frame(None)
            return

        if frame.path.exists():
            self._ai_pixmap = QPixmap(str(frame.path))
        else:
            self._ai_pixmap = None

        self._canvas.set_ai_frame(self._ai_pixmap)
        self._update_status()

    def set_alignment(
        self,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
    ) -> None:
        """Set the alignment values.

        Args:
            offset_x: X offset for the AI frame
            offset_y: Y offset for the AI frame
            flip_h: Horizontal flip state
            flip_v: Vertical flip state
        """
        self._has_mapping = True
        self._set_controls_enabled(True)

        # Block signals to prevent feedback loop
        self._flip_h_checkbox.blockSignals(True)
        self._flip_v_checkbox.blockSignals(True)

        self._canvas.set_offset(offset_x, offset_y)
        self._canvas.set_flip(flip_h, flip_v)
        self._flip_h_checkbox.setChecked(flip_h)
        self._flip_v_checkbox.setChecked(flip_v)
        self._offset_label.setText(f"Offset: ({offset_x}, {offset_y})")

        self._flip_h_checkbox.blockSignals(False)
        self._flip_v_checkbox.blockSignals(False)

        self._update_status()

    def clear_alignment(self) -> None:
        """Clear alignment values (reset to defaults)."""
        self._has_mapping = False
        self._set_controls_enabled(False)
        self.set_alignment(0, 0, False, False)

    def clear(self) -> None:
        """Clear all content."""
        self._current_ai_frame = None
        self._current_game_frame = None
        self._game_pixmap = None
        self._ai_pixmap = None
        self._has_mapping = False
        self._canvas.set_game_frame(None)
        self._canvas.set_ai_frame(None)
        self.clear_alignment()
        self._update_status()

    def get_alignment(self) -> tuple[int, int, bool, bool]:
        """Get current alignment values.

        Returns:
            Tuple of (offset_x, offset_y, flip_h, flip_v)
        """
        x, y = self._canvas.get_offset()
        return x, y, self._flip_h_checkbox.isChecked(), self._flip_v_checkbox.isChecked()

    def focus_canvas(self) -> None:
        """Set focus to the canvas for keyboard input."""
        self._canvas.setFocus()

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable alignment controls."""
        self._left_btn.setEnabled(enabled)
        self._right_btn.setEnabled(enabled)
        self._up_btn.setEnabled(enabled)
        self._down_btn.setEnabled(enabled)
        self._flip_h_checkbox.setEnabled(enabled)
        self._flip_v_checkbox.setEnabled(enabled)

    def _update_status(self) -> None:
        """Update the status label."""
        if self._current_ai_frame is None:
            self._status_label.setText("No AI frame selected")
        elif not self._has_mapping:
            self._status_label.setText("Frame not mapped")
        else:
            self._status_label.setText("Use arrow keys or buttons to adjust")

    def _on_opacity_changed(self, value: int) -> None:
        """Handle opacity slider change."""
        self._opacity_value.setText(f"{value}%")
        self._canvas.set_opacity(value / 100.0)

    def _on_canvas_offset_changed(self, x: int, y: int) -> None:
        """Handle offset change from canvas (keyboard input)."""
        self._offset_label.setText(f"Offset: ({x}, {y})")
        self._emit_alignment_changed()

    def _on_flip_changed(self) -> None:
        """Handle flip checkbox change."""
        flip_h = self._flip_h_checkbox.isChecked()
        flip_v = self._flip_v_checkbox.isChecked()
        self._canvas.set_flip(flip_h, flip_v)
        self._emit_alignment_changed()

    def _nudge(self, dx: int, dy: int) -> None:
        """Nudge the offset by the given delta."""
        x, y = self._canvas.get_offset()
        x += dx
        y += dy
        self._canvas.set_offset(x, y)
        self._offset_label.setText(f"Offset: ({x}, {y})")
        self._emit_alignment_changed()

    def _emit_alignment_changed(self) -> None:
        """Emit alignment_changed signal with current values."""
        x, y = self._canvas.get_offset()
        flip_h = self._flip_h_checkbox.isChecked()
        flip_v = self._flip_v_checkbox.isChecked()
        self.alignment_changed.emit(x, y, flip_h, flip_v)
