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

from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.components.visualization import SelectionMode
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
