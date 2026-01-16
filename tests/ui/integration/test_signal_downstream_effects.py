"""
Signal downstream effects tests.

Tests verifying that signals not only emit, but cause expected downstream
behavior (state changes, UI updates, etc.). Uses both QSignalSpy for emission
verification AND state assertions for observable effects.

Rule of thumb from plan:
- QSignalSpy alone for "did it emit?"
- State assertions alone when signal is implementation detail
- BOTH for integration tests where signals must cause observable effects
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtTest import QSignalSpy

from tests.fixtures.timeouts import signal_timeout
from tests.ui.integration.helpers.signal_spy_utils import MultiSignalRecorder
from ui.sprite_editor.controllers.editing_controller import EditingController

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class MockPreviewCoordinator(QObject):
    """Mock coordinator for testing signal downstream effects."""

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


class TestImageChangedDownstream:
    """Test downstream effects of imageChanged signal."""

    @pytest.fixture
    def controller(self) -> EditingController:
        return EditingController()

    def test_imageChanged_triggers_validation_state_update(self, qtbot: QtBot, controller: EditingController) -> None:
        """imageChanged must update internal validation state (observable effect)."""
        # Load invalid image (>16 colors, wrong dimensions)
        data = np.arange(32, dtype=np.uint8).reshape((4, 8))  # 32 colors, 4x8 (not 8-aligned height)
        controller.load_image(data)
        QCoreApplication.processEvents()

        # Observable effect: validation state should reflect invalid image
        assert controller.is_valid_for_rom() is False
        assert len(controller.get_validation_errors()) > 0

    def test_imageChanged_after_draw_updates_data(self, qtbot: QtBot, controller: EditingController) -> None:
        """Drawing must emit imageChanged AND update accessible data."""
        # Setup
        data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(data)
        QCoreApplication.processEvents()

        spy = QSignalSpy(controller.imageChanged)

        # Action: draw pixel
        controller.set_selected_color(5)
        controller.handle_pixel_press(3, 3)
        controller.handle_pixel_release(3, 3)
        QCoreApplication.processEvents()

        # Signal emitted
        assert spy.count() >= 1, "imageChanged not emitted after draw"

        # Observable effect: data changed
        result = controller.get_image_data()
        assert result is not None
        assert result[3, 3] == 5, f"Pixel value not updated. Got {result[3, 3]}"


class TestUndoStateDownstream:
    """Test downstream effects of undoStateChanged signal."""

    @pytest.fixture
    def controller(self) -> EditingController:
        return EditingController()

    def test_undoStateChanged_reflects_undo_availability(self, qtbot: QtBot, controller: EditingController) -> None:
        """undoStateChanged(can_undo, can_redo) must match has_unsaved_changes()."""
        recorder = MultiSignalRecorder()
        recorder.connect_signal(controller.undoStateChanged, "undoStateChanged")

        # Initial state: nothing to undo
        data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(data)
        QCoreApplication.processEvents()

        # Observable effect: no unsaved changes yet
        assert controller.has_unsaved_changes() is False

        # Draw creates unsaved changes
        recorder.clear()
        controller.set_selected_color(1)
        controller.handle_pixel_press(0, 0)
        controller.handle_pixel_release(0, 0)
        QCoreApplication.processEvents()

        # Signal emitted with can_undo=True
        recorder.assert_emitted("undoStateChanged", times=1)
        args = recorder.get_args("undoStateChanged")
        assert args is not None
        can_undo, can_redo = args
        assert can_undo is True, "undoStateChanged should report can_undo=True"
        assert can_redo is False, "undoStateChanged should report can_redo=False"

        # Observable effect: now has unsaved changes
        assert controller.has_unsaved_changes() is True

    def test_undo_restores_previous_state(self, qtbot: QtBot, controller: EditingController) -> None:
        """Undo must emit signals AND restore observable state."""
        # Setup
        data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(data)
        controller.set_selected_color(7)
        controller.handle_pixel_press(2, 2)
        controller.handle_pixel_release(2, 2)
        QCoreApplication.processEvents()

        # Verify draw worked
        result_before = controller.get_image_data()
        assert result_before is not None
        assert result_before[2, 2] == 7

        spy_image = QSignalSpy(controller.imageChanged)
        spy_undo = QSignalSpy(controller.undoStateChanged)

        # Perform undo
        controller.undo()
        QCoreApplication.processEvents()

        # Signals emitted
        assert spy_image.count() >= 1
        assert spy_undo.count() >= 1

        # Observable effect: data restored
        result_after = controller.get_image_data()
        assert result_after is not None
        assert result_after[2, 2] == 0, f"Undo did not restore pixel. Got {result_after[2, 2]}"


class TestValidationDownstream:
    """Test downstream effects of validationChanged signal."""

    @pytest.fixture
    def controller(self) -> EditingController:
        return EditingController()

    def test_validationChanged_updates_queryable_state(self, qtbot: QtBot, controller: EditingController) -> None:
        """validationChanged emission must match is_valid_for_rom() and get_validation_errors().

        Note: validationChanged only emits when state CHANGES. We load an invalid
        image to trigger a state change from valid (no image) to invalid.
        """
        recorder = MultiSignalRecorder()
        recorder.connect_signal(controller.validationChanged, "validationChanged")

        # Load invalid image to trigger state change
        data = np.arange(32, dtype=np.uint8).reshape((4, 8))  # 32 colors, wrong dims
        controller.load_image(data)
        QCoreApplication.processEvents()

        # Signal emitted
        recorder.assert_emitted("validationChanged", times=1)
        args = recorder.get_args("validationChanged")
        assert args is not None
        sig_valid, sig_errors = args

        # Observable state must match signal args
        assert controller.is_valid_for_rom() == sig_valid
        assert controller.get_validation_errors() == list(sig_errors)

    def test_validation_fails_for_too_many_colors(self, qtbot: QtBot, controller: EditingController) -> None:
        """Image with >16 colors must fail validation (signal + state)."""
        recorder = MultiSignalRecorder()
        recorder.connect_signal(controller.validationChanged, "validationChanged")

        # 256 unique colors (way more than 16)
        data = np.arange(256, dtype=np.uint8).reshape((16, 16))
        controller.load_image(data)
        QCoreApplication.processEvents()

        # Signal reports invalid
        args = recorder.get_args("validationChanged")
        assert args is not None
        sig_valid, sig_errors = args
        assert sig_valid is False

        # State also reports invalid
        assert controller.is_valid_for_rom() is False
        errors = controller.get_validation_errors()
        assert len(errors) > 0
        # Should mention color count
        assert any("color" in e.lower() for e in errors), f"Expected color error, got: {errors}"


class TestPreviewReadyDownstream:
    """Test downstream effects of preview_ready signal on workflow controller."""

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

    def test_preview_ready_transitions_state_to_edit(
        self, qtbot: QtBot, workflow_controller, mock_editing_controller
    ) -> None:
        """preview_ready with auto_open must transition state to 'edit'."""
        workflow_controller.rom_path = "test.sfc"
        workflow_controller.rom_size = 2048

        # Request with auto_open=True
        workflow_controller.set_offset(0x100, auto_open=True)

        # State before signal
        assert workflow_controller.state != "edit"

        # Emit preview_ready
        dummy_data = b"\x00" * 32
        with patch("ui.sprite_editor.services.SpriteRenderer") as MockRenderer:
            mock_image = MagicMock()
            mock_image.__array__ = MagicMock(return_value=np.zeros((8, 8), dtype=np.uint8))
            MockRenderer.return_value.render_4bpp.return_value = mock_image

            workflow_controller.preview_coordinator.preview_ready.emit(dummy_data, 8, 8, "Sprite", 32, 0, 0x100, True)
            QCoreApplication.processEvents()

        # Observable effect: state changed
        assert workflow_controller.state == "edit"

    def test_preview_ready_loads_image_in_editor(
        self, qtbot: QtBot, workflow_controller, mock_editing_controller
    ) -> None:
        """preview_ready with auto_open must call editing_controller.load_image()."""
        workflow_controller.rom_path = "test.sfc"
        workflow_controller.rom_size = 2048
        workflow_controller.set_offset(0x100, auto_open=True)

        # Emit preview_ready
        dummy_data = b"\x00" * 32
        with patch("ui.sprite_editor.services.SpriteRenderer") as MockRenderer:
            mock_image = MagicMock()
            mock_image.__array__ = MagicMock(return_value=np.zeros((8, 8), dtype=np.uint8))
            MockRenderer.return_value.render_4bpp.return_value = mock_image

            workflow_controller.preview_coordinator.preview_ready.emit(dummy_data, 8, 8, "Sprite", 32, 0, 0x100, True)
            QCoreApplication.processEvents()

        # Observable effect: editing controller received image
        mock_editing_controller.load_image.assert_called()

    def test_preview_error_does_not_transition_state(
        self, qtbot: QtBot, workflow_controller, mock_editing_controller
    ) -> None:
        """preview_error must NOT transition state to 'edit'."""
        workflow_controller.rom_path = "test.sfc"
        workflow_controller.rom_size = 2048
        workflow_controller.set_offset(0x100, auto_open=True)

        initial_state = workflow_controller.state

        # Emit preview_error
        workflow_controller.preview_coordinator.preview_error.emit("Decompression failed")
        QCoreApplication.processEvents()

        # State should NOT have changed to edit
        assert workflow_controller.state != "edit" or workflow_controller.state == initial_state


class TestToolChangedDownstream:
    """Test downstream effects of toolChanged signal."""

    @pytest.fixture
    def controller(self) -> EditingController:
        return EditingController()

    def test_toolChanged_updates_current_tool_name(self, qtbot: QtBot, controller: EditingController) -> None:
        """toolChanged emission must match get_current_tool_name()."""
        spy = QSignalSpy(controller.toolChanged)

        controller.set_tool("fill")
        QCoreApplication.processEvents()

        # Signal emitted with new tool name
        assert spy.count() >= 1
        assert spy.at(spy.count() - 1)[0] == "fill"

        # Observable state matches
        assert controller.get_current_tool_name() == "fill"

    def test_tool_affects_drawing_behavior(self, qtbot: QtBot, controller: EditingController) -> None:
        """Different tools should produce different drawing results."""
        # Setup
        data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(data)
        QCoreApplication.processEvents()

        # Fill with color 1 should fill entire area
        controller.set_tool("fill")
        controller.set_selected_color(1)
        controller.handle_pixel_press(0, 0)
        controller.handle_pixel_release(0, 0)
        QCoreApplication.processEvents()

        result = controller.get_image_data()
        assert result is not None
        # Fill should have changed multiple pixels (all connected zeros)
        assert np.sum(result == 1) > 1, "Fill tool should change multiple pixels"


class TestColorChangedDownstream:
    """Test downstream effects of colorChanged signal."""

    @pytest.fixture
    def controller(self) -> EditingController:
        return EditingController()

    def test_colorChanged_updates_selected_color(self, qtbot: QtBot, controller: EditingController) -> None:
        """colorChanged emission must match get_selected_color()."""
        spy = QSignalSpy(controller.colorChanged)

        controller.set_selected_color(7)
        QCoreApplication.processEvents()

        # Signal emitted
        assert spy.count() >= 1
        assert spy.at(spy.count() - 1)[0] == 7

        # Observable state matches
        assert controller.get_selected_color() == 7

    def test_selected_color_affects_drawing(self, qtbot: QtBot, controller: EditingController) -> None:
        """Drawing uses the selected color."""
        data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(data)
        controller.set_tool("pencil")
        controller.set_selected_color(9)
        QCoreApplication.processEvents()

        # Draw a pixel
        controller.handle_pixel_press(4, 4)
        controller.handle_pixel_release(4, 4)
        QCoreApplication.processEvents()

        result = controller.get_image_data()
        assert result is not None
        assert result[4, 4] == 9, f"Drawing should use selected color 9, got {result[4, 4]}"
