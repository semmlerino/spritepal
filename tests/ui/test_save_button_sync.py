"""Test save button synchronization with validation state."""

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject, Signal

from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


class MockEditingController(QObject):
    """Mock editing controller with signals for testing."""

    validationChanged = Signal(bool, list)
    paletteSourceSelected = Signal(str)
    paletteChanged = Signal(list)
    undoStateChanged = Signal(bool, bool)  # (can_undo, can_redo)


def test_save_button_follows_validation_state(qtbot):
    """
    Test that the primary action button (Save to ROM) correctly
    follows the validation state from the editing controller.

    This tests the signal connection: when the editing controller
    emits validationChanged, the workflow controller updates the UI.
    """
    # Create a mock editing controller with real signals
    mock_editing = MockEditingController()

    # Controller is a QObject, qtbot handles app context
    controller = ROMWorkflowController(None, mock_editing)

    # Mock view and source_bar
    mock_view = MagicMock()
    mock_source_bar = MagicMock()
    mock_view.source_bar = mock_source_bar
    controller.set_view(mock_view)

    # Simulate being in edit mode by triggering a state transition
    # We need the controller to be in edit state for validation to matter
    controller.state = "edit"  # This is a public attribute

    # Emit validation changed signal (Invalid)
    mock_editing.validationChanged.emit(False, ["Too many colors"])

    # Verify: SourceBar action button should be disabled
    mock_source_bar.set_action_enabled.assert_called_with(False)

    # Emit validation changed signal (Valid)
    mock_editing.validationChanged.emit(True, [])

    # Verify: SourceBar action button should be enabled
    mock_source_bar.set_action_enabled.assert_called_with(True)
