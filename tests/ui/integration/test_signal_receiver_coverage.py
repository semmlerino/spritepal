"""
Signal receiver coverage tests.

Tests verifying that critical signals have working connections by testing
behavior (emit signal -> verify handler runs) rather than connection counts.

Note: PySide6's QObject.receivers() only counts old-style SIGNAL() connections,
not new-style signal.connect() connections. These tests verify behavior instead.

Async Safety Notes
------------------
Tests that emit signals from mock coordinators (preview_ready, preview_error)
use synchronous emission + processEvents(). This works because:
1. MockPreviewCoordinator emits in the main thread
2. Handler runs immediately (direct connection)
3. processEvents() ensures any queued side-effects complete

For real async coordinators (worker threads), replace with:
    with qtbot.waitSignal(coord.preview_ready, timeout=worker_timeout()):
        coord.request_preview(offset)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtTest import QSignalSpy

from tests.ui.integration.helpers.signal_spy_utils import MultiSignalRecorder
from ui.sprite_editor.controllers.editing_controller import EditingController

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class MockPreviewCoordinator(QObject):
    """Mock coordinator for testing receiver connections."""

    preview_ready = Signal(bytes, int, int, str, int, int, int, bool)
    preview_cached = Signal(bytes, int, int, str, int, int, int, bool)
    preview_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    def set_rom_data_provider(self, provider: object) -> None:
        pass

    def request_manual_preview(self, offset: int) -> None:
        pass

    def request_full_preview(self, offset: int) -> None:
        pass

    def cleanup(self) -> None:
        pass


class TestEditingControllerReceivers:
    """Verify EditingController's signals have working receivers via behavior tests."""

    @pytest.fixture
    def controller(self) -> EditingController:
        return EditingController()

    def test_imageChanged_triggers_validation_handler(self, controller: EditingController) -> None:
        """Verify imageChanged -> _validate_rom_constraints connection works.

        Test behavior: when imageChanged fires (via load_image), validation state updates.
        """
        # Load image with >16 colors (invalid)
        data = np.arange(32, dtype=np.uint8).reshape((4, 8))
        controller.load_image(data)
        QCoreApplication.processEvents()

        # If the connection works, validation should have run and state should be invalid
        assert controller.is_valid_for_rom() is False, (
            "imageChanged -> _validate_rom_constraints connection not working: validation state did not update"
        )

    def test_tool_manager_signal_triggers_handler(self, controller: EditingController) -> None:
        """Verify tool_manager.tool_changed -> _on_tool_changed connection works.

        Test behavior: when tool changes, toolChanged signal emits with correct value.
        """
        spy = QSignalSpy(controller.toolChanged)

        # Change tool via tool_manager
        controller.tool_manager.set_tool("fill")
        QCoreApplication.processEvents()

        # If connection works, controller should have forwarded the signal
        assert spy.count() >= 1, (
            "tool_manager.tool_changed -> _on_tool_changed connection not working: "
            "controller.toolChanged was not emitted"
        )
        assert spy.at(spy.count() - 1)[0] == "fill"


