"""Tests for Captures Library pane filter sync on link status change."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.frame_mapping_project import GameFrame
from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane


@pytest.fixture
def pane_with_captures(qtbot, tmp_path):
    """Create CapturesLibraryPane with 3 game frames, all unlinked."""
    captures_dir = tmp_path / "captures"
    captures_dir.mkdir()
    frames = []
    for i in range(3):
        capture_path = captures_dir / f"capture_{i:03d}.json"
        capture_path.write_text("{}")
        frames.append(
            GameFrame(
                id=f"game_{i:03d}",
                rom_offsets=[0x100000 + i * 0x100],
                capture_path=capture_path,
                palette_index=7,
                width=8,
                height=8,
                selected_entry_ids=[i],
            )
        )
    pane = CapturesLibraryPane()
    qtbot.addWidget(pane)
    pane.set_game_frames(frames)
    return pane, frames


class TestCapturesFilterSync:
    """Test that link status changes refilter when unlinked filter is active."""

    def test_linked_frame_hidden_when_unlinked_filter_active(self, pane_with_captures):
        """Link a frame while unlinked filter is on → frame disappears."""
        pane, frames = pane_with_captures
        # Enable unlinked filter
        pane._show_unlinked_only = True
        pane._refresh_list()
        assert pane._list.count() == 3  # All 3 unlinked

        # Link status change: game_000 gets linked
        pane.update_single_item_link_status(frames[0].id, "some_ai_frame")

        # Frame should disappear from filtered list
        assert pane._list.count() == 2

    def test_unlinked_frame_appears_when_unlinked_filter_active(self, pane_with_captures):
        """Unlink a previously linked frame while filter is on → frame reappears."""
        pane, frames = pane_with_captures
        # Set one frame as linked first
        pane.set_link_status({frames[0].id: "some_ai_frame"})
        # Enable unlinked filter
        pane._show_unlinked_only = True
        pane._refresh_list()
        assert pane._list.count() == 2  # Only unlinked visible

        # Unlink: game_000 becomes unlinked
        pane.update_single_item_link_status(frames[0].id, None)

        # Frame should reappear
        assert pane._list.count() == 3

    def test_no_refresh_when_no_filter_active(self, pane_with_captures):
        """Link status change without filter → in-place update only."""
        pane, frames = pane_with_captures
        assert pane._list.count() == 3

        # Link without filter
        pane.update_single_item_link_status(frames[0].id, "some_ai_frame")

        # All items still visible
        assert pane._list.count() == 3
        # Check text was updated in-place
        item = pane._list.item(0)
        assert item is not None
        assert "✓" in item.text()
