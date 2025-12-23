"""
Protocol definitions for managers to break circular dependencies.
These protocols define the interfaces that managers must implement.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from PySide6.QtCore import Signal


@runtime_checkable
class ExtractionManagerProtocol(Protocol):
    """Protocol for extraction manager."""

    # Signals (accessed via attributes)
    cache_operation_started: Signal  # Signal(str, str) - operation_type, description
    cache_hit: Signal  # Signal(str, float) - cache_key, time_saved
    cache_miss: Signal  # Signal(str) - cache_key
    cache_saved: Signal  # Signal(str, int) - cache_key, size_bytes
    palettes_extracted: Signal  # Signal(list) - extracted palettes
    active_palettes_found: Signal  # Signal(list) - active palettes
    preview_generated: Signal  # Signal(Image, int) - preview image, tile count

    def extract_from_rom(
        self,
        rom_path: str,
        offset: int,
        output_base: str,
        sprite_name: str,
        cgram_path: str | None = None
    ) -> list[str]:
        """
        Extract sprites from ROM at given offset.

        Args:
            rom_path: Path to ROM file
            offset: Starting offset in ROM
            output_base: Base name for output files
            sprite_name: Name of the sprite being extracted
            cgram_path: Optional path to CGRAM palette file

        Returns:
            List of output file paths
        """
        ...

    def get_known_sprite_locations(self, rom_path: str) -> Mapping[str, object]:
        """
        Get known sprite locations for ROM.

        Args:
            rom_path: Path to ROM file as string

        Returns:
            Dictionary with sprite locations
        """
        ...

    def validate_extraction_params(self, params: dict[str, Any]) -> bool:  # pyright: ignore[reportExplicitAny] - params are dynamic extraction config
        """
        Validate extraction parameters.

        Args:
            params: Dictionary of extraction parameters

        Returns:
            True if parameters are valid

        Raises:
            ValueError: If parameters are invalid
        """
        ...

    def get_rom_extractor(self) -> ROMExtractorProtocol:
        """
        Get the ROM extractor instance for advanced operations.

        Returns:
            ROMExtractor instance

        Note:
            This method provides access to the underlying ROM extractor
            for UI components that need direct access to ROM operations.
            Consider using the manager methods when possible.
        """
        ...

    def extract_sprite_to_png(self, rom_path: str, sprite_offset: int,
                              output_path: str, cgram_path: str | None = None) -> bool:
        """Extract a single sprite to PNG file.

        Args:
            rom_path: Path to ROM file
            sprite_offset: Offset of sprite in ROM
            output_path: Full path where PNG should be saved
            cgram_path: Optional CGRAM file for palette data

        Returns:
            True if extraction successful

        Raises:
            ExtractionError: If operation fails (service not initialized, etc.)
        """
        ...


@runtime_checkable
class InjectionManagerProtocol(Protocol):
    """Protocol for injection manager."""

    # Signals (accessed via attributes)
    injection_progress: Signal  # Signal(str) - progress message
    injection_finished: Signal  # Signal(bool, str) - success, message
    cache_saved: Signal  # Signal(str, int) - cache_key, size_bytes

    def start_injection(self, params: Mapping[str, object]) -> bool:
        """
        Start injection process with given parameters.

        Args:
            params: Dictionary of injection parameters

        Returns:
            True if injection started successfully
        """
        ...

    def get_smart_vram_suggestion(
        self,
        sprite_path: str,
        metadata_path: str = ""
    ) -> str:
        """
        Get smart VRAM file suggestion for injection.

        Args:
            sprite_path: Path to sprite file
            metadata_path: Path to metadata file

        Returns:
            Suggested VRAM file path
        """
        ...

    def load_metadata(self, metadata_path: str) -> Mapping[str, object] | None:
        """
        Load and parse metadata file.

        Args:
            metadata_path: Path to metadata JSON file

        Returns:
            Parsed metadata dict or None if loading fails
        """
        ...

    def find_suggested_input_vram(self, sprite_path: str, metadata: Mapping[str, object] | None = None,
                                  suggested_vram: str = "") -> str:
        """Find the best suggestion for input VRAM path.

        Args:
            sprite_path: Path to sprite file
            metadata: Loaded metadata dict (from load_metadata)
            suggested_vram: Pre-suggested VRAM path

        Returns:
            Suggested VRAM path or empty string if none found
        """
        ...

    def suggest_output_vram_path(self, input_vram_path: str) -> str:
        """Suggest output VRAM path based on input path with smart numbering.

        Args:
            input_vram_path: Input VRAM file path

        Returns:
            Suggested output path
        """
        ...

    def suggest_output_rom_path(self, input_rom_path: str) -> str:
        """Suggest output ROM path based on input path with smart numbering.

        Args:
            input_rom_path: Input ROM file path

        Returns:
            Suggested output path (in same directory as input)
        """
        ...

    def load_rom_injection_defaults(self, sprite_path: str, metadata: Mapping[str, object] | None = None
                                    ) -> Mapping[str, object]:
        """Load ROM injection defaults from metadata or saved settings.

        Args:
            sprite_path: Path to sprite file
            metadata: Loaded metadata dict (from load_metadata)

        Returns:
            Dict containing input_rom, output_rom, rom_offset, etc.
        """
        ...

    def restore_saved_sprite_location(self, extraction_vram_offset: str | None,
                                      sprite_locations: Mapping[str, int]) -> Mapping[str, object]:
        """Restore saved sprite location selection.

        Args:
            extraction_vram_offset: VRAM offset from extraction metadata
            sprite_locations: Dict of sprite name -> offset from loaded ROM

        Returns:
            Dict containing sprite_location_name, sprite_location_index, custom_offset
        """
        ...

    def save_rom_injection_settings(self, input_rom: str, sprite_location_text: str,
                                    custom_offset: str, fast_compression: bool) -> None:
        """Save ROM injection parameters to settings for future use.

        Args:
            input_rom: Input ROM path
            sprite_location_text: Selected sprite location text from combo box
            custom_offset: Custom offset text if used
            fast_compression: Fast compression checkbox state
        """
        ...


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

