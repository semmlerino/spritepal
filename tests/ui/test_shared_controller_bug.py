import pytest
from PySide6.QtCore import QObject, Signal

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace


def test_shared_controller_disconnection(qtbot):
    # Shared controller
    controller = EditingController()

    # Create two workspaces
    workspace1 = EditWorkspace()
    workspace2 = EditWorkspace()

    # Wire them to the same controller
    workspace1.set_controller(controller)

    canvas1 = workspace1.get_canvas()
    initial_version = canvas1._palette_version

    # Now wire the second workspace to the same controller
    # This should NOT disconnect the first one
    workspace2.set_controller(controller)

    # Change palette
    controller.paletteChanged.emit()

    # If bug exists, canvas1 won't receive the signal and _palette_version stays at initial_version
    assert canvas1._palette_version > initial_version, (
        "Workspace 1 was disconnected by Workspace 2's set_controller call!"
    )
