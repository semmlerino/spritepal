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
