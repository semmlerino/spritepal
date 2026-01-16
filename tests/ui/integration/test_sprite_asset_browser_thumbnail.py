"""
Tests for SpriteAssetBrowser thumbnail handling.

These tests verify that thumbnails are correctly set on ALL items
with matching offsets, not just the first match.

Bug context: When a ROM sprite and Mesen capture share the same offset
(valid scenario - same sprite discovered via Mesen), only the first item
in tree iteration was getting the thumbnail due to early return.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def browser(qtbot: QtBot):
    """Create a fresh SpriteAssetBrowser."""
    from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

    browser = SpriteAssetBrowser()
    qtbot.addWidget(browser)
    return browser


@pytest.fixture
def red_thumbnail() -> QPixmap:
    """Create a recognizable red test thumbnail."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(255, 0, 0))
    return pixmap


@pytest.fixture
def green_thumbnail() -> QPixmap:
    """Create a recognizable green test thumbnail."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 255, 0))
    return pixmap


class TestSetThumbnailMultipleMatches:
    """Tests for set_thumbnail when multiple items share the same offset."""

    def test_set_thumbnail_updates_all_items_with_same_offset(self, browser, red_thumbnail, qtbot: QtBot) -> None:
        """
        BUG REPRODUCTION: When ROM sprite and Mesen capture share same offset,
        set_thumbnail should update BOTH items, not just the first match.

        This test will FAIL before the fix is applied.
        """
        shared_offset = 0x3C6EF1

        # Add ROM sprite and Mesen capture at same offset
        browser.add_rom_sprite("ROM Sprite", shared_offset)
        browser.add_mesen_capture("Mesen Capture", shared_offset)

        # Deliver thumbnail for this offset
        browser.set_thumbnail(shared_offset, red_thumbnail)

        # Get the category items
        rom_category = browser._rom_category
        mesen_category = browser._mesen_category

        # Find the items we added
        rom_item = rom_category.child(0)
        mesen_item = mesen_category.child(0)

        assert rom_item is not None, "ROM item should exist"
        assert mesen_item is not None, "Mesen item should exist"

        # Get their data
        rom_data = rom_item.data(0, Qt.ItemDataRole.UserRole)
        mesen_data = mesen_item.data(0, Qt.ItemDataRole.UserRole)

        # Verify both items have the thumbnail
        assert rom_data.get("thumbnail") is not None, (
            "ROM item missing thumbnail - set_thumbnail stopped at first match"
        )
        assert mesen_data.get("thumbnail") is not None, (
            "Mesen item missing thumbnail - set_thumbnail stopped at first match"
        )

    def test_set_thumbnail_updates_multiple_rom_sprites_same_offset(self, browser, red_thumbnail, qtbot: QtBot) -> None:
        """
        Edge case: Multiple ROM sprites with same offset (no idempotency check).
        All should receive the thumbnail.
        """
        shared_offset = 0x100000

        # Add same offset twice (no duplicate check in add_rom_sprite)
        browser.add_rom_sprite("Sprite Copy 1", shared_offset)
        browser.add_rom_sprite("Sprite Copy 2", shared_offset)

        browser.set_thumbnail(shared_offset, red_thumbnail)

        rom_category = browser._rom_category
        item1 = rom_category.child(0)
        item2 = rom_category.child(1)

        data1 = item1.data(0, Qt.ItemDataRole.UserRole)
        data2 = item2.data(0, Qt.ItemDataRole.UserRole)

        assert data1.get("thumbnail") is not None, "First ROM item missing thumbnail"
        assert data2.get("thumbnail") is not None, "Second ROM item missing thumbnail"


class TestSetThumbnailUniqueOffsets:
    """Tests for normal case: unique offsets."""

    def test_set_thumbnail_with_unique_offsets(self, browser, red_thumbnail, green_thumbnail, qtbot: QtBot) -> None:
        """Verify unique offsets each get their own thumbnail correctly."""
        browser.add_rom_sprite("Sprite A", 0x1000)
        browser.add_rom_sprite("Sprite B", 0x2000)

        browser.set_thumbnail(0x1000, red_thumbnail)
        browser.set_thumbnail(0x2000, green_thumbnail)

        rom_category = browser._rom_category
        item_a = rom_category.child(0)
        item_b = rom_category.child(1)

        data_a = item_a.data(0, Qt.ItemDataRole.UserRole)
        data_b = item_b.data(0, Qt.ItemDataRole.UserRole)

        assert data_a.get("thumbnail") is not None, "Sprite A missing thumbnail"
        assert data_b.get("thumbnail") is not None, "Sprite B missing thumbnail"

    def test_set_thumbnail_no_match_does_not_crash(self, browser, red_thumbnail, qtbot: QtBot) -> None:
        """Setting thumbnail for non-existent offset should not crash."""
        browser.add_rom_sprite("Existing Sprite", 0x1000)

        # Set thumbnail for non-existent offset - should not raise
        browser.set_thumbnail(0x9999, red_thumbnail)

        # Verify existing sprite is unaffected
        rom_category = browser._rom_category
        item = rom_category.child(0)
        data = item.data(0, Qt.ItemDataRole.UserRole)
        assert data.get("thumbnail") is None, "Unrelated sprite should not get thumbnail"


class TestClearThumbnailMultipleMatches:
    """Tests for clear_thumbnail when multiple items share the same offset."""

    def test_clear_thumbnail_clears_all_items_with_same_offset(self, browser, red_thumbnail, qtbot: QtBot) -> None:
        """
        BUG REPRODUCTION: When ROM sprite and Mesen capture share same offset,
        clear_thumbnail should clear BOTH items, not just the first match.

        This test will FAIL before the fix is applied.
        """
        shared_offset = 0x3C6EF1

        # Add ROM sprite and Mesen capture at same offset
        browser.add_rom_sprite("ROM Sprite", shared_offset)
        browser.add_mesen_capture("Mesen Capture", shared_offset)

        # Set thumbnails for both
        browser.set_thumbnail(shared_offset, red_thumbnail)

        # Verify both have thumbnails before clearing
        rom_category = browser._rom_category
        mesen_category = browser._mesen_category
        rom_item = rom_category.child(0)
        mesen_item = mesen_category.child(0)

        rom_data = rom_item.data(0, Qt.ItemDataRole.UserRole)
        mesen_data = mesen_item.data(0, Qt.ItemDataRole.UserRole)
        assert rom_data.get("thumbnail") is not None, "Setup: ROM item should have thumbnail"
        assert mesen_data.get("thumbnail") is not None, "Setup: Mesen item should have thumbnail"

        # Clear thumbnails
        result = browser.clear_thumbnail(shared_offset)

        # Refresh data after clear
        rom_data = rom_item.data(0, Qt.ItemDataRole.UserRole)
        mesen_data = mesen_item.data(0, Qt.ItemDataRole.UserRole)

        # Both should have thumbnail cleared
        assert rom_data.get("thumbnail") is None, (
            "ROM item still has thumbnail - clear_thumbnail stopped at first match"
        )
        assert mesen_data.get("thumbnail") is None, (
            "Mesen item still has thumbnail - clear_thumbnail stopped at first match"
        )
        assert result is True, "Should return True when items were cleared"

    def test_clear_thumbnail_returns_false_for_nonexistent_offset(self, browser, qtbot: QtBot) -> None:
        """clear_thumbnail should return False when offset doesn't exist."""
        browser.add_rom_sprite("Existing Sprite", 0x1000)

        result = browser.clear_thumbnail(0x9999)

        assert result is False, "Should return False when no items match"


