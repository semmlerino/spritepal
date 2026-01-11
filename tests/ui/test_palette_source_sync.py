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

    # The controller loads presets from default_palettes.json in load_presets(),
    # plus "Default" from widget init, plus our "Red Palette"
    # We verify that our registered palette is present in the combo
    combo_items = [combo.itemText(i) for i in range(combo.count())]
    assert "Red Palette" in combo_items, f"'Red Palette' not found in combo items: {combo_items[:5]}..."

    # Verify the controller's palette sources include our registered palette
    sources = controller.get_palette_sources()
    assert ("rom", 10) in sources, f"('rom', 10) not found in controller sources: {list(sources.keys())[:5]}..."


def test_rom_workspace_palette_source_syncs(qtbot):
    """
    Contract: Programmatic palette source selection updates the ROM workspace dropdown.

    Verifies that when EditingController.set_palette_source() is called,
    the ROM EditWorkspace's palette selector also updates (not just VRAM EditTab).

    Regression: Before fix, EditingController only updated self._view (VRAM EditTab),
    leaving the ROM workspace's dropdown stale.
    """
    from ui.sprite_editor.views.tabs.edit_tab import EditTab

    controller = EditingController()

    # Setup VRAM view (like normal initialization in SpriteEditorWorkspace)
    vram_tab = EditTab()
    qtbot.addWidget(vram_tab)
    controller.set_view(vram_tab)

    # Setup ROM workspace (connected separately, like in SpriteEditorWorkspace._wire_controllers)
    rom_workspace = EditWorkspace()
    qtbot.addWidget(rom_workspace)
    rom_workspace.set_controller(controller)

    # Register a ROM palette and select it programmatically
    colors = [(0, 0, 0)] * 16
    controller.register_palette_source("rom", 8, colors, "ROM Palette 8")
    controller.set_palette_source("rom", 8)

    # Verify controller state (source of truth)
    assert ("rom", 8) in controller.get_palette_sources()

    # Verify ROM workspace dropdown reflects the selection
    selector = rom_workspace.palette_panel.palette_source_selector
    selected_source = selector.get_selected_source()
    assert selected_source == (
        "rom",
        8,
    ), f"Expected ('rom', 8), got {selected_source}"


def test_load_palette_updates_selector(qtbot, tmp_path):
    """
    Verify that loading a palette file registers it as a "file" source
    and updates the dropdown selector.

    Regression: Before fix, handle_load_palette() bypassed the source system,
    leaving the dropdown showing "Default" while colors showed the loaded file.
    """
    from unittest.mock import patch

    controller = EditingController()

    # Setup workspace
    workspace = EditWorkspace()
    qtbot.addWidget(workspace)
    workspace.set_controller(controller)

    # Create a test JASC-PAL file
    pal_file = tmp_path / "test.pal"
    pal_file.write_text("JASC-PAL\n0100\n16\n" + "\n".join(f"{i * 16} {i * 16} {i * 16}" for i in range(16)))

    # Mock the file dialog to return our test file
    with patch(
        "PySide6.QtWidgets.QFileDialog.getOpenFileName",
        return_value=(str(pal_file), ""),
    ):
        controller.handle_load_palette()

    # Verify: "file" source should be registered and selected
    selector = workspace.palette_panel.palette_source_selector
    selected_source = selector.get_selected_source()
    assert selected_source == ("file", 0), f"Expected ('file', 0), got {selected_source}"

    # Verify: Dropdown should have "Loaded Palette" item
    combo = selector.findChild(QComboBox)
    item_texts = [combo.itemText(i) for i in range(combo.count())]
    assert "Loaded Palette" in item_texts, f"Expected 'Loaded Palette' in {item_texts}"
