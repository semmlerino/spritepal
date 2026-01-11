from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


class MockPreviewCoordinator(QObject):
    """Mock coordinator that exposes signals."""

    preview_ready = Signal(bytes, int, int, str, int, int, int, bool)
    preview_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.request_manual_preview_called = False
        self.last_requested_offset = -1

    def set_rom_data_provider(self, provider):
        pass

    def request_manual_preview(self, offset):
        self.request_manual_preview_called = True
        self.last_requested_offset = offset

    def cleanup(self):
        pass


@pytest.fixture
def mock_editing_controller():
    ctrl = Mock()
    ctrl.has_unsaved_changes.return_value = False
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
        ctrl._mock_coordinator = mock_instance

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
    with (
        patch("core.rom_validator.ROMValidator.validate_rom_file", return_value=(True, "")),
        patch("core.rom_validator.ROMValidator.validate_rom_header", return_value=(Mock(title="Kirby Test"), None)),
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
    # Setup Spies
    spy_state = QSignalSpy(workflow_controller.workflow_state_changed)

    # Prerequisite: Load a ROM (to set rom_path)
    workflow_controller.rom_path = "dummy.sfc"
    workflow_controller.rom_size = 2048

    # Action 1: Set Offset with auto_open
    workflow_controller.set_offset(0x100, auto_open=True)

    # Verify preview requested (internal check to ensure flow is moving,
    # though strict interpretation might say NO internal checks,
    # but this is checking the Mock's state which is the test harness)
    assert workflow_controller._mock_coordinator.request_manual_preview_called is True
    assert workflow_controller._mock_coordinator.last_requested_offset == 0x100

    # State should still be 'preview' (or unset/initial) before preview returns
    assert spy_state.count() == 0

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
        workflow_controller._mock_coordinator.preview_ready.emit(dummy_data, 8, 8, "Sprite 100", 32, 0, 0x100, True)

    # Assert Final State
    # Should have transitioned to 'edit' because auto_open was True
    assert spy_state.count() > 0
    assert spy_state.at(0)[0] == "edit"

    # Verify EditingController was called (Integration point)
    mock_editing_controller.load_image.assert_called()


def test_preview_only_workflow(qtbot, workflow_controller, mock_editing_controller):
    """
    Test flow: set_offset(auto_open=False) -> preview ready -> NO state change to edit.
    """
    spy_state = QSignalSpy(workflow_controller.workflow_state_changed)

    workflow_controller.rom_path = "dummy.sfc"
    workflow_controller.rom_size = 2048

    # Action
    workflow_controller.set_offset(0x200, auto_open=False)

    # Trigger Preview
    dummy_data = b"\x00" * 32
    workflow_controller._mock_coordinator.preview_ready.emit(dummy_data, 8, 8, "Sprite 200", 32, 0, 0x200, True)

    # Assert
    # Should NOT have transitioned to 'edit'
    assert spy_state.count() == 0

    # Editing controller should NOT have been called
    mock_editing_controller.load_image.assert_not_called()


def test_state_transition_edit_to_preview(qtbot, workflow_controller, mock_editing_controller):
    """
    Test that setting offset while in 'edit' mode transitions back to 'preview'.
    """
    spy_state = QSignalSpy(workflow_controller.workflow_state_changed)

    workflow_controller.rom_path = "dummy.sfc"
    workflow_controller.rom_size = 2048

    # Force state to 'edit' (simulating previous open)
    workflow_controller.state = "edit"

    # Action: Change offset
    workflow_controller.set_offset(0x300)

    # Assert transition to 'preview'
    assert spy_state.count() > 0
    assert spy_state.at(0)[0] == "preview"
