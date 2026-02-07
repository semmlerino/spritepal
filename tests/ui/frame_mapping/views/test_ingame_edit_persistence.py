"""Tests for in-game edit extraction and AI frame file overwriting."""

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


def create_indexed_image(
    path: Path, size: tuple[int, int], palette_colors: list[tuple[int, int, int]], fill_index: int = 1
) -> None:
    """Create a real indexed PNG file for in-game edit."""
    img = Image.new("P", size)
    flat_palette = []
    for c in palette_colors:
        flat_palette.extend(c)
    # Pad to 256 colors
    flat_palette.extend([0] * (768 - len(flat_palette)))
    img.putpalette(flat_palette)

    # Fill with specified index
    import numpy as np

    pixels = np.full((size[1], size[0]), fill_index, dtype=np.uint8)
    img_indexed = Image.fromarray(pixels, mode="P")
    img_indexed.putpalette(flat_palette)
    img_indexed.save(path)


class TestIngameEditExtraction:
    """Tests for in-game edit extraction and AI frame overwriting."""

    @pytest.fixture
    def setup_canvas(self, qtbot: QtBot, tmp_path: Path):
        """Setup canvas with AI frame and game frame."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create test AI image file (RGBA)
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

        # Set sheet palette with known colors
        palette_colors = [(0, 0, 0), (248, 0, 0), (0, 248, 0), (0, 0, 248)] + [(128, 128, 128)] * 12
        palette = SheetPalette(colors=palette_colors)
        canvas.set_sheet_palette(palette)

        return canvas, ai_image_path, palette_colors, tmp_path

    def test_set_ingame_edited_path_overwrites_ai_frame_file(self, setup_canvas):
        """Setting ingame edited path should overwrite the AI frame file with extracted indices."""
        canvas, ai_image_path, palette_colors, tmp_path = setup_canvas

        # Verify AI frame is initially RGBA
        original_ai = Image.open(ai_image_path)
        assert original_ai.mode == "RGBA"

        # Create an ingame composite PNG with distinctive index value (index 2)
        ingame_path = tmp_path / "ingame_edit.png"
        create_indexed_image(ingame_path, (32, 32), palette_colors, fill_index=2)

        # Call set_ingame_edited_path
        canvas.set_ingame_edited_path(str(ingame_path))

        # Assert: The original AI frame file has been overwritten with indexed PNG
        overwritten_ai = Image.open(ai_image_path)
        assert overwritten_ai.mode == "P", "AI frame should be overwritten as indexed PNG"
        assert overwritten_ai.size == (32, 32), "AI frame dimensions should match"

        # Assert: The ingame composite file has been deleted
        assert not ingame_path.exists(), "Ingame composite should be deleted after extraction"

    def test_set_ingame_edited_path_refreshes_cache(self, setup_canvas):
        """Setting ingame edited path should refresh the AI frame cache with new data."""
        canvas, ai_image_path, palette_colors, tmp_path = setup_canvas

        # Put a dummy entry in the AI frame cache (keyed by Path, not str)
        dummy = MagicMock()
        canvas._ai_frame_cache[ai_image_path] = dummy
        assert ai_image_path in canvas._ai_frame_cache

        # Create ingame composite
        ingame_path = tmp_path / "ingame_edit.png"
        create_indexed_image(ingame_path, (32, 32), palette_colors, fill_index=2)

        # Call set_ingame_edited_path
        canvas.set_ingame_edited_path(str(ingame_path))

        # Assert: cache entry has been refreshed (not the dummy)
        assert ai_image_path in canvas._ai_frame_cache, "AI frame cache should have refreshed entry"
        assert canvas._ai_frame_cache[ai_image_path] is not dummy, "Cache entry should be replaced with fresh data"

    def test_set_ingame_edited_path_none_is_noop(self, setup_canvas):
        """Setting ingame edited path to None should be a no-op."""
        canvas, ai_image_path, palette_colors, tmp_path = setup_canvas

        # Store original AI frame content
        original_ai = Image.open(ai_image_path)
        original_mode = original_ai.mode
        original_size = original_ai.size

        # Call with None
        canvas.set_ingame_edited_path(None)

        # Assert: AI frame unchanged
        unchanged_ai = Image.open(ai_image_path)
        assert unchanged_ai.mode == original_mode
        assert unchanged_ai.size == original_size

    def test_set_ingame_edited_path_nonexistent_file_is_noop(self, setup_canvas):
        """Setting ingame edited path to nonexistent file should be a no-op."""
        canvas, ai_image_path, palette_colors, tmp_path = setup_canvas

        # Store original AI frame content
        original_ai = Image.open(ai_image_path)
        original_mode = original_ai.mode
        original_size = original_ai.size

        # Call with nonexistent path
        canvas.set_ingame_edited_path("/nonexistent/path.png")

        # Assert: AI frame unchanged
        unchanged_ai = Image.open(ai_image_path)
        assert unchanged_ai.mode == original_mode
        assert unchanged_ai.size == original_size
