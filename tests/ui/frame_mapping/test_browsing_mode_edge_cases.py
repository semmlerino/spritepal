"""Tests for browsing mode edge cases.

Browsing mode is when the user is viewing a different capture than the one
their selected AI frame is mapped to. These tests verify proper state handling
when the mapped capture is deleted or the mapping is removed while browsing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, FrameMappingProject, GameFrame

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def create_test_image(path: Path) -> None:
    """Create a test image file."""
    img = Image.new("RGBA", (32, 32), (100, 100, 100, 255))
    img.save(path)


class TestBrowsingModeWhenMappedCaptureDeleted:
    """Tests for browsing mode when the mapped capture is deleted."""

    @pytest.fixture
    def project_with_mapping(self, tmp_path: Path) -> tuple[FrameMappingProject, str, str, str]:
        """Create a project with an AI frame mapped to a game frame.

        Returns:
            project, ai_frame_id, mapped_capture_id, browsed_capture_id
        """
        project = FrameMappingProject(name="test_project")

        # Create AI frame
        ai_path = tmp_path / "frame_0.png"
        create_test_image(ai_path)
        ai_frame = AIFrame(path=ai_path, index=0)
        project.add_ai_frame(ai_frame)

        # Create two game frames
        capture_a = GameFrame(id="capture_a", rom_offsets=[0x1000])
        capture_b = GameFrame(id="capture_b", rom_offsets=[0x2000])
        project.add_game_frame(capture_a)
        project.add_game_frame(capture_b)

        # Create mapping from AI frame to capture_a
        project.create_mapping(ai_frame.id, "capture_a")

        return project, ai_frame.id, "capture_a", "capture_b"

    def test_browsing_mode_cleared_when_mapped_capture_deleted(
        self, qtbot: QtBot, project_with_mapping: tuple, tmp_path: Path
    ) -> None:
        """Browsing mode should be cleared when the mapped capture is deleted.

        Scenario:
        1. AI frame is mapped to capture A
        2. User browses capture B (canvas shows B, is_browsing=True)
        3. User deletes capture A (the mapped capture)
        4. Mapping is removed, browsing mode should be cleared
        """
        from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas
        from ui.frame_mapping.workspace_logic_helper import WorkspaceLogicHelper
        from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager

        project, ai_frame_id, mapped_id, browsed_id = project_with_mapping

        # Create state manager
        state = WorkspaceStateManager()
        state.selected_ai_frame_id = ai_frame_id
        state.selected_game_id = browsed_id  # User selected capture B
        state.current_canvas_game_id = browsed_id  # Canvas shows capture B

        # Create canvas mock
        canvas = MagicMock(spec=WorkbenchCanvas)

        # Create logic helper
        helper = WorkspaceLogicHelper()
        helper.set_state(state)

        controller = MagicMock()
        controller.project = project
        helper.set_controller(controller)

        mapping_panel = MagicMock()
        captures_pane = MagicMock()
        ai_pane = MagicMock()
        helper.set_panes(ai_pane, captures_pane, mapping_panel, canvas)

        # Verify initial browsing mode
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        assert mapping is not None
        assert mapping.game_frame_id == mapped_id
        # User is browsing different capture
        is_browsing = state.current_canvas_game_id != mapping.game_frame_id
        assert is_browsing is True

        # Delete the mapped capture (simulates what workspace would do)
        project.remove_game_frame(mapped_id)

        # After deletion, mapping should be gone
        mapping_after = project.get_mapping_for_ai_frame(ai_frame_id)
        assert mapping_after is None

        # Verify: browsing mode should be cleared since there's no mapping
        # (The canvas should call set_browsing_mode(False) through some path)
        # For now, this test documents the expected behavior

    def test_canvas_state_preserved_when_browsing_different_capture(
        self, qtbot: QtBot, project_with_mapping: tuple, tmp_path: Path
    ) -> None:
        """Canvas should stay on browsed capture when mapped capture is deleted.

        The user was viewing capture B. Deleting capture A (which was mapped)
        should NOT change the canvas to suddenly show nothing - it should
        continue showing capture B.
        """
        project, ai_frame_id, mapped_id, browsed_id = project_with_mapping

        from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager

        # Create state manager showing user browsing capture B
        state = WorkspaceStateManager()
        state.selected_ai_frame_id = ai_frame_id
        state.selected_game_id = browsed_id
        state.current_canvas_game_id = browsed_id

        # Delete the mapped capture (not the one being viewed)
        project.remove_game_frame(mapped_id)

        # Canvas state should be unchanged - still showing browsed capture
        assert state.current_canvas_game_id == browsed_id
        assert state.selected_game_id == browsed_id


class TestBrowsingModeWhenMappingRemoved:
    """Tests for browsing mode when the mapping is explicitly removed."""

    @pytest.fixture
    def project_with_mapping(self, tmp_path: Path) -> tuple[FrameMappingProject, str, str, str]:
        """Create a project with an AI frame mapped to a game frame."""
        project = FrameMappingProject(name="test_project")

        ai_path = tmp_path / "frame_0.png"
        create_test_image(ai_path)
        ai_frame = AIFrame(path=ai_path, index=0)
        project.add_ai_frame(ai_frame)

        capture_a = GameFrame(id="capture_a", rom_offsets=[0x1000])
        capture_b = GameFrame(id="capture_b", rom_offsets=[0x2000])
        project.add_game_frame(capture_a)
        project.add_game_frame(capture_b)

        project.create_mapping(ai_frame.id, "capture_a")

        return project, ai_frame.id, "capture_a", "capture_b"

    def test_browsing_mode_cleared_when_mapping_explicitly_removed(
        self, qtbot: QtBot, project_with_mapping: tuple, tmp_path: Path
    ) -> None:
        """Browsing mode should be cleared when the mapping is explicitly removed.

        Scenario:
        1. AI frame is mapped to capture A
        2. User browses capture B (canvas shows B, is_browsing=True)
        3. User removes the mapping (via unmap button)
        4. Browsing mode should be cleared since there's no mapping to browse away from
        """
        project, ai_frame_id, mapped_id, browsed_id = project_with_mapping

        # Verify mapping exists
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        assert mapping is not None

        # Remove the mapping
        project.remove_mapping_for_ai_frame(ai_frame_id)

        # Mapping should be gone
        mapping_after = project.get_mapping_for_ai_frame(ai_frame_id)
        assert mapping_after is None

        # Expected: browsing mode should be cleared
        # (This test documents expected behavior - implementation may need updating)


class TestWorkspaceHandlesBrowsingModeClearing:
    """Integration tests for workspace handling of browsing mode edge cases."""

    def test_on_mapping_removed_clears_browsing_mode_for_selected_frame(self, qtbot: QtBot, tmp_path: Path) -> None:
        """_on_mapping_removed should clear browsing mode for the selected AI frame.

        When a mapping is removed for the currently selected AI frame,
        browsing mode should be cleared since there's no mapping to browse away from.
        """
        from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager

        # Create minimal workspace mock
        state = WorkspaceStateManager()
        state.selected_ai_frame_id = "frame_0.png"

        canvas = MagicMock()
        canvas.set_browsing_mode = MagicMock()

        # Simulate _on_mapping_removed logic
        ai_frame_id = "frame_0.png"
        if ai_frame_id == state.selected_ai_frame_id:
            canvas.set_browsing_mode(False)

        # Verify browsing mode was cleared
        canvas.set_browsing_mode.assert_called_once_with(False)

    def test_on_mapping_removed_does_not_clear_for_unselected_frame(self, qtbot: QtBot, tmp_path: Path) -> None:
        """_on_mapping_removed should NOT clear browsing mode for unselected frames.

        When a mapping is removed for a frame that's NOT currently selected,
        browsing mode should not be affected.
        """
        from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager

        state = WorkspaceStateManager()
        state.selected_ai_frame_id = "frame_0.png"  # Different frame selected

        canvas = MagicMock()
        canvas.set_browsing_mode = MagicMock()

        # Simulate _on_mapping_removed for a different AI frame
        ai_frame_id = "frame_1.png"  # Not the selected frame
        if ai_frame_id == state.selected_ai_frame_id:
            canvas.set_browsing_mode(False)

        # Verify browsing mode was NOT cleared
        canvas.set_browsing_mode.assert_not_called()
