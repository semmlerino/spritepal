# pyright: basic
"""
Consolidated tests for GridArrangementDialog.

Merged from:
- tests/ui/test_grid_arrangement_ux_fixes.py
- tests/ui/test_arrangement_palette_preservation.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QToolButton

from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = [pytest.mark.gui]


# =============================================================================
# Grid Arrangement UX Fixes (from test_grid_arrangement_ux_fixes.py)
# =============================================================================


class TestGridArrangementUXFixes:
    """Test UX improvements in GridArrangementDialog."""

    @pytest.fixture
    def dialog(self, qtbot: QtBot, tmp_path) -> GridArrangementDialog:
        """Create a GridArrangementDialog with a test image."""
        test_image_path = tmp_path / "test_sprite.png"
        # Create a 32x16 image (2x2 8x8 tiles)
        test_image = Image.new("RGB", (16, 16), color="white")
        test_image.save(test_image_path)

        dialog = GridArrangementDialog(str(test_image_path), tiles_per_row=16)
        qtbot.addWidget(dialog)
        return dialog

    def test_export_button_presence(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify Export button is present in button box and initially disabled."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        assert dialog.export_btn is not None
        assert not dialog.export_btn.isEnabled()
        assert dialog.export_btn.isVisible()

        if dialog.button_box:
            buttons = dialog.button_box.buttons()
            assert dialog.export_btn in buttons

    def test_remove_selection_undo_redo(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify removing selection via CanvasRemoveMultipleItemsCommand works with undo."""
        # Setup: Add a tile
        tile_pos = TilePosition(0, 0)
        dialog.arrangement_manager.add_tile(tile_pos)
        assert dialog.arrangement_manager.is_tile_arranged(tile_pos)

        # Select it in source grid
        dialog.grid_view.current_selection.add(tile_pos)

        # Call remove selection
        dialog._remove_selection()

        # Should be removed
        assert not dialog.arrangement_manager.is_tile_arranged(tile_pos)
        assert dialog.undo_stack.can_undo()

        # Undo
        dialog._on_undo()
        assert dialog.arrangement_manager.is_tile_arranged(tile_pos)

    def test_enter_key_adds_selection(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify Enter key calls _add_selection() as advertised in legend."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Select a tile first (add to grid_view selection)
        tile = TilePosition(0, 0)
        dialog.grid_view.current_selection.add(tile)
        dialog.grid_view._update_selection_display()

        # Press Enter
        qtbot.keyClick(dialog, Qt.Key.Key_Return)

        # Verify tile was added to arrangement
        assert dialog.arrangement_manager.is_tile_arranged(tile)

    def test_target_width_affects_auto_placement(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify Target Sheet Width spinbox affects tile auto-placement."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Set width to 2 via spinbox - this triggers signal to update manager
        dialog.width_spin.setValue(2)
        # Process events to ensure signal is handled
        qtbot.wait(10)

        # Add 3 tiles sequentially (they should wrap at width=2)
        tiles = [TilePosition(0, 0), TilePosition(0, 1), TilePosition(1, 0)]
        for tile in tiles:
            if not dialog.arrangement_manager.is_tile_arranged(tile):
                dialog.arrangement_manager.add_tile(tile)

        # Verify behavior through observable output: grid_mapping
        mapping = dialog.arrangement_manager.get_grid_mapping()
        # First two tiles should be at (0,0) and (0,1)
        # Third tile should wrap to (1,0) because width is 2
        assert (0, 0) in mapping
        assert (0, 1) in mapping
        assert (1, 0) in mapping
        # Verify (0, 2) does NOT exist (would only exist if width > 2)
        assert (0, 2) not in mapping

    def test_c_key_toggles_palette(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify C key toggles palette mode."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Initial state
        initial_mode = dialog.colorizer.is_palette_mode()

        # Press C
        qtbot.keyClick(dialog, Qt.Key.Key_C)
        assert dialog.colorizer.is_palette_mode() != initial_mode

    def test_legend_shows_mouse_shortcuts(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify legend contains mouse interaction shortcuts."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Check that legend is visible via public API
        assert dialog.is_legend_visible()

        # Check legend text contains key mouse shortcuts via public API
        legend_text = dialog.get_legend_text()
        assert "Ctrl+Click" in legend_text
        assert "Ctrl+Shift+Drag" in legend_text
        assert "Wheel zoom" in legend_text
        assert "Middle-drag pan" in legend_text
        assert "Ctrl+E" in legend_text  # Export shortcut

    def test_legend_collapsible(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify legend can be collapsed and expanded."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Initially expanded - verify via public API
        assert dialog.is_legend_visible()

        # Click toggle to collapse (toggle button is internal, but we use findChild)
        toggle_btn = dialog.findChild(QToolButton)
        assert toggle_btn is not None
        qtbot.mouseClick(toggle_btn, Qt.MouseButton.LeftButton)
        assert not dialog.is_legend_visible()

        # Click toggle to expand again
        qtbot.mouseClick(toggle_btn, Qt.MouseButton.LeftButton)
        assert dialog.is_legend_visible()

    def test_palette_toggle_button(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify palette toggle button works and syncs with C key."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Verify button exists
        assert hasattr(dialog, "palette_toggle_btn")
        btn = dialog.palette_toggle_btn

        # Initial state (should match colorizer, usually False)
        assert btn.isChecked() == dialog.colorizer.is_palette_mode()

        # Click button to toggle ON
        qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert btn.isChecked()
        assert dialog.colorizer.is_palette_mode()

        # Press C to toggle OFF
        qtbot.keyClick(dialog, Qt.Key.Key_C)
        assert not dialog.colorizer.is_palette_mode()
        assert not btn.isChecked()  # Should sync back


# =============================================================================
# Palette Preservation Tests (from test_arrangement_palette_preservation.py)
# =============================================================================


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

        # Mock ColorMappingDialog to avoid blocking on exec()
        from PySide6.QtWidgets import QDialog

        mock_mapping_dialog = MagicMock()
        mock_mapping_dialog.exec.return_value = QDialog.DialogCode.Accepted
        # Provide a simple color mapping: red (255,0,0) -> palette index 1
        mock_mapping_dialog.color_mappings = {(255, 0, 0): 1}

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                with patch("ui.dialogs.color_mapping_dialog.ColorMappingDialog", return_value=mock_mapping_dialog):
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
