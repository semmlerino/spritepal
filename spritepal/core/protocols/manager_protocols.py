"""
Protocol definitions for managers to break circular dependencies.
These protocols define the interfaces that managers must implement.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ExtractionManagerProtocol(Protocol):
    """Protocol for extraction manager."""

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

    def read_rom_header(self, rom_path: str) -> dict[str, Any]:
        """
        Read ROM header from file path.

        Args:
            rom_path: Path to ROM file as string

        Returns:
            Dictionary with header information
        """
        ...

    def get_known_sprite_locations(self, rom_path: str) -> dict[str, Any]:
        """
        Get known sprite locations for ROM.

        Args:
            rom_path: Path to ROM file as string

        Returns:
            Dictionary with sprite locations
        """
        ...

    def validate_extraction_params(self, params: dict[str, Any]) -> bool:
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

    def get_rom_extractor(self) -> Any:
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

class InjectionManagerProtocol(Protocol):
    """Protocol for injection manager."""

    def start_injection(self, params: dict[str, Any]) -> bool:
        """
        Start injection process with given parameters.

        Args:
            params: Dictionary of injection parameters

        Returns:
            True if injection started successfully
        """
        ...

    def validate_injection_params(self, params: dict[str, Any]) -> None:
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

    def load_metadata(self, metadata_path: str) -> dict[str, Any] | None:
        """
        Load and parse metadata file.

        Args:
            metadata_path: Path to metadata JSON file

        Returns:
            Parsed metadata dict or None if loading fails
        """
        ...

    def load_rom_info(self, rom_path: str) -> dict[str, Any] | None:
        """
        Load ROM information and sprite locations.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dict with header, sprite_locations, etc., or None on failure
        """
        ...

# SessionManagerProtocol has been consolidated into ApplicationStateManagerProtocol.
# Use inject(ApplicationStateManagerProtocol) for session management functionality.


class SettingsManagerProtocol(Protocol):
    """Protocol for the Settings Manager."""

    app_name: str

    def save_settings(self) -> None:
        """Save settings to file."""
        ...

    def save(self) -> None:
        """Save settings to file (alias for save_settings)."""
        ...

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        ...

    def get_value(self, category: str, key: str, default: Any = None) -> Any:
        """Get a setting value (alias for get method)."""
        ...

    def set(self, category: str, key: str, value: Any) -> None:
        """Set a setting value."""
        ...

    def set_value(self, category: str, key: str, value: Any) -> None:
        """Set a setting value (alias for set method)."""
        ...

    def get_session_data(self) -> dict[str, Any]:
        """Get all session data."""
        ...

    def save_session_data(self, session_data: dict[str, Any]) -> None:
        """Save session data."""
        ...

    def get_ui_data(self) -> dict[str, Any]:
        """Get UI settings."""
        ...

    def save_ui_data(self, ui_data: dict[str, Any]) -> None:
        """Save UI settings."""
        ...

    def validate_file_paths(self) -> dict[str, str]:
        """Validate and return existing file paths from session."""
        ...

    def has_valid_session(self) -> bool:
        """Check if there's a valid session to restore."""
        ...

    def clear_session(self) -> None:
        """Clear session data."""
        ...

    def get_default_directory(self) -> str:
        """Get the default directory for file operations."""
        ...

    def set_last_used_directory(self, directory: str) -> None:
        """Set the last used directory."""
        ...

    def get_cache_settings(self) -> dict[str, Any]:
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


class ROMExtractorProtocol(Protocol):
    """Protocol for the ROM extractor."""

    rom_injector: Any  # ROMInjector instance for compression/decompression operations


