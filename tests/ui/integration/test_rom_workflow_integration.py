"""
ROM Workflow Integration Tests.

These tests verify the integration between ROMWorkflowController and its
collaborators through signals and observable behavior.
"""

from datetime import datetime
from unittest.mock import ANY, MagicMock, Mock, patch

import numpy as np
import pytest
from PySide6.QtTest import QSignalSpy

from core.mesen_integration.log_watcher import CapturedOffset
from tests.infrastructure.mock_preview_coordinator import MockPreviewCoordinator
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


@pytest.fixture
def mock_editing_controller():
    ctrl = Mock()
    ctrl.has_unsaved_changes.return_value = False
    # Must return None (not Mock) for subscript safety in open_in_editor
    ctrl.get_current_palette_source.return_value = None
    ctrl.get_palette_sources.return_value = {}
    return ctrl


@pytest.fixture
def workflow_controller(qtbot, mock_editing_controller):
    """
    Fixture for ROMWorkflowController with mocked dependencies.
    Uses MockPreviewCoordinator from tests/infrastructure for signal injection.
    """
    with patch("ui.sprite_editor.controllers.rom_workflow_controller.SmartPreviewCoordinator") as MockCoordClass:
        # Use our signal-enabled mock
        mock_instance = MockPreviewCoordinator()
        MockCoordClass.return_value = mock_instance

        # Mock other dependencies
        mock_rom_extractor = Mock()
        mock_rom_extractor.read_rom_header.return_value = Mock(title="Test ROM")

        ctrl = ROMWorkflowController(
            parent=None, editing_controller=mock_editing_controller, rom_extractor=mock_rom_extractor
        )

        # Expose the coordinator mock for tests
        ctrl.preview_coordinator = mock_instance

        yield ctrl

        ctrl.cleanup()


@pytest.fixture
def test_rom_file(tmp_path) -> str:
    """Create a minimal 1KB test ROM file."""
    rom_path = tmp_path / "test_rom.sfc"
    rom_data = b"SNES" + b"\x00" * (1024 - 4)
    rom_path.write_bytes(rom_data)
    return str(rom_path)


def test_load_rom_emits_info(qtbot, workflow_controller, test_rom_file):
    """
    Test that loading a valid ROM emits rom_info_updated signal.
    """
    spy_info = QSignalSpy(workflow_controller.rom_info_updated)

    mock_header = Mock(title="Kirby Test", header_offset=0, mapping_type=None, checksum=0x1234)
    with (
        patch("core.rom_validator.ROMValidator.validate_rom_file", return_value=(True, "")),
        patch("core.rom_validator.ROMValidator.validate_rom_header", return_value=(mock_header, None)),
        patch("core.rom_validator.ROMValidator.verify_rom_checksum", return_value=True),
    ):
        workflow_controller.load_rom(test_rom_file)

        assert spy_info.count() == 1
        assert spy_info.at(0)[0] == "Kirby Test"


def test_auto_open_workflow(qtbot, workflow_controller, mock_editing_controller):
    """
    Test the full flow: set_offset(auto_open=True) -> preview ready -> open in editor -> state change.
    """
    workflow_controller.rom_path = "dummy.sfc"
    workflow_controller.rom_size = 2048

    # Set offset with auto_open
    workflow_controller.set_offset(0x100, auto_open=True)

    # Verify full preview requested (auto_open=True uses full decompression)
    assert workflow_controller.preview_coordinator.request_full_preview_called is True
    assert workflow_controller.preview_coordinator.last_requested_offset == 0x100

    # State should not be 'edit' yet
    assert workflow_controller.state != "edit"

    # Emit preview ready using helper method
    with patch("ui.sprite_editor.services.SpriteRenderer") as MockRenderer:
        mock_image = MagicMock()
        mock_image.__array__ = MagicMock(return_value=np.zeros((8, 8), dtype=np.uint8))
        MockRenderer.return_value.render_4bpp.return_value = mock_image

        workflow_controller.preview_coordinator.emit_success(offset=0x100)

    # Should have transitioned to 'edit'
    assert workflow_controller.state == "edit"
    mock_editing_controller.load_image.assert_called()


