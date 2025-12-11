"""
Protocol definitions for managers to break circular dependencies.
These protocols define the interfaces that managers must implement.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from PIL import Image
    from PySide6.QtCore import SignalInstance
    from PySide6.QtWidgets import QStatusBar

    from core.rom_extractor import ROMExtractor


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

    def inject_to_rom(
        self,
        rom_path: Path,
        sprites: list[Any],
        offset: int | None = None
    ) -> bool:
        """
        Inject sprites into ROM.

        Args:
            rom_path: Path to ROM file
            sprites: List of sprites to inject
            offset: Optional target offset

        Returns:
            True if successful
        """
        ...

    def validate_injection(
        self,
        rom_path: Path,
        sprites: list[Any]
    ) -> bool:
        """
        Validate if injection is feasible.

        Args:
            rom_path: Path to ROM file
            sprites: Sprites to inject

        Returns:
            True if injection is valid
        """
        ...

    def get_free_space(self, rom_path: Path) -> list[tuple[int, int]]:
        """
        Find free space regions in ROM.

        Args:
            rom_path: Path to ROM file

        Returns:
            List of (offset, size) tuples for free regions
        """
        ...

    def get_smart_vram_suggestion(
        self,
        sprite_path: str,
        metadata_path: str
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

    def start_injection(self, params: dict[str, Any]) -> bool:
        """
        Start injection process with given parameters.

        Args:
            params: Dictionary of injection parameters

        Returns:
            True if injection started successfully
        """
        ...

class NavigationManagerProtocol(Protocol):
    """Protocol for navigation manager."""

    def navigate_to_offset(self, offset: int) -> None:
        """
        Navigate to specific ROM offset.

        Args:
            offset: Target offset
        """
        ...

    def get_current_offset(self) -> int:
        """
        Get current navigation offset.

        Returns:
            Current offset
        """
        ...

    def get_navigation_history(self) -> list[int]:
        """
        Get navigation history.

        Returns:
            List of previously visited offsets
        """
        ...

    def navigate_back(self) -> int | None:
        """
        Navigate to previous offset.

        Returns:
            Previous offset or None if at start
        """
        ...

    def navigate_forward(self) -> int | None:
        """
        Navigate to next offset in history.

        Returns:
            Next offset or None if at end
        """
        ...

class SessionManagerProtocol(Protocol):
    """Protocol for session manager."""

    def save_session(self, path: Path | None = None) -> bool:
        """
        Save current session state.

        Args:
            path: Optional path to save to

        Returns:
            True if successful
        """
        ...

    def load_session(self, path: Path) -> bool:
        """
        Load session state from file.

        Args:
            path: Path to session file

        Returns:
            True if successful
        """
        ...

    def get_session_data(self) -> dict[str, Any]:
        """
        Get current session data.

        Returns:
            Dictionary with session state
        """
        ...

    def clear_session(self) -> None:
        """Clear current session data."""
        ...

    def update_session_data(self, data: dict[str, Any]) -> None:
        """
        Update multiple session values at once.

        Args:
            data: Dictionary of session data to update
        """
        ...

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """
        Get a setting value.

        Args:
            category: Setting category
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value or default
        """
        ...

    def set(self, category: str, key: str, value: Any) -> None:
        """
        Set a setting value.

        Args:
            category: Setting category
            key: Setting key
            value: Value to set
        """
        ...

class ContextManagerProtocol(Protocol):
    """Protocol for context manager."""

    def get_context(self, key: str) -> Any | None:
        """
        Get context value by key.

        Args:
            key: Context key

        Returns:
            Context value or None
        """
        ...

    def set_context(self, key: str, value: Any) -> None:
        """
        Set context value.

        Args:
            key: Context key
            value: Context value
        """
        ...

    def clear_context(self) -> None:
        """Clear all context data."""
        ...

    def get_all_context(self) -> dict[str, Any]:
        """
        Get all context data.

        Returns:
            Dictionary with all context
        """
        ...

class RegistryManagerProtocol(Protocol):
    """Protocol for registry manager."""

    def register(self, key: str, value: Any) -> None:
        """
        Register a value.

        Args:
            key: Registry key
            value: Value to register
        """
        ...

    def unregister(self, key: str) -> None:
        """
        Unregister a value.

        Args:
            key: Registry key
        """
        ...

    def get(self, key: str) -> Any | None:
        """
        Get registered value.

        Args:
            key: Registry key

        Returns:
            Registered value or None
        """
        ...

    def get_all(self) -> dict[str, Any]:
        """
        Get all registered values.

        Returns:
            Dictionary with all registrations
        """
        ...

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


class MainWindowProtocol(Protocol):
    """Protocol for main window interface required by controllers."""

    # Signals
    extract_requested: SignalInstance
    open_in_editor_requested: SignalInstance
    arrange_rows_requested: SignalInstance
    arrange_grid_requested: SignalInstance
    inject_requested: SignalInstance

    # UI Components
    extraction_panel: Any
    sprite_preview: Any
    palette_preview: Any
    preview_coordinator: Any
    status_bar: QStatusBar
    status_bar_manager: Any
    rom_extraction_panel: Any

    def get_extraction_params(self) -> dict[str, Any]:
        """
        Get extraction parameters from UI.

        Returns:
            Dictionary with extraction parameters
        """
        ...

    def get_output_path(self) -> str:
        """
        Get output path for extraction.

        Returns:
            Output path string
        """
        ...

    def extraction_complete(self, extracted_files: list[str]) -> None:
        """
        Handle extraction completion.

        Args:
            extracted_files: List of extracted file paths
        """
        ...

    def extraction_failed(self, error_message: str) -> None:
        """
        Handle extraction failure.

        Args:
            error_message: Error message to display
        """
        ...

    def show_cache_operation_badge(self, badge_text: str) -> None:
        """
        Show cache operation badge.

        Args:
            badge_text: Text to display in badge
        """
        ...

    def hide_cache_operation_badge(self) -> None:
        """Hide cache operation badge."""
        ...


class ROMServiceProtocol(Protocol):
    """
    Protocol for ROM extraction service.

    Provides methods for extracting sprites from ROM files,
    generating previews, and reading ROM metadata.
    """

    # Signals
    extraction_progress: SignalInstance
    extraction_warning: SignalInstance
    preview_generated: SignalInstance
    files_created: SignalInstance
    cache_operation_started: SignalInstance
    cache_hit: SignalInstance
    cache_miss: SignalInstance
    cache_saved: SignalInstance
    error_occurred: SignalInstance

    def extract_from_rom(
        self,
        rom_path: str,
        offset: int,
        output_base: str,
        sprite_name: str,
        cgram_path: str | None = None,
    ) -> list[str]:
        """
        Extract sprites from ROM at specific offset.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM to extract from
            output_base: Base name for output files
            sprite_name: Name of the sprite being extracted
            cgram_path: CGRAM dump for palette extraction

        Returns:
            List of created file paths

        Raises:
            ExtractionError: If extraction fails
            ValidationError: If parameters are invalid
        """
        ...

    def get_sprite_preview(
        self, rom_path: str, offset: int, sprite_name: str | None = None
    ) -> tuple[bytes, int, int]:
        """
        Get a preview of sprite data from ROM without saving files.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM
            sprite_name: Sprite name for logging

        Returns:
            Tuple of (tile_data, width, height)

        Raises:
            ExtractionError: If preview generation fails
        """
        ...

    def extract_sprite_to_png(
        self,
        rom_path: str,
        sprite_offset: int,
        output_path: str,
        cgram_path: str | None = None,
    ) -> bool:
        """
        Extract a single sprite to PNG file.

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
        """
        Get known sprite locations for a ROM with caching.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of known sprite locations

        Raises:
            ExtractionError: If operation fails
        """
        ...

    def read_rom_header(self, rom_path: str) -> dict[str, Any]:
        """
        Read ROM header information.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary containing ROM header information

        Raises:
            ExtractionError: If operation fails
        """
        ...

    def get_rom_extractor(self) -> ROMExtractor:
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


