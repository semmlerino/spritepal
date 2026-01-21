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
