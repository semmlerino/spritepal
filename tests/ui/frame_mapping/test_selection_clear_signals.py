"""Tests for Selection Clear Signal Emission.

When a pane's selection is actually cleared (row becomes -1 due to refresh/list changes),
the pane should emit an empty string to notify listeners. This is different from
filter operations which should NOT emit empty strings (tested in test_selection_state_decoupling.py).

Note: The explicit clear_selection() methods intentionally block signals to prevent
feedback loops. The tests here verify that the _on_selection_changed handlers emit
properly when the Qt selection changes naturally (row becomes -1).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, GameFrame

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestCapturesLibraryPaneEmitsOnClear:
    """Tests for CapturesLibraryPane emitting signal on selection clear."""

    def test_captures_pane_emits_empty_on_row_minus_one(self, qtbot: QtBot) -> None:
        """CapturesLibraryPane should emit empty string when row becomes -1."""
        from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane

        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)
        pane.show()
        qtbot.wait(20)

        frame = GameFrame(id="F001", rom_offsets=[0x1000])
        pane.set_game_frames([frame])
        pane.select_frame("F001")

        # Track emissions
        emissions: list[str] = []
        pane.game_frame_selected.connect(lambda fid: emissions.append(fid))

        # Directly call the handler with row=-1 (simulates list becoming empty or cleared)
        pane._on_selection_changed(-1)

        assert "" in emissions, (
            "CapturesLibraryPane._on_selection_changed(-1) should emit empty string."
        )

    def test_captures_pane_handler_previously_returned_early_on_minus_one(
        self, qtbot: QtBot
    ) -> None:
        """Verify the fix: handler no longer returns early on row=-1.

        Before the fix, _on_selection_changed would return early when row < 0,
        leaving the workspace with stale selection state.
        """
        from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane

        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)

        # Track emissions
        emissions: list[str] = []
        pane.game_frame_selected.connect(lambda fid: emissions.append(fid))

        # Call handler with -1 multiple times
        pane._on_selection_changed(-1)
        pane._on_selection_changed(-1)

        # Each call should emit
        assert emissions.count("") == 2


class TestMappingPanelEmitsOnClear:
    """Tests for MappingPanel emitting signal on selection clear."""

    def test_mapping_panel_handler_emits_empty_when_no_selection(
        self, qtbot: QtBot
    ) -> None:
        """MappingPanel._on_selection_changed should emit empty when no selection."""
        from ui.frame_mapping.views.mapping_panel import MappingPanel

        panel = MappingPanel()
        qtbot.addWidget(panel)

        # Track emissions
        emissions: list[str] = []
        panel.mapping_selected.connect(lambda fid: emissions.append(fid))

        # Manually call _on_selection_changed when there's no selection
        # (get_selected_ai_frame_id returns None)
        panel._on_selection_changed()

        assert "" in emissions, (
            "MappingPanel._on_selection_changed should emit empty string when no selection."
        )

    def test_mapping_panel_emits_empty_after_selection_cleared(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """MappingPanel should emit empty string when table selection is cleared."""
        from ui.frame_mapping.views.mapping_panel import MappingPanel

        panel = MappingPanel()
        qtbot.addWidget(panel)
        panel.show()
        qtbot.wait(20)

        # Create a mock project with one AI frame
        img_path = tmp_path / "frame_0.png"
        img = Image.new("RGBA", (32, 32), (100, 100, 100, 255))
        img.save(img_path)
        ai_frame = AIFrame(path=img_path, index=0)

        project = MagicMock()
        project.ai_frames = [ai_frame]
        project.mappings = []
        project.get_mapping_for_ai_frame = MagicMock(return_value=None)

        panel.set_project(project)
        panel.refresh()

        # Select the row
        panel._table.selectRow(0)
        assert panel.get_selected_ai_frame_id() is not None

        # Track emissions
        emissions: list[str] = []
        panel.mapping_selected.connect(lambda fid: emissions.append(fid))

        # Clear table and trigger selection change
        panel._table.clearSelection()
        # Manually trigger since clearSelection doesn't always emit
        panel._on_selection_changed()

        # Should emit empty string to notify listeners
        assert "" in emissions, (
            "MappingPanel should emit empty string when selection is cleared."
        )


class TestBatchSelectionResetsOnAIReload:
    """Tests for batch selection reset when AI frames are reloaded."""

    def test_mapping_panel_has_reset_batch_selection_method(self) -> None:
        """MappingPanel should have reset_batch_selection method."""
        from ui.frame_mapping.views.mapping_panel import MappingPanel

        assert hasattr(MappingPanel, "reset_batch_selection"), (
            "MappingPanel should have reset_batch_selection method"
        )

    def test_reset_batch_selection_clears_tracking(self, qtbot: QtBot) -> None:
        """reset_batch_selection should reset to default behavior."""
        from ui.frame_mapping.views.mapping_panel import MappingPanel

        panel = MappingPanel()
        qtbot.addWidget(panel)

        # Simulate user toggling a checkbox (starts tracking)
        panel._selection_state.toggle_checked("frame_0.png", checked=False)
        assert panel._selection_state.is_tracking_user_selections()

        # Reset should clear tracking
        panel.reset_batch_selection()

        assert not panel._selection_state.is_tracking_user_selections(), (
            "reset_batch_selection should clear user selection tracking"
        )

    def test_workspace_calls_reset_on_ai_frames_loaded(
        self, qtbot: QtBot
    ) -> None:
        """FrameMappingWorkspace should reset batch selection when AI frames loaded."""
        from unittest.mock import patch

        from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace

        # Create workspace with mocked init
        with patch.object(FrameMappingWorkspace, "__init__", lambda self: None):
            workspace = FrameMappingWorkspace.__new__(FrameMappingWorkspace)
            workspace._message_service = None

            # Mock the mapping panel
            workspace._mapping_panel = MagicMock()

            # Call the handler
            workspace._on_ai_frames_loaded(5)

            # Should have called reset_batch_selection
            workspace._mapping_panel.reset_batch_selection.assert_called_once()


class TestHandleMappingSelectedClearPath:
    """Tests for handle_mapping_selected handling empty AI frame ID."""

    def test_handle_mapping_selected_clears_state_on_empty_id(
        self, qtbot: QtBot
    ) -> None:
        """handle_mapping_selected should clear state when ai_frame_id is empty."""
        from ui.frame_mapping.workspace_logic_helper import WorkspaceLogicHelper
        from ui.workspaces.frame_mapping_workspace import WorkspaceStateManager

        state = WorkspaceStateManager()
        state.selected_ai_frame_id = "some_frame.png"  # Pre-existing selection

        # Create mocks for required components
        controller = MagicMock()
        alignment_canvas = MagicMock()
        ai_frames_pane = MagicMock()
        captures_pane = MagicMock()
        mapping_panel = MagicMock()

        logic = WorkspaceLogicHelper()
        logic.set_controller(controller)
        logic.set_state(state)
        logic.set_panes(ai_frames_pane, captures_pane, mapping_panel, alignment_canvas)

        # Call with empty string (cleared selection)
        logic.handle_mapping_selected("")

        # Should have cleared state
        assert state.selected_ai_frame_id is None, (
            "handle_mapping_selected('') should clear selected_ai_frame_id"
        )

        # Should have cleared canvas
        alignment_canvas.set_ai_frame.assert_called_with(None)
        alignment_canvas.clear_alignment.assert_called_once()

    def test_handle_mapping_selected_updates_button_state_on_clear(
        self, qtbot: QtBot
    ) -> None:
        """handle_mapping_selected should update button state when cleared."""
        from ui.frame_mapping.workspace_logic_helper import WorkspaceLogicHelper
        from ui.workspaces.frame_mapping_workspace import WorkspaceStateManager

        state = WorkspaceStateManager()
        state.selected_ai_frame_id = "frame.png"

        controller = MagicMock()
        alignment_canvas = MagicMock()
        ai_frames_pane = MagicMock()
        captures_pane = MagicMock()
        mapping_panel = MagicMock()

        logic = WorkspaceLogicHelper()
        logic.set_controller(controller)
        logic.set_state(state)
        logic.set_panes(ai_frames_pane, captures_pane, mapping_panel, alignment_canvas)

        # Spy on update_map_button_state
        with patch.object(logic, "update_map_button_state") as mock_update:
            logic.handle_mapping_selected("")

            # Should have called update_map_button_state
            mock_update.assert_called_once()