class VRAMServiceProtocol(Protocol):
    """
    Protocol for VRAM extraction service.

    Provides methods for extracting sprites from VRAM dumps
    and generating previews.
    """

    # Signals
    extraction_progress: SignalInstance
    extraction_warning: SignalInstance
    preview_generated: SignalInstance
    palettes_extracted: SignalInstance
    active_palettes_found: SignalInstance
    files_created: SignalInstance
    error_occurred: SignalInstance

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
        """
        Extract sprites from VRAM dump.

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

        Raises:
            ExtractionError: If extraction fails
            ValidationError: If parameters are invalid
        """
        ...

    def generate_preview(self, vram_path: str, offset: int) -> tuple[Image.Image, int]:
        """
        Generate a preview image from VRAM at the specified offset.

        Args:
            vram_path: Path to VRAM dump file
            offset: Offset in VRAM to start extracting from

        Returns:
            Tuple of (PIL image, tile count)

        Raises:
            ExtractionError: If preview generation fails
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


class ControllerUIBridgeProtocol(Protocol):
    """
    Minimal read-only protocol for controller access to UI state.

    This protocol provides the minimum interface needed by ExtractionController
    to read UI state without coupling to the full MainWindow interface.
    Controllers should emit signals for UI updates rather than calling
    UI methods directly.

    This decouples the controller from the UI layer while still allowing
    necessary read operations like getting extraction parameters.
    """

    def get_extraction_params(self) -> dict[str, Any]:
        """
        Get extraction parameters from the UI.

        Returns:
            Dictionary containing extraction parameters:
            - vram_path: str
            - cgram_path: str | None
            - oam_path: str | None
            - vram_offset: int
            - output_base: str
            - create_grayscale: bool
            - create_metadata: bool
            - grayscale_mode: bool
        """
        ...

    def get_output_path(self) -> str:
        """
        Get the current output path for extracted files.

        Returns:
            Output path string (without extension)
        """
        ...

    def get_vram_path(self) -> str | None:
        """
        Get the currently loaded VRAM file path.

        Returns:
            VRAM file path or None if not loaded
        """
        ...

    def has_vram_loaded(self) -> bool:
        """
        Check if a VRAM file is currently loaded.

        Returns:
            True if VRAM is loaded, False otherwise
        """
        ...

    def get_preview_size(self) -> tuple[int, int]:
        """
        Get the size of the preview widget for preview generation.

        Returns:
            Tuple of (width, height)
        """
        ...

    def get_tile_info(self) -> tuple[int, int]:
        """
        Get tile information from the current preview.

        Returns:
            Tuple of (tile_count, tiles_per_row)
        """
        ...

    def get_palettes(self) -> dict[str, list[tuple[int, int, int]]] | None:
        """
        Get palette data from the current session.

        Returns:
            Dictionary mapping palette names to RGB color lists,
            or None if no palettes are available
        """
        ...