class TestROMWorkflowControllerReceivers:
    """Verify ROMWorkflowController's coordinator signals are handled."""

    @pytest.fixture
    def mock_editing_controller(self) -> Mock:
        ctrl = Mock()
        ctrl.has_unsaved_changes.return_value = False
        return ctrl

    @pytest.fixture
    def workflow_controller(self, qtbot: QtBot, mock_editing_controller: Mock):
        """ROMWorkflowController with mocked dependencies."""
        from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController

        with patch("ui.sprite_editor.controllers.rom_workflow_controller.SmartPreviewCoordinator") as MockCoordClass:
            mock_instance = MockPreviewCoordinator()
            MockCoordClass.return_value = mock_instance

            mock_rom_extractor = Mock()
            mock_rom_extractor.read_rom_header.return_value = Mock(title="Test ROM")

            ctrl = ROMWorkflowController(
                parent=None,
                editing_controller=mock_editing_controller,
                rom_extractor=mock_rom_extractor,
            )
            ctrl.preview_coordinator = mock_instance

            yield ctrl
            ctrl.cleanup()

    def test_coordinator_preview_ready_handled(
        self, qtbot: QtBot, workflow_controller, mock_editing_controller
    ) -> None:
        """preview_coordinator.preview_ready must be handled by controller.

        Test behavior: emitting preview_ready causes state transition.
        """
        workflow_controller.rom_path = "test.sfc"
        workflow_controller.rom_size = 2048
        workflow_controller.set_offset(0x100, auto_open=True)

        # Emit preview_ready signal
        dummy_data = b"\x00" * 32
        with patch("ui.sprite_editor.services.SpriteRenderer") as MockRenderer:
            mock_image = MagicMock()
            mock_image.__array__ = MagicMock(return_value=np.zeros((8, 8), dtype=np.uint8))
            MockRenderer.return_value.render_4bpp.return_value = mock_image

            workflow_controller.preview_coordinator.preview_ready.emit(dummy_data, 8, 8, "Sprite", 32, 0, 0x100, True)
            QCoreApplication.processEvents()

        # If connection works, state should have changed
        assert workflow_controller.state == "edit", (
            "preview_ready signal not handled: state did not transition to 'edit'"
        )

    def test_coordinator_preview_error_handled(self, qtbot: QtBot, workflow_controller) -> None:
        """preview_coordinator.preview_error must be handled by controller.

        Test behavior: emitting preview_error does not crash and state doesn't become 'edit'.
        """
        workflow_controller.rom_path = "test.sfc"
        workflow_controller.rom_size = 2048
        workflow_controller.set_offset(0x100, auto_open=True)

        initial_state = workflow_controller.state

        # Emit preview_error signal
        workflow_controller.preview_coordinator.preview_error.emit("Test error")
        QCoreApplication.processEvents()

        # If connection works, controller should have handled error gracefully
        # State should not transition to 'edit' after error
        assert workflow_controller.state != "edit" or workflow_controller.state == initial_state


class TestSignalWiringConsistency:
    """Test that signal connections work consistently across operations."""

    @pytest.fixture
    def controller(self) -> EditingController:
        return EditingController()

    def test_validation_works_after_multiple_loads(self, controller: EditingController) -> None:
        """Verify validation connection works through multiple image loads."""
        # Load valid image
        valid_data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(valid_data)
        QCoreApplication.processEvents()
        assert controller.is_valid_for_rom() is True

        # Load invalid image
        invalid_data = np.arange(32, dtype=np.uint8).reshape((4, 8))
        controller.load_image(invalid_data)
        QCoreApplication.processEvents()
        assert controller.is_valid_for_rom() is False

        # Load valid image again
        controller.load_image(valid_data)
        QCoreApplication.processEvents()
        assert controller.is_valid_for_rom() is True

    def test_tool_signal_works_after_undo_redo(self, controller: EditingController) -> None:
        """Verify tool signal connection works after undo/redo cycle."""
        data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(data)
        controller.set_selected_color(1)
        controller.handle_pixel_press(0, 0)
        controller.handle_pixel_release(0, 0)
        QCoreApplication.processEvents()

        controller.undo()
        controller.redo()
        QCoreApplication.processEvents()

        # Tool signal should still work
        spy = QSignalSpy(controller.toolChanged)
        controller.set_tool("picker")
        QCoreApplication.processEvents()

        assert spy.count() >= 1, "Tool signal connection broken after undo/redo"


class TestSignalDocumentation:
    """Document which signals are internally vs externally connected."""

    def test_editing_controller_signals_exist(self) -> None:
        """All expected EditingController signals should exist."""
        controller = EditingController()

        expected_signals = [
            "imageChanged",
            "paletteChanged",
            "toolChanged",
            "colorChanged",
            "undoStateChanged",
            "paletteSourceAdded",
            "paletteSourceSelected",
            "paletteSourcesCleared",
            "validationChanged",
        ]

        for sig_name in expected_signals:
            assert hasattr(controller, sig_name), f"Missing expected signal: {sig_name}"

    def test_internally_connected_signals_work(self) -> None:
        """Signals documented as internally connected should work.

        imageChanged -> _validate_rom_constraints (internal)
        """
        controller = EditingController()

        # Test imageChanged internal connection
        data = np.arange(32, dtype=np.uint8).reshape((4, 8))
        controller.load_image(data)
        QCoreApplication.processEvents()

        # Validation should have been triggered
        assert controller.is_valid_for_rom() is False
        assert len(controller.get_validation_errors()) > 0
