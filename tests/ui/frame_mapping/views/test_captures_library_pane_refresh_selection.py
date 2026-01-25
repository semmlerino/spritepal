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


class TestFilterDoesNotClearExternalSelection:
    """Tests for correct behavior: filter hiding selection should NOT emit deselection.

    The workspace state manager is the source of truth for selection, not the pane.
    When a filter hides the selected item, the pane should NOT emit "" because
    that would incorrectly clear the workspace selection state. This matches
    AIFramesPane behavior (see ai_frames_pane.py:636-638).
    """

    def test_filter_hides_selected_item_does_not_emit_signal(self, qtbot: QtBot) -> None:
        """When unlinked filter hides a linked (selected) frame, no signal should emit.

        The workspace state manager maintains the selection even when the pane
        can't display it. Emitting "" would incorrectly clear external state.
        """
        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)

        frame_a = GameFrame(id="F001", rom_offsets=[0x1000])
        frame_b = GameFrame(id="F002", rom_offsets=[0x2000])
        pane.set_game_frames([frame_a, frame_b])

        # Mark F001 as linked (has ai_frame_id), F002 as unlinked
        pane.set_link_status({"F001": "frame_0.png", "F002": None})

        # Select the linked frame
        pane.select_frame("F001")
        assert pane.get_selected_id() == "F001"

        # Now listen for signals
        signal_emissions: list[str] = []
        pane.game_frame_selected.connect(lambda fid: signal_emissions.append(fid))

        # Enable "show unlinked only" filter - should hide F001
        pane._unlinked_filter.setChecked(True)

        # Pane returns None because item is hidden, but NO signal should be emitted
        assert pane.get_selected_id() is None
        assert signal_emissions == [], f"Expected no signal, got {signal_emissions}"

    def test_search_hides_selected_item_does_not_emit_signal(self, qtbot: QtBot) -> None:
        """When search filter hides selected frame, no signal should emit.

        The workspace state manager maintains the selection even when the pane
        can't display it. Emitting "" would incorrectly clear external state.
        """
        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)

        frame_a = GameFrame(id="F001", rom_offsets=[0x1000])
        frame_b = GameFrame(id="F002", rom_offsets=[0x2000])
        pane.set_game_frames([frame_a, frame_b])

        # Select F001
        pane.select_frame("F001")
        assert pane.get_selected_id() == "F001"

        # Now listen for signals
        signal_emissions: list[str] = []
        pane.game_frame_selected.connect(lambda fid: signal_emissions.append(fid))

        # Search for "F002" - should hide F001
        pane._search_box.setText("F002")

        # Pane returns None because item is hidden, but NO signal should be emitted
        assert pane.get_selected_id() is None
        assert signal_emissions == [], f"Expected no signal, got {signal_emissions}"

    def test_no_signal_when_selection_preserved_after_filter(self, qtbot: QtBot) -> None:
        """No deselection signal when filter doesn't hide the selected item."""
        pane = CapturesLibraryPane()
        qtbot.addWidget(pane)

        frame_a = GameFrame(id="F001", rom_offsets=[0x1000])
        frame_b = GameFrame(id="F002", rom_offsets=[0x2000])
        pane.set_game_frames([frame_a, frame_b])

        # Mark F002 as linked, F001 as unlinked
        pane.set_link_status({"F001": None, "F002": 0})

        # Select the unlinked frame
        pane.select_frame("F001")
        assert pane.get_selected_id() == "F001"

        # Now listen for signals
        signal_emissions: list[str] = []
        pane.game_frame_selected.connect(lambda fid: signal_emissions.append(fid))

        # Enable "show unlinked only" filter - F001 is unlinked, should remain visible
        pane._unlinked_filter.setChecked(True)

        # Selection should be preserved and no signal emitted
        assert pane.get_selected_id() == "F001"
        assert signal_emissions == []
