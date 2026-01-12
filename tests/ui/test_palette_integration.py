from unittest.mock import MagicMock

import pytest

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace


def test_palette_wiring(qtbot):
    """Verify palette panel signals are wired to controller."""
    workspace = EditWorkspace()
    qtbot.addWidget(workspace)

    controller = EditingController()

    # Mock handler methods to verify they are called
    # We need to do this BEFORE set_controller because set_controller connects them
    # But EditingController is a class, we need to mock instance methods.
    # Since we replaced the methods in the class, we can just mock them on the instance.
    controller.handle_load_palette = MagicMock()
    controller.handle_save_palette = MagicMock()
    controller.handle_edit_color = MagicMock()
    controller.handle_palette_source_changed = MagicMock()

    # Set controller (this connects signals)
    workspace.set_controller(controller)

    # Trigger signals from panel
    workspace.palette_panel.loadPaletteClicked.emit()
    assert controller.handle_load_palette.called

    workspace.palette_panel.savePaletteClicked.emit()
    assert controller.handle_save_palette.called

    workspace.palette_panel.editColorClicked.emit()
    assert controller.handle_edit_color.called

    workspace.palette_panel.sourceChanged.emit("mesen", 1)
    controller.handle_palette_source_changed.assert_called_with("mesen", 1)


def test_palette_source_update(qtbot):
    """Verify controller can update palette sources in view."""
    workspace = EditWorkspace()
    qtbot.addWidget(workspace)
    controller = EditingController()
    workspace.set_controller(controller)

    # Mock add_palette_source on panel to verify it receives signal
    # We need to mock it on the object that receives the signal
    workspace.palette_panel.add_palette_source = MagicMock()

    # Note: connect happens in set_controller. If we mock AFTER set_controller,
    # the signal is already connected to the REAL method.
    # We should rely on the fact that signal emission calls the slot.
    # But wait, Qt signals connect to slots. If we replace the slot method on the instance,
    # does the signal call the new mock? In Python with PySide, usually yes if it's a python method.

    # Let's try mocking before connecting just in case, but EditWorkspace creates PalettePanel internally.
    # We can't mock PalettePanel methods before EditWorkspace creates it.
    # But we can mock it before set_controller.

    workspace.palette_panel.add_palette_source = MagicMock()

    # Re-connect (since set_controller was already called in test setup if we followed previous pattern,
    # but here we called it after creation)
    workspace.set_controller(controller)

    # Emit signal from controller
    # Signal signature: (name, type, index, colors, is_active)
    test_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    controller.paletteSourceAdded.emit("New Source", "mesen", 2, test_colors, True)

    workspace.palette_panel.add_palette_source.assert_called_with("New Source", "mesen", 2, test_colors, True)
