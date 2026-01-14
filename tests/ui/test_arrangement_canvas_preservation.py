"""
Tests to verify canvas dimensions are preserved after overlay application.

Regression test for: Canvas size changing after applying overlay in GridArrangementDialog
when only a subset of tiles are arranged.

Bug: When user arranges only some tiles and applies an overlay, the canvas size shrinks
to only the arranged tiles, causing non-arranged tiles to become invisible.
"""

from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition
from ui.sprite_editor.services.arrangement_bridge import ArrangementBridge


@pytest.fixture
def wide_sprite(tmp_path):
    """Create a 24-tile wide sprite (192x8 px)."""
    # 24 tiles = 192px wide, 1 row = 8px tall
    img = Image.new("L", (192, 8), 0)
    # Add distinguishing pattern to each tile for verification
    for tile_idx in range(24):
        x = tile_idx * 8
        for px in range(8):
            for py in range(8):
                # Each tile has distinct value: tile 0 = 10, tile 1 = 20, etc.
                img.putpixel((x + px, py), min(tile_idx * 10, 240))
    path = tmp_path / "wide_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def small_overlay(tmp_path):
    """Create a small overlay covering only 4 tiles (32x8 px)."""
    img = Image.new("RGBA", (32, 8), (255, 0, 0, 255))
    path = tmp_path / "small_overlay.png"
    img.save(path)
    return str(path)


class TestCanvasPreservation:
    """Tests for preserving canvas dimensions after overlay application."""

    def test_canvas_size_preserved_after_overlay_partial_coverage(
        self, qtbot, wide_sprite, small_overlay
    ):
        """
        REGRESSION TEST: When overlay is applied to only some tiles, canvas size
        must remain unchanged in the sprite editor.

        Bug: Canvas size changes from 192x8 to 32x8 after applying overlay.
        """
        # Create dialog with wide sprite (24 tiles)
        dialog = GridArrangementDialog(wide_sprite, tiles_per_row=24)
        qtbot.addWidget(dialog)
        dialog.show()

        # Verify original dimensions
        original_width = dialog.processor.grid_cols * 8  # 192px
        original_height = dialog.processor.grid_rows * 8  # 8px
        assert original_width == 192
        assert original_height == 8

        # Arrange only 4 tiles (first 4)
        for col in range(4):
            dialog.arrangement_manager.set_item_at(0, col, ArrangementType.TILE, f"0,{col}")

        # Import and apply overlay
        dialog.overlay_layer.import_image(small_overlay)
        dialog.overlay_layer.set_position(0, 0)

        # Apply overlay (bypass message boxes)
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(
                QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok
            ):
                dialog._apply_overlay()

        # Get arrangement result
        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        # CRITICAL ASSERTION: Logical size must preserve original dimensions
        logical_width_px, logical_height_px = bridge.logical_size
        assert logical_width_px == original_width, (
            f"Canvas width changed from {original_width}px to {logical_width_px}px. "
            "Non-arranged tiles would become invisible!"
        )
        assert logical_height_px == original_height, (
            f"Canvas height changed from {original_height}px to {logical_height_px}px."
        )

    def test_physical_to_logical_preserves_all_tiles(self, wide_sprite):
        """
        Verify that physical_to_logical transformation preserves ALL tiles,
        not just the arranged ones.
        """
        # Create dialog with wide sprite (24 tiles)
        dialog = GridArrangementDialog(wide_sprite, tiles_per_row=24)

        # Arrange only first 4 tiles
        for col in range(4):
            dialog.arrangement_manager.set_item_at(0, col, ArrangementType.TILE, f"0,{col}")

        # Get arrangement result
        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        # Create test input array (192x8) with distinct values per tile
        input_array = np.zeros((8, 192), dtype=np.uint8)
        for tile_idx in range(24):
            x = tile_idx * 8
            input_array[:, x : x + 8] = min(tile_idx * 10, 240)

        # Transform physical to logical
        output_array = bridge.physical_to_logical(input_array)

        # CRITICAL ASSERTION: Output must have same dimensions as input
        assert output_array.shape == input_array.shape, (
            f"physical_to_logical changed shape from {input_array.shape} to {output_array.shape}. "
            "Non-arranged tiles are lost!"
        )

        # Verify non-arranged tiles are preserved at their original positions
        # Tiles 4-23 should be unchanged (identity mapping)
        for tile_idx in range(4, 24):
            x = tile_idx * 8
            expected_value = min(tile_idx * 10, 240)
            actual_value = output_array[0, x]
            assert actual_value == expected_value, (
                f"Tile {tile_idx} at x={x} was not preserved. "
                f"Expected {expected_value}, got {actual_value}"
            )

    def test_logical_to_physical_preserves_non_arranged_tiles(self, wide_sprite):
        """
        Verify that logical_to_physical transformation preserves tiles that
        were not explicitly arranged (identity mapping for non-arranged tiles).
        """
        # Create dialog with wide sprite (24 tiles)
        dialog = GridArrangementDialog(wide_sprite, tiles_per_row=24)

        # Arrange only first 4 tiles
        for col in range(4):
            dialog.arrangement_manager.set_item_at(0, col, ArrangementType.TILE, f"0,{col}")

        # Get arrangement result
        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        # Create logical array (same size as physical)
        logical_w, logical_h = bridge.logical_size
        logical_array = np.zeros((logical_h, logical_w), dtype=np.uint8)

        # Fill with distinct values
        for tile_idx in range(24):
            x = tile_idx * 8
            if x + 8 <= logical_w:  # Only fill within bounds
                logical_array[:, x : x + 8] = min(tile_idx * 10, 240)

        # Transform logical to physical
        physical_array = bridge.logical_to_physical(logical_array)

        # Physical dimensions should match original sprite
        phys_w, phys_h = bridge.physical_size
        assert physical_array.shape == (phys_h, phys_w), (
            f"logical_to_physical output shape {physical_array.shape} "
            f"doesn't match physical size ({phys_h}, {phys_w})"
        )

        # Verify arranged tiles were copied correctly
        for col in range(4):
            expected_value = min(col * 10, 240)
            actual_value = physical_array[0, col * 8]
            assert actual_value == expected_value, (
                f"Arranged tile {col} was not correctly transformed. "
                f"Expected {expected_value}, got {actual_value}"
            )


class TestArrangementBridgeDimensions:
    """Unit tests for ArrangementBridge dimension calculations."""

    def test_logical_size_minimum_physical(self, wide_sprite):
        """
        Logical size should be at least as large as physical size
        to prevent losing tiles.
        """
        dialog = GridArrangementDialog(wide_sprite, tiles_per_row=24)

        # Arrange only 2 tiles (16px)
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
        dialog.arrangement_manager.set_item_at(0, 1, ArrangementType.TILE, "0,1")

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        logical_w, logical_h = bridge.logical_size
        physical_w, physical_h = bridge.physical_size

        # Logical size should accommodate all physical tiles
        assert logical_w >= physical_w, (
            f"Logical width {logical_w}px is smaller than physical {physical_w}px"
        )
        assert logical_h >= physical_h, (
            f"Logical height {logical_h}px is smaller than physical {physical_h}px"
        )
