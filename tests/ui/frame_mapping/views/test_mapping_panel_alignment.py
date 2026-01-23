"""Tests for MappingPanel alignment update behavior.

Verifies that alignment changes don't reset checkbox state.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
from ui.frame_mapping.views.mapping_panel import MappingPanel


class TestMappingPanelAlignmentUpdate:
    """Tests for targeted alignment update preserving checkbox state."""

    def test_alignment_change_preserves_checkbox_state(self, qtbot) -> None:
        """Checkbox state is preserved when alignment is updated.

        Scenario: User unchecks a mapped frame, then adjusts alignment.
        Expected: The unchecked state is preserved after alignment update.
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        # Create project with mapped frames
        # Note: AIFrame.id is computed from path.name
        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("/fake/frame1.png"), index=0),
            AIFrame(path=Path("/fake/frame2.png"), index=1),
        ]
        project.game_frames = [
            GameFrame(id="GF001"),
            GameFrame(id="GF002"),
        ]
        project.mappings = [
            FrameMapping(ai_frame_id="frame1.png", game_frame_id="GF001", offset_x=0, offset_y=0),
            FrameMapping(ai_frame_id="frame2.png", game_frame_id="GF002", offset_x=0, offset_y=0),
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # Initially, both mapped frames should be checked (default behavior)
        checkbox_0 = panel._table.item(0, 0)
        checkbox_1 = panel._table.item(1, 0)
        assert checkbox_0 is not None
        assert checkbox_1 is not None
        assert checkbox_0.checkState() == Qt.CheckState.Checked
        assert checkbox_1.checkState() == Qt.CheckState.Checked

        # User unchecks first frame
        checkbox_0.setCheckState(Qt.CheckState.Unchecked)
        assert checkbox_0.checkState() == Qt.CheckState.Unchecked

        # Update alignment for first frame (simulates drag or arrow key)
        panel.update_row_alignment(0, offset_x=5, offset_y=10, flip_h=False, flip_v=False)

        # Checkbox state should be PRESERVED
        assert checkbox_0.checkState() == Qt.CheckState.Unchecked, "Checkbox state was reset by alignment update"
        assert checkbox_1.checkState() == Qt.CheckState.Checked

    def test_alignment_change_updates_only_alignment_columns(self, qtbot) -> None:
        """Alignment update only modifies offset and flip columns.

        Verifies that other columns (AI Frame, Game Frame, Status) are unchanged.
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        # Create project
        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("/fake/frame1.png"), index=0),
        ]
        project.game_frames = [
            GameFrame(id="GF001"),
        ]
        project.mappings = [
            FrameMapping(ai_frame_id="frame1.png", game_frame_id="GF001", offset_x=0, offset_y=0),
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # Get initial values of columns that should NOT change
        ai_frame_item = panel._table.item(0, 2)  # AI Frame column
        game_frame_item = panel._table.item(0, 3)  # Game Frame column
        status_item = panel._table.item(0, 6)  # Status column

        assert ai_frame_item is not None
        assert game_frame_item is not None
        assert status_item is not None

        initial_ai_text = ai_frame_item.text()
        initial_game_text = game_frame_item.text()
        initial_status_text = status_item.text()

        # Update alignment
        panel.update_row_alignment(0, offset_x=15, offset_y=-20, flip_h=True, flip_v=False)

        # Verify offset and flip columns WERE updated
        offset_item = panel._table.item(0, 4)
        flip_item = panel._table.item(0, 5)
        assert offset_item is not None
        assert flip_item is not None
        assert offset_item.text() == "(15, -20)"
        assert flip_item.text() == "H"

        # Verify other columns were NOT changed
        assert ai_frame_item.text() == initial_ai_text
        assert game_frame_item.text() == initial_game_text
        assert status_item.text() == initial_status_text

    def test_alignment_update_handles_zero_offset(self, qtbot) -> None:
        """Zero offset shows dash instead of (0, 0)."""
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("/fake/frame1.png"), index=0),
        ]
        project.game_frames = [
            GameFrame(id="GF001"),
        ]
        project.mappings = [
            FrameMapping(ai_frame_id="frame1.png", game_frame_id="GF001", offset_x=10, offset_y=10),
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # Set non-zero offset first
        panel.update_row_alignment(0, offset_x=5, offset_y=5, flip_h=False, flip_v=False)
        offset_item = panel._table.item(0, 4)
        assert offset_item is not None
        assert offset_item.text() == "(5, 5)"

        # Update to zero offset
        panel.update_row_alignment(0, offset_x=0, offset_y=0, flip_h=False, flip_v=False)
        assert offset_item.text() == "—"

    def test_alignment_update_handles_both_flips(self, qtbot) -> None:
        """Both H and V flips show as 'HV'."""
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("/fake/frame1.png"), index=0),
        ]
        project.game_frames = [
            GameFrame(id="GF001"),
        ]
        project.mappings = [
            FrameMapping(ai_frame_id="frame1.png", game_frame_id="GF001", offset_x=0, offset_y=0),
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # Update with both flips
        panel.update_row_alignment(0, offset_x=0, offset_y=0, flip_h=True, flip_v=True)
        flip_item = panel._table.item(0, 5)
        assert flip_item is not None
        assert flip_item.text() == "HV"

    def test_alignment_update_for_nonexistent_row_is_noop(self, qtbot) -> None:
        """Updating alignment for non-existent AI index does nothing."""
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("/fake/frame1.png"), index=0),
        ]
        project.game_frames = [
            GameFrame(id="GF001"),
        ]
        project.mappings = [
            FrameMapping(ai_frame_id="frame1.png", game_frame_id="GF001", offset_x=0, offset_y=0),
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # Try to update non-existent row (should not raise)
        panel.update_row_alignment(999, offset_x=10, offset_y=10, flip_h=True, flip_v=True)

        # Verify existing row was not affected
        offset_item = panel._table.item(0, 4)
        assert offset_item is not None
        assert offset_item.text() == "—"  # Still default


class TestMappingPanelStatusUpdate:
    """Tests for targeted status column update."""

    def test_status_update_changes_status_column_text(self, qtbot) -> None:
        """update_row_status changes the status column text and color."""
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("/fake/frame1.png"), index=0),
        ]
        project.game_frames = [
            GameFrame(id="GF001"),
        ]
        project.mappings = [
            FrameMapping(
                ai_frame_id="frame1.png",
                game_frame_id="GF001",
                offset_x=0,
                offset_y=0,
                status="mapped",
            ),
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # Verify initial status
        status_item = panel._table.item(0, 6)
        assert status_item is not None
        assert "Mapped" in status_item.text()

        # Update status to "edited"
        panel.update_row_status(0, "edited")

        # Verify status column was updated
        assert "Edited" in status_item.text()
        assert "●" in status_item.text()  # Filled indicator for non-unmapped

    def test_status_update_to_unmapped_shows_empty_indicator(self, qtbot) -> None:
        """Unmapped status shows empty circle indicator."""
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("/fake/frame1.png"), index=0),
        ]
        project.game_frames = [
            GameFrame(id="GF001"),
        ]
        project.mappings = [
            FrameMapping(
                ai_frame_id="frame1.png",
                game_frame_id="GF001",
                offset_x=0,
                offset_y=0,
                status="mapped",
            ),
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # Update status to "unmapped"
        panel.update_row_status(0, "unmapped")

        status_item = panel._table.item(0, 6)
        assert status_item is not None
        assert "Unmapped" in status_item.text()
        assert "○" in status_item.text()  # Empty indicator for unmapped

    def test_status_update_preserves_other_columns(self, qtbot) -> None:
        """Status update does not affect other columns."""
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("/fake/frame1.png"), index=0),
        ]
        project.game_frames = [
            GameFrame(id="GF001"),
        ]
        project.mappings = [
            FrameMapping(
                ai_frame_id="frame1.png",
                game_frame_id="GF001",
                offset_x=5,
                offset_y=10,
                flip_h=True,
                flip_v=False,
                status="mapped",
            ),
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # Get initial values
        offset_item = panel._table.item(0, 4)
        flip_item = panel._table.item(0, 5)
        checkbox_item = panel._table.item(0, 0)

        assert offset_item is not None
        assert flip_item is not None
        assert checkbox_item is not None

        initial_offset = offset_item.text()
        initial_flip = flip_item.text()
        initial_checkbox = checkbox_item.checkState()

        # Update status
        panel.update_row_status(0, "injected")

        # Verify other columns were NOT changed
        assert offset_item.text() == initial_offset
        assert flip_item.text() == initial_flip
        assert checkbox_item.checkState() == initial_checkbox

    def test_status_update_for_nonexistent_row_is_noop(self, qtbot) -> None:
        """Updating status for non-existent AI index does nothing."""
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = FrameMappingProject(name="test")
        project.ai_frames = [
            AIFrame(path=Path("/fake/frame1.png"), index=0),
        ]
        project.game_frames = [
            GameFrame(id="GF001"),
        ]
        project.mappings = [
            FrameMapping(
                ai_frame_id="frame1.png",
                game_frame_id="GF001",
                offset_x=0,
                offset_y=0,
                status="mapped",
            ),
        ]
        project._invalidate_mapping_index()

        panel.set_project(project)
        panel.refresh()

        # Get initial status
        status_item = panel._table.item(0, 6)
        assert status_item is not None
        initial_status = status_item.text()

        # Try to update non-existent row (should not raise)
        panel.update_row_status(999, "edited")

        # Verify existing row was not affected
        assert status_item.text() == initial_status
