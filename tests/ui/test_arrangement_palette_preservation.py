"""
Tests for palette preservation when only some tiles are modified via overlay.

REGRESSION: When overlay is applied to only SOME tiles:
- Modified tiles become L-mode with pixel values = palette_index * 16
- Unmodified tiles stay in P-mode (or L-mode with raw indices 0-15)
- If get_arrangement_result() returns ALL tiles, _update_tile_data_from_modified_tiles()
  corrupts unmodified tiles because it assumes L-mode encoding

FIX: Track which tiles were actually modified and only return those.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition


@pytest.fixture
def multi_tile_sprite(tmp_path):
    """Create a 4-tile sprite (32x8 px) with distinct palette indices.

    Each tile has a unique index pattern so we can verify preservation:
    - Tile (0,0): All pixels = index 1 (P-mode value 1)
    - Tile (0,1): All pixels = index 2
    - Tile (0,2): All pixels = index 3
    - Tile (0,3): All pixels = index 4
    """
    # Create P-mode image with 16-color palette
    img = Image.new("P", (32, 8))

    # Set up a simple grayscale palette
    palette = []
    for i in range(16):
        palette.extend([i * 16, i * 16, i * 16])
    palette.extend([0] * (256 - 16) * 3)  # Pad to 256 colors
    img.putpalette(palette)

    # Fill each 8x8 tile with a distinct palette index
    for tile_idx in range(4):
        x_start = tile_idx * 8
        index_value = tile_idx + 1  # Indices 1, 2, 3, 4
        for y in range(8):
            for x in range(x_start, x_start + 8):
                img.putpixel((x, y), index_value)

    path = tmp_path / "multi_tile_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def small_red_overlay(tmp_path):
    """Create a small 8x8 red overlay (covers exactly 1 tile)."""
    img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    path = tmp_path / "red_overlay.png"
    img.save(path)
    return str(path)


class TestPalettePreservationOnPartialOverlay:
    """Tests for palette preservation when overlay modifies only some tiles."""

    def test_get_arrangement_result_only_returns_actually_modified_tiles(
        self, qtbot, multi_tile_sprite, small_red_overlay
    ):
        """
        REGRESSION TEST: get_arrangement_result() must only return tiles that were
        actually modified by the overlay, not ALL tiles.

        Bug: After applying overlay to tile (0,0), get_arrangement_result() returns
        all 4 tiles. When _update_tile_data_from_modified_tiles() processes them,
        it assumes all are L-mode (index * 16), but unmodified tiles are P-mode,
        causing palette corruption.

        Fix: Track which positions were actually modified and only return those.
        """
        dialog = GridArrangementDialog(multi_tile_sprite, tiles_per_row=4)
        qtbot.addWidget(dialog)
        dialog.show()

        # Arrange only tiles (0,0) and (0,1) on canvas
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
        dialog.arrangement_manager.set_item_at(0, 1, ArrangementType.TILE, "0,1")

        # Import overlay at position (0, 0) - covers only tile (0,0)
        dialog.overlay_layer.import_image(small_red_overlay)
        dialog.overlay_layer.set_position(0, 0)

        # Apply overlay (should only modify tile at canvas position (0,0))
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog._apply_overlay()

        # Verify which tile was modified by the apply operation
        apply_result = dialog.apply_result
        assert apply_result is not None
        assert apply_result.success
        assert len(apply_result.modified_tiles) == 1, (
            f"Apply operation should modify exactly 1 tile, got {len(apply_result.modified_tiles)}"
        )
        assert TilePosition(0, 0) in apply_result.modified_tiles, "Tile (0,0) should be modified"

        # Now get the arrangement result
        result = dialog.get_arrangement_result()
        assert result is not None

        # THE BUG: modified_tiles contains ALL tiles, not just actually modified ones
        # THE FIX: modified_tiles should only contain tile (0,0)
        modified_tiles = result.modified_tiles
        assert modified_tiles is not None, "modified_tiles should not be None after apply"

        # Verify ONLY the actually modified tile is in the result
        assert len(modified_tiles) == 1, (
            f"modified_tiles should contain exactly 1 tile (the one modified by overlay), "
            f"but contains {len(modified_tiles)} tiles. "
            f"Keys: {list(modified_tiles.keys())}"
        )
        assert TilePosition(0, 0) in modified_tiles, "Only tile (0,0) should be in modified_tiles"
        assert TilePosition(0, 1) not in modified_tiles, (
            "Tile (0,1) was NOT modified by overlay, should NOT be in modified_tiles"
        )

    def test_multiple_apply_operations_accumulate_modified_positions(self, qtbot, multi_tile_sprite, small_red_overlay):
        """
        When overlay is applied multiple times, modified positions should accumulate.

        This tests the tracking mechanism: if user applies overlay at (0,0), then
        moves overlay and applies at (0,1), both positions should be tracked.
        """
        dialog = GridArrangementDialog(multi_tile_sprite, tiles_per_row=4)
        qtbot.addWidget(dialog)
        dialog.show()

        # Arrange all 4 tiles on canvas
        for col in range(4):
            dialog.arrangement_manager.set_item_at(0, col, ArrangementType.TILE, f"0,{col}")

        # First apply: overlay at (0, 0) - modifies tile (0,0)
        dialog.overlay_layer.import_image(small_red_overlay)
        dialog.overlay_layer.set_position(0, 0)

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog._apply_overlay()

        # Second apply: move overlay to (8, 0) - modifies tile (0,1)
        dialog.overlay_layer.set_visible(True)  # Re-show overlay
        dialog.overlay_layer.set_position(8, 0)

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog._apply_overlay()

        # Get arrangement result
        result = dialog.get_arrangement_result()
        assert result is not None

        modified_tiles = result.modified_tiles
        assert modified_tiles is not None

        # Both (0,0) and (0,1) should be tracked as modified
        assert len(modified_tiles) == 2, (
            f"Expected 2 modified tiles after two apply operations, got {len(modified_tiles)}"
        )
        assert TilePosition(0, 0) in modified_tiles
        assert TilePosition(0, 1) in modified_tiles
        assert TilePosition(0, 2) not in modified_tiles
        assert TilePosition(0, 3) not in modified_tiles

    def test_unmodified_tiles_preserve_original_format(self, qtbot, multi_tile_sprite, small_red_overlay):
        """
        Tiles not modified by overlay should preserve their original format.

        This is a behavioral test: we verify that tiles not in modified_tiles
        still have their original pixel values.
        """
        dialog = GridArrangementDialog(multi_tile_sprite, tiles_per_row=4)
        qtbot.addWidget(dialog)
        dialog.show()

        # Get original pixel values for tile (0,1) - should be index 2
        original_tile_01 = dialog.tiles[TilePosition(0, 1)].copy()
        original_pixel = original_tile_01.getpixel((0, 0))

        # Arrange tiles and apply overlay only to (0,0)
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
        dialog.arrangement_manager.set_item_at(0, 1, ArrangementType.TILE, "0,1")

        dialog.overlay_layer.import_image(small_red_overlay)
        dialog.overlay_layer.set_position(0, 0)

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog._apply_overlay()

        # Verify tile (0,1) is unchanged in self.tiles
        current_tile_01 = dialog.tiles[TilePosition(0, 1)]
        current_pixel = current_tile_01.getpixel((0, 0))

        assert current_pixel == original_pixel, (
            f"Tile (0,1) pixel value changed from {original_pixel} to {current_pixel}. "
            f"Unmodified tiles should preserve their original values."
        )


class TestArrangementResultModifiedTilesContract:
    """Tests for the modified_tiles contract in ArrangementResult."""

    def test_no_overlay_applied_returns_none_modified_tiles(self, qtbot, multi_tile_sprite):
        """
        When no overlay is applied, modified_tiles should be None.
        """
        dialog = GridArrangementDialog(multi_tile_sprite, tiles_per_row=4)
        qtbot.addWidget(dialog)
        dialog.show()

        # Arrange tiles but don't apply overlay
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

        result = dialog.get_arrangement_result()
        assert result is not None
        assert result.modified_tiles is None, "modified_tiles should be None when no overlay was applied"

    def test_modified_tiles_images_have_correct_encoding(self, qtbot, multi_tile_sprite, small_red_overlay):
        """
        Modified tiles in ArrangementResult should be L-mode with index * 16 encoding.

        This verifies that _update_tile_data_from_modified_tiles() will work correctly.
        """
        dialog = GridArrangementDialog(multi_tile_sprite, tiles_per_row=4)
        qtbot.addWidget(dialog)
        dialog.show()

        # Define a 16-color palette for quantization
        palette = [(i * 16, i * 16, i * 16) for i in range(16)]
        dialog.colorizer.set_palettes({0: palette})
        dialog.colorizer.toggle_palette_mode()  # Enable palette mode
        dialog.colorizer.set_selected_palette(0)

        # Arrange and apply
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

        dialog.overlay_layer.import_image(small_red_overlay)
        dialog.overlay_layer.set_position(0, 0)

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog._apply_overlay()

        result = dialog.get_arrangement_result()
        assert result is not None
        assert result.modified_tiles is not None

        # The modified tile should be in L-mode
        modified_tile = result.modified_tiles[TilePosition(0, 0)]
        assert modified_tile.mode == "L", f"Modified tile should be L-mode, got {modified_tile.mode}"

        # Pixel values should be in range 0-240 (index 0-15 * 16)
        pixel = modified_tile.getpixel((0, 0))
        assert pixel % 16 == 0, (
            f"Pixel value {pixel} is not a multiple of 16. Modified tiles should have index * 16 encoding."
        )
        assert 0 <= pixel <= 240, f"Pixel value {pixel} out of expected range 0-240"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
