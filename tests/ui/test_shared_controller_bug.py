from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace


def test_shared_controller_disconnection(qtbot):
    """Regression test: connecting workspace2 must not disconnect workspace1.

    This verifies that when multiple workspaces share a controller,
    connecting a second workspace doesn't break signal delivery to the first.
    """
    # Shared controller
    controller = EditingController()

    # Create two workspaces
    workspace1 = EditWorkspace()
    workspace2 = EditWorkspace()

    # Wire workspace1 to controller
    workspace1.set_controller(controller)

    # Set a known palette state on workspace1
    initial_palette = [(0, 0, 0)] * 16
    initial_palette[5] = (100, 100, 100)  # Gray
    controller.set_palette(initial_palette, "Initial")

    # Verify workspace1 has the initial palette
    assert workspace1.palette_panel.get_color_at(5) == (100, 100, 100)

    # Now wire workspace2 to the same controller
    # This is the critical moment - workspace1 should NOT be disconnected
    workspace2.set_controller(controller)

    # Change the palette via controller
    new_palette = [(0, 0, 0)] * 16
    new_palette[5] = (255, 0, 0)  # Red
    controller.set_palette(new_palette, "Changed")

    # If workspace1 was disconnected, it won't see the new palette
    assert workspace1.palette_panel.get_color_at(5) == (255, 0, 0), (
        "Workspace 1 was disconnected by Workspace 2's set_controller call! "
        "Expected (255, 0, 0) but palette wasn't updated."
    )

    # Verify workspace2 also received the update
    assert workspace2.palette_panel.get_color_at(5) == (255, 0, 0)
