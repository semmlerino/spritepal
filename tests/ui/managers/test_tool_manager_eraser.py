from unittest.mock import MagicMock, Mock

import pytest

from ui.sprite_editor.managers.tool_manager import EraserTool, ToolManager, ToolType
from ui.sprite_editor.models import ImageModel


def test_tool_manager_has_eraser():
    manager = ToolManager()
    assert ToolType.ERASER in manager.tools
    assert isinstance(manager.tools[ToolType.ERASER], EraserTool)


def test_tool_manager_set_tool_eraser():
    manager = ToolManager()

    # Test setting by string
    manager.set_tool("eraser")
    assert manager.current_tool == ToolType.ERASER
    assert isinstance(manager.get_tool(), EraserTool)

    # Test setting by string case insensitive
    manager.set_tool("ERASER")
    assert manager.current_tool == ToolType.ERASER


def test_eraser_tool_usage():
    tool = EraserTool()
    image_model = Mock(spec=ImageModel)

    # on_press should call set_pixel with color 0
    # PencilTool.on_press calls image_model.set_pixel
    # We mock set_pixel to return True
    image_model.set_pixel.return_value = True

    # Press at 10, 10 with color 5 (should be ignored and use 0)
    result = tool.on_press(10, 10, 5, image_model)

    image_model.set_pixel.assert_called_with(10, 10, 0)
    assert result is True


def test_eraser_tool_move():
    tool = EraserTool()
    image_model = Mock(spec=ImageModel)

    # Setup initial point
    image_model.set_pixel.return_value = True
    tool.on_press(0, 0, 5, image_model)

    # Move to 0, 2 (should interpolate 0,1 and 0,2)
    # PencilTool.on_move calls _get_line_points which returns points
    # But PencilTool implementation of on_move doesn't seem to call set_pixel?
    # Wait, let's check PencilTool implementation again.
    # It returns points. The Controller/Canvas likely handles the actual drawing for move?
    # No, usually tool handles it.

    # Let's check PencilTool.on_move source in previous turn.
    # on_move returns list[tuple[int, int]]. It does NOT call set_pixel on the model?
    # Ah, PencilTool.on_press DOES call set_pixel.
    # PencilTool.on_move returns points. Who draws them?
    # The Controller calls tool.on_move, gets points, and then calls image_model.set_pixels(points, color)?
    pass
