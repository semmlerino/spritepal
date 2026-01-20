"""Unit tests for AlignmentDialog."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPixmap

from ui.frame_mapping.dialogs.alignment_dialog import (
    DISPLAY_SCALE,
    AlignmentDialog,
    OverlayCanvas,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestOverlayCanvas:
    """Tests for the OverlayCanvas widget."""

    def test_canvas_creates_with_default_values(self, qtbot: QtBot) -> None:
        """Canvas initializes with default alignment values."""
        canvas = OverlayCanvas()
        qtbot.addWidget(canvas)

        assert canvas._offset_x == 0
        assert canvas._offset_y == 0
        assert canvas._flip_h is False
        assert canvas._flip_v is False
        assert canvas._opacity == 0.5
        assert canvas._dragging is False
        assert canvas._drag_start is None

    def test_canvas_set_offset_updates_values(self, qtbot: QtBot) -> None:
        """set_offset updates internal offset values."""
        canvas = OverlayCanvas()
        qtbot.addWidget(canvas)

        canvas.set_offset(10, -5)

        assert canvas._offset_x == 10
        assert canvas._offset_y == -5

    def test_canvas_set_flip_updates_values(self, qtbot: QtBot) -> None:
        """set_flip updates internal flip values."""
        canvas = OverlayCanvas()
        qtbot.addWidget(canvas)

        canvas.set_flip(True, False)
        assert canvas._flip_h is True
        assert canvas._flip_v is False

        canvas.set_flip(False, True)
        assert canvas._flip_h is False
        assert canvas._flip_v is True

    def test_canvas_set_opacity_clamps_values(self, qtbot: QtBot) -> None:
        """set_opacity clamps values to 0.0-1.0 range."""
        canvas = OverlayCanvas()
        qtbot.addWidget(canvas)

        canvas.set_opacity(0.7)
        assert canvas._opacity == 0.7

        canvas.set_opacity(-0.5)
        assert canvas._opacity == 0.0

        canvas.set_opacity(1.5)
        assert canvas._opacity == 1.0

    def test_canvas_set_game_frame(self, qtbot: QtBot) -> None:
        """set_game_frame stores the pixmap."""
        canvas = OverlayCanvas()
        qtbot.addWidget(canvas)

        pixmap = QPixmap(32, 32)
        canvas.set_game_frame(pixmap)

        assert canvas._game_pixmap is not None
        assert canvas._game_pixmap.width() == 32

    def test_canvas_set_ai_frame(self, qtbot: QtBot) -> None:
        """set_ai_frame stores the pixmap."""
        canvas = OverlayCanvas()
        qtbot.addWidget(canvas)

        pixmap = QPixmap(24, 24)
        canvas.set_ai_frame(pixmap)

        assert canvas._ai_pixmap is not None
        assert canvas._ai_pixmap.width() == 24


class TestAlignmentDialogInitialization:
    """Tests for AlignmentDialog initialization."""

    def test_dialog_creates_with_default_values(self, qtbot: QtBot) -> None:
        """Dialog initializes with default alignment values."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        assert dialog.offset_x == 0
        assert dialog.offset_y == 0
        assert dialog.flip_h is False
        assert dialog.flip_v is False

    def test_dialog_creates_with_initial_values(self, qtbot: QtBot) -> None:
        """Dialog initializes with provided alignment values."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
            initial_offset_x=10,
            initial_offset_y=-5,
            initial_flip_h=True,
            initial_flip_v=True,
        )
        qtbot.addWidget(dialog)

        assert dialog.offset_x == 10
        assert dialog.offset_y == -5
        assert dialog.flip_h is True
        assert dialog.flip_v is True

    def test_dialog_has_correct_title(self, qtbot: QtBot) -> None:
        """Dialog has the expected window title."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        assert dialog.windowTitle() == "Adjust Alignment"


