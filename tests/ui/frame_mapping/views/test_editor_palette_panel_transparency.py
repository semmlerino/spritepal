"""Tests for index 0 transparency indicator in editor palette panel.

Verifies that index 0 is visually marked as the transparency slot.
"""

from __future__ import annotations

import pytest

from ui.frame_mapping.views.editor_palette_panel import ColorSwatch, EditorPalettePanel


class TestIndex0TransparencyIndicator:
    """Tests for index 0 transparency visual indicator."""

    def test_swatch_0_returns_transparency_text(
        self,
        qtbot,
    ) -> None:
        """Swatch at index 0 should return 'T' as its display text."""
        swatch = ColorSwatch(0, (0, 0, 0))
        qtbot.addWidget(swatch)

        assert swatch.get_display_text() == "T"

    def test_swatch_nonzero_returns_index_number(
        self,
        qtbot,
    ) -> None:
        """Non-zero swatches should return their index as display text."""
        swatch = ColorSwatch(5, (128, 128, 128))
        qtbot.addWidget(swatch)

        assert swatch.get_display_text() == "5"

    def test_panel_has_transparency_note(
        self,
        qtbot,
    ) -> None:
        """Panel should have a note explaining index 0 is transparent."""
        panel = EditorPalettePanel()
        qtbot.addWidget(panel)

        # The transparency note should mention index 0 or transparent
        note_text = panel._transparency_note.text().lower()
        assert "0" in note_text or "transparent" in note_text
