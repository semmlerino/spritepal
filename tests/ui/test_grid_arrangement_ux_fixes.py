# pyright: basic
"""
Tests for Grid Arrangement Dialog UX fixes.
Verifies Export button, Selection interactions, and Undo/Redo logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PIL import Image
from PySide6.QtCore import Qt

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

        # Check that legend content widget exists and is visible
        assert hasattr(dialog, "_legend_content")
        assert dialog._legend_content.isVisible()

        # Check legend text contains key mouse shortcuts
        legend_text = dialog._legend_content.text()
        assert "Ctrl+Click" in legend_text
        assert "Ctrl+Shift+Drag" in legend_text
        assert "Wheel zoom" in legend_text
        assert "Middle-drag pan" in legend_text
        assert "Ctrl+E" in legend_text  # Export shortcut

    def test_legend_collapsible(self, dialog: GridArrangementDialog, qtbot: QtBot):
        """Verify legend can be collapsed and expanded."""
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Initially expanded
        assert dialog._legend_content.isVisible()
        assert dialog._legend_toggle_btn.isChecked()

        # Click toggle to collapse
        qtbot.mouseClick(dialog._legend_toggle_btn, Qt.MouseButton.LeftButton)
        assert not dialog._legend_content.isVisible()
        assert not dialog._legend_toggle_btn.isChecked()

        # Click toggle to expand again
        qtbot.mouseClick(dialog._legend_toggle_btn, Qt.MouseButton.LeftButton)
        assert dialog._legend_content.isVisible()
        assert dialog._legend_toggle_btn.isChecked()

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
