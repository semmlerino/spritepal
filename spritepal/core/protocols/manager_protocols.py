"""
Protocol definitions for managers to break circular dependencies.
These protocols define the interfaces that managers must implement.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from PIL import Image


class ExtractionManagerProtocol(Protocol):
    """Protocol for extraction manager."""

    # Signals (accessed via attributes)
    cache_operation_started: Any  # Signal(str, str) - operation_type, description
    cache_hit: Any  # Signal(str, float) - cache_key, time_saved
    cache_miss: Any  # Signal(str) - cache_key
    cache_saved: Any  # Signal(str, int) - cache_key, size_bytes
    palettes_extracted: Any  # Signal(list) - extracted palettes
    active_palettes_found: Any  # Signal(list) - active palettes
    preview_generated: Any  # Signal(Image, int) - preview image, tile count

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
            True if extraction successful, False otherwise
        """
        ...


class InjectionManagerProtocol(Protocol):
    """Protocol for injection manager."""

    # Signals (accessed via attributes)
    injection_progress: Any  # Signal(str) - progress message
    injection_finished: Any  # Signal(bool, str) - success, message
    cache_saved: Any  # Signal(str, int) - cache_key, size_bytes

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

    def find_suggested_input_vram(self, sprite_path: str, metadata: dict[str, Any] | None = None,
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

    def load_rom_injection_defaults(self, sprite_path: str, metadata: dict[str, Any] | None = None
                                    ) -> dict[str, Any]:
        """Load ROM injection defaults from metadata or saved settings.

        Args:
            sprite_path: Path to sprite file
            metadata: Loaded metadata dict (from load_metadata)

        Returns:
            Dict containing input_rom, output_rom, rom_offset, etc.
        """
        ...

    def restore_saved_sprite_location(self, extraction_vram_offset: str | None,
                                      sprite_locations: dict[str, int]) -> dict[str, Any]:
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


# SessionManagerProtocol has been consolidated into ApplicationStateManagerProtocol.
# Use inject(ApplicationStateManagerProtocol) for session management functionality.


class SettingsManagerProtocol(Protocol):
    """Protocol for the Settings Manager."""

    app_name: str

    def save_settings(self) -> None:
        """Save settings to file."""
        ...

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        ...

    def set(self, category: str, key: str, value: Any) -> None:
        """Set a setting value."""
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

    def extract_sprite_data(
        self, rom_path: str, sprite_offset: int, sprite_config: dict[str, Any] | None = None
    ) -> bytes:
        """Extract raw sprite data from ROM at specified offset."""
        ...

    def extract_sprite_from_rom(
        self, rom_path: str, sprite_offset: int, output_base: str, sprite_name: str = ""
    ) -> tuple[str, dict[str, str | int | bool]]:
        """Extract sprite from ROM at specified offset."""
        ...

    def get_known_sprite_locations(self, rom_path: str) -> dict[str, Any]:
        """Get known sprite locations for the given ROM."""
        ...


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


class ROMServiceProtocol(Protocol):
    """Protocol for ROM-based sprite extraction service.

    Provides ROM sprite extraction with palette support, preview generation,
    sprite location discovery with caching, and ROM header reading.
    """

    # Signals (accessed via attributes)
    extraction_progress: Any  # Signal(str) - progress message
    extraction_warning: Any  # Signal(str) - warning message (partial success)
    preview_generated: Any  # Signal(object, int) - PIL Image, tile count
    palettes_extracted: Any  # Signal(dict) - palette data
    active_palettes_found: Any  # Signal(list) - active palette indices
    files_created: Any  # Signal(list) - list of created files
    cache_operation_started: Any  # Signal(str, str) - operation type, cache type
    cache_hit: Any  # Signal(str, float) - cache type, time saved
    cache_miss: Any  # Signal(str) - cache type
    cache_saved: Any  # Signal(str, int) - cache type, number of items
    error_occurred: Any  # Signal(str) - error message

    def cleanup(self) -> None:
        """Cleanup service resources."""
        ...

    def get_rom_extractor(self) -> ROMExtractorProtocol:
        """Get the ROM extractor instance for advanced operations."""
        ...

    def extract_from_rom(
        self,
        rom_path: str,
        offset: int,
        output_base: str,
        sprite_name: str,
        cgram_path: str | None = None,
    ) -> list[str]:
        """Extract sprites from ROM at specific offset.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM to extract from
            output_base: Base name for output files
            sprite_name: Name of the sprite being extracted
            cgram_path: CGRAM dump for palette extraction

        Returns:
            List of created file paths
        """
        ...

    def get_sprite_preview(
        self,
        rom_path: str,
        offset: int,
        sprite_name: str | None = None,
    ) -> tuple[bytes, int, int]:
        """Get a preview of sprite data from ROM without saving files.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM
            sprite_name: Sprite name for logging

        Returns:
            Tuple of (tile_data, width, height)
        """
        ...

    def extract_sprite_to_png(
        self,
        rom_path: str,
        sprite_offset: int,
        output_path: str,
        cgram_path: str | None = None,
    ) -> bool:
        """Extract a single sprite to PNG file.

        Args:
            rom_path: Path to ROM file
            sprite_offset: Offset of sprite in ROM
            output_path: Full path where PNG should be saved
            cgram_path: Optional CGRAM file for palette data

        Returns:
            True if extraction successful, False otherwise
        """
        ...

    def get_known_sprite_locations(self, rom_path: str) -> dict[str, Any]:
        """Get known sprite locations for a ROM with caching.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of known sprite locations
        """
        ...

    def read_rom_header(self, rom_path: str) -> dict[str, Any]:
        """Read ROM header information.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary containing ROM header information
        """
        ...


class VRAMServiceProtocol(Protocol):
    """Protocol for VRAM-based sprite extraction service.

    Provides VRAM sprite extraction with palette support and preview generation.
    """

    # Signals (accessed via attributes)
    extraction_progress: Any  # Signal(str) - progress message
    extraction_warning: Any  # Signal(str) - warning message (partial success)
    preview_generated: Any  # Signal(object, int) - PIL Image, tile count
    palettes_extracted: Any  # Signal(dict) - palette data
    active_palettes_found: Any  # Signal(list) - active palette indices
    files_created: Any  # Signal(list) - list of created files
    error_occurred: Any  # Signal(str) - error message

    def cleanup(self) -> None:
        """Cleanup service resources."""
        ...

    def extract_from_vram(
        self,
        vram_path: str,
        output_base: str,
        cgram_path: str | None = None,
        oam_path: str | None = None,
        vram_offset: int | None = None,
        create_grayscale: bool = True,
        create_metadata: bool = True,
        grayscale_mode: bool = False,
    ) -> list[str]:
        """Extract sprites from VRAM dump.

        Args:
            vram_path: Path to VRAM dump file
            output_base: Base name for output files (without extension)
            cgram_path: Path to CGRAM dump for palette extraction
            oam_path: Path to OAM dump for palette analysis
            vram_offset: Offset in VRAM (default: 0xC000)
            create_grayscale: Create grayscale palette files
            create_metadata: Create metadata JSON file
            grayscale_mode: Skip palette extraction entirely

        Returns:
            List of created file paths
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
    # State signals
    state_changed: Any  # Signal(str, dict) - category, data
    workflow_state_changed: Any  # Signal(object, object) - old_state, new_state
    application_state_snapshot: Any  # Signal(dict) - full state for debugging

    # Session signals
    session_changed: Any  # Signal() - session data modified
    files_updated: Any  # Signal(dict) - file paths changed
    settings_saved: Any  # Signal() - settings persisted to disk
    session_restored: Any  # Signal(dict) - session loaded from disk

    # History signals
    history_updated: Any  # Signal(list) - list of sprite offsets
    sprite_added: Any  # Signal(int, float) - offset, quality_score

    # Cache signals
    cache_stats_updated: Any  # Signal(dict) - updated cache metrics

    # UI coordination signals
    current_offset_changed: Any  # Signal(int) - ROM offset changed
    preview_ready: Any  # Signal(int, QImage) - offset, preview_image

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

    def get_window_geometry(self) -> dict[str, int | list[int]]:
        """Get saved window geometry including splitter sizes."""
        ...

    def update_window_state(self, geometry: dict[str, int | float | list[int]]) -> None:
        """Update window geometry in settings including splitter sizes."""
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


# ========== Extracted Service Protocols ==========


class StateSnapshotServiceProtocol(Protocol):
    """Protocol for state snapshot service.

    Manages creation, storage, and restoration of state snapshots
    for undo/restore functionality.
    """

    # Signals
    snapshot_created: Any  # Signal(str) - snapshot_id
    snapshot_restored: Any  # Signal(str) - snapshot_id

    def create_snapshot(
        self,
        states: dict[str, Any],
        namespace: str | None = None,
    ) -> str:
        """Create a snapshot of the provided state."""
        ...

    def restore_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """Retrieve state from a snapshot."""
        ...

    def get_snapshot_namespace(self, snapshot_id: str) -> str | None:
        """Get the namespace of a snapshot."""
        ...

    def list_snapshots(self) -> list[str]:
        """List all snapshot IDs in creation order."""
        ...

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a specific snapshot."""
        ...

    def clear(self) -> None:
        """Clear all snapshots."""
        ...

    @property
    def count(self) -> int:
        """Get the number of stored snapshots."""
        ...

    def cleanup(self) -> None:
        """Clean up resources."""
        ...


class WorkflowManagerProtocol(Protocol):
    """Protocol for workflow state machine management.

    Manages the extraction workflow state machine including state
    transitions, busy states, and capability queries.
    """

    # Signals
    workflow_state_changed: Any  # Signal(str, str) - old_state, new_state
    workflow_error: Any  # Signal(str) - error message

    @property
    def workflow_state(self) -> Any:
        """Get current workflow state."""
        ...

    @property
    def is_workflow_busy(self) -> bool:
        """Check if workflow is in a busy state."""
        ...

    @property
    def can_extract(self) -> bool:
        """Check if extraction can be started."""
        ...

    @property
    def can_preview(self) -> bool:
        """Check if preview can be generated."""
        ...

    @property
    def can_search(self) -> bool:
        """Check if search can be performed."""
        ...

    @property
    def can_scan(self) -> bool:
        """Check if scan can be started."""
        ...

    @property
    def workflow_error_message(self) -> str | None:
        """Get current workflow error message."""
        ...

    def transition_workflow(
        self, new_state: Any, error_message: str | None = None
    ) -> bool:
        """Attempt to transition to a new workflow state."""
        ...

    def reset_workflow(self) -> None:
        """Reset workflow to IDLE state."""
        ...

    # Convenience transition methods
    def start_loading_rom(self) -> bool:
        """Transition to LOADING_ROM state."""
        ...

    def finish_loading_rom(self, success: bool = True, error: str | None = None) -> bool:
        """Transition from LOADING_ROM to IDLE or ERROR."""
        ...

    def start_scanning(self) -> bool:
        """Transition to SCANNING_SPRITES state."""
        ...

    def finish_scanning(self, success: bool = True, error: str | None = None) -> bool:
        """Transition from SCANNING_SPRITES to IDLE or ERROR."""
        ...

    def start_preview(self) -> bool:
        """Transition to PREVIEWING_SPRITE state."""
        ...

    def finish_preview(self, success: bool = True, error: str | None = None) -> bool:
        """Transition from PREVIEWING_SPRITE to IDLE or ERROR."""
        ...

    def start_extraction(self) -> bool:
        """Transition to EXTRACTING state."""
        ...

    def finish_extraction(self, success: bool = True, error: str | None = None) -> bool:
        """Transition from EXTRACTING to IDLE or ERROR."""
        ...

    def cleanup(self) -> None:
        """Clean up resources."""
        ...


class HistoryManagerProtocol(Protocol):
    """Protocol for sprite history and recent files management.

    Manages sprite history tracking and recent files list.
    """

    # Signals
    history_changed: Any  # Signal() - emitted when history changes
    recent_files_changed: Any  # Signal() - emitted when recent files change

    def add_sprite_to_history(
        self,
        offset: int,
        rom_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a sprite to history."""
        ...

    def get_sprite_history(self) -> list[dict[str, Any]]:
        """Get sprite history list."""
        ...

    def clear_sprite_history(self) -> None:
        """Clear sprite history."""
        ...

    def add_recent_file(self, file_path: str) -> None:
        """Add a file to recent files list."""
        ...

    def get_recent_files(self) -> list[str]:
        """Get recent files list."""
        ...

    def clear_recent_files(self) -> None:
        """Clear recent files list."""
        ...

    @property
    def history_count(self) -> int:
        """Get number of items in sprite history."""
        ...

    @property
    def recent_files_count(self) -> int:
        """Get number of recent files."""
        ...

    def cleanup(self) -> None:
        """Clean up resources."""
        ...
