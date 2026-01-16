"""
Tests for manual palette selection restoring previous selection.

Bug context: When "Manual Palette Offset..." is selected, the dropdown
reverts to "Default" instead of restoring the previous selection.
This causes UI desync when the user cancels the manual palette dialog.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QComboBox

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def selector(qtbot: QtBot):
    """Create a PaletteSourceSelector widget."""
    from ui.sprite_editor.views.widgets.palette_source_selector import (
        PaletteSourceSelector,
    )

    widget = PaletteSourceSelector()
    qtbot.addWidget(widget)
    return widget


class TestManualPaletteSelectionRestore:
    """Tests for restoring selection after manual palette action."""

    def test_manual_palette_emits_signal(self, selector, qtbot: QtBot) -> None:
        """Selecting 'Manual Palette Offset...' should emit manualPaletteRequested."""
        spy = QSignalSpy(selector.manualPaletteRequested)

        # Find the manual palette entry (last item)
        combo = selector.findChild(QComboBox)
        manual_index = combo.count() - 1

        combo.setCurrentIndex(manual_index)

        assert spy.count() == 1

    def test_manual_palette_restores_previous_selection_not_default(self, selector, qtbot: QtBot) -> None:
        """
        BUG REPRODUCTION: After selecting 'Manual Palette Offset...',
        dropdown should restore to PREVIOUS selection, not 'Default'.

        This test will FAIL before the fix is applied.
        """
        # Add a ROM palette source
        selector.add_palette_source("ROM Palette 8", "rom", 8)

        # Select the ROM palette
        selector.set_selected_source("rom", 8)
        assert selector.get_selected_source() == ("rom", 8)

        # Find and select manual palette entry
        combo = selector.findChild(QComboBox)
        manual_index = combo.count() - 1

        # This triggers manual palette selection which should restore previous
        combo.setCurrentIndex(manual_index)

        # Should restore to previous selection (rom, 8), NOT default
        current_source = selector.get_selected_source()
        assert current_source == ("rom", 8), (
            f"Expected ('rom', 8), got {current_source}. "
            "Manual palette selection should restore previous selection, not Default."
        )

    def test_manual_palette_does_not_emit_source_changed(self, selector, qtbot: QtBot) -> None:
        """Manual palette selection should NOT emit sourceChanged signal."""
        # Add and select a ROM palette
        selector.add_palette_source("ROM Palette 8", "rom", 8)
        selector.set_selected_source("rom", 8)

        # Spy on sourceChanged
        spy = QSignalSpy(selector.sourceChanged)

        # Select manual palette
        combo = selector.findChild(QComboBox)
        manual_index = combo.count() - 1
        combo.setCurrentIndex(manual_index)

        # Should not emit sourceChanged (only manualPaletteRequested)
        assert spy.count() == 0, (
            f"sourceChanged emitted {spy.count()} times, expected 0. "
            "Manual palette selection should not change the active source."
        )

    def test_manual_palette_restores_default_when_no_previous_selection(self, selector, qtbot: QtBot) -> None:
        """When no previous selection exists, should restore to Default (index 0)."""
        # Don't add any palette sources, start from default state

        # Find and select manual palette entry
        combo = selector.findChild(QComboBox)
        manual_index = combo.count() - 1

        combo.setCurrentIndex(manual_index)

        # Should restore to Default (the only previous state)
        current_source = selector.get_selected_source()
        assert current_source == ("default", 0), (
            f"Expected ('default', 0), got {current_source}. With no previous selection, should restore to Default."
        )
