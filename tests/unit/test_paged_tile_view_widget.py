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

pytestmark = [pytest.mark.unit, pytest.mark.parallel_unsafe]


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

    def test_palette_checkbox_default_state(self, qtbot) -> None:
        """Test palette checkbox is checked by default."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        assert widget._palette_checkbox.isChecked()
        assert widget._palette_enabled is True

    def test_palette_toggle_disables_palette(self, qtbot, sample_rom_data: bytes) -> None:
        """Test unchecking palette checkbox disables palette rendering."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Set a palette
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        widget.set_palette(palette)
        assert widget._palette_enabled is True

        # Uncheck the palette checkbox
        widget._palette_checkbox.setChecked(False)

        assert widget._palette_enabled is False

    def test_palette_toggle_enables_palette(self, qtbot, sample_rom_data: bytes) -> None:
        """Test checking palette checkbox enables palette rendering."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Set a palette and disable it
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        widget.set_palette(palette)
        widget._palette_checkbox.setChecked(False)
        assert widget._palette_enabled is False

        # Re-check the palette checkbox
        widget._palette_checkbox.setChecked(True)

        assert widget._palette_enabled is True

    def test_palette_checkbox_disabled_when_no_palette(self, qtbot) -> None:
        """Test palette checkbox is disabled when no palette is set."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Set palette to None
        widget.set_palette(None)

        assert not widget._palette_checkbox.isEnabled()
        assert not widget._palette_checkbox.isChecked()

    def test_palette_checkbox_enabled_when_palette_set(self, qtbot) -> None:
        """Test palette checkbox is enabled when a palette is set."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # First set to None to disable
        widget.set_palette(None)
        assert not widget._palette_checkbox.isEnabled()

        # Now set a real palette
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        widget.set_palette(palette)

        # Checkbox should be enabled (but may not be checked due to previous None)
        assert widget._palette_checkbox.isEnabled()

    def test_palette_dropdown_default_has_grayscale(self, qtbot) -> None:
        """Test palette dropdown has Grayscale option by default."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        assert widget._palette_combo.count() == 1
        assert widget._palette_combo.itemText(0) == "Grayscale"

    def test_add_palette_option(self, qtbot) -> None:
        """Test adding a palette option to the dropdown."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        widget.add_palette_option("Test Palette", palette)

        assert widget._palette_combo.count() == 2
        assert widget._palette_combo.itemText(1) == "Test Palette"
        assert "Test Palette" in widget._palette_options

    def test_set_palette_with_name(self, qtbot) -> None:
        """Test setting palette with a custom name."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        palette = [[255, 0, 0]] + [[i * 16, i * 16, i * 16] for i in range(1, 16)]
        widget.set_palette(palette, name="Red Palette")

        assert widget._palette_combo.currentText() == "Red Palette"
        assert widget._selected_palette_name == "Red Palette"
        assert widget._palette == palette

    def test_select_palette_by_name(self, qtbot, sample_rom_data: bytes) -> None:
        """Test selecting a palette by name."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Add two palettes
        palette1 = [[255, 0, 0] for _ in range(16)]
        palette2 = [[0, 255, 0] for _ in range(16)]
        widget.add_palette_option("Red", palette1)
        widget.add_palette_option("Green", palette2)

        # Select Green
        result = widget.select_palette("Green")
        assert result is True
        assert widget._palette_combo.currentText() == "Green"

    def test_select_nonexistent_palette(self, qtbot) -> None:
        """Test selecting a palette that doesn't exist."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        result = widget.select_palette("Nonexistent")
        assert result is False

    def test_clear_palette_options(self, qtbot) -> None:
        """Test clearing all palette options."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Add some palettes
        palette1 = [[255, 0, 0] for _ in range(16)]
        palette2 = [[0, 255, 0] for _ in range(16)]
        widget.add_palette_option("Red", palette1)
        widget.add_palette_option("Green", palette2)
        assert widget._palette_combo.count() == 3

        # Clear all
        widget.clear_palette_options()

        assert widget._palette_combo.count() == 1
        assert widget._palette_combo.itemText(0) == "Grayscale"
        assert widget._selected_palette_name == "Grayscale"
        assert widget._palette is None

    def test_palette_selection_updates_state(self, qtbot, sample_rom_data: bytes) -> None:
        """Test that selecting a palette updates checkbox and internal state."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Add a palette and select it
        palette = [[255, 0, 0] for _ in range(16)]
        widget.add_palette_option("Red", palette)
        widget.select_palette("Red")

        # Checkbox should be enabled and checked
        assert widget._palette_checkbox.isEnabled()
        assert widget._palette_checkbox.isChecked()
        assert widget._palette_enabled is True

        # Now select Grayscale
        widget.select_palette("Grayscale")

        # Checkbox should be disabled and unchecked
        assert not widget._palette_checkbox.isEnabled()
        assert not widget._palette_checkbox.isChecked()
        assert widget._palette_enabled is False

    def test_user_palette_tracking(self, qtbot) -> None:
        """Test that user palettes are tracked separately from built-in ones."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Add built-in palette (default behavior)
        palette1 = [[255, 0, 0] for _ in range(16)]
        widget.add_palette_option("Built-in", palette1)
        assert "Built-in" not in widget._user_palettes

        # Add user palette
        palette2 = [[0, 255, 0] for _ in range(16)]
        widget.add_palette_option("User Palette", palette2, is_user_palette=True)
        assert "User Palette" in widget._user_palettes

    def test_get_user_palettes(self, qtbot) -> None:
        """Test retrieving user palettes for persistence."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Add mix of built-in and user palettes
        palette1 = [[255, 0, 0] for _ in range(16)]
        palette2 = [[0, 255, 0] for _ in range(16)]
        palette3 = [[0, 0, 255] for _ in range(16)]

        widget.add_palette_option("Built-in", palette1)
        widget.add_palette_option("User1", palette2, is_user_palette=True)
        widget.add_palette_option("User2", palette3, is_user_palette=True)

        user_palettes = widget.get_user_palettes()

        assert len(user_palettes) == 2
        assert "User1" in user_palettes
        assert "User2" in user_palettes
        assert "Built-in" not in user_palettes
        assert user_palettes["User1"] == palette2
        assert user_palettes["User2"] == palette3

    def test_load_user_palettes(self, qtbot) -> None:
        """Test loading user palettes from saved data."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        palette1 = [[255, 0, 0] for _ in range(16)]
        palette2 = [[0, 255, 0] for _ in range(16)]

        saved_palettes = {
            "Saved1": palette1,
            "Saved2": palette2,
        }

        widget.load_user_palettes(saved_palettes)

        assert "Saved1" in widget._palette_options
        assert "Saved2" in widget._palette_options
        assert "Saved1" in widget._user_palettes
        assert "Saved2" in widget._user_palettes
        assert widget._palette_combo.count() == 3  # Grayscale + 2 loaded

    def test_clear_palette_options_clears_user_palettes(self, qtbot) -> None:
        """Test that clear_palette_options also clears user palette tracking."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Add user palette
        palette = [[255, 0, 0] for _ in range(16)]
        widget.add_palette_option("User Palette", palette, is_user_palette=True)
        assert len(widget._user_palettes) == 1

        widget.clear_palette_options()

        assert len(widget._user_palettes) == 0

    def test_palette_menu_button_exists(self, qtbot) -> None:
        """Test that palette management menu button exists."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        assert widget._palette_menu_btn is not None
        assert widget._palette_menu is not None
        assert widget._action_load is not None
        assert widget._action_rename is not None
        assert widget._action_delete is not None

    def test_rename_delete_disabled_for_builtin(self, qtbot) -> None:
        """Test that rename/delete are disabled for built-in palettes."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Grayscale is selected by default
        assert not widget._action_rename.isEnabled()
        assert not widget._action_delete.isEnabled()

    def test_rename_delete_enabled_for_user_palette(self, qtbot) -> None:
        """Test that rename/delete are enabled for user palettes."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Add and select user palette
        palette = [[255, 0, 0] for _ in range(16)]
        widget.add_palette_option("User Palette", palette, is_user_palette=True)
        widget.select_palette("User Palette")

        assert widget._action_rename.isEnabled()
        assert widget._action_delete.isEnabled()

    def test_load_palette_file_valid(self, qtbot, tmp_path) -> None:
        """Test loading a valid palette file."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Create a test palette file
        palette_data = {
            "name": "Test Palette",
            "colors": [[255, 0, 0], [0, 255, 0], [0, 0, 255]] + [[0, 0, 0] for _ in range(13)],
        }
        palette_file = tmp_path / "test.pal.json"
        palette_file.write_text(__import__("json").dumps(palette_data))

        result = widget._load_palette_file(palette_file)

        assert result is not None
        assert result["name"] == "Test Palette"
        assert len(result["colors"]) == 16
        assert result["colors"][0] == [255, 0, 0]

    def test_load_palette_file_missing_colors(self, qtbot, tmp_path) -> None:
        """Test loading a palette file without colors field."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Create an invalid palette file
        palette_data = {"name": "Invalid Palette"}
        palette_file = tmp_path / "invalid.pal.json"
        palette_file.write_text(__import__("json").dumps(palette_data))

        import pytest

        with pytest.raises(ValueError, match="Missing 'colors' field"):
            widget._load_palette_file(palette_file)

    def test_load_palette_file_uses_filename_if_no_name(self, qtbot, tmp_path) -> None:
        """Test that palette name defaults to filename if not in file."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Create a palette file without name
        palette_data = {
            "colors": [[255, 0, 0] for _ in range(16)],
        }
        palette_file = tmp_path / "my_custom_palette.pal.json"
        palette_file.write_text(__import__("json").dumps(palette_data))

        result = widget._load_palette_file(palette_file)

        assert result is not None
        assert result["name"] == "my_custom_palette.pal"  # Stem of filename


