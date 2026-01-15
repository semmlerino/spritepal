from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage, QPainter

from ui.sprite_editor.views.widgets.pixel_canvas import PixelCanvas


@pytest.fixture
def canvas(qtbot):
    controller = MagicMock()
    # Mock image model with 16x16 data
    image_model = MagicMock()
    import numpy as np

    image_model.data = np.zeros((16, 16), dtype=np.uint8)
    controller.image_model = image_model
    controller.has_image.return_value = True

    # Mock brush pixels
    controller.get_brush_pixels.return_value = []

    canvas = PixelCanvas(controller)
    canvas.resize(200, 200)
    canvas.show()
    qtbot.addWidget(canvas)
    return canvas


def test_overlay_rendering_state(canvas):
    """Verify that overlay state correctly enables rendering logic."""
    # Initial state - use public API
    assert not canvas.has_overlay()

    # Set overlay
    overlay_img = QImage(32, 32, QImage.Format.Format_ARGB32)
    overlay_img.fill(Qt.GlobalColor.red)

    canvas.set_overlay_image(overlay_img)

    # Verify via public API
    assert canvas.has_overlay()
    bounds = canvas.get_overlay_bounds()
    assert bounds.width() > 0 and bounds.height() > 0
    assert canvas.get_overlay_scale() == 1.0

    # Verify bounds
    bounds = canvas.get_overlay_bounds()
    # Zoom is 20 by default? Let's check
    zoom = canvas.zoom
    assert bounds.width() == 32 * zoom
    assert bounds.height() == 32 * zoom

    # Trigger paint and ensure no crash
    canvas.update()


def test_paint_event_logic(canvas, qtbot):
    """Manual check of paint event logic via mocking painter if possible,
    but here we just ensure it doesn't crash and has correct properties."""
    overlay_img = QImage(32, 32, QImage.Format.Format_ARGB32)
    canvas.set_overlay_image(overlay_img)
    canvas.set_overlay_opacity(50)

    # This just ensures execution path doesn't crash
    canvas.repaint()
