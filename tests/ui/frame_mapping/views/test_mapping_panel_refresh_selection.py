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
from ui.frame_mapping.views.mapping_panel import MappingPanel

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def create_test_project(tmp_path: Path, num_frames: int = 5) -> FrameMappingProject:
    """Create a test project with multiple AI frames.

    Args:
        tmp_path: Temporary directory for test files
        num_frames: Number of AI frames to create

    Returns:
        FrameMappingProject with the specified number of frames
    """
    ai_frames_dir = tmp_path / "ai_frames"
    ai_frames_dir.mkdir()

    # Create dummy AI frame image files
    ai_frames: list[AIFrame] = []
    for i in range(num_frames):
        frame_path = ai_frames_dir / f"frame_{i:03d}.png"
        # Create a minimal PNG file (1x1 transparent pixel)
        frame_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        ai_frames.append(AIFrame(path=frame_path, index=i, width=1, height=1))

    return FrameMappingProject(
        name="test_project",
        ai_frames_dir=ai_frames_dir,
        ai_frames=ai_frames,
        game_frames=[],
        mappings=[],
    )


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
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=5)
        panel.set_project(project)

        # Select row 2
        panel._table.selectRow(2)
        assert panel.get_selected_ai_frame_index() == 2

        # Track signals
        signal_emissions: list[int] = []
        panel.mapping_selected.connect(lambda idx: signal_emissions.append(idx))

        # Call set_project with the same project (simulates project_changed handling)
        panel.set_project(project)

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
        followed by another refresh() in _on_alignment_changed.
        """
        panel = MappingPanel()
        qtbot.addWidget(panel)

        project = create_test_project(tmp_path, num_frames=5)
        panel.set_project(project)

        # Select row 3
        panel._table.selectRow(3)
        assert panel.get_selected_ai_frame_index() == 3

        # Track signals
        signal_emissions: list[int] = []
        panel.mapping_selected.connect(lambda idx: signal_emissions.append(idx))

        # Simulate the actual bug scenario:
        # 1. project_changed causes set_project (which calls refresh internally)
        panel.set_project(project)
        # 2. Then _on_alignment_changed calls refresh directly
        panel.refresh()

        # Selection should still be preserved
        assert panel.get_selected_ai_frame_index() == 3, "Selection was not preserved after double refresh"

        # No spurious signals
        assert signal_emissions == [], f"Unexpected signals: {signal_emissions}"
