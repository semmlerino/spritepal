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
    
    # Verify canvas item updated
    assert dialog.overlay_item.pos() == QPoint(1, 10)

    dialog.close()
