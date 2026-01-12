"""
Integration tests for SpriteEditorWorkspace mode switching.

These tests verify observable behavior through signals and public state,
mocking only at external boundaries (ROM validation, async preview coordinator).

Replaces over-mocked tests from:
- tests/ui/test_rom_mode_workflow.py (TestRomModeWorkflow.test_mode_switch, test_jump_to_offset_switches_mode)
- tests/ui/test_mode_switch_repro.py (test_load_rom_switches_mode)
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import QObject, Signal

from tests.ui.integration.helpers.signal_spy_utils import MultiSignalRecorder
from ui.workspaces.sprite_editor_workspace import SpriteEditorWorkspace


class MockPreviewCoordinator(QObject):
    """Mock coordinator that exposes signals for testing async preview flow."""

    preview_ready = Signal(bytes, int, int, str, int, int, int, bool)
    preview_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.request_manual_preview_called = False
        self.request_full_preview_called = False
        self.last_requested_offset = -1

    def set_rom_data_provider(self, provider: object) -> None:
        pass

    def request_manual_preview(self, offset: int) -> None:
        self.request_manual_preview_called = True
        self.last_requested_offset = offset

    def request_full_preview(self, offset: int) -> None:
        """Request full decompression preview (not truncated to 4KB)."""
        self.request_full_preview_called = True
        self.last_requested_offset = offset

    def cleanup(self) -> None:
        pass


@pytest.fixture
def mock_preview_coordinator_class() -> type[MockPreviewCoordinator]:
    """Return the MockPreviewCoordinator class for patching."""
    return MockPreviewCoordinator


@pytest.fixture
def mock_managers() -> MagicMock:
    """Create minimal mock managers for workspace initialization."""
    managers = MagicMock()
    managers.rom_cache = MagicMock()
    managers.rom_extractor = MagicMock()
    managers.application_state_manager = MagicMock()
    managers.log_watcher = MagicMock()
    managers.sprite_library = MagicMock()
    return managers


@pytest.fixture
def sprite_editor_workspace_real(qtbot, mock_managers, mock_preview_coordinator_class) -> SpriteEditorWorkspace:
    """
    Create a real SpriteEditorWorkspace with real page components.

    Only SmartPreviewCoordinator is mocked (async boundary).
    All other components (VRAMEditorPage, ROMWorkflowPage, controllers) are real.
    """
    # Mock only the async preview coordinator at the boundary
    with patch(
        "ui.sprite_editor.controllers.rom_workflow_controller.SmartPreviewCoordinator",
        mock_preview_coordinator_class,
    ):
        workspace = SpriteEditorWorkspace(
            parent=None,
            settings_manager=mock_managers.application_state_manager,
            rom_cache=mock_managers.rom_cache,
            rom_extractor=mock_managers.rom_extractor,
            log_watcher=mock_managers.log_watcher,
            sprite_library=mock_managers.sprite_library,
        )
        qtbot.addWidget(workspace)

        yield workspace

        # Cleanup
        workspace.cleanup()


class TestModeSwitchIntegration:
    """
    Integration tests for mode switching in SpriteEditorWorkspace.

    These tests verify observable behavior:
    - mode_changed signal emission
    - current_mode property updates
    - UI state changes (stack widget index)
    """

    def test_default_mode_is_rom(self, sprite_editor_workspace_real):
        """Verify workspace starts in ROM mode by default."""
        workspace = sprite_editor_workspace_real
        assert workspace.current_mode == "rom"

    def test_mode_switch_emits_signal_and_updates_state(self, sprite_editor_workspace_real):
        """
        Verify mode switching emits mode_changed signal and updates current_mode.

        Replaces: test_rom_mode_workflow.py:TestRomModeWorkflow.test_mode_switch
        """
        workspace = sprite_editor_workspace_real

        recorder = MultiSignalRecorder()
        recorder.connect_signal(workspace.mode_changed, "mode_changed")

        # Default is ROM mode
        assert workspace.current_mode == "rom"

        # Switch to VRAM mode
        workspace.set_mode("vram")

        # Assert observable outcomes
        assert workspace.current_mode == "vram"
        recorder.assert_emitted("mode_changed", times=1)
        assert recorder.get_args("mode_changed", 0) == ("vram",)

        # Switch back to ROM mode
        workspace.set_mode("rom")

        assert workspace.current_mode == "rom"
        recorder.assert_emitted("mode_changed", times=2)
        assert recorder.get_args("mode_changed", 1) == ("rom",)

    def test_mode_switch_updates_visible_page(self, sprite_editor_workspace_real):
        """
        Verify mode switching changes the visible page in the stack widget.

        This tests the observable UI state change.
        """
        workspace = sprite_editor_workspace_real

        # Get the stack widget to verify visible page
        mode_stack = workspace._mode_stack

        # ROM mode is default (index 1)
        assert workspace.current_mode == "rom"
        assert mode_stack.currentWidget() == workspace.rom_page

        workspace.set_mode("vram")

        # VRAM page should now be visible (index 0)
        assert workspace.current_mode == "vram"
        assert mode_stack.currentWidget() == workspace.vram_page

        workspace.set_mode("rom")

        # Back to ROM page
        assert workspace.current_mode == "rom"
        assert mode_stack.currentWidget() == workspace.rom_page

    def test_redundant_mode_switch_does_not_emit(self, sprite_editor_workspace_real):
        """
        Verify switching to the same mode doesn't emit redundant signals.
        """
        workspace = sprite_editor_workspace_real

        recorder = MultiSignalRecorder()
        recorder.connect_signal(workspace.mode_changed, "mode_changed")

        # Start in ROM mode
        assert workspace.current_mode == "rom"

        # "Switch" to ROM (same mode) - should not emit
        workspace.set_mode("rom")

        # No signal should have been emitted
        recorder.assert_emitted("mode_changed", times=0)

    def test_jump_to_offset_switches_to_rom_mode(self, sprite_editor_workspace_real):
        """
        Verify jump_to_offset switches to ROM mode.

        Replaces: test_rom_mode_workflow.py:TestRomModeWorkflow.test_jump_to_offset_switches_mode
        """
        workspace = sprite_editor_workspace_real

        recorder = MultiSignalRecorder()
        recorder.connect_signal(workspace.mode_changed, "mode_changed")

        # Start in VRAM mode
        workspace.set_mode("vram")
        recorder.clear()  # Clear the mode switch signal
        assert workspace.current_mode == "vram"

        # Jump to offset - should switch to ROM mode
        workspace.jump_to_offset(0x123456)

        # Assert observable outcomes
        assert workspace.current_mode == "rom"
        recorder.assert_emitted("mode_changed", times=1)
        assert recorder.get_args("mode_changed", 0) == ("rom",)

    def test_jump_to_offset_from_rom_mode_does_not_emit_mode_change(self, sprite_editor_workspace_real):
        """
        Verify jump_to_offset from ROM mode doesn't emit redundant mode change.
        """
        workspace = sprite_editor_workspace_real

        # Already in ROM mode
        assert workspace.current_mode == "rom"

        recorder = MultiSignalRecorder()
        recorder.connect_signal(workspace.mode_changed, "mode_changed")

        # Jump to offset - already in ROM mode
        workspace.jump_to_offset(0x100)

        # Should not emit mode_changed (already in ROM)
        recorder.assert_emitted("mode_changed", times=0)


class TestLoadRomModeSwitch:
    """
    Integration tests for ROM loading and automatic mode switching.

    Replaces: test_mode_switch_repro.py
    """

    def test_load_rom_switches_to_rom_mode(self, sprite_editor_workspace_real, tmp_path):
        """
        Verify loading a ROM switches to ROM mode and emits signals.

        Replaces: test_mode_switch_repro.py:test_load_rom_switches_mode
        """
        workspace = sprite_editor_workspace_real

        # Create test ROM file
        test_rom = tmp_path / "test.sfc"
        test_rom.write_bytes(b"\x00" * 32768)

        recorder = MultiSignalRecorder()
        recorder.connect_signal(workspace.mode_changed, "mode_changed")
        recorder.connect_signal(workspace.rom_workflow_controller.rom_info_updated, "rom_info_updated")

        # Start in VRAM mode
        workspace.set_mode("vram")
        recorder.clear()
        assert workspace.current_mode == "vram"

        # Mock ROM validation to pass
        mock_header = Mock(title="Test ROM", header_offset=0, mapping_type=None, checksum=0x1234)
        with (
            patch("core.rom_validator.ROMValidator.validate_rom_file", return_value=(True, "")),
            patch("core.rom_validator.ROMValidator.validate_rom_header", return_value=(mock_header, None)),
            patch("core.rom_validator.ROMValidator.verify_rom_checksum", return_value=True),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat", return_value=Mock(st_size=32768)),
        ):
            workspace.load_rom(str(test_rom))

        # Assert observable outcomes
        assert workspace.current_mode == "rom"
        recorder.assert_emitted("mode_changed", times=1)
        recorder.assert_emitted("rom_info_updated", times=1)

    def test_load_rom_from_rom_mode(self, sprite_editor_workspace_real, tmp_path):
        """
        Verify loading a ROM while already in ROM mode doesn't emit mode change.
        """
        workspace = sprite_editor_workspace_real

        # Create test ROM file
        test_rom = tmp_path / "test.sfc"
        test_rom.write_bytes(b"\x00" * 32768)

        # Already in ROM mode
        assert workspace.current_mode == "rom"

        recorder = MultiSignalRecorder()
        recorder.connect_signal(workspace.mode_changed, "mode_changed")
        recorder.connect_signal(workspace.rom_workflow_controller.rom_info_updated, "rom_info_updated")

        # Mock ROM validation to pass
        mock_header = Mock(title="Test ROM", header_offset=0, mapping_type=None, checksum=0x1234)
        with (
            patch("core.rom_validator.ROMValidator.validate_rom_file", return_value=(True, "")),
            patch("core.rom_validator.ROMValidator.validate_rom_header", return_value=(mock_header, None)),
            patch("core.rom_validator.ROMValidator.verify_rom_checksum", return_value=True),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat", return_value=Mock(st_size=32768)),
        ):
            workspace.load_rom(str(test_rom))

        # Should NOT emit mode_changed (already in ROM mode)
        recorder.assert_emitted("mode_changed", times=0)
        # Should still emit rom_info_updated
        recorder.assert_emitted("rom_info_updated", times=1)
