# pyright: basic
"""
Tests for Grid Arrangement Dialog UX fixes.
Verifies Export button, Selection Mode shortcuts, and Undo/Redo logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox

from ui.components.visualization import SelectionMode
from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import TilePosition

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = [pytest.mark.gui]


class TestGridArrangementUXFixes:
    """Test UX improvements in GridArrangementDialog."""

    @pytest.fixture
    def dialog(self, qtbot: QtBot, tmp_path) -> GridArrangementDialog:
        """Create a GridArrangementDialog with a test image."""
        test_image_path = tmp_path / "test_sprite.png"
        # Create a 32x16 image (2x2 8x8 tiles - wait, 16x16 is 2x2 8x8 tiles)
        # Processor default tile size is usually 8x8.
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
        
        # Verify it's in the button box if possible (checking parent or layout)
        # QDialogButtonBox layout is internal, but we can check if button is visible/parented
        assert dialog.export_btn.isVisible()
        
        # Check if it's in the button box list of buttons
        # (This depends on how it was added. We added it manually via addButton)
        if dialog.button_box:
            buttons = dialog.button_box.buttons()
            assert dialog.export_btn in buttons

    def test_selection_mode_shortcuts(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify T, R, C, M shortcuts switch selection modes."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)
        
        # Default is TILE
        assert dialog.mode_toggle.current_data() == SelectionMode.TILE
        
        # Press R for Row
        qtbot.keyClick(dialog, Qt.Key.Key_R)
        assert dialog.mode_toggle.current_data() == SelectionMode.ROW
        assert dialog.grid_view.selection_mode == SelectionMode.ROW
        
        # Press C for Column
        qtbot.keyClick(dialog, Qt.Key.Key_C)
        assert dialog.mode_toggle.current_data() == SelectionMode.COLUMN
        assert dialog.grid_view.selection_mode == SelectionMode.COLUMN
        
        # Press M for Marquee (Rectangle)
        qtbot.keyClick(dialog, Qt.Key.Key_M)
        assert dialog.mode_toggle.current_data() == SelectionMode.RECTANGLE
        assert dialog.grid_view.selection_mode == SelectionMode.RECTANGLE
        
        # Press T for Tile
        qtbot.keyClick(dialog, Qt.Key.Key_T)
        assert dialog.mode_toggle.current_data() == SelectionMode.TILE
        assert dialog.grid_view.selection_mode == SelectionMode.TILE

    def test_tile_click_undo_redo(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify clicking a tile adds it, and undo/redo works."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)
        
        # Ensure we are in TILE mode
        dialog.mode_toggle.set_current_data(SelectionMode.TILE)
        
        # Simulate clicking tile at (0, 0)
        tile_pos = TilePosition(0, 0)
        
        # Initial state: not arranged
        assert not dialog.arrangement_manager.is_tile_arranged(tile_pos)
        
        # Trigger click manually (simulating signal from grid view)
        dialog._on_tile_clicked(tile_pos)
        
        # Should be arranged now
        assert dialog.arrangement_manager.is_tile_arranged(tile_pos)
        assert dialog.undo_stack.can_undo()
        
        # Undo
        dialog._on_undo()
        assert not dialog.arrangement_manager.is_tile_arranged(tile_pos)
        assert dialog.undo_stack.can_redo()
        
        # Redo
        dialog._on_redo()
        assert dialog.arrangement_manager.is_tile_arranged(tile_pos)

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

        # Verify the manager's target width was updated
        assert dialog.arrangement_manager._target_width == 2

        # Add 3 tiles sequentially (they should wrap at width=2)
        tiles = [TilePosition(0, 0), TilePosition(0, 1), TilePosition(1, 0)]
        for tile in tiles:
            if not dialog.arrangement_manager.is_tile_arranged(tile):
                dialog.arrangement_manager.add_tile(tile)

        # Check grid_mapping uses width=2
        mapping = dialog.arrangement_manager.get_grid_mapping()
        # First two tiles should be at (0,0) and (0,1)
        # Third tile should wrap to (1,0) because width is 2
        assert (0, 0) in mapping
        assert (0, 1) in mapping
        assert (1, 0) in mapping
        # Verify (0, 2) does NOT exist (would only exist if width > 2)
        assert (0, 2) not in mapping

    def test_row_mode_click_adds_entire_row(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify clicking a tile in ROW mode adds the entire row."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Set ROW mode
        dialog.mode_toggle.set_current_data(SelectionMode.ROW)

        # Simulate click on tile (0, 0)
        dialog._on_tile_clicked(TilePosition(0, 0))

        # Verify all tiles in row 0 are arranged
        for col in range(dialog.grid_view.grid_cols):
            assert dialog.arrangement_manager.is_tile_arranged(TilePosition(0, col))

    def test_column_mode_click_adds_entire_column(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify clicking a tile in COLUMN mode adds the entire column."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Set COLUMN mode
        dialog.mode_toggle.set_current_data(SelectionMode.COLUMN)

        # Simulate click on tile (0, 0)
        dialog._on_tile_clicked(TilePosition(0, 0))

        # Verify all tiles in column 0 are arranged
        for row in range(dialog.grid_view.grid_rows):
            assert dialog.arrangement_manager.is_tile_arranged(TilePosition(row, 0))

    def test_c_key_only_sets_column_mode(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify C key sets Column mode (and doesn't toggle palette)."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Start in TILE mode
        dialog.mode_toggle.set_current_data(SelectionMode.TILE)

        # Remember initial palette state
        initial_palette_mode = dialog.colorizer.is_palette_mode()

        # Press C
        qtbot.keyClick(dialog, Qt.Key.Key_C)

        # Verify Column mode was set
        assert dialog.mode_toggle.current_data() == SelectionMode.COLUMN

        # Verify palette mode unchanged (C no longer toggles palette)
        assert dialog.colorizer.is_palette_mode() == initial_palette_mode

    def test_row_mode_click_removes_entire_row_if_arranged(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify clicking in ROW mode removes the row if all tiles are arranged."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # First, add the entire row manually
        row_tiles = dialog.arrangement_manager.get_row_tiles(0)
        for tile in row_tiles:
            dialog.arrangement_manager.add_tile(tile)

        # Verify all are arranged
        for tile in row_tiles:
            assert dialog.arrangement_manager.is_tile_arranged(tile)

        # Set ROW mode
        dialog.mode_toggle.set_current_data(SelectionMode.ROW)

        # Click should remove the row since it's fully arranged
        dialog._on_tile_clicked(TilePosition(0, 0))

        # Verify all tiles in row 0 are now removed
        for tile in row_tiles:
            assert not dialog.arrangement_manager.is_tile_arranged(tile)
