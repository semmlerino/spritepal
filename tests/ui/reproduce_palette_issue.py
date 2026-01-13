import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.models.image_model import ImageModel
from ui.sprite_editor.models.palette_model import PaletteModel
from ui.sprite_editor.views.widgets.pixel_canvas import PixelCanvas


@pytest.fixture
def controller():
    return EditingController()


def test_canvas_palette_sync(qtbot, controller):
    # Setup canvas
    canvas = PixelCanvas(controller)
    canvas.greyscale_mode = False  # Ensure we're in color mode
    canvas.show()
    qtbot.addWidget(canvas)

    # Set some data with index 7 and 8
    data = np.zeros((16, 16), dtype=np.uint8)
    data[0, 0] = 7
    data[0, 1] = 8
    controller.load_image(data)

    # Force update the cache
    canvas._update_color_lut()

    # Check initial colors (should be grayscale 7*17=119 by default in PaletteModel)
    assert canvas._qcolor_cache[7].red() == 119

    # Change palette to something else (e.g. Orange for index 7 and 8)
    new_palette = [(0, 0, 0)] * 16
    new_palette[7] = (255, 165, 0)  # Orange
    new_palette[8] = (255, 140, 0)  # Dark Orange

    # This should trigger paletteChanged signal
    controller.set_palette(new_palette)

    # Signal should have triggered _on_palette_changed which increments _palette_version
    # and invalidates color cache.
    # The next time paintEvent happens (or we call _update_color_lut), it will rebuild.

    canvas._update_color_lut()

    assert canvas._qcolor_cache[7].red() == 255
    assert canvas._qcolor_cache[7].green() == 165
    assert canvas._qcolor_cache[7].blue() == 0

    assert canvas._qcolor_cache[8].red() == 255
    assert canvas._qcolor_cache[8].green() == 140
    assert canvas._qcolor_cache[8].blue() == 0
