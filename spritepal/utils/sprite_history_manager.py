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
        sprite_info = {
            "offset": offset,
            "quality": quality,
            "timestamp": datetime.now(tz=UTC)
        }

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

    def get_sprite_info(self, offset: int) -> dict[str, Any] | None:  # pyright: ignore[reportExplicitAny] - Sprite info dict
        """
        Get detailed info for a specific sprite.

        Args:
            offset: ROM offset of the sprite

        Returns:
            Sprite info dict or None if not found
        """
        for sprite in self._found_sprites:
            if sprite["offset"] == offset:
                return sprite.copy()
        return None

    def set_sprites(self, sprites: list[tuple[int, float]]):
        """
        Set sprites from a list, replacing existing history.

        Args:
            sprites: List of (offset, quality) tuples
        """
        self.clear_history()
        for offset, quality in sprites:
            self.add_sprite(offset, quality)

    def get_sprite_count(self) -> int:
        """
        Get the number of sprites in history.

        Returns:
            Number of sprites
        """
        return len(self._found_sprites)

    def get_max_history(self) -> int:
        """
        Get the maximum history limit.

        Returns:
            Maximum number of history items
        """
        return self._max_history

    def set_max_history(self, max_history: int):
        """
        Set the maximum history limit.

        Args:
            max_history: New maximum (must be > 0)
        """
        if max_history <= 0:
            raise ValueError("Maximum history must be positive")

        self._max_history = max_history
        self._enforce_limit()

    def _enforce_limit(self):
        """Enforce the maximum history limit by removing oldest items."""
        while len(self._found_sprites) > self._max_history:
            self._found_sprites.pop(0)  # Remove oldest

    def get_history_items(self) -> list[str]:
        """
        Get formatted history items for display.

        Returns:
            List of formatted strings
        """
        items = []
        for sprite in self._found_sprites:
            offset = sprite["offset"]
            quality = sprite["quality"]
            items.append(f"0x{offset:06X} - Quality: {quality:.2f}")
        return items

    def remove_sprite(self, offset: int) -> bool:
        """
        Remove a sprite from history.

        Args:
            offset: ROM offset of sprite to remove

        Returns:
            True if sprite was removed, False if not found
        """
        for i, sprite in enumerate(self._found_sprites):
            if sprite["offset"] == offset:
                self._found_sprites.pop(i)
                return True
        return False

    def get_most_recent(self, count: int = 10) -> list[tuple[int, float]]:
        """
        Get the most recent sprites.

        Args:
            count: Number of recent sprites to return

        Returns:
            List of (offset, quality) tuples for most recent sprites
        """
        recent = self._found_sprites[-count:] if count > 0 else []
        return [(s["offset"], s["quality"]) for s in reversed(recent)]

    def get_highest_quality(self, count: int = 10) -> list[tuple[int, float]]:
        """
        Get sprites with highest quality scores.

        Args:
            count: Number of top sprites to return

        Returns:
            List of (offset, quality) tuples sorted by quality
        """
        sorted_sprites = sorted(
            self._found_sprites,
            key=lambda s: s["quality"],
            reverse=True
        )
        top_sprites = sorted_sprites[:count] if count > 0 else []
        return [(s["offset"], s["quality"]) for s in top_sprites]
