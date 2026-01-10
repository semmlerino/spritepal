import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.controllers.extraction_controller import ExtractionController
from ui.sprite_editor.controllers.injection_controller import InjectionController
from ui.sprite_editor.managers import ToolType
from ui.sprite_editor.views.main_window import SpriteEditorMainWindow


def test_shortcut_conflict_f_key(qtbot):
    """
    Verify that pressing 'F' selects the Fill tool as advertised in the menu,
    and not Zoom Fit.
    """
    # 1. Setup
    main_window = SpriteEditorMainWindow()
    qtbot.addWidget(main_window)

    editing_controller = EditingController()
    extraction_controller = ExtractionController()
    injection_controller = InjectionController()

    main_window.wire_controllers(
        extraction_controller=extraction_controller,
        editing_controller=editing_controller,
        injection_controller=injection_controller,
    )

    # 2. Get Workspace and Canvas
    # We need to access the EditTab -> EditWorkspace -> Canvas
    # This path assumes EditTab wraps EditWorkspace
    edit_tab = main_window.edit_tab
    # Assuming direct access for now, will debug if fails
    workspace = edit_tab.workspace
    canvas = workspace.get_canvas()

    # 3. Focus Canvas
    main_window.show()
    main_window.show_edit_tab()
    qtbot.wait(100)
    canvas.setFocus()

    # Ensure tool starts as Pencil
    editing_controller.set_tool("pencil")
    assert editing_controller.tool_manager.current_tool_type == ToolType.PENCIL

    # 4. Press 'B' (Fill)
    qtbot.keyClick(canvas, Qt.Key_B)
    qtbot.wait(100)

    # Assert: Tool changed to FILL
    assert editing_controller.tool_manager.current_tool_type == ToolType.FILL, "Pressing B should select Fill tool"

    # 5. Press 'P' (Pencil) to reset
    qtbot.keyClick(canvas, Qt.Key_P)
    qtbot.wait(100)
    assert editing_controller.tool_manager.current_tool_type == ToolType.PENCIL

    # 6. Press 'F' (Fit)
    qtbot.keyClick(canvas, Qt.Key_F)
    qtbot.wait(100)

    # Assert: Tool remains PENCIL (F should be Zoom Fit, not Fill)
    assert editing_controller.tool_manager.current_tool_type == ToolType.PENCIL, (
        "Pressing F should NOT select Fill tool (it triggers Zoom Fit)"
    )
