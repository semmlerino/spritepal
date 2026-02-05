"""Tests for constrain-to-index feature in PaletteEditorController."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import Qt

from core.frame_mapping_project import SheetPalette
from ui.frame_mapping.controllers.palette_editor_controller import (
    EditorTool,
    PaletteEditorController,
)


@pytest.fixture
def palette() -> SheetPalette:
    """16-color test palette."""
    colors = [(i * 16, i * 16, i * 16) for i in range(16)]
    return SheetPalette(colors=colors)


@pytest.fixture
def controller(qtbot: object, palette: SheetPalette) -> PaletteEditorController:
    """Controller loaded with a 4x4 test image.

    Image layout (palette indices):
      Row 0: [1, 2, 3, 0]
      Row 1: [1, 1, 2, 0]
      Row 2: [3, 2, 1, 0]
      Row 3: [0, 0, 0, 0]
    """
    ctrl = PaletteEditorController()
    data = np.array(
        [
            [1, 2, 3, 0],
            [1, 1, 2, 0],
            [3, 2, 1, 0],
            [0, 0, 0, 0],
        ],
        dtype=np.uint8,
    )
    ctrl.load_indexed_data(data, palette)
    return ctrl


def test_constrain_default_off(controller: PaletteEditorController) -> None:
    """Constrain-to-index should be disabled by default."""
    assert controller.constrain_to_index is False


def test_set_constrain_emits_signal(qtbot: object, controller: PaletteEditorController) -> None:
    """Setting constrain-to-index should emit signal when value changes."""
    # Signal should emit when enabling
    with qtbot.waitSignal(controller.constrain_to_index_changed, timeout=1000):
        controller.set_constrain_to_index(True)

    assert controller.constrain_to_index is True

    # No signal when setting same value
    with qtbot.assertNotEmitted(controller.constrain_to_index_changed):
        controller.set_constrain_to_index(True)

    # Signal should emit when disabling
    with qtbot.waitSignal(controller.constrain_to_index_changed, timeout=1000):
        controller.set_constrain_to_index(False)

    assert controller.constrain_to_index is False


def test_constrain_eraser_skips_non_matching(
    controller: PaletteEditorController,
) -> None:
    """Eraser with constrain should skip pixels not matching active index."""
    controller.set_tool(EditorTool.ERASER)
    controller.set_active_index(1)
    controller.set_constrain_to_index(True)

    # Pixel (0,0) has index 1 => should erase to 0
    controller.handle_pixel_click(0, 0, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.finish_stroke()
    assert controller.image_model.get_pixel(0, 0) == 0

    # Pixel (1,0) has index 2 => should remain 2 (skipped)
    controller.handle_pixel_click(1, 0, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.finish_stroke()
    assert controller.image_model.get_pixel(1, 0) == 2


def test_constrain_eraser_erases_matching(
    controller: PaletteEditorController,
) -> None:
    """Eraser with constrain should erase pixels matching active index."""
    controller.set_tool(EditorTool.ERASER)
    controller.set_active_index(2)
    controller.set_constrain_to_index(True)

    # Pixel (1,0) has index 2 => should erase to 0
    controller.handle_pixel_click(1, 0, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.finish_stroke()
    assert controller.image_model.get_pixel(1, 0) == 0


def test_constrain_eraser_stroke(controller: PaletteEditorController) -> None:
    """Eraser stroke with constrain should only erase matching pixels."""
    controller.set_tool(EditorTool.ERASER)
    controller.set_active_index(1)
    controller.set_constrain_to_index(True)

    # Drag eraser across row 0: [1, 2, 3, 0]
    # Only pixel (0,0) with index 1 should be erased
    controller.handle_pixel_click(0, 0, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.handle_pixel_drag(1, 0)
    controller.handle_pixel_drag(2, 0)
    controller.handle_pixel_drag(3, 0)
    controller.finish_stroke()

    # Check results: only (0,0) should be erased
    assert controller.image_model.get_pixel(0, 0) == 0  # Was 1, erased
    assert controller.image_model.get_pixel(1, 0) == 2  # Unchanged
    assert controller.image_model.get_pixel(2, 0) == 3  # Unchanged
    assert controller.image_model.get_pixel(3, 0) == 0  # Was already 0


def test_constrain_off_erases_all(controller: PaletteEditorController) -> None:
    """Eraser with constrain OFF should erase all pixels."""
    controller.set_tool(EditorTool.ERASER)
    controller.set_constrain_to_index(False)

    # Erase pixel (0,0) with index 1 => should become 0
    controller.handle_pixel_click(0, 0, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.finish_stroke()
    assert controller.image_model.get_pixel(0, 0) == 0

    # Erase pixel (1,0) with index 2 => should become 0
    controller.handle_pixel_click(1, 0, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.finish_stroke()
    assert controller.image_model.get_pixel(1, 0) == 0


def test_constrain_undo(controller: PaletteEditorController) -> None:
    """Undo should restore pixels erased with constrain enabled."""
    controller.set_tool(EditorTool.ERASER)
    controller.set_active_index(1)
    controller.set_constrain_to_index(True)

    # Erase pixel (0,0) which has index 1
    original_value = controller.image_model.get_pixel(0, 0)
    assert original_value == 1

    controller.handle_pixel_click(0, 0, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.finish_stroke()
    assert controller.image_model.get_pixel(0, 0) == 0

    # Undo should restore original value
    controller.undo()
    assert controller.image_model.get_pixel(0, 0) == original_value
