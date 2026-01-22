"""
Tests for PagedTileViewWidget.

Tests the main tile grid widget with navigation and display.
These tests verify behavior through public APIs and observable state.
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
    """Test the TileGridGraphicsView observable behaviors."""

    def test_set_image(self, qtbot) -> None:
        """Test setting an image in the view."""
        view = TileGridGraphicsView()
        qtbot.addWidget(view)

        image = QImage(400, 400, QImage.Format.Format_RGBA8888)
        image.fill(0xFF0000FF)

        # Initially no image
        assert not view.has_image()

        view.set_image(image)

        # After setting, image should be present
        assert view.has_image()
        # Scene should have content (not empty)
        assert not view.sceneRect().isEmpty()

    def test_clear_image(self, qtbot) -> None:
        """Test clearing the image."""
        view = TileGridGraphicsView()
        qtbot.addWidget(view)

        image = QImage(100, 100, QImage.Format.Format_RGBA8888)
        image.fill(0xFF0000FF)
        view.set_image(image)
        assert view.has_image()

        view.clear_image()

        # Image should be cleared
        assert not view.has_image()


class TestPagedTileViewWidget:
    """Test the PagedTileViewWidget observable behaviors."""

    @pytest.fixture
    def sample_rom_data(self) -> bytes:
        """Create sample ROM data for testing."""
        # Create data for multiple pages
        # Default 50x50 = 2500 tiles * 32 bytes = 80000 bytes per page
        # Create 3 pages worth
        return bytes(range(256)) * 1000  # 256000 bytes

    def test_set_rom_data(self, qtbot, sample_rom_data: bytes) -> None:
        """Test setting ROM data enables navigation for multi-page ROM."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        widget.set_rom_data(sample_rom_data)

        # Multi-page ROM: next should be enabled, prev disabled (first page)
        assert widget.can_go_next()
        assert not widget.can_go_prev()
        # Current offset starts at 0
        assert widget.get_current_offset() == 0

    def test_set_palette(self, qtbot, sample_rom_data: bytes) -> None:
        """Test setting palette enables palette checkbox."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Initially no palette - checkbox disabled
        widget.set_palette(None)
        assert not widget._palette_checkbox.isEnabled()

        # Set palette - checkbox becomes enabled
        palette = [[255, 0, 0]] + [[i * 16, i * 16, i * 16] for i in range(1, 16)]
        widget.set_palette(palette)
        assert widget._palette_checkbox.isEnabled()

    def test_set_grid_dimensions(self, qtbot, sample_rom_data: bytes) -> None:
        """Test changing grid dimensions updates navigation."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Change to smaller grid (20x20 vs default 50x50)
        # This creates more pages from same data
        widget.set_grid_dimensions(20, 20)

        # Should still be on first page with navigation available
        assert widget.get_current_offset() == 0
        assert widget.can_go_next()

    def test_go_to_page(self, qtbot, sample_rom_data: bytes) -> None:
        """Test navigating to a specific page emits signal and updates offset."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        page_signals: list[int] = []
        widget.page_changed.connect(page_signals.append)

        # Navigate to page 1 (multi-page ROM should have page 1)
        widget.go_to_page(1)

        # Signal should be emitted
        assert len(page_signals) == 1
        assert page_signals[0] == 1
        # Offset should have advanced
        assert widget.get_current_offset() > 0
        # Prev should now be possible
        assert widget.can_go_prev()

    def test_go_to_offset(self, qtbot, sample_rom_data: bytes) -> None:
        """Test navigating to a specific offset updates navigation."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Navigate to an offset in the second page (256KB ROM, 80KB per page)
        target_offset = 100000  # ~100KB, past first page

        widget.go_to_offset(target_offset)

        # Should be past first page, so prev should be enabled
        assert widget.can_go_prev()
        # Current offset should be page-aligned to target's page
        assert widget.get_current_offset() > 0

    def test_get_current_offset(self, qtbot, sample_rom_data: bytes) -> None:
        """Test getting current page offset."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        assert widget.get_current_offset() == 0

        total_pages = widget._total_pages
        if total_pages > 1:
            widget.go_to_page(1)
            bytes_per_page = widget._cols * widget._rows * BYTES_PER_TILE
            assert widget.get_current_offset() == bytes_per_page

    def test_navigation_buttons_state(self, qtbot, sample_rom_data: bytes) -> None:
        """Test navigation button enable/disable state via public API."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)

        # Load ROM data
        widget.set_rom_data(sample_rom_data)

        # On first page, prev should not be possible
        assert not widget.can_go_prev()

        # Next should be possible if multiple pages
        total_pages = widget._total_pages
        if total_pages > 1:
            assert widget.can_go_next()

            # Navigate to last page
            widget.go_to_page(total_pages - 1)

            # Next should not be possible on last page
            assert not widget.can_go_next()
            # Prev should be possible
            assert widget.can_go_prev()

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

    def test_grid_preset_change(self, qtbot, sample_rom_data: bytes) -> None:
        """Test changing grid size via combo box updates navigation."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Change to small grid preset (index 0)
        widget._grid_combo.setCurrentIndex(0)

        # Combo should show selected preset
        assert widget._grid_combo.currentIndex() == 0
        # Navigation should still work
        assert widget.can_go_next()

    def test_goto_offset_hex_with_prefix(self, qtbot, sample_rom_data: bytes) -> None:
        """Test go-to-offset with 0x hex prefix navigates correctly."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Navigate to offset past first page (100KB)
        widget._offset_input.setText("0x18000")
        widget._on_goto_offset()

        # Should be past first page, prev enabled
        assert widget.can_go_prev()
        assert widget.get_current_offset() > 0

    def test_goto_offset_hex_without_prefix(self, qtbot, sample_rom_data: bytes) -> None:
        """Test go-to-offset with plain hex navigates correctly."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Navigate to offset past first page (100KB = 0x18000)
        widget._offset_input.setText("18000")
        widget._on_goto_offset()

        # Should be past first page, prev enabled
        assert widget.can_go_prev()
        assert widget.get_current_offset() > 0

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
        """Test that setting a highlight stores the offset."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Wait for page render to complete
        qtbot.waitUntil(lambda: widget._graphics_view.has_image(), timeout=5000)

        # Set highlight on current page
        widget._graphics_view.set_highlight(0x1000)

        # Verify highlight offset is stored via public API
        assert widget._graphics_view.get_highlight_offset() == 0x1000

    def test_set_highlight_none_clears_rect(self, qtbot, sample_rom_data: bytes) -> None:
        """Test that setting highlight to None clears it."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Wait for page render to complete
        qtbot.waitUntil(lambda: widget._graphics_view.has_image(), timeout=5000)

        # Set then clear highlight
        widget._graphics_view.set_highlight(0x1000)
        assert widget._graphics_view.get_highlight_offset() is not None

        widget._graphics_view.set_highlight(None)
        assert widget._graphics_view.get_highlight_offset() is None

    def test_goto_offset_sets_highlight(self, qtbot, sample_rom_data: bytes) -> None:
        """Test that go-to-offset sets the highlight."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Use go-to-offset input
        widget._offset_input.setText("0x1000")
        widget._on_goto_offset()

        assert widget._graphics_view.get_highlight_offset() == 0x1000

    def test_tile_click_clears_highlight(self, qtbot, sample_rom_data: bytes) -> None:
        """Test that clicking a tile clears the highlight."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        widget.set_rom_data(sample_rom_data)

        # Set highlight
        widget._graphics_view.set_highlight(0x1000)
        assert widget._graphics_view.get_highlight_offset() is not None

        # Simulate tile click
        widget._on_tile_clicked(0x2000)

        assert widget._graphics_view.get_highlight_offset() is None
