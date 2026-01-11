"""
Tests for IconToolbar public signal behavior.

These tests verify ONLY observable signal behavior:
- Signal emission count
- Signal argument values
- Signal emission order

They do NOT inspect internal state or private attributes.
The tests should FAIL if the UI stops emitting expected public signals,
even if internal state changes still occur.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestIconToolbarToolSignals:
    """Test IconToolbar emits correct toolChanged signals on UI interaction."""

    def test_pencil_button_click_emits_toolChanged_with_pencil(self, qtbot: QtBot) -> None:
        """Verify clicking pencil button emits toolChanged with 'pencil'."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        # First select a different tool so clicking pencil is a change
        qtbot.mouseClick(toolbar.tool_buttons["fill"], Qt.MouseButton.LeftButton)

        spy = QSignalSpy(toolbar.toolChanged)

        # Drive via real UI interaction
        qtbot.mouseClick(toolbar.tool_buttons["pencil"], Qt.MouseButton.LeftButton)

        # Assert ONLY on signal behavior
        assert spy.count() == 1, "SIGNAL CONTRACT VIOLATION: toolChanged must be emitted when pencil button is clicked."
        assert list(spy.at(0)) == ["pencil"]

    def test_fill_button_click_emits_toolChanged_with_fill(self, qtbot: QtBot) -> None:
        """Verify clicking fill button emits toolChanged with 'fill'."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.toolChanged)

        qtbot.mouseClick(toolbar.tool_buttons["fill"], Qt.MouseButton.LeftButton)

        assert spy.count() == 1, "SIGNAL CONTRACT VIOLATION: toolChanged must be emitted when fill button is clicked."
        assert list(spy.at(0)) == ["fill"]

    def test_picker_button_click_emits_toolChanged_with_picker(self, qtbot: QtBot) -> None:
        """Verify clicking picker button emits toolChanged with 'picker'."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.toolChanged)

        qtbot.mouseClick(toolbar.tool_buttons["picker"], Qt.MouseButton.LeftButton)

        assert spy.count() == 1, "SIGNAL CONTRACT VIOLATION: toolChanged must be emitted when picker button is clicked."
        assert list(spy.at(0)) == ["picker"]

    def test_eraser_button_click_emits_toolChanged_with_eraser(self, qtbot: QtBot) -> None:
        """Verify clicking eraser button emits toolChanged with 'eraser'."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.toolChanged)

        qtbot.mouseClick(toolbar.tool_buttons["eraser"], Qt.MouseButton.LeftButton)

        assert spy.count() == 1, "SIGNAL CONTRACT VIOLATION: toolChanged must be emitted when eraser button is clicked."
        assert list(spy.at(0)) == ["eraser"]

    def test_multiple_tool_clicks_emit_multiple_signals(self, qtbot: QtBot) -> None:
        """Verify each tool button click emits a separate toolChanged signal."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.toolChanged)

        # Click through all tools
        qtbot.mouseClick(toolbar.tool_buttons["fill"], Qt.MouseButton.LeftButton)
        qtbot.mouseClick(toolbar.tool_buttons["picker"], Qt.MouseButton.LeftButton)
        qtbot.mouseClick(toolbar.tool_buttons["eraser"], Qt.MouseButton.LeftButton)
        qtbot.mouseClick(toolbar.tool_buttons["pencil"], Qt.MouseButton.LeftButton)

        assert spy.count() == 4
        assert list(spy.at(0)) == ["fill"]
        assert list(spy.at(1)) == ["picker"]
        assert list(spy.at(2)) == ["eraser"]
        assert list(spy.at(3)) == ["pencil"]


class TestIconToolbarZoomSignals:
    """Test IconToolbar emits correct zoom signals on UI interaction."""

    def test_zoom_in_click_emits_zoomInClicked(self, qtbot: QtBot) -> None:
        """Verify zoom in button emits zoomInClicked signal."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.zoomInClicked)

        assert toolbar.zoom_in_btn is not None
        qtbot.mouseClick(toolbar.zoom_in_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: zoomInClicked must be emitted when zoom in button is clicked."
        )

    def test_zoom_out_click_emits_zoomOutClicked(self, qtbot: QtBot) -> None:
        """Verify zoom out button emits zoomOutClicked signal."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.zoomOutClicked)

        assert toolbar.zoom_out_btn is not None
        qtbot.mouseClick(toolbar.zoom_out_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: zoomOutClicked must be emitted when zoom out button is clicked."
        )