def test_preview_only_workflow(qtbot, workflow_controller, mock_editing_controller):
    """
    Test flow: set_offset(auto_open=False) -> preview ready -> NO state change to edit.
    """
    workflow_controller.rom_path = "dummy.sfc"
    workflow_controller.rom_size = 2048

    workflow_controller.set_offset(0x200, auto_open=False)

    # Emit preview ready
    workflow_controller.preview_coordinator.emit_success(offset=0x200)

    # Should NOT have transitioned to 'edit'
    assert workflow_controller.state != "edit"
    mock_editing_controller.load_image.assert_not_called()


def test_state_transition_edit_to_preview(qtbot, workflow_controller, mock_editing_controller):
    """
    Test that setting offset while in 'edit' mode transitions back to 'preview'.
    """
    workflow_controller.rom_path = "dummy.sfc"
    workflow_controller.rom_size = 2048

    # Force state to 'edit'
    workflow_controller.state = "edit"

    # Change offset
    workflow_controller.set_offset(0x300)

    # Should transition to 'preview'
    assert workflow_controller.state == "preview"


def test_revert_to_original_forces_rom_reload():
    """
    Test that revert_to_original() triggers a fresh reload from ROM
    by calling set_offset(..., auto_open=True).
    """
    mock_editing = MagicMock()
    mock_editing.has_unsaved_changes.return_value = False

    with patch("ui.sprite_editor.controllers.rom_workflow_controller.SmartPreviewCoordinator"):
        controller = ROMWorkflowController(None, mock_editing)
        controller.rom_path = "dummy.sfc"
        controller.current_offset = 0x1000
        controller.state = "edit"
        controller.current_tile_data = b"\x00" * 32

        with patch.object(controller, "set_offset") as mock_set_offset:
            controller.revert_to_original()
            mock_set_offset.assert_called_once_with(0x1000, auto_open=True)

        assert mock_editing.clear_undo_history.called
        controller.cleanup()


# =============================================================================
# Regression tests for desync issues
# =============================================================================


class TestROMWorkflowControllerRegression:
    """Regression tests for ROMWorkflowController desync issues."""

    @pytest.fixture
    def mock_view(self):
        view = MagicMock()
        view.asset_browser = MagicMock()
        return view

    @pytest.fixture
    def mock_log_watcher(self):
        watcher = MagicMock()
        watcher.recent_captures = []
        watcher.load_persistent_clicks.return_value = []
        return watcher

    @pytest.fixture
    def controller(self, mock_view, mock_log_watcher):
        mock_editing_ctrl = MagicMock()
        mock_rom_cache = MagicMock()
        mock_rom_extractor = MagicMock()
        mock_sprite_library = MagicMock()

        ctrl = ROMWorkflowController(
            parent=None,
            editing_controller=mock_editing_ctrl,
            rom_cache=mock_rom_cache,
            rom_extractor=mock_rom_extractor,
            log_watcher=mock_log_watcher,
            sprite_library=mock_sprite_library,
        )
        yield ctrl
        ctrl.cleanup()

    @pytest.fixture
    def regression_test_rom_file(self, tmp_path) -> str:
        """Create a 1MB test ROM file for regression tests."""
        rom_path = tmp_path / "test_rom.sfc"
        rom_data = b"SNES" + b"\x00" * (1024 * 1024 - 4)
        rom_path.write_bytes(rom_data)
        return str(rom_path)

    @patch("core.rom_validator.ROMValidator.validate_rom_file")
    @patch("core.rom_validator.ROMValidator.validate_rom_header")
    @patch("core.rom_validator.ROMValidator.verify_rom_checksum")
    def test_mesen_captures_lost_on_rom_load(
        self,
        mock_verify_checksum,
        mock_validate_header,
        mock_validate_file,
        controller,
        mock_view,
        mock_log_watcher,
        regression_test_rom_file,
    ):
        """
        Reproduction test for UI-logic desync:
        Mesen captures are re-populated after loading a new ROM.
        """
        mock_validate_file.return_value = (True, "")
        mock_verify_checksum.return_value = True
        mock_header = MagicMock()
        mock_header.title = "Test ROM"
        mock_header.mapping_type = "LoROM"
        mock_header.header_offset = 0
        mock_header.checksum = 0x1234
        mock_validate_header.return_value = (mock_header, None)

        # Setup: 1 capture in LogWatcher
        capture = CapturedOffset(
            offset=0x123456, frame=123, timestamp=datetime.now(), raw_line="FILE OFFSET: 0x123456 frame=123"
        )
        mock_log_watcher.recent_captures = [capture]

        # Connect view -> should populate browser
        controller.set_view(mock_view)
        mock_view.add_mesen_capture.assert_called_with(ANY, 0x123456, frame=123, update_if_exists=False)
        mock_view.add_mesen_capture.reset_mock()

        # Load a new ROM (using real test file)
        controller.load_rom(regression_test_rom_file)

        # Verify re-population
        mock_view.add_mesen_capture.assert_called_with(ANY, 0x123456, frame=123, update_if_exists=False)


