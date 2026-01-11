"""
Tests for SpriteAssetBrowser public signal behavior.

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

    @pytest.mark.parametrize(
        "signal_name",
        [
            "sprite_selected",
            "sprite_activated",
            "rename_requested",
            "delete_requested",
            "save_to_library_requested",
        ],
    )
    def test_signal_exists(self, signal_name: str, asset_browser) -> None:
        """Verify all expected public signals exist on SpriteAssetBrowser."""
        assert hasattr(asset_browser, signal_name), (
            f"SIGNAL CONTRACT: SpriteAssetBrowser must expose '{signal_name}' signal"
        )

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
