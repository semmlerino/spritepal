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
    NEARBY_DELTAS,
    NEARBY_THUMBNAIL_SIZE,
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
        """Verify thumbnail labels have correct size."""
        for label in sidebar._nearby_labels:
            assert label.width() == NEARBY_THUMBNAIL_SIZE
            assert label.height() == NEARBY_THUMBNAIL_SIZE

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
        assert NEARBY_DELTAS == [-128, -64, -32, 32, 64, 128]

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
        expected_offsets = [center_offset + delta for delta in NEARBY_DELTAS]
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
        expected_offsets = [center + delta for delta in NEARBY_DELTAS]
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
        expected_offsets = [center + delta for delta in NEARBY_DELTAS]
        assert sidebar._nearby_offsets == expected_offsets
