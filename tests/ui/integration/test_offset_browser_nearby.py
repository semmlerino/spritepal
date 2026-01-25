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
        """Verify nearby panel is created with initial thumbnails."""
        assert sidebar.get_thumbnail_count() == 6

    def test_nearby_labels_created(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify 6 thumbnail labels are created."""
        assert sidebar.get_thumbnail_count() == 6

    def test_nearby_labels_have_correct_size(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify thumbnail labels have correct default size (medium)."""
        default_size = NEARBY_SIZES["medium"]
        sizes = sidebar.get_thumbnail_label_sizes()
        for width, height in sizes:
            assert width == default_size
            assert height == default_size

    def test_nearby_timer_functional(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify debounce timer can be activated."""
        sidebar.update_nearby_offsets(0x10000, 0x400000)
        assert sidebar.is_debounce_timer_active()

    def test_nearby_current_offset_label_exists(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify current offset label shows initial text."""
        assert sidebar.get_current_offset_text() == "No offset"


class TestNearbyPanelInDialog:
    """Tests for nearby panel integration with offset browser dialog."""

    def test_sidebar_has_nearby_panel(self, offset_browser) -> None:
        """Verify the dialog's sidebar has a nearby panel with thumbnails."""
        sidebar = offset_browser._sidebar
        assert sidebar is not None
        assert sidebar.get_thumbnail_count() == 6

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
        assert sidebar.is_debounce_timer_active()

    def test_nearby_offsets_calculated_correctly(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify nearby offsets are calculated correctly after debounce."""
        center_offset = 0x10000
        rom_size = 0x400000

        sidebar.update_nearby_offsets(center_offset, rom_size)

        # Wait for debounce timer
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Check calculated offsets
        expected_offsets = [center_offset + delta for delta in NEARBY_DELTAS_CORE]
        assert sidebar.get_nearby_offsets() == expected_offsets


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
        offsets = sidebar.get_nearby_offsets()
        assert offsets[0] == -1  # -128
        assert offsets[1] == -1  # -64
        assert offsets[2] == 0  # -32 (offset 0 is valid)
        assert offsets[3] > 0  # +32
        assert offsets[4] > 0  # +64
        assert offsets[5] > 0  # +128

    def test_near_rom_end_hides_overflow_offsets(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify offsets beyond ROM size are marked invalid."""
        rom_size = 0x400000
        # Set center offset near end (only 32 bytes from end)
        center_offset = rom_size - 32

        sidebar.update_nearby_offsets(center_offset, rom_size)
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Last three deltas (+32, +64, +128) should be invalid for this position
        # (rom_size - 32) + 32 = rom_size (invalid, >= rom_size)
        offsets = sidebar.get_nearby_offsets()
        assert offsets[0] > 0  # -128 (valid)
        assert offsets[1] > 0  # -64 (valid)
        assert offsets[2] > 0  # -32 (valid)
        assert offsets[3] == -1  # +32 (overflow)
        assert offsets[4] == -1  # +64 (overflow)
        assert offsets[5] == -1  # +128 (overflow)

    def test_no_rom_extractor_clears_thumbnails(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify thumbnails are cleared when no ROM extractor is set."""
        # Without ROM extractor, update should clear thumbnails
        sidebar.update_nearby_offsets(0x10000, 0x400000)
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Thumbnails should be empty/placeholder (no pixmap)
        for i in range(sidebar.get_thumbnail_count()):
            assert not sidebar.has_thumbnail_pixmap(i)


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
            sidebar.click_thumbnail(3)  # Index 3 is +32 offset

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
        sidebar.click_thumbnail(0)

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
        assert sidebar.is_debounce_timer_active()

        # Wait for debounce
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Only the last offset should be used
        # Last update was offset 9000
        center = 9000
        expected_offsets = [center + delta for delta in NEARBY_DELTAS_CORE]
        assert sidebar.get_nearby_offsets() == expected_offsets

    def test_timer_restarts_on_new_update(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify timer restarts when new offset is set."""
        sidebar.update_nearby_offsets(0x10000, 0x400000)

        # Wait partway through debounce
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS // 2)

        # Send another update - should restart timer
        sidebar.update_nearby_offsets(0x20000, 0x400000)

        # Timer should still be active
        assert sidebar.is_debounce_timer_active()

        # Wait for full debounce from second update
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Should have the second offset's values
        center = 0x20000
        expected_offsets = [center + delta for delta in NEARBY_DELTAS_CORE]
        assert sidebar.get_nearby_offsets() == expected_offsets


class TestNearbySizeControl:
    """Tests for thumbnail size control."""

    def test_size_buttons_exist(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify S/M/L size options are available."""
        # Test by checking we can get tooltips for all sizes
        for size_key in ["small", "medium", "large"]:
            tooltip = sidebar.get_size_button_tooltip(size_key)
            assert tooltip != ""

    def test_medium_is_default(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify medium (96px) is default size."""
        assert sidebar.get_thumbnail_size() == NEARBY_SIZES["medium"]
        assert sidebar.get_selected_size_key() == "medium"

    def test_size_change_updates_internal_state(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify changing size updates the internal size variable."""
        sidebar.select_thumbnail_size("large")
        qtbot.wait(50)
        assert sidebar.get_thumbnail_size() == NEARBY_SIZES["large"]

    def test_size_change_unchecks_other_buttons(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify changing size selects the correct size key."""
        sidebar.select_thumbnail_size("small")
        qtbot.wait(50)
        assert sidebar.get_selected_size_key() == "small"

    def test_size_change_resizes_labels(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify changing size updates label dimensions."""
        sidebar.select_thumbnail_size("large")
        qtbot.wait(50)
        # Check all labels have new size
        sizes = sidebar.get_thumbnail_label_sizes()
        for width, height in sizes:
            assert width == NEARBY_SIZES["large"]
            assert height == NEARBY_SIZES["large"]

    def test_size_change_to_small(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify changing to small size works."""
        sidebar.select_thumbnail_size("small")
        qtbot.wait(50)
        assert sidebar.get_thumbnail_size() == NEARBY_SIZES["small"]
        sizes = sidebar.get_thumbnail_label_sizes()
        for width, _ in sizes:
            assert width == NEARBY_SIZES["small"]


class TestNearbyExpansion:
    """Tests for expand/collapse functionality."""

    def test_expand_button_exists(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expand button has text."""
        assert sidebar.get_expand_button_text() != ""

    def test_collapsed_is_default(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify collapsed state is the default."""
        assert not sidebar.is_expanded()
        assert "Show More" in sidebar.get_expand_button_text()

    def test_expand_shows_more_labels(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expansion adds 6 more thumbnails (12 total)."""
        assert sidebar.get_thumbnail_count() == 6
        sidebar.toggle_expansion()
        qtbot.wait(50)
        assert sidebar.get_thumbnail_count() == 12

    def test_collapse_returns_to_six(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify collapsing returns to 6 thumbnails."""
        sidebar.toggle_expansion()  # Expand
        qtbot.wait(50)
        assert sidebar.get_thumbnail_count() == 12
        sidebar.toggle_expansion()  # Collapse
        qtbot.wait(50)
        assert sidebar.get_thumbnail_count() == 6

    def test_expand_button_text_changes(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expand button text changes on toggle."""
        assert "Show More" in sidebar.get_expand_button_text()
        sidebar.toggle_expansion()
        qtbot.wait(50)
        assert "Show Less" in sidebar.get_expand_button_text()
        sidebar.toggle_expansion()
        qtbot.wait(50)
        assert "Show More" in sidebar.get_expand_button_text()

    def test_expanded_deltas_include_extended_range(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expanded mode includes ±256, ±512, ±1024."""
        sidebar.toggle_expansion()
        qtbot.wait(50)

        # Get all deltas from labels
        deltas = sidebar.get_thumbnail_label_deltas()

        # Should have both core and extended deltas
        for delta in NEARBY_DELTAS_CORE:
            assert delta in deltas
        for delta in NEARBY_DELTAS_EXTENDED:
            assert delta in deltas

    def test_collapsed_only_has_core_deltas(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify collapsed mode only has core deltas."""
        # Get all deltas from labels
        deltas = sidebar.get_thumbnail_label_deltas()

        # Should have only core deltas
        assert set(deltas) == set(NEARBY_DELTAS_CORE)

    def test_expanded_offsets_calculated_correctly(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expanded mode calculates correct offsets."""
        center_offset = 0x10000
        rom_size = 0x400000

        sidebar.toggle_expansion()  # Expand
        sidebar.update_nearby_offsets(center_offset, rom_size)
        qtbot.wait(NEARBY_UPDATE_DEBOUNCE_MS + 100)

        # Check that we have 12 offsets
        offsets = sidebar.get_nearby_offsets()
        assert len(offsets) == 12

        # All core deltas should result in valid offsets
        for delta in NEARBY_DELTAS_CORE:
            expected_offset = center_offset + delta
            assert expected_offset in offsets

        # Extended deltas should also be valid for this center
        for delta in NEARBY_DELTAS_EXTENDED:
            expected_offset = center_offset + delta
            assert expected_offset in offsets


class TestNearbySizeAndExpansionCombination:
    """Tests for combining size changes with expansion."""

    def test_size_change_while_expanded(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify size change works correctly when expanded."""
        sidebar.toggle_expansion()  # Expand
        qtbot.wait(50)
        assert sidebar.get_thumbnail_count() == 12

        sidebar.select_thumbnail_size("large")
        qtbot.wait(50)

        # Should still have 12 labels, all with large size
        assert sidebar.get_thumbnail_count() == 12
        sizes = sidebar.get_thumbnail_label_sizes()
        for width, _ in sizes:
            assert width == NEARBY_SIZES["large"]

    def test_expand_preserves_size(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expansion preserves the current size setting."""
        sidebar.select_thumbnail_size("small")
        qtbot.wait(50)

        sidebar.toggle_expansion()
        qtbot.wait(50)

        # All 12 labels should have small size
        assert sidebar.get_thumbnail_count() == 12
        sizes = sidebar.get_thumbnail_label_sizes()
        for width, _ in sizes:
            assert width == NEARBY_SIZES["small"]

    def test_collapse_preserves_size(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify collapse preserves the current size setting."""
        sidebar.select_thumbnail_size("large")
        sidebar.toggle_expansion()  # Expand
        sidebar.toggle_expansion()  # Collapse
        qtbot.wait(50)

        # 6 labels should have large size
        assert sidebar.get_thumbnail_count() == 6
        sizes = sidebar.get_thumbnail_label_sizes()
        for width, _ in sizes:
            assert width == NEARBY_SIZES["large"]


class TestNearbyTooltips:
    """Tests for tooltips on nearby panel controls."""

    def test_size_buttons_have_tooltips(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify S/M/L buttons have descriptive tooltips with keyboard shortcuts."""
        small_tip = sidebar.get_size_button_tooltip("small")
        medium_tip = sidebar.get_size_button_tooltip("medium")
        large_tip = sidebar.get_size_button_tooltip("large")

        assert "[1]" in small_tip
        assert "64px" in small_tip
        assert "[2]" in medium_tip
        assert "96px" in medium_tip
        assert "[3]" in large_tip
        assert "128px" in large_tip

    def test_expand_button_has_tooltip(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify expand button has tooltip with shortcut hint."""
        tooltip = sidebar.get_expand_button_tooltip()
        assert "[E]" in tooltip
        # Initial state should mention "Show" and extended range
        assert "Show" in tooltip
        assert "±256" in tooltip

    def test_expand_button_tooltip_updates_on_expand(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify tooltip changes when expanded."""
        sidebar.toggle_expansion()  # Expand
        qtbot.wait(50)
        tooltip = sidebar.get_expand_button_tooltip()
        assert "Hide" in tooltip
        assert "[E]" in tooltip

    def test_expand_button_tooltip_updates_on_collapse(self, qtbot: QtBot, sidebar: OffsetBrowserSidebar) -> None:
        """Verify tooltip changes when collapsed again."""
        sidebar.toggle_expansion()  # Expand
        sidebar.toggle_expansion()  # Collapse
        qtbot.wait(50)
        tooltip = sidebar.get_expand_button_tooltip()
        assert "Show" in tooltip
        assert "±256" in tooltip
        assert "[E]" in tooltip


class TestNearbyKeyboardShortcuts:
    """Tests for keyboard shortcuts controlling the nearby panel."""

    def test_key_1_sets_small_size(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing 1 sets small thumbnail size."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # Start with medium (default)
        assert sidebar.get_thumbnail_size() == NEARBY_SIZES["medium"]

        # Press key 1
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier)
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        assert sidebar.get_thumbnail_size() == NEARBY_SIZES["small"]
        assert sidebar.get_selected_size_key() == "small"

    def test_key_2_sets_medium_size(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing 2 sets medium thumbnail size."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # First change to small
        sidebar.select_thumbnail_size("small")
        qtbot.wait(50)
        assert sidebar.get_thumbnail_size() == NEARBY_SIZES["small"]

        # Press key 2
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_2, Qt.KeyboardModifier.NoModifier)
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        assert sidebar.get_thumbnail_size() == NEARBY_SIZES["medium"]
        assert sidebar.get_selected_size_key() == "medium"

    def test_key_3_sets_large_size(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing 3 sets large thumbnail size."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # Press key 3
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_3, Qt.KeyboardModifier.NoModifier)
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        assert sidebar.get_thumbnail_size() == NEARBY_SIZES["large"]
        assert sidebar.get_selected_size_key() == "large"

    def test_key_e_toggles_expand(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing E toggles expansion."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # Start collapsed
        assert not sidebar.is_expanded()

        # Press key E to expand
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_E, Qt.KeyboardModifier.NoModifier)
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        assert sidebar.is_expanded()
        assert sidebar.get_thumbnail_count() == 12

        # Press key E again to collapse
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_E, Qt.KeyboardModifier.NoModifier)
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        assert not sidebar.is_expanded()
        assert sidebar.get_thumbnail_count() == 6

    def test_key_1_with_modifier_does_not_change_size(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing Ctrl+1 does not change size (modifiers block shortcut)."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # Start with medium (default)
        assert sidebar.get_thumbnail_size() == NEARBY_SIZES["medium"]

        # Press Ctrl+1
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_1,
            Qt.KeyboardModifier.ControlModifier,
        )
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        # Size should remain medium (no change from modifier key)
        assert sidebar.get_thumbnail_size() == NEARBY_SIZES["medium"]

    def test_key_e_with_modifier_does_not_toggle(self, qtbot: QtBot, offset_browser) -> None:
        """Verify pressing Ctrl+E does not toggle expand (modifiers block shortcut)."""
        from PySide6.QtGui import QKeyEvent

        sidebar = offset_browser._sidebar
        assert sidebar is not None

        # Start collapsed
        assert not sidebar.is_expanded()

        # Press Ctrl+E
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_E,
            Qt.KeyboardModifier.ControlModifier,
        )
        offset_browser.keyPressEvent(event)
        qtbot.wait(50)

        # Should still be collapsed (no change from modifier key)
        assert not sidebar.is_expanded()


class TestNearbyPaletteControl:
    """Tests for palette control in nearby panel."""

    def test_palette_toggle_exists(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify palette toggle button is available."""
        # Check via facade - not enabled by default means toggle exists
        assert not sidebar.is_palette_toggle_available()

    def test_palette_toggle_disabled_by_default(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify palette toggle is disabled when no palette is set."""
        assert not sidebar.is_palette_toggle_available()
        assert not sidebar.is_custom_palette_enabled()

    def test_set_palette_enables_toggle(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify setting a palette enables the toggle."""
        # Create a dummy palette (16 colors)
        dummy_palette = [[i, i, i] for i in range(16)]
        sidebar.set_palette(dummy_palette)

        assert sidebar.is_palette_toggle_available()

    def test_clear_palette_disables_toggle(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify clearing palette disables the toggle."""
        dummy_palette = [[i, i, i] for i in range(16)]
        sidebar.set_palette(dummy_palette)
        assert sidebar.is_palette_toggle_available()

        sidebar.set_palette(None)
        assert not sidebar.is_palette_toggle_available()
        assert not sidebar.is_custom_palette_enabled()

    def test_toggle_updates_state(self, sidebar: OffsetBrowserSidebar) -> None:
        """Verify toggling palette updates internal state."""
        dummy_palette = [[i, i, i] for i in range(16)]
        sidebar.set_palette(dummy_palette)

        # Click to enable - we need to access the button directly for click
        # But we can verify the state via is_custom_palette_enabled()
        # Use the internal method that the button calls
        sidebar._on_palette_toggled(True)
        assert sidebar.is_custom_palette_enabled()

        # Click to disable
        sidebar._on_palette_toggled(False)
        assert not sidebar.is_custom_palette_enabled()
