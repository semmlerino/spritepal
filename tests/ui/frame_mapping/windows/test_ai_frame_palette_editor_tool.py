"""Tests for tool selection in AI Frame Palette Editor.

Verifies that the Brush tool replaces the Pencil tool and shortcuts work.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication

from core.frame_mapping_project import AIFrame, SheetPalette
from ui.frame_mapping.controllers.palette_editor_controller import EditorTool
from ui.frame_mapping.windows.ai_frame_palette_editor import AIFramePaletteEditorWindow


@pytest.fixture
def test_image(tmp_path: Path) -> Path:
    """Create a test indexed image."""
    img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
    path = tmp_path / "test.png"
    img.save(path)
    return path


@pytest.fixture
def test_palette() -> SheetPalette:
    """Create a test palette."""
    colors = [(i * 16, i * 16, i * 16) for i in range(16)]
    return SheetPalette(colors=colors)


@pytest.fixture
def test_ai_frame(test_image: Path) -> AIFrame:
    """Create a test AI frame."""
    return AIFrame(
        path=test_image,
        index=0,
        display_name="Test Frame",
    )


class TestToolSelection:
    """Tests for tool selection and shortcuts."""

    def test_default_tool_is_brush(
        self,
        qtbot,
        test_ai_frame: AIFrame,
        test_palette: SheetPalette,
    ) -> None:
        """Default tool should be Brush."""
        window = AIFramePaletteEditorWindow(test_ai_frame, test_palette)
        qtbot.addWidget(window)
        window.show()

        assert window._controller.current_tool == EditorTool.BRUSH
        assert window._tool_buttons[EditorTool.BRUSH].isChecked()
        assert window._tool_label.text() == "Tool: Brush"

    def test_brush_tool_shortcut(
        self,
        qtbot,
        test_ai_frame: AIFrame,
        test_palette: SheetPalette,
    ) -> None:
        """Pressing 'B' should select Brush tool."""
        window = AIFramePaletteEditorWindow(test_ai_frame, test_palette)
        qtbot.addWidget(window)
        window.show()

        # Switch to another tool first
        window._select_tool(EditorTool.ERASER)
        assert window._controller.current_tool == EditorTool.ERASER

        # Simulate 'B' key press
        # Note: QShortcut activation is hard to simulate directly via keyClick in some envs,
        # but we can verify the shortcut exists and calls the method.
        
        # Verify shortcut setup
        brush_shortcut = None
        for child in window.children():
            if isinstance(child, QShortcut):
                if child.key().toString() == "B":
                    brush_shortcut = child
                    break
        
        assert brush_shortcut is not None
        
        # Manually activate to verify the callback
        brush_shortcut.activated.emit()
        
        assert window._controller.current_tool == EditorTool.BRUSH
        assert window._tool_buttons[EditorTool.BRUSH].isChecked()
        assert window._tool_label.text() == "Tool: Brush"

    def test_enum_has_brush_not_pencil(self):
        """EditorTool enum should have BRUSH and not PENCIL."""
        assert hasattr(EditorTool, "BRUSH")
        assert not hasattr(EditorTool, "PENCIL")

    def test_picker_tool_shortcut(
        self,
        qtbot,
        test_ai_frame: AIFrame,
        test_palette: SheetPalette,
    ) -> None:
        """Pressing 'I' should select Picker tool."""
        window = AIFramePaletteEditorWindow(test_ai_frame, test_palette)
        qtbot.addWidget(window)
        window.show()

        # Switch to Brush first (default)
        assert window._controller.current_tool == EditorTool.BRUSH

        # Verify shortcut setup for 'I'
        picker_shortcut = None
        for child in window.children():
            if isinstance(child, QShortcut):
                if child.key().toString() == "I":
                    picker_shortcut = child
                    break
        
        assert picker_shortcut is not None
        
        # Manually activate to verify the callback
        picker_shortcut.activated.emit()
        
        assert window._controller.current_tool == EditorTool.PICKER
        assert window._tool_buttons[EditorTool.PICKER].isChecked()
        assert window._tool_label.text() == "Tool: Picker"

    def test_picker_switches_back_to_brush(
        self,
        qtbot,
        test_ai_frame: AIFrame,
        test_palette: SheetPalette,
    ) -> None:
        """Using Picker should switch back to Brush."""
        window = AIFramePaletteEditorWindow(test_ai_frame, test_palette)
        qtbot.addWidget(window)
        window.show()

        # Load indexed data manually since we want to pick a specific color
        import numpy as np
        data = np.zeros((16, 16), dtype=np.uint8)
        data[5, 5] = 7
        window._controller.load_indexed_data(data, test_palette)

        window._select_tool(EditorTool.PICKER)
        assert window._controller.current_tool == EditorTool.PICKER

        # Click at (5, 5) to pick index 7
        window._on_canvas_clicked(5, 5, 0) # button 0 is left click

        assert window._controller.active_index == 7
        assert window._controller.current_tool == EditorTool.BRUSH
        assert window._tool_buttons[EditorTool.BRUSH].isChecked()
