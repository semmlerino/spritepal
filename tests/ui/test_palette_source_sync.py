import pytest
from PySide6.QtWidgets import QComboBox

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace


def test_palette_source_sync_late_connection(qtbot):
    """
    Verify that palette sources registered in the controller BEFORE
    the view is connected are correctly populated in the view.
    """
    # 1. Setup Controller with pre-existing state
    controller = EditingController()

    # Simulate ROM workflow registering a palette BEFORE view exists/connects
    # This happens often when the controller is long-lived or shared
    controller.register_palette_source("rom", 10, [(255, 0, 0)] * 16, "Red Palette")

    # 2. Create View and Connect
    workspace = EditWorkspace()
    qtbot.addWidget(workspace)
    workspace.set_controller(controller)

    # 3. Assert UI reflects state
    # Access the combo box to verify it has the item
    # We need to dig into the palette panel -> palette source selector
    palette_panel = workspace.palette_panel
    selector = palette_panel.palette_source_selector

    # We need to find the QComboBox within the selector.
    # Based on code it's stored as self._combo_box but not public.
    # We can find it by type.
    combo = selector.findChild(QComboBox)
    assert combo is not None, "Could not find QComboBox in PaletteSourceSelector"

    # Expect "Default" (always added by widget init) + "Red Palette" (synced from controller)
    # Current behavior: Fails because it only has "Default"
    assert combo.count() == 2, f"Expected 2 items, found {combo.count()}"
    assert combo.itemText(1) == "Red Palette"
