
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QApplication

from ui.frame_mapping.views.indexed_canvas import IndexedCanvas


def test_highlight_visibility_during_paint(qtbot):
    """Test that the highlight overlay is hidden while painting (holding left mouse button)."""
    canvas = IndexedCanvas()
    qtbot.addWidget(canvas)
    
    # Resize to ensure valid geometry for mapping
    canvas.resize(500, 500)
    canvas.show()
    qtbot.waitExposed(canvas)
    
    # Mock data
    data = np.zeros((10, 10), dtype=np.uint8)
    data[0, 0] = 1
    
    palette = MagicMock()
    palette.colors = [(0,0,0), (255,0,0)] # 0=Black, 1=Red
    
    canvas.set_image(data, palette)
    canvas.set_highlight_index(1)
    
    # Ensure highlight is visible initially
    assert canvas._highlight_item.isVisible(), "Highlight should be visible initially"
    
    view = canvas._view
    
    # Find a valid point on the image (5, 5)
    scene_target = QPointF(5, 5)
    viewport_pos = view.mapFromScene(scene_target)
    
    # Simulate Press (Start Painting)
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=viewport_pos)
    
    # Check if highlight is hidden
    assert not canvas._highlight_item.isVisible(), "Highlight should be hidden during paint"
        
    # Simulate Release (End Painting)
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=viewport_pos)
    
    # Check if highlight is restored
    assert canvas._highlight_item.isVisible(), "Highlight should be restored after paint"

def test_highlight_remains_visible_during_sample(qtbot):
    """Test that the highlight overlay remains visible while sampling (holding right mouse button)."""
    canvas = IndexedCanvas()
    qtbot.addWidget(canvas)
    
    # Resize to ensure valid geometry for mapping
    canvas.resize(500, 500)
    canvas.show()
    qtbot.waitExposed(canvas)
    
    # Mock data
    data = np.zeros((10, 10), dtype=np.uint8)
    data[0, 0] = 1
    
    palette = MagicMock()
    palette.colors = [(0,0,0), (255,0,0)] # 0=Black, 1=Red
    
    canvas.set_image(data, palette)
    canvas.set_highlight_index(1)
    
    view = canvas._view
    
    # Find a valid point on the image (5, 5)
    scene_target = QPointF(5, 5)
    viewport_pos = view.mapFromScene(scene_target)
    
    # Simulate Right Press (Sampling)
    qtbot.mousePress(view.viewport(), Qt.MouseButton.RightButton, pos=viewport_pos)
    
    # Check if highlight remains visible
    assert canvas._highlight_item.isVisible(), "Highlight should remain visible during sample"
        
    # Simulate Release
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.RightButton, pos=viewport_pos)
    
    # Check if highlight remains visible
    assert canvas._highlight_item.isVisible(), "Highlight should remain visible after sample"
