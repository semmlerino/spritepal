"""Tests for ROM workflow state transitions."""

from unittest.mock import MagicMock, Mock, patch

import pytest


class TestROMWorkflowStateTransitions:
    """Tests for state transitions in ROMWorkflowController."""

    def test_offset_change_in_edit_mode_resets_to_preview(self, qtbot, tmp_path, monkeypatch):
        """
        Contract: Changing offset while in edit mode (no unsaved changes)
        returns workflow to preview state.

        Expected:
        - state becomes "preview"
        - left panel enabled
        - workspace disabled
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        # Create minimal editing controller
        editing_controller = EditingController()

        # Create controller and view
        controller = ROMWorkflowController(parent=None, editing_controller=editing_controller)
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
        # Left panel should stay enabled so user can navigate (triggers unsaved changes prompt)
        assert view.left_panel.isEnabled()

        # Ensure no unsaved changes (undo_manager.can_undo() returns False)
        assert not editing_controller.undo_manager.can_undo()

        # Change offset while in edit mode (no unsaved changes)
        controller.set_offset(0x2000)

        # Verify state transition occurred
        assert controller.state == "preview", "State should be 'preview' after offset change"
        assert controller.current_offset == 0x2000
        assert view.left_panel.isEnabled(), "Left panel should be enabled in preview state"
        assert not view.workspace.isEnabled(), "Workspace should be disabled in preview state"

    def test_offset_change_with_unsaved_changes_shows_dialog(self, qtbot, tmp_path, monkeypatch):
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
        controller = ROMWorkflowController(parent=None, editing_controller=editing_controller)
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

        monkeypatch.setattr(controller.preview_coordinator, "request_manual_preview", fake_preview)

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


class TestSMCHeaderConfiguration:
    """Tests for SMC header offset configuration during ROM load.

    REGRESSION: These tests ensure the controller properly configures the view
    with SMC header offset after ROM load, fixing offset misalignment bugs when
    manually pasting Mesen2 "FILE OFFSET: 0x..." values.
    """

    def test_view_has_set_header_offset_method(self, qtbot):
        """
        Verify that the view chain has set_header_offset method.

        This is a prerequisite for the fix to work - ensures the delegation
        chain exists from ROMWorkflowPage -> SourceBar -> OffsetLineEdit.
        """
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        view = ROMWorkflowPage()
        qtbot.addWidget(view)

        # Verify the method exists and is callable
        assert hasattr(view, "set_header_offset")
        assert callable(view.set_header_offset)

        # Verify it doesn't raise
        view.set_header_offset(512)
        view.set_header_offset(0)

    def test_controller_stores_smc_header_offset_on_rom_load(self, qtbot, tmp_path, monkeypatch):
        """
        Verify that controller.smc_header_offset is updated when ROM loads.

        This confirms the controller correctly extracts header offset from
        the ROM validator's response.
        """
        from core.rom_validator import ROMHeader, RomMappingType
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        # Create controller and view
        editing_controller = EditingController()
        controller = ROMWorkflowController(parent=None, editing_controller=editing_controller)
        view = ROMWorkflowPage()
        qtbot.addWidget(view)
        controller.set_view(view)

        # Create mock header with SMC header present
        mock_header = ROMHeader(
            title="TEST ROM",
            rom_type=0x00,
            rom_size=0x08,
            sram_size=0x00,
            checksum=0x0000,
            checksum_complement=0xFFFF,
            header_offset=512,  # SMC header
            rom_type_offset=0x7FC0,
            mapping_type=RomMappingType.SA1,
        )

        # Create a dummy ROM file
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 0x10000)

        # Patch the validation to return our mock header
        with (
            patch(
                "core.rom_validator.ROMValidator.validate_rom_file",
                return_value=(True, None),
            ),
            patch(
                "core.rom_validator.ROMValidator.validate_rom_header",
                return_value=(mock_header, None),
            ),
            patch(
                "core.rom_validator.ROMValidator.verify_rom_checksum",
                return_value=True,
            ),
        ):
            controller.load_rom(str(rom_path))

        # Verify controller state was updated
        assert controller.smc_header_offset == 512

    def test_widget_header_offset_affects_mesen2_parsing(self, qtbot):
        """
        Verify the offset widget correctly adjusts for header offset when
        parsing Mesen2 format input.

        This is the end-to-end behavior we want to ensure works.
        """
        from ui.sprite_editor.views.widgets.offset_line_edit import OffsetLineEdit

        widget = OffsetLineEdit()
        qtbot.addWidget(widget)

        # Set header offset (as controller would do after ROM load)
        widget.set_header_offset(512)

        # Parse Mesen2 format
        file_offset = 0x3C6EF1
        expected_rom_offset = file_offset - 512

        with qtbot.waitSignal(widget.offset_changed, check_params_cb=lambda val: val == expected_rom_offset):
            widget.setText(f"FILE OFFSET: 0x{file_offset:06X}")

        assert widget.offset() == expected_rom_offset
