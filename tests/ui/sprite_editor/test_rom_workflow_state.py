"""Tests for ROM workflow state transitions."""
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestROMWorkflowStateTransitions:
    """Tests for state transitions in ROMWorkflowController."""

    def test_offset_change_in_edit_mode_resets_to_preview(
        self, qtbot, tmp_path, monkeypatch
    ):
        """
        Contract: Changing offset while in edit mode (no unsaved changes)
        returns workflow to preview state.

        Expected:
        - state becomes "preview"
        - left panel enabled
        - workspace disabled
        - workflow_state_changed signal emitted with "preview"
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        # Create minimal editing controller
        editing_controller = EditingController()

        # Create controller and view
        controller = ROMWorkflowController(
            parent=None, editing_controller=editing_controller
        )
        view = ROMWorkflowPage()
        qtbot.addWidget(view)
        controller.set_view(view)

        # Set up ROM state directly to skip validation
        dummy_rom = tmp_path / "test.sfc"
        dummy_rom.write_bytes(b"\x00" * 0x10000)
        controller.rom_path = str(dummy_rom)
        controller.rom_size = 0x10000

        # Mock preview to complete immediately
        def fake_preview(offset: int) -> None:
            controller._on_preview_ready(
                tile_data=b"\x00" * 64,
                width=8,
                height=8,
                sprite_name="test_sprite",
                compressed_size=32,
                slack_size=0,
                actual_offset=offset,
                hal_succeeded=True,
            )

        monkeypatch.setattr(
            controller.preview_coordinator,
            "request_manual_preview",
            fake_preview,
        )

        # Set initial offset (triggers preview)
        controller.set_offset(0x1000)
        assert controller.state == "preview"
        assert controller.current_offset == 0x1000

        # Enter edit mode manually (simulating what open_in_editor does)
        controller.state = "edit"
        view.set_workflow_state("edit")
        assert not view.left_panel.isEnabled()  # Verify edit state applied

        # Ensure no unsaved changes (undo_manager.can_undo() returns False)
        assert not editing_controller.undo_manager.can_undo()

        # Track signal emissions
        state_changes: list[str] = []
        controller.workflow_state_changed.connect(state_changes.append)

        # Change offset while in edit mode (no unsaved changes)
        controller.set_offset(0x2000)

        # Verify state transition occurred
        assert controller.state == "preview", "State should be 'preview' after offset change"
        assert controller.current_offset == 0x2000
        assert view.left_panel.isEnabled(), "Left panel should be enabled in preview state"
        assert not view.workspace.isEnabled(), "Workspace should be disabled in preview state"
        assert "preview" in state_changes, "workflow_state_changed should emit 'preview'"

    def test_offset_change_with_unsaved_changes_shows_dialog(
        self, qtbot, tmp_path, monkeypatch
    ):
        """
        Contract: When there ARE unsaved changes, the discard dialog appears.
        If user declines, offset should NOT change.
        """
        from PySide6.QtWidgets import QMessageBox

        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        # Create controller with mocked undo manager that reports unsaved changes
        editing_controller = EditingController()
        controller = ROMWorkflowController(
            parent=None, editing_controller=editing_controller
        )
        view = ROMWorkflowPage()
        qtbot.addWidget(view)
        controller.set_view(view)

        # Set up ROM state
        dummy_rom = tmp_path / "test.sfc"
        dummy_rom.write_bytes(b"\x00" * 0x10000)
        controller.rom_path = str(dummy_rom)
        controller.rom_size = 0x10000

        # Mock preview
        def fake_preview(offset: int) -> None:
            controller._on_preview_ready(
                tile_data=b"\x00" * 64,
                width=8,
                height=8,
                sprite_name="test_sprite",
                compressed_size=32,
                slack_size=0,
                actual_offset=offset,
                hal_succeeded=True,
            )

        monkeypatch.setattr(
            controller.preview_coordinator, "request_manual_preview", fake_preview
        )

        # Set initial offset
        controller.set_offset(0x1000)

        # Enter edit mode and simulate unsaved changes
        controller.state = "edit"
        view.set_workflow_state("edit")

        # Mock can_undo to return True (unsaved changes exist)
        monkeypatch.setattr(editing_controller.undo_manager, "can_undo", lambda: True)

        # Mock dialog to return "No" (user declines to discard)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.No,
        )

        # Try to change offset
        controller.set_offset(0x2000)

        # Offset should NOT have changed
        assert controller.current_offset == 0x1000, "Offset should not change when user declines"
        assert controller.state == "edit", "State should remain 'edit' when user declines"
