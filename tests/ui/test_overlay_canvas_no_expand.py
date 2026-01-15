"""
Regression tests for overlay application and canvas dimensions.
"""

from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition


@pytest.fixture
def test_sprite(tmp_path):
    """Create a 16x16 sprite (4 tiles: 0,0; 0,1; 1,0; 1,1)."""
    img = Image.new("L", (16, 16), 0)
    # Put unique values in each tile
    # Tile (0,0) = 10, (0,1) = 20, (1,0) = 30, (1,1) = 40
    data = np.array(img)
    data[0:8, 0:8] = 10
    data[0:8, 8:16] = 20
    data[8:16, 0:8] = 30
    data[8:16, 8:16] = 40
    img = Image.fromarray(data, mode="L")
    path = tmp_path / "test_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def test_overlay(tmp_path):
    """Create a 16x16 red overlay."""
    img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
    path = tmp_path / "test_overlay.png"
    img.save(path)
    return str(path)


class TestOverlayCanvasFixes:
    def test_no_duplication_when_moving_tiles(self, qtbot, test_sprite):
        """
        Verify that physical_to_logical does NOT duplicate tiles.
        If tile (0,0) is moved to (0,2), its original spot (0,0) should be EMPTY (0).
        """
        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        # Move tile (0,0) to logical (0,2)
        dialog.arrangement_manager.set_item_at(0, 2, ArrangementType.TILE, "0,0")

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        # Logical size should be at least 3 tiles wide (24px) to accommodate (0,2)
        # and at least 2 tiles wide (16px) and 2 tiles high (16px) to accommodate physical
        # So 24x16
        w, h = bridge.logical_size
        assert w == 24
        assert h == 16

        # Transform
        input_array = np.zeros((16, 16), dtype=np.uint8)
        input_array[0:8, 0:8] = 10  # Tile (0,0)

        output_array = bridge.physical_to_logical(input_array)

        # Tile (0,0) in output should be 0 (moved!)
        assert np.all(output_array[0:8, 0:8] == 0), "Tile (0,0) was duplicated at its original position!"

        # Tile (0,2) in output (x=16..24) should be 10
        assert np.all(output_array[0:8, 16:24] == 10), "Tile (0,0) was not moved to (0,2)!"

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_keep_layout_false_preserves_physical_canvas(
        self, mock_info, mock_warning, qtbot, test_sprite, test_overlay
    ):
        """
        This tests the workflow level (simulated) where keep_arrangement=False
        means we should revert to physical layout.
        """
        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        # 1. Arrange tiles arbitrarily
        dialog.arrangement_manager.set_item_at(5, 5, ArrangementType.TILE, "0,0")

        # 2. Uncheck "Keep layout"
        dialog.keep_layout_check.setChecked(False)

        # 3. Apply overlay
        dialog.overlay_layer.import_image(test_overlay)
        dialog._apply_overlay()
        # Process events to handle the deferred QMessageBox
        qtbot.wait(10)

        # 4. Get result
        result = dialog.get_arrangement_result()
        assert result is not None
        assert result.keep_arrangement is False

        # In ROMWorkflowController logic, keep_arrangement=False leads to _clear_arrangement()
        # which means open_in_editor uses current_width/height (physical).

        # Verify bridge still correctly maps back to physical if we were to use it
        # (though the controller will discard it)
        bridge = result.bridge
        input_data = np.zeros((48, 48), dtype=np.uint8)  # large logical canvas
        input_data[40:48, 40:48] = 255  # logical (5,5) which is physical (0,0)

        phys = bridge.logical_to_physical(input_data)
        assert phys.shape == (16, 16)
        assert np.all(phys[0:8, 0:8] == 255), "Mapping back to physical failed"

    def test_canvas_not_shrinking_if_arrangement_is_small(self, qtbot, test_sprite):
        """
        Verify that if we arrange only 1 tile at (0,0), the canvas remains 16x16
        (the physical size) rather than shrinking to 8x8.
        """
        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        # Arrange only 1 tile at (0,0)
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        # Should be 16x16 (physical size), not 8x8 (arrangement size)
        w, h = bridge.logical_size
        assert w == 16
        assert h == 16

    def test_intentional_expansion_works(self, qtbot, test_sprite):
        """
        Verify that we can still expand the canvas if we want to.
        If we place a tile at (10, 10), the canvas should grow.
        """
        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        # Place tile at logical (10, 10)
        dialog.arrangement_manager.set_item_at(10, 10, ArrangementType.TILE, "0,0")

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        w, h = bridge.logical_size
        # tile at col 10 means at least 11 columns (88px)
        # tile at row 10 means at least 11 rows (88px)
        assert w == 88
        assert h == 88


