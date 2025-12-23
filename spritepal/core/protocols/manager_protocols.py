"""
Protocol definitions for managers to break circular dependencies.
These protocols define the interfaces that managers must implement.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from PIL import Image
    from PySide6.QtCore import Signal

    from core.types import SpritePreset


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

    def read_rom_header(self, rom_path: str) -> Mapping[str, object]:
        """
        Read ROM header from file path.

        Args:
            rom_path: Path to ROM file as string

        Returns:
            Dictionary with header information
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

    def generate_preview(self, vram_path: str, offset: int) -> tuple[Image.Image, int]:
        """Generate a preview image from VRAM at the specified offset.

        Args:
            vram_path: Path to VRAM dump file
            offset: Offset in VRAM to start extracting from

        Returns:
            Tuple of (PIL image, tile count)
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

    def validate_injection_params(self, params: Mapping[str, object]) -> None:
        """
        Validate injection parameters.

        Args:
            params: Parameters to validate

        Raises:
            ValidationError: If parameters are invalid
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

    def is_injection_active(self) -> bool:
        """
        Check if injection is currently active.

        Returns:
            True if injection is running
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

    def load_rom_info(self, rom_path: str) -> Mapping[str, object] | None:
        """
        Load ROM information and sprite locations.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dict with header, sprite_locations, etc., or None on failure
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
# ApplicationStateManagerProtocol. Use inject(ApplicationStateManagerProtocol) for
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

    def get_rom_info(self, rom_path: str) -> Mapping[str, object] | None:
        """Get cached ROM information (header, etc.)."""
        ...

    def save_rom_info(self, rom_path: str, rom_info: Mapping[str, object]) -> bool:
        """Save ROM information to cache."""
        ...

    def clear_scan_progress_cache(self, rom_path: str | None = None,
                                 scan_params: Mapping[str, int] | None = None) -> int:
        """Clear scan progress caches."""
        ...

    def clear_preview_cache(self, rom_path: str | None = None) -> int:
        """Clear preview data caches."""
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

    def get_offset_suggestions(self, rom_path: str, current_offset: int | None = None,
                              limit: int = 10) -> list[Mapping[str, object]]:
        """Get offset suggestions based on cached scan results and preview data."""
        ...

    def refresh_settings(self) -> None:
        """Refresh cache settings from settings manager."""
        ...


class ConfigurationServiceProtocol(Protocol):
    """
    Protocol for centralized application path configuration.

    This protocol defines the interface for the ConfigurationService,
    which provides a single source of truth for all application paths.
    """

    @property
    def app_root(self) -> Path:
        """Application root directory (where launch_spritepal.py lives)."""
        ...

    @property
    def settings_file(self) -> Path:
        """Path to the settings JSON file."""
        ...

    @property
    def log_directory(self) -> Path:
        """Directory for log files."""
        ...

    @property
    def cache_directory(self) -> Path:
        """Directory for ROM cache files."""
        ...

    @property
    def config_directory(self) -> Path:
        """Directory for configuration files (sprite locations, etc.)."""
        ...

    @property
    def default_dumps_directory(self) -> Path:
        """Default directory for Mesen2 debug dumps."""
        ...

    @property
    def sprite_config_file(self) -> Path:
        """Path to sprite_locations.json configuration file."""
        ...

    def resolve_path(self, path_key: str) -> Path:
        """
        Resolve a path by key (for extensibility).

        Args:
            path_key: Path identifier

        Returns:
            Resolved Path

        Raises:
            KeyError: If path_key is not recognized
        """
        ...

    def ensure_directories_exist(self) -> None:
        """Create required directories if they don't exist."""
        ...

    def set_settings_manager(self, settings_manager: ApplicationStateManagerProtocol) -> None:
        """Set settings manager for user override resolution."""
        ...


