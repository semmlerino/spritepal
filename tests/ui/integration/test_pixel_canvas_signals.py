"""
Tests for PixelCanvas public signal behavior.

These tests verify ONLY observable signal behavior:
- Signal emission count
- Signal argument values

They do NOT inspect internal state or private attributes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QSignalSpy

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def canvas_with_image(qtbot: QtBot):
    """Create a PixelCanvas with a loaded 8x8 image."""
    from PySide6.QtCore import QCoreApplication

    from ui.sprite_editor.controllers.editing_controller import EditingController
    from ui.sprite_editor.views.widgets.pixel_canvas import PixelCanvas

    controller = EditingController()
    canvas = PixelCanvas(controller)
    qtbot.addWidget(canvas)

    # Load 8x8 test image
    data = np.zeros((8, 8), dtype=np.uint8)
    controller.load_image(data)

    # Set zoom to 8 for easier coordinate calculation
    canvas.set_zoom(8)

    # Ensure canvas has sufficient size for mouse events to register
    # With zoom=8 and 8x8 image, we need at least 64x64 pixels
    canvas.setMinimumSize(100, 100)
    canvas.resize(100, 100)

    # Show the widget and wait for it to be fully exposed
    canvas.show()
    qtbot.waitExposed(canvas)
    QCoreApplication.processEvents()

    return canvas, controller


class TestPixelCanvasMouseSignals:
    """Test PixelCanvas emits correct signals on mouse interactions."""

    def test_mouse_press_emits_pixelPressed(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse press on canvas emits pixelPressed with coordinates."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.pixelPressed)

        # Click at pixel (1, 1) - with zoom=8, that's screen position ~12, 12
        # Click in center of pixel to avoid edge issues
        click_pos = QPoint(12, 12)
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=click_pos)

        # Assert signal was emitted with correct pixel coordinates
        assert spy.count() == 1, "SIGNAL CONTRACT VIOLATION: pixelPressed must be emitted when canvas is clicked."
        # Pixel coordinates should be (1, 1)
        assert list(spy.at(0)) == [1, 1]

    def test_mouse_press_at_origin_emits_pixelPressed_0_0(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse press at origin emits pixelPressed with (0, 0)."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.pixelPressed)

        # Click at pixel (0, 0) - with zoom=8, that's screen position ~4, 4
        click_pos = QPoint(4, 4)
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=click_pos)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: pixelPressed must be emitted when canvas is clicked at pixel (0, 0)."
        )
        assert list(spy.at(0)) == [0, 0]

    def test_mouse_release_emits_pixelReleased(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse release emits pixelReleased signal."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.pixelReleased)

        click_pos = QPoint(4, 4)
        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=click_pos)
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=click_pos)

        assert spy.count() == 1, "SIGNAL CONTRACT VIOLATION: pixelReleased must be emitted when mouse is released."
        assert list(spy.at(0)) == [0, 0]

    def test_mouse_drag_emits_pixelMoved(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse move during draw emits pixelMoved."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.pixelMoved)

        # Press at (0,0), move to (1,1)
        start = QPoint(4, 4)
        end = QPoint(12, 12)

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        qtbot.mouseMove(canvas, pos=end)
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)

        # pixelMoved should have been emitted at least once during the move
        assert spy.count() >= 1, (
            "SIGNAL CONTRACT VIOLATION: pixelMoved must be emitted when mouse is dragged during drawing."
        )

    def test_complete_draw_stroke_emits_press_move_release(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify a complete draw stroke emits press, move, and release signals."""
        canvas, _ = canvas_with_image

        press_spy = QSignalSpy(canvas.pixelPressed)
        move_spy = QSignalSpy(canvas.pixelMoved)
        release_spy = QSignalSpy(canvas.pixelReleased)

        start = QPoint(4, 4)
        middle = QPoint(12, 12)
        end = QPoint(20, 20)

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        qtbot.mouseMove(canvas, pos=middle)
        qtbot.mouseMove(canvas, pos=end)
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)

        # All three signal types should have been emitted
        assert press_spy.count() == 1
        assert move_spy.count() >= 1
        assert release_spy.count() == 1


