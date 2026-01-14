import numpy as np

from ui.sprite_editor import get_default_snes_palette
from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace


def test_palette_sync_across_workspaces(qtbot):
    """Verify palette changes propagate to both workspaces sharing a controller.

    This tests the signal wiring between EditingController and multiple
    EditWorkspace instances, ensuring palette changes are visible in all.
    """
    # Create shared controller
    controller = EditingController()

    # Create two workspaces sharing the controller
    vram_workspace = EditWorkspace()
    vram_workspace.set_controller(controller)

    rom_workspace = EditWorkspace()
    rom_workspace.set_controller(controller)

    # Load initial image with default SNES palette
    fallback_palette = get_default_snes_palette()
    data = np.zeros((16, 16), dtype=np.uint8)
    data[0, 0] = 7  # Index 7 = Blue (88, 144, 248) in default palette

    controller.load_image(data, fallback_palette)
    qtbot.wait_exposed(rom_workspace)

    # Verify initial palette via public API (palette panel reflects controller state)
    # Index 7 should be Blue (88, 144, 248)
    assert rom_workspace.palette_panel.get_color_at(7) == (88, 144, 248)
    assert vram_workspace.palette_panel.get_color_at(7) == (88, 144, 248)

    # User loads a different palette (Orange at index 7)
    orange_palette = [(0, 0, 0)] * 16
    orange_palette[7] = (255, 165, 0)  # Orange
    orange_palette[8] = (139, 69, 19)  # Brown

    controller.set_palette(orange_palette, "JSON Palette")

    # Both workspaces should reflect the new palette
    assert rom_workspace.palette_panel.get_color_at(7) == (255, 165, 0)
    assert vram_workspace.palette_panel.get_color_at(7) == (255, 165, 0)
