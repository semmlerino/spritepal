"""Tests for drag cancellation functionality.

Regression tests for BUG-G: Drag cancellation should clear drag_start_alignment
to prevent incorrect undo baseline for subsequent drags.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from ui.frame_mapping.views.workbench_items import AIFrameItem


@pytest.fixture
def ai_frame_item(qtbot: object) -> AIFrameItem:
    """Create an AIFrameItem for testing."""
    item = AIFrameItem()
    return item


class TestDragCancel:
    """Tests for drag cancellation via Escape key."""

    def test_escape_cancels_drag_and_restores_position(self, ai_frame_item: AIFrameItem) -> None:
        """Pressing Escape during drag restores original position and clears state."""
        # Setup: Position item at (0, 0) with scale 1.0
        ai_frame_item.setPos(0, 0)
        ai_frame_item.set_scale_factor(1.0)

        # Start a drag at the original position
        ai_frame_item.start_drag(0, 0, 1.0)
        assert ai_frame_item.is_dragging

        # Move item during drag
        ai_frame_item.setPos(50, 30)
        ai_frame_item.set_scale_factor(0.8)

        # Verify position changed
        assert ai_frame_item.pos().x() == 50
        assert ai_frame_item.pos().y() == 30

        # Press Escape
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        ai_frame_item.keyPressEvent(event)

        # Verify: position restored to drag start
        assert ai_frame_item.pos().x() == 0
        assert ai_frame_item.pos().y() == 0
        assert ai_frame_item.scale_factor() == 1.0

        # Verify: drag state cleared
        assert not ai_frame_item.is_dragging
        assert ai_frame_item.get_drag_start_alignment() is None

    def test_escape_without_drag_does_nothing_harmful(self, ai_frame_item: AIFrameItem) -> None:
        """Pressing Escape when not dragging should not crash or change state."""
        # Setup: Position item, but don't start drag
        ai_frame_item.setPos(25, 15)
        ai_frame_item.set_scale_factor(0.9)
        original_pos = ai_frame_item.pos()
        original_scale = ai_frame_item.scale_factor()

        # Press Escape without active drag
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        ai_frame_item.keyPressEvent(event)

        # Position should be unchanged
        assert ai_frame_item.pos() == original_pos
        assert ai_frame_item.scale_factor() == original_scale
        assert not ai_frame_item.is_dragging

    def test_end_drag_clears_drag_start_alignment(self, ai_frame_item: AIFrameItem) -> None:
        """Normal drag completion should clear drag_start_alignment."""
        # Start drag
        ai_frame_item.start_drag(10, 20, 0.5)
        assert ai_frame_item.get_drag_start_alignment() == (10, 20, 0.5)
        assert ai_frame_item.is_dragging

        # End drag normally
        ai_frame_item.end_drag()

        # Verify cleanup
        assert not ai_frame_item.is_dragging
        assert ai_frame_item.get_drag_start_alignment() is None
