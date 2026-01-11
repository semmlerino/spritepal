from unittest.mock import MagicMock

import pytest

from tests.fixtures.timeouts import ui_timeout
from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.controllers.extraction_controller import ExtractionController
from ui.sprite_editor.controllers.injection_controller import InjectionController
from ui.sprite_editor.views.main_window import SpriteEditorMainWindow


def test_undo_action_enable_state(qtbot):
    """
    Verify that the main window Undo/Redo actions are enabled/disabled
    based on the controller's undo stack state.
    """
    # 1. Setup
    main_window = SpriteEditorMainWindow()
    qtbot.addWidget(main_window)

    editing_controller = EditingController()
    extraction_controller = ExtractionController()
    injection_controller = InjectionController()

    # 2. Wire controllers
    main_window.wire_controllers(
        extraction_controller=extraction_controller,
        editing_controller=editing_controller,
        injection_controller=injection_controller,
    )

    # 3. Initial State: Stack is empty -> Actions disabled
    # Wait for signal processing to settle using deterministic wait
    qtbot.waitUntil(
        lambda: not main_window.action_undo.isEnabled() and not main_window.action_redo.isEnabled(),
        timeout=ui_timeout(),
    )

    # Failure point: These are currently always enabled (default QAction state) or not wired
    # We expect them to be disabled initially if wired correctly to empty stack
    assert not main_window.action_undo.isEnabled(), "Undo action should be disabled initially"
    assert not main_window.action_redo.isEnabled(), "Redo action should be disabled initially"

    # 4. Perform Action: Stack has item -> Undo enabled
    # Simulate a draw operation
    editing_controller.handle_pixel_press(0, 0)
    editing_controller.handle_pixel_release(0, 0)

    qtbot.waitUntil(
        lambda: main_window.action_undo.isEnabled() and not main_window.action_redo.isEnabled(),
        timeout=ui_timeout(),
    )
    assert main_window.action_undo.isEnabled(), "Undo action should be enabled after action"
    assert not main_window.action_redo.isEnabled(), "Redo action should be disabled after action"

    # 5. Undo: Stack pointer moves -> Redo enabled
    editing_controller.undo()

    qtbot.waitUntil(
        lambda: not main_window.action_undo.isEnabled() and main_window.action_redo.isEnabled(),
        timeout=ui_timeout(),
    )
    assert not main_window.action_undo.isEnabled(), "Undo action should be disabled after undo"
    assert main_window.action_redo.isEnabled(), "Redo action should be enabled after undo"