class ROMCacheProtocol(Protocol):
    """Protocol for the ROM cache."""

    @property
    def cache_enabled(self) -> bool:
        """Get whether caching is enabled."""
        ...

    def save_partial_scan_results(self, rom_path: str, scan_params: dict[str, int],
                                 found_sprites: list[dict[str, Any]],
                                 current_offset: int, completed: bool = False) -> bool:
        """Save partial scan results for incremental progress."""
        ...

    def get_partial_scan_results(self, rom_path: str, scan_params: dict[str, int]) -> dict[str, Any] | None:
        """Get partial scan results for resuming."""
        ...

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics with error handling."""
        ...

    def clear_cache(self, older_than_days: int | None = None) -> int:
        """Clear cache files and hash cache with error handling."""
        ...

    def get_sprite_locations(self, rom_path: str) -> dict[str, Any] | None:
        """Get cached sprite locations for ROM."""
        ...

    def save_sprite_locations(self, rom_path: str, sprite_locations: dict[str, Any],
                            rom_header: dict[str, Any] | None = None) -> bool:
        """Save sprite locations to cache."""
        ...

    def get_rom_info(self, rom_path: str) -> dict[str, Any] | None:
        """Get cached ROM information (header, etc.)."""
        ...

    def save_rom_info(self, rom_path: str, rom_info: dict[str, Any]) -> bool:
        """Save ROM information to cache."""
        ...

    def clear_scan_progress_cache(self, rom_path: str | None = None,
                                 scan_params: dict[str, int] | None = None) -> int:
        """Clear scan progress caches."""
        ...

    def clear_preview_cache(self, rom_path: str | None = None) -> int:
        """Clear preview data caches."""
        ...

    def save_preview_data(self, rom_path: str, offset: int, tile_data: bytes,
                         width: int, height: int, params: dict[str, Any] | None = None) -> bool:
        """Save preview tile data to cache with compression."""
        ...

    def get_preview_data(self, rom_path: str, offset: int,
                        params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Get cached preview data for ROM and offset."""
        ...

    def save_preview_batch(self, rom_path: str, preview_data_dict: dict[int, dict[str, Any]]) -> bool:
        """Save multiple preview data entries in batch for efficiency."""
        ...

    def get_offset_suggestions(self, rom_path: str, current_offset: int | None = None,
                              limit: int = 10) -> list[dict[str, Any]]:
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

    def set_settings_manager(self, settings_manager: SettingsManagerProtocol) -> None:
        """Set settings manager for user override resolution."""
        ...


# ========== Application State Manager Protocols (A.4) ==========


class ApplicationStateManagerProtocol(Protocol):
    """Protocol for the consolidated application state manager.

    This protocol defines the full interface for ApplicationStateManager,
    including settings, runtime state, workflow, session management, and cache statistics.

    Note: This protocol consolidates SessionManagerProtocol functionality.
    """

    # Signals (accessed via attributes)
    state_changed: Any  # Signal(str, dict)
    workflow_state_changed: Any  # Signal(object, object)
    session_changed: Any  # Signal()
    cache_stats_updated: Any  # Signal(dict)
    current_offset_changed: Any  # Signal(int)
    preview_ready: Any  # Signal(int, QImage)
    application_state_snapshot: Any  # Signal(dict)

    # ========== Settings management ==========
    def get_setting(self, category: str, key: str, default: Any = None) -> Any:
        """Get a persistent setting value."""
        ...

    def set_setting(self, category: str, key: str, value: Any) -> None:
        """Set a persistent setting value."""
        ...

    def save_settings(self) -> bool:
        """Save settings to disk."""
        ...

    # ========== Session management (from SessionManagerProtocol) ==========
    def save_session(self, path: Path | None = None) -> bool:
        """Save current session state."""
        ...

    def load_session(self, path: Path) -> bool:
        """Load session state from file."""
        ...

    def get_session_data(self) -> dict[str, Any]:
        """Get current session data."""
        ...

    def clear_session(self) -> None:
        """Clear current session data."""
        ...

    def update_session_data(self, data: dict[str, Any]) -> None:
        """Update multiple session values at once."""
        ...

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """Get a setting value by category and key."""
        ...

    def set(self, category: str, key: str, value: Any) -> None:
        """Set a setting value by category and key."""
        ...

    def get_window_geometry(self) -> dict[str, int]:
        """Get saved window geometry."""
        ...

    def update_window_state(self, geometry: dict[str, int | float]) -> None:
        """Update window geometry in settings."""
        ...

    # Runtime state management
    def get_state(self, namespace: str, key: str, default: Any = None) -> Any:
        """Get runtime state value (not persisted)."""
        ...

    def set_state(
        self, namespace: str, key: str, value: Any, ttl_seconds: float | None = None
    ) -> None:
        """Set runtime state value."""
        ...

    def clear_state(self, namespace: str | None = None) -> None:
        """Clear runtime state."""
        ...

    # Workflow state
    @property
    def workflow_state(self) -> Any:
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
        self, new_state: Any, error_message: str | None = None
    ) -> bool:
        """Attempt to transition to a new workflow state."""
        ...

    # Cache statistics
    def record_cache_hit(self) -> None:
        """Record a cache hit in session statistics."""
        ...

    def record_cache_miss(self) -> None:
        """Record a cache miss in session statistics."""
        ...

    def get_cache_session_stats(self) -> dict[str, int]:
        """Get current cache session statistics."""
        ...

    # Unified state snapshot
    def get_full_state_snapshot(self) -> dict[str, Any]:
        """Get a complete snapshot of all application state."""
        ...

    def emit_state_snapshot(self) -> dict[str, Any]:
        """Emit a state snapshot signal and return the snapshot."""
        ...

    # Current offset
    def set_current_offset(self, offset: int) -> None:
        """Set the current ROM offset and emit signal."""
        ...

    def get_current_offset(self) -> int | None:
        """Get the current ROM offset."""
        ...
