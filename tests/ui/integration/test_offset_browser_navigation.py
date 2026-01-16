"""Integration tests for Manual Offset Browser navigation.

Tests the new keyboard-first navigation system including:
- Arrow keys for fine/coarse navigation
- Step size configuration
- History tracking
- Comparison pin slots
- Dialog staying open after apply
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt

from tests.fixtures.timeouts import signal_timeout

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
    from pytestqt.qtbot import QtBot


@pytest.fixture
def mock_rom_cache(mocker: MockerFixture):
    """Create a mock ROM cache."""
    mock = mocker.MagicMock()
    mock.get.return_value = None
    mock.put.return_value = None
    return mock


@pytest.fixture
def mock_settings_manager(mocker: MockerFixture):
    """Create a mock settings manager."""
    mock = mocker.MagicMock()
    mock.get_setting.return_value = None
    mock.set_setting.return_value = None
    return mock


@pytest.fixture
def mock_extraction_manager(mocker: MockerFixture):
    """Create a mock extraction manager."""
    mock = mocker.MagicMock()
    mock.get_rom_extractor.return_value = None
    return mock


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


class TestNavigationMethods:
    """Tests for navigation helper methods (_navigate_by_delta, _get_step_size)."""

    def test_navigate_forward_by_tile_row(self, offset_browser):
        """_navigate_by_delta with +16 bytes moves forward by one tile row."""
        offset_browser.set_offset(0x1000)
        offset_browser._navigate_by_delta(16)
        assert offset_browser.get_current_offset() == 0x1010

    def test_navigate_backward_by_tile_row(self, offset_browser):
        """_navigate_by_delta with -16 bytes moves backward."""
        offset_browser.set_offset(0x1000)
        offset_browser._navigate_by_delta(-16)
        assert offset_browser.get_current_offset() == 0x0FF0

    def test_navigate_by_tile(self, offset_browser):
        """_navigate_by_delta with +32 bytes moves by one tile."""
        offset_browser.set_offset(0x1000)
        offset_browser._navigate_by_delta(32)
        assert offset_browser.get_current_offset() == 0x1020

    def test_navigate_by_step_size(self, offset_browser):
        """_navigate_by_delta uses step size for larger movements."""
        offset_browser.set_offset(0x1000)

        # Set step size via browse tab
        if offset_browser.browse_tab is not None:
            offset_browser.browse_tab.step_spinbox.setValue(0x100)

        step = offset_browser._get_step_size()
        offset_browser._navigate_by_delta(step)
        assert offset_browser.get_current_offset() == 0x1100

    def test_navigate_coarse_forward(self, offset_browser):
        """_navigate_by_delta with +4096 bytes for coarse navigation."""
        offset_browser.set_offset(0x1000)
        offset_browser._navigate_by_delta(4096)
        assert offset_browser.get_current_offset() == 0x2000

    def test_navigate_coarse_backward(self, offset_browser):
        """_navigate_by_delta with -4096 bytes for coarse backward navigation."""
        offset_browser.set_offset(0x10000)
        offset_browser._navigate_by_delta(-4096)
        assert offset_browser.get_current_offset() == 0xF000

    def test_navigate_to_start(self, offset_browser):
        """set_offset(0) jumps to ROM start."""
        offset_browser.set_offset(0x10000)
        offset_browser.set_offset(0)
        assert offset_browser.get_current_offset() == 0

    def test_navigate_to_end(self, offset_browser):
        """set_offset(rom_size-1) jumps to ROM end."""
        offset_browser.set_offset(0x1000)
        offset_browser.set_offset(offset_browser.rom_size - 1)
        assert offset_browser.get_current_offset() == offset_browser.rom_size - 1

    def test_navigation_clamps_below_zero(self, offset_browser):
        """Navigation clamps to 0 when going below."""
        offset_browser.set_offset(10)
        offset_browser._navigate_by_delta(-100)
        assert offset_browser.get_current_offset() == 0

    def test_navigation_clamps_above_rom_size(self, offset_browser):
        """Navigation clamps to rom_size-1 when going above."""
        offset_browser.set_offset(offset_browser.rom_size - 10)
        offset_browser._navigate_by_delta(100)
        assert offset_browser.get_current_offset() == offset_browser.rom_size - 1

    def test_get_step_size_returns_browse_tab_value(self, offset_browser):
        """_get_step_size returns the browse tab's step spinbox value."""
        if offset_browser.browse_tab is not None:
            offset_browser.browse_tab.step_spinbox.setValue(0x200)
            assert offset_browser._get_step_size() == 0x200


