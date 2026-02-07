"""Tests for in-game edit persistence and clearance on transform changes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from PIL import Image
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import AIFrame, GameFrame, SheetPalette
from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

def create_indexed_image(path: Path, size: tuple[int, int], palette_colors: list[tuple[int, int, int]]) -> None:
    """Create a real indexed PNG file for in-game edit."""
    img = Image.new("P", size)
    flat_palette = []
    for c in palette_colors:
        flat_palette.extend(c)
    # Pad to 256 colors
    flat_palette.extend([0] * (768 - len(flat_palette)))
    img.putpalette(flat_palette)

    # Fill with index 1
    import numpy as np
    pixels = np.full((size[1], size[0]), 1, dtype=np.uint8)
    img_indexed = Image.fromarray(pixels, mode="P")
    img_indexed.putpalette(flat_palette)
    img_indexed.save(path)

class TestIngameEditPersistence:
    """Tests for in-game edit persistence and clearance."""

    @pytest.fixture
    def setup_canvas(self, qtbot: QtBot, tmp_path: Path):
        """Setup canvas with AI frame and game frame."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create test AI image file
        ai_image_path = tmp_path / "test_ai_frame.png"
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Set AI frame
        ai_frame = AIFrame(path=ai_image_path, index=0)
        canvas.set_ai_frame(ai_frame)

        # Create mock game pixmap and capture result
        game_pixmap = QPixmap(32, 32)
        mock_capture = MagicMock()
        mock_capture.bounding_box = MagicMock()
        mock_capture.bounding_box.x = 0
        mock_capture.bounding_box.y = 0
        mock_capture.bounding_box.width = 32
        mock_capture.bounding_box.height = 32
        mock_capture.palettes = {}
        mock_capture.entries = []

        # Set game frame
        game_frame = GameFrame(
            id="F00000",
            capture_path=tmp_path / "capture.json",
            rom_offsets=[],
            compression_types={},
        )
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=mock_capture,
        )

        # Set sheet palette
        palette_colors = [(0, 0, 0), (248, 0, 0), (0, 248, 0), (0, 0, 248)] + [(128, 128, 128)] * 12
        palette = SheetPalette(colors=palette_colors)
        canvas.set_sheet_palette(palette)

        # Create and set in-game edited path
        ingame_path = tmp_path / "ingame_edit.png"
        create_indexed_image(ingame_path, (32, 32), palette_colors)
        canvas.set_ingame_edited_path(str(ingame_path))

        return canvas, ingame_path

    def test_ingame_edit_cleared_on_transform_move(self, setup_canvas):
        """Moving the AI frame should clear the in-game edited path."""
        canvas, _ = setup_canvas
        assert canvas._ingame_edited_path is not None

        # Simulate transform change via signal handler
        canvas._on_ai_frame_transform_changed(10, 10, 1.0)

        # Should be cleared because the baked-in image is no longer valid for new offset
        assert canvas._ingame_edited_path is None

    def test_ingame_edit_cleared_on_scale_change(self, setup_canvas):
        """Changing scale should clear the in-game edited path."""
        canvas, _ = setup_canvas
        assert canvas._ingame_edited_path is not None

        # Change scale slider (triggers _on_scale_slider_changed)
        canvas._scale_slider.setValue(800) # 0.8x

        assert canvas._ingame_edited_path is None

    def test_ingame_edit_cleared_on_flip_change(self, setup_canvas):
        """Changing flip should clear the in-game edited path."""
        canvas, _ = setup_canvas
        assert canvas._ingame_edited_path is not None

        # Toggle flip (triggers _on_flip_changed)
        canvas._flip_h_checkbox.setChecked(True)

        assert canvas._ingame_edited_path is None

    def test_ingame_edit_cleared_on_sharpen_change(self, setup_canvas):
        """Changing sharpen should clear the in-game edited path."""
        canvas, _ = setup_canvas
        assert canvas._ingame_edited_path is not None

        # Change sharpen (triggers _on_sharpen_changed)
        canvas._sharpen_slider.setValue(20) # 2.0

        assert canvas._ingame_edited_path is None

    def test_ingame_edit_cleared_on_resampling_change(self, setup_canvas):
        """Changing resampling should clear the in-game edited path."""
        canvas, _ = setup_canvas
        assert canvas._ingame_edited_path is not None

        # Change resampling (triggers _on_resampling_changed)
        canvas._resampling_combo.setCurrentIndex(1) # Nearest

        assert canvas._ingame_edited_path is None
