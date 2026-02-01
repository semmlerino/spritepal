"""
Centralized configuration service for application path resolution.

This module provides a single source of truth for all application paths,
eliminating the scattered path resolution logic that previously caused
inconsistent behavior depending on how the application was launched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager


@dataclass(frozen=True)
class ApplicationPaths:
    """Immutable container for resolved application paths."""

    app_root: Path
    settings_file: Path
    log_directory: Path
    cache_directory: Path
    config_directory: Path
    default_dumps_directory: Path


class ConfigurationService:
    """
    Centralized service for resolving all application paths.

    This service is the SINGLE SOURCE OF TRUTH for path resolution.
    It should be initialized EARLY in application startup, before any
    other managers that depend on paths.

    Design principles:
    1. All paths computed from app_root (determined once at startup)
    2. User overrides loaded from settings AFTER settings are available
    3. Immutable base paths, mutable user preferences

    Example:
        # In launch_spritepal.py (early initialization)
        config_service = ConfigurationService()

        # Pass to app context creation
        from core.app_context import create_app_context
        ctx = create_app_context(
            "SpritePal",
            settings_path=config_service.settings_file,
            configuration_service=config_service,
        )

        # Access via app context later
        from core.app_context import get_app_context
        config = get_app_context().configuration_service
    """

    # Default subdirectory/file names
    SETTINGS_FILENAME = ".spritepal_settings.json"
    CACHE_DIR_NAME = ".spritepal_rom_cache"
    LOG_DIR_NAME = "logs"  # Now relative to app_root, not home
    CONFIG_DIR_NAME = "config"
    DEFAULT_DUMPS_SUBPATH = "Documents/Mesen2/Debugger"

    def __init__(
        self,
        app_root: Path | None = None,
        settings_manager: ApplicationStateManager | None = None,
    ) -> None:
        """
        Initialize configuration service.

        Args:
            app_root: Application root directory. If None, determined from
                     this module's location (core/configuration_service.py).
            settings_manager: Optional ApplicationStateManager for user overrides.
                             Can be set later via set_settings_manager().
        """
        # Resolve app root
        if app_root is not None:
            self._app_root = app_root.resolve()
        else:
            # Default: this file is in core/, so parent is app root (spritepal/)
            self._app_root = Path(__file__).parent.parent.resolve()

        self._settings_manager: ApplicationStateManager | None = settings_manager

        # Compute base paths (immutable)
        self._base_paths = self._compute_base_paths()

    def _compute_base_paths(self) -> ApplicationPaths:
        """Compute all base paths from app_root.

        Environment variables take precedence for test isolation (set by xdist fixtures):
        - SPRITEPAL_SETTINGS_DIR: Override for settings file directory
        - SPRITEPAL_CACHE_DIR: Override for cache directory
        - SPRITEPAL_LOG_DIR: Override for log directory
        """
        # Check for test isolation overrides
        settings_dir = os.environ.get("SPRITEPAL_SETTINGS_DIR")
        cache_dir = os.environ.get("SPRITEPAL_CACHE_DIR")
        log_dir = os.environ.get("SPRITEPAL_LOG_DIR")

        return ApplicationPaths(
            app_root=self._app_root,
            settings_file=(
                Path(settings_dir) / self.SETTINGS_FILENAME if settings_dir else self._app_root / self.SETTINGS_FILENAME
            ),
            log_directory=Path(log_dir) if log_dir else self._app_root / self.LOG_DIR_NAME,
            cache_directory=(Path(cache_dir) if cache_dir else Path.home() / self.CACHE_DIR_NAME),
            config_directory=self._app_root / self.CONFIG_DIR_NAME,
            default_dumps_directory=Path.home() / self.DEFAULT_DUMPS_SUBPATH,
        )

    def set_settings_manager(self, settings_manager: ApplicationStateManager) -> None:
        """
        Set settings manager for user override resolution.

        This allows cache directory to be overridden by user settings.

        Args:
            settings_manager: The ApplicationStateManager instance
        """
        self._settings_manager = settings_manager

    # === Core path properties ===

    @property
    def app_root(self) -> Path:
        """
        Application root directory.

        This is the directory containing launch_spritepal.py and the
        core/, ui/, utils/ subdirectories.
        """
        return self._base_paths.app_root

    @property
    def settings_file(self) -> Path:
        """
        Path to settings JSON file.

        Always relative to app_root, not CWD. This ensures consistent
        settings location regardless of how the app is launched.
        """
        return self._base_paths.settings_file

    @property
    def log_directory(self) -> Path:
        """
        Directory for log files.

        Located in user's home directory to persist across sessions.
        """
        return self._base_paths.log_directory

    @property
    def cache_directory(self) -> Path:
        """
        Directory for ROM cache.

        Returns user override if configured in settings, otherwise default.
        The default is in the user's home directory.
        """
        if self._settings_manager is not None:
            custom_location = self._settings_manager.get_cache_location()
            if custom_location:
                return Path(custom_location)
        return self._base_paths.cache_directory

    @property
    def config_directory(self) -> Path:
        """
        Directory for configuration files (sprite locations, etc.).

        Located relative to app_root.
        """
        return self._base_paths.config_directory

    @property
    def default_dumps_directory(self) -> Path:
        """
        Default directory for Mesen2 debug dumps.

        This is the typical location where Mesen2 saves its debugger output.
        """
        return self._base_paths.default_dumps_directory

    # === Specific config file paths ===

    @property
    def sprite_config_file(self) -> Path:
        """Path to sprite_locations.json configuration file."""
        return self.config_directory / "sprite_locations.json"

    # === Methods for extensibility ===

    def resolve_path(self, path_key: str) -> Path:
        """
        Resolve a path by key name.

        Useful for dynamic path lookups and extensibility.

        Args:
            path_key: One of: 'app_root', 'settings_file', 'log_directory',
                     'cache_directory', 'config_directory', 'default_dumps_directory',
                     'sprite_config_file'

        Returns:
            Resolved Path

        Raises:
            KeyError: If path_key is not recognized
        """
        path_map = {
            "app_root": self.app_root,
            "settings_file": self.settings_file,
            "log_directory": self.log_directory,
            "cache_directory": self.cache_directory,
            "config_directory": self.config_directory,
            "default_dumps_directory": self.default_dumps_directory,
            "sprite_config_file": self.sprite_config_file,
        }
        if path_key not in path_map:
            valid_keys = list(path_map.keys())
            msg = f"Unknown path key: {path_key}. Valid keys: {valid_keys}"
            raise KeyError(msg)
        return path_map[path_key]

    def ensure_directories_exist(self) -> None:
        """
        Create required directories if they don't exist.

        Creates log and cache directories. Safe to call multiple times.
        """
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self.cache_directory.mkdir(parents=True, exist_ok=True)

    @override
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"ConfigurationService(app_root={self._app_root}, settings_file={self.settings_file})"