class TestThumbnailRequeueOnAlignment:
    """Tests for thumbnail re-queuing when offset alignment occurs."""

    @pytest.fixture
    def mock_view(self):
        view = MagicMock()
        view.asset_browser = MagicMock()
        view.asset_browser.update_sprite_offset.return_value = True
        return view

    @pytest.fixture
    def controller_with_mock_coordinator(self, mock_view):
        """Controller with MockPreviewCoordinator for signal emission."""
        with patch("ui.sprite_editor.controllers.rom_workflow_controller.SmartPreviewCoordinator") as MockCoordClass:
            mock_coordinator = MockPreviewCoordinator()
            MockCoordClass.return_value = mock_coordinator

            mock_editing_ctrl = MagicMock()
            mock_rom_cache = MagicMock()
            mock_rom_extractor = MagicMock()
            mock_log_watcher = MagicMock()
            mock_log_watcher.recent_captures = []
            mock_log_watcher.load_persistent_clicks.return_value = []
            mock_sprite_library = MagicMock()

            ctrl = ROMWorkflowController(
                parent=None,
                editing_controller=mock_editing_ctrl,
                rom_cache=mock_rom_cache,
                rom_extractor=mock_rom_extractor,
                log_watcher=mock_log_watcher,
                sprite_library=mock_sprite_library,
            )
            ctrl.preview_coordinator = mock_coordinator
            ctrl.set_view(mock_view)
            ctrl.current_offset = 0x1000

            yield ctrl, mock_coordinator

            ctrl.cleanup()

    def test_preview_ready_signal_triggers_offset_update_on_alignment(
        self,
        controller_with_mock_coordinator,
        mock_view,
    ):
        """Verify preview_ready signal triggers update_sprite_offset when offset is adjusted.

        This tests the integration through signals rather than calling _on_preview_ready directly.
        """
        controller, mock_coordinator = controller_with_mock_coordinator
        actual_offset = 0x1004  # Adjusted from 0x1000

        # Emit signal with adjusted offset
        mock_coordinator.emit_success(
            offset=actual_offset,
            tile_data=b"\x00" * 32,
            width=8,
            height=8,
        )

        # Verify asset browser received offset update
        mock_view.asset_browser.update_sprite_offset.assert_called_with(0x1000, 0x1004)

    def test_offset_changed_handler_queues_thumbnail(
        self,
        controller_with_mock_coordinator,
    ):
        """Verify _on_item_offset_changed handler queues thumbnail for new offset."""
        controller, _ = controller_with_mock_coordinator
        mock_thumb_ctrl = MagicMock()
        controller._thumbnail_controller = mock_thumb_ctrl

        controller._on_item_offset_changed(0x1000, 0x1004)

        mock_thumb_ctrl.queue_thumbnail.assert_called_with(0x1004)
