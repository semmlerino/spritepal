from datetime import datetime
from unittest.mock import ANY, MagicMock, Mock, patch

import numpy as np
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

from core.mesen_integration.log_watcher import CapturedOffset
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


class MockPreviewCoordinator(QObject):
    """Mock coordinator that exposes signals."""

    preview_ready = Signal(bytes, int, int, str, int, int, int, bool)
    preview_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.request_manual_preview_called = False
        self.request_full_preview_called = False
        self.last_requested_offset = -1

    def set_rom_data_provider(self, provider):
        pass

    def request_manual_preview(self, offset):
        self.request_manual_preview_called = True
        self.last_requested_offset = offset

    def request_full_preview(self, offset):
        """Request full decompression preview (not truncated to 4KB)."""
        self.request_full_preview_called = True
        self.last_requested_offset = offset

    def cleanup(self):
        pass


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
    Patches SmartPreviewCoordinator to allow signal injection.
    """
    with patch("ui.sprite_editor.controllers.rom_workflow_controller.SmartPreviewCoordinator") as MockCoordClass:
        # Configure the mock class to return our signal-enabled mock instance
        # We need to keep a reference to the instance to emit signals from test
        mock_instance = MockPreviewCoordinator()
        MockCoordClass.return_value = mock_instance

        # Mock other dependencies
        mock_rom_extractor = Mock()
        mock_rom_extractor.read_rom_header.return_value = Mock(title="Test ROM")

        ctrl = ROMWorkflowController(
            parent=None, editing_controller=mock_editing_controller, rom_extractor=mock_rom_extractor
        )

        # Expose the coordinator mock for tests to drive
        # Use the public attribute name from ROMWorkflowController
        ctrl.preview_coordinator = mock_instance

        yield ctrl

        # Cleanup: stop any running workers
        ctrl.cleanup()


def test_load_rom_emits_info(qtbot, workflow_controller):
    """
    Test that loading a valid ROM emits rom_info_updated signal.
    """
    # Setup Spy
    spy_info = QSignalSpy(workflow_controller.rom_info_updated)

    # Mock validation to pass
    mock_header = Mock(title="Kirby Test", header_offset=0, mapping_type=None, checksum=0x1234)
    with (
        patch("core.rom_validator.ROMValidator.validate_rom_file", return_value=(True, "")),
        patch("core.rom_validator.ROMValidator.validate_rom_header", return_value=(mock_header, None)),
        patch("core.rom_validator.ROMValidator.verify_rom_checksum", return_value=True),
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.stat", return_value=Mock(st_size=1024)),
    ):
        # Action
        workflow_controller.load_rom("dummy.sfc")

        # Assert Signal
        assert spy_info.count() == 1
        assert spy_info.at(0)[0] == "Kirby Test"


def test_auto_open_workflow(qtbot, workflow_controller, mock_editing_controller):
    """
    Test the full flow: set_offset(auto_open=True) -> preview ready -> open in editor -> state change.
    """
    # Prerequisite: Load a ROM (to set rom_path)
    workflow_controller.rom_path = "dummy.sfc"
    workflow_controller.rom_size = 2048

    # Action 1: Set Offset with auto_open
    workflow_controller.set_offset(0x100, auto_open=True)

    # Verify full preview requested (auto_open=True uses full decompression)
    assert workflow_controller.preview_coordinator.request_full_preview_called is True
    assert workflow_controller.preview_coordinator.last_requested_offset == 0x100

    # State should still be 'preview' (or unset/initial) before preview returns
    assert workflow_controller.state != "edit"

    # Action 2: Simulate Preview Ready (Async response)
    # Mock SpriteRenderer to avoid PIL image processing (causes thread-safety issues)
    dummy_data = b"\x00" * 32
    with patch("ui.sprite_editor.services.SpriteRenderer") as MockRenderer:
        # Configure mock to return a fake PIL-like image that converts to numpy
        mock_image = MagicMock()
        # Must return an actual numpy array for np.array() conversion
        mock_image.__array__ = MagicMock(return_value=np.zeros((8, 8), dtype=np.uint8))
        MockRenderer.return_value.render_4bpp.return_value = mock_image

        # signature: tile_data, width, height, sprite_name, compressed_size, slack_size, actual_offset, hal_succeeded
        workflow_controller.preview_coordinator.preview_ready.emit(dummy_data, 8, 8, "Sprite 100", 32, 0, 0x100, True)

    # Assert Final State
    # Should have transitioned to 'edit' because auto_open was True
    assert workflow_controller.state == "edit"

    # Verify EditingController was called (Integration point)
    mock_editing_controller.load_image.assert_called()


def test_preview_only_workflow(qtbot, workflow_controller, mock_editing_controller):
    """
    Test flow: set_offset(auto_open=False) -> preview ready -> NO state change to edit.
    """
    workflow_controller.rom_path = "dummy.sfc"
    workflow_controller.rom_size = 2048

    # Action
    workflow_controller.set_offset(0x200, auto_open=False)

    # Trigger Preview
    dummy_data = b"\x00" * 32
    workflow_controller.preview_coordinator.preview_ready.emit(dummy_data, 8, 8, "Sprite 200", 32, 0, 0x200, True)

    # Assert
    # Should NOT have transitioned to 'edit'
    assert workflow_controller.state != "edit"

    # Editing controller should NOT have been called
    mock_editing_controller.load_image.assert_not_called()


def test_state_transition_edit_to_preview(qtbot, workflow_controller, mock_editing_controller):
    """
    Test that setting offset while in 'edit' mode transitions back to 'preview'.
    """
    workflow_controller.rom_path = "dummy.sfc"
    workflow_controller.rom_size = 2048

    # Force state to 'edit' (simulating previous open)
    workflow_controller.state = "edit"

    # Action: Change offset
    workflow_controller.set_offset(0x300)

    # Assert transition to 'preview'
    assert workflow_controller.state == "preview"


def test_revert_to_original_forces_rom_reload():
    """
    Test that revert_to_original() triggers a fresh reload from ROM
    by calling set_offset(..., auto_open=True) instead of using
    possibly dirty internal cache.

    (Merged from tests/ui/test_revert_desync.py)
    """
    # Setup
    mock_editing = MagicMock()
    mock_editing.has_unsaved_changes.return_value = False

    # Patch SmartPreviewCoordinator to avoid Qt worker initialization
    with patch("ui.sprite_editor.controllers.rom_workflow_controller.SmartPreviewCoordinator"):
        controller = ROMWorkflowController(None, mock_editing)
        controller.rom_path = "dummy.sfc"
        controller.current_offset = 0x1000
        controller.state = "edit"
        # Must have tile data to revert
        controller.current_tile_data = b"\x00" * 32

        # Action: Click "Revert to Original"
        with patch.object(controller, "set_offset") as mock_set_offset:
            controller.revert_to_original()

            # Verify fix: it calls set_offset with auto_open=True
            mock_set_offset.assert_called_once_with(0x1000, auto_open=True)

        # Verify undo history was cleared (via clear_undo_history which emits signal)
        assert mock_editing.clear_undo_history.called

        # Cleanup
        controller.cleanup()


# =============================================================================
# Merged from tests/ui/rom_extraction/test_rom_workflow_controller.py
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
        # Mock dependencies
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

    @patch("core.rom_validator.ROMValidator.validate_rom_file")
    @patch("core.rom_validator.ROMValidator.validate_rom_header")
    @patch("core.rom_validator.ROMValidator.verify_rom_checksum")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.stat")
    def test_mesen_captures_lost_on_rom_load(
        self,
        mock_stat,
        mock_exists,
        mock_verify_checksum,
        mock_validate_header,
        mock_validate_file,
        controller,
        mock_view,
        mock_log_watcher,
    ):
        """
        Reproduction test for UI-logic desync:
        Mesen captures are cleared from the Asset Browser when loading a new ROM
        and are not re-populated, even though they persist in LogWatcher.
        """
        # Setup mocks for ROM loading
        mock_exists.return_value = True
        mock_stat.return_value.st_size = 1024 * 1024
        mock_validate_file.return_value = (True, "")
        mock_verify_checksum.return_value = True
        mock_header = MagicMock()
        mock_header.title = "Test ROM"
        mock_header.mapping_type = "LoROM"
        mock_header.header_offset = 0
        mock_header.checksum = 0x1234
        mock_validate_header.return_value = (mock_header, None)

        # 1. Setup initial state: 1 capture in LogWatcher
        capture = CapturedOffset(
            offset=0x123456, frame=123, timestamp=datetime.now(), raw_line="FILE OFFSET: 0x123456 frame=123"
        )
        mock_log_watcher.recent_captures = [capture]

        # 2. Connect view -> should populate browser
        controller.set_view(mock_view)

        # Verify initial population - now includes frame and update_if_exists parameters
        mock_view.add_mesen_capture.assert_called_with(ANY, 0x123456, frame=123, update_if_exists=False)
        mock_view.add_mesen_capture.reset_mock()

        # 3. Load a new ROM
        controller.load_rom("test.sfc")

        # Verify re-population
        # The controller should re-add the existing Mesen captures after clearing
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
    def controller(self, mock_view):
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
        ctrl.set_view(mock_view)
        ctrl.current_offset = 0x1000
        yield ctrl
        ctrl.cleanup()

    def test_preview_calls_update_sprite_offset_on_alignment(
        self,
        controller,
        mock_view,
    ):
        """Verify _on_preview_ready calls update_sprite_offset when offset is adjusted."""
        tile_data = b"\x00" * 32
        actual_offset = 0x1004  # Adjusted from 0x1000

        controller._on_preview_ready(
            tile_data=tile_data,
            width=8,
            height=8,
            sprite_name="Test Sprite",
            compressed_size=32,
            slack_size=0,
            actual_offset=actual_offset,
            hal_succeeded=True,
        )

        mock_view.asset_browser.update_sprite_offset.assert_called_with(0x1000, 0x1004)

    def test_offset_changed_handler_queues_thumbnail(
        self,
        controller,
    ):
        """Verify _on_item_offset_changed handler queues thumbnail for new offset."""
        mock_thumb_ctrl = MagicMock()
        controller._thumbnail_controller = mock_thumb_ctrl

        controller._on_item_offset_changed(0x1000, 0x1004)

        mock_thumb_ctrl.queue_thumbnail.assert_called_with(0x1004)