class TestIconToolbarToggleSignals:
    """Test IconToolbar emits correct toggle signals on UI interaction."""

    def test_grid_toggle_emits_gridToggled_true_then_false(self, qtbot: QtBot) -> None:
        """Verify grid toggle emits gridToggled with correct bool state."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.gridToggled)

        # Toggle on (starts unchecked)
        assert toolbar.grid_btn is not None
        qtbot.mouseClick(toolbar.grid_btn, Qt.MouseButton.LeftButton)
        assert spy.count() == 1
        assert list(spy.at(0)) == [True]

        # Toggle off
        qtbot.mouseClick(toolbar.grid_btn, Qt.MouseButton.LeftButton)
        assert spy.count() == 2
        assert list(spy.at(1)) == [False]

    def test_tile_grid_toggle_emits_tileGridToggled(self, qtbot: QtBot) -> None:
        """Verify tile grid toggle emits tileGridToggled with correct bool state."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.tileGridToggled)

        # Toggle on
        assert toolbar.tile_grid_btn is not None
        qtbot.mouseClick(toolbar.tile_grid_btn, Qt.MouseButton.LeftButton)
        assert spy.count() == 1
        assert list(spy.at(0)) == [True]

        # Toggle off
        qtbot.mouseClick(toolbar.tile_grid_btn, Qt.MouseButton.LeftButton)
        assert spy.count() == 2
        assert list(spy.at(1)) == [False]

    def test_palette_preview_toggle_emits_palettePreviewToggled(self, qtbot: QtBot) -> None:
        """Verify palette preview toggle emits palettePreviewToggled with correct bool state."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.palettePreviewToggled)

        # Palette preview starts checked (True), so first click turns it off
        assert toolbar.palette_preview_btn is not None
        qtbot.mouseClick(toolbar.palette_preview_btn, Qt.MouseButton.LeftButton)
        assert spy.count() == 1
        assert list(spy.at(0)) == [False]

        # Toggle back on
        qtbot.mouseClick(toolbar.palette_preview_btn, Qt.MouseButton.LeftButton)
        assert spy.count() == 2
        assert list(spy.at(1)) == [True]


class TestIconToolbarBackgroundSignals:
    """Test IconToolbar emits correct backgroundChanged signals."""

    def test_background_menu_checkerboard_emits_backgroundChanged(self, qtbot: QtBot) -> None:
        """Verify selecting checkerboard background emits backgroundChanged."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.backgroundChanged)

        assert toolbar.background_btn is not None
        menu = toolbar.background_btn.menu()
        assert menu is not None

        # Find and trigger the checkerboard action
        checkerboard_action = menu.actions()[0]  # First action is checkerboard
        checkerboard_action.trigger()

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: backgroundChanged must be emitted when checkerboard background is selected."
        )
        args = list(spy.at(0))
        assert args[0] == "checkerboard"
        # Second arg is None for non-custom backgrounds
        assert args[1] is None

    def test_background_menu_black_emits_backgroundChanged(self, qtbot: QtBot) -> None:
        """Verify selecting black background emits backgroundChanged."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.backgroundChanged)

        assert toolbar.background_btn is not None
        menu = toolbar.background_btn.menu()
        assert menu is not None

        # Find and trigger the black action (second in menu)
        black_action = menu.actions()[1]
        black_action.trigger()

        assert spy.count() == 1
        args = list(spy.at(0))
        assert args[0] == "black"
        assert args[1] is None

    def test_background_menu_white_emits_backgroundChanged(self, qtbot: QtBot) -> None:
        """Verify selecting white background emits backgroundChanged."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.backgroundChanged)

        assert toolbar.background_btn is not None
        menu = toolbar.background_btn.menu()
        assert menu is not None

        # Find and trigger the white action (third in menu)
        white_action = menu.actions()[2]
        white_action.trigger()

        assert spy.count() == 1
        args = list(spy.at(0))
        assert args[0] == "white"
        assert args[1] is None


class TestIconToolbarSignalContract:
    """Tests that document the expected public signal contract."""

    @pytest.mark.parametrize(
        "signal_name",
        [
            "toolChanged",
            "zoomInClicked",
            "zoomOutClicked",
            "gridToggled",
            "tileGridToggled",
            "palettePreviewToggled",
            "backgroundChanged",
        ],
    )
    def test_signal_exists(self, signal_name: str) -> None:
        """Verify all expected public signals exist on IconToolbar."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        assert hasattr(toolbar, signal_name), f"SIGNAL CONTRACT: IconToolbar must expose '{signal_name}' signal"

    def test_programmatic_set_tool_does_not_emit_signal(self, qtbot: QtBot) -> None:
        """Verify set_tool() does not emit toolChanged (avoids feedback loops)."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.toolChanged)

        # Programmatic update should not emit
        toolbar.set_tool("fill")

        assert spy.count() == 0, (
            "set_tool() should use QSignalBlocker to prevent toolChanged emission "
            "when called programmatically (avoids feedback loops)."
        )
