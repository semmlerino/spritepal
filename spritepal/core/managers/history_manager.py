"""
History Manager for sprite history and recent files.

This manager handles sprite history tracking and recent files management.
It's extracted from ApplicationStateManager to follow the Single Responsibility
Principle.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, override

from PySide6.QtCore import QObject, Signal

from .base_manager import BaseManager


class HistoryManager(BaseManager):
    """
    Manager for sprite history and recent files.

    Provides:
    - Sprite history tracking with deduplication
    - Recent files list management
    - History limits and cleanup
    """

    DEFAULT_MAX_HISTORY = 50
    DEFAULT_MAX_RECENT_FILES = 20

    # Signals
    sprite_added = Signal(int, float)  # offset, quality
    history_updated = Signal(list)  # list of offsets
    history_changed = Signal()  # generic history change
    recent_files_changed = Signal()  # generic recent files change

    def __init__(
        self,
        max_history: int = DEFAULT_MAX_HISTORY,
        max_recent_files: int = DEFAULT_MAX_RECENT_FILES,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the history manager.

        Args:
            max_history: Maximum number of sprites in history
            max_recent_files: Maximum number of recent files
            parent: Optional Qt parent object
        """
        self._max_history = max_history
        self._max_recent_files = max_recent_files
        self._sprite_history: list[dict[str, Any]] = []
        self._recent_files: list[str] = []
        self._history_lock = threading.RLock()

        super().__init__("HistoryManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize the history manager."""
        self._is_initialized = True
        self._logger.info("HistoryManager initialized")

    @override
    def cleanup(self) -> None:
        """Clean up resources."""
        with self._history_lock:
            self._sprite_history.clear()
            self._recent_files.clear()
        super().cleanup()

    # ========== Sprite History ==========

    def add_sprite_to_history(
        self,
        offset: int,
        rom_path: str | None = None,
        quality: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Add sprite to history.

        Args:
            offset: ROM offset of sprite
            rom_path: Path to ROM file (optional)
            quality: Quality score (0.0 to 1.0)
            metadata: Optional additional metadata

        Returns:
            True if added (not duplicate), False if duplicate
        """
        with self._history_lock:
            # Check for duplicate
            if any(s["offset"] == offset for s in self._sprite_history):
                return False

            # Create sprite info
            sprite_info: dict[str, Any] = {
                "offset": offset,
                "quality": quality,
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "metadata": metadata or {},
            }
            if rom_path:
                sprite_info["rom_path"] = rom_path

            # Add to history
            self._sprite_history.append(sprite_info)

            # Enforce limit
            if len(self._sprite_history) > self._max_history:
                self._sprite_history = self._sprite_history[-self._max_history :]

            # Emit signals
            self.sprite_added.emit(offset, quality)
            self.history_updated.emit([s["offset"] for s in self._sprite_history])
            self.history_changed.emit()

            return True

    def get_sprite_history(self) -> Sequence[dict[str, Any]]:
        """Get full sprite history (read-only snapshot)."""
        with self._history_lock:
            return tuple(self._sprite_history)

    def clear_sprite_history(self) -> None:
        """Clear sprite history."""
        with self._history_lock:
            self._sprite_history.clear()
            self.history_updated.emit([])
            self.history_changed.emit()

    @property
    def history_count(self) -> int:
        """Get number of items in sprite history."""
        with self._history_lock:
            return len(self._sprite_history)

    # ========== Recent Files ==========

    def add_recent_file(self, file_path: str) -> None:
        """
        Add a file to recent files list.

        Moves the file to the front if it already exists.

        Args:
            file_path: Path to the file
        """
        with self._history_lock:
            # Remove if exists (to move to front)
            if file_path in self._recent_files:
                self._recent_files.remove(file_path)

            # Add to front
            self._recent_files.insert(0, file_path)

            # Enforce limit
            if len(self._recent_files) > self._max_recent_files:
                self._recent_files = self._recent_files[: self._max_recent_files]

            self.recent_files_changed.emit()

    def get_recent_files(self, max_files: int | None = None) -> list[str]:
        """
        Get recent files list.

        Args:
            max_files: Maximum number of files to return (None for all)

        Returns:
            List of recent file paths
        """
        with self._history_lock:
            if max_files is None:
                return list(self._recent_files)
            return list(self._recent_files[:max_files])

    def clear_recent_files(self) -> None:
        """Clear recent files list."""
        with self._history_lock:
            self._recent_files.clear()
            self.recent_files_changed.emit()

    def remove_recent_file(self, file_path: str) -> bool:
        """
        Remove a file from recent files list.

        Args:
            file_path: Path to remove

        Returns:
            True if removed, False if not found
        """
        with self._history_lock:
            if file_path in self._recent_files:
                self._recent_files.remove(file_path)
                self.recent_files_changed.emit()
                return True
            return False

    @property
    def recent_files_count(self) -> int:
        """Get number of recent files."""
        with self._history_lock:
            return len(self._recent_files)

    # ========== Serialization (for settings persistence) ==========

    def get_state(self) -> dict[str, Any]:
        """
        Get serializable state for persistence.

        Returns:
            Dictionary with sprite_history and recent_files
        """
        with self._history_lock:
            return {
                "sprite_history": list(self._sprite_history),
                "recent_files": list(self._recent_files),
            }

    def restore_state(self, state: dict[str, Any]) -> None:
        """
        Restore state from persisted data.

        Args:
            state: Dictionary with sprite_history and recent_files
        """
        with self._history_lock:
            self._sprite_history = list(state.get("sprite_history", []))
            self._recent_files = list(state.get("recent_files", []))
            self.history_changed.emit()
            self.recent_files_changed.emit()
