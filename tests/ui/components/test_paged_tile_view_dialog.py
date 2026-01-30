"""
Tests for PagedTileViewDialog.

Tests the dialog wrapper for the paged tile view widget.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QObject, Qt, Signal

from tests.fixtures.timeouts import signal_timeout
from ui.dialogs.paged_tile_view_dialog import PagedTileViewDialog


class MockWorker(QObject):
    """Mock worker to avoid threading issues in tests."""
    page_ready = Signal(int, object, int, int)
    error = Signal(str, object)
    operation_finished = Signal(bool, str)

    def __init__(self, *args, **kwargs):
        super().__init__()
    
    def start(self):
        pass
    
    def cancel(self):
        pass
        
    def wait(self, timeout=None):
        return True
    
    def isRunning(self):
        return False


class TestPagedTileViewDialog:
    """Test the PagedTileViewDialog implementation."""

    @pytest.fixture(autouse=True)
    def mock_workers(self):
        """Mock the worker classes to prevent threading crashes."""
        with patch("ui.widgets.paged_tile_view.PagedTileViewWorker", MockWorker), \
             patch("ui.widgets.paged_tile_view.DecompressedPageWorker", MockWorker):
            yield

    @pytest.fixture
    def sample_rom_data(self) -> bytes:
        """Create sample ROM data for testing."""
        return bytes(range(256)) * 1000  # 256000 bytes

    def test_dialog_creation(self, qtbot, sample_rom_data: bytes) -> None:
        """Test dialog can be created with ROM data."""
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
        )
        qtbot.addWidget(dialog)

        # Verify dialog is functional (can get current offset)
        assert dialog.get_current_offset() == 0
        assert dialog.get_palette() is None

    def test_dialog_with_palette(self, qtbot, sample_rom_data: bytes) -> None:
        """Test dialog creation with custom palette."""
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
            palette=palette,
        )
        qtbot.addWidget(dialog)

        assert dialog.get_palette() == palette

    def test_dialog_with_initial_offset(self, qtbot, sample_rom_data: bytes) -> None:
        """Test dialog navigates to initial offset."""
        # Navigate to second page
        initial_offset = 100000  # Middle of ROM

        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
            initial_offset=initial_offset,
        )
        qtbot.addWidget(dialog)

        # The widget should be on the page containing this offset
        assert dialog.get_current_page() > 0

    def test_set_palette(self, qtbot, sample_rom_data: bytes) -> None:
        """Test updating palette after creation."""
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
        )
        qtbot.addWidget(dialog)

        palette = [[255, 0, 0]] + [[i * 16, i * 16, i * 16] for i in range(1, 16)]
        dialog.set_palette(palette)

        assert dialog.get_palette() == palette

    def test_go_to_offset(self, qtbot, sample_rom_data: bytes) -> None:
        """Test navigating to an offset."""
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
        )
        qtbot.addWidget(dialog)

        # Start on page 0
        assert dialog.get_current_page() == 0

        # Navigate to an offset well into the ROM (guaranteed to be on page 1+)
        # Default grid is 50x50 = 2500 tiles, at 32 bytes/tile = 80000 bytes/page
        target_offset = 100000  # Well past first page

        dialog.go_to_offset(target_offset)

        # Should have navigated to a page > 0
        assert dialog.get_current_page() >= 1

    def test_get_current_offset(self, qtbot, sample_rom_data: bytes) -> None:
        """Test getting current offset."""
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
        )
        qtbot.addWidget(dialog)

        # Initial offset should be 0
        assert dialog.get_current_offset() == 0

    def test_offset_selected_signal(self, qtbot, sample_rom_data: bytes) -> None:
        """Test offset_selected signal emission."""
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
        )
        qtbot.addWidget(dialog)

        offsets: list[int] = []
        dialog.offset_selected.connect(offsets.append)

        # Simulate tile click then button click
        dialog.simulate_tile_selection(5000)
        assert dialog.get_selected_offset() == 5000
        assert dialog.is_go_to_enabled()

        dialog._on_go_to_clicked()
        assert len(offsets) == 1
        assert offsets[0] == 5000

    def test_tile_click_updates_button(self, qtbot, sample_rom_data: bytes) -> None:
        """Test tile click enables and updates Go to Offset button."""
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
        )
        qtbot.addWidget(dialog)

        # Initially button should be disabled
        assert not dialog.is_go_to_enabled()

        # Click a tile
        dialog.simulate_tile_selection(0x1234)

        assert dialog.is_go_to_enabled()
        assert dialog.get_selected_offset() == 0x1234

    def test_dialog_non_modal(self, qtbot, sample_rom_data: bytes) -> None:
        """Test dialog is non-modal."""
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
        )
        qtbot.addWidget(dialog)

        # Dialog should be non-modal
        assert dialog.windowModality() != Qt.WindowModality.ApplicationModal

    def test_dialog_close_cleanup(self, qtbot, sample_rom_data: bytes) -> None:
        """Test dialog cleanup on close."""
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
        )
        qtbot.addWidget(dialog)
        dialog.show()

        # Close the dialog
        dialog.close()

        # Widget should have been cleaned up
        assert dialog.is_cache_cleared()