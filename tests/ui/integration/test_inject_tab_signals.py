"""
Tests for InjectTab public signal behavior.

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
def inject_tab(qtbot: QtBot):
    """Create an InjectTab for testing."""
    from ui.sprite_editor.views.tabs.inject_tab import InjectTab

    tab = InjectTab()
    qtbot.addWidget(tab)
    return tab


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


class TestInjectTabSignalContract:
    """Tests that document the expected public signal contract."""

    @pytest.mark.parametrize(
        "signal_name",
        [
            "inject_requested",
            "save_rom_requested",
            "browse_png_requested",
            "browse_vram_requested",
            "browse_rom_requested",
        ],
    )
    def test_signal_exists(self, signal_name: str, inject_tab) -> None:
        """Verify all expected public signals exist on InjectTab."""
        assert hasattr(inject_tab, signal_name), f"SIGNAL CONTRACT: InjectTab must expose '{signal_name}' signal"
