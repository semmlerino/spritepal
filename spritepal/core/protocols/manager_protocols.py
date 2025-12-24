"""
Protocol definitions for managers to break circular dependencies.
These protocols define the interfaces that managers must implement.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from PIL import Image
    from PySide6.QtCore import Signal


# ExtractionManagerProtocol and InjectionManagerProtocol have been removed.
# Use CoreOperationsManager directly via inject(CoreOperationsManager) for
# extraction and injection functionality.
#
# SessionManagerProtocol and SettingsManagerProtocol have been consolidated into
# ApplicationStateManager. Use inject(ApplicationStateManager) for
# session, settings, and state management functionality.


class ROMExtractorProtocol(Protocol):
    """Protocol for the ROM extractor."""

    rom_injector: object  # ROMInjector instance for compression/decompression operations

    def extract_sprite_data(
        self, rom_path: str, sprite_offset: int, sprite_config: Mapping[str, object] | None = None
    ) -> bytes:
        """Extract raw sprite data from ROM at specified offset."""
        ...

    def extract_sprite_from_rom(
        self, rom_path: str, sprite_offset: int, output_base: str, sprite_name: str = ""
    ) -> tuple[str, Mapping[str, str | int | bool]]:
        """Extract sprite from ROM at specified offset."""
        ...

    def get_known_sprite_locations(self, rom_path: str) -> Mapping[str, object]:
        """Get known sprite locations for the given ROM."""
        ...


@runtime_checkable
class ROMCacheProtocol(Protocol):
    """Protocol for the ROM cache."""

    @property
    def cache_enabled(self) -> bool:
        """Get whether caching is enabled."""
        ...

    def save_partial_scan_results(self, rom_path: str, scan_params: Mapping[str, int],
                                 found_sprites: Sequence[Mapping[str, Any]],  # pyright: ignore[reportExplicitAny] - sprite result dicts have mixed types
                                 current_offset: int, completed: bool = False) -> bool:
        """Save partial scan results for incremental progress."""
        ...

    def get_partial_scan_results(self, rom_path: str, scan_params: Mapping[str, int]) -> Mapping[str, object] | None:
        """Get partial scan results for resuming."""
        ...

    def get_cache_stats(self) -> Mapping[str, object]:
        """Get cache statistics with error handling."""
        ...

    def clear_cache(self, older_than_days: int | None = None) -> int:
        """Clear cache files and hash cache with error handling."""
        ...

    def get_sprite_locations(self, rom_path: str) -> Mapping[str, object] | None:
        """Get cached sprite locations for ROM."""
        ...

    def save_sprite_locations(self, rom_path: str, sprite_locations: Mapping[str, object],
                            rom_header: Mapping[str, object] | None = None) -> bool:
        """Save sprite locations to cache."""
        ...

    def clear_scan_progress_cache(self, rom_path: str | None = None,
                                 scan_params: Mapping[str, int] | None = None) -> int:
        """Clear scan progress caches."""
        ...

    def save_preview_data(self, rom_path: str, offset: int, tile_data: bytes,
                         width: int, height: int, params: Mapping[str, object] | None = None) -> bool:
        """Save preview tile data to cache with compression."""
        ...

    def get_preview_data(self, rom_path: str, offset: int,
                        params: Mapping[str, object] | None = None) -> Mapping[str, object] | None:
        """Get cached preview data for ROM and offset."""
        ...

    def save_preview_batch(self, rom_path: str, preview_data_dict: Mapping[int, Mapping[str, object]]) -> bool:
        """Save multiple preview data entries in batch for efficiency."""
        ...

    def refresh_settings(self) -> None:
        """Refresh cache settings from settings manager."""
        ...

    def get_rom_info(self, rom_path: str) -> dict[str, object] | None:
        """Get cached ROM information (header, etc.).

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of ROM info or None if not cached
        """
        ...

    def save_rom_info(self, rom_path: str, rom_info: Mapping[str, object]) -> bool:
        """Save ROM information to cache.

        Args:
            rom_path: Path to ROM file
            rom_info: Dictionary of ROM information to cache

        Returns:
            True if saved successfully, False otherwise
        """
        ...

