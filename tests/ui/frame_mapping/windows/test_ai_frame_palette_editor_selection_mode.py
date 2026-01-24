"""Tests for selection mode indicator in AI Frame Palette Editor.

Verifies that the status bar shows the current selection mode (Replace/Add/Subtract)
and updates dynamically based on keyboard modifiers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image
from PySide6.QtCore import Qt

from core.frame_mapping_project import AIFrame, SheetPalette
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


class TestFillSelectionCommand:
    """Tests for Fill Selection button and command."""

    def test_has_fill_selection_button(
        self,
        qtbot,
        test_ai_frame: AIFrame,
        test_palette: SheetPalette,
    ) -> None:
        """Window should have a Fill Selection button."""
        window = AIFramePaletteEditorWindow(test_ai_frame, test_palette)
        qtbot.addWidget(window)

        assert hasattr(window, "_fill_selection_btn")
        assert window._fill_selection_btn is not None

    def test_fill_selection_button_calls_controller(
        self,
        qtbot,
        test_ai_frame: AIFrame,
        test_palette: SheetPalette,
    ) -> None:
        """Fill Selection button should call controller's paint_selection method."""
        window = AIFramePaletteEditorWindow(test_ai_frame, test_palette)
        qtbot.addWidget(window)
        window.show()

        # Mock the controller method
        window._controller.paint_selection = MagicMock()

        # Click the button
        window._fill_selection_btn.click()

        # Verify paint_selection was called
        window._controller.paint_selection.assert_called_once()


class TestSelectionModeIndicator:
    """Tests for selection mode status bar indicator."""

    def test_status_bar_has_selection_mode_label(
        self,
        qtbot,
        test_ai_frame: AIFrame,
        test_palette: SheetPalette,
    ) -> None:
        """Status bar should have a selection mode label."""
        window = AIFramePaletteEditorWindow(test_ai_frame, test_palette)
        qtbot.addWidget(window)

        assert hasattr(window, "_selection_mode_label")
        assert window._selection_mode_label is not None
        # Default mode should be shown
        assert "Replace" in window._selection_mode_label.text()

    def test_selection_mode_shows_add_when_shift_held(
        self,
        qtbot,
        test_ai_frame: AIFrame,
        test_palette: SheetPalette,
    ) -> None:
        """Selection mode should show 'Add' when Shift is held."""
        window = AIFramePaletteEditorWindow(test_ai_frame, test_palette)
        qtbot.addWidget(window)
        window.show()

        # Simulate updating selection mode with Shift modifier
        window._update_selection_mode_display(Qt.KeyboardModifier.ShiftModifier)

        assert "Add" in window._selection_mode_label.text()

    def test_selection_mode_shows_subtract_when_ctrl_held(
        self,
        qtbot,
        test_ai_frame: AIFrame,
        test_palette: SheetPalette,
    ) -> None:
        """Selection mode should show 'Subtract' when Ctrl is held."""
        window = AIFramePaletteEditorWindow(test_ai_frame, test_palette)
        qtbot.addWidget(window)
        window.show()

        # Simulate updating selection mode with Ctrl modifier
        window._update_selection_mode_display(Qt.KeyboardModifier.ControlModifier)

        assert "Subtract" in window._selection_mode_label.text()

    def test_selection_mode_returns_to_replace_when_no_modifiers(
        self,
        qtbot,
        test_ai_frame: AIFrame,
        test_palette: SheetPalette,
    ) -> None:
        """Selection mode should return to 'Replace' when modifiers released."""
        window = AIFramePaletteEditorWindow(test_ai_frame, test_palette)
        qtbot.addWidget(window)
        window.show()

        # Set to Add mode first
        window._update_selection_mode_display(Qt.KeyboardModifier.ShiftModifier)
        assert "Add" in window._selection_mode_label.text()

        # Then release modifiers
        window._update_selection_mode_display(Qt.KeyboardModifier.NoModifier)
        assert "Replace" in window._selection_mode_label.text()
