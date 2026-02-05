#!/usr/bin/env python3
"""
Regression test for AIFramePaletteEditorWindow in-game canvas refresh bug.

Bug: When a palette color was changed via right-click, the main canvas was
refreshed but the in-game canvas was not updated, even though both share
the same palette.

Fix: _on_palette_color_changed() now refreshes both canvases.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.frame_mapping_project import SheetPalette


def test_palette_color_change_refreshes_ingame_canvas():
    """Test that changing a palette color refreshes the in-game canvas.

    Regression test: Previously, only the main canvas was refreshed when
    a palette color changed. The in-game canvas should also be refreshed
    since it shares the same palette.
    """
    from ui.frame_mapping.windows.ai_frame_palette_editor import AIFramePaletteEditorWindow

    # Create a SheetPalette with 16 colors
    colors = [(i * 16, i * 16, i * 16) for i in range(16)]
    palette = SheetPalette(colors=colors)

    # Create mock controllers
    main_controller = MagicMock()
    ingame_controller = MagicMock()

    # Create mock canvases
    main_canvas = MagicMock()
    ingame_canvas = MagicMock()

    # Create mock indexed data (8x8 image)
    main_data = np.zeros((8, 8), dtype=np.uint8)
    ingame_data = np.ones((8, 8), dtype=np.uint8)

    # Set up controller return values
    main_controller.get_indexed_data.return_value = main_data
    ingame_controller.get_indexed_data.return_value = ingame_data

    # Create a minimal window instance without full initialization
    # We'll manually set up the attributes we need
    window = AIFramePaletteEditorWindow.__new__(AIFramePaletteEditorWindow)
    window._palette = palette
    window._main_controller = main_controller
    window._ingame_controller = ingame_controller
    window._main_canvas = main_canvas
    window._ingame_canvas = ingame_canvas
    window._palette_panel = MagicMock()
    # Mock the signal to avoid Qt runtime error
    window.palette_color_changed = MagicMock()

    # Call the handler directly
    new_color = (255, 0, 0)  # Red
    window._on_palette_color_changed(1, new_color)

    # Verify the palette was updated
    assert palette.colors[1] == new_color

    # Verify main controller was called
    main_controller.set_palette_color.assert_called_once_with(1, new_color)

    # Verify main canvas was refreshed
    main_canvas.set_image.assert_called_once()
    main_call_args = main_canvas.set_image.call_args
    assert np.array_equal(main_call_args[0][0], main_data)
    assert main_call_args[0][1] is palette

    # CRITICAL: Verify in-game canvas was also refreshed (the bug fix)
    ingame_canvas.set_image.assert_called_once()
    ingame_call_args = ingame_canvas.set_image.call_args
    assert np.array_equal(ingame_call_args[0][0], ingame_data)
    assert ingame_call_args[0][1] is palette

    # Verify palette panel was synced
    window._palette_panel.sync_palette.assert_called_once_with(palette)

    # Verify signal was emitted
    window.palette_color_changed.emit.assert_called_once_with(1, new_color)


def test_palette_color_change_without_ingame_canvas():
    """Test palette color change when in-game canvas is not active.

    Should not crash when ingame_controller or ingame_canvas is None.
    """
    from ui.frame_mapping.windows.ai_frame_palette_editor import AIFramePaletteEditorWindow

    # Create a SheetPalette with 16 colors
    colors = [(i * 16, i * 16, i * 16) for i in range(16)]
    palette = SheetPalette(colors=colors)

    # Create mock controller and canvas (main only)
    main_controller = MagicMock()
    main_canvas = MagicMock()

    # Create mock indexed data
    main_data = np.zeros((8, 8), dtype=np.uint8)
    main_controller.get_indexed_data.return_value = main_data

    # Create a minimal window instance without in-game canvas
    window = AIFramePaletteEditorWindow.__new__(AIFramePaletteEditorWindow)
    window._palette = palette
    window._main_controller = main_controller
    window._ingame_controller = None  # No in-game controller
    window._ingame_canvas = None  # No in-game canvas
    window._main_canvas = main_canvas
    window._palette_panel = MagicMock()
    # Mock the signal to avoid Qt runtime error
    window.palette_color_changed = MagicMock()

    # Call the handler - should not crash
    new_color = (0, 255, 0)  # Green
    window._on_palette_color_changed(2, new_color)

    # Verify the palette was updated
    assert palette.colors[2] == new_color

    # Verify main canvas was refreshed
    main_canvas.set_image.assert_called_once()

    # In-game canvas should not be called (doesn't exist)
    # No assertion needed - if it crashes, the test fails


def test_palette_color_change_with_none_data():
    """Test palette color change when get_indexed_data returns None.

    Should handle gracefully when controllers return None.
    """
    from ui.frame_mapping.windows.ai_frame_palette_editor import AIFramePaletteEditorWindow

    # Create a SheetPalette with 16 colors
    colors = [(i * 16, i * 16, i * 16) for i in range(16)]
    palette = SheetPalette(colors=colors)

    # Create mock controllers
    main_controller = MagicMock()
    ingame_controller = MagicMock()

    # Create mock canvases
    main_canvas = MagicMock()
    ingame_canvas = MagicMock()

    # Set up controllers to return None (no data loaded)
    main_controller.get_indexed_data.return_value = None
    ingame_controller.get_indexed_data.return_value = None

    # Create a minimal window instance
    window = AIFramePaletteEditorWindow.__new__(AIFramePaletteEditorWindow)
    window._palette = palette
    window._main_controller = main_controller
    window._ingame_controller = ingame_controller
    window._main_canvas = main_canvas
    window._ingame_canvas = ingame_canvas
    window._palette_panel = MagicMock()
    # Mock the signal to avoid Qt runtime error
    window.palette_color_changed = MagicMock()

    # Call the handler - should not crash
    new_color = (0, 0, 255)  # Blue
    window._on_palette_color_changed(3, new_color)

    # Verify the palette was updated
    assert palette.colors[3] == new_color

    # Verify controllers were called
    main_controller.set_palette_color.assert_called_once_with(3, new_color)
    main_controller.get_indexed_data.assert_called_once()
    ingame_controller.get_indexed_data.assert_called_once()

    # Canvases should not be called when data is None
    main_canvas.set_image.assert_not_called()
    ingame_canvas.set_image.assert_not_called()
