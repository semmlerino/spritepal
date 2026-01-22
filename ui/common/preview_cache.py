"""
LRU Cache for slider scrubbing previews to enable instant display.

Architecture Note:
    This cache is part of the UI preview stack, separate from core/services/preview_generator.py:

    UI Layer (this module + smart_preview_coordinator.py):
        - SliderPreviewCache: Fast in-memory LRU cache for offset slider scrubbing
        - SmartPreviewCoordinator: Manages drag state, debouncing, and worker coordination
        - Used for real-time 60 FPS preview updates during slider interaction

    Core Layer (core/services/preview_generator.py):
        - PreviewGenerator: General-purpose preview generation service
        - Used for one-shot preview generation in dialogs and other non-slider contexts

    The separation is intentional: slider interaction requires specialized timing/debouncing
    that would complicate the general-purpose preview generator.

Features:
- LRU eviction policy to manage memory usage
- Cache key generation based on ROM path and offset
- Thread-safe operations for concurrent access
- Size-based eviction to prevent memory bloat
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast, override

from core.services.lru_cache import BaseLRUCache
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Type alias for preview data tuple: (tile_data, width, height, sprite_name, compressed_size, slack_size, actual_offset, hal_succeeded, header_bytes)
PreviewData = tuple[bytes, int, int, str | None, int, int, int, bool, bytes]


def _calculate_preview_size(data: PreviewData) -> int:
    """Calculate byte size of preview data tuple."""
    (
        tile_data,
        _width,
        _height,
        sprite_name,
        _compressed_size,
        _slack_size,
        _actual_offset,
        _hal_succeeded,
        header_bytes,
    ) = data
    name_len = len(sprite_name) if sprite_name else 0
    return len(tile_data) + name_len + len(header_bytes) + 33  # Rough size estimate


class SliderPreviewCache(BaseLRUCache[PreviewData]):
    """LRU cache for slider scrubbing previews.

    Used during ROM offset slider interactions to provide instant feedback.
    This is separate from the preview generation service in core/services/.

    Features:
    - Thread-safe operations (inherited from BaseLRUCache)
    - Size-based eviction (both count and memory)
    - Efficient key generation
    - Memory usage tracking
    """

    def __init__(self, max_size: int = 20, max_memory_mb: float = 2.0):
        """Initialize slider preview cache.

        Args:
            max_size: Maximum number of entries to cache
            max_memory_mb: Maximum memory usage in MB
        """
        super().__init__(
            max_size=max_size,
            max_bytes=int(max_memory_mb * 1024 * 1024),
            size_fn=_calculate_preview_size,
            name="slider_preview_cache",
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
        # Use filename, size and mtime for ROM identity (faster than full path hash)
        try:
            path_obj = Path(rom_path)
            stat = path_obj.stat()
            rom_name = path_obj.name
            rom_size = stat.st_size
            rom_mtime = stat.st_mtime
        except OSError:
            rom_name = Path(rom_path).name if rom_path else "unknown"
            rom_size = 0
            rom_mtime = 0

        # Create key components
        key_parts = [
            rom_name,
            str(rom_size),
            str(rom_mtime),
            f"{offset:06X}",
        ]

        if sprite_config_hash:
            key_parts.append(sprite_config_hash)

        # Generate deterministic key
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()[:16]

    @override
    def get(self, key: str) -> PreviewData:
        """Get cached preview data.

        Args:
            key: Cache key

        Returns:
            Tuple of (tile_data, width, height, sprite_name, compressed_size, slack_size, actual_offset, hal_succeeded, header_bytes) or default tuple if not found
        """
        result = super().get(key)
        if result is None:
            return (b"", 0, 0, None, 0, 0, -1, True, b"")
        return result

    @override
    def get_stats(self) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny] - Cache statistics dict
        """Get cache statistics with backward-compatible keys."""
        base_stats = super().get_stats()
        current_bytes = cast(int, base_stats["current_bytes"])
        max_bytes = cast(int, base_stats["max_bytes"])
        # Add backward-compatible keys
        return {
            **base_stats,
            "entry_count": base_stats["cache_size"],
            "memory_usage_bytes": current_bytes,
            "memory_usage_mb": base_stats["current_mb"],
            "memory_utilization": current_bytes / max_bytes if max_bytes > 0 else 0,
        }
