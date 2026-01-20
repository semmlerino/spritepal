"""
Tests for palette persistence across application restarts.

Feature: The last loaded palette file should be automatically reloaded on startup.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication

from core.app_context import AppContext
from ui.sprite_editor.controllers.editing_controller import EditingController


@pytest.fixture
def red_palette_json(tmp_path: Path) -> Path:
    """Create a test palette JSON with all red colors."""
    palette_file = tmp_path / "red_palette.pal.json"
    palette_data = {
        "name": "Test Red Palette",
        "colors": [[255, 0, 0]] * 16,  # All red
    }
    palette_file.write_text(json.dumps(palette_data))
    return palette_file


def test_palette_path_saved_on_load(qtbot, app_context: AppContext, red_palette_json: Path) -> None:
    """Verify that loading a palette saves its path to settings."""
    controller = EditingController()
    state_manager = app_context.application_state_manager

    # Initially last_palette_path should be empty
    assert state_manager.get("paths", "last_palette_path", "") == ""

    # Load palette via controller
    success = controller.load_palette_from_file(str(red_palette_json))
    assert success is True

    # Verify path is saved in settings
    saved_path = state_manager.get("paths", "last_palette_path", "")
    assert saved_path == str(red_palette_json)


def test_palette_auto_loaded_on_init(qtbot, app_context: AppContext, red_palette_json: Path) -> None:
    """Verify that EditingController loads the last used palette on initialization."""
    state_manager = app_context.application_state_manager

    # Pre-set the last_palette_path in settings
    state_manager.set("paths", "last_palette_path", str(red_palette_json))
    state_manager.save_settings()

    # Create new controller - it should auto-load from settings
    # We need to mock AppContext.get_app_context to return our app_context
    with patch("core.app_context.get_app_context", return_value=app_context):
        controller = EditingController()

    # Verify palette colors are red
    colors = controller.get_current_colors()
    assert colors[0] == (255, 0, 0)
    assert colors[15] == (255, 0, 0)

    # Verify it's registered as a 'file' source
    current_source = controller.get_current_palette_source()
    assert current_source == ("file", 0)


def test_workspace_syncs_palette_on_set_controller(qtbot, app_context: AppContext, red_palette_json: Path) -> None:
    """Verify that EditWorkspace synchronizes with the controller's current palette."""
    from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace

    # Setup controller with loaded palette
    controller = EditingController()
    controller.load_palette_from_file(str(red_palette_json))

    # Create workspace
    workspace = EditWorkspace()
    qtbot.addWidget(workspace)

    # Set controller - this should sync palette UI
    workspace.set_controller(controller)

    # Verify palette panel shows the custom palette
    # Check current colors in palette panel
    panel_colors = workspace.palette_panel.get_palette_colors()
    assert panel_colors[0] == (255, 0, 0)

    # Verify source selector shows the file source
    selector = workspace.palette_panel.palette_source_selector
    current_source = selector.get_selected_source()
    assert current_source == ("file", 0)
