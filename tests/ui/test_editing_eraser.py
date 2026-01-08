
import numpy as np
import pytest

from ui.sprite_editor.controllers.editing_controller import EditingController


def test_eraser_tool_uses_transparent_color():
    """Test that eraser tool always uses color 0 regardless of selected color."""
    controller = EditingController()
    
    # Create a 2x2 image filled with color 1
    data = np.full((2, 2), 1, dtype=np.uint8)
    controller.load_image(data)
    
    # Select color 2 (to ensure it's NOT used)
    controller.set_selected_color(2)
    assert controller.get_selected_color() == 2
    
    # Set tool to Eraser
    controller.set_tool("eraser")
    assert controller.get_current_tool_name() == "eraser"
    
    # Perform a stroke
    # 1. Press at 0,0
    controller.handle_pixel_press(0, 0)
    assert controller.image_model.get_pixel(0, 0) == 0, "Eraser press should set pixel to 0"
    
    # 2. Move to 0,1
    controller.handle_pixel_move(0, 1)
    assert controller.image_model.get_pixel(0, 1) == 0, "Eraser move should set pixel to 0"
    
    # 3. Release
    controller.handle_pixel_release(0, 1)

def test_pencil_tool_uses_selected_color():
    """Verify pencil tool still uses selected color."""
    controller = EditingController()
    
    # Create a 2x2 image filled with color 1
    data = np.full((2, 2), 1, dtype=np.uint8)
    controller.load_image(data)
    
    # Select color 2
    controller.set_selected_color(2)
    
    # Set tool to Pencil
    controller.set_tool("pencil")
    
    # Perform a stroke
    controller.handle_pixel_press(0, 0)
    assert controller.image_model.get_pixel(0, 0) == 2, "Pencil press should set pixel to 2"
    
    controller.handle_pixel_move(0, 1)
    assert controller.image_model.get_pixel(0, 1) == 2, "Pencil move should set pixel to 2"
