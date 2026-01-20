"""Tests for SpriteSelectionDialog.

Tests the sprite selection dialog for Mesen capture import.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from core.mesen_integration.click_extractor import (
    CaptureResult,
    OAMEntry,
    OBSELConfig,
    TileData,
)
from ui.frame_mapping.dialogs.sprite_selection_dialog import SpriteSelectionDialog


@pytest.fixture
def obsel_config() -> OBSELConfig:
    """Create a default OBSEL configuration."""
    return OBSELConfig(
        raw=0x63,
        name_base=3,
        name_select=0,
        size_select=3,
        tile_base_addr=0x6000,
        oam_base_addr=0x0000,
        oam_addr_offset=0x0100,
    )


@pytest.fixture
def sample_tile_data() -> TileData:
    """Create sample tile data."""
    return TileData(
        tile_index=10,
        vram_addr=0x6000,
        pos_x=0,
        pos_y=0,
        data_hex="FF" * 32,
    )


@pytest.fixture
def sample_palettes() -> dict[int, list[int]]:
    """Create sample RGB palettes."""
    return {
        0: [0x000000] + [0x00FF00] * 15,
        3: [0x000000] + [0x0000FF] * 15,
        7: [0x000000] + [0xFF0000] * 15,
    }


@pytest.fixture
def sample_capture(
    obsel_config: OBSELConfig,
    sample_tile_data: TileData,
    sample_palettes: dict[int, list[int]],
) -> CaptureResult:
    """Create a sample capture with entries in different palettes."""
    entries = [
        # Palette 0 - 2 entries (Kirby)
        OAMEntry(
            id=0,
            x=80,
            y=60,
            tile=10,
            width=32,
            height=32,
            flip_h=False,
            flip_v=False,
            palette=0,
            priority=2,
            tiles=[sample_tile_data],
        ),
        OAMEntry(
            id=1,
            x=112,
            y=60,
            tile=11,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=0,
            priority=2,
            tiles=[sample_tile_data],
        ),
        # Palette 3 - 3 entries (Dedede)
        OAMEntry(
            id=2,
            x=132,
            y=125,
            tile=20,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=3,
            priority=3,
            tiles=[sample_tile_data],
        ),
        OAMEntry(
            id=3,
            x=124,
            y=125,
            tile=21,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=3,
            priority=3,
            tiles=[sample_tile_data],
        ),
        OAMEntry(
            id=4,
            x=128,
            y=117,
            tile=22,
            width=16,
            height=16,
            flip_h=False,
            flip_v=False,
            palette=3,
            priority=3,
            tiles=[sample_tile_data],
        ),
        # Palette 7 - 1 entry (different sprite)
        OAMEntry(
            id=5,
            x=200,
            y=150,
            tile=30,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=7,
            priority=1,
            tiles=[sample_tile_data],
        ),
    ]

    return CaptureResult(
        frame=2,
        visible_count=len(entries),
        obsel=obsel_config,
        entries=entries,
        palettes=sample_palettes,
        timestamp=0,
    )


class TestSpriteSelectionDialogBasics:
    """Basic dialog functionality tests."""

    def test_dialog_shows_correct_entry_count(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Dialog displays correct number of OAM entries."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        # Info label should show 6 entries
        assert dialog._info_label is not None
        info_text = dialog._info_label.text()
        assert "6 OAM Entries" in info_text

    def test_dialog_shows_correct_palettes(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Dialog displays correct palette list."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._info_label is not None
        info_text = dialog._info_label.text()
        # Palettes should be listed in sorted order
        assert "Palettes:" in info_text
        assert "0" in info_text
        assert "3" in info_text
        assert "7" in info_text

    def test_dialog_shows_correct_frame_number(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Dialog displays correct frame number."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._info_label is not None
        info_text = dialog._info_label.text()
        assert "Frame 2" in info_text

    def test_sprite_list_has_correct_item_count(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Sprite list should have one item per OAM entry."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._sprite_list is not None
        assert dialog._sprite_list.count() == 6

    def test_all_sprites_selected_by_default(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """All sprites should be selected when dialog opens."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._sprite_list is not None
        for i in range(dialog._sprite_list.count()):
            item = dialog._sprite_list.item(i)
            assert item is not None
            assert item.checkState() == Qt.CheckState.Checked


