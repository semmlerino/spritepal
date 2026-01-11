import numpy as np
import pytest
from PySide6.QtTest import QSignalSpy

from ui.sprite_editor.controllers.editing_controller import EditingController


@pytest.fixture
def controller(qtbot):
    """
    Fixture to provide an EditingController instance.
    We don't need a full view for this integration test as we drive logic via public API.
    """
    ctrl = EditingController()
    return ctrl


def test_draw_pixel_workflow(qtbot, controller):
    """
    Test the workflow of drawing a pixel:
    1. Load image
    2. Select tool
    3. Select color
    4. Draw (Press -> Release)
    5. Verify signals (imageChanged, undoStateChanged)
    """
    # 1. Setup Spies
    spy_image = QSignalSpy(controller.imageChanged)
    spy_undo = QSignalSpy(controller.undoStateChanged)
    spy_color = QSignalSpy(controller.colorChanged)
    spy_tool = QSignalSpy(controller.toolChanged)

    # 2. Load Image (White 8x8)
    # Using public API to set state
    initial_data = np.zeros((8, 8), dtype=np.uint8)
    controller.load_image(initial_data)

    # Assert initial signal from load
    assert spy_image.count() == 1
    image_count = spy_image.count()

    # 3. Select Pencil Tool (Switch to Fill then Pencil to ensure signal)
    controller.set_tool("fill")
    assert spy_tool.count() > 0
    assert spy_tool.at(spy_tool.count() - 1)[0] == "fill"

    controller.set_tool("pencil")
    assert spy_tool.count() > 1
    assert spy_tool.at(spy_tool.count() - 1)[0] == "pencil"

    # 4. Select Color (Index 1)
    controller.set_selected_color(1)
    # Assert signal behavior: color index
    assert spy_color.count() > 0
    assert spy_color.at(spy_color.count() - 1)[0] == 1

    # 5. Perform Draw Action (Press and Release at 0,0)
    # Driving system via public API calls simulating UI interaction
    controller.handle_pixel_press(0, 0)
    controller.handle_pixel_release(0, 0)

    # 6. Verify Signals
    # Image should have changed
    assert spy_image.count() > image_count

    # Undo state should have changed (Can Undo: True, Can Redo: False)
    assert spy_undo.count() > 0
    args = spy_undo.at(spy_undo.count() - 1)
    assert args[0] is True  # can_undo
    assert args[1] is False  # can_redo

    # 7. Verify Data via Public API (observable state)
    data = controller.get_image_data()
    assert data is not None
    assert data[0, 0] == 1


def test_undo_redo_workflow(qtbot, controller):
    """
    Test the Undo/Redo workflow via signals.
    """
    # Setup
    spy_image = QSignalSpy(controller.imageChanged)
    spy_undo = QSignalSpy(controller.undoStateChanged)

    initial_data = np.zeros((8, 8), dtype=np.uint8)
    controller.load_image(initial_data)
    image_count = spy_image.count()
    undo_count = spy_undo.count()

    # Action: Draw something
    controller.set_selected_color(2)
    controller.handle_pixel_press(1, 1)
    controller.handle_pixel_release(1, 1)

    # Verify Draw occurred
    assert spy_image.count() > image_count
    image_count = spy_image.count()

    assert spy_undo.count() > undo_count
    undo_count = spy_undo.count()
    assert spy_undo.at(undo_count - 1)[0] is True  # Can undo

    # Action: Undo
    controller.undo()

    # Verify Undo Signals
    assert spy_image.count() > image_count
    image_count = spy_image.count()

    assert spy_undo.count() > undo_count
    undo_count = spy_undo.count()

    args = spy_undo.at(undo_count - 1)
    assert args[0] is False  # Can undo (empty stack)
    assert args[1] is True  # Can redo

    # Action: Redo
    controller.redo()

    # Verify Redo Signals
    assert spy_image.count() > image_count

    assert spy_undo.count() > undo_count
    undo_count = spy_undo.count()

    args = spy_undo.at(undo_count - 1)
    assert args[0] is True  # Can undo
    assert args[1] is False  # Can redo


def test_tool_switching_signals(qtbot, controller):
    """
    Test that switching tools emits the correct signals.
    """
    spy_tool = QSignalSpy(controller.toolChanged)

    # Switch to Fill
    controller.set_tool("fill")
    assert spy_tool.count() == 1
    assert spy_tool.at(0)[0] == "fill"

    # Switch to Eraser
    controller.set_tool("eraser")
    assert spy_tool.count() == 2
    assert spy_tool.at(1)[0] == "eraser"

    # Switch to Picker
    controller.set_tool("picker")
    assert spy_tool.count() == 3
    assert spy_tool.at(2)[0] == "picker"

    # Switch to Invalid (should default or ignore?)
    # Implementation details: defaults to pencil in set_tool map
    controller.set_tool("invalid_tool")
    assert spy_tool.count() == 4
    assert spy_tool.at(3)[0] == "pencil"


def test_palette_signals(qtbot, controller):
    """
    Test palette modification signals.
    """
    spy_palette = QSignalSpy(controller.paletteChanged)

    # Simulate loading a palette via set_palette (Public API)
    new_palette = [(i * 10, i * 10, i * 10) for i in range(16)]
    controller.set_palette(new_palette, "Test Palette")

    assert spy_palette.count() == 1

    # Verify palette via public API
    current_colors = controller.get_current_colors()
    assert current_colors[0] == (0, 0, 0)
    assert current_colors[1] == (10, 10, 10)
