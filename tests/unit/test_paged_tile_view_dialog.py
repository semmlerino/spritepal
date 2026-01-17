"""
Tests for PagedTileViewDialog.

Tests the dialog wrapper for the paged tile view widget.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from tests.fixtures.timeouts import signal_timeout
from ui.dialogs.paged_tile_view_dialog import PagedTileViewDialog


class TestPagedTileViewDialog:
    """Test the PagedTileViewDialog implementation."""

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

        assert dialog._tile_view is not None
        assert dialog._rom_data == sample_rom_data
        assert dialog._palette is None

    def test_dialog_with_palette(self, qtbot, sample_rom_data: bytes) -> None:
        """Test dialog creation with custom palette."""
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
            palette=palette,
        )
        qtbot.addWidget(dialog)

        assert dialog._palette == palette

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
        assert dialog._tile_view is not None
        assert dialog._tile_view._current_page > 0

    def test_set_palette(self, qtbot, sample_rom_data: bytes) -> None:
        """Test updating palette after creation."""
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
        )
        qtbot.addWidget(dialog)

        palette = [[255, 0, 0]] + [[i * 16, i * 16, i * 16] for i in range(1, 16)]
        dialog.set_palette(palette)

        assert dialog._palette == palette
        assert dialog._tile_view is not None
        assert dialog._tile_view._palette == palette

    def test_go_to_offset(self, qtbot, sample_rom_data: bytes) -> None:
        """Test navigating to an offset."""
        dialog = PagedTileViewDialog(
            parent=None,
            rom_data=sample_rom_data,
        )
        qtbot.addWidget(dialog)

        assert dialog._tile_view is not None

        # Calculate an offset in page 1 (80000 bytes per page for 50x50 grid)
        # Our sample ROM is 256000 bytes, giving us 4 pages (0-3)
        bytes_per_page = dialog._tile_view._cols * dialog._tile_view._rows * 32
        target_offset = bytes_per_page + 1000  # Middle of page 1

        dialog.go_to_offset(target_offset)

        # Should have navigated to page 1
        assert dialog._tile_view._current_page == 1

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
        dialog._on_tile_clicked(5000)
        assert dialog._selected_offset == 5000
        assert dialog._go_to_btn.isEnabled()

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
        assert not dialog._go_to_btn.isEnabled()

        # Click a tile
        dialog._on_tile_clicked(0x1234)

        assert dialog._go_to_btn.isEnabled()
        assert "0x001234" in dialog._go_to_btn.text()

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
        assert dialog._tile_view is not None
        assert len(dialog._tile_view._cache) == 0
