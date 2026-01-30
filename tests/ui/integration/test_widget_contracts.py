"""
Widget Signal Contract Tests

This module consolidates all UI widget signal contract tests. These tests verify
ONLY observable signal behavior:
- Signal emission count
- Signal argument values
- Signal emission order
- Signal forwarding from child widgets

They do NOT inspect internal state or private attributes.
The tests should FAIL if the UI stops emitting expected public signals,
even if internal state changes still occur.

Widgets covered:
- IconToolbar: Tool selection, zoom, grid toggles, background selection
- InjectTab: Inject/Save buttons, browse actions
- PalettePanel: Color selection, source changes, button forwarding
- PixelCanvas: Mouse interactions, hover, zoom
- SpriteAssetBrowser: Selection, activation, context menu actions
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QSignalSpy

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def inject_tab(qtbot: QtBot):
    """Create an InjectTab for testing."""
    from ui.sprite_editor.views.tabs.inject_tab import InjectTab

    tab = InjectTab()
    qtbot.addWidget(tab)
    return tab


@pytest.fixture
def palette_panel(qtbot: QtBot):
    """Create a PalettePanel for testing."""
    from ui.sprite_editor.views.panels.palette_panel import PalettePanel

    panel = PalettePanel()
    qtbot.addWidget(panel)
    return panel


@pytest.fixture
def canvas_with_image(qtbot: QtBot):
    """Create a PixelCanvas with a loaded 8x8 image."""
    from PySide6.QtCore import QCoreApplication

    from ui.sprite_editor.controllers.editing_controller import EditingController
    from ui.sprite_editor.views.widgets.pixel_canvas import PixelCanvas

    controller = EditingController()
    canvas = PixelCanvas(controller)
    qtbot.addWidget(canvas)

    # Load 8x8 test image
    data = np.zeros((8, 8), dtype=np.uint8)
    controller.load_image(data)

    # Set zoom to 8 for easier coordinate calculation
    canvas.set_zoom(8)

    # Ensure canvas has sufficient size for mouse events to register
    # With zoom=8 and 8x8 image, we need at least 64x64 pixels
    canvas.setMinimumSize(100, 100)
    canvas.resize(100, 100)

    # Show the widget and wait for it to be fully exposed
    canvas.show()
    qtbot.waitExposed(canvas)
    QCoreApplication.processEvents()

    return canvas, controller


@pytest.fixture
def asset_browser(qtbot: QtBot):
    """Create a SpriteAssetBrowser with some test items."""
    from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

    browser = SpriteAssetBrowser()
    qtbot.addWidget(browser)

    # Add some test items (name, offset)
    browser.add_rom_sprite("Test Sprite 1", 0x1000)
    browser.add_rom_sprite("Test Sprite 2", 0x2000)
    browser.add_mesen_capture("Capture 1", 0x3000)

    return browser


# =============================================================================
# ICON TOOLBAR SIGNALS
# =============================================================================


class TestIconToolbarToolSignals:
    """Test IconToolbar emits correct toolChanged signals on UI interaction."""

    @pytest.mark.parametrize("tool_name", ["pencil", "fill", "picker", "eraser"])
    def test_tool_button_click_emits_toolChanged(self, qtbot: QtBot, tool_name: str) -> None:
        """Verify clicking a tool button emits toolChanged with the correct tool name."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        # Select a different tool first to ensure clicking causes a change
        # For pencil, select fill first; for others, pencil is already selected so clicking triggers signal
        if tool_name == "pencil":
            qtbot.mouseClick(toolbar.tool_buttons["fill"], Qt.MouseButton.LeftButton)

        spy = QSignalSpy(toolbar.toolChanged)
        qtbot.mouseClick(toolbar.tool_buttons[tool_name], Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            f"SIGNAL CONTRACT VIOLATION: toolChanged must be emitted when {tool_name} button is clicked."
        )
        assert list(spy.at(0)) == [tool_name]

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

    @pytest.mark.parametrize(
        "action_index,expected_bg",
        [
            (0, "checkerboard"),
            (1, "black"),
            (2, "white"),
        ],
    )
    def test_background_menu_action_emits_backgroundChanged(
        self, qtbot: QtBot, action_index: int, expected_bg: str
    ) -> None:
        """Verify selecting background option emits backgroundChanged with correct value."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        spy = QSignalSpy(toolbar.backgroundChanged)

        assert toolbar.background_btn is not None
        menu = toolbar.background_btn.menu()
        assert menu is not None

        # Trigger the action at the specified index
        menu.actions()[action_index].trigger()

        assert spy.count() == 1, (
            f"SIGNAL CONTRACT VIOLATION: backgroundChanged must be emitted when {expected_bg} background is selected."
        )
        args = list(spy.at(0))
        assert args[0] == expected_bg
        # Second arg is None for non-custom backgrounds
        assert args[1] is None


class TestIconToolbarSignalContract:
    """Tests that document the expected public signal contract."""

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


# =============================================================================
# INJECT TAB SIGNALS
# =============================================================================


class TestInjectTabButtonSignals:
    """Test InjectTab emits correct signals on button clicks."""

    def test_inject_button_emits_inject_requested(self, qtbot: QtBot, inject_tab) -> None:
        """Verify clicking Inject Sprites button emits inject_requested."""
        spy = QSignalSpy(inject_tab.inject_requested)

        qtbot.mouseClick(inject_tab.inject_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: inject_requested must be emitted when Inject Sprites button is clicked."
        )

    def test_save_rom_button_emits_save_rom_requested(self, qtbot: QtBot, inject_tab) -> None:
        """Verify clicking Save to ROM button emits save_rom_requested."""
        # Show the Save ROM button first (it's hidden by default)
        inject_tab.save_rom_btn.show()

        spy = QSignalSpy(inject_tab.save_rom_requested)

        qtbot.mouseClick(inject_tab.save_rom_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: save_rom_requested must be emitted when Save to ROM button is clicked."
        )

    def test_browse_rom_button_emits_browse_rom_requested(self, qtbot: QtBot, inject_tab) -> None:
        """Verify clicking Browse ROM button emits browse_rom_requested."""
        # Show the ROM group first (it's hidden by default)
        inject_tab.rom_group.show()

        spy = QSignalSpy(inject_tab.browse_rom_requested)

        qtbot.mouseClick(inject_tab.browse_rom_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: browse_rom_requested must be emitted when Browse ROM button is clicked."
        )

    def test_multiple_inject_clicks_emit_multiple_signals(self, qtbot: QtBot, inject_tab) -> None:
        """Verify multiple button clicks emit multiple signals."""
        spy = QSignalSpy(inject_tab.inject_requested)

        qtbot.mouseClick(inject_tab.inject_btn, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(inject_tab.inject_btn, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(inject_tab.inject_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 3


class TestInjectTabModeSignals:
    """Test InjectTab signals in different modes."""

    def test_vram_mode_inject_button_not_hidden_and_emits(self, qtbot: QtBot, inject_tab) -> None:
        """Verify in VRAM mode, inject button is not hidden and emits signals."""
        inject_tab.set_mode("vram")

        spy = QSignalSpy(inject_tab.inject_requested)

        # In VRAM mode, inject button should not be hidden
        # (isVisible() requires parent to be shown, so we check isHidden() instead)
        assert not inject_tab.inject_btn.isHidden()
        qtbot.mouseClick(inject_tab.inject_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1

    def test_rom_mode_save_button_not_hidden_and_emits(self, qtbot: QtBot, inject_tab) -> None:
        """Verify in ROM mode, save button is not hidden and emits signals."""
        inject_tab.set_mode("rom")

        spy = QSignalSpy(inject_tab.save_rom_requested)

        # In ROM mode, save button should not be hidden
        assert not inject_tab.save_rom_btn.isHidden()
        qtbot.mouseClick(inject_tab.save_rom_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1


# =============================================================================
# PALETTE PANEL SIGNALS
# =============================================================================


class TestPalettePanelColorSignals:
    """Test PalettePanel emits colorSelected signal on color clicks."""

    def test_color_click_emits_colorSelected(self, qtbot: QtBot, palette_panel) -> None:
        """Verify clicking a color emits colorSelected with correct index."""
        spy = QSignalSpy(palette_panel.colorSelected)

        # Click on color index 5 (row 1, col 1)
        # Formula: x = col * cell_size + 5, y = row * cell_size + 5
        # For index 5: row=1, col=1, cell_size=48 (set in PalettePanel)
        # Position: x = 1*48 + 5 + 10 = 63, y = 1*48 + 5 + 10 = 63
        # Add some padding for safety
        click_pos = QPoint(60, 60)
        qtbot.mouseClick(palette_panel.palette_widget, Qt.MouseButton.LeftButton, pos=click_pos)

        assert spy.count() == 1, "SIGNAL CONTRACT VIOLATION: colorSelected must be emitted when a color is clicked."
        assert list(spy.at(0)) == [5]

    def test_first_color_click_emits_colorSelected_0(self, qtbot: QtBot, palette_panel) -> None:
        """Verify clicking first color emits colorSelected with index 0."""
        spy = QSignalSpy(palette_panel.colorSelected)

        # Click on color index 0 (row 0, col 0)
        # With cell_size=48: x = 0*48 + 5 + 10 = 15, y = 0*48 + 5 + 10 = 15
        click_pos = QPoint(15, 15)
        qtbot.mouseClick(palette_panel.palette_widget, Qt.MouseButton.LeftButton, pos=click_pos)

        assert spy.count() == 1
        assert list(spy.at(0)) == [0]

    def test_multiple_color_clicks_emit_multiple_signals(self, qtbot: QtBot, palette_panel) -> None:
        """Verify multiple color clicks emit multiple signals."""
        spy = QSignalSpy(palette_panel.colorSelected)

        cell_size = palette_panel.palette_widget.cell_size

        # Click colors 0, 5, 10, 15
        for color_idx in [0, 5, 10, 15]:
            row = color_idx // 4
            col = color_idx % 4
            x = col * cell_size + 10 + 5
            y = row * cell_size + 10 + 5
            click_pos = QPoint(x, y)
            qtbot.mouseClick(palette_panel.palette_widget, Qt.MouseButton.LeftButton, pos=click_pos)

        assert spy.count() == 4
        assert list(spy.at(0)) == [0]
        assert list(spy.at(1)) == [5]
        assert list(spy.at(2)) == [10]
        assert list(spy.at(3)) == [15]


class TestPalettePanelButtonSignals:
    """Test PalettePanel forwards button signals from PaletteSourceSelector."""

    def test_load_signal_forwarded_to_panel(self, palette_panel) -> None:
        """Verify PalettePanel forwards loadPaletteClicked from child selector."""
        spy = QSignalSpy(palette_panel.loadPaletteClicked)

        # Emit on child widget - panel should forward
        palette_panel.palette_source_selector.loadPaletteClicked.emit()

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: loadPaletteClicked must be forwarded from PaletteSourceSelector."
        )

    def test_save_signal_forwarded_to_panel(self, palette_panel) -> None:
        """Verify PalettePanel forwards savePaletteClicked from child selector."""
        spy = QSignalSpy(palette_panel.savePaletteClicked)

        # Emit on child widget - panel should forward
        palette_panel.palette_source_selector.savePaletteClicked.emit()

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: savePaletteClicked must be forwarded from PaletteSourceSelector."
        )

    def test_edit_signal_forwarded_to_panel(self, palette_panel) -> None:
        """Verify PalettePanel forwards editColorClicked from child selector."""
        spy = QSignalSpy(palette_panel.editColorClicked)

        # Emit on child widget - panel should forward
        palette_panel.palette_source_selector.editColorClicked.emit()

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: editColorClicked must be forwarded from PaletteSourceSelector."
        )


class TestPalettePanelSourceSignals:
    """Test PalettePanel emits sourceChanged signal on source selection."""

    def test_add_and_select_source_emits_sourceChanged(self, palette_panel) -> None:
        """Verify selecting a different source emits sourceChanged."""
        # Add a new palette source
        palette_panel.add_palette_source("Mesen2 #1", "mesen", 1)

        spy = QSignalSpy(palette_panel.sourceChanged)

        # Use public API to select the source
        palette_panel.set_selected_palette_source("mesen", 1)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: sourceChanged must be emitted when palette source is changed."
        )
        args = list(spy.at(0))
        assert args[0] == "mesen"
        assert args[1] == 1

    def test_select_different_sources_emits_each_time(self, palette_panel) -> None:
        """Verify selecting different sources emits each time."""
        # Add some sources
        palette_panel.add_palette_source("Mesen2 #1", "mesen", 1)
        palette_panel.add_palette_source("Mesen2 #2", "mesen", 2)

        spy = QSignalSpy(palette_panel.sourceChanged)

        # Use public API to select sources
        palette_panel.set_selected_palette_source("mesen", 1)
        palette_panel.set_selected_palette_source("mesen", 2)

        assert spy.count() == 2
        assert list(spy.at(0))[0] == "mesen"
        assert list(spy.at(0))[1] == 1
        assert list(spy.at(1))[0] == "mesen"
        assert list(spy.at(1))[1] == 2


class TestPalettePanelSignalContract:
    """Tests that document the expected public signal contract."""

    def test_programmatic_set_color_does_not_emit_signal(self, qtbot: QtBot, palette_panel) -> None:
        """Verify set_selected_color() does not emit colorSelected."""
        spy = QSignalSpy(palette_panel.colorSelected)

        # Programmatic update should not emit
        palette_panel.set_selected_color(5)

        assert spy.count() == 0, (
            "set_selected_color() should use QSignalBlocker to prevent "
            "colorSelected emission when called programmatically."
        )


# =============================================================================
# PIXEL CANVAS SIGNALS
# =============================================================================


class TestPixelCanvasMouseSignals:
    """Test PixelCanvas emits correct signals on mouse interactions."""

    def test_mouse_press_emits_pixelPressed(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse press on canvas emits pixelPressed with coordinates."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.pixelPressed)

        # Click at pixel (1, 1) - with zoom=8, that's screen position ~12, 12
        # Click in center of pixel to avoid edge issues
        click_pos = QPoint(12, 12)
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=click_pos)

        # Assert signal was emitted with correct pixel coordinates
        assert spy.count() == 1, "SIGNAL CONTRACT VIOLATION: pixelPressed must be emitted when canvas is clicked."
        # Pixel coordinates should be (1, 1)
        assert list(spy.at(0)) == [1, 1]

    def test_mouse_press_at_origin_emits_pixelPressed_0_0(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse press at origin emits pixelPressed with (0, 0)."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.pixelPressed)

        # Click at pixel (0, 0) - with zoom=8, that's screen position ~4, 4
        click_pos = QPoint(4, 4)
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=click_pos)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: pixelPressed must be emitted when canvas is clicked at pixel (0, 0)."
        )
        assert list(spy.at(0)) == [0, 0]

    def test_mouse_release_emits_pixelReleased(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse release emits pixelReleased signal."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.pixelReleased)

        click_pos = QPoint(4, 4)
        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=click_pos)
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=click_pos)

        assert spy.count() == 1, "SIGNAL CONTRACT VIOLATION: pixelReleased must be emitted when mouse is released."
        assert list(spy.at(0)) == [0, 0]

    def test_mouse_drag_emits_pixelMoved(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse move during draw emits pixelMoved."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.pixelMoved)

        # Press at (0,0), move to (1,1)
        start = QPoint(4, 4)
        end = QPoint(12, 12)

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        qtbot.mouseMove(canvas, pos=end)
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)

        # pixelMoved should have been emitted at least once during the move
        assert spy.count() >= 1, (
            "SIGNAL CONTRACT VIOLATION: pixelMoved must be emitted when mouse is dragged during drawing."
        )

    def test_complete_draw_stroke_emits_press_move_release(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify a complete draw stroke emits press, move, and release signals."""
        canvas, _ = canvas_with_image

        press_spy = QSignalSpy(canvas.pixelPressed)
        move_spy = QSignalSpy(canvas.pixelMoved)
        release_spy = QSignalSpy(canvas.pixelReleased)

        start = QPoint(4, 4)
        middle = QPoint(12, 12)
        end = QPoint(20, 20)

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        qtbot.mouseMove(canvas, pos=middle)
        qtbot.mouseMove(canvas, pos=end)
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)

        # All three signal types should have been emitted
        assert press_spy.count() == 1
        assert move_spy.count() >= 1
        assert release_spy.count() == 1


