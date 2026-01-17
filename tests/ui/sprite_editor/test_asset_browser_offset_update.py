"""Tests for asset browser offset display synchronization."""

import pytest
from PySide6.QtWidgets import QApplication, QTreeWidget


class TestAssetBrowserOffsetUpdate:
    """Tests for asset browser offset display updates."""

    def test_update_sprite_offset_updates_display_text_with_frame(self, qtbot):
        """
        Bug: Asset browser display text doesn't update when offset is adjusted.

        Scenario: A Mesen capture with offset 0x293AEB and frame F1938 is added.
        The preview worker discovers the actual sprite is at 0x293AED (+2 bytes).
        The controller calls update_sprite_offset(0x293AEB, 0x293AED).

        Expected:
        - Display text should update from "0x293AEB (F1938)" to "0x293AED (F1938)"
        - Internal data offset should update from 0x293AEB to 0x293AED (already works)

        Current behavior (bug):
        - Display text remains "0x293AEB (F1938)" (WRONG)
        - Internal data updates correctly (GOOD)
        """
        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        # Create browser
        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add a Mesen capture with offset and frame info
        original_offset = 0x293AEB
        new_offset = 0x293AED
        original_name = "0x293AEB (F1938)"

        browser.add_mesen_capture(original_name, original_offset)

        # Find the Mesen category (it's one of the top-level items)
        mesen_category = None
        for i in range(browser.tree.topLevelItemCount()):
            item = browser.tree.topLevelItem(i)
            if item.text(0) == "Mesen2 Captures":
                mesen_category = item
                break

        assert mesen_category is not None, "Mesen category not found"

        # Get the first (and only) sprite in the Mesen category
        mesen_item = mesen_category.child(0)
        assert mesen_item is not None, "No sprite added to Mesen category"
        assert mesen_item.text(0) == original_name

        # Verify internal data has correct offset
        data = mesen_item.data(0, 256)  # Qt.ItemDataRole.UserRole = 256
        assert data["offset"] == original_offset

        # Simulate preview discovering sprite at different offset
        success = browser.update_sprite_offset(original_offset, new_offset)

        # Should find and update the item
        assert success

        # Internal data should be updated (this already works)
        data_after = mesen_item.data(0, 256)
        assert data_after["offset"] == new_offset

        # Display text should also be updated (THIS IS THE BUG FIX)
        expected_name = "0x293AED (F1938)"
        assert mesen_item.text(0) == expected_name, (
            f"Display text not updated: got '{mesen_item.text(0)}', expected '{expected_name}'"
        )

    def test_update_sprite_offset_preserves_frame_info(self, qtbot):
        """
        Verify that offset update preserves frame information from original name.

        Multiple formats should be supported:
        - With frame: "0x293AEB (F1938)" → "0x293AED (F1938)"
        - Without frame: "0x293AEB" → "0x293AED"
        """
        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Test with frame info
        browser.add_mesen_capture("0x100000 (F500)", 0x100000)

        # Find Mesen category and get sprite item
        mesen_category = None
        for i in range(browser.tree.topLevelItemCount()):
            item = browser.tree.topLevelItem(i)
            if item.text(0) == "Mesen2 Captures":
                mesen_category = item
                break

        assert mesen_category is not None
        item = mesen_category.child(0)
        assert item is not None

        browser.update_sprite_offset(0x100000, 0x100010)

        assert item.text(0) == "0x100010 (F500)"

    def test_update_sprite_offset_handles_missing_frame_info(self, qtbot):
        """
        Verify offset update works for sprites without frame info.

        Handles names like "0x293AEB" (no frame number in parentheses).
        """
        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add sprite without frame info
        browser.add_mesen_capture("0x200000", 0x200000)

        # Find Mesen category and get sprite item
        mesen_category = None
        for i in range(browser.tree.topLevelItemCount()):
            item = browser.tree.topLevelItem(i)
            if item.text(0) == "Mesen2 Captures":
                mesen_category = item
                break

        assert mesen_category is not None
        item = mesen_category.child(0)
        assert item is not None

        browser.update_sprite_offset(0x200000, 0x200004)

        # Should update offset but no frame info to preserve
        assert item.text(0) == "0x200004"

    def test_update_sprite_offset_returns_false_when_not_found(self, qtbot):
        """
        Verify update_sprite_offset returns False when offset doesn't exist.
        """
        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Try to update non-existent offset
        success = browser.update_sprite_offset(0x999999, 0x999998)

        assert not success


class TestSpriteAssetBrowserRefresh:
    """Tests for refresh button functionality in SpriteAssetBrowser."""

    def test_refresh_button_exists(self, qtbot):
        """Widget should have a refresh button."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        assert hasattr(browser, "_refresh_btn")
        assert browser._refresh_btn is not None

    def test_refresh_button_emits_signal(self, qtbot):
        """Clicking refresh should emit refresh_requested signal."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add a sprite
        browser.add_rom_sprite("Test Sprite", 0x1000)

        with qtbot.waitSignal(browser.refresh_requested, timeout=1000):
            browser._refresh_btn.click()

    def test_refresh_clears_thumbnails(self, qtbot):
        """Refresh should clear thumbnails from items."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap

        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add sprite and set thumbnail
        browser.add_rom_sprite("Test Sprite", 0x1000)
        test_pixmap = QPixmap(32, 32)
        browser.set_thumbnail(0x1000, test_pixmap)

        # Verify thumbnail is set
        rom_category = None
        for i in range(browser.tree.topLevelItemCount()):
            item = browser.tree.topLevelItem(i)
            if item.text(0) == "ROM Sprites":
                rom_category = item
                break

        sprite_item = rom_category.child(0)
        data_before = sprite_item.data(0, Qt.ItemDataRole.UserRole)
        assert data_before["thumbnail"] is not None

        # Clear thumbnails
        browser._clear_all_thumbnails()

        # Verify thumbnail is cleared
        data_after = sprite_item.data(0, Qt.ItemDataRole.UserRole)
        assert data_after["thumbnail"] is None

    def test_get_all_offsets_returns_all_sprite_offsets(self, qtbot):
        """get_all_offsets should return offsets for all sprites."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add multiple sprites
        browser.add_rom_sprite("Sprite 1", 0x1000)
        browser.add_rom_sprite("Sprite 2", 0x2000)
        browser.add_mesen_capture("Capture 1", 0x3000)

        offsets = browser.get_all_offsets()

        assert len(offsets) == 3
        assert 0x1000 in offsets
        assert 0x2000 in offsets
        assert 0x3000 in offsets

    def test_get_all_offsets_excludes_categories_and_local_files(self, qtbot):
        """get_all_offsets should exclude categories and local files."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add sprite and local file
        browser.add_rom_sprite("Sprite 1", 0x1000)
        browser.add_local_file("/path/to/file.png", "file.png")

        offsets = browser.get_all_offsets()

        # Should only have the ROM sprite offset, not local file
        assert len(offsets) == 1
        assert 0x1000 in offsets