class TestTileGridHighlight:
    """Test the highlight feature for go-to-offset."""

    @pytest.fixture
    def sample_rom_data(self) -> bytes:
        """Create sample ROM data for testing."""
        return bytes(range(256)) * 1000  # 256000 bytes

    def test_set_highlight_creates_rect(self, qtbot, sample_rom_data: bytes) -> None:
        """Test that setting a highlight creates a rectangle."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Wait for page render to complete
        qtbot.waitUntil(lambda: widget._graphics_view._pixmap_item is not None, timeout=5000)

        # Set highlight on current page
        widget._graphics_view.set_highlight(0x1000)

        assert widget._graphics_view._highlight_offset == 0x1000
        assert widget._graphics_view._highlight_rect is not None

    def test_set_highlight_none_clears_rect(self, qtbot, sample_rom_data: bytes) -> None:
        """Test that setting highlight to None clears it."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Wait for page render to complete
        qtbot.waitUntil(lambda: widget._graphics_view._pixmap_item is not None, timeout=5000)

        # Set then clear highlight
        widget._graphics_view.set_highlight(0x1000)
        assert widget._graphics_view._highlight_rect is not None

        widget._graphics_view.set_highlight(None)
        assert widget._graphics_view._highlight_rect is None
        assert widget._graphics_view._highlight_offset is None

    def test_goto_offset_sets_highlight(self, qtbot, sample_rom_data: bytes) -> None:
        """Test that go-to-offset sets the highlight."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Use go-to-offset input
        widget._offset_input.setText("0x1000")
        widget._on_goto_offset()

        assert widget._graphics_view._highlight_offset == 0x1000

    def test_tile_click_clears_highlight(self, qtbot, sample_rom_data: bytes) -> None:
        """Test that clicking a tile clears the highlight."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Set highlight
        widget._graphics_view.set_highlight(0x1000)
        assert widget._graphics_view._highlight_offset is not None

        # Simulate tile click
        widget._on_tile_clicked(0x2000)

        assert widget._graphics_view._highlight_offset is None
