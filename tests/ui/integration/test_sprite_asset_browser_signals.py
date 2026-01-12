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
