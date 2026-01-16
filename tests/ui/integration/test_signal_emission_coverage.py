"""
Signal emission coverage tests.

Tests verifying that critical signals are actually emitted when expected actions
are performed. Uses QSignalSpy for emission counting and arg inspection.

Tier 1: Critical User-Facing Workflows
- preview_coordinator.preview_ready -> view update
- EditingController.imageChanged -> validationChanged
- undoStateChanged -> UI buttons

Async Safety Notes
------------------
These tests use `QCoreApplication.processEvents()` which is safe for:
- Synchronous signal emissions (EditingController, ToolManager)
- Mock objects that emit synchronously in the main thread

For tests that simulate what would be async in production (e.g., preview_ready
from a worker thread), the pattern works because mocks emit synchronously.
If swapped with real async components, use `qtbot.waitSignal()` instead:

    # ASYNC PATTERN (for real workers):
    with qtbot.waitSignal(coordinator.preview_ready, timeout=worker_timeout()):
        coordinator.request_preview(offset)  # Starts async work

    # SYNC PATTERN (current - for mocks):
    coordinator.preview_ready.emit(...)  # Mock emits synchronously
    QCoreApplication.processEvents()
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtTest import QSignalSpy

from tests.fixtures.timeouts import signal_timeout, worker_timeout
from tests.ui.integration.helpers.signal_spy_utils import MultiSignalRecorder
from ui.sprite_editor.controllers.editing_controller import EditingController

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class MockPreviewCoordinator(QObject):
    """Mock coordinator that exposes signals for testing."""

    preview_ready = Signal(bytes, int, int, str, int, int, int, bool)
    preview_cached = Signal(bytes, int, int, str, int, int, int, bool)
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
        self.request_full_preview_called = True
        self.last_requested_offset = offset

    def cleanup(self) -> None:
        pass


class TestEditingControllerEmissions:
    """Verify EditingController emits required signals during operations."""

    @pytest.fixture
    def controller(self) -> EditingController:
        """Create an EditingController for testing."""
        return EditingController()

    def test_load_image_emits_imageChanged(self, qtbot: QtBot, controller: EditingController) -> None:
        """imageChanged must emit after load_image call."""
        spy = QSignalSpy(controller.imageChanged)

        data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(data)
        QCoreApplication.processEvents()

        assert spy.count() >= 1, f"imageChanged not emitted after load_image. Expected >=1 emission, got {spy.count()}"

    def test_draw_emits_imageChanged_and_undoStateChanged(self, qtbot: QtBot, controller: EditingController) -> None:
        """Drawing must emit both imageChanged and undoStateChanged."""
        # Setup: load image first
        data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(data)
        QCoreApplication.processEvents()

        # Setup spies after initial load
        spy_image = QSignalSpy(controller.imageChanged)
        spy_undo = QSignalSpy(controller.undoStateChanged)

        # Draw a pixel
        controller.set_selected_color(1)
        controller.handle_pixel_press(0, 0)
        controller.handle_pixel_release(0, 0)
        QCoreApplication.processEvents()

        assert spy_image.count() >= 1, f"imageChanged not emitted after draw. Expected >=1, got {spy_image.count()}"
        assert spy_undo.count() >= 1, f"undoStateChanged not emitted after draw. Expected >=1, got {spy_undo.count()}"

    def test_imageChanged_triggers_validationChanged(self, qtbot: QtBot, controller: EditingController) -> None:
        """imageChanged must cause validationChanged to emit when validation state changes.

        Note: validationChanged only emits when the validation state CHANGES.
        Initial state: no image = valid. Loading an invalid image = invalid (state change).
        Signal emission order may vary by implementation (both may be emitted synchronously
        during load_image).
        """
        recorder = MultiSignalRecorder()
        recorder.connect_signal(controller.imageChanged, "imageChanged")
        recorder.connect_signal(controller.validationChanged, "validationChanged")

        # Load an INVALID image (>16 colors) - this causes state change from valid to invalid
        data = np.arange(32, dtype=np.uint8).reshape((4, 8))  # 32 unique colors
        controller.load_image(data)
        QCoreApplication.processEvents()

        # Verify both signals emitted (order may vary by implementation)
        recorder.assert_emitted("imageChanged", times=1)
        recorder.assert_emitted("validationChanged", times=1)
        # Both signals should be present; exact order is implementation detail
        order = recorder.emission_order()
        assert "imageChanged" in order, f"imageChanged not in emission order: {order}"
        assert "validationChanged" in order, f"validationChanged not in emission order: {order}"

    def test_undo_emits_required_signals(self, qtbot: QtBot, controller: EditingController) -> None:
        """undo() must emit imageChanged and undoStateChanged."""
        # Setup: create undoable state
        data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(data)
        controller.set_selected_color(1)
        controller.handle_pixel_press(0, 0)
        controller.handle_pixel_release(0, 0)
        QCoreApplication.processEvents()

        # Clear spies and perform undo
        spy_image = QSignalSpy(controller.imageChanged)
        spy_undo = QSignalSpy(controller.undoStateChanged)

        controller.undo()
        QCoreApplication.processEvents()

        assert spy_image.count() >= 1, "imageChanged not emitted after undo"
        assert spy_undo.count() >= 1, "undoStateChanged not emitted after undo"

    def test_set_palette_emits_paletteChanged(self, qtbot: QtBot, controller: EditingController) -> None:
        """set_palette must emit paletteChanged signal."""
        spy = QSignalSpy(controller.paletteChanged)

        colors = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]
        controller.set_palette(colors)
        QCoreApplication.processEvents()

        assert spy.count() >= 1, "paletteChanged not emitted after set_palette"


class TestROMWorkflowControllerEmissions:
    """Verify ROMWorkflowController emits required signals."""

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

    def test_load_rom_emits_rom_info_updated(self, qtbot: QtBot, workflow_controller) -> None:
        """load_rom must emit rom_info_updated signal with ROM title."""
        spy = QSignalSpy(workflow_controller.rom_info_updated)

        mock_header = Mock(title="Kirby Test", header_offset=0, mapping_type=None, checksum=0x1234)
        with (
            patch("core.rom_validator.ROMValidator.validate_rom_file", return_value=(True, "")),
            patch("core.rom_validator.ROMValidator.validate_rom_header", return_value=(mock_header, None)),
            patch("core.rom_validator.ROMValidator.verify_rom_checksum", return_value=True),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat", return_value=Mock(st_size=1024)),
        ):
            workflow_controller.load_rom("test.sfc")
            QCoreApplication.processEvents()

        assert spy.count() >= 1, "rom_info_updated not emitted after load_rom"
        assert spy.at(0)[0] == "Kirby Test"

    def test_set_offset_emits_offset_changed(self, qtbot: QtBot, workflow_controller) -> None:
        """set_offset must emit offset_changed signal."""
        workflow_controller.rom_path = "test.sfc"
        workflow_controller.rom_size = 2048

        spy = QSignalSpy(workflow_controller.offset_changed)

        workflow_controller.set_offset(0x100)
        QCoreApplication.processEvents()

        assert spy.count() >= 1, "offset_changed not emitted after set_offset"
        assert spy.at(0)[0] == 0x100

    def test_preview_coordinator_ready_emits_on_response(
        self, qtbot: QtBot, workflow_controller, mock_editing_controller
    ) -> None:
        """Verify preview_coordinator.preview_ready is handled correctly.

        This tests that when preview_coordinator emits preview_ready,
        the workflow controller processes it (state transition, image load).
        """
        workflow_controller.rom_path = "test.sfc"
        workflow_controller.rom_size = 2048
        workflow_controller.set_offset(0x100, auto_open=True)

        # Verify the coordinator received the request
        assert workflow_controller.preview_coordinator.request_full_preview_called

        # Now simulate the async response via signal
        dummy_data = b"\x00" * 32
        with patch("ui.sprite_editor.services.SpriteRenderer") as MockRenderer:
            mock_image = MagicMock()
            mock_image.__array__ = MagicMock(return_value=np.zeros((8, 8), dtype=np.uint8))
            MockRenderer.return_value.render_4bpp.return_value = mock_image

            # Emit the signal (simulating worker completion)
            workflow_controller.preview_coordinator.preview_ready.emit(
                dummy_data, 8, 8, "Sprite 100", 32, 0, 0x100, True
            )
            QCoreApplication.processEvents()

        # Verify state transitioned (observable effect of signal handling)
        assert workflow_controller.state == "edit", (
            f"State did not transition to 'edit' after preview_ready. Current: {workflow_controller.state}"
        )


class TestValidationSignalChain:
    """Verify the imageChanged -> validationChanged signal chain."""

    @pytest.fixture
    def controller(self) -> EditingController:
        return EditingController()

    def test_invalid_image_emits_validation_false(self, qtbot: QtBot, controller: EditingController) -> None:
        """Loading invalid image (>16 colors) must emit validationChanged(False, errors)."""
        recorder = MultiSignalRecorder()
        recorder.connect_signal(controller.validationChanged, "validationChanged")

        # Create image with >16 unique colors (invalid for 4bpp ROM sprite)
        # 256 unique values exceeds 16-color limit
        data = np.arange(256, dtype=np.uint8).reshape((16, 16))
        controller.load_image(data)
        QCoreApplication.processEvents()

        recorder.assert_emitted("validationChanged", times=1)
        args = recorder.get_args("validationChanged")
        assert args is not None
        is_valid, errors = args
        assert is_valid is False, "Expected validation to fail for >16 color image"
        assert len(errors) > 0, "Expected error messages for invalid image"

    def test_valid_image_emits_validation_true(self, qtbot: QtBot, controller: EditingController) -> None:
        """Loading valid image after invalid must emit validationChanged(True, []).

        Note: validationChanged only emits when state CHANGES. We must first
        put the controller in invalid state, then load a valid image.
        """
        # First load an invalid image to set state to invalid
        invalid_data = np.arange(32, dtype=np.uint8).reshape((4, 8))
        controller.load_image(invalid_data)
        QCoreApplication.processEvents()

        # Now setup recorder and load valid image
        recorder = MultiSignalRecorder()
        recorder.connect_signal(controller.validationChanged, "validationChanged")

        # Valid 4bpp image: all zeros (1 color)
        valid_data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(valid_data)
        QCoreApplication.processEvents()

        recorder.assert_emitted("validationChanged", times=1)
        args = recorder.get_args("validationChanged")
        assert args is not None
        is_valid, errors = args
        assert is_valid is True, f"Expected valid image, got errors: {errors}"
        assert len(errors) == 0, f"Expected no errors, got: {errors}"