class TestAlignmentDialogControls:
    """Tests for AlignmentDialog control interactions."""

    def test_offset_x_spinbox_updates_property(self, qtbot: QtBot) -> None:
        """Changing X offset spinbox updates the property."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        dialog._offset_x_spin.setValue(15)

        assert dialog.offset_x == 15

    def test_offset_y_spinbox_updates_property(self, qtbot: QtBot) -> None:
        """Changing Y offset spinbox updates the property."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        dialog._offset_y_spin.setValue(-8)

        assert dialog.offset_y == -8

    def test_flip_h_checkbox_updates_property(self, qtbot: QtBot) -> None:
        """Toggling horizontal flip checkbox updates the property."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        dialog._flip_h_check.setChecked(True)

        assert dialog.flip_h is True

    def test_flip_v_checkbox_updates_property(self, qtbot: QtBot) -> None:
        """Toggling vertical flip checkbox updates the property."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        dialog._flip_v_check.setChecked(True)

        assert dialog.flip_v is True

    def test_get_alignment_returns_all_values(self, qtbot: QtBot) -> None:
        """get_alignment returns tuple of all current values."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        dialog._offset_x_spin.setValue(5)
        dialog._offset_y_spin.setValue(-3)
        dialog._flip_h_check.setChecked(True)
        dialog._flip_v_check.setChecked(False)

        result = dialog.get_alignment()

        assert result == (5, -3, True, False)


class TestAlignmentDialogSignals:
    """Tests for AlignmentDialog signals."""

    def test_offset_change_emits_alignment_changed(self, qtbot: QtBot) -> None:
        """Changing offset emits alignment_changed signal."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        with qtbot.waitSignal(dialog.alignment_changed, timeout=1000) as blocker:
            dialog._offset_x_spin.setValue(10)

        assert blocker.args == [10, 0, False, False]

    def test_flip_change_emits_alignment_changed(self, qtbot: QtBot) -> None:
        """Changing flip emits alignment_changed signal."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        with qtbot.waitSignal(dialog.alignment_changed, timeout=1000) as blocker:
            dialog._flip_h_check.setChecked(True)

        assert blocker.args == [0, 0, True, False]


class TestAlignmentDialogOpacity:
    """Tests for opacity slider functionality."""

    def test_opacity_slider_updates_canvas(self, qtbot: QtBot) -> None:
        """Moving opacity slider updates canvas opacity."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        dialog._opacity_slider.setValue(75)

        assert dialog._canvas._opacity == 0.75

    def test_opacity_slider_updates_label(self, qtbot: QtBot) -> None:
        """Moving opacity slider updates the percentage label."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        dialog._opacity_slider.setValue(30)

        assert dialog._opacity_label.text() == "30%"


class TestOverlayCanvasDrag:
    """Tests for canvas drag-to-adjust functionality."""

    def test_canvas_has_open_hand_cursor(self, qtbot: QtBot) -> None:
        """Canvas shows open hand cursor by default."""
        canvas = OverlayCanvas()
        qtbot.addWidget(canvas)

        assert canvas.cursor().shape() == Qt.CursorShape.OpenHandCursor

    def test_canvas_emits_offset_changed_signal(self, qtbot: QtBot) -> None:
        """Canvas emits offset_changed when drag updates offset."""
        canvas = OverlayCanvas()
        qtbot.addWidget(canvas)

        # Need an AI frame for drag to work
        pixmap = QPixmap(32, 32)
        canvas.set_ai_frame(pixmap)

        with qtbot.waitSignal(canvas.offset_changed, timeout=1000) as blocker:
            # Simulate drag: press, move, release
            canvas._dragging = True
            canvas._drag_start = QPoint(100, 100)
            canvas._drag_start_offset_x = 0
            canvas._drag_start_offset_y = 0

            # Move by DISPLAY_SCALE * 5 pixels = 5 sprite pixels
            from PySide6.QtCore import QPointF
            from PySide6.QtGui import QMouseEvent

            move_event = QMouseEvent(
                QMouseEvent.Type.MouseMove,
                QPointF(100 + DISPLAY_SCALE * 5, 100 + DISPLAY_SCALE * 3),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            canvas.mouseMoveEvent(move_event)

        assert blocker.args == [5, 3]

    def test_canvas_drag_without_ai_frame_does_nothing(self, qtbot: QtBot) -> None:
        """Drag has no effect when no AI frame is loaded."""
        canvas = OverlayCanvas()
        qtbot.addWidget(canvas)

        # No AI frame set - drag should not start
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent

        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(100, 100),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        canvas.mousePressEvent(press_event)

        assert canvas._dragging is False

    def test_dialog_canvas_drag_updates_spinboxes(self, qtbot: QtBot) -> None:
        """Dragging on canvas updates the offset spinboxes."""
        dialog = AlignmentDialog(
            game_frame_pixmap=None,
            ai_frame_path=None,
        )
        qtbot.addWidget(dialog)

        # Set an AI frame via the canvas
        pixmap = QPixmap(32, 32)
        dialog._canvas.set_ai_frame(pixmap)

        # Directly emit the canvas signal (simulating a completed drag)
        dialog._canvas.offset_changed.emit(7, -4)

        assert dialog._offset_x_spin.value() == 7
        assert dialog._offset_y_spin.value() == -4

    def test_drag_offset_clamped_to_range(self, qtbot: QtBot) -> None:
        """Drag offset is clamped to -128 to 128 range."""
        canvas = OverlayCanvas()
        qtbot.addWidget(canvas)

        pixmap = QPixmap(32, 32)
        canvas.set_ai_frame(pixmap)

        # Start drag from edge
        canvas._dragging = True
        canvas._drag_start = QPoint(100, 100)
        canvas._drag_start_offset_x = 120  # Near upper limit

        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent

        # Try to move way past the limit
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(100 + DISPLAY_SCALE * 50, 100),  # Would be +50, so 170 total
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        with qtbot.waitSignal(canvas.offset_changed, timeout=1000) as blocker:
            canvas.mouseMoveEvent(move_event)

        # Should be clamped to 128
        assert blocker.args[0] == 128
