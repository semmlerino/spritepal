
import pytest
from PySide6.QtWidgets import QWidget
from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

def test_ready_for_inject_hidden_in_rom_mode(qtbot):
    """Verify that 'Ready for Inject' button is hidden in ROM workflow page."""
    page = ROMWorkflowPage()
    qtbot.addWidget(page)
    
    # Check initial state
    assert not page.workspace._inject_btn.isVisible(), \
        "Ready for Inject button should be hidden in ROM mode"
    
    # Check Save to ROM button visibility (via SaveExportPanel)
    assert page.workspace.save_export_panel.save_to_rom_btn.isVisible(), \
        "Save to ROM button should be visible in ROM mode"

    # Verify set_workflow_mode was called correctly
    # We can't check internal state easily, but we can call it again and verify
    page.workspace.set_workflow_mode("rom")
    assert not page.workspace._inject_btn.isVisible()
    
    page.workspace.set_workflow_mode("vram")
    assert page.workspace._inject_btn.isVisible()