class PathSuggestionServiceProtocol(Protocol):
    """
    Protocol for path suggestion service.

    Provides smart file path suggestions for injection workflows using
    multiple strategies: metadata, session data, basename patterns, etc.
    """

    def set_session_manager_getter(
        self, getter: Callable[[], ApplicationStateManagerProtocol | None]
    ) -> None:
        """Set the session manager getter for session-based strategies."""
        ...

    def validate_path(self, path: str | None) -> str:
        """Validate and return path if it exists, empty string otherwise."""
        ...

    def find_vram_path(
        self,
        sprite_path: str,
        metadata_path: str = "",
        metadata: Mapping[str, object] | None = None,
        pre_suggested: str = "",
        strip_editor_suffixes: bool = False,
    ) -> str:
        """
        Find VRAM path using multiple strategies in priority order.

        Args:
            sprite_path: Path to sprite file
            metadata_path: Optional metadata file path
            metadata: Pre-loaded metadata dict
            pre_suggested: Pre-suggested VRAM path to check first
            strip_editor_suffixes: Strip editor suffixes from sprite name

        Returns:
            Suggested VRAM path or empty string if none found
        """
        ...

    def get_smart_vram_suggestion(
        self, sprite_path: str, metadata_path: str = ""
    ) -> str:
        """Get smart VRAM file suggestion for injection."""
        ...

    def find_suggested_input_vram(
        self,
        sprite_path: str,
        metadata: Mapping[str, object] | None = None,
        suggested_vram: str = "",
    ) -> str:
        """Find the best suggestion for input VRAM path."""
        ...

    def suggest_output_path(
        self,
        input_path: str,
        suffix: str,
        extension: str | None = None,
        preserve_parent: bool = False,
    ) -> str:
        """Generic output path suggestion with smart numbering."""
        ...

    def suggest_output_vram_path(self, input_vram_path: str) -> str:
        """Suggest output VRAM path based on input path."""
        ...

    def suggest_output_rom_path(self, input_rom_path: str) -> str:
        """Suggest output ROM path based on input path."""
        ...


# ========== Application State Manager Protocol ==========


class ApplicationStateManagerProtocol(Protocol):
    """Protocol for the consolidated application state manager.

    Manages workflow state, session persistence, settings access, cache statistics,
    runtime state, and current offset coordination. This is the primary protocol
    for application state - inject this for all state management needs.
    """

    # Workflow signals
    workflow_state_changed: Signal  # Signal(object, object) - old_state, new_state

    # Session signals
    session_changed: Signal  # Signal() - session data modified
    files_updated: Signal  # Signal(dict) - file paths changed
    session_restored: Signal  # Signal(dict) - session loaded from disk

    # Settings signals
    settings_saved: Signal  # Signal() - settings persisted to disk

    # Cache signals
    cache_stats_updated: Signal  # Signal(dict) - updated cache metrics

    # State signals
    state_changed: Signal  # Signal(str, dict) - category, data

    # Offset signals
    current_offset_changed: Signal  # Signal(int) - ROM offset changed
    preview_ready: Signal  # Signal(int, QImage) - offset, preview_image

    # Additional signals
    application_state_snapshot: Signal  # Signal(dict) - full state for debugging
    history_updated: Signal  # Signal(list) - list of sprite offsets
    sprite_added: Signal  # Signal(int, float) - offset, quality_score

    # ----- Workflow State Methods -----

    @property
    def workflow_state(self) -> object:
        """Get current workflow state (ExtractionState)."""
        ...

    @property
    def is_workflow_busy(self) -> bool:
        """Check if a blocking operation is in progress."""
        ...

    @property
    def can_extract(self) -> bool:
        """Check if extraction can be started."""
        ...

    def transition_workflow(
        self, new_state: object, error_message: str | None = None
    ) -> bool:
        """Attempt to transition to a new workflow state."""
        ...

    # ----- Session Persistence Methods -----

    def save_session(self, path: Path | None = None) -> bool:
        """Save current session state."""
        ...

    def load_session(self, path: Path) -> bool:
        """Load session state from file."""
        ...

    def get_session_data(self) -> Mapping[str, object]:
        """Get current session data."""
        ...

    def clear_session(self) -> None:
        """Clear current session data."""
        ...

    def update_session_data(self, data: Mapping[str, object]) -> None:
        """Update multiple session values at once."""
        ...

    # ----- Settings Access Methods -----

    def get_setting(self, category: str, key: str, default: object = None) -> object:
        """Get a persistent setting value."""
        ...

    def set_setting(self, category: str, key: str, value: object) -> None:
        """Set a persistent setting value."""
        ...

    def save_settings(self) -> bool:
        """Save settings to disk."""
        ...

    def get(self, category: str, key: str, default: object = None) -> object:
        """Get a setting value by category and key."""
        ...

    def set(self, category: str, key: str, value: object) -> None:
        """Set a setting value by category and key."""
        ...

    def get_window_geometry(self) -> Mapping[str, int | list[int]]:
        """Get saved window geometry including splitter sizes."""
        ...

    def update_window_state(self, geometry: Mapping[str, int | float | list[int]]) -> None:
        """Update window geometry in settings including splitter sizes."""
        ...

    # ----- Cache Stats Methods -----

    def record_cache_hit(self) -> None:
        """Record a cache hit in session statistics."""
        ...

    def record_cache_miss(self) -> None:
        """Record a cache miss in session statistics."""
        ...

    def get_cache_session_stats(self) -> Mapping[str, int]:
        """Get current cache session statistics."""
        ...

    # ----- Runtime State Methods -----

    def get_state(self, namespace: str, key: str, default: object = None) -> object:
        """Get runtime state value (not persisted)."""
        ...

    def set_state(
        self, namespace: str, key: str, value: object, ttl_seconds: float | None = None
    ) -> None:
        """Set runtime state value."""
        ...

    def clear_state(self, namespace: str | None = None) -> None:
        """Clear runtime state."""
        ...

    # ----- Current Offset Methods -----

    def set_current_offset(self, offset: int) -> None:
        """Set the current ROM offset and emit signal."""
        ...

    def get_current_offset(self) -> int | None:
        """Get the current ROM offset."""
        ...

    # ----- Settings Convenience Methods (from SettingsManager) -----

    @property
    def app_name(self) -> str:
        """Get the application name."""
        ...

    def get_ui_data(self) -> Mapping[str, object]:
        """Get UI settings."""
        ...

    def save_ui_data(self, ui_data: Mapping[str, object]) -> None:
        """Save UI settings."""
        ...

    def validate_file_paths(self) -> Mapping[str, str]:
        """Validate and return existing file paths from session."""
        ...

    def has_valid_session(self) -> bool:
        """Check if there's a valid session to restore."""
        ...

    def get_default_directory(self) -> str:
        """Get the default directory for file operations."""
        ...

    def set_last_used_directory(self, directory: str) -> None:
        """Set the last used directory."""
        ...

    def get_cache_settings(self) -> Mapping[str, object]:
        """Get all cache settings."""
        ...

    def set_cache_enabled(self, enabled: bool) -> None:
        """Enable or disable caching."""
        ...

    def get_cache_enabled(self) -> bool:
        """Check if caching is enabled."""
        ...

    def set_cache_location(self, location: str) -> None:
        """Set custom cache location."""
        ...

    def get_cache_location(self) -> str:
        """Get custom cache location (empty string means default)."""
        ...

    def get_cache_max_size_mb(self) -> int:
        """Get maximum cache size in MB."""
        ...

    def set_cache_max_size_mb(self, size_mb: int) -> None:
        """Set maximum cache size in MB."""
        ...

    def get_cache_expiration_days(self) -> int:
        """Get cache expiration in days."""
        ...

    def set_cache_expiration_days(self, days: int) -> None:
        """Set cache expiration in days."""
        ...


