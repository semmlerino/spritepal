"""Tests for MappingPanel.refresh() selection preservation.

Bug: refresh() was causing spurious mapping_selected signals due to missing
signal blocking during table rebuild. When setRowCount(0) was called, Qt
would fire itemSelectionChanged which could load wrong frame data and crash.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from core.frame_mapping_project import AIFrame, FrameMappingProject
from tests.fixtures.frame_mapping_helpers import create_test_project
from ui.frame_mapping.views.mapping_panel import MappingPanel

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestRefreshPreservesSelection:
    """Tests for MappingPanel.refresh() selection preservation."""

    def test_refresh_does_not_emit_mapping_selected_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Refresh should not emit mapping_selected signal.

        Bug: refresh() cleared the table without blocking signals, causing
        itemSelectionChanged to fire and emit mapping_selected with wrong index.
        """
        # Setup: Create panel with project
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=5)
        panel.set_project(project)
        panel.refresh()

        # Select row 2 (index 2)
        panel._table.selectRow(2)
        assert panel.get_selected_ai_frame_index() == 2

        # Track signals emitted during refresh
        signal_emissions: list[int] = []
        panel.mapping_selected.connect(lambda idx: signal_emissions.append(idx))

        # Call refresh (this is the bug path)
        panel.refresh()

        # Bug behavior: mapping_selected would be emitted (possibly with wrong index)
        # Fixed behavior: mapping_selected should NOT be emitted during refresh
        assert signal_emissions == [], f"Expected no signals, but got {signal_emissions}"

    def test_refresh_preserves_selected_row(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Refresh should preserve the currently selected row.

        After refresh completes, the same AI frame should still be selected.
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=5)
        panel.set_project(project)
        panel.refresh()

        # Select row 3 (AI frame index 3)
        panel._table.selectRow(3)
        assert panel.get_selected_ai_frame_index() == 3

        # Refresh
        panel.refresh()

        # Selection should be preserved
        assert panel.get_selected_ai_frame_index() == 3, "Selection was not preserved after refresh"

    def test_refresh_with_no_selection_does_not_emit_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Refresh with no selection should not emit mapping_selected."""
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=3)
        panel.set_project(project)
        panel.refresh()

        # Clear any selection
        panel._table.clearSelection()
        assert panel.get_selected_ai_frame_index() is None

        # Track signals
        signal_emissions: list[int] = []
        panel.mapping_selected.connect(lambda idx: signal_emissions.append(idx))

        # Refresh
        panel.refresh()

        # No signals should be emitted
        assert signal_emissions == [], f"Unexpected signals: {signal_emissions}"

    def test_refresh_after_row_deleted_clears_invalid_selection(self, qtbot: QtBot, tmp_path: Path) -> None:
        """If selected row no longer exists after refresh, selection is cleared.

        This tests the edge case where the project has fewer frames after refresh.
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        # Start with 5 frames
        project = create_test_project(tmp_path, num_frames=5)
        panel.set_project(project)
        panel.refresh()

        # Select the last row (index 4)
        panel._table.selectRow(4)
        assert panel.get_selected_ai_frame_index() == 4

        # Reduce to 3 frames (simulating external change)
        project.ai_frames = project.ai_frames[:3]

        # Track signals
        signal_emissions: list[int] = []
        panel.mapping_selected.connect(lambda idx: signal_emissions.append(idx))

        # Refresh - should not crash or emit spurious signals
        panel.refresh()

        # Selection should be cleared since index 4 no longer exists
        # But no spurious signals should be emitted during table rebuild
        # (Any signals emitted should be for valid restoration only)
        assert panel.get_selected_ai_frame_index() is None

    def test_set_project_preserves_selection_on_same_project(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Calling set_project with the same project should preserve selection.

        This tests the scenario where project_changed signal causes set_project
        to be called again with the same project during alignment updates.
        Note: Caller must call refresh() after set_project() to populate table.
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=5)
        panel.set_project(project)
        panel.refresh()  # Caller must call refresh after set_project

        # Select row 2
        panel._table.selectRow(2)
        assert panel.get_selected_ai_frame_index() == 2

        # Track signals
        signal_emissions: list[int] = []
        panel.mapping_selected.connect(lambda idx: signal_emissions.append(idx))

        # Call set_project with the same project (simulates project_changed handling)
        # In real usage, workspace calls refresh() separately via _update_mapping_panel_previews
        panel.set_project(project)
        panel.refresh()

        # Selection should be preserved
        assert panel.get_selected_ai_frame_index() == 2, "Selection was not preserved after set_project"

        # No spurious signals
        assert signal_emissions == [], f"Unexpected signals: {signal_emissions}"

    def test_multiple_rapid_refreshes_preserve_selection(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Multiple rapid refresh calls should all preserve selection.

        This simulates the drag scenario where refresh is called many times
        in quick succession.
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=5)
        panel.set_project(project)
        panel.refresh()  # Caller must call refresh after set_project

        # Select row 2
        panel._table.selectRow(2)
        assert panel.get_selected_ai_frame_index() == 2

        # Track signals
        signal_emissions: list[int] = []
        panel.mapping_selected.connect(lambda idx: signal_emissions.append(idx))

        # Simulate rapid refresh calls (like during drag)
        for _ in range(10):
            panel.refresh()

        # Selection should still be preserved
        assert panel.get_selected_ai_frame_index() == 2, "Selection was not preserved after multiple refreshes"

        # No spurious signals
        assert signal_emissions == [], f"Unexpected signals: {signal_emissions}"

    def test_double_refresh_from_different_paths(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Test the exact scenario: set_project followed by refresh.

        This happens when project_changed signal causes set_project to be called,
        followed by another refresh() via _update_mapping_panel_previews.
        Note: set_project no longer calls refresh internally.
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=5)
        panel.set_project(project)
        panel.refresh()  # Initial population

        # Select row 3
        panel._table.selectRow(3)
        assert panel.get_selected_ai_frame_index() == 3

        # Track signals
        signal_emissions: list[int] = []
        panel.mapping_selected.connect(lambda idx: signal_emissions.append(idx))

        # Simulate the workspace flow:
        # 1. project_changed causes set_project (does NOT call refresh)
        panel.set_project(project)
        # 2. Then _update_mapping_panel_previews calls refresh
        panel.refresh()

        # Selection should still be preserved
        assert panel.get_selected_ai_frame_index() == 3, "Selection was not preserved after double refresh"

        # No spurious signals
        assert signal_emissions == [], f"Unexpected signals: {signal_emissions}"


