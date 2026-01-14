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
    # The scale depends on the auto-scaling logic in import_image.
    # dummy_sprite is usually small, so target_w/target_h will be small.
    # Let's force a known scale for the test.
    dialog.overlay_layer.set_scale(0.1)  # 10%
    dialog.overlay_layer.set_position(0.0, 0.0)

    assert dialog.overlay_layer.scale == 0.1
    assert dialog.overlay_layer.position == (0.0, 0.0)
    # Visual size is 3.2x3.2. Center is at 1.6, 1.6
    initial_center = (1.6, 1.6)

    # Change scale to 5% (0.05) (should become 1.6x1.6)
    # New top-left should be 1.6 - (1.6/2) = 0.8
    dialog.overlay_controls.scale_spin.setValue(5.0)
    assert dialog.overlay_layer.scale == 0.05
    assert dialog.overlay_layer.x == pytest.approx(0.8)

    # Check visual center
    new_width = 32 * 0.05
    new_center_x = dialog.overlay_layer.x + new_width / 2
    assert new_center_x == pytest.approx(initial_center[0])

    # Change scale to 20% (0.2) (should become 6.4x6.4)
    # To keep center at 1.6, 1.6, top-left must be 1.6 - (6.4/2) = -1.6
    dialog.overlay_controls.scale_slider.setValue(200)  # 200 * 0.1% = 20%
    assert dialog.overlay_layer.scale == 0.2
    assert dialog.overlay_layer.x == pytest.approx(-1.6)

    dialog.close()
