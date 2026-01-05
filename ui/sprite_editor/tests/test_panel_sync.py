#!/usr/bin/env python3
"""
Regression tests for panel synchronization fixes (Task 4.1.B).

Tests verify bidirectional sync between EditingController and EditTab panels
(tool panel, palette panel) to prevent desync between UI and controller state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QCoreApplication

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestPanelSynchronization:
    """Tests for controller ↔ panel bidirectional sync."""

    def test_tool_panel_syncs_from_controller(self, qtbot: QtBot) -> None:
        """Verify tool_panel updates when controller.set_tool() is called.

        Bug: Controller state changes not reflected in tool panel UI.

        Fix: EditTab connects controller.toolChanged → tool_panel.set_tool
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.tabs.edit_tab import EditTab

        # Create controller and tab
        controller = EditingController()
        tab = EditTab(parent=None)

        # Set controller on tab (triggers signal connection)
        tab.set_controller(controller)

        # Verify initial state (pencil is default)
        assert controller.get_current_tool_name() == "pencil"
        assert tab.tool_panel.get_current_tool() == "pencil"

        # Change tool via controller
        controller.set_tool("fill")
        QCoreApplication.processEvents()

        # Verify tool panel synced
        assert tab.tool_panel.get_current_tool() == "fill", "Tool panel should sync when controller.set_tool() called"

        # Change to picker
        controller.set_tool("picker")
        QCoreApplication.processEvents()

        assert tab.tool_panel.get_current_tool() == "picker"

    def test_palette_panel_syncs_color(self, qtbot: QtBot) -> None:
        """Verify palette_panel updates when controller.set_selected_color() is called.

        Bug: Color selection in controller not reflected in palette panel UI.

        Fix: EditTab connects controller.colorChanged → palette_panel.set_selected_color
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.tabs.edit_tab import EditTab

        # Create controller and tab
        controller = EditingController()
        tab = EditTab(parent=None)

        # Set controller on tab
        tab.set_controller(controller)

        # Verify initial state (color 1 is default)
        assert controller.get_selected_color() == 1
        assert tab.palette_panel.get_selected_color() == 1

        # Change color via controller
        controller.set_selected_color(5)
        QCoreApplication.processEvents()

        # Verify palette panel synced
        assert tab.palette_panel.palette_widget.selected_index == 5, (
            "Palette panel should sync when controller.set_selected_color() called"
        )

        # Change to another color
        controller.set_selected_color(12)
        QCoreApplication.processEvents()

        assert tab.palette_panel.get_selected_color() == 12

    def test_palette_panel_syncs_on_load(self, qtbot: QtBot) -> None:
        """Verify palette_panel updates when image with palette is loaded.

        Bug: Loading image with custom palette doesn't update palette panel.

        Fix: EditTab connects controller.paletteChanged → _update_palette
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.tabs.edit_tab import EditTab

        # Create controller and tab
        controller = EditingController()
        tab = EditTab(parent=None)

        # Set controller on tab
        tab.set_controller(controller)

        # Create test image and custom palette
        test_data = np.zeros((16, 16), dtype=np.uint8)
        custom_palette = [
            (255, 0, 0),  # Red
            (0, 255, 0),  # Green
            (0, 0, 255),  # Blue
            *[(i * 16, i * 16, i * 16) for i in range(13)],  # Grayscale for rest
        ]

        # Load image with palette via controller
        controller.load_image(test_data, custom_palette)
        QCoreApplication.processEvents()

        # Verify palette panel displays correct colors
        displayed_colors = tab.palette_panel.get_palette_colors()
        assert len(displayed_colors) == 16, "Palette panel should show 16 colors"
        assert displayed_colors[0] == (255, 0, 0), "First color should be red"
        assert displayed_colors[1] == (0, 255, 0), "Second color should be green"
        assert displayed_colors[2] == (0, 0, 255), "Third color should be blue"

    def test_brush_size_syncs_from_controller(self, qtbot: QtBot) -> None:
        """Verify tool_panel brush size updates when controller.set_brush_size() is called.

        Note: Currently, brush size does NOT have automatic bidirectional sync
        (no controller.brushSizeChanged signal). Brush size syncs only via
        update_from_controller() which is called manually when needed.

        This test verifies the current behavior where programmatic controller changes
        do NOT automatically sync to panel, but update_from_controller() does work.
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.tabs.edit_tab import EditTab

        # Create controller and tab
        controller = EditingController()
        tab = EditTab(parent=None)

        # Set controller on tab
        tab.set_controller(controller)

        # Verify initial brush size
        assert controller.tool_manager.get_brush_size() == 1
        assert tab.tool_panel.get_brush_size() == 1

        # Change brush size via controller
        controller.set_brush_size(3)
        QCoreApplication.processEvents()

        # Currently brush size does NOT auto-sync (no signal connection)
        # This is expected behavior - brush size is not signaled
        assert tab.tool_panel.get_brush_size() == 1, "Tool panel brush size does NOT auto-sync (no signal connection)"

        # However, update_from_controller() SHOULD sync it
        tab.update_from_controller()
        QCoreApplication.processEvents()

        assert tab.tool_panel.get_brush_size() == 3, (
            "Tool panel brush size should sync when update_from_controller() is called"
        )

    def test_update_from_controller_syncs_all_panels(self, qtbot: QtBot) -> None:
        """Verify update_from_controller() syncs all panel states.

        This is called when switching sprites or reconnecting controller.
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.tabs.edit_tab import EditTab

        # Create controller and tab
        controller = EditingController()
        tab = EditTab(parent=None)

        # Set controller on tab
        tab.set_controller(controller)

        # Change controller state
        controller.set_tool("fill")
        controller.set_brush_size(4)
        controller.set_selected_color(7)
        QCoreApplication.processEvents()

        # Reset panel state manually (simulate desync)
        tab.tool_panel.set_tool("pencil")
        tab.tool_panel.set_brush_size(1)
        tab.palette_panel.set_selected_color(0)
        QCoreApplication.processEvents()

        # Verify panels are desynced
        assert tab.tool_panel.get_current_tool() == "pencil"
        assert tab.tool_panel.get_brush_size() == 1
        assert tab.palette_panel.get_selected_color() == 0

        # Call update_from_controller to re-sync
        tab.update_from_controller()
        QCoreApplication.processEvents()

        # Verify all panels synced back to controller state
        assert tab.tool_panel.get_current_tool() == "fill", "Tool should sync from controller"
        assert tab.tool_panel.get_brush_size() == 4, "Brush size should sync from controller"
        assert tab.palette_panel.get_selected_color() == 7, "Selected color should sync from controller"

    def test_tool_change_signal_not_blocked_on_user_click(self, qtbot: QtBot) -> None:
        """Verify user-initiated tool changes DO emit signals (not blocked).

        QSignalBlocker should only block programmatic updates from controller,
        not user interactions with the tool panel.
        """
        from unittest.mock import Mock

        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.tabs.edit_tab import EditTab

        # Create controller and tab
        controller = EditingController()
        tab = EditTab(parent=None)

        # Set controller on tab
        tab.set_controller(controller)

        # Connect signal spy to controller
        signal_spy = Mock()
        controller.toolChanged.connect(signal_spy)

        # Simulate user clicking fill button
        tab.tool_panel.fill_btn.click()
        QCoreApplication.processEvents()

        # Signal should have been emitted (user action)
        assert signal_spy.call_count > 0, "User-initiated tool change should emit signal"
        assert controller.get_current_tool_name() == "fill"

    def test_color_change_signal_not_blocked_on_user_click(self, qtbot: QtBot) -> None:
        """Verify user-initiated color changes DO emit signals (not blocked)."""
        from unittest.mock import Mock

        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.tabs.edit_tab import EditTab

        # Create controller and tab
        controller = EditingController()
        tab = EditTab(parent=None)

        # Set controller on tab
        tab.set_controller(controller)

        # Connect signal spy to controller
        signal_spy = Mock()
        controller.colorChanged.connect(signal_spy)

        # Simulate user clicking palette color directly on widget
        # (This emits colorSelected signal which connects to controller)
        tab.palette_panel.palette_widget.colorSelected.emit(8)
        QCoreApplication.processEvents()

        # Signal should propagate through to controller
        assert signal_spy.call_count > 0, "User-initiated color change should emit signal"
        assert controller.get_selected_color() == 8
