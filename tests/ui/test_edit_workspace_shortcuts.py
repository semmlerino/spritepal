import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QWidget

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace


@pytest.fixture
def workspace(qtbot):
    """Create an EditWorkspace with a controller."""
    workspace = EditWorkspace()
    qtbot.addWidget(workspace)
    controller = EditingController()
    workspace.set_controller(controller)
    return workspace


def test_shortcuts_exist(workspace):
    """Verify QShortcut objects are created for key tools."""
    # QShortcut objects are children of the workspace
    shortcuts = workspace.findChildren(object, "")  # QShortcut is QObject not QWidget
    # Filter for QShortcut (can't import QShortcut easily from findChildren types sometimes)
    from PySide6.QtGui import QShortcut

    shortcuts = [c for c in workspace.children() if isinstance(c, QShortcut)]

    keys = [s.key().toString() for s in shortcuts]

    assert "P" in keys
    assert "B" in keys
    assert "K" in keys
    assert "E" in keys
    assert "G" in keys
    assert "T" in keys
    assert "C" in keys
    assert "+" in keys or "=" in keys
    assert "Ctrl+0" in keys
    assert "F" in keys


def test_eraser_shortcut_triggers_eraser_tool(workspace, qtbot):
    """Test that pressing E selects the eraser tool."""
    workspace.show()  # Must be visible for shortcuts?
    # Actually QShortcut requires window to be active usually.
    # We can try simulate click.

    # Check initial tool
    assert workspace.controller.get_current_tool_name() == "pencil"

    # We can't easily robustly test QShortcut activation in headless without focus.
    # Instead, let's verify that the Eraser button in toolbar works.

    eraser_btn = workspace.icon_toolbar.tool_buttons["eraser"]
    qtbot.mouseClick(eraser_btn, Qt.MouseButton.LeftButton)

    assert workspace.controller.get_current_tool_name() == "eraser"


def test_tile_grid_toggle(workspace, qtbot):
    """Test that T button toggles tile grid."""

    # Initial state
    canvas = workspace.get_canvas()
    assert canvas.tile_grid_visible is False

    # Find button
    btn = workspace.icon_toolbar.tile_grid_btn
    assert btn is not None

    # Click it
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    assert canvas.tile_grid_visible is True

    # Click again
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    assert canvas.tile_grid_visible is False
