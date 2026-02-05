"""Test that mapping panel game frame column updates on relink."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from ui.frame_mapping.views.mapping_panel import MappingPanel


class TestMappingPanelGameFrameText:
    """Test update_row_game_frame_text updates column 3."""

    @pytest.fixture
    def panel_with_row(self, qtbot):
        """Create a MappingPanel and add one row."""
        panel = MappingPanel()
        qtbot.addWidget(panel)
        # Manually insert a row to test against
        panel._table.insertRow(0)
        # Column 0: checkbox item with AI frame ID in UserRole+1
        from PySide6.QtWidgets import QTableWidgetItem

        checkbox_item = QTableWidgetItem()
        checkbox_item.setData(Qt.ItemDataRole.UserRole + 1, "ai_frame_001")
        panel._table.setItem(0, 0, checkbox_item)
        # Column 3: game frame text
        game_item = QTableWidgetItem("old_game_frame")
        panel._table.setItem(0, 3, game_item)
        return panel

    def test_relink_updates_game_frame_column_text(self, panel_with_row):
        """update_row_game_frame_text should update column 3 text."""
        panel = panel_with_row
        # Verify initial state
        assert panel._table.item(0, 3).text() == "old_game_frame"

        # Update game frame text
        panel.update_row_game_frame_text("ai_frame_001", "new_game_frame")

        # Verify column 3 was updated
        assert panel._table.item(0, 3).text() == "new_game_frame"

    def test_no_crash_on_unknown_ai_frame(self, panel_with_row):
        """update_row_game_frame_text with unknown AI frame ID should not crash."""
        panel = panel_with_row
        # Should just silently do nothing
        panel.update_row_game_frame_text("nonexistent_frame", "some_game_frame")
        # Original text unchanged
        assert panel._table.item(0, 3).text() == "old_game_frame"