class TestComparisonPins:
    """Tests for comparison pin functionality."""

    def test_pin_current_offset(self, offset_browser):
        """_pin_current_offset adds current offset to pins."""
        offset_browser.set_offset(0x1000)
        assert len(offset_browser._pinned_offsets) == 0

        offset_browser._pin_current_offset()
        assert len(offset_browser._pinned_offsets) == 1
        assert 0x1000 in offset_browser._pinned_offsets

    def test_pin_limit_is_two(self, offset_browser):
        """Only 2 pins are allowed; third replaces oldest."""
        offset_browser.set_offset(0x1000)
        offset_browser._pin_current_offset()

        offset_browser.set_offset(0x2000)
        offset_browser._pin_current_offset()

        offset_browser.set_offset(0x3000)
        offset_browser._pin_current_offset()

        assert len(offset_browser._pinned_offsets) == 2
        assert 0x1000 not in offset_browser._pinned_offsets  # First was replaced
        assert 0x2000 in offset_browser._pinned_offsets
        assert 0x3000 in offset_browser._pinned_offsets

    def test_clear_pins(self, offset_browser):
        """_clear_pinned_offsets clears all pins."""
        offset_browser.set_offset(0x1000)
        offset_browser._pin_current_offset()
        assert len(offset_browser._pinned_offsets) == 1

        offset_browser._clear_pinned_offsets()
        assert len(offset_browser._pinned_offsets) == 0

    def test_duplicate_pin_rejected(self, offset_browser):
        """Pinning the same offset twice is ignored."""
        offset_browser.set_offset(0x1000)
        offset_browser._pin_current_offset()
        offset_browser._pin_current_offset()

        assert len(offset_browser._pinned_offsets) == 1


class TestDialogBehavior:
    """Tests for dialog behavior changes."""

    def test_apply_keeps_dialog_open(self, qtbot: QtBot, offset_browser):
        """Apply offset (Enter) keeps dialog open."""
        offset_browser.show()
        offset_browser.set_offset(0x1000)

        # Connect to signal to verify it's emitted
        signals_received = []
        offset_browser.sprite_found.connect(lambda o, n: signals_received.append(o))

        qtbot.keyClick(offset_browser, Qt.Key.Key_Return)

        # Signal was emitted
        assert len(signals_received) == 1
        assert signals_received[0] == 0x1000

        # Dialog is still visible
        assert offset_browser.isVisible()


class TestHistoryTracking:
    """Tests for sidebar history tracking."""

    def test_sidebar_exists(self, offset_browser):
        """Sidebar widget is created."""
        assert offset_browser._sidebar is not None

    def test_history_tracks_offsets(self, qtbot: QtBot, offset_browser):
        """History tracks visited offsets after dwell time."""
        if offset_browser._sidebar is None:
            pytest.skip("Sidebar not available")

        offset_browser.set_offset(0x1000)

        # Wait for dwell time (500ms) + some buffer
        qtbot.wait(600)

        history = offset_browser._sidebar.get_history_offsets()
        assert 0x1000 in history

    def test_rapid_navigation_does_not_pollute_history(self, qtbot: QtBot, offset_browser):
        """Rapid navigation doesn't add entries to history."""
        if offset_browser._sidebar is None:
            pytest.skip("Sidebar not available")

        # Navigate rapidly without waiting
        for _ in range(5):
            qtbot.keyClick(offset_browser, Qt.Key.Key_Right)

        # No dwell time elapsed, so history should be empty
        history = offset_browser._sidebar.get_history_offsets()
        assert len(history) == 0


class TestSidebarScanResults:
    """Tests for sidebar scan results integration."""

    def test_scan_results_populate_sidebar(self, qtbot: QtBot, offset_browser):
        """Scan results are routed to sidebar."""
        if offset_browser._sidebar is None:
            pytest.skip("Sidebar not available")

        # Simulate scan results
        test_results = [
            {"offset": 0x1000, "quality": 0.95},
            {"offset": 0x2000, "quality": 0.85},
        ]

        # Convert to the format the handler expects
        offset_browser._on_scan_results_ready(test_results)

        # Verify sidebar was populated
        # The sidebar converts to its own format, so check via the list widget
        assert offset_browser._sidebar._scan_list.count() == 2
