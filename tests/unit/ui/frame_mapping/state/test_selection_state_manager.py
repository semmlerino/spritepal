"""Tests for SelectionStateManager."""

from __future__ import annotations

import pytest

from ui.frame_mapping.state.selection_state_manager import SelectionStateManager


class TestSelectionStateManager:
    """Tests for SelectionStateManager behavior."""

    def test_initial_state_uses_default_behavior(self) -> None:
        """Initially, should_check returns True if mapped."""
        manager = SelectionStateManager()

        assert not manager.is_tracking_user_selections()
        assert manager.should_check("frame1", is_mapped=True) is True
        assert manager.should_check("frame2", is_mapped=False) is False

    def test_toggle_checked_starts_tracking(self) -> None:
        """After toggle_checked, manager tracks user selections."""
        manager = SelectionStateManager()
        manager.toggle_checked("frame1", checked=True)

        assert manager.is_tracking_user_selections()
        # Only explicitly checked frames return True
        assert manager.should_check("frame1", is_mapped=True) is True
        assert manager.should_check("frame2", is_mapped=True) is False  # Not checked

    def test_set_baseline_then_toggle(self) -> None:
        """Setting baseline before toggle preserves existing state."""
        manager = SelectionStateManager()

        # Simulate: user had frame1 and frame2 checked, then unchecks frame2
        manager.set_baseline({"frame1", "frame2", "frame3"})
        manager.toggle_checked("frame2", checked=False)

        assert manager.should_check("frame1", is_mapped=True) is True
        assert manager.should_check("frame2", is_mapped=True) is False
        assert manager.should_check("frame3", is_mapped=True) is True

    def test_select_all_sets_mapped_frames(self) -> None:
        """select_all sets all provided frame IDs as checked."""
        manager = SelectionStateManager()
        manager.select_all({"frame1", "frame3"})

        assert manager.is_tracking_user_selections()
        assert manager.should_check("frame1", is_mapped=True) is True
        assert manager.should_check("frame2", is_mapped=True) is False
        assert manager.should_check("frame3", is_mapped=True) is True

    def test_deselect_all_clears_all(self) -> None:
        """deselect_all clears all selections."""
        manager = SelectionStateManager()
        manager.select_all({"frame1", "frame2"})
        manager.deselect_all()

        assert manager.is_tracking_user_selections()
        # All should be unchecked
        assert manager.should_check("frame1", is_mapped=True) is False
        assert manager.should_check("frame2", is_mapped=True) is False

    def test_update_from_refresh_only_when_tracking(self) -> None:
        """update_from_refresh only updates if already tracking."""
        manager = SelectionStateManager()

        # Before any user interaction - should not start tracking
        manager.update_from_refresh({"frame1", "frame2"})
        assert not manager.is_tracking_user_selections()
        # Default behavior still applies
        assert manager.should_check("frame1", is_mapped=True) is True
        assert manager.should_check("frame1", is_mapped=False) is False

        # After user interaction - updates tracked state
        manager.toggle_checked("frame3", checked=True)
        manager.update_from_refresh({"frame4", "frame5"})

        # Now uses the refreshed state
        assert manager.should_check("frame3", is_mapped=True) is False
        assert manager.should_check("frame4", is_mapped=True) is True
        assert manager.should_check("frame5", is_mapped=True) is True

    def test_reset_returns_to_default_behavior(self) -> None:
        """reset() returns to default behavior (check if mapped)."""
        manager = SelectionStateManager()
        manager.select_all({"frame1"})
        assert manager.is_tracking_user_selections()

        manager.reset()

        assert not manager.is_tracking_user_selections()
        # Back to default behavior
        assert manager.should_check("frame1", is_mapped=True) is True
        assert manager.should_check("frame2", is_mapped=True) is True
        assert manager.should_check("frame3", is_mapped=False) is False

    def test_get_checked_ids_returns_copy(self) -> None:
        """get_checked_ids returns a copy, not the internal set."""
        manager = SelectionStateManager()
        manager.select_all({"frame1", "frame2"})

        checked = manager.get_checked_ids()
        assert checked == {"frame1", "frame2"}

        # Modifying returned set should not affect internal state
        if checked is not None:
            checked.add("frame3")
        assert manager.get_checked_ids() == {"frame1", "frame2"}

    def test_get_checked_ids_returns_none_when_not_tracking(self) -> None:
        """get_checked_ids returns None when using default behavior."""
        manager = SelectionStateManager()
        assert manager.get_checked_ids() is None