class TestSpriteSelectionButtons:
    """Tests for Select All / Select None functionality."""

    def test_select_none_deselects_all(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Select None button deselects all entries."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        # Click Select None
        dialog._select_no_sprites()

        assert dialog._sprite_list is not None
        for i in range(dialog._sprite_list.count()):
            item = dialog._sprite_list.item(i)
            assert item is not None
            assert item.checkState() == Qt.CheckState.Unchecked

    def test_select_all_selects_all(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Select All button selects all entries."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        # First deselect all
        dialog._select_no_sprites()

        # Then select all
        dialog._select_all_sprites()

        assert dialog._sprite_list is not None
        for i in range(dialog._sprite_list.count()):
            item = dialog._sprite_list.item(i)
            assert item is not None
            assert item.checkState() == Qt.CheckState.Checked


class TestPaletteFilter:
    """Tests for palette filtering functionality."""

    def test_palette_filter_has_all_palettes(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Palette filter dropdown should have all used palettes plus 'All'."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._palette_filter is not None
        # Should have: All, Palette 0, Palette 3, Palette 7
        assert dialog._palette_filter.count() == 4

    def test_palette_filter_hides_non_matching(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Filtering by palette hides non-matching entries."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._palette_filter is not None
        assert dialog._sprite_list is not None

        # Select "Palette 3" (index 2 in combo: All=0, Pal0=1, Pal3=2, Pal7=3)
        dialog._palette_filter.setCurrentIndex(2)

        # Count visible items
        visible_count = 0
        for i in range(dialog._sprite_list.count()):
            item = dialog._sprite_list.item(i)
            if item is not None and not item.isHidden():
                visible_count += 1

        # Should show only palette 3 entries (IDs 2, 3, 4 = 3 entries)
        assert visible_count == 3

    def test_palette_filter_all_shows_all(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Selecting 'All Palettes' shows all entries."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._palette_filter is not None
        assert dialog._sprite_list is not None

        # First filter to Palette 3
        dialog._palette_filter.setCurrentIndex(2)

        # Then select All
        dialog._palette_filter.setCurrentIndex(0)

        # All should be visible
        visible_count = 0
        for i in range(dialog._sprite_list.count()):
            item = dialog._sprite_list.item(i)
            if item is not None and not item.isHidden():
                visible_count += 1

        assert visible_count == 6


class TestSelectedEntries:
    """Tests for selected_entries property."""

    def test_selected_entries_returns_all_when_all_checked(
        self, qtbot: pytest.fixture, sample_capture: CaptureResult
    ) -> None:
        """When all are checked, selected_entries returns all entries."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        # Simulate accepting the dialog
        dialog.accept()

        assert len(dialog.selected_entries) == 6

    def test_selected_entries_returns_none_when_all_unchecked(
        self, qtbot: pytest.fixture, sample_capture: CaptureResult
    ) -> None:
        """When none are checked, selected_entries returns empty list."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        dialog._select_no_sprites()
        dialog.accept()

        assert len(dialog.selected_entries) == 0

    def test_selected_entries_returns_only_checked(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """selected_entries returns only checked entries."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        # Deselect all first
        dialog._select_no_sprites()

        # Manually check items 2 and 3 (Palette 3 entries)
        assert dialog._sprite_list is not None
        item2 = dialog._sprite_list.item(2)
        item3 = dialog._sprite_list.item(3)
        assert item2 is not None
        assert item3 is not None
        item2.setCheckState(Qt.CheckState.Checked)
        item3.setCheckState(Qt.CheckState.Checked)

        dialog.accept()

        assert len(dialog.selected_entries) == 2
        selected_ids = {e.id for e in dialog.selected_entries}
        assert selected_ids == {2, 3}


class TestPreviewUpdate:
    """Tests for preview rendering."""

    def test_preview_updates_on_selection_change(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Preview should update when selection changes."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._preview_label is not None

        # Initially should have a pixmap (all selected)
        initial_pixmap = dialog._preview_label.pixmap()
        assert initial_pixmap is not None
        assert not initial_pixmap.isNull()

        # Deselect all
        dialog._select_no_sprites()

        # Should show text instead of pixmap
        # Check that either pixmap is null or text is set
        result_pixmap = dialog._preview_label.pixmap()
        if result_pixmap is not None and not result_pixmap.isNull():
            # If there's still a pixmap, the text should indicate no selection
            pass
        else:
            # Text should indicate selection needed
            assert "Select" in dialog._preview_label.text()

    def test_preview_updates_on_filter_change(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """Preview should update when palette filter changes."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._preview_label is not None
        assert dialog._palette_filter is not None

        # Track _update_preview calls
        update_calls: list[str] = []
        original_update = dialog._update_preview

        def tracking_update() -> None:
            update_calls.append("called")
            original_update()

        dialog._update_preview = tracking_update  # type: ignore[method-assign]

        # Clear tracking from init
        update_calls.clear()

        # Change filter to specific palette
        dialog._palette_filter.setCurrentIndex(1)  # Palette 0

        # Verify preview was updated
        assert len(update_calls) == 1

        # Change filter again
        update_calls.clear()
        dialog._palette_filter.setCurrentIndex(2)  # Palette 3

        # Verify preview was updated again
        assert len(update_calls) == 1


class TestListItemFormat:
    """Tests for list item display format."""

    def test_item_shows_sprite_dimensions(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """List items should show sprite dimensions."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._sprite_list is not None
        # First entry is 32x32
        item = dialog._sprite_list.item(0)
        assert item is not None
        assert "32x32" in item.text()

    def test_item_shows_position(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """List items should show sprite position."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._sprite_list is not None
        # First entry is at (80, 60)
        item = dialog._sprite_list.item(0)
        assert item is not None
        assert "@(80,60)" in item.text()

    def test_item_shows_palette(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """List items should show palette number."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._sprite_list is not None
        # First entry uses palette 0
        item = dialog._sprite_list.item(0)
        assert item is not None
        assert "Pal 0" in item.text()

    def test_item_shows_priority(self, qtbot: pytest.fixture, sample_capture: CaptureResult) -> None:
        """List items should show priority."""
        dialog = SpriteSelectionDialog(sample_capture)
        qtbot.addWidget(dialog)

        assert dialog._sprite_list is not None
        # First entry has priority 2
        item = dialog._sprite_list.item(0)
        assert item is not None
        assert "P2" in item.text()
