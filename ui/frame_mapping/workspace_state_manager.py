"""Workspace State Manager.

Manages UI state for the Frame Mapping workspace, including:
- Selection tracking (AI frame, game frame, canvas state)
- ROM path tracking
- Directory history
- Project identity tracking
- Auto-advance toggle state

This is a pure state container with no Qt dependencies or signals.
"""

from __future__ import annotations

from pathlib import Path


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
        self._modified_rom_path: Path | None = None
        self._last_injected_rom: Path | None = None

        # Selection tracking (ID-based - stable across reloads)
        self._selected_ai_frame_id: str | None = None
        self._selected_game_id: str | None = None
        self._current_canvas_game_id: str | None = None

        # Auto-advance toggle state (default: OFF per UX spec)
        self._auto_advance_enabled = False

        # Track stale entry warnings during injection
        self._stale_entry_frame_id: str | None = None

        # Track project identity for canvas state preservation
        self._previous_project_id: int | None = None

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
    def modified_rom_path(self) -> Path | None:
        """Get the modified ROM path."""
        return self._modified_rom_path

    @modified_rom_path.setter
    def modified_rom_path(self, path: Path | None) -> None:
        """Set the modified ROM path."""
        self._modified_rom_path = path

    @property
    def last_injected_rom(self) -> Path | None:
        """Get the last injected ROM path."""
        return self._last_injected_rom

    @last_injected_rom.setter
    def last_injected_rom(self, path: Path | None) -> None:
        """Set the last injected ROM path."""
        self._last_injected_rom = path

    def clear_rom_state(self) -> None:
        """Clear all ROM path state."""
        self._rom_path = None
        self._modified_rom_path = None
        self._last_injected_rom = None

    def is_rom_valid(self) -> bool:
        """Check if the current ROM path is valid and exists.

        Returns:
            True if rom_path is set and exists, False otherwise.
        """
        return self._rom_path is not None and self._rom_path.exists()

    # -------------------------------------------------------------------------
    # Selection State Properties
    # -------------------------------------------------------------------------

    @property
    def selected_ai_frame_id(self) -> str | None:
        """Get the selected AI frame ID."""
        return self._selected_ai_frame_id

    @selected_ai_frame_id.setter
    def selected_ai_frame_id(self, frame_id: str | None) -> None:
        """Set the selected AI frame ID."""
        self._selected_ai_frame_id = frame_id

    @property
    def selected_game_id(self) -> str | None:
        """Get the selected game frame ID."""
        return self._selected_game_id

    @selected_game_id.setter
    def selected_game_id(self, frame_id: str | None) -> None:
        """Set the selected game frame ID."""
        self._selected_game_id = frame_id

    @property
    def current_canvas_game_id(self) -> str | None:
        """Get the game frame ID currently displayed on canvas."""
        return self._current_canvas_game_id

    @current_canvas_game_id.setter
    def current_canvas_game_id(self, frame_id: str | None) -> None:
        """Set the game frame ID currently displayed on canvas."""
        self._current_canvas_game_id = frame_id

    def clear_selections(self) -> None:
        """Clear all selection state."""
        self._selected_ai_frame_id = None
        self._selected_game_id = None
        self._current_canvas_game_id = None

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
    def stale_entry_frame_id(self) -> str | None:
        """Get the frame ID with stale entry warning."""
        return self._stale_entry_frame_id

    @stale_entry_frame_id.setter
    def stale_entry_frame_id(self, frame_id: str | None) -> None:
        """Set the frame ID with stale entry warning."""
        self._stale_entry_frame_id = frame_id

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
