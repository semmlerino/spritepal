"""
Tests for PagedTileViewWidget.

Tests the main tile grid widget with navigation and display.
These tests verify behavior through public APIs and observable state.
"""

from __future__ import annotations

from collections.abc import Generator

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

    @pytest.fixture
    def widget(self, qtbot) -> Generator[PagedTileViewWidget, None, None]:
        """Fixture to provide a widget instance with automatic cleanup."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        yield widget
        widget.cleanup()

    def test_set_rom_data(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test setting ROM data enables navigation for multi-page ROM."""
        widget.set_rom_data(sample_rom_data)

        # Multi-page ROM: next should be enabled, prev disabled (first page)
        assert widget.can_go_next()
        assert not widget.can_go_prev()
        # Current offset starts at 0
        assert widget.get_current_offset() == 0

    def test_set_palette(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test setting palette enables palette checkbox."""
        widget.set_rom_data(sample_rom_data)

        # Initially no palette - checkbox disabled
        widget.set_palette(None)
        assert not widget.is_palette_checkbox_enabled()

        # Set palette - checkbox becomes enabled
        palette = [[255, 0, 0]] + [[i * 16, i * 16, i * 16] for i in range(1, 16)]
        widget.set_palette(palette)
        assert widget.is_palette_checkbox_enabled()

    def test_set_grid_dimensions(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test changing grid dimensions updates navigation."""
        widget.set_rom_data(sample_rom_data)

        # Change to smaller grid (20x20 vs default 50x50)
        # This creates more pages from same data
        widget.set_grid_dimensions(20, 20)

        # Should still be on first page with navigation available
        assert widget.get_current_offset() == 0
        assert widget.can_go_next()

    def test_go_to_page(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test navigating to a specific page emits signal and updates offset."""
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

    def test_go_to_offset(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test navigating to a specific offset updates navigation."""
        widget.set_rom_data(sample_rom_data)

        # Navigate to an offset in the second page (256KB ROM, 80KB per page)
        target_offset = 100000  # ~100KB, past first page

        widget.go_to_offset(target_offset)

        # Should be past first page, so prev should be enabled
        assert widget.can_go_prev()
        # Current offset should be page-aligned to target's page
        assert widget.get_current_offset() > 0

    def test_get_current_offset(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test getting current page offset."""
        widget.set_rom_data(sample_rom_data)

        assert widget.get_current_offset() == 0

        total_pages = widget.total_page_count()
        if total_pages > 1:
            widget.go_to_page(1)
            cols, rows = widget.get_grid_dimensions()
            bytes_per_page = cols * rows * BYTES_PER_TILE
            assert widget.get_current_offset() == bytes_per_page

    def test_navigation_buttons_state(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test navigation button enable/disable state via public API."""
        # Load ROM data
        widget.set_rom_data(sample_rom_data)

        # On first page, prev should not be possible
        assert not widget.can_go_prev()

        # Next should be possible if multiple pages
        total_pages = widget.total_page_count()
        if total_pages > 1:
            assert widget.can_go_next()

            # Navigate to last page
            widget.go_to_page(total_pages - 1)

            # Next should not be possible on last page
            assert not widget.can_go_next()
            # Prev should be possible
            assert widget.can_go_prev()

    def test_tile_clicked_signal(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test tile_clicked signal emission."""
        widget.set_rom_data(sample_rom_data)

        offsets: list[int] = []
        widget.tile_clicked.connect(offsets.append)

        # Simulate click through public emit method
        # Click at tile (5, 5) on page 0
        cols, _ = widget.get_grid_dimensions()
        tile_index = 5 * cols + 5
        expected_offset = tile_index * BYTES_PER_TILE
        widget.emit_tile_clicked(expected_offset)

        assert len(offsets) == 1
        assert offsets[0] == expected_offset

    def test_grid_preset_change(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test changing grid size via combo box updates navigation."""
        widget.set_rom_data(sample_rom_data)

        # Change to small grid preset (index 0)
        widget.set_grid_preset_index(0)

        # Combo should show selected preset
        assert widget.get_grid_preset_index() == 0
        # Navigation should still work
        assert widget.can_go_next()

    def test_goto_offset_hex_with_prefix(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test go-to-offset with 0x hex prefix navigates correctly."""
        widget.set_rom_data(sample_rom_data)

        # Navigate to offset past first page (100KB)
        widget.navigate_to_offset_text("0x18000")

        # Should be past first page, prev enabled
        assert widget.can_go_prev()
        assert widget.get_current_offset() > 0

    def test_goto_offset_hex_without_prefix(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test go-to-offset with plain hex navigates correctly."""
        widget.set_rom_data(sample_rom_data)

        # Navigate to offset past first page (100KB = 0x18000)
        widget.navigate_to_offset_text("18000")

        # Should be past first page, prev enabled
        assert widget.can_go_prev()
        assert widget.get_current_offset() > 0

    def test_goto_offset_clears_input(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test that go-to-offset clears the input field after success."""
        widget.set_rom_data(sample_rom_data)

        widget.navigate_to_offset_text("0x1000")

        assert widget.get_offset_input_text() == ""

    def test_goto_offset_invalid_format(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test go-to-offset with invalid format shows error."""
        widget.set_rom_data(sample_rom_data)

        widget.navigate_to_offset_text("not_a_number")

        assert "Invalid offset format" in widget.get_status_text()

    def test_goto_offset_exceeds_rom(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test go-to-offset with offset beyond ROM size shows error."""
        widget.set_rom_data(sample_rom_data)

        # Try offset way beyond ROM size
        widget.navigate_to_offset_text("0xFFFFFFFF")

        assert "exceeds ROM size" in widget.get_status_text()

    def test_palette_checkbox_default_state(self, widget: PagedTileViewWidget) -> None:
        """Test palette checkbox is checked by default."""
        assert widget.is_palette_checked()
        assert widget.is_palette_enabled()

    def test_palette_toggle_disables_palette(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test unchecking palette checkbox disables palette rendering."""
        widget.set_rom_data(sample_rom_data)

        # Set a palette
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        widget.set_palette(palette)
        assert widget.is_palette_enabled()

        # Uncheck the palette checkbox
        widget.set_palette_checked(False)

        assert not widget.is_palette_enabled()

    def test_palette_toggle_enables_palette(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test checking palette checkbox enables palette rendering."""
        widget.set_rom_data(sample_rom_data)

        # Set a palette and disable it
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        widget.set_palette(palette)
        widget.set_palette_checked(False)
        assert not widget.is_palette_enabled()

        # Re-check the palette checkbox
        widget.set_palette_checked(True)

        assert widget.is_palette_enabled()

    def test_palette_checkbox_disabled_when_no_palette(self, widget: PagedTileViewWidget) -> None:
        """Test palette checkbox is disabled when no palette is set."""
        # Set palette to None
        widget.set_palette(None)

        assert not widget.is_palette_checkbox_enabled()
        assert not widget.is_palette_checked()

    def test_palette_checkbox_enabled_when_palette_set(self, widget: PagedTileViewWidget) -> None:
        """Test palette checkbox is enabled when a palette is set."""
        # First set to None to disable
        widget.set_palette(None)
        assert not widget.is_palette_checkbox_enabled()

        # Now set a real palette
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        widget.set_palette(palette)

        # Checkbox should be enabled (but may not be checked due to previous None)
        assert widget.is_palette_checkbox_enabled()

    def test_palette_dropdown_default_has_grayscale(self, widget: PagedTileViewWidget) -> None:
        """Test palette dropdown has Grayscale option by default."""
        assert widget.palette_count() == 1
        assert widget.get_palette_names()[0] == "Grayscale"

    def test_add_palette_option(self, widget: PagedTileViewWidget) -> None:
        """Test adding a palette option to the dropdown."""
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        widget.add_palette_option("Test Palette", palette)

        assert widget.palette_count() == 2
        assert widget.get_palette_names()[1] == "Test Palette"
        assert widget.has_palette_option("Test Palette")

    def test_set_palette_with_name(self, widget: PagedTileViewWidget) -> None:
        """Test setting palette with a custom name."""
        palette = [[255, 0, 0]] + [[i * 16, i * 16, i * 16] for i in range(1, 16)]
        widget.set_palette(palette, name="Red Palette")

        assert widget.get_selected_palette_name() == "Red Palette"
        assert widget.get_palette() == palette

    def test_select_palette_by_name(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test selecting a palette by name."""
        widget.set_rom_data(sample_rom_data)

        # Add two palettes
        palette1 = [[255, 0, 0] for _ in range(16)]
        palette2 = [[0, 255, 0] for _ in range(16)]
        widget.add_palette_option("Red", palette1)
        widget.add_palette_option("Green", palette2)

        # Select Green
        result = widget.select_palette("Green")
        assert result is True
        assert widget.get_selected_palette_name() == "Green"

    def test_select_nonexistent_palette(self, widget: PagedTileViewWidget) -> None:
        """Test selecting a palette that doesn't exist."""
        result = widget.select_palette("Nonexistent")
        assert result is False

    def test_clear_palette_options(self, widget: PagedTileViewWidget) -> None:
        """Test clearing all palette options."""
        # Add some palettes
        palette1 = [[255, 0, 0] for _ in range(16)]
        palette2 = [[0, 255, 0] for _ in range(16)]
        widget.add_palette_option("Red", palette1)
        widget.add_palette_option("Green", palette2)
        assert widget.palette_count() == 3

        # Clear all
        widget.clear_palette_options()

        assert widget.palette_count() == 1
        assert widget.get_palette_names()[0] == "Grayscale"
        assert widget.get_selected_palette_name() == "Grayscale"
        assert widget.get_palette() is None

    def test_palette_selection_updates_state(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test that selecting a palette updates checkbox and internal state."""
        widget.set_rom_data(sample_rom_data)

        # Add a palette and select it
        palette = [[255, 0, 0] for _ in range(16)]
        widget.add_palette_option("Red", palette)
        widget.select_palette("Red")

        # Checkbox should be enabled and checked
        assert widget.is_palette_checkbox_enabled()
        assert widget.is_palette_checked()
        assert widget.is_palette_enabled()

        # Now select Grayscale
        widget.select_palette("Grayscale")

        # Checkbox should be disabled and unchecked
        assert not widget.is_palette_checkbox_enabled()
        assert not widget.is_palette_checked()
        assert not widget.is_palette_enabled()

    def test_user_palette_tracking(self, widget: PagedTileViewWidget) -> None:
        """Test that user palettes are tracked separately from built-in ones."""
        # Add built-in palette (default behavior)
        palette1 = [[255, 0, 0] for _ in range(16)]
        widget.add_palette_option("Built-in", palette1)
        assert not widget.is_user_palette("Built-in")

        # Add user palette
        palette2 = [[0, 255, 0] for _ in range(16)]
        widget.add_palette_option("User Palette", palette2, is_user_palette=True)
        assert widget.is_user_palette("User Palette")

    def test_get_user_palettes(self, widget: PagedTileViewWidget) -> None:
        """Test retrieving user palettes for persistence."""
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

    def test_load_user_palettes(self, widget: PagedTileViewWidget) -> None:
        """Test loading user palettes from saved data."""
        palette1 = [[255, 0, 0] for _ in range(16)]
        palette2 = [[0, 255, 0] for _ in range(16)]

        saved_palettes = {
            "Saved1": palette1,
            "Saved2": palette2,
        }

        widget.load_user_palettes(saved_palettes)

        assert widget.has_palette_option("Saved1")
        assert widget.has_palette_option("Saved2")
        assert widget.is_user_palette("Saved1")
        assert widget.is_user_palette("Saved2")
        assert widget.palette_count() == 3  # Grayscale + 2 loaded

    def test_clear_palette_options_clears_user_palettes(self, widget: PagedTileViewWidget) -> None:
        """Test that clear_palette_options also clears user palette tracking."""
        # Add user palette
        palette = [[255, 0, 0] for _ in range(16)]
        widget.add_palette_option("User Palette", palette, is_user_palette=True)
        assert widget.is_user_palette("User Palette")

        widget.clear_palette_options()

        # After clear, no user palettes should remain
        assert widget.get_user_palettes() == {}

    def test_palette_menu_actions_exist(self, widget: PagedTileViewWidget) -> None:
        """Test that palette management actions are functional."""
        # Can query rename/delete state (functionality verified via these APIs)
        # For built-in Grayscale, should not be able to rename/delete
        assert not widget.can_rename_selected_palette()
        assert not widget.can_delete_selected_palette()

    def test_rename_delete_disabled_for_builtin(self, widget: PagedTileViewWidget) -> None:
        """Test that rename/delete are disabled for built-in palettes."""
        # Grayscale is selected by default
        assert not widget.can_rename_selected_palette()
        assert not widget.can_delete_selected_palette()

    def test_rename_delete_enabled_for_user_palette(self, widget: PagedTileViewWidget) -> None:
        """Test that rename/delete are enabled for user palettes."""
        # Add and select user palette
        palette = [[255, 0, 0] for _ in range(16)]
        widget.add_palette_option("User Palette", palette, is_user_palette=True)
        widget.select_palette("User Palette")

        assert widget.can_rename_selected_palette()
        assert widget.can_delete_selected_palette()

    def test_load_palette_file_valid(self, widget: PagedTileViewWidget, tmp_path) -> None:
        """Test loading a valid palette file."""
        # Create a test palette file
        palette_data = {
            "name": "Test Palette",
            "colors": [[255, 0, 0], [0, 255, 0], [0, 0, 255]] + [[0, 0, 0] for _ in range(13)],
        }
        palette_file = tmp_path / "test.pal.json"
        palette_file.write_text(__import__("json").dumps(palette_data))

        result = widget.load_palette_file(palette_file)

        assert result is not None
        assert result["name"] == "Test Palette"
        assert len(result["colors"]) == 16
        assert result["colors"][0] == [255, 0, 0]

    def test_load_palette_file_missing_colors(self, widget: PagedTileViewWidget, tmp_path) -> None:
        """Test loading a palette file without colors field."""
        # Create an invalid palette file
        palette_data = {"name": "Invalid Palette"}
        palette_file = tmp_path / "invalid.pal.json"
        palette_file.write_text(__import__("json").dumps(palette_data))

        import pytest

        with pytest.raises(ValueError, match="Missing 'colors' field"):
            widget.load_palette_file(palette_file)

    def test_load_palette_file_uses_filename_if_no_name(self, widget: PagedTileViewWidget, tmp_path) -> None:
        """Test that palette name defaults to filename if not in file."""
        # Create a palette file without name
        palette_data = {
            "colors": [[255, 0, 0] for _ in range(16)],
        }
        palette_file = tmp_path / "my_custom_palette.pal.json"
        palette_file.write_text(__import__("json").dumps(palette_data))

        result = widget.load_palette_file(palette_file)

        assert result is not None
        assert result["name"] == "my_custom_palette.pal"  # Stem of filename


class TestTileGridHighlight:
    """Test the highlight feature for go-to-offset."""

    @pytest.fixture
    def sample_rom_data(self) -> bytes:
        """Create sample ROM data for testing."""
        return bytes(range(256)) * 1000  # 256000 bytes

    @pytest.fixture
    def widget(self, qtbot) -> Generator[PagedTileViewWidget, None, None]:
        """Fixture to provide a widget instance with automatic cleanup."""
        widget = PagedTileViewWidget()
        qtbot.addWidget(widget)
        yield widget
        widget.cleanup()

    def test_set_highlight_creates_rect(self, widget: PagedTileViewWidget, qtbot, sample_rom_data: bytes) -> None:
        """Test that setting a highlight stores the offset."""
        widget.set_rom_data(sample_rom_data)

        # Wait for page render to complete
        qtbot.waitUntil(lambda: widget.has_image(), timeout=5000)

        # Set highlight on current page
        widget.set_highlight(0x1000)

        # Verify highlight offset is stored via public API
        assert widget.get_highlight_offset() == 0x1000

    def test_set_highlight_none_clears_rect(self, widget: PagedTileViewWidget, qtbot, sample_rom_data: bytes) -> None:
        """Test that setting highlight to None clears it."""
        widget.set_rom_data(sample_rom_data)

        # Wait for page render to complete
        qtbot.waitUntil(lambda: widget.has_image(), timeout=5000)

        # Set then clear highlight
        widget.set_highlight(0x1000)
        assert widget.get_highlight_offset() is not None

        widget.set_highlight(None)
        assert widget.get_highlight_offset() is None

    def test_goto_offset_sets_highlight(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test that go-to-offset sets the highlight."""
        widget.set_rom_data(sample_rom_data)

        # Use go-to-offset via public API
        widget.navigate_to_offset_text("0x1000")

        assert widget.get_highlight_offset() == 0x1000

    def test_tile_click_clears_highlight(self, widget: PagedTileViewWidget, sample_rom_data: bytes) -> None:
        """Test that clicking a tile clears the highlight."""
        widget.set_rom_data(sample_rom_data)

        # Set highlight
        widget.set_highlight(0x1000)
        assert widget.get_highlight_offset() is not None

        # Simulate tile click via public handler
        widget.handle_tile_click(0x2000)

        assert widget.get_highlight_offset() is None