class TestCheckboxDefaults:
    """Tests for Bug 1: Canvas Expansion due to checkbox default."""

    def test_keep_layout_checkbox_defaults_to_unchecked(self, qtbot, test_sprite):
        """Verify keep_layout_check is unchecked by default.

        When the checkbox defaults to unchecked, users who only want to apply
        overlay pixel changes won't accidentally get canvas expansion from
        the arrangement grid layout.
        """
        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        # CRITICAL: Checkbox should be unchecked by default
        assert hasattr(dialog, "keep_layout_check"), "Dialog should have keep_layout_check"
        assert dialog.keep_layout_check.isChecked() is False, (
            "keep_layout_check should default to unchecked. "
            "When checked, arrangement grid dimensions leak to sprite editor canvas."
        )

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_overlay_apply_without_keep_layout_returns_false(
        self, mock_info, mock_warning, qtbot, test_sprite, test_overlay
    ):
        """Result should have keep_arrangement=False when checkbox is unchecked (default)."""
        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        # Place tiles
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

        # Apply overlay
        dialog.overlay_layer.import_image(test_overlay)
        dialog._apply_overlay()
        # Process events to handle the deferred QMessageBox
        qtbot.wait(10)

        # Get result WITHOUT checking keep_layout (defaults to unchecked)
        result = dialog.get_arrangement_result()
        assert result is not None

        # With keep_arrangement=False, controller won't apply layout transformation
        assert result.keep_arrangement is False, "keep_arrangement should be False when checkbox is unchecked"

        # modified_tiles should still be present (pixel data changed)
        assert result.modified_tiles is not None, "modified_tiles should be present even when keep_arrangement=False"


class TestDelayedVisualFeedback:
    """Tests for Bug 2: Overlay not immediately applied."""

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_apply_overlay_modifies_tiles_immediately(self, mock_info, mock_warning, qtbot, test_sprite, test_overlay):
        """Tiles should be updated before success message is shown.

        This verifies that the tile data is actually modified immediately
        after _apply_overlay() returns, regardless of any blocking dialog.
        """
        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        # Place tile and apply overlay
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
        dialog.overlay_layer.import_image(test_overlay)
        dialog.overlay_layer.set_position(0, 0)

        # Get original pixel value
        original_tile = dialog.tiles[TilePosition(0, 0)]
        original_pixel = original_tile.getpixel((0, 0))

        # Apply overlay
        dialog._apply_overlay()

        # Tile should be modified IMMEDIATELY after apply
        # (tiles are updated synchronously, message box is deferred)
        modified_tile = dialog.tiles[TilePosition(0, 0)]
        modified_pixel = modified_tile.getpixel((0, 0))

        assert modified_pixel != original_pixel, (
            f"Tile pixel should have changed after apply. Original={original_pixel}, After={modified_pixel}"
        )

        # Process events to handle the deferred QMessageBox (cleanup)
        qtbot.wait(10)

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_arrangement_canvas_shows_modified_tiles_after_apply(
        self, mock_info, mock_warning, qtbot, test_sprite, test_overlay
    ):
        """Arrangement canvas should display the modified tiles after overlay apply.

        BUG: When applying overlay with palette mode enabled, the colorizer cache
        was cleared AFTER _update_displays() ran, causing stale (cached) tile
        images to be shown in the arrangement grid instead of the modified tiles.
        """
        from PySide6.QtWidgets import QGraphicsPixmapItem

        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        # Enable palette mode with a simple grayscale palette
        palette = [(i, i, i) for i in range(0, 256, 16)]  # 16 grayscale colors
        dialog.colorizer.set_palettes({0: palette})
        dialog.colorizer.set_selected_palette(0)
        dialog.colorizer.toggle_palette_mode()  # Actually enable palette mode

        # Place tile (0,0) at position (0,0) on arrangement canvas
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

        # Apply overlay - this modifies the tile pixel data
        dialog.overlay_layer.import_image(test_overlay)
        dialog.overlay_layer.set_position(0, 0)
        dialog._apply_overlay()
        qtbot.wait(10)  # Process deferred QMessageBox

        # Get the pixmap items from the arrangement scene
        scene_items = [item for item in dialog.arrangement_scene.items() if isinstance(item, QGraphicsPixmapItem)]

        # Should have at least one pixmap item (the placed tile)
        assert len(scene_items) >= 1, "Expected at least one pixmap item in scene"

        # Find the pixmap at position (0, 0) - this is the tile we placed
        tile_pixmap = None
        for item in scene_items:
            if item.pos().x() == 0 and item.pos().y() == 0:
                tile_pixmap = item.pixmap()
                break

        assert tile_pixmap is not None, "Could not find tile pixmap at (0,0)"

        # Convert pixmap to image to check pixel values
        qimage = tile_pixmap.toImage()
        # Get pixel at (0,0) of the tile
        pixel_color = qimage.pixelColor(0, 0)

        # After applying red overlay, the tile should NOT have the original value (10)
        # The overlay is red (255, 0, 0) which when quantized to grayscale palette
        # should result in a different value than the original grayscale 10
        # Original tile had value 10 (very dark gray)
        # Red (255, 0, 0) has luminance ~76, so should quantize to lighter gray

        # The key assertion: the displayed pixel should NOT match the original (dark) value
        # If the bug exists, we'd see the cached original tile (dark gray)
        # If fixed, we'd see the modified tile (lighter gray from red overlay)
        assert pixel_color.red() > 50, (
            f"Tile in arrangement canvas should show modified pixels. "
            f"Got color ({pixel_color.red()}, {pixel_color.green()}, {pixel_color.blue()}), "
            f"expected brighter value after red overlay was applied."
        )
