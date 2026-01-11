"""
Tests for ExtractTab public signal behavior.

These tests verify ONLY observable signal behavior:
- Signal emission count
- Signal argument values

They do NOT inspect internal state or private attributes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def extract_tab(qtbot: QtBot):
    """Create an ExtractTab for testing."""
    from ui.sprite_editor.views.tabs.extract_tab import ExtractTab

    tab = ExtractTab()
    qtbot.addWidget(tab)
    return tab


class TestExtractTabButtonSignals:
    """Test ExtractTab emits correct signals on button clicks."""

    def test_extract_button_emits_extract_requested(self, qtbot: QtBot, extract_tab) -> None:
        """Verify clicking Extract Sprites button emits extract_requested."""
        spy = QSignalSpy(extract_tab.extract_requested)

        qtbot.mouseClick(extract_tab.extract_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: extract_requested must be emitted when Extract Sprites button is clicked."
        )

    def test_browse_rom_button_emits_browse_rom_requested(self, qtbot: QtBot, extract_tab) -> None:
        """Verify clicking Browse ROM button emits browse_rom_requested."""
        # Show the ROM group first (it's hidden by default)
        extract_tab.rom_group.show()

        spy = QSignalSpy(extract_tab.browse_rom_requested)

        qtbot.mouseClick(extract_tab.browse_rom_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: browse_rom_requested must be emitted when Browse ROM button is clicked."
        )

    def test_load_rom_button_emits_load_rom_requested(self, qtbot: QtBot, extract_tab) -> None:
        """Verify clicking Load from ROM button emits load_rom_requested."""
        # Show the Load ROM button first (it's hidden by default)
        extract_tab.load_rom_btn.show()

        spy = QSignalSpy(extract_tab.load_rom_requested)

        qtbot.mouseClick(extract_tab.load_rom_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 1, (
            "SIGNAL CONTRACT VIOLATION: load_rom_requested must be emitted when Load from ROM button is clicked."
        )

    def test_multiple_extract_clicks_emit_multiple_signals(self, qtbot: QtBot, extract_tab) -> None:
        """Verify multiple button clicks emit multiple signals."""
        spy = QSignalSpy(extract_tab.extract_requested)

        qtbot.mouseClick(extract_tab.extract_btn, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(extract_tab.extract_btn, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(extract_tab.extract_btn, Qt.MouseButton.LeftButton)

        assert spy.count() == 3


class TestExtractTabSignalContract:
    """Tests that document the expected public signal contract."""

    @pytest.mark.parametrize(
        "signal_name",
        [
            "browse_vram_requested",
            "browse_cgram_requested",
            "browse_rom_requested",
            "extract_requested",
            "load_rom_requested",
            "extractionRequested",
        ],
    )
    def test_signal_exists(self, signal_name: str, extract_tab) -> None:
        """Verify all expected public signals exist on ExtractTab."""
        assert hasattr(extract_tab, signal_name), f"SIGNAL CONTRACT: ExtractTab must expose '{signal_name}' signal"
