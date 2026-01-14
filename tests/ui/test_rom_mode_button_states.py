import pytest
from PySide6.QtWidgets import QWidget

from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage


def test_ready_for_inject_hidden_in_rom_mode(qtbot):
    """Verify that 'Ready for Inject' button is hidden in ROM workflow page."""
    page = ROMWorkflowPage()
    qtbot.addWidget(page)
    page.show()
    qtbot.waitForWindowShown(page)

    # Check initial state
    assert not page.workspace.is_inject_button_visible, "Ready for Inject button should be hidden in ROM mode"

    # Check Save to ROM button visibility (via SaveExportPanel)
    assert page.workspace.save_export_panel.save_to_rom_btn.isVisible(), (
        "Save to ROM button should be visible in ROM mode"
    )

    # Check initial enabled state (should be disabled until image loaded)
    assert not page.workspace.save_export_panel.save_to_rom_btn.isEnabled(), (
        "Save to ROM button should be disabled initially"
    )

    # Mock controller to trigger enablement
    from unittest.mock import MagicMock

    from PySide6.QtCore import QObject, Signal

    class MockController(QObject):
        imageChanged = Signal()
        paletteChanged = Signal()
        toolChanged = Signal(str)
        colorChanged = Signal(int)
        paletteSourceAdded = Signal(str, str, int, object, bool)
        paletteSourceSelected = Signal(str, int)
        paletteSourcesCleared = Signal(str)
        validationChanged = Signal(bool, list)
        validationChanged = Signal(bool, list)

        def __init__(self):
            super().__init__()
            self.image_model = MagicMock()
            self.palette_model = MagicMock()
            self.palette_model.name = "Test"

        def has_image(self):
            return True

        def get_current_colors(self):
            return [(0, 0, 0)] * 16

        def get_current_tool_name(self):
            return "pencil"

        def get_selected_color(self):
            return 1

        def get_image_size(self):
            return (8, 8)

        def handle_pixel_press(self, x, y):
            pass

        def handle_pixel_move(self, x, y):
            pass

        def handle_pixel_release(self, x, y):
            pass

        def set_tool(self, tool):
            pass

        def set_selected_color(self, color):
            pass

        def handle_palette_source_changed(self, source, index):
            pass

        def handle_load_palette(self):
            pass

        def handle_save_palette(self):
            pass

        def handle_edit_color(self):
            pass

        def get_palette_sources(self):
            return {}

    controller = MockController()
    page.workspace.set_controller(controller)

    # It should be enabled now because has_image() returns True and set_controller calls set_image_loaded
    assert page.workspace.save_export_panel.save_to_rom_btn.isEnabled(), (
        "Save to ROM button should be enabled after controller set"
    )

    # Verify set_workflow_mode was called correctly
    # We can't check internal state easily, but we can call it again and verify
    page.workspace.set_workflow_mode("rom")
    assert not page.workspace.is_inject_button_visible

    page.workspace.set_workflow_mode("vram")
    assert page.workspace.is_inject_button_visible
