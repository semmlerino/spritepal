#!/usr/bin/env python3
"""
Unit tests for the background toggle feature in the sprite editor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar
from ui.sprite_editor.views.widgets.pixel_canvas import PixelCanvas
from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = [pytest.mark.parallel_unsafe]


class TestBackgroundToggle:
    """Tests for background toggle functionality."""

    def test_canvas_default_background(self, qtbot: QtBot) -> None:
        """Verify PixelCanvas default background is checkerboard."""
        mock_controller = Mock()
        mock_controller.has_image.return_value = False
        mock_controller.get_current_tool_name.return_value = "pencil"

        canvas = PixelCanvas(mock_controller)
        qtbot.addWidget(canvas)

        assert canvas.background_type == "checkerboard"

    def test_canvas_set_background(self, qtbot: QtBot) -> None:
        """Verify PixelCanvas can change background type."""
        mock_controller = Mock()
        mock_controller.has_image.return_value = False
        mock_controller.get_current_tool_name.return_value = "pencil"

        canvas = PixelCanvas(mock_controller)
        qtbot.addWidget(canvas)

        canvas.set_background("black")
        assert canvas.background_type == "black"

        canvas.set_background("white")
        assert canvas.background_type == "white"

        custom_color = QColor(255, 0, 0)
        canvas.set_background("custom", custom_color)
        assert canvas.background_type == "custom"
        assert canvas.custom_background_color == custom_color

    def test_toolbar_background_signals(self, qtbot: QtBot) -> None:
        """Verify IconToolbar background button emits signals."""
        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        signal_spy = Mock()
        toolbar.backgroundChanged.connect(signal_spy)

        # We can't easily click the menu items, but we can trigger the actions
        menu = toolbar.background_btn.menu()
        for action in menu.actions():
            if action.text() == "Black":
                action.trigger()
                break

        QCoreApplication.processEvents()
        signal_spy.assert_called_with("black", None)

    def test_workspace_background_wiring(self, qtbot: QtBot) -> None:
        """Verify EditWorkspace correctly wires toolbar to canvas for background."""
        # Create controller
        controller = EditingController()

        workspace = EditWorkspace()
        qtbot.addWidget(workspace)
        workspace.set_controller(controller)

        canvas = workspace.get_canvas()
        assert canvas is not None

        # Trigger background change from toolbar
        workspace.icon_toolbar.backgroundChanged.emit("white", None)

        assert canvas.background_type == "white"
