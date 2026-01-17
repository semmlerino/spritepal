"""
Tests for PagedTileViewWidget.

Tests the main tile grid widget with navigation and display.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from tests.fixtures.timeouts import signal_timeout, worker_timeout
from ui.widgets.paged_tile_view import (
    DEFAULT_PRESET_INDEX,
    GRID_PRESETS,
    PagedTileViewWidget,
    TileGridGraphicsView,
)
from ui.workers.paged_tile_view_worker import BYTES_PER_TILE


class TestTileGridGraphicsView:
    """Test the TileGridGraphicsView implementation."""

    def test_view_creation(self, qtbot) -> None:
        """Test view can be created."""
        view = TileGridGraphicsView()
        qtbot.addWidget(view)
        assert view._cols == 50
        assert view._rows == 50
        assert view._page_offset == 0

    def test_set_grid_info(self, qtbot) -> None:
        """Test setting grid dimensions and offset."""
        view = TileGridGraphicsView()
        qtbot.addWidget(view)

        view.set_grid_info(cols=20, rows=30, page_offset=64000)
        assert view._cols == 20
        assert view._rows == 30
        assert view._page_offset == 64000

    def test_set_image(self, qtbot) -> None:
        """Test setting an image in the view."""
        view = TileGridGraphicsView()
        qtbot.addWidget(view)

        image = QImage(400, 400, QImage.Format.Format_RGBA8888)
        image.fill(0xFF0000FF)

        view.set_image(image)
        assert view._pixmap_item is not None
        assert not view._scene.sceneRect().isEmpty()

    def test_clear_image(self, qtbot) -> None:
        """Test clearing the image."""
        view = TileGridGraphicsView()
        qtbot.addWidget(view)

        image = QImage(100, 100, QImage.Format.Format_RGBA8888)
        image.fill(0xFF0000FF)
        view.set_image(image)

        view.clear_image()
        assert view._pixmap_item is None


class TestPagedTileViewWidget:
    """Test the PagedTileViewWidget implementation."""

    @pytest.fixture
    def sample_rom_data(self) -> bytes:
        """Create sample ROM data for testing."""
        # Create data for multiple pages
        # Default 50x50 = 2500 tiles * 32 bytes = 80000 bytes per page
        # Create 3 pages worth
        return bytes(range(256)) * 1000  # 256000 bytes

    def test_widget_creation(self, qtbot) -> None:
        """Test widget can be created with default settings."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Check default grid dimensions from preset
        expected_cols = GRID_PRESETS[DEFAULT_PRESET_INDEX][1]
        expected_rows = GRID_PRESETS[DEFAULT_PRESET_INDEX][2]
        assert widget._cols == expected_cols
        assert widget._rows == expected_rows
        assert widget._current_page == 0
        assert widget._total_pages == 0

    def test_set_rom_data(self, qtbot, sample_rom_data: bytes) -> None:
        """Test setting ROM data updates page count."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        widget.set_rom_data(sample_rom_data)

        # Calculate expected pages
        bytes_per_page = widget._cols * widget._rows * BYTES_PER_TILE
        expected_pages = (len(sample_rom_data) + bytes_per_page - 1) // bytes_per_page

        assert widget._total_pages == expected_pages
        assert widget._current_page == 0

    def test_set_palette(self, qtbot, sample_rom_data: bytes) -> None:
        """Test setting palette."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        old_hash = widget._palette_hash
        palette = [[255, 0, 0]] + [[i * 16, i * 16, i * 16] for i in range(1, 16)]
        widget.set_palette(palette)

        assert widget._palette == palette
        assert widget._palette_hash != old_hash

    def test_set_grid_dimensions(self, qtbot, sample_rom_data: bytes) -> None:
        """Test changing grid dimensions."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        old_pages = widget._total_pages
        widget.set_grid_dimensions(20, 20)

        assert widget._cols == 20
        assert widget._rows == 20
        # Smaller grid = more pages
        assert widget._total_pages > old_pages

    def test_go_to_page(self, qtbot, sample_rom_data: bytes) -> None:
        """Test navigating to a specific page."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        page_signals: list[int] = []
        widget.page_changed.connect(page_signals.append)

        # Navigate to page 1
        if widget._total_pages > 1:
            widget.go_to_page(1)
            assert widget._current_page == 1
            assert len(page_signals) == 1
            assert page_signals[0] == 1

    def test_go_to_offset(self, qtbot, sample_rom_data: bytes) -> None:
        """Test navigating to a specific offset."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Calculate offset in middle of second page
        bytes_per_page = widget._cols * widget._rows * BYTES_PER_TILE
        target_offset = bytes_per_page + 1000

        widget.go_to_offset(target_offset)
        assert widget._current_page == 1

    def test_get_current_offset(self, qtbot, sample_rom_data: bytes) -> None:
        """Test getting current page offset."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        assert widget.get_current_offset() == 0

        if widget._total_pages > 1:
            widget.go_to_page(1)
            bytes_per_page = widget._cols * widget._rows * BYTES_PER_TILE
            assert widget.get_current_offset() == bytes_per_page

    def test_navigation_buttons_state(self, qtbot, sample_rom_data: bytes) -> None:
        """Test navigation button enable/disable state."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Load ROM data
        widget.set_rom_data(sample_rom_data)

        # On first page, prev should be disabled
        assert not widget._prev_btn.isEnabled()
        # Next should be enabled if multiple pages
        if widget._total_pages > 1:
            assert widget._next_btn.isEnabled()

            # Navigate to last page
            widget.go_to_page(widget._total_pages - 1)
            # Next should be disabled on last page
            assert not widget._next_btn.isEnabled()
            # Prev should be enabled
            assert widget._prev_btn.isEnabled()

    def test_tile_clicked_signal(self, qtbot, sample_rom_data: bytes) -> None:
        """Test tile_clicked signal emission."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        offsets: list[int] = []
        widget.tile_clicked.connect(offsets.append)

        # Simulate click through graphics view signal
        # Click at tile (5, 5) on page 0
        # Offset = 0 + (5 * 50 + 5) * 32 = 0 + 255 * 32 = 8160
        tile_index = 5 * widget._cols + 5
        expected_offset = tile_index * BYTES_PER_TILE
        widget._graphics_view.tile_clicked.emit(expected_offset)

        assert len(offsets) == 1
        assert offsets[0] == expected_offset

    def test_cleanup(self, qtbot, sample_rom_data: bytes) -> None:
        """Test cleanup method."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        widget.cleanup()
        # Cache should be cleared
        assert len(widget._cache) == 0

    def test_grid_preset_change(self, qtbot, sample_rom_data: bytes) -> None:
        """Test changing grid size via combo box."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Change to small grid preset (index 0)
        widget._grid_combo.setCurrentIndex(0)
        small_name, small_cols, small_rows = GRID_PRESETS[0]

        assert widget._cols == small_cols
        assert widget._rows == small_rows

    def test_goto_offset_hex_with_prefix(self, qtbot, sample_rom_data: bytes) -> None:
        """Test go-to-offset with 0x hex prefix."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Calculate target offset in page 1
        bytes_per_page = widget._cols * widget._rows * BYTES_PER_TILE
        target_offset = bytes_per_page + 0x1000

        # Type offset in input and trigger
        widget._offset_input.setText(f"0x{target_offset:X}")
        widget._on_goto_offset()

        assert widget._current_page == 1

    def test_goto_offset_hex_without_prefix(self, qtbot, sample_rom_data: bytes) -> None:
        """Test go-to-offset with plain hex (no prefix)."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Calculate target offset in page 1
        bytes_per_page = widget._cols * widget._rows * BYTES_PER_TILE
        target_offset = bytes_per_page + 0x1000

        # Type offset without 0x prefix
        widget._offset_input.setText(f"{target_offset:X}")
        widget._on_goto_offset()

        assert widget._current_page == 1

    def test_goto_offset_clears_input(self, qtbot, sample_rom_data: bytes) -> None:
        """Test that go-to-offset clears the input field after success."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        widget._offset_input.setText("0x1000")
        widget._on_goto_offset()

        assert widget._offset_input.text() == ""

    def test_goto_offset_invalid_format(self, qtbot, sample_rom_data: bytes) -> None:
        """Test go-to-offset with invalid format shows error."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        widget._offset_input.setText("not_a_number")
        widget._on_goto_offset()

        assert "Invalid offset format" in widget._status_label.text()

    def test_goto_offset_exceeds_rom(self, qtbot, sample_rom_data: bytes) -> None:
        """Test go-to-offset with offset beyond ROM size shows error."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Try offset way beyond ROM size
        widget._offset_input.setText("0xFFFFFFFF")
        widget._on_goto_offset()

        assert "exceeds ROM size" in widget._status_label.text()