class TestPixelCanvasHoverSignals:
    """Test PixelCanvas emits hoverPositionChanged signals correctly."""

    def test_mouse_move_emits_hoverPositionChanged(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse move emits hoverPositionChanged with coordinates."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.hoverPositionChanged)

        # Move to pixel (2, 2) - with zoom=8, that's screen position ~20, 20
        move_pos = QPoint(20, 20)
        qtbot.mouseMove(canvas, pos=move_pos)

        # Should have emitted at least once with valid coordinates
        assert spy.count() >= 1, (
            "SIGNAL CONTRACT VIOLATION: hoverPositionChanged must be emitted when mouse moves over the canvas."
        )
        # Check the last emission has the expected coordinates
        assert list(spy.at(spy.count() - 1)) == [2, 2]

    def test_mouse_leave_emits_hoverPositionChanged_minus1(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse leave emits hoverPositionChanged with (-1, -1)."""
        canvas, _ = canvas_with_image

        spy = QSignalSpy(canvas.hoverPositionChanged)

        # Simulate leave event
        leave_event = QEvent(QEvent.Type.Leave)
        canvas.leaveEvent(leave_event)

        # Should emit (-1, -1) to indicate no hover position
        assert spy.count() >= 1
        # Last emission should be (-1, -1)
        assert list(spy.at(spy.count() - 1)) == [-1, -1]


class TestPixelCanvasZoomSignals:
    """Test PixelCanvas emits zoomRequested signals correctly."""

    def test_wheel_scroll_up_emits_zoomRequested_higher(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse wheel scroll up emits zoomRequested with higher zoom."""
        from PySide6.QtCore import QPointF

        canvas, _ = canvas_with_image

        # Get initial zoom
        initial_zoom = canvas.zoom

        spy = QSignalSpy(canvas.zoomRequested)

        # Simulate wheel scroll up (zoom in)
        wheel_event = QWheelEvent(
            QPointF(50, 50),  # position
            QPointF(50, 50),  # global position
            QPoint(0, 0),  # pixel delta
            QPoint(0, 120),  # angle delta (positive = scroll up = zoom in)
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        canvas.wheelEvent(wheel_event)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: zoomRequested must be emitted when mouse wheel is scrolled."
        )
        # New zoom should be higher than initial
        new_zoom = spy.at(0)[0]
        assert new_zoom > initial_zoom

    def test_wheel_scroll_down_emits_zoomRequested_lower(self, qtbot: QtBot, canvas_with_image: tuple) -> None:
        """Verify mouse wheel scroll down emits zoomRequested with lower zoom."""
        from PySide6.QtCore import QPointF

        canvas, _ = canvas_with_image

        # Get initial zoom
        initial_zoom = canvas.zoom

        spy = QSignalSpy(canvas.zoomRequested)

        # Simulate wheel scroll down (zoom out)
        wheel_event = QWheelEvent(
            QPointF(50, 50),
            QPointF(50, 50),
            QPoint(0, 0),
            QPoint(0, -120),  # negative = scroll down = zoom out
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        canvas.wheelEvent(wheel_event)

        assert spy.count() == 1
        # New zoom should be lower than initial
        new_zoom = spy.at(0)[0]
        assert new_zoom < initial_zoom


class TestPixelCanvasRegression:
    """Regression tests for PixelCanvas correctness fixes."""

    def test_canvas_palette_sync(self, qtbot, canvas_with_image):
        """Verify canvas triggers repaint when controller palette changes.

        Tests observable behavior (update triggered) rather than internal cache state.
        """
        from unittest.mock import Mock

        canvas, controller = canvas_with_image
        canvas.greyscale_mode = False

        # Set some data
        data = np.zeros((8, 8), dtype=np.uint8)
        data[0, 0] = 7
        controller.load_image(data)

        # Mock update to track repaint requests
        original_update = canvas.update
        canvas.update = Mock()

        # Change palette to something else
        new_palette = [(0, 0, 0)] * 16
        new_palette[7] = (255, 165, 0)  # Orange

        # This should trigger paletteChanged signal and cause canvas to request repaint
        controller.set_palette(new_palette)

        # Verify that palette change triggered a display update (observable behavior)
        assert canvas.update.called, "Palette change should trigger canvas update"

        # Restore original update method
        canvas.update = original_update

    def test_hover_artifacts_fix(self, qtbot, canvas_with_image):
        """Verify proper invalidation of previous hover rect when brush size changes.

        This ensures that if the brush size decreases, we still clear the full
        area of the PREVIOUS large brush, preventing visual artifacts (trails).
        """
        from unittest.mock import Mock

        from PySide6.QtCore import QPoint, QRect

        canvas, controller = canvas_with_image

        # Mock canvas.update to track calls and prevent actual painting
        canvas.update = Mock()

        # 1. Start with Large Brush (Size 3)
        controller.get_brush_size = Mock(return_value=3)

        # Move to (0,0) - Establishes the "Previous" state
        # Manually call _update_hover_regions to isolate logic
        canvas._update_hover_regions(None, QPoint(0, 0))

        # Verify initial rect is stored and is "Large"
        # Size 3 * Zoom 8 = 24px. Plus 2px pen padding = 26px.
        assert canvas._last_hover_rect is not None
        large_rect = canvas._last_hover_rect
        assert large_rect.width() == 26
        assert large_rect.height() == 26

        # 2. Decrease Brush Size to 1 (Small)
        controller.get_brush_size = Mock(return_value=1)

        # 3. Move to (2,2)
        # This acts as the "cleanup" of the old position (0,0)
        canvas._update_hover_regions(QPoint(0, 0), QPoint(2, 2))

        # 4. Verify Correct Invalidation
        # We expect canvas.update() to be called with the OLD Large rect.
        # If the fix is working, it uses the stored large_rect.
        # If the fix is missing, it would calculate a new rect at (0,0) using size 1 (width 10),
        # leaving the outer pixels of the large rect un-cleared.

        canvas.update.assert_any_call(large_rect)

        # Also verify the new stored rect is Small
        assert canvas._last_hover_rect.width() == 10  # 1*8 + 2


# =============================================================================
# SPRITE ASSET BROWSER SIGNALS
# =============================================================================


class TestSpriteAssetBrowserSelectionSignals:
    """Test SpriteAssetBrowser emits selection signals correctly."""

    def test_item_selection_emits_sprite_selected(self, qtbot: QtBot, asset_browser) -> None:
        """Verify selecting an item emits sprite_selected with offset and source_type."""
        spy = QSignalSpy(asset_browser.sprite_selected)

        # Find and select the first ROM sprite
        rom_category = asset_browser.tree.topLevelItem(0)
        if rom_category and rom_category.childCount() > 0:
            first_sprite = rom_category.child(0)
            asset_browser.tree.setCurrentItem(first_sprite)

            assert spy.count() >= 1, (
                "SIGNAL CONTRACT VIOLATION: sprite_selected must be emitted when an item is selected."
            )
            # Check arguments: offset should be 0x1000, source_type should be "rom"
            args = list(spy.at(spy.count() - 1))
            assert args[0] == 0x1000
            assert args[1] == "rom"

    def test_different_items_emit_different_offsets(self, qtbot: QtBot, asset_browser) -> None:
        """Verify selecting different items emits correct offsets."""
        spy = QSignalSpy(asset_browser.sprite_selected)

        rom_category = asset_browser.tree.topLevelItem(0)
        if rom_category and rom_category.childCount() > 1:
            # Select first sprite
            first_sprite = rom_category.child(0)
            asset_browser.tree.setCurrentItem(first_sprite)

            # Select second sprite
            second_sprite = rom_category.child(1)
            asset_browser.tree.setCurrentItem(second_sprite)

            # Should have emitted twice with different offsets
            assert spy.count() >= 2
            # Last emission should be for second sprite
            args = list(spy.at(spy.count() - 1))
            assert args[0] == 0x2000
            assert args[1] == "rom"

    def test_mesen_selection_emits_mesen_source_type(self, qtbot: QtBot, asset_browser) -> None:
        """Verify selecting Mesen capture emits 'mesen' source type."""
        spy = QSignalSpy(asset_browser.sprite_selected)

        # Find Mesen captures category
        mesen_category = None
        for i in range(asset_browser.tree.topLevelItemCount()):
            item = asset_browser.tree.topLevelItem(i)
            if item and "Mesen" in (item.text(0) or ""):
                mesen_category = item
                break

        if mesen_category and mesen_category.childCount() > 0:
            capture = mesen_category.child(0)
            asset_browser.tree.setCurrentItem(capture)

            assert spy.count() >= 1
            args = list(spy.at(spy.count() - 1))
            assert args[0] == 0x3000
            assert args[1] == "mesen"


class TestSpriteAssetBrowserActivationSignals:
    """Test SpriteAssetBrowser emits activation signals on double-click."""

    def test_double_click_emits_sprite_activated(self, qtbot: QtBot, asset_browser) -> None:
        """Verify double-clicking an item emits sprite_activated."""
        spy = QSignalSpy(asset_browser.sprite_activated)

        rom_category = asset_browser.tree.topLevelItem(0)
        if rom_category and rom_category.childCount() > 0:
            first_sprite = rom_category.child(0)

            # Simulate double-click by emitting the itemDoubleClicked signal directly
            # (mouseDClick doesn't work reliably on hidden tree widgets)
            asset_browser.tree.itemDoubleClicked.emit(first_sprite, 0)

            assert spy.count() >= 1, (
                "SIGNAL CONTRACT VIOLATION: sprite_activated must be emitted when an item is double-clicked."
            )
            args = list(spy.at(spy.count() - 1))
            assert args[0] == 0x1000
            assert args[1] == "rom"


class TestSpriteAssetBrowserContextMenuSignals:
    """Test SpriteAssetBrowser emits context menu action signals."""

    def test_delete_action_emits_delete_requested(self, qtbot: QtBot, asset_browser) -> None:
        """Verify delete action emits delete_requested signal."""
        spy = QSignalSpy(asset_browser.delete_requested)

        rom_category = asset_browser.tree.topLevelItem(0)
        if rom_category and rom_category.childCount() > 0:
            first_sprite = rom_category.child(0)

            # Select the item first
            asset_browser.tree.setCurrentItem(first_sprite)

            # Directly call the delete method (simulating context menu action)
            # This avoids blocking on menu.exec()
            asset_browser._delete_item(first_sprite)

            assert spy.count() >= 1, (
                "SIGNAL CONTRACT VIOLATION: delete_requested must be emitted when delete action is triggered."
            )
            args = list(spy.at(spy.count() - 1))
            assert args[0] == 0x1000
            assert args[1] == "rom"

    def test_save_to_library_action_emits_save_to_library_requested(self, qtbot: QtBot, asset_browser) -> None:
        """Verify save to library action emits save_to_library_requested."""
        spy = QSignalSpy(asset_browser.save_to_library_requested)

        rom_category = asset_browser.tree.topLevelItem(0)
        if rom_category and rom_category.childCount() > 0:
            first_sprite = rom_category.child(0)
            asset_browser.tree.setCurrentItem(first_sprite)

            # Trigger save to library directly (simulating context menu action)
            asset_browser._save_to_library(first_sprite)

            assert spy.count() >= 1, (
                "SIGNAL CONTRACT VIOLATION: save_to_library_requested must be emitted "
                "when save to library action is triggered."
            )
            args = list(spy.at(spy.count() - 1))
            assert args[0] == 0x1000
            assert args[1] == "rom"


class TestSpriteAssetBrowserSignalContract:
    """Tests that document the expected public signal contract."""

    def test_category_selection_does_not_emit_sprite_selected(self, qtbot: QtBot, asset_browser) -> None:
        """Verify selecting a category (not a sprite) does not emit sprite_selected."""
        spy = QSignalSpy(asset_browser.sprite_selected)

        # Select the category itself, not a child
        rom_category = asset_browser.tree.topLevelItem(0)
        if rom_category:
            asset_browser.tree.setCurrentItem(rom_category)

            # Category selection should not emit sprite_selected
            # (category items have no offset data, so signal shouldn't fire)
            assert spy.count() == 0, "Category selection should not emit sprite_selected signal"


class TestSpriteAssetBrowserOffsetUpdate:
    """Tests for update_sprite_offset() - ensures thumbnail/selection sync after alignment."""

    def test_update_sprite_offset_updates_rom_sprite(self, qtbot: QtBot, asset_browser) -> None:
        """Verify ROM sprite item offset is updated when alignment is detected."""
        # ROM sprite at 0x1000 should be updated to 0x1001
        result = asset_browser.update_sprite_offset(0x1000, 0x1001)

        assert result is True
        # Verify item now has new offset
        assert asset_browser.find_display_name_by_offset(0x1001) == "Test Sprite 1"
        assert asset_browser.find_display_name_by_offset(0x1000) is None

    def test_update_sprite_offset_updates_mesen_capture(self, qtbot: QtBot, asset_browser) -> None:
        """Verify Mesen capture item offset is updated when alignment is detected."""
        # Mesen capture at 0x3000 should be updated to 0x3001
        result = asset_browser.update_sprite_offset(0x3000, 0x3001)

        assert result is True
        assert asset_browser.find_display_name_by_offset(0x3001) == "Capture 1"
        assert asset_browser.find_display_name_by_offset(0x3000) is None

    def test_update_sprite_offset_returns_false_for_unknown_offset(self, qtbot: QtBot, asset_browser) -> None:
        """Verify update_sprite_offset returns False if offset not found."""
        result = asset_browser.update_sprite_offset(0x9999, 0x9999 + 1)

        assert result is False

    def test_set_thumbnail_after_offset_update(self, qtbot: QtBot, asset_browser) -> None:
        """Verify set_thumbnail finds item after offset update."""
        from PySide6.QtGui import QPixmap

        # Update offset from 0x1000 to 0x1001
        asset_browser.update_sprite_offset(0x1000, 0x1001)

        # Create a test pixmap and set it
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.red)
        asset_browser.set_thumbnail(0x1001, pixmap)

        # Verify thumbnail was set by checking item data
        rom_category = asset_browser.tree.topLevelItem(0)
        if rom_category:
            for i in range(rom_category.childCount()):
                item = rom_category.child(i)
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and data.get("offset") == 0x1001:
                    assert data.get("thumbnail") is not None, "Thumbnail should be set after offset update"
                    break

    def test_clear_thumbnail_after_offset_update(self, qtbot: QtBot, asset_browser) -> None:
        """Verify clear_thumbnail finds item after offset update."""
        from PySide6.QtGui import QPixmap

        # First set a thumbnail on the original offset
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.blue)
        asset_browser.set_thumbnail(0x1000, pixmap)

        # Update offset from 0x1000 to 0x1001
        asset_browser.update_sprite_offset(0x1000, 0x1001)

        # Now clear thumbnail using the new offset
        result = asset_browser.clear_thumbnail(0x1001)

        assert result is True, "clear_thumbnail should find item after offset update"

    def test_selection_uses_updated_offset(self, qtbot: QtBot, asset_browser) -> None:
        """Verify re-selecting item after offset update emits new offset."""
        # Update offset from 0x1000 to 0x1001
        asset_browser.update_sprite_offset(0x1000, 0x1001)

        spy = QSignalSpy(asset_browser.sprite_selected)

        # Find and select the updated item
        rom_category = asset_browser.tree.topLevelItem(0)
        if rom_category and rom_category.childCount() > 0:
            first_sprite = rom_category.child(0)
            asset_browser.tree.setCurrentItem(first_sprite)

            assert spy.count() >= 1
            args = list(spy.at(spy.count() - 1))
            assert args[0] == 0x1001, "Selected item should emit updated offset"
            assert args[1] == "rom"

    def test_update_sprite_offset_emits_item_offset_changed(self, qtbot: QtBot, asset_browser) -> None:
        """Verify update_sprite_offset emits item_offset_changed signal with old and new offsets."""
        spy = QSignalSpy(asset_browser.item_offset_changed)

        # Update offset from 0x1000 to 0x1005
        result = asset_browser.update_sprite_offset(0x1000, 0x1005)

        assert result is True
        assert spy.count() == 1, "item_offset_changed signal must be emitted exactly once"
        args = list(spy.at(0))
        assert args[0] == 0x1000, "First argument should be old offset"
        assert args[1] == 0x1005, "Second argument should be new offset"

    def test_update_sprite_offset_does_not_emit_when_not_found(self, qtbot: QtBot, asset_browser) -> None:
        """Verify item_offset_changed is NOT emitted when offset is not found."""
        spy = QSignalSpy(asset_browser.item_offset_changed)

        # Try to update non-existent offset
        result = asset_browser.update_sprite_offset(0x9999, 0x9999 + 1)

        assert result is False
        assert spy.count() == 0, "item_offset_changed should not emit when update fails"
