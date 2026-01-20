import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QWidget

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace


def test_canvas_click_modifies_controller_state(qtbot):
    """
    Verify that clicking the canvas widget actually updates the controller state.
    This bridges the "View -> Controller" coverage gap.
    """
    # 1. Setup Controller
    controller = EditingController()
    initial_data = np.zeros((8, 8), dtype=np.uint8)
    controller.load_image(initial_data)

    # Set tool to pencil and color to index 1
    controller.set_tool("pencil")
    controller.set_selected_color(1)

    # 2. Setup Workspace (View)
    # We use 'embedded' mode to keep it simple, though 'standalone' works too
    workspace = EditWorkspace(embed_mode="standalone")
    workspace.set_controller(controller)
    workspace.show()
    qtbot.addWidget(workspace)

    # Get the canvas
    canvas = workspace.get_canvas()
    assert canvas is not None

    # 3. Calculate Interaction Coordinates
    # Canvas default zoom is usually 4. Let's force it to be sure.
    canvas.set_zoom(4)
    zoom = 4

    # Target pixel (1, 1)
    target_x, target_y = 1, 1

    # Calculate widget coordinates (center of the pixel)
    # widget_x = (image_x * zoom) + (zoom / 2)
    widget_pos_x = int((target_x * zoom) + (zoom / 2))
    widget_pos_y = int((target_y * zoom) + (zoom / 2))

    click_point = QPoint(widget_pos_x, widget_pos_y)

    # 4. Simulate User Interaction
    # This sends a real QMouseEvent to the widget
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=click_point)

    # 5. Verify Controller State
    # The image data should now have color 1 at (1, 1)
    result_data = controller.get_image_data()
    assert result_data[target_y, target_x] == 1, "Clicking canvas did not update controller state!"