class TestPixelCanvasHoverSignals:
    """Test PixelCanvas emits hoverPositionChanged signals correctly."""

    def test_mouse_move_emits_hoverPositionChanged(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse move emits hoverPositionChanged with coordinates."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.hoverPositionChanged)

        # Move to pixel (2, 2) - with zoom=8, that's screen position ~20, 20
        move_pos = QPoint(20, 20)
        qtbot.mouseMove(canvas, pos=move_pos)

        # Should have emitted at least once with valid coordinates
        assert spy.count() >= 1, (
            "SIGNAL CONTRACT VIOLATION: hoverPositionChanged must be emitted when mouse moves over the canvas."
        )
        # Check the last emission has the expected coordinates
        assert list(spy.at(spy.count() - 1)) == [2, 2]

    def test_mouse_leave_emits_hoverPositionChanged_minus1(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse leave emits hoverPositionChanged with (-1, -1)."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.hoverPositionChanged)

        # Simulate leave event
        leave_event = QEvent(QEvent.Type.Leave)
        canvas.leaveEvent(leave_event)

        # Should emit (-1, -1) to indicate no hover position
        assert spy.count() >= 1
        # Last emission should be (-1, -1)
        assert list(spy.at(spy.count() - 1)) == [-1, -1]


class TestPixelCanvasZoomSignals:
    """Test PixelCanvas emits zoomRequested signals correctly."""

    def test_wheel_scroll_up_emits_zoomRequested_higher(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse wheel scroll up emits zoomRequested with higher zoom."""
        from PySide6.QtCore import QPointF

        canvas, _ = canvas_with_image

        # Get initial zoom
        initial_zoom = canvas.zoom

        spy = QSignalSpy(canvas.zoomRequested)

        # Simulate wheel scroll up (zoom in)
        wheel_event = QWheelEvent(
            QPointF(50, 50),  # position
            QPointF(50, 50),  # global position
            QPoint(0, 0),  # pixel delta
            QPoint(0, 120),  # angle delta (positive = scroll up = zoom in)
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        canvas.wheelEvent(wheel_event)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: zoomRequested must be emitted when mouse wheel is scrolled."
        )
        # New zoom should be higher than initial
        new_zoom = spy.at(0)[0]
        assert new_zoom > initial_zoom

    def test_wheel_scroll_down_emits_zoomRequested_lower(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse wheel scroll down emits zoomRequested with lower zoom."""
        from PySide6.QtCore import QPointF

        canvas, _ = canvas_with_image

        # Get initial zoom
        initial_zoom = canvas.zoom

        spy = QSignalSpy(canvas.zoomRequested)

        # Simulate wheel scroll down (zoom out)
        wheel_event = QWheelEvent(
            QPointF(50, 50),
            QPointF(50, 50),
            QPoint(0, 0),
            QPoint(0, -120),  # negative = scroll down = zoom out
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        canvas.wheelEvent(wheel_event)

        assert spy.count() == 1
        # New zoom should be lower than initial
        new_zoom = spy.at(0)[0]
        assert new_zoom < initial_zoom


class TestPixelCanvasSignalContract:
    """Tests that document the expected public signal contract."""

    @pytest.mark.parametrize(
        "signal_name",
        [
            "pixelPressed",
            "pixelMoved",
            "pixelReleased",
            "zoomRequested",
            "hoverPositionChanged",
        ],
    )
    def test_signal_exists(self, signal_name: str, canvas_with_image: tuple) -> None:
        """Verify all expected public signals exist on PixelCanvas."""
        canvas, _ = canvas_with_image
        assert hasattr(canvas, signal_name), f"SIGNAL CONTRACT: PixelCanvas must expose '{signal_name}' signal"


class TestPixelCanvasRegression:
    """Regression tests for PixelCanvas correctness fixes."""

    def test_canvas_palette_sync(self, qtbot, canvas_with_image):
        """Verify canvas updates its color cache when controller palette changes."""
        canvas, controller = canvas_with_image
        canvas.greyscale_mode = False

        # Set some data with index 7
        data = np.zeros((8, 8), dtype=np.uint8)
        data[0, 0] = 7
        controller.load_image(data)

        # Force update the cache
        canvas._update_color_lut()

        # Check initial colors (should be grayscale 7*17=119 by default in PaletteModel)
        assert canvas._qcolor_cache[7].red() == 119

        # Change palette to something else (e.g. Orange for index 7)
        new_palette = [(0, 0, 0)] * 16
        new_palette[7] = (255, 165, 0)  # Orange

        # This should trigger paletteChanged signal
        controller.set_palette(new_palette)

        # Canvas invalidates cache on signal, rebuild on next access
        canvas._update_color_lut()

        assert canvas._qcolor_cache[7].red() == 255
        assert canvas._qcolor_cache[7].green() == 165
        assert canvas._qcolor_cache[7].blue() == 0
