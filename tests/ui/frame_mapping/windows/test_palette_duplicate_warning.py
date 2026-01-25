"""Tests for Palette Editor Duplicate Color Warning.

When a palette contains duplicate RGB colors, the editor should display
a warning that palette index information will be lost during injection.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, SheetPalette

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestDuplicateColorWarning:
    """Tests for duplicate color detection and warning display."""

    @pytest.fixture
    def ai_frame(self, tmp_path: Path) -> AIFrame:
        """Create a test AI frame with an image file."""
        img_path = tmp_path / "test_frame.png"
        # Create a simple 8x8 indexed image
        img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        img.save(img_path)
        return AIFrame(path=img_path, index=0)

    @pytest.fixture
    def palette_no_duplicates(self) -> SheetPalette:
        """Create a palette with no duplicate colors."""
        colors = [(i * 16, i * 8, i * 4) for i in range(16)]
        return SheetPalette(colors=colors)

    @pytest.fixture
    def palette_with_duplicates(self) -> SheetPalette:
        """Create a palette with duplicate colors."""
        colors = [
            (0, 0, 0),  # Index 0: transparent
            (255, 0, 0),  # Index 1: red
            (0, 255, 0),  # Index 2: green
            (255, 0, 0),  # Index 3: DUPLICATE of index 1
            (0, 0, 255),  # Index 4: blue
            (255, 0, 0),  # Index 5: DUPLICATE of index 1
            (255, 255, 0),  # Index 6: yellow
            (0, 255, 255),  # Index 7: cyan
            (255, 0, 255),  # Index 8: magenta
            (128, 128, 128),  # Index 9: gray
            (64, 64, 64),  # Index 10: dark gray
            (192, 192, 192),  # Index 11: light gray
            (128, 0, 0),  # Index 12: dark red
            (0, 128, 0),  # Index 13: dark green
            (0, 0, 128),  # Index 14: dark blue
            (128, 128, 0),  # Index 15: olive
        ]
        return SheetPalette(colors=colors)

    def test_no_warning_when_no_duplicates(
        self, qtbot: QtBot, ai_frame: AIFrame, palette_no_duplicates: SheetPalette
    ) -> None:
        """No warning should be shown when palette has no duplicate colors."""
        from ui.frame_mapping.windows.ai_frame_palette_editor import AIFramePaletteEditorWindow

        editor = AIFramePaletteEditorWindow(ai_frame, palette_no_duplicates)
        qtbot.addWidget(editor)
        editor.show()
        qtbot.wait(20)

        assert not editor.has_duplicate_color_warning()
        assert not editor._duplicate_warning_label.isVisible()

    def test_warning_shown_when_duplicates_exist(
        self, qtbot: QtBot, ai_frame: AIFrame, palette_with_duplicates: SheetPalette
    ) -> None:
        """Warning should be shown when palette has duplicate colors."""
        from ui.frame_mapping.windows.ai_frame_palette_editor import AIFramePaletteEditorWindow

        editor = AIFramePaletteEditorWindow(ai_frame, palette_with_duplicates)
        qtbot.addWidget(editor)
        editor.show()
        qtbot.wait(20)

        assert editor.has_duplicate_color_warning()
        assert editor._duplicate_warning_label.isVisible()

    def test_warning_text_mentions_index(
        self, qtbot: QtBot, ai_frame: AIFrame, palette_with_duplicates: SheetPalette
    ) -> None:
        """Warning text should mention index loss issue."""
        from ui.frame_mapping.windows.ai_frame_palette_editor import AIFramePaletteEditorWindow

        editor = AIFramePaletteEditorWindow(ai_frame, palette_with_duplicates)
        qtbot.addWidget(editor)

        warning_text = editor._duplicate_warning_label.text().lower()
        # Should mention index or duplicate
        assert "index" in warning_text or "duplicate" in warning_text


class TestDuplicateColorDetection:
    """Tests for the _has_duplicate_colors() detection method."""

    def test_detects_duplicates(self) -> None:
        """_has_duplicate_colors should return True for palette with duplicates."""
        from ui.frame_mapping.windows.ai_frame_palette_editor import _has_duplicate_colors

        colors = [
            (0, 0, 0),
            (255, 0, 0),
            (0, 255, 0),
            (255, 0, 0),  # Duplicate
        ]
        assert _has_duplicate_colors(colors)

    def test_no_duplicates(self) -> None:
        """_has_duplicate_colors should return False for unique colors."""
        from ui.frame_mapping.windows.ai_frame_palette_editor import _has_duplicate_colors

        colors = [
            (0, 0, 0),
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
        ]
        assert not _has_duplicate_colors(colors)

    def test_ignores_transparent_index(self) -> None:
        """Should ignore index 0 (transparent) in duplicate detection."""
        from ui.frame_mapping.windows.ai_frame_palette_editor import _has_duplicate_colors

        # Index 0 is often black for transparency - shouldn't count as duplicate
        colors = [
            (0, 0, 0),  # Index 0 (transparent)
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
        ]
        assert not _has_duplicate_colors(colors)
