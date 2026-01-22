"""Tests for CapturesLibraryPane list refresh selection preservation.

Bug: list refreshes during link status or preview updates dropped user selection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QPixmap

from core.frame_mapping_project import GameFrame
from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def create_game_frames(num_frames: int = 5) -> list[GameFrame]:
    """Create a list of GameFrame objects for testing."""
    return [GameFrame(id=f"F{i:03d}", rom_offsets=[0x1000 * (i + 1)]) for i in range(num_frames)]


class TestRefreshPreservesSelection:
    """Tests for CapturesLibraryPane selection preservation during refreshes."""

    def test_captures_pane_preserves_selection_on_link_status_update(self, qtbot: QtBot) -> None:
        """Refreshing link status must not clear the currently selected capture."""
        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)

        frame_a = GameFrame(id="F001", rom_offsets=[0x1000])
        frame_b = GameFrame(id="F002", rom_offsets=[0x2000])
        pane.set_game_frames([frame_a, frame_b])

        pane.select_frame("F001")
        assert pane.get_selected_id() == "F001"

        # Simulate project_changed refresh
        pane.set_link_status({"F001": 0, "F002": None})

        assert pane.get_selected_id() == "F001"  # Selection preserved

    def test_captures_pane_preserves_selection_on_preview_update(self, qtbot: QtBot) -> None:
        """Refreshing previews must not clear the currently selected capture."""
        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)

        frame_a = GameFrame(id="F001", rom_offsets=[0x1000])
        frame_b = GameFrame(id="F002", rom_offsets=[0x2000])
        pane.set_game_frames([frame_a, frame_b])

        pane.select_frame("F002")
        assert pane.get_selected_id() == "F002"

        # Simulate preview refresh with pixmaps
        pane.set_game_frame_previews({"F001": QPixmap(32, 32), "F002": QPixmap(32, 32)})

        assert pane.get_selected_id() == "F002"  # Selection preserved

    def test_link_status_update_does_not_emit_spurious_selection_signal(self, qtbot: QtBot) -> None:
        """set_link_status must not emit game_frame_selected during refresh."""
        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)

        frame_a = GameFrame(id="F001", rom_offsets=[0x1000])
        pane.set_game_frames([frame_a])
        pane.select_frame("F001")

        emissions: list[str | None] = []
        pane.game_frame_selected.connect(lambda x: emissions.append(x))

        pane.set_link_status({"F001": 0})

        assert emissions == []  # No spurious signal

    def test_preview_update_does_not_emit_spurious_selection_signal(self, qtbot: QtBot) -> None:
        """set_game_frame_previews must not emit game_frame_selected during refresh."""
        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)

        frame_a = GameFrame(id="F001", rom_offsets=[0x1000])
        pane.set_game_frames([frame_a])
        pane.select_frame("F001")

        emissions: list[str | None] = []
        pane.game_frame_selected.connect(lambda x: emissions.append(x))

        pane.set_game_frame_previews({"F001": QPixmap(32, 32)})

        assert emissions == []  # No spurious signal

    def test_selection_preserved_when_frame_remains_visible(self, qtbot: QtBot) -> None:
        """Selection preserved when frame is still visible after status update."""
        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)

        frame_a = GameFrame(id="F001", rom_offsets=[0x1000])
        frame_b = GameFrame(id="F002", rom_offsets=[0x2000])
        pane.set_game_frames([frame_a, frame_b])

        # Select an unlinked frame
        pane.select_frame("F001")
        assert pane.get_selected_id() == "F001"

        # Update link status where F001 remains unlinked
        pane.set_link_status({"F001": None, "F002": 0})

        # Selection should be preserved
        assert pane.get_selected_id() == "F001"
