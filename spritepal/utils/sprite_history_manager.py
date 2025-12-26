"""
Sprite history management utilities.

This module provides non-Qt history management for sprite tracking,
including duplicate prevention, limit enforcement, and data management.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class SpriteHistoryManager:
    """
    Manages sprite history with duplicate prevention and size limits.

    This class provides pure Python history management without Qt dependencies,
    making it suitable for both UI and non-UI contexts.
    """

    MAX_HISTORY = 50  # Default maximum history items

    def __init__(self, max_history: int | None = None):
        """
        Initialize sprite history manager.

        Args:
            max_history: Maximum number of history items (default: 50)
        """
        self._max_history = max_history or self.MAX_HISTORY
        self._found_sprites: list[dict[str, Any]] = []  # pyright: ignore[reportExplicitAny] - Sprite history dict

    def add_sprite(self, offset: int, quality: float = 1.0) -> bool:
        """
        Add a sprite to history if not duplicate.

        Args:
            offset: ROM offset of the sprite
            quality: Quality score (0.0 to 1.0)

        Returns:
            True if sprite was added (not a duplicate), False otherwise
        """
        # Check for duplicate
        if self.has_sprite(offset):
            return False

        # Create sprite info
        sprite_info = {"offset": offset, "quality": quality, "timestamp": datetime.now(tz=UTC)}

        # Add to history
        self._found_sprites.append(sprite_info)

        # Enforce limit
        self._enforce_limit()

        return True

    def has_sprite(self, offset: int) -> bool:
        """
        Check if sprite at offset already exists in history.

        Args:
            offset: ROM offset to check

        Returns:
            True if sprite exists in history
        """
        return any(s["offset"] == offset for s in self._found_sprites)

    def clear_history(self):
        """Clear all sprite history."""
        self._found_sprites.clear()

    def get_sprites(self) -> list[tuple[int, float]]:
        """
        Get all sprites as (offset, quality) tuples.

        Returns:
            List of (offset, quality) tuples
        """
        return [(s["offset"], s["quality"]) for s in self._found_sprites]

    def get_sprite_count(self) -> int:
        """
        Get the number of sprites in history.

        Returns:
            Number of sprites
        """
        return len(self._found_sprites)

    def _enforce_limit(self):
        """Enforce the maximum history limit by removing oldest items."""
        while len(self._found_sprites) > self._max_history:
            self._found_sprites.pop(0)  # Remove oldest
