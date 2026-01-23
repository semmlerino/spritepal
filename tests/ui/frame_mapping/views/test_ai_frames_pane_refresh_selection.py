"""Tests for AIFramesPane list refresh selection preservation.

Bug: list refreshes during alignment updates caused spurious selection changes.

Signal migration: ai_frame_selected now emits str (frame ID/filename) instead of int (index).
- Selection: emits frame ID like "frame_002.png"
- Cleared selection: emits empty string ""
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.frame_mapping_project import AIFrame
from ui.frame_mapping.views.ai_frames_pane import AIFramesPane

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def create_ai_frames(tmp_path: Path, num_frames: int = 5) -> list[AIFrame]:
    """Create a list of AIFrame objects with minimal PNG files."""
    ai_frames_dir = tmp_path / "ai_frames"
    ai_frames_dir.mkdir(parents=True, exist_ok=True)

    frames: list[AIFrame] = []
    for i in range(num_frames):
        frame_path = ai_frames_dir / f"frame_{i:03d}.png"
        frame_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        frames.append(AIFrame(path=frame_path, index=i, width=1, height=1))

    return frames


class TestRefreshPreservesSelection:
    """Tests for AIFramesPane selection preservation during refreshes."""

    def test_set_mapping_status_does_not_emit_selection(self, qtbot: QtBot, tmp_path: Path) -> None:
        """set_mapping_status should preserve selection without emitting signals."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)
        pane.select_frame(2)
        assert pane.get_selected_index() == 2

        signal_emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda frame_id: signal_emissions.append(frame_id))

        # Use AI frame IDs (filenames) as keys
        status_map = {f"frame_{i:03d}.png": "mapped" for i in range(5)}
        pane.set_mapping_status(status_map)

        assert pane.get_selected_index() == 2
        assert signal_emissions == []

    def test_set_ai_frames_preserves_selection(self, qtbot: QtBot, tmp_path: Path) -> None:
        """set_ai_frames should preserve selection when frames are unchanged."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)
        pane.select_frame(3)
        assert pane.get_selected_index() == 3

        signal_emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda frame_id: signal_emissions.append(frame_id))

        pane.set_ai_frames(frames)

        assert pane.get_selected_index() == 3
        assert signal_emissions == []


class TestFilterClearsSelectionSignal:
    """Tests for Bug #1: selection state desync when filter hides selected item."""

    def test_filter_hides_selected_item_emits_deselection_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """When unmapped filter hides a mapped (selected) frame, signal must emit empty string."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)

        # Mark frame 2 as mapped (use AI frame IDs as keys)
        pane.set_mapping_status({
            "frame_000.png": "unmapped",
            "frame_001.png": "unmapped",
            "frame_002.png": "mapped",
            "frame_003.png": "unmapped",
            "frame_004.png": "unmapped",
        })

        # Select the mapped frame
        pane.select_frame(2)
        assert pane.get_selected_index() == 2

        # Now listen for signals
        signal_emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda frame_id: signal_emissions.append(frame_id))

        # Enable "show unmapped only" filter - should hide frame 2
        pane._unmapped_filter.setChecked(True)

        # Selection should be cleared and signal should emit empty string
        assert pane.get_selected_index() is None
        assert signal_emissions == [""], f"Expected [''], got {signal_emissions}"

    def test_search_hides_selected_item_emits_deselection_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """When search filter hides selected frame, signal must emit empty string."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)

        # Select frame_002.png
        pane.select_frame(2)
        assert pane.get_selected_index() == 2

        # Now listen for signals
        signal_emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda frame_id: signal_emissions.append(frame_id))

        # Search for "frame_004" - should hide frame_002
        pane._search_box.setText("frame_004")

        # Selection should be cleared and signal should emit empty string
        assert pane.get_selected_index() is None
        assert signal_emissions == [""], f"Expected [''], got {signal_emissions}"

    def test_no_signal_when_selection_preserved_after_filter(self, qtbot: QtBot, tmp_path: Path) -> None:
        """No deselection signal when filter doesn't hide the selected item."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)

        # Mark all as unmapped except frame 3 (use AI frame IDs as keys)
        pane.set_mapping_status({
            "frame_000.png": "unmapped",
            "frame_001.png": "unmapped",
            "frame_002.png": "unmapped",
            "frame_003.png": "mapped",
            "frame_004.png": "unmapped",
        })

        # Select an unmapped frame
        pane.select_frame(0)
        assert pane.get_selected_index() == 0

        # Now listen for signals
        signal_emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda frame_id: signal_emissions.append(frame_id))

        # Enable "show unmapped only" filter - frame 0 is unmapped, should remain visible
        pane._unmapped_filter.setChecked(True)

        # Selection should be preserved and no signal emitted
        assert pane.get_selected_index() == 0
        assert signal_emissions == []


class TestProjectReloadSignaling:
    """Tests for Phase 2 bug: silent selection restoration after project reload.

    Bug: When project is reloaded (set_ai_frames called with new frame list),
    selection that was preserved should emit signal to notify listeners (like canvas).
    Currently blocks signals, restores silently, then unblocks - workspace never knows
    selection was restored, leaving canvas showing stale data.

    Signal migration: Now emits frame ID (filename) instead of index.
    """

    def test_project_reload_with_selection_emits_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Reloading project with same selection should emit signal to sync canvas."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        # Initial project with 5 frames
        frames_v1 = create_ai_frames(tmp_path / "v1", num_frames=5)
        pane.set_ai_frames(frames_v1)
        pane.select_frame(2)

        # Set up signal listener
        signal_emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda frame_id: signal_emissions.append(frame_id))

        # Reload project with new frames (e.g., from disk)
        # The frames are different objects but represent the same logical frames
        frames_v2 = create_ai_frames(tmp_path / "v2", num_frames=5)

        # Before fix: Selection is restored silently, no signal
        # After fix: Signal emitted to notify workspace canvas to update
        pane.set_ai_frames(frames_v2)

        # Selection should still be at frame 2
        assert pane.get_selected_index() == 2

        # BUG: signal_emissions is empty - workspace never syncs canvas
        # FIX: Should emit frame ID to notify workspace canvas to update
        assert signal_emissions == ["frame_002.png"], (
            f"Expected signal emission ['frame_002.png'] after project reload with preserved selection, "
            f"got {signal_emissions}. Canvas would show stale data from old project."
        )

    def test_project_reload_without_selection_emits_clear_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Reloading project that loses selection should emit empty string signal."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        # Initial project with 5 frames
        frames_v1 = create_ai_frames(tmp_path / "v1", num_frames=5)
        pane.set_ai_frames(frames_v1)
        pane.select_frame(2)

        # Set up signal listener
        signal_emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda frame_id: signal_emissions.append(frame_id))

        # Reload with fewer frames (selected frame no longer exists)
        frames_v2 = create_ai_frames(tmp_path / "v2", num_frames=2)  # Only 2 frames now
        pane.set_ai_frames(frames_v2)

        # Selection should be cleared
        assert pane.get_selected_index() is None

        # Should emit empty string to notify workspace to clear mapping panel
        assert signal_emissions == [""], (
            f"Expected deselection signal [''] when reload loses selection, got {signal_emissions}"
        )


class TestIDBasedSelectionMethods:
    """Tests for new ID-based selection methods (part of signal migration)."""

    def test_get_selected_id_returns_filename(self, qtbot: QtBot, tmp_path: Path) -> None:
        """get_selected_id should return the filename of the selected frame."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)
        pane.select_frame(2)

        assert pane.get_selected_id() == "frame_002.png"

    def test_get_selected_id_returns_none_when_no_selection(self, qtbot: QtBot, tmp_path: Path) -> None:
        """get_selected_id should return None when nothing is selected."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)

        # Clear selection
        pane._list.clearSelection()
        pane._list.setCurrentRow(-1)

        assert pane.get_selected_id() is None

    def test_select_frame_by_id(self, qtbot: QtBot, tmp_path: Path) -> None:
        """select_frame_by_id should select the frame with matching ID."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)

        pane.select_frame_by_id("frame_003.png")

        assert pane.get_selected_index() == 3
        assert pane.get_selected_id() == "frame_003.png"

    def test_select_frame_by_id_does_not_emit_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """select_frame_by_id should block signals like select_frame does."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)

        signal_emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda frame_id: signal_emissions.append(frame_id))

        pane.select_frame_by_id("frame_003.png")

        assert signal_emissions == []

    def test_user_selection_emits_id(self, qtbot: QtBot, tmp_path: Path) -> None:
        """User-initiated selection should emit frame ID via signal."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)

        signal_emissions: list[str] = []
        pane.ai_frame_selected.connect(lambda frame_id: signal_emissions.append(frame_id))

        # Simulate user selection by setting current row (without blocking signals)
        pane._list.setCurrentRow(2)

        assert signal_emissions == ["frame_002.png"]
