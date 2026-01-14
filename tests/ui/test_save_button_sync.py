import pytest
from unittest.mock import MagicMock
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController

def test_save_button_follows_validation_state(qtbot):
    """
    Test that the primary action button (Save to ROM) correctly
    follows the validation state from the editing controller.
    """
    mock_editing = MagicMock()
    # Controller is a QObject, qtbot handles app context
    controller = ROMWorkflowController(None, mock_editing)
    
    # Mock view and source_bar
    mock_view = MagicMock()
    mock_source_bar = MagicMock()
    mock_view.source_bar = mock_source_bar
    controller.set_view(mock_view)
    
    # Simulate being in edit mode
    controller.state = "edit"
    
    # Trigger validation changed (Invalid)
    controller._on_validation_changed(False, ["Too many colors"])
    
    # Verify: SourceBar action button should be disabled
    mock_source_bar.set_action_enabled.assert_called_with(False)
    
    # Trigger validation changed (Valid)
    controller._on_validation_changed(True, [])
    
    # Verify: SourceBar action button should be enabled
    mock_source_bar.set_action_enabled.assert_called_with(True)