class TestRefreshPreservesCheckboxState:
    """Tests for MappingPanel.refresh() checkbox state preservation.

    Issue: After injection, user-modified checkbox states were being reset.
    These tests verify that checkbox state is preserved across refresh() calls.
    """

    def test_refresh_preserves_unchecked_state(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Unchecked checkboxes should remain unchecked after refresh.

        Scenario: User unchecks some mapped frames, then refresh is called.
        Expected: The unchecked state is preserved.
        """
        from PySide6.QtCore import Qt

        from core.frame_mapping_project import FrameMapping, GameFrame

        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=3)
        # Add mappings so all frames are initially checked
        project.game_frames = [GameFrame(id="GF001")]
        project.mappings = [
            FrameMapping(ai_frame_id=f.id, game_frame_id="GF001", offset_x=0, offset_y=0)
            for f in project.ai_frames
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # Initially all mapped frames should be checked
        for row in range(3):
            checkbox = panel._table.item(row, 0)
            assert checkbox is not None
            assert checkbox.checkState() == Qt.CheckState.Checked

        # User unchecks the second frame
        checkbox_1 = panel._table.item(1, 0)
        assert checkbox_1 is not None
        checkbox_1.setCheckState(Qt.CheckState.Unchecked)

        # Refresh (simulating project_changed during injection)
        panel.refresh()

        # Checkbox states should be preserved
        checkbox_0 = panel._table.item(0, 0)
        checkbox_1 = panel._table.item(1, 0)
        checkbox_2 = panel._table.item(2, 0)
        assert checkbox_0 is not None
        assert checkbox_1 is not None
        assert checkbox_2 is not None
        assert checkbox_0.checkState() == Qt.CheckState.Checked, "Frame 0 should be checked"
        assert checkbox_1.checkState() == Qt.CheckState.Unchecked, "Frame 1 should remain unchecked"
        assert checkbox_2.checkState() == Qt.CheckState.Checked, "Frame 2 should be checked"

    def test_multiple_refreshes_preserve_checkbox_state(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Multiple rapid refreshes should all preserve checkbox state.

        Scenario: During batch injection, multiple project_changed signals
        trigger multiple refresh() calls. Checkbox state must be preserved.
        """
        from PySide6.QtCore import Qt

        from core.frame_mapping_project import FrameMapping, GameFrame

        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=5)
        project.game_frames = [GameFrame(id="GF001")]
        project.mappings = [
            FrameMapping(ai_frame_id=f.id, game_frame_id="GF001", offset_x=0, offset_y=0)
            for f in project.ai_frames
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # User unchecks frames 1 and 3
        panel._table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
        panel._table.item(3, 0).setCheckState(Qt.CheckState.Unchecked)

        # Simulate multiple refresh calls (like during batch injection)
        for _ in range(10):
            panel.refresh()

        # Checkbox states should still be preserved
        assert panel._table.item(0, 0).checkState() == Qt.CheckState.Checked
        assert panel._table.item(1, 0).checkState() == Qt.CheckState.Unchecked
        assert panel._table.item(2, 0).checkState() == Qt.CheckState.Checked
        assert panel._table.item(3, 0).checkState() == Qt.CheckState.Unchecked
        assert panel._table.item(4, 0).checkState() == Qt.CheckState.Checked

    def test_set_sheet_palette_same_object_skips_refresh(self, qtbot: QtBot, tmp_path: Path) -> None:
        """set_sheet_palette with same object should skip refresh.

        Scenario: During project_changed, set_sheet_palette is called with
        the same palette object. No refresh should occur, preserving state.
        """
        from PySide6.QtCore import Qt

        from core.frame_mapping_project import FrameMapping, GameFrame, SheetPalette

        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=3)
        project.game_frames = [GameFrame(id="GF001")]
        project.mappings = [
            FrameMapping(ai_frame_id=f.id, game_frame_id="GF001", offset_x=0, offset_y=0)
            for f in project.ai_frames
        ]
        project._invalidate_mapping_index()

        # Set initial palette and refresh
        palette = SheetPalette(colors=[(0, 0, 0), (255, 255, 255)], color_mappings={})
        panel.set_project(project)
        panel.set_sheet_palette(palette)

        # User unchecks second frame
        panel._table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)

        # Simulate project_changed calling set_sheet_palette with SAME palette
        panel.set_sheet_palette(palette)  # Should skip refresh (identity check)

        # Checkbox state should be preserved (no refresh occurred)
        assert panel._table.item(0, 0).checkState() == Qt.CheckState.Checked
        assert panel._table.item(1, 0).checkState() == Qt.CheckState.Unchecked
        assert panel._table.item(2, 0).checkState() == Qt.CheckState.Checked