"""Manager for injection selection state.

Tracks which AI frames are selected for batch injection. This is business logic
that was previously embedded in MappingPanel. The manager handles:
- Default behavior: all mapped frames are checked
- User overrides: when user explicitly checks/unchecks frames
- State preservation: across view refreshes
"""

from __future__ import annotations

from utils.logging_config import get_logger

logger = get_logger(__name__)


class BatchSelectionManager:
    """Manages AI frame selection state for batch injection.

    Selection behavior:
    - Before any user interaction: default behavior (mapped frames are checked)
    - After first checkbox toggle: user's explicit choices are tracked
    - State is preserved across refresh() calls
    - Resets to default behavior on project change
    """

    def __init__(self) -> None:
        """Initialize the batch selection manager."""
        # None = use default behavior (check all mapped frames)
        # set[str] = explicit user selections (even if empty)
        self._user_checked_ids: set[str] | None = None

    # ─── State Queries ───────────────────────────────────────────────────────

    def is_tracking_user_selections(self) -> bool:
        """Check if user has explicitly modified checkbox selections.

        Returns:
            True if user has toggled checkboxes, False if using default behavior.
        """
        return self._user_checked_ids is not None

    def should_check(self, ai_frame_id: str, is_mapped: bool) -> bool:
        """Determine if a frame should be checked in the UI.

        Args:
            ai_frame_id: The AI frame ID to check.
            is_mapped: Whether the frame has a mapping.

        Returns:
            True if the checkbox should be checked.
        """
        if self._user_checked_ids is not None:
            result = ai_frame_id in self._user_checked_ids
            logger.debug(
                "should_check: id=%s, in_tracked=%s, result=%s",
                ai_frame_id,
                result,
                result,
            )
            return result
        logger.debug(
            "should_check: id=%s, is_mapped=%s (default mode)",
            ai_frame_id,
            is_mapped,
        )
        return is_mapped  # Default: check if mapped

    def get_checked_ids(self) -> set[str] | None:
        """Get the set of explicitly checked frame IDs.

        Returns:
            Set of checked IDs if user has made selections, None for default behavior.
        """
        if self._user_checked_ids is None:
            return None
        return self._user_checked_ids.copy()

    # ─── State Mutations ─────────────────────────────────────────────────────

    def toggle_checked(self, ai_frame_id: str, checked: bool) -> None:
        """Handle user toggling a checkbox.

        On first call, captures the baseline state. On subsequent calls,
        updates the tracked set.

        Args:
            ai_frame_id: The AI frame ID that was toggled.
            checked: New checked state.
        """
        if self._user_checked_ids is None:
            # First user interaction - caller should provide baseline via set_baseline
            logger.debug("toggle_checked: FIRST toggle, was_None=True")
            self._user_checked_ids = set()

        if checked:
            self._user_checked_ids.add(ai_frame_id)
        else:
            self._user_checked_ids.discard(ai_frame_id)
        logger.debug(
            "toggle_checked: id=%s, checked=%s, tracked_ids=%s",
            ai_frame_id,
            checked,
            self._user_checked_ids,
        )

    def set_baseline(self, checked_ids: set[str]) -> None:
        """Set the baseline checked state from current UI.

        Called on first user checkbox interaction to capture current state
        before applying the toggle.

        Args:
            checked_ids: Set of currently checked AI frame IDs.
        """
        logger.debug("set_baseline: captured %d ids: %s", len(checked_ids), checked_ids)
        self._user_checked_ids = checked_ids.copy()

    def select_all(self, mapped_frame_ids: set[str]) -> None:
        """Select all mapped frames for injection.

        Args:
            mapped_frame_ids: Set of AI frame IDs that have mappings.
        """
        logger.debug("select_all: setting tracked_ids to %s", mapped_frame_ids)
        self._user_checked_ids = mapped_frame_ids.copy()

    def deselect_all(self) -> None:
        """Deselect all frames for injection."""
        logger.debug("deselect_all: setting tracked_ids to empty set")
        self._user_checked_ids = set()

    def update_from_refresh(self, current_checked_ids: set[str]) -> None:
        """Update tracked state from view during refresh.

        Only updates if we're already tracking user selections.

        Args:
            current_checked_ids: Currently checked IDs from UI.
        """
        if self._user_checked_ids is not None:
            logger.debug(
                "update_from_refresh: updating tracked state from %s to %s",
                self._user_checked_ids,
                current_checked_ids,
            )
            self._user_checked_ids = current_checked_ids.copy()
        else:
            logger.debug(
                "update_from_refresh: skipped (not tracking), captured=%s",
                current_checked_ids,
            )

    def reset(self) -> None:
        """Reset to default behavior.

        Called on project change to restore default (all mapped = checked).
        """
        logger.debug("reset: clearing tracked state, was=%s", self._user_checked_ids)
        self._user_checked_ids = None
