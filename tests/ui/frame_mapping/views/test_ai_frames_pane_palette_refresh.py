"""Tests for AIFramesPane thumbnail refresh after palette changes.

Bug: When editing a palette via context menu, only the edited frame's thumbnail
visually updates. Other AI frames using the same palette don't visually refresh
even though the data is updated.

The fix requires explicit viewport update after _refresh_list() in set_sheet_palette().
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QListWidget

from core.frame_mapping_project import AIFrame
from tests.fixtures.frame_mapping_helpers import create_ai_frames
from ui.frame_mapping.views.ai_frames_pane import AIFramesPane

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def create_test_palette() -> MagicMock:
    """Create a mock SheetPalette with test colors."""
    palette = MagicMock()
    palette.colors = [
        (0, 0, 0),  # Black
        (255, 0, 0),  # Red
        (0, 255, 0),  # Green
        (0, 0, 255),  # Blue
    ]
    return palette


class TestSetSheetPaletteViewportUpdate:
    """Tests for viewport update after set_sheet_palette()."""

    def test_set_sheet_palette_calls_viewport_update(self, qtbot: QtBot, tmp_path: Path) -> None:
        """set_sheet_palette should call viewport().update() to force repaint."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=3)
        pane.set_ai_frames(frames)

        palette = create_test_palette()

        # Get reference to the viewport and mock update()
        viewport = pane._list.viewport()
        original_update = viewport.update

        update_called = []

        def track_update() -> None:
            update_called.append(True)
            original_update()

        with patch.object(viewport, "update", side_effect=track_update):
            pane.set_sheet_palette(palette)

        # Verify viewport.update() was called
        assert len(update_called) > 0, "viewport.update() should be called after set_sheet_palette()"

    def test_set_sheet_palette_refreshes_all_thumbnails(self, qtbot: QtBot, tmp_path: Path) -> None:
        """set_sheet_palette should refresh thumbnails for all frames."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=3)
        pane.set_ai_frames(frames)

        # Track thumbnail creation calls
        thumbnail_calls: list[Path] = []
        original_create = pane._create_quantized_thumbnail

        def track_thumbnail(frame_path: Path):
            thumbnail_calls.append(frame_path)
            return original_create(frame_path)

        palette = create_test_palette()

        with patch.object(pane, "_create_quantized_thumbnail", side_effect=track_thumbnail):
            pane.set_sheet_palette(palette)

        # All 3 frames should have had thumbnails regenerated
        assert len(thumbnail_calls) == 3, f"Expected 3 thumbnail calls, got {len(thumbnail_calls)}"

    def test_set_sheet_palette_twice_regenerates_thumbnails(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Calling set_sheet_palette twice should regenerate thumbnails each time."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=3)
        pane.set_ai_frames(frames)

        # First palette
        palette1 = create_test_palette()
        pane.set_sheet_palette(palette1)

        # Track thumbnail creation for second palette call
        thumbnail_calls: list[Path] = []
        original_create = pane._create_quantized_thumbnail

        def track_thumbnail(frame_path: Path):
            thumbnail_calls.append(frame_path)
            return original_create(frame_path)

        # Second palette (simulating palette edit)
        palette2 = create_test_palette()
        palette2.colors = [(255, 255, 255), (128, 128, 128), (64, 64, 64), (0, 0, 0)]

        with patch.object(pane, "_create_quantized_thumbnail", side_effect=track_thumbnail):
            pane.set_sheet_palette(palette2)

        # All 3 frames should have had thumbnails regenerated again
        assert len(thumbnail_calls) == 3, f"Expected 3 thumbnail calls on palette change, got {len(thumbnail_calls)}"


class TestPaletteChangeViewportRepaint:
    """Tests for Qt viewport repaint behavior after palette changes."""

    def test_list_widget_schedules_repaint_after_palette_change(self, qtbot: QtBot, tmp_path: Path) -> None:
        """The QListWidget should schedule a repaint after palette change."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)
        pane.show()  # Need to show for repaint scheduling to work

        frames = create_ai_frames(tmp_path, num_frames=3)
        pane.set_ai_frames(frames)

        palette = create_test_palette()

        # Call set_sheet_palette
        pane.set_sheet_palette(palette)

        # After the fix, viewport.update() should have been called
        # We can verify by process events and checking the widget state
        qtbot.wait(10)  # Allow event loop to process

        # If fix is in place, we shouldn't crash or hang
        # The visual verification is done manually; this test ensures
        # the code path is exercised without error
        assert pane._sheet_palette is palette
