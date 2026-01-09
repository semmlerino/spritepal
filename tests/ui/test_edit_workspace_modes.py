import pytest

from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace


def test_edit_workspace_modes(qtbot):
    """Verify that setting workflow mode updates button visibility correctly."""
    workspace = EditWorkspace()
    qtbot.addWidget(workspace)
    workspace.show()

    # Test VRAM Mode
    # - Ready for Inject: Visible (switch to inject tab)
    # - Save to ROM: Hidden (not applicable)
    # - Export PNG: Visible
    workspace.set_workflow_mode("vram")

    assert workspace.is_inject_button_visible is True
    assert workspace._save_export_panel.save_to_rom_btn.isVisible() is False
    assert workspace._save_export_panel.export_png_btn.isVisible() is True

    # Test ROM Mode
    # - Ready for Inject: Hidden (stay in same view)
    # - Save to ROM: Visible (direct injection)
    # - Export PNG: Visible
    workspace.set_workflow_mode("rom")

    assert workspace.is_inject_button_visible is False
    assert workspace._save_export_panel.save_to_rom_btn.isVisible() is True
    assert workspace._save_export_panel.export_png_btn.isVisible() is True
