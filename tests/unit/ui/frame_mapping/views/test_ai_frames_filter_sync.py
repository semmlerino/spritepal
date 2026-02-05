"""Tests for AI Frames pane filter sync on status change."""

from __future__ import annotations

import pytest

from core.frame_mapping_project import AIFrame
from tests.fixtures.frame_mapping_helpers import MINIMAL_PNG_DATA
from ui.frame_mapping.views.ai_frames_pane import AIFramesPane


@pytest.fixture
def pane_with_frames(qtbot, tmp_path):
    """Create AIFramesPane with 3 frames, all unmapped."""
    ai_dir = tmp_path / "ai_frames"
    ai_dir.mkdir()
    frames = []
    for i in range(3):
        p = ai_dir / f"frame_{i:03d}.png"
        p.write_bytes(MINIMAL_PNG_DATA)
        frames.append(AIFrame(path=p, index=i, width=1, height=1))
    pane = AIFramesPane()
    qtbot.addWidget(pane)
    pane.set_ai_frames(frames)
    return pane, frames


class TestAIFramesFilterSync:
    """Test that status changes refilter when unmapped filter is active."""

    def test_mapped_frame_hidden_when_unmapped_filter_active(self, pane_with_frames):
        """Map a frame while unmapped filter is on → frame disappears, count updates."""
        pane, frames = pane_with_frames
        # Enable unmapped filter
        pane._show_unmapped_only = True
        pane._refresh_list()
        assert pane._list.count() == 3  # All 3 unmapped

        # Status change: frame_000 becomes mapped
        pane.update_single_item_status(frames[0].id, "mapped")

        # Frame should disappear from filtered list
        assert pane._list.count() == 2
        assert pane._count_label.text() == "2/3"

    def test_unmapped_frame_appears_when_unmapped_filter_active(self, pane_with_frames):
        """Unmap a previously mapped frame while filter is on → frame reappears."""
        pane, frames = pane_with_frames
        # Set one frame as mapped first
        pane.set_mapping_status({frames[0].id: "mapped"})
        # Enable unmapped filter
        pane._show_unmapped_only = True
        pane._refresh_list()
        assert pane._list.count() == 2  # Only unmapped frames visible

        # Status change: frame_000 becomes unmapped again
        pane.update_single_item_status(frames[0].id, "unmapped")

        # Frame should reappear
        assert pane._list.count() == 3

    def test_no_refresh_when_no_filter_active(self, pane_with_frames):
        """Status change without filter active → in-place update, no item count change."""
        pane, frames = pane_with_frames
        assert pane._list.count() == 3

        # Status change without filter
        pane.update_single_item_status(frames[0].id, "mapped")

        # All items still visible (just color/text changed)
        assert pane._list.count() == 3
        # Check text was updated in-place
        item = pane._list.item(0)
        assert item is not None
        assert "●" in item.text()