class SpritePresetManagerProtocol(Protocol):
    """Protocol for sprite preset management.

    Manages user-defined sprite presets with persistence, ROM matching,
    and import/export functionality for community sharing.
    """

    # Signals
    preset_added: Signal  # Signal(str) - preset name
    preset_removed: Signal  # Signal(str) - preset name
    preset_updated: Signal  # Signal(str) - preset name
    presets_loaded: Signal  # Signal()
    presets_imported: Signal  # Signal(int) - number imported

    # CRUD operations
    def add_preset(self, preset: SpritePreset) -> bool:
        """Add a new preset. Returns True if added."""
        ...

    def update_preset(self, preset: SpritePreset) -> bool:
        """Update an existing preset. Returns True if updated."""
        ...

    def remove_preset(self, name: str) -> bool:
        """Remove a preset by name. Returns True if removed."""
        ...

    def get_preset(self, name: str) -> SpritePreset | None:
        """Get a preset by name."""
        ...

    def get_all_presets(self) -> list[SpritePreset]:
        """Get all user presets."""
        ...

    def get_presets_for_game(self, game_title: str) -> list[SpritePreset]:
        """Get all presets for a specific game."""
        ...

    def get_presets_for_checksum(self, checksum: int) -> list[SpritePreset]:
        """Get all presets that match a ROM checksum."""
        ...

    def get_presets_by_tag(self, tag: str) -> list[SpritePreset]:
        """Get all presets with a specific tag."""
        ...

    # Import/Export
    def export_presets(
        self,
        path: Path,
        preset_names: list[str] | None = None,
    ) -> int:
        """Export presets to a file. Returns number exported."""
        ...

    def import_presets(
        self,
        path: Path,
        overwrite_existing: bool = False,
    ) -> int:
        """Import presets from a file. Returns number imported."""
        ...

    # Utility methods
    def has_preset(self, name: str) -> bool:
        """Check if a preset with the given name exists."""
        ...

    def get_preset_count(self) -> int:
        """Get the total number of presets."""
        ...

    def get_all_game_titles(self) -> list[str]:
        """Get list of unique game titles in presets."""
        ...

    def get_all_tags(self) -> list[str]:
        """Get list of all unique tags."""
        ...

    def clear_all(self) -> None:
        """Remove all presets."""
        ...

    def reload(self) -> None:
        """Reload presets from disk."""
        ...

