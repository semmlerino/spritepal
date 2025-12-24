"""
LRU Cache for sprite previews to enable instant display during slider scrubbing.

This module provides a memory-efficient cache for preview data:
- LRU eviction policy to manage memory usage
- Cache key generation based on ROM path and offset
- Thread-safe operations for concurrent access
- Size-based eviction to prevent memory bloat
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from core.services.lru_cache import BaseLRUCache
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Type alias for preview data tuple: (tile_data, width, height, sprite_name)
PreviewData = tuple[bytes, int, int, str | None]


def _calculate_preview_size(data: PreviewData) -> int:
    """Calculate byte size of preview data tuple."""
    tile_data, _width, _height, sprite_name = data
    name_len = len(sprite_name) if sprite_name else 0
    return len(tile_data) + name_len + 16  # Rough size estimate


class SpritePreviewCache(BaseLRUCache[PreviewData]):
    """LRU cache for sprite preview data.

    Features:
    - Thread-safe operations (inherited from BaseLRUCache)
    - Size-based eviction (both count and memory)
    - Efficient key generation
    - Memory usage tracking
    """

    def __init__(self, max_size: int = 20, max_memory_mb: float = 2.0):
        """Initialize preview cache.

        Args:
            max_size: Maximum number of entries to cache
            max_memory_mb: Maximum memory usage in MB
        """
        super().__init__(
            max_size=max_size,
            max_bytes=int(max_memory_mb * 1024 * 1024),
            size_fn=_calculate_preview_size,
            name="sprite_preview_cache",
        )

    @staticmethod
    def make_key(rom_path: str, offset: int, sprite_config_hash: str | None = None) -> str:
        """Generate cache key for preview data.

        Args:
            rom_path: Path to ROM file
            offset: ROM offset for sprite
            sprite_config_hash: Optional sprite configuration hash

        Returns:
            str: Cache key
        """
        # Use filename and size for ROM identity (faster than full path hash)
        try:
            rom_name = Path(rom_path).name
            # Single stat() call avoids TOCTOU race with exists()
            rom_size = Path(rom_path).stat().st_size
        except OSError:
            rom_name = Path(rom_path).name if rom_path else "unknown"
            rom_size = 0

        # Create key components
        key_parts = [
            rom_name,
            str(rom_size),
            f"{offset:06X}",
        ]

        if sprite_config_hash:
            key_parts.append(sprite_config_hash)

        # Generate deterministic key
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()[:16]

    def get(self, key: str) -> PreviewData:
        """Get cached preview data.

        Args:
            key: Cache key

        Returns:
            Tuple of (tile_data, width, height, sprite_name) or empty tuple if not found
        """
        result = super().get(key)
        if result is None:
            return (b"", 0, 0, None)
        return result

    def get_stats(self) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny] - Cache statistics dict
        """Get cache statistics with backward-compatible keys."""
        base_stats = super().get_stats()
        # Add backward-compatible keys
        return {
            **base_stats,
            "entry_count": base_stats["cache_size"],
            "memory_usage_bytes": base_stats["current_bytes"],
            "memory_usage_mb": base_stats["current_mb"],
            "memory_utilization": (
                base_stats["current_bytes"] / base_stats["max_bytes"]
                if base_stats["max_bytes"] > 0 else 0
            ),
        }


# Backward compatibility alias
PreviewCache = SpritePreviewCache