class TestUpdateSpriteOffsetMultipleMatches:
    """Tests for update_sprite_offset when multiple items share the same offset.

    Bug: update_sprite_offset returns after first match, leaving other items
    with stale offset values. This causes desync when a sprite exists in both
    ROM Sprites and Mesen Captures categories.
    """

    def test_update_sprite_offset_updates_all_items_with_same_offset(self, browser, qtbot: QtBot) -> None:
        """
        BUG REPRODUCTION: When ROM sprite and Mesen capture share same offset,
        update_sprite_offset should update BOTH items, not just the first match.

        This test will FAIL before the fix is applied.
        """
        old_offset = 0x3C6EF1
        new_offset = 0x3C6EF3  # Simulating +2 alignment adjustment

        # Add ROM sprite and Mesen capture at same offset
        browser.add_rom_sprite("ROM Sprite", old_offset)
        browser.add_mesen_capture("Mesen Capture", old_offset)

        # Verify setup
        rom_category = browser._rom_category
        mesen_category = browser._mesen_category
        rom_item = rom_category.child(0)
        mesen_item = mesen_category.child(0)

        assert rom_item is not None, "ROM item should exist"
        assert mesen_item is not None, "Mesen item should exist"

        # Update offset (simulating alignment adjustment from preview coordinator)
        result = browser.update_sprite_offset(old_offset, new_offset)

        # Refresh data after update
        rom_data = rom_item.data(0, Qt.ItemDataRole.UserRole)
        mesen_data = mesen_item.data(0, Qt.ItemDataRole.UserRole)

        # Both items should have updated offset
        assert rom_data.get("offset") == new_offset, (
            f"ROM item offset not updated: expected 0x{new_offset:X}, "
            f"got 0x{rom_data.get('offset'):X}. "
            "update_sprite_offset stopped at first match."
        )
        assert mesen_data.get("offset") == new_offset, (
            f"Mesen item offset not updated: expected 0x{new_offset:X}, "
            f"got 0x{mesen_data.get('offset'):X}. "
            "update_sprite_offset stopped at first match."
        )
        assert result is True, "Should return True when items were updated"

    def test_update_sprite_offset_emits_signal_for_each_item(self, browser, qtbot: QtBot) -> None:
        """
        The item_offset_changed signal should be emitted for EACH updated item,
        so the thumbnail controller can re-queue thumbnails correctly.
        """
        old_offset = 0x1000
        new_offset = 0x1002

        # Add multiple items at same offset
        browser.add_rom_sprite("ROM Sprite", old_offset)
        browser.add_mesen_capture("Mesen Capture", old_offset)

        # Track signal emissions
        signal_count = 0

        def on_offset_changed(old: int, new: int) -> None:
            nonlocal signal_count
            signal_count += 1

        browser.item_offset_changed.connect(on_offset_changed)

        browser.update_sprite_offset(old_offset, new_offset)

        # Should emit once per updated item
        assert signal_count == 2, (
            f"Expected 2 signal emissions (one per item), got {signal_count}. "
            "update_sprite_offset should emit for each updated item."
        )

    def test_update_sprite_offset_updates_display_text_for_all_items(self, browser, qtbot: QtBot) -> None:
        """
        When items have offset in display text (like Mesen captures),
        all matching items should have their text updated.

        Note: add_mesen_capture is idempotent (skips duplicate offsets),
        so we use ROM sprite + Mesen capture which both have the offset.
        """
        old_offset = 0x293AEB
        new_offset = 0x293AED

        # Add a ROM sprite (no offset in name) and a Mesen capture (offset in name)
        browser.add_rom_sprite("Plain Name", old_offset)
        browser.add_mesen_capture(f"0x{old_offset:06X} (capture)", old_offset)

        browser.update_sprite_offset(old_offset, new_offset)

        rom_category = browser._rom_category
        mesen_category = browser._mesen_category
        rom_item = rom_category.child(0)
        mesen_item = mesen_category.child(0)

        # ROM sprite text should be unchanged (no offset in name)
        assert rom_item.text(0) == "Plain Name", f"ROM item text should not change: {rom_item.text(0)}"

        # Mesen capture text should have updated offset
        assert f"0x{new_offset:06X}" in mesen_item.text(0), f"Mesen item text not updated: {mesen_item.text(0)}"
        assert f"0x{old_offset:06X}" not in mesen_item.text(0), (
            f"Mesen item still has old offset in text: {mesen_item.text(0)}"
        )
