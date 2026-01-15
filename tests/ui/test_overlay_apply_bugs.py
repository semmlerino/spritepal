"""
Tests for overlay apply bugs:
1. Dialog accept() not setting _arrangement_result
2. PaletteColorizer cache not invalidated after Apply
"""

from unittest.mock import patch

import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import TilePosition


@pytest.fixture
def simple_sprite(tmp_path):
    """Create a simple 16x16 sprite sheet (4 tiles of 8x8, all black)."""
    img = Image.new("L", (16, 16), 0)  # All black (index 0)
    path = tmp_path / "simple_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def white_overlay(tmp_path):
    """Create a 16x16 white overlay image."""
    img = Image.new("RGBA", (16, 16), (255, 255, 255, 255))  # All white
    path = tmp_path / "white_overlay.png"
    img.save(path)
    return str(path)


@pytest.fixture
def sample_palette():
    """Create a simple 16-color palette for testing."""
    # Simple grayscale palette
    return [(i * 16, i * 16, i * 16) for i in range(16)]


class TestAcceptPathBug:
    """Tests for Bug 1: Dialog accept() not setting _arrangement_result."""

    def test_arrangement_result_none_before_accept(self, qtbot, simple_sprite):
        """arrangement_result should be None before accept is called."""
        dialog = GridArrangementDialog(simple_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        # Before accept, result should be None
        assert dialog.arrangement_result is None

        dialog.close()

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_arrangement_result_set_after_direct_accept(
        self, mock_info, mock_warning, qapp, simple_sprite, white_overlay
    ):
        """arrangement_result should be set when accept() is called directly.

        This simulates clicking the OK button (which calls accept() directly).
        Currently this fails because accept() doesn't set _arrangement_result.
        """
        # Don't use qtbot.addWidget since accept() will close and delete the dialog
        dialog = GridArrangementDialog(simple_sprite, tiles_per_row=2)
        dialog.show()

        # Place a tile on the canvas (required for arrangement)
        pos = TilePosition(0, 0)
        dialog.arrangement_manager.add_tile(pos)

        # Import overlay and apply
        dialog.overlay_layer.import_image(white_overlay, 16, 16)
        dialog._apply_overlay()

        # Verify Apply succeeded (using public property)
        assert dialog.apply_result is not None
        assert dialog.apply_result.success

        # Now simulate clicking OK button (calls accept directly)
        dialog.accept()

        # CRITICAL: arrangement_result should be set!
        # This currently fails because accept() doesn't set it
        assert dialog.arrangement_result is not None, (
            "arrangement_result is None after accept()! "
            "This means changes will be discarded when dialog closes via OK button."
        )
        assert dialog.arrangement_result.modified_tiles is not None

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_modified_tiles_preserved_through_accept(self, mock_info, mock_warning, qapp, simple_sprite, white_overlay):
        """Modified tiles should be accessible after accept().

        When user clicks Apply and then OK, the modified tile data must
        be available through arrangement_result.
        """
        # Don't use qtbot.addWidget since accept() will close and delete the dialog
        dialog = GridArrangementDialog(simple_sprite, tiles_per_row=2)
        dialog.show()

        # Add tile and apply overlay
        pos = TilePosition(0, 0)
        dialog.arrangement_manager.add_tile(pos)
        dialog.overlay_layer.import_image(white_overlay, 16, 16)
        dialog._apply_overlay()

        # Get the modified tile data before accept
        pre_accept_tiles = dialog.tiles.copy()
        assert pos in pre_accept_tiles

        # Call accept
        dialog.accept()

        # Verify modified_tiles matches what was in self.tiles
        result = dialog.arrangement_result
        assert result is not None
        assert result.modified_tiles is not None
        assert pos in result.modified_tiles


class TestPaletteCacheBug:
    """Tests for Bug 2: PaletteColorizer cache not invalidated after Apply."""

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_colorizer_cache_cleared_during_apply(
        self, mock_info, mock_warning, qtbot, simple_sprite, white_overlay, sample_palette
    ):
        """Colorizer cache should be cleared when overlay is applied.

        Otherwise the display shows old tile images even after Apply modifies them.
        The cache is cleared BEFORE _update_displays() runs, which then repopulates
        it with the new tile images. This ensures stale cached images aren't used.
        """
        dialog = GridArrangementDialog(simple_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        # Enable palette mode
        dialog.colorizer.set_palettes({8: sample_palette})
        dialog.colorizer.toggle_palette_mode()  # Turn on palette mode
        assert dialog.colorizer.is_palette_mode()

        # Add tile to arrangement
        pos = TilePosition(0, 0)
        dialog.arrangement_manager.add_tile(pos)

        # Get original tile image
        original_tile = dialog.tiles.get(pos)
        assert original_tile is not None

        # Get display image (this populates the cache)
        tile_index = pos.row * dialog.processor.grid_cols + pos.col + 1000
        _ = dialog.colorizer.get_display_image(tile_index, original_tile)

        # Verify cache is populated
        cache_stats_before = dialog.colorizer.get_cache_stats()
        assert cache_stats_before["size"] > 0, "Cache should be populated after get_display_image"

        # Wrap clear_cache to track calls
        original_clear_cache = dialog.colorizer.clear_cache
        clear_cache_called = []

        def tracked_clear_cache() -> None:
            clear_cache_called.append(True)
            original_clear_cache()

        dialog.colorizer.clear_cache = tracked_clear_cache  # type: ignore[method-assign]

        # Apply overlay (modifies tiles)
        dialog.overlay_layer.import_image(white_overlay, 16, 16)
        dialog._apply_overlay()

        # CRITICAL: clear_cache() must be called during Apply
        # This ensures stale cached images are invalidated before _update_displays() runs
        assert len(clear_cache_called) > 0, (
            "clear_cache() was not called during _apply_overlay()! "
            "This causes the display to show old tiles instead of modified ones."
        )
        # qtbot handles dialog cleanup - don't call dialog.close()
