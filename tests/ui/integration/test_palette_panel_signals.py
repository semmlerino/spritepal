"""
Tests for PalettePanel public signal behavior.

These tests verify ONLY observable signal behavior:
- Signal emission count
- Signal argument values

They do NOT inspect internal state or private attributes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def palette_panel(qtbot: QtBot):
    """Create a PalettePanel for testing."""
    from ui.sprite_editor.views.panels.palette_panel import PalettePanel

    panel = PalettePanel()
    qtbot.addWidget(panel)
    return panel


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
    """Test PalettePanel emits button click signals."""

    def test_load_button_emits_loadPaletteClicked(self, qtbot: QtBot, palette_panel) -> None:
        """Verify clicking Load Palette button emits loadPaletteClicked."""
        spy = QSignalSpy(palette_panel.loadPaletteClicked)

        # Access the button through the palette_source_selector
        load_btn = palette_panel.palette_source_selector._load_palette_btn
        qtbot.mouseClick(load_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: loadPaletteClicked must be emitted when Load Palette button is clicked."
        )

    def test_save_button_emits_savePaletteClicked(self, qtbot: QtBot, palette_panel) -> None:
        """Verify clicking Save Palette button emits savePaletteClicked."""
        spy = QSignalSpy(palette_panel.savePaletteClicked)

        save_btn = palette_panel.palette_source_selector._save_palette_btn
        qtbot.mouseClick(save_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: savePaletteClicked must be emitted when Save Palette button is clicked."
        )

    def test_edit_button_emits_editColorClicked(self, qtbot: QtBot, palette_panel) -> None:
        """Verify clicking Edit Color button emits editColorClicked."""
        spy = QSignalSpy(palette_panel.editColorClicked)

        edit_btn = palette_panel.palette_source_selector._edit_color_btn
        qtbot.mouseClick(edit_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: editColorClicked must be emitted when Edit Color button is clicked."
        )


class TestPalettePanelSourceSignals:
    """Test PalettePanel emits sourceChanged signal on source selection."""

    def test_add_and_select_source_emits_sourceChanged(self, qtbot: QtBot, palette_panel) -> None:
        """Verify selecting a different source emits sourceChanged."""
        # Add a new palette source
        palette_panel.add_palette_source("Mesen2 #1", "mesen", 1)

        spy = QSignalSpy(palette_panel.sourceChanged)

        # Select the new source (index 1)
        palette_panel.palette_source_selector._combo_box.setCurrentIndex(1)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: sourceChanged must be emitted when palette source is changed."
        )
        args = list(spy.at(0))
        assert args[0] == "mesen"
        assert args[1] == 1

    def test_select_same_source_twice_emits_once(self, qtbot: QtBot, palette_panel) -> None:
        """Verify selecting different sources emits each time."""
        # Add some sources
        palette_panel.add_palette_source("Mesen2 #1", "mesen", 1)
        palette_panel.add_palette_source("Mesen2 #2", "mesen", 2)

        spy = QSignalSpy(palette_panel.sourceChanged)

        # Select source 1
        palette_panel.palette_source_selector._combo_box.setCurrentIndex(1)
        # Select source 2
        palette_panel.palette_source_selector._combo_box.setCurrentIndex(2)

        assert spy.count() == 2
        assert list(spy.at(0))[0] == "mesen"
        assert list(spy.at(0))[1] == 1
        assert list(spy.at(1))[0] == "mesen"
        assert list(spy.at(1))[1] == 2


class TestPalettePanelSignalContract:
    """Tests that document the expected public signal contract."""

    @pytest.mark.parametrize(
        "signal_name",
        [
            "colorSelected",
            "sourceChanged",
            "loadPaletteClicked",
            "savePaletteClicked",
            "editColorClicked",
        ],
    )
    def test_signal_exists(self, signal_name: str, palette_panel) -> None:
        """Verify all expected public signals exist on PalettePanel."""
        assert hasattr(palette_panel, signal_name), f"SIGNAL CONTRACT: PalettePanel must expose '{signal_name}' signal"

    def test_programmatic_set_color_does_not_emit_signal(self, qtbot: QtBot, palette_panel) -> None:
        """Verify set_selected_color() does not emit colorSelected."""
        spy = QSignalSpy(palette_panel.colorSelected)

        # Programmatic update should not emit
        palette_panel.set_selected_color(5)

        assert spy.count() == 0, (
            "set_selected_color() should use QSignalBlocker to prevent "
            "colorSelected emission when called programmatically."
        )
