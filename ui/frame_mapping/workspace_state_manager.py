"""Workspace State Manager.

Manages UI state for the Frame Mapping workspace, including:
- Selection tracking (AI frame, game frame, canvas state) - CACHED from panes
- ROM path tracking
- Directory history
- Project identity tracking
- Auto-advance toggle state

This is a pure state container with no Qt dependencies or signals.

Note: Selection state is cached locally. The workspace panes
(AIFramesPane, CapturesLibraryPane) manage their own selection state.
This manager provides helper properties for convenient access to cached
selection state without requiring pane references.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:

    class SelectionPane(Protocol):
        """Protocol for panes that track selection."""

        def get_selected_id(self) -> str | None:
            """Get the currently selected frame ID from the pane."""
            ...


logger = logging.getLogger(__name__)


class WorkspaceStateManager:
    """State manager for Frame Mapping workspace UI state.

    Tracks selection state, ROM paths, directory history, and other
    workspace-specific UI state. Does not emit signals - state changes
    are transparent to the caller.
    """

    def __init__(self) -> None:
        """Initialize with empty state."""
        # Directory history
        self._last_ai_dir: Path | None = None
        self._last_capture_dir: Path | None = None
        self._project_path: Path | None = None

        # ROM tracking for injection
        self._rom_path: Path | None = None
        self._last_injected_rom: Path | None = None

        # Selection tracking (ID-based - stable across reloads)
        self._selected_ai_frame_id: str | None = None
        self._selected_game_id: str | None = None
        self._current_canvas_game_id: str | None = None

        # Auto-advance toggle state (default: OFF per UX spec)
        self._auto_advance_enabled = False

        # Track stale entry warnings during injection (stores game frame ID)
        self._stale_entry_game_frame_id: str | None = None

        # Track project identity for canvas state preservation
        self._previous_project_id: int | None = None

        # Batch async injection tracking
        self._batch_injection_target_rom: Path | None = None
        self._batch_injection_pending: set[str] = set()
        self._batch_injection_success: set[str] = set()
        self._batch_injection_failed_stale: set[str] = set()
        self._batch_injection_failed_other: set[str] = set()

        # Dirty flag for unsaved changes tracking
        self._dirty: bool = False

    # -------------------------------------------------------------------------
    # Dirty State Tracking
    # -------------------------------------------------------------------------

    @property
    def dirty(self) -> bool:
        """Check if there are unsaved changes."""
        return self._dirty

    @dirty.setter
    def dirty(self, value: bool) -> None:
        """Set the dirty flag."""
        self._dirty = value

    def mark_dirty(self) -> None:
        """Mark workspace as having unsaved changes."""
        self._dirty = True

    # -------------------------------------------------------------------------
    # Directory History Properties
    # -------------------------------------------------------------------------

    @property
    def last_ai_dir(self) -> Path | None:
        """Get the last used AI frames directory."""
        return self._last_ai_dir

    @last_ai_dir.setter
    def last_ai_dir(self, path: Path | None) -> None:
        """Set the last used AI frames directory."""
        self._last_ai_dir = path

    @property
    def last_capture_dir(self) -> Path | None:
        """Get the last used captures directory."""
        return self._last_capture_dir

    @last_capture_dir.setter
    def last_capture_dir(self, path: Path | None) -> None:
        """Set the last used captures directory."""
        self._last_capture_dir = path

    @property
    def project_path(self) -> Path | None:
        """Get the current project path."""
        return self._project_path

    @project_path.setter
    def project_path(self, path: Path | None) -> None:
        """Set the current project path."""
        self._project_path = path

    # -------------------------------------------------------------------------
    # ROM State Properties
    # -------------------------------------------------------------------------

    @property
    def rom_path(self) -> Path | None:
        """Get the ROM path for injection."""
        return self._rom_path

    @rom_path.setter
    def rom_path(self, path: Path | None) -> None:
        """Set the ROM path for injection."""
        self._rom_path = path

    @property
    def last_injected_rom(self) -> Path | None:
        """Get the last injected ROM path."""
        return self._last_injected_rom

    @last_injected_rom.setter
    def last_injected_rom(self, path: Path | None) -> None:
        """Set the last injected ROM path."""
        self._last_injected_rom = path

    def is_rom_valid(self) -> bool:
        """Check if the current ROM path is valid and exists.

        Returns:
            True if rom_path is set and exists, False otherwise.
        """
        return self._rom_path is not None and self._rom_path.exists()

    # -------------------------------------------------------------------------
    # Selection State Properties (Cached for Performance)
    # -------------------------------------------------------------------------
    # NOTE: Panes (AIFramesPane, CapturesLibraryPane) are the SOURCE OF TRUTH
    # for selection state. These properties are CACHED for convenience/performance.
    # When freshness matters, query panes directly via workspace helper methods.

    @property
    def selected_ai_frame_id(self) -> str | None:
        """Get the cached selected AI frame ID.

        NOTE: This is a performance cache. For fresh state, query AIFramesPane
        via workspace._get_selected_ai_frame_id() which checks the pane first.
        """
        return self._selected_ai_frame_id

    @selected_ai_frame_id.setter
    def selected_ai_frame_id(self, frame_id: str | None) -> None:
        """Set the cached selected AI frame ID."""
        self._selected_ai_frame_id = frame_id

    @property
    def selected_game_id(self) -> str | None:
        """Get the cached selected game frame ID.

        NOTE: This is a performance cache. For fresh state, query CapturesLibraryPane
        via workspace._get_selected_game_id() which checks the pane first.
        """
        return self._selected_game_id

    @selected_game_id.setter
    def selected_game_id(self, frame_id: str | None) -> None:
        """Set the cached selected game frame ID."""
        self._selected_game_id = frame_id

    @property
    def current_canvas_game_id(self) -> str | None:
        """Get the game frame ID currently displayed on canvas."""
        return self._current_canvas_game_id

    @current_canvas_game_id.setter
    def current_canvas_game_id(self, frame_id: str | None) -> None:
        """Set the game frame ID currently displayed on canvas."""
        self._current_canvas_game_id = frame_id

    # -------------------------------------------------------------------------
    # Auto-Advance Properties
    # -------------------------------------------------------------------------

    @property
    def auto_advance_enabled(self) -> bool:
        """Get the auto-advance toggle state."""
        return self._auto_advance_enabled

    @auto_advance_enabled.setter
    def auto_advance_enabled(self, enabled: bool) -> None:
        """Set the auto-advance toggle state."""
        self._auto_advance_enabled = enabled

    # -------------------------------------------------------------------------
    # Stale Entry Warning Properties
    # -------------------------------------------------------------------------

    @property
    def stale_entry_game_frame_id(self) -> str | None:
        """Get the game frame ID with stale entry warning."""
        return self._stale_entry_game_frame_id

    @stale_entry_game_frame_id.setter
    def stale_entry_game_frame_id(self, frame_id: str | None) -> None:
        """Set the game frame ID with stale entry warning."""
        self._stale_entry_game_frame_id = frame_id

    # -------------------------------------------------------------------------
    # Project Identity Properties
    # -------------------------------------------------------------------------

    @property
    def previous_project_id(self) -> int | None:
        """Get the previous project identity (id())."""
        return self._previous_project_id

    @previous_project_id.setter
    def previous_project_id(self, project_id: int | None) -> None:
        """Set the previous project identity (id())."""
        self._previous_project_id = project_id

    # -------------------------------------------------------------------------
    # Batch Async Injection Tracking
    # -------------------------------------------------------------------------

    @property
    def batch_injection_target_rom(self) -> Path | None:
        """Get the target ROM for batch injection."""
        return self._batch_injection_target_rom

    @batch_injection_target_rom.setter
    def batch_injection_target_rom(self, path: Path | None) -> None:
        """Set the target ROM for batch injection."""
        self._batch_injection_target_rom = path

    @property
    def batch_injection_pending(self) -> set[str]:
        """Get the set of frame IDs pending injection."""
        return self._batch_injection_pending

    @property
    def batch_injection_success(self) -> set[str]:
        """Get the set of frame IDs that were successfully injected."""
        return self._batch_injection_success

    @property
    def batch_injection_failed_stale(self) -> set[str]:
        """Get the set of frame IDs that failed due to stale entries."""
        return self._batch_injection_failed_stale

    @property
    def batch_injection_failed_other(self) -> set[str]:
        """Get the set of frame IDs that failed for non-stale reasons."""
        return self._batch_injection_failed_other

    def start_batch_injection(self, frame_ids: list[str], target_rom: Path) -> None:
        """Start tracking a batch injection.

        Args:
            frame_ids: List of AI frame IDs to inject
            target_rom: Target ROM path for injection
        """
        self._batch_injection_target_rom = target_rom
        self._batch_injection_pending = set(frame_ids)
        self._batch_injection_success = set()
        self._batch_injection_failed_stale = set()
        self._batch_injection_failed_other = set()

    def clear_batch_injection(self) -> None:
        """Clear batch injection tracking state."""
        self._batch_injection_target_rom = None
        self._batch_injection_pending = set()
        self._batch_injection_success = set()
        self._batch_injection_failed_stale = set()
        self._batch_injection_failed_other = set()

    def is_batch_injection_active(self) -> bool:
        """Check if a batch injection is in progress."""
        return len(self._batch_injection_pending) > 0

    def record_batch_injection_result(self, ai_frame_id: str, success: bool, stale_entries: bool = False) -> None:
        """Record the result of a single injection in the batch.

        Args:
            ai_frame_id: The frame ID that was injected
            success: Whether the injection succeeded
            stale_entries: Whether failure was due to stale entries
        """
        self._batch_injection_pending.discard(ai_frame_id)
        if success:
            self._batch_injection_success.add(ai_frame_id)
        elif stale_entries:
            self._batch_injection_failed_stale.add(ai_frame_id)
        else:
            self._batch_injection_failed_other.add(ai_frame_id)

    def validate_selection_sync(
        self,
        ai_pane: SelectionPane | None,
        captures_pane: SelectionPane | None,
    ) -> None:
        """Debug-only: Log warnings when cached state diverges from panes.

        This method is only active when SPRITEPAL_DEBUG_STATE=1 environment
        variable is set. It helps catch bugs where the cached selection state
        gets out of sync with the actual pane selections.

        The panes are the source of truth - this method validates that our
        cached state matches them.

        Args:
            ai_pane: The AI frames pane (source of truth for AI selection)
            captures_pane: The captures pane (source of truth for game selection)
        """
        if os.environ.get("SPRITEPAL_DEBUG_STATE") != "1":
            return

        # Validate AI frame selection
        if ai_pane is not None:
            pane_ai_selection = ai_pane.get_selected_id()
            if pane_ai_selection != self._selected_ai_frame_id:
                logger.warning(
                    "STATE SYNC: AI frame selection mismatch - pane=%r, cached=%r",
                    pane_ai_selection,
                    self._selected_ai_frame_id,
                )

        # Validate game frame selection
        if captures_pane is not None:
            pane_game_selection = captures_pane.get_selected_id()
            if pane_game_selection != self._selected_game_id:
                logger.warning(
                    "STATE SYNC: Game frame selection mismatch - pane=%r, cached=%r",
                    pane_game_selection,
                    self._selected_game_id,
                )
