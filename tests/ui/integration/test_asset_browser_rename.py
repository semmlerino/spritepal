"""
Tests for SpriteAssetBrowser rename functionality.

Reproduces and verifies fix for crash when renaming sprites.
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
    """Create a SpriteAssetBrowser with test items."""
    from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

    browser = SpriteAssetBrowser()
    qtbot.addWidget(browser)

    # Add test items
    browser.add_rom_sprite("Test Sprite 1", 0x1000)
    browser.add_rom_sprite("Test Sprite 2", 0x2000)
    browser.add_mesen_capture("Capture 1", 0x3000)

    return browser


class TestSpriteAssetBrowserRename:
    """Test SpriteAssetBrowser rename functionality."""

    def test_rename_item_emits_rename_requested(self, qtbot: QtBot, asset_browser) -> None:
        """Verify renaming an item emits rename_requested with offset and new name."""
        spy = QSignalSpy(asset_browser.rename_requested)

        # Find the first ROM sprite
        rom_category = asset_browser.tree.topLevelItem(0)
        assert rom_category is not None
        assert rom_category.childCount() > 0

        first_sprite = rom_category.child(0)
        assert first_sprite is not None

        # Start inline edit by calling _rename_item
        asset_browser._rename_item(first_sprite)

        # Simulate edit completion by changing the text and emitting itemChanged
        # This mimics what happens when user finishes inline editing
        first_sprite.setText(0, "Renamed Sprite")
        asset_browser.tree.itemChanged.emit(first_sprite, 0)

        # Signal should be emitted with offset and new name
        assert spy.count() >= 1, "SIGNAL CONTRACT VIOLATION: rename_requested must be emitted when rename completes."
        args = list(spy.at(spy.count() - 1))
        assert args[0] == 0x1000, "First argument should be the offset"
        assert args[1] == "Renamed Sprite", "Second argument should be the new name"

    def test_rename_item_updates_item_data(self, qtbot: QtBot, asset_browser) -> None:
        """Verify renaming updates the item's UserRole data."""
        rom_category = asset_browser.tree.topLevelItem(0)
        first_sprite = rom_category.child(0)

        # Start inline edit
        asset_browser._rename_item(first_sprite)

        # Simulate edit completion
        first_sprite.setText(0, "New Name")
        asset_browser.tree.itemChanged.emit(first_sprite, 0)

        # Verify item data was updated
        data = first_sprite.data(0, Qt.ItemDataRole.UserRole)
        assert isinstance(data, dict)
        assert data.get("name") == "New Name", "Item data name should be updated"

    def test_rename_item_disables_editing_after_completion(self, qtbot: QtBot, asset_browser) -> None:
        """Verify item editing flag is disabled after rename completes."""
        rom_category = asset_browser.tree.topLevelItem(0)
        first_sprite = rom_category.child(0)

        # Start inline edit
        asset_browser._rename_item(first_sprite)

        # Verify editing was enabled
        assert first_sprite.flags() & Qt.ItemFlag.ItemIsEditable

        # Simulate edit completion
        first_sprite.setText(0, "New Name")
        asset_browser.tree.itemChanged.emit(first_sprite, 0)

        # Verify editing is now disabled
        assert not (first_sprite.flags() & Qt.ItemFlag.ItemIsEditable), (
            "ItemIsEditable flag should be removed after rename completes"
        )

    def test_rename_mesen_capture_emits_correct_offset(self, qtbot: QtBot, asset_browser) -> None:
        """Verify renaming a Mesen capture emits the correct offset."""
        spy = QSignalSpy(asset_browser.rename_requested)

        # Find Mesen captures category
        mesen_category = None
        for i in range(asset_browser.tree.topLevelItemCount()):
            item = asset_browser.tree.topLevelItem(i)
            if item and "Mesen" in (item.text(0) or ""):
                mesen_category = item
                break

        assert mesen_category is not None
        assert mesen_category.childCount() > 0

        capture = mesen_category.child(0)
        assert capture is not None

        # Start inline edit and complete
        asset_browser._rename_item(capture)
        capture.setText(0, "Renamed Capture")
        asset_browser.tree.itemChanged.emit(capture, 0)

        assert spy.count() >= 1
        args = list(spy.at(spy.count() - 1))
        assert args[0] == 0x3000, "Mesen capture offset should be 0x3000"
        assert args[1] == "Renamed Capture"

    def test_multiple_renames_work_correctly(self, qtbot: QtBot, asset_browser) -> None:
        """Verify renaming multiple items in sequence works correctly."""
        spy = QSignalSpy(asset_browser.rename_requested)

        rom_category = asset_browser.tree.topLevelItem(0)
        first_sprite = rom_category.child(0)
        second_sprite = rom_category.child(1)

        # Rename first sprite
        asset_browser._rename_item(first_sprite)
        first_sprite.setText(0, "First Renamed")
        asset_browser.tree.itemChanged.emit(first_sprite, 0)

        # Rename second sprite
        asset_browser._rename_item(second_sprite)
        second_sprite.setText(0, "Second Renamed")
        asset_browser.tree.itemChanged.emit(second_sprite, 0)

        assert spy.count() >= 2, "Should have emitted rename_requested twice"

        # Verify both renames
        first_args = list(spy.at(0))
        second_args = list(spy.at(1))

        assert first_args[0] == 0x1000
        assert first_args[1] == "First Renamed"
        assert second_args[0] == 0x2000
        assert second_args[1] == "Second Renamed"

    def test_rename_with_controller_integration(self, qtbot: QtBot, asset_browser) -> None:
        """Test rename through controller integration."""
        from ui.sprite_editor.controllers.asset_browser_controller import AssetBrowserController

        controller = AssetBrowserController()
        controller.set_browser(asset_browser)

        # Add a sprite through the controller so it tracks metadata
        controller.add_rom_sprite("Controller Sprite", 0x5000)

        # Find the item we just added
        rom_category = asset_browser.tree.topLevelItem(0)
        item = None
        for i in range(rom_category.childCount()):
            child = rom_category.child(i)
            data = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("offset") == 0x5000:
                item = child
                break

        assert item is not None, "Should find the item added via controller"

        # Perform rename
        asset_browser._rename_item(item)
        item.setText(0, "Controller Renamed")
        asset_browser.tree.itemChanged.emit(item, 0)

        # Verify controller's internal state was updated
        name = controller.get_asset_name(0x5000, "rom")
        assert name == "Controller Renamed", "Controller should have updated asset name after rename"
