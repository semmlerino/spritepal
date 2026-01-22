"""Tests for AIFramesPane list refresh selection preservation.

Bug: list refreshes during alignment updates caused spurious selection changes.
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
    ai_frames_dir.mkdir()

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

        signal_emissions: list[int] = []
        pane.ai_frame_selected.connect(lambda idx: signal_emissions.append(idx))

        status_map = dict.fromkeys(range(5), "mapped")
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

        signal_emissions: list[int] = []
        pane.ai_frame_selected.connect(lambda idx: signal_emissions.append(idx))

        pane.set_ai_frames(frames)

        assert pane.get_selected_index() == 3
        assert signal_emissions == []


class TestFilterClearsSelectionSignal:
    """Tests for Bug #1: selection state desync when filter hides selected item."""

    def test_filter_hides_selected_item_emits_deselection_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """When unmapped filter hides a mapped (selected) frame, signal must emit -1."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)

        # Mark frame 2 as mapped
        pane.set_mapping_status({0: "unmapped", 1: "unmapped", 2: "mapped", 3: "unmapped", 4: "unmapped"})

        # Select the mapped frame
        pane.select_frame(2)
        assert pane.get_selected_index() == 2

        # Now listen for signals
        signal_emissions: list[int] = []
        pane.ai_frame_selected.connect(lambda idx: signal_emissions.append(idx))

        # Enable "show unmapped only" filter - should hide frame 2
        pane._unmapped_filter.setChecked(True)

        # Selection should be cleared and signal should emit -1
        assert pane.get_selected_index() is None
        assert signal_emissions == [-1], f"Expected [-1], got {signal_emissions}"

    def test_search_hides_selected_item_emits_deselection_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """When search filter hides selected frame, signal must emit -1."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)

        # Select frame_002.png
        pane.select_frame(2)
        assert pane.get_selected_index() == 2

        # Now listen for signals
        signal_emissions: list[int] = []
        pane.ai_frame_selected.connect(lambda idx: signal_emissions.append(idx))

        # Search for "frame_004" - should hide frame_002
        pane._search_box.setText("frame_004")

        # Selection should be cleared and signal should emit -1
        assert pane.get_selected_index() is None
        assert signal_emissions == [-1], f"Expected [-1], got {signal_emissions}"

    def test_no_signal_when_selection_preserved_after_filter(self, qtbot: QtBot, tmp_path: Path) -> None:
        """No deselection signal when filter doesn't hide the selected item."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames = create_ai_frames(tmp_path, num_frames=5)
        pane.set_ai_frames(frames)

        # Mark all as unmapped except frame 3
        pane.set_mapping_status({0: "unmapped", 1: "unmapped", 2: "unmapped", 3: "mapped", 4: "unmapped"})

        # Select an unmapped frame
        pane.select_frame(0)
        assert pane.get_selected_index() == 0

        # Now listen for signals
        signal_emissions: list[int] = []
        pane.ai_frame_selected.connect(lambda idx: signal_emissions.append(idx))

        # Enable "show unmapped only" filter - frame 0 is unmapped, should remain visible
        pane._unmapped_filter.setChecked(True)

        # Selection should be preserved and no signal emitted
        assert pane.get_selected_index() == 0
        assert signal_emissions == []
