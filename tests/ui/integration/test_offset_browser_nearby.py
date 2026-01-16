"""Tests for the Nearby Sprites Gallery panel in Manual Offset Browser sidebar.

These tests verify the nearby panel functionality:
- Panel existence and layout
- Thumbnail updates on offset changes
- Click navigation
- Edge case handling (offsets near ROM boundaries)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt

from tests.fixtures.timeouts import ui_timeout
from ui.widgets.offset_browser_sidebar import (
    NEARBY_DELTAS_CORE,
    NEARBY_DELTAS_EXTENDED,
    NEARBY_SIZES,
    NEARBY_UPDATE_DEBOUNCE_MS,
    OffsetBrowserSidebar,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def mock_rom_cache():
    """Create a mock ROM cache for testing."""
    cache = MagicMock()
    cache.get_cached_preview.return_value = None
    cache.set_cached_preview.return_value = None
    return cache


@pytest.fixture
def mock_settings_manager():
    """Create a mock settings manager for testing."""
    manager = MagicMock()
    manager.get_dialog_geometry.return_value = None
    manager.get_dialog_state.return_value = {}
    manager.get_view_state.return_value = {}
    return manager


@pytest.fixture
def mock_extraction_manager():
    """Create a mock extraction manager for testing."""
    manager = MagicMock()
    manager.get_rom_extractor.return_value = None
    return manager


@pytest.fixture
def offset_browser(qtbot: QtBot, mock_rom_cache, mock_settings_manager, mock_extraction_manager):
    """Create an offset browser dialog for testing."""
    from ui.dialogs.manual_offset_dialog import UnifiedManualOffsetDialog

    dialog = UnifiedManualOffsetDialog(
        parent=None,
        rom_cache=mock_rom_cache,
        settings_manager=mock_settings_manager,
        extraction_manager=mock_extraction_manager,
    )
    qtbot.addWidget(dialog)

    # Set ROM path and size so navigation works (_has_rom_data() requires both)
    dialog.rom_path = "/tmp/test.sfc"  # Doesn't need to exist for navigation tests
    dialog.rom_size = 0x400000  # 4MB

    return dialog


@pytest.fixture
def sidebar(qtbot: QtBot) -> OffsetBrowserSidebar:
    """Create a standalone sidebar for testing."""
    sidebar_widget = OffsetBrowserSidebar()
    qtbot.addWidget(sidebar_widget)
    return sidebar_widget


class TestNearbyPanelExists:
    """Tests for nearby panel creation and structure."""

    def test_nearby_panel_created_in_sidebar(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify nearby panel is created in sidebar."""
        assert hasattr(sidebar, "_nearby_panel")
        assert sidebar._nearby_panel is not None

    def test_nearby_labels_created(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify 6 thumbnail labels are created."""
        assert len(sidebar._nearby_labels) == 6

    def test_nearby_labels_have_correct_size(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify thumbnail labels have correct default size (medium)."""
        default_size = NEARBY_SIZES["medium"]
        for label in sidebar._nearby_labels:
            assert label.width() == default_size
            assert label.height() == default_size

    def test_nearby_timer_created(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify debounce timer is created."""
        assert sidebar._nearby_timer is not None
        assert sidebar._nearby_timer.isSingleShot()

    def test_nearby_current_offset_label_exists(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify current offset label is created."""
        assert sidebar._nearby_current_offset_label is not None


class TestNearbyPanelInDialog:
    """Tests for nearby panel integration with offset browser dialog."""

    def test_sidebar_has_nearby_panel(self, offset_browser) -> None:
        """Verify the dialog's sidebar has a nearby panel."""
        sidebar = offset_browser._sidebar
        assert sidebar is not None
        assert hasattr(sidebar, "_nearby_panel")
        assert sidebar._nearby_panel is not None

    def test_nearby_signal_connected(self, offset_browser) -> None:
        """Verify nearby_offset_selected signal is connected."""
        sidebar = offset_browser._sidebar
        assert sidebar is not None
        # Signal should be connected - we verify by checking the receivers
        # Note: in Qt, we can't easily check connected slots, so we verify via behavior test


class TestNearbyOffsetCalculations:
    """Tests for offset calculations in the nearby panel."""

    def test_nearby_deltas_are_correct(self) -> None:
        """Verify the delta constants are as expected."""
        assert NEARBY_DELTAS_CORE == [-128, -64, -32, 32, 64, 128]
        assert NEARBY_DELTAS_EXTENDED == [-1024, -512, -256, 256, 512, 1024]

    def test_update_nearby_schedules_timer(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify update_nearby_offsets starts the debounce timer."""
        sidebar.update_nearby_offsets(0x10000, 0x400000)
        assert sidebar._nearby_timer is not None
        assert sidebar._nearby_timer.isActive()

    def test_nearby_offsets_calculated_correctly(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify nearby offsets are calculated correctly after debounce."""
        center_offset = 0x10000
        rom_size = 0x400000

        sidebar.update_nearby_offsets(center_offset, rom_size)

        # Wait for debounce timer
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Check calculated offsets
        expected_offsets = [center_offset + delta for delta in NEARBY_DELTAS_CORE]
        assert sidebar._nearby_offsets == expected_offsets


class TestNearbyEdgeCases:
    """Tests for edge cases in the nearby panel."""

    def test_near_rom_start_hides_negative_offsets(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify offsets that would be negative are marked invalid."""
        # Set center offset near start (only 32 bytes in)
        center_offset = 32
        rom_size = 0x400000

        sidebar.update_nearby_offsets(center_offset, rom_size)
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # First three deltas (-128, -64, -32) should be invalid
        # 32 + (-128) = -96 (invalid)
        # 32 + (-64) = -32 (invalid)
        # 32 + (-32) = 0 (valid)
        # The invalid ones should be marked as -1
        assert sidebar._nearby_offsets[0] == -1  # -128
        assert sidebar._nearby_offsets[1] == -1  # -64
        assert sidebar._nearby_offsets[2] == 0  # -32 (offset 0 is valid)
        assert sidebar._nearby_offsets[3] > 0  # +32
        assert sidebar._nearby_offsets[4] > 0  # +64
        assert sidebar._nearby_offsets[5] > 0  # +128

    def test_near_rom_end_hides_overflow_offsets(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify offsets beyond ROM size are marked invalid."""
        rom_size = 0x400000
        # Set center offset near end (only 32 bytes from end)
        center_offset = rom_size - 32

        sidebar.update_nearby_offsets(center_offset, rom_size)
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Last three deltas (+32, +64, +128) should be invalid for this position
        # (rom_size - 32) + 32 = rom_size (invalid, >= rom_size)
        assert sidebar._nearby_offsets[0] > 0  # -128 (valid)
        assert sidebar._nearby_offsets[1] > 0  # -64 (valid)
        assert sidebar._nearby_offsets[2] > 0  # -32 (valid)
        assert sidebar._nearby_offsets[3] == -1  # +32 (overflow)
        assert sidebar._nearby_offsets[4] == -1  # +64 (overflow)
        assert sidebar._nearby_offsets[5] == -1  # +128 (overflow)

    def test_no_rom_extractor_clears_thumbnails(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify thumbnails are cleared when no ROM extractor is set."""
        # Without ROM extractor, update should clear thumbnails
        sidebar.update_nearby_offsets(0x10000, 0x400000)
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Thumbnails should be empty/placeholder
        for label in sidebar._nearby_labels:
            # Should show delta text, not a pixmap
            assert label.pixmap() is None or label.pixmap().isNull()


class TestNearbyClickNavigation:
    """Tests for click navigation on nearby thumbnails."""

    def test_click_emits_signal(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify clicking a nearby thumbnail emits the signal."""
        center_offset = 0x10000
        rom_size = 0x400000

        # Set up offsets first
        sidebar.update_nearby_offsets(center_offset, rom_size)
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Now click on a thumbnail
        with qtbot.waitSignal(sidebar.nearby_offset_selected, timeout=ui_timeout()) as blocker:
            sidebar._on_nearby_clicked(3)  # Index 3 is +32 offset

        # Verify the emitted offset
        expected_offset = center_offset + 32
        assert blocker.args == [expected_offset]

    def test_click_on_invalid_offset_does_not_emit(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify clicking on invalid offset doesn't emit signal."""
        # Set offset near start so some offsets are invalid
        sidebar.update_nearby_offsets(32, 0x400000)
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Signal spy to check no emission
        signal_emitted = False

        def capture_signal(_: int) -> None:
            nonlocal signal_emitted
            signal_emitted = True

        sidebar.nearby_offset_selected.connect(capture_signal)

        # Click on invalid index (first one, -128, which is invalid)
        sidebar._on_nearby_clicked(0)

        # Give a moment for any potential signal to emit
        qtbot.wait(50)

        # Should not have emitted
        assert not signal_emitted


class TestNearbyDebouncing:
    """Tests for debounce behavior."""

    def test_rapid_updates_debounced(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify rapid offset changes are debounced."""
        # Rapidly update offsets
        for i in range(10):
            sidebar.update_nearby_offsets(i * 1000, 0x400000)

        # Timer should still be active
        assert sidebar._nearby_timer is not None
        assert sidebar._nearby_timer.isActive()

        # Wait for debounce
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Only the last offset should be used
        # Last update was offset 9000
        center = 9000
        expected_offsets = [center + delta for delta in NEARBY_DELTAS_CORE]
        assert sidebar._nearby_offsets == expected_offsets

    def test_timer_restarts_on_new_update(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify timer restarts when new offset is set."""
        sidebar.update_nearby_offsets(0x10000, 0x400000)

        # Wait partway through debounce
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS // 2)

        # Send another update - should restart timer
        sidebar.update_nearby_offsets(0x20000, 0x400000)

        # Timer should still be active
        assert sidebar._nearby_timer is not None
        assert sidebar._nearby_timer.isActive()

        # Wait for full debounce from second update
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Should have the second offset's values
        center = 0x20000
        expected_offsets = [center + delta for delta in NEARBY_DELTAS_CORE]
        assert sidebar._nearby_offsets == expected_offsets


class TestNearbySizeControl:
    """Tests for thumbnail size control."""

    def test_size_buttons_exist(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify S/M/L buttons are created."""
        assert len(sidebar._nearby_size_buttons) == 3
        assert "small" in sidebar._nearby_size_buttons
        assert "medium" in sidebar._nearby_size_buttons
        assert "large" in sidebar._nearby_size_buttons

    def test_medium_is_default(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify medium (48px) is default size."""
        assert sidebar._nearby_thumbnail_size == NEARBY_SIZES["medium"]
        assert sidebar._nearby_size_buttons["medium"].isChecked()
        assert not sidebar._nearby_size_buttons["small"].isChecked()
        assert not sidebar._nearby_size_buttons["large"].isChecked()

    def test_size_change_updates_internal_state(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify changing size updates the internal size variable."""
        sidebar._on_size_changed("large")
        qtbot.wait(50)
        assert sidebar._nearby_thumbnail_size == NEARBY_SIZES["large"]

    def test_size_change_unchecks_other_buttons(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify changing size unchecks the other buttons."""
        sidebar._on_size_changed("small")
        qtbot.wait(50)
        assert sidebar._nearby_size_buttons["small"].isChecked()
        assert not sidebar._nearby_size_buttons["medium"].isChecked()
        assert not sidebar._nearby_size_buttons["large"].isChecked()

    def test_size_change_resizes_labels(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify changing size updates label dimensions."""
        sidebar._on_size_changed("large")
        qtbot.wait(50)
        # Check all labels have new size
        for label in sidebar._nearby_labels:
            assert label.width() == NEARBY_SIZES["large"]
            assert label.height() == NEARBY_SIZES["large"]

    def test_size_change_to_small(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify changing to small size works."""
        sidebar._on_size_changed("small")
        qtbot.wait(50)
        assert sidebar._nearby_thumbnail_size == NEARBY_SIZES["small"]
        for label in sidebar._nearby_labels:
            assert label.width() == NEARBY_SIZES["small"]


class TestNearbyExpansion:
    """Tests for expand/collapse functionality."""

    def test_expand_button_exists(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expand button is created."""
        assert sidebar._nearby_expand_btn is not None

    def test_collapsed_is_default(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify collapsed state is the default."""
        assert not sidebar._nearby_expanded
        assert sidebar._nearby_expand_btn is not None
        assert "Show More" in sidebar._nearby_expand_btn.text()

    def test_expand_shows_more_labels(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expansion adds 6 more thumbnails (12 total)."""
        assert len(sidebar._nearby_labels) == 6
        sidebar._on_expand_toggled()
        qtbot.wait(50)
        assert len(sidebar._nearby_labels) == 12

    def test_collapse_returns_to_six(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify collapsing returns to 6 thumbnails."""
        sidebar._on_expand_toggled()  # Expand
        qtbot.wait(50)
        assert len(sidebar._nearby_labels) == 12
        sidebar._on_expand_toggled()  # Collapse
        qtbot.wait(50)
        assert len(sidebar._nearby_labels) == 6

    def test_expand_button_text_changes(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expand button text changes on toggle."""
        assert sidebar._nearby_expand_btn is not None
        assert "Show More" in sidebar._nearby_expand_btn.text()
        sidebar._on_expand_toggled()
        qtbot.wait(50)
        assert "Show Less" in sidebar._nearby_expand_btn.text()
        sidebar._on_expand_toggled()
        qtbot.wait(50)
        assert "Show More" in sidebar._nearby_expand_btn.text()

    def test_expanded_deltas_include_extended_range(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expanded mode includes ±256, ±512, ±1024."""
        sidebar._on_expand_toggled()
        qtbot.wait(50)

        # Get all deltas from labels
        deltas = [label.property("nearby_delta") for label in sidebar._nearby_labels]

        # Should have both core and extended deltas
        for delta in NEARBY_DELTAS_CORE:
            assert delta in deltas
        for delta in NEARBY_DELTAS_EXTENDED:
            assert delta in deltas

    def test_collapsed_only_has_core_deltas(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify collapsed mode only has core deltas."""
        # Get all deltas from labels
        deltas = [label.property("nearby_delta") for label in sidebar._nearby_labels]

        # Should have only core deltas
        assert set(deltas) == set(NEARBY_DELTAS_CORE)

    def test_expanded_offsets_calculated_correctly(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expanded mode calculates correct offsets."""
        center_offset = 0x10000
        rom_size = 0x400000

        sidebar._on_expand_toggled()  # Expand
        sidebar.update_nearby_offsets(center_offset, rom_size)
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Check that we have 12 offsets
        assert len(sidebar._nearby_offsets) == 12

        # All core deltas should result in valid offsets
        for delta in NEARBY_DELTAS_CORE:
            expected_offset = center_offset + delta
            assert expected_offset in sidebar._nearby_offsets

        # Extended deltas should also be valid for this center
        for delta in NEARBY_DELTAS_EXTENDED:
            expected_offset = center_offset + delta
            assert expected_offset in sidebar._nearby_offsets


class TestNearbySizeAndExpansionCombination:
    """Tests for combining size changes with expansion."""

    def test_size_change_while_expanded(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify size change works correctly when expanded."""
        sidebar._on_expand_toggled()  # Expand
        qtbot.wait(50)
        assert len(sidebar._nearby_labels) == 12

        sidebar._on_size_changed("large")
        qtbot.wait(50)

        # Should still have 12 labels, all with large size
        assert len(sidebar._nearby_labels) == 12
        for label in sidebar._nearby_labels:
            assert label.width() == NEARBY_SIZES["large"]

    def test_expand_preserves_size(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expansion preserves the current size setting."""
        sidebar._on_size_changed("small")
        qtbot.wait(50)

        sidebar._on_expand_toggled()
        qtbot.wait(50)

        # All 12 labels should have small size
        assert len(sidebar._nearby_labels) == 12
        for label in sidebar._nearby_labels:
            assert label.width() == NEARBY_SIZES["small"]

    def test_collapse_preserves_size(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify collapse preserves the current size setting."""
        sidebar._on_size_changed("large")
        sidebar._on_expand_toggled()  # Expand
        sidebar._on_expand_toggled()  # Collapse
        qtbot.wait(50)

        # 6 labels should have large size
        assert len(sidebar._nearby_labels) == 6
        for label in sidebar._nearby_labels:
            assert label.width() == NEARBY_SIZES["large"]


class TestNearbyTooltips:
    """Tests for tooltips on nearby panel controls."""

    def test_size_buttons_have_tooltips(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify S/M/L buttons have descriptive tooltips with keyboard shortcuts."""
        assert "[1]" in sidebar._nearby_size_buttons["small"].toolTip()
        assert "36px" in sidebar._nearby_size_buttons["small"].toolTip()
        assert "[2]" in sidebar._nearby_size_buttons["medium"].toolTip()
        assert "48px" in sidebar._nearby_size_buttons["medium"].toolTip()
        assert "[3]" in sidebar._nearby_size_buttons["large"].toolTip()
        assert "64px" in sidebar._nearby_size_buttons["large"].toolTip()

    def test_expand_button_has_tooltip(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expand button has tooltip with shortcut hint."""
        assert sidebar._nearby_expand_btn is not None
        assert "[E]" in sidebar._nearby_expand_btn.toolTip()
        # Initial state should mention "Show" and extended range
        assert "Show" in sidebar._nearby_expand_btn.toolTip()
        assert "±256" in sidebar._nearby_expand_btn.toolTip()

    def test_expand_button_tooltip_updates_on_expand(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify tooltip changes when expanded."""
        assert sidebar._nearby_expand_btn is not None
        sidebar._on_expand_toggled()  # Expand
        qtbot.wait(50)
        assert "Hide" in sidebar._nearby_expand_btn.toolTip()
        assert "[E]" in sidebar._nearby_expand_btn.toolTip()

    def test_expand_button_tooltip_updates_on_collapse(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify tooltip changes when collapsed again."""
        assert sidebar._nearby_expand_btn is not None
        sidebar._on_expand_toggled()  # Expand
        sidebar._on_expand_toggled()  # Collapse
        qtbot.wait(50)
        assert "Show" in sidebar._nearby_expand_btn.toolTip()
        assert "±256" in sidebar._nearby_expand_btn.toolTip()
        assert "[E]" in sidebar._nearby_expand_btn.toolTip()


class TestNearbyKeyboardShortcuts:
    """Tests for keyboard shortcuts controlling the nearby panel."""

    def test_key_1_sets_small_size(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing 1 sets small thumbnail size."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # Start with medium (default)
        assert sidebar._nearby_thumbnail_size == NEARBY_SIZES["medium"]

        # Press key 1
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier)
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        assert sidebar._nearby_thumbnail_size == NEARBY_SIZES["small"]
        assert sidebar._nearby_size_buttons["small"].isChecked()

    def test_key_2_sets_medium_size(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing 2 sets medium thumbnail size."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # First change to small
        sidebar._on_size_changed("small")
        qtbot.wait(50)
        assert sidebar._nearby_thumbnail_size == NEARBY_SIZES["small"]

        # Press key 2
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_2, Qt.KeyboardModifier.NoModifier)
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        assert sidebar._nearby_thumbnail_size == NEARBY_SIZES["medium"]
        assert sidebar._nearby_size_buttons["medium"].isChecked()

    def test_key_3_sets_large_size(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing 3 sets large thumbnail size."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # Press key 3
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_3, Qt.KeyboardModifier.NoModifier)
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        assert sidebar._nearby_thumbnail_size == NEARBY_SIZES["large"]
        assert sidebar._nearby_size_buttons["large"].isChecked()

    def test_key_e_toggles_expand(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing E toggles expansion."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # Start collapsed
        assert not sidebar._nearby_expanded

        # Press key E to expand
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_E, Qt.KeyboardModifier.NoModifier)
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        assert sidebar._nearby_expanded
        assert len(sidebar._nearby_labels) == 12

        # Press key E again to collapse
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_E, Qt.KeyboardModifier.NoModifier)
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        assert not sidebar._nearby_expanded
        assert len(sidebar._nearby_labels) == 6

    def test_key_1_with_modifier_does_not_change_size(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing Ctrl+1 does not change size (modifiers block shortcut)."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # Start with medium (default)
        assert sidebar._nearby_thumbnail_size == NEARBY_SIZES["medium"]

        # Press Ctrl+1
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_1,
            Qt.KeyboardModifier.ControlModifier,
        )
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        # Size should remain medium (no change from modifier key)
        assert sidebar._nearby_thumbnail_size == NEARBY_SIZES["medium"]

    def test_key_e_with_modifier_does_not_toggle(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing Ctrl+E does not toggle expand (modifiers block shortcut)."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # Start collapsed
        assert not sidebar._nearby_expanded

        # Press Ctrl+E
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_E,
            Qt.KeyboardModifier.ControlModifier,
        )
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        # Should still be collapsed (no change from modifier key)
        assert not sidebar._nearby_expanded
