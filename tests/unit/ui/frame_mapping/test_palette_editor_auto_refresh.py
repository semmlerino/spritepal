#!/usr/bin/env python3
"""Tests for auto-refresh of in-game canvas when main canvas is painted."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.frame_mapping_project import SheetPalette


def _make_window(
    *,
    preview_enabled: bool = True,
    ingame_dirty: bool = False,
    has_ingame: bool = True,
    has_mapping: bool = True,
    has_frame_controller: bool = True,
):
    """Create a minimal AIFramePaletteEditorWindow for testing."""
    from ui.frame_mapping.windows.ai_frame_palette_editor import AIFramePaletteEditorWindow

    colors = [(i * 16, i * 16, i * 16) for i in range(16)]
    palette = SheetPalette(colors=colors)

    main_controller = MagicMock()
    main_controller.get_indexed_data.return_value = np.zeros((8, 8), dtype=np.uint8)
    main_controller.active_index = 0

    ai_frame = MagicMock()
    ai_frame.id = "test-frame-id"

    mapping = MagicMock() if has_mapping else None

    frame_controller = MagicMock() if has_frame_controller else None
    if frame_controller is not None:
        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = mapping
        frame_controller.project = project

    ingame_controller = None
    ingame_canvas = None
    if has_ingame:
        ingame_controller = MagicMock()
        ingame_controller.is_dirty = ingame_dirty
        ingame_canvas = MagicMock()

    window = AIFramePaletteEditorWindow.__new__(AIFramePaletteEditorWindow)
    window._palette = palette
    window._main_controller = main_controller
    window._ingame_controller = ingame_controller
    window._main_canvas = MagicMock()
    window._ingame_canvas = ingame_canvas
    window._ingame_refresh_timer = None
    window._preview_enabled = preview_enabled
    window._frame_controller = frame_controller
    window._ai_frame = ai_frame
    window._status_bar = MagicMock()

    return window


def test_main_paint_schedules_ingame_refresh():
    """Verify _generate_ingame_canvas is called after debounce timer fires."""
    window = _make_window()

    with (
        patch.object(window, "_generate_ingame_canvas") as mock_gen,
        patch("ui.frame_mapping.windows.ai_frame_palette_editor.QTimer") as mock_qtimer_cls,
    ):
        # Set up mock QTimer
        mock_timer = MagicMock()
        mock_qtimer_cls.return_value = mock_timer

        # Call _on_main_image_changed which should schedule refresh
        window._on_main_image_changed()

        # Timer should have been created
        assert window._ingame_refresh_timer is not None
        mock_qtimer_cls.assert_called_once_with(window)
        mock_timer.setSingleShot.assert_called_once_with(True)
        mock_timer.timeout.connect.assert_called_once_with(window._do_auto_refresh_ingame)
        mock_timer.start.assert_called_once_with(200)

        # Manually fire the timer's timeout (simulate debounce completing)
        # by calling the method that would be triggered
        window._do_auto_refresh_ingame()

        # Should have called _generate_ingame_canvas with the mapping
        mock_gen.assert_called_once()


def test_debounce_coalesces_rapid_changes():
    """3 rapid _on_main_image_changed calls should result in only 1 refresh."""
    window = _make_window()

    with (
        patch.object(window, "_generate_ingame_canvas") as mock_gen,
        patch("ui.frame_mapping.windows.ai_frame_palette_editor.QTimer") as mock_qtimer_cls,
    ):
        # Set up mock QTimer
        mock_timer = MagicMock()
        mock_qtimer_cls.return_value = mock_timer

        # Simulate 3 rapid changes
        window._on_main_image_changed()
        window._on_main_image_changed()
        window._on_main_image_changed()

        # Timer should exist but _generate_ingame_canvas not yet called
        assert window._ingame_refresh_timer is not None
        mock_gen.assert_not_called()

        # Timer should only be created once (reused for subsequent calls)
        mock_qtimer_cls.assert_called_once()
        # But start() should be called 3 times (once per change)
        assert mock_timer.start.call_count == 3

        # Fire timeout once by calling the callback
        window._do_auto_refresh_ingame()

        # Should only be called once despite 3 changes
        mock_gen.assert_called_once()


def test_skip_when_ingame_dirty():
    """When in-game controller is dirty, auto-refresh should be skipped."""
    window = _make_window(ingame_dirty=True)

    with patch.object(window, "_generate_ingame_canvas") as mock_gen:
        window._on_main_image_changed()

        # Timer should NOT have been created
        assert window._ingame_refresh_timer is None
        mock_gen.assert_not_called()


def test_skip_when_preview_disabled():
    """When preview is disabled, auto-refresh should be skipped."""
    window = _make_window(preview_enabled=False)

    with patch.object(window, "_generate_ingame_canvas") as mock_gen:
        window._on_main_image_changed()

        # Timer should NOT have been created
        assert window._ingame_refresh_timer is None
        mock_gen.assert_not_called()


def test_skip_when_no_mapping():
    """When no mapping exists, auto-refresh should not crash and should skip."""
    window = _make_window(has_mapping=False)

    with patch.object(window, "_generate_ingame_canvas") as mock_gen:
        window._on_main_image_changed()

        # Should not crash, timer should not be created (or not started meaningfully)
        mock_gen.assert_not_called()
