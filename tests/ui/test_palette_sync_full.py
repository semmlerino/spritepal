import numpy as np
import pytest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.core.palette_utils import get_default_snes_palette
from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace


def test_palette_sync_across_workspaces(qtbot):
    # This simulates SpriteEditorWorkspace initialization
    controller = EditingController()

    # Create VRAM workspace and wire it
    vram_workspace = EditWorkspace()
    vram_workspace.set_controller(controller)

    # Create ROM workspace and wire it (shares controller)
    rom_workspace = EditWorkspace()
    rom_workspace.set_controller(controller)

    # 1. Initial state check: Both should have default controller colors (grayscale)
    # Actually, EditingController.load_presets() is called in __init__,
    # but let's assume it starts with grayscale or default.

    # Simulate ROMWorkflowController.open_in_editor behavior:
    # 1. Sprite extracted, no ROM palette found, use default SNES palette fallback.
    fallback_palette = get_default_snes_palette()
    data = np.zeros((16, 16), dtype=np.uint8)
    data[0, 0] = 7  # Should be Blue in fallback
    data[0, 1] = 8  # Should be Green in fallback

    controller.load_image(data, fallback_palette)

    # Verify both canvases see Blue/Green
    qtbot.wait_exposed(rom_workspace)
    rom_canvas = rom_workspace.get_canvas()
    rom_canvas._update_color_lut()

    # Index 7 should be Blue (88, 144, 248)
    assert rom_canvas._qcolor_cache[7].red() == 88
    assert rom_canvas._qcolor_cache[7].green() == 144
    assert rom_canvas._qcolor_cache[7].blue() == 248

    # 2. User loads JSON palette (Orange/Brown)
    orange_palette = [(0, 0, 0)] * 16
    orange_palette[7] = (255, 165, 0)  # Orange
    orange_palette[8] = (139, 69, 19)  # Brown

    # This happens in EditingController.handle_load_palette
    controller.set_palette(orange_palette, "JSON Palette")

    # 3. Check ROM workspace update
    # The PalettePanel should have updated
    assert rom_workspace.palette_panel.get_color_at(7) == (255, 165, 0)

    # The Canvas should have updated
    rom_canvas._update_color_lut()
    assert rom_canvas._qcolor_cache[7].red() == 255
    assert rom_canvas._qcolor_cache[7].green() == 165
    assert rom_canvas._qcolor_cache[7].blue() == 0

    # 4. Check VRAM workspace (it's hidden but should still be connected)
    vram_canvas = vram_workspace.get_canvas()
    vram_canvas._update_color_lut()
    assert vram_canvas._qcolor_cache[7].red() == 255
