"""
Tests for overlay movement in GridArrangementDialog.
"""

import os
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from ui.grid_arrangement_dialog import GridArrangementDialog


@pytest.fixture
def dummy_sprite(tmp_path):
    """Create a dummy sprite sheet for testing."""
    img = Image.new("RGBA", (128, 128), (255, 0, 0, 255))
    path = tmp_path / "dummy_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def dummy_overlay(tmp_path):
    """Create a dummy overlay image."""
    img = Image.new("RGBA", (32, 32), (0, 255, 0, 128))
    path = tmp_path / "dummy_overlay.png"
    img.save(path)
    return str(path)


def test_overlay_drag_interaction(qtbot, dummy_sprite, dummy_overlay):
    """Test that dragging the overlay item updates the layer position."""
    dialog = GridArrangementDialog(dummy_sprite)
    qtbot.addWidget(dialog)
    dialog.show()

    # Import overlay
    dialog.overlay_layer.import_image(dummy_overlay)
    dialog._update_arrangement_canvas()

    overlay_item = dialog.overlay_item
    assert overlay_item is not None
    assert overlay_item.isVisible()

    initial_pos = dialog.overlay_layer.position
    assert initial_pos == (0, 0)

    # Get the center of the overlay in the view
    viewport = dialog.arrangement_grid.viewport()
    # Overlay is at (0,0) scene coords, which is usually top-left of viewport if not scrolled
    center_scene = QPoint(16, 16)
    center_view = dialog.arrangement_grid.mapFromScene(center_scene)

    # Simulate mouse press on the overlay
    # We use qtbot to simulate mouse events on the viewport
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=center_view)
    assert overlay_item.is_dragging

    # Drag to a new position
    target_view = center_view + QPoint(50, 30)
    # QtTest.mouseMove doesn't exist? Use qtbot.mouseMove or QTest.mouseMove
    QTest.mouseMove(viewport, target_view)
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=target_view)

    assert not overlay_item.is_dragging

    # Check if layer position updated
    new_pos = dialog.overlay_layer.position
    # It should be approximately (50, 30) depending on where exactly we clicked
    assert new_pos[0] > 0
    assert new_pos[1] > 0


def test_overlay_keyboard_nudge(qtbot, dummy_sprite, dummy_overlay):
    """Test that keyboard arrow keys nudge the overlay."""
    dialog = GridArrangementDialog(dummy_sprite)
    qtbot.addWidget(dialog)
    dialog.show()

    # Import overlay
    dialog.overlay_layer.import_image(dummy_overlay)
    dialog._update_arrangement_canvas()

    initial_pos = dialog.overlay_layer.position
    assert initial_pos == (0, 0)

    # Send arrow key events to the dialog
    qtbot.keyClick(dialog, Qt.Key.Key_Right)
    assert dialog.overlay_layer.position == (1, 0)

    qtbot.keyClick(dialog, Qt.Key.Key_Down, modifier=Qt.KeyboardModifier.ShiftModifier)
    assert dialog.overlay_layer.position == (1, 10)


def test_overlay_scaling(qtbot, dummy_sprite, dummy_overlay):
    """Test that changing overlay scale updates the graphics item and keeps center fixed."""
    dialog = GridArrangementDialog(dummy_sprite)
    qtbot.addWidget(dialog)
    dialog.show()

    # Import overlay
    dialog.overlay_layer.import_image(dummy_overlay)
    dialog._update_arrangement_canvas()

    # Initial state (32x32 at 0,0)
    # Use a scale within UI control range (0.1%-7.5%)
    # Note: UI controls use percentage values (scale_spin 0.1-7.5 = 0.1%-7.5%)
    # but overlay_layer.set_scale() takes decimal (0.05 = 5%)
    dialog.overlay_layer.set_scale(0.05)  # 5% (within UI range)
    dialog.overlay_layer.set_position(0.0, 0.0)

    assert dialog.overlay_layer.scale == 0.05
    assert dialog.overlay_layer.position == (0.0, 0.0)
    # Visual size is 32 * 0.05 = 1.6x1.6. Center is at 0.8, 0.8
    initial_center = (0.8, 0.8)

    # Change scale to 2% (0.02) using spinbox (should become 0.64x0.64)
    # New top-left should be 0.8 - (0.64/2) = 0.48
    dialog.overlay_controls.scale_spin.setValue(2.0)  # 2% = 0.02
    assert dialog.overlay_layer.scale == 0.02
    assert dialog.overlay_layer.x == pytest.approx(0.48)

    # Check visual center remains at 0.8
    new_width = 32 * 0.02
    new_center_x = dialog.overlay_layer.x + new_width / 2
    assert new_center_x == pytest.approx(initial_center[0])

    # Change scale to 7% (0.07) using slider (should become 2.24x2.24)
    # To keep center at 0.8, new x = 0.8 - (2.24/2) = 0.8 - 1.12 = -0.32
    # Slider: value 70 = 7.0% (slider range 1-75 maps to 0.1%-7.5%)
    dialog.overlay_controls.scale_slider.setValue(70)  # 70 / 10 = 7.0%
    assert dialog.overlay_layer.scale == 0.07
    assert dialog.overlay_layer.x == pytest.approx(-0.32)

    dialog.close()
