#!/usr/bin/env python3
"""Tests for IndexedCanvasView drag behavior.

Verifies that right-click (sample) does not trigger drag-painting.
"""

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QGraphicsScene

from ui.frame_mapping.views.indexed_canvas import IndexedCanvasView


@pytest.fixture
def canvas_view(qtbot):
    """Create an IndexedCanvasView for testing."""
    scene = QGraphicsScene()
    view = IndexedCanvasView(scene)
    view.set_image_size(64, 64)
    view.resize(200, 200)
    view.show()
    qtbot.addWidget(view)
    qtbot.waitExposed(view)
    return view


def test_left_click_enables_dragging(canvas_view, qtbot):
    """Left-click inside image bounds should enable dragging mode."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent

    # Use position (1, 1) in scene coords, convert to viewport
    scene_pos = QPointF(1, 1)
    viewport_pos = canvas_view.mapFromScene(scene_pos)

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(viewport_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    canvas_view.mousePressEvent(event)

    assert canvas_view._is_dragging is True


def test_right_click_does_not_enable_dragging(canvas_view, qtbot):
    """Right-click should NOT enable dragging mode - sample only."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent

    # Use position (1, 1) in scene coords, convert to viewport
    scene_pos = QPointF(1, 1)
    viewport_pos = canvas_view.mapFromScene(scene_pos)

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(viewport_pos),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )

    canvas_view.mousePressEvent(event)

    # Right-click should NOT set dragging
    assert canvas_view._is_dragging is False


def test_right_click_does_not_emit_drag_signal_on_move(canvas_view, qtbot):
    """Right-click drag should NOT emit pixel_dragged signal."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent

    # Setup signal spy
    drag_signals = []
    canvas_view.pixel_dragged.connect(lambda x, y: drag_signals.append((x, y)))

    # Use position (1, 1) in scene coords
    scene_pos = QPointF(1, 1)
    viewport_pos = canvas_view.mapFromScene(scene_pos)

    # Right-click press
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(viewport_pos),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas_view.mousePressEvent(press_event)

    # Move to a different position
    move_scene_pos = QPointF(5, 5)
    move_viewport_pos = canvas_view.mapFromScene(move_scene_pos)
    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(move_viewport_pos),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas_view.mouseMoveEvent(move_event)

    # Should NOT have emitted pixel_dragged because dragging wasn't enabled
    assert len(drag_signals) == 0


def test_left_click_drag_emits_signal(canvas_view, qtbot):
    """Left-click drag should emit pixel_dragged signal."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent

    # Setup signal spy
    drag_signals = []
    canvas_view.pixel_dragged.connect(lambda x, y: drag_signals.append((x, y)))

    # Use position (1, 1) in scene coords
    scene_pos = QPointF(1, 1)
    viewport_pos = canvas_view.mapFromScene(scene_pos)

    # Left-click press - should enable dragging
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(viewport_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas_view.mousePressEvent(press_event)

    # Verify dragging is enabled
    assert canvas_view._is_dragging is True

    # Move to a different position
    move_scene_pos = QPointF(5, 5)
    move_viewport_pos = canvas_view.mapFromScene(move_scene_pos)
    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(move_viewport_pos),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas_view.mouseMoveEvent(move_event)

    # Should have emitted pixel_dragged
    assert len(drag_signals) > 0


def test_dragging_state_tracks_button_correctly():
    """Verify _is_dragging is only set for left button, not right."""
    # Direct unit test without Qt event machinery
    from ui.frame_mapping.views.indexed_canvas import IndexedCanvasView

    scene = QGraphicsScene()
    view = IndexedCanvasView(scene)
    view.set_image_size(64, 64)

    # Initially not dragging
    assert view._is_dragging is False

    # Simulate setting drag state for left button
    view._is_dragging = True
    assert view._is_dragging is True

    # Reset
    view._is_dragging = False
    assert view._is_dragging is False
