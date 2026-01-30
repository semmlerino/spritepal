"""
Consolidated Application State Manager for SpritePal.

This manager combines session, settings, state, and workflow management
into a single cohesive unit while maintaining backward compatibility.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar, cast, override

from PySide6.QtCore import QObject, Signal, SignalInstance
from PySide6.QtGui import QImage

from core.exceptions import SessionError, ValidationError
from utils.constants import (
    CACHE_EXPIRATION_MAX_DAYS,
    CACHE_EXPIRATION_MIN_DAYS,
    CACHE_SIZE_MAX_MB,
    CACHE_SIZE_MIN_MB,
)

if TYPE_CHECKING:
    from core.configuration_service import ConfigurationService
from utils.file_validator import atomic_write

from .base_manager import BaseManager

T = TypeVar("T")


# ========== Workflow State Machine ==========
from core.managers.workflow_state_manager import ExtractionState, WorkflowStateManager

# Re-export at module level for backward compatibility
__all__ = ["ApplicationStateManager", "ExtractionState", "WorkflowStateManager"]


class ApplicationStateManager(BaseManager):
    """
    Consolidated manager for all application state:
    - Session management (persistent settings)
    - Settings management (configuration)
    - Workflow management (delegated to WorkflowStateManager)

    This manager provides a unified interface for all state-related operations
    while maintaining backward compatibility through delegation.
    """

    # ========== Signal Architecture ==========
    #
    # CANONICAL SIGNALS (use in new code):
    #   state_changed - Unified state change with category and data
    #   workflow_state_changed - From WorkflowStateManager (delegated)
    #
    # DOMAIN-SPECIFIC SIGNALS (simplified for specific use cases):
    #   session_changed, settings_saved - Persistence events
    #   preview_ready - UI updates
    # =========================================

    # Unified signals (canonical) - use object to avoid PySide6 copy warning
    state_changed = Signal(str, object)  # category, data
    # Note: workflow_state_changed is delegated from WorkflowStateManager

    # Session signals (persistence) - use object to avoid PySide6 copy warning
    session_changed = Signal()  # session data modified
    files_updated = Signal(object)  # file paths changed (emitted by update_session_data)
    settings_saved = Signal()  # settings persisted to disk
    session_restored = Signal(object)  # session loaded from disk

    # UI coordination signals
    preview_ready = Signal(int, QImage)  # offset, preview_image

    def __init__(
        self,
        app_name: str = "SpritePal",
        settings_path: Path | None = None,
        parent: QObject | None = None,
        configuration_service: ConfigurationService | None = None,
    ) -> None:
        """
        Initialize application state manager.

        Args:
            app_name: Application name for settings file
            settings_path: Optional custom path for settings file
            parent: Qt parent object
            configuration_service: Optional ConfigurationService (uses DI if not provided)
        """
        # Initialize state components
        self._app_name = app_name
        if settings_path:
            self._settings_file = settings_path
        else:
            # Use ConfigurationService for consistent path resolution
            # This ensures settings file location is relative to app root, not CWD
            config = configuration_service
            if config is None:
                # Create ConfigurationService if not provided
                # (AppContext normally provides this, but fallback is safe since it's stateless)
                from core.configuration_service import ConfigurationService

                config = ConfigurationService()
            self._settings_file = config.settings_file

        # Persistent settings (saved to disk) - JSON-serializable values
        self._settings: dict[str, dict[str, object]] = {}
        self._session_dirty = False

        # Workflow state manager (composition - owns its own state and lock)
        self._workflow_manager = WorkflowStateManager(parent=None)

        # Note: Thread safety uses self._lock from BaseManager
        # Workflow locking is handled by WorkflowStateManager internally

        super().__init__("ApplicationStateManager", parent)

        # Forward workflow state changes to unified state_changed signal
        self._workflow_manager.workflow_state_changed.connect(self._on_workflow_state_changed)

    def _on_workflow_state_changed(self, old_state: ExtractionState, new_state: ExtractionState) -> None:
        """Forward workflow state changes to unified state_changed signal."""
        self.state_changed.emit("workflow", {"old": old_state.name, "new": new_state.name})

    @override
    def _initialize(self) -> None:
        """Initialize application state management."""
        try:
            # Load persistent settings
            self._settings = self._load_settings()

            # Ensure default settings exist (migrated from SettingsManager)
            self._ensure_default_settings()

            self._is_initialized = True
            self._logger.info("ApplicationStateManager initialized successfully")

        except Exception as e:
            self._handle_error(e, "initialization")
            raise

    @override
    def cleanup(self) -> None:
        """Save state and cleanup resources."""
        # Save any pending changes
        if self._session_dirty:
            self.save_settings()

        self._logger.info("ApplicationStateManager cleaned up")

    def reset_state(self, full_reset: bool = False) -> None:
        """Reset internal state for test isolation.

        This method resets mutable state without fully re-initializing the manager.
        Use this for test isolation when you need to clear workflow state but don't
        want the overhead of full manager re-initialization.

        Args:
            full_reset: If True, also reset settings to defaults and clear the
                       session dirty flag. Does NOT reset initialization state
                       since this manager requires settings to function.
        """
        with self._lock:
            self._session_dirty = False

            if full_reset:
                # Reset settings to defaults
                self._settings = self._get_default_settings()

        # Reset workflow state (delegated to WorkflowStateManager)
        self._workflow_manager.reset_state()

        self._logger.debug("ApplicationStateManager state reset (full_reset=%s)", full_reset)

    # ========== Settings Management (Persistent) ==========

    def save_settings(self) -> bool:
        """
        Save settings to disk.

        Returns:
            True if saved successfully
        """
        try:
            with self._lock:
                # Create backup of existing file
                if self._settings_file.exists():
                    backup_file = self._settings_file.with_suffix(".json.bak")
                    backup_file.write_text(self._settings_file.read_text())

                # Save settings
                with self._settings_file.open("w") as f:
                    json.dump(self._settings, f, indent=2)

                self._session_dirty = False
                self.settings_saved.emit()
                self._logger.info("Settings saved successfully")
                return True

        except Exception as e:
            self._handle_error(e, "save_settings")
            return False

    def _load_settings(self) -> dict[str, dict[str, object]]:
        """Load settings from file."""
        if self._settings_file.exists():
            try:
                with self._settings_file.open() as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._logger.info("Settings loaded successfully")
                        # Cast to expected structure after validation
                        return self._merge_with_defaults(cast(dict[str, dict[str, object]], data))
            except (OSError, json.JSONDecodeError) as e:
                self._logger.warning(f"Could not load settings: {e}")

        return self._get_default_settings()

    def _get_default_settings(self) -> dict[str, dict[str, object]]:
        """Get default settings structure."""
        return {
            "session": {
                "vram_path": "",
                "cgram_path": "",
                "oam_path": "",
                "output_name": "",
                "create_grayscale": True,
                "create_metadata": True,
                "last_rom_path": "",
                "last_vram_path": "",
                "last_output_dir": "",
            },
            "rom_injection": {
                "last_input_rom": "",
                "last_output_rom": "",
                "last_sprite_location": "",
                "last_custom_offset": "",
                "fast_compression": False,
            },
            "ui": {
                "window_width": 900,
                "window_height": 600,
                "window_x": -1,
                "window_y": -1,
                "restore_position": True,
                "theme": "default",
                "debug_logging": False,
            },
            "cache": {
                "enabled": True,
                "max_size_mb": 500,
                "expiration_days": 30,
                "auto_cleanup": True,
                "show_indicators": True,
            },
            "paths": {
                "default_dumps_dir": str(Path.home() / "Documents" / "Mesen2" / "Debugger"),
                "mesen_output_dir": "",  # Mesen2 exchange dir (empty = use project default)
                "last_used_dir": "",
                "last_palette_path": "",
                "last_export_dir": "",
                "last_import_dir": "",
            },
            "recent_files": {
                "vram": [],
                "cgram": [],
                "oam": [],
                "rom": [],
                "max_recent": 10,
            },
            "tile_grid": {
                "cols": 50,
                "rows": 50,
                "last_page": 0,
            },
            "logging": {
                "disabled_categories": [
                    "core.rom_extractor",
                    "core.tile_renderer",
                    "ui.workers.batch_thumbnail_worker",
                    "core.mesen_integration.tile_hash_database",
                    "core.mesen_integration.rom_tile_matcher",
                    "core.hal_compression",
                    "core.rom_injector",
                    "ui.workers",
                ],
            },
        }

    def _merge_with_defaults(self, data: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
        """Merge loaded settings with defaults."""
        defaults = self._get_default_settings()

        for category, values in defaults.items():
            if category not in data:
                data[category] = values
            else:
                # Merge category values with defaults
                for key, default_value in values.items():
                    if key not in data[category]:
                        data[category][key] = default_value

        return data

    # ========== SessionManagerProtocol Methods ==========

    def get(self, category: str, key: str, default: object = None) -> object:
        """
        Get a persistent setting value.

        Args:
            category: Setting category (e.g., "ui", "cache", "paths")
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value or default
        """
        with self._lock:
            if category in self._settings and key in self._settings[category]:
                return self._settings[category][key]
            return default

    def set(self, category: str, key: str, value: object) -> None:
        """
        Set a persistent setting value.

        Args:
            category: Setting category
            key: Setting key
            value: Setting value
        """
        with self._lock:
            if category not in self._settings:
                self._settings[category] = {}

            self._settings[category][key] = value
            self._session_dirty = True

            # Emit signals
            self.session_changed.emit()
            self.state_changed.emit("settings", {category: {key: value}})

            self._logger.debug(f"Setting updated: {category}.{key} = {value}")

        # Emit specific signals for file updates
        if category == "session" and key in ["vram_path", "cgram_path", "oam_path"]:
            self.files_updated.emit({key: value})

    def save_session(self) -> bool:
        """
        Save current session to file (alias for save_settings).

        Returns:
            True if saved successfully
        """
        operation = "save_session"
        if not self._start_operation(operation):
            return False

        try:
            # Use atomic write to prevent corruption on crash/power loss
            with self._lock:
                data = json.dumps(self._settings, indent=2).encode("utf-8")
                atomic_write(self._settings_file, data)
                self._session_dirty = False

            self.settings_saved.emit()
            self._logger.info("Session saved successfully")
            return True

        except OSError as e:
            error = SessionError(f"Could not save settings: {e}")
            self._handle_error(error, operation)
            return False
        finally:
            self._finish_operation(operation)

    def load_session(self, path: str | None = None) -> bool:
        """
        Load session from file.

        Args:
            path: Optional custom path to load from (defaults to settings file)

        Returns:
            True if loaded successfully
        """
        load_path = Path(path) if path else self._settings_file

        if not load_path.exists():
            return False

        try:
            with load_path.open() as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._settings = self._merge_with_defaults(data)
                    self._session_dirty = False
                    self.session_changed.emit()
                    self._logger.info(f"Session loaded from {load_path}")
                    return True
            return False
        except (OSError, json.JSONDecodeError) as e:
            self._logger.warning(f"Could not load session: {e}")
            return False

    def restore_session(self) -> dict[str, object]:
        """
        Restore session from file.

        Returns:
            Session data dictionary
        """
        operation = "restore_session"

        if not self._start_operation(operation):
            return {}

        try:
            # Reload settings from file
            self._settings = self._load_settings()
            session_data = self.get_session_data()

            self.session_restored.emit(session_data)
            self._logger.info("Session restored successfully")
            return session_data

        except Exception as e:
            error = SessionError(f"Could not restore session: {e}")
            self._handle_error(error, operation)
            return {}
        finally:
            self._finish_operation(operation)

    def get_session_data(self) -> dict[str, object]:
        """Get all session data."""
        with self._lock:
            session = self._settings.get("session", {})
            return session

    def update_session_data(self, data: Mapping[str, object]) -> None:
        """
        Update multiple session values at once.

        Args:
            data: Dictionary of session data to update
        """
        with self._lock:
            if "session" not in self._settings:
                self._settings["session"] = {}

            changed = False
            for key, value in data.items():
                if self._settings["session"].get(key) != value:
                    self._settings["session"][key] = value
                    changed = True

            if changed:
                self._session_dirty = True
                self.session_changed.emit()

                # Check for file updates
                file_keys = {"vram_path", "cgram_path", "oam_path"}
                file_updates = {k: v for k, v in data.items() if k in file_keys}
                if file_updates:
                    self.files_updated.emit(file_updates)

    def update_window_state(self, geometry: dict[str, int | float | list[int]]) -> None:
        """
        Update window geometry in settings.

        Args:
            geometry: Dictionary with width, height, x, y, and optionally splitter_sizes
        """
        with self._lock:
            if "ui" not in self._settings:
                self._settings["ui"] = {}

            changed = False
            for key in ["width", "height", "x", "y"]:
                if key in geometry:
                    setting_key = f"window_{key}"
                    if self._settings["ui"].get(setting_key) != geometry[key]:
                        self._settings["ui"][setting_key] = geometry[key]
                        changed = True

            # Handle splitter sizes separately (list type)
            if "splitter_sizes" in geometry:
                sizes = geometry["splitter_sizes"]
                if isinstance(sizes, list) and self._settings["ui"].get("splitter_sizes") != sizes:
                    self._settings["ui"]["splitter_sizes"] = sizes
                    changed = True

            if changed:
                self._session_dirty = True

    def get_window_geometry(self) -> dict[str, int | list[int]]:
        """Get saved window geometry including splitter sizes."""
        with self._lock:
            ui_settings = self._settings.get("ui", {})
            width = ui_settings.get("window_width")
            height = ui_settings.get("window_height")
            x = ui_settings.get("window_x")
            y = ui_settings.get("window_y")
            splitter_sizes = ui_settings.get("splitter_sizes", [])

            return {
                "width": width if isinstance(width, int) else 900,
                "height": height if isinstance(height, int) else 600,
                "x": x if isinstance(x, int) else -1,
                "y": y if isinstance(y, int) else -1,
                "splitter_sizes": splitter_sizes if isinstance(splitter_sizes, list) else [],
            }

    def clear_session(self) -> None:
        """Clear current session data."""
        with self._lock:
            if "session" in self._settings:
                self._settings["session"] = self._get_default_settings()["session"]
                self._session_dirty = True
                self.session_changed.emit()
                self._logger.info("Session cleared")

    def clear_recent_files(self, file_type: str | None = None) -> None:
        """
        Clear recent files.

        Args:
            file_type: Specific type to clear, or None for all
        """
        with self._lock:
            if "recent_files" not in self._settings:
                return

            if file_type:
                if file_type in self._settings["recent_files"]:
                    self._settings["recent_files"][file_type] = []
                    self._session_dirty = True
            else:
                # Clear all except max_recent setting
                max_recent = self._settings["recent_files"].get("max_recent", 10)
                self._settings["recent_files"] = {"max_recent": max_recent}
                self._session_dirty = True

    def export_settings(self, file_path: str) -> None:
        """
        Export settings to a file.

        Args:
            file_path: Path to export to

        Raises:
            SessionError: If export fails
        """
        try:
            with Path(file_path).open("w") as f:
                json.dump(self._settings, f, indent=2)
            self._logger.info(f"Settings exported to {file_path}")
        except OSError as e:
            raise SessionError(f"Could not export settings: {e}") from e

    def import_settings(self, file_path: str) -> None:
        """
        Import settings from a file.

        Args:
            file_path: Path to import from

        Raises:
            SessionError: If import fails
            ValidationError: If settings are invalid
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise ValidationError(f"Settings file not found: {file_path}")

            with path.open() as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValidationError("Invalid settings file format")

            # Validate basic structure
            if "session" not in data and "ui" not in data and "paths" not in data:
                raise ValidationError("Settings file missing required sections")

            # Merge with defaults to ensure all keys exist
            self._settings = self._merge_with_defaults(data)
            self._session_dirty = True
            self.session_changed.emit()
            self._logger.info(f"Settings imported from {file_path}")

        except (OSError, json.JSONDecodeError) as e:
            raise SessionError(f"Could not import settings: {e}") from e

    # ========== Recent Files ==========

    def get_recent_files(self, max_files: int = 10) -> list[str]:
        """Get list of recent files."""
        recent = self.get("session", "recent_files", [])
        if isinstance(recent, list):
            return recent[:max_files]
        return []

    def add_recent_file(self, file_path: str) -> None:
        """Add file to recent files list."""
        recent_obj = self.get("session", "recent_files", [])

        # Ensure we have a list to work with
        if not isinstance(recent_obj, list):
            recent: list[str] = []
        else:
            recent = list(recent_obj)

        # Remove if already in list
        if file_path in recent:
            recent.remove(file_path)

        # Add to beginning
        recent.insert(0, file_path)

        # Limit size
        recent = recent[:20]

        self.set("session", "recent_files", recent)

    # ========== Workflow State Machine (Delegated to WorkflowStateManager) ==========
    # Only scanning operations and signal passthrough are used in production.
    # Direct workflow state queries use WorkflowStateManager directly.

    @property
    def can_scan(self) -> bool:
        """Check if sprite scanning can be started."""
        return self._workflow_manager.can_scan

    @property
    def workflow_state_changed(self) -> SignalInstance:
        """Get workflow state changed signal from WorkflowStateManager."""
        return self._workflow_manager.workflow_state_changed

    def start_scanning(self) -> bool:
        """Start sprite scanning operation."""
        return self._workflow_manager.start_scanning()

    def finish_scanning(self, success: bool = True, error: str | None = None) -> bool:
        """Finish sprite scanning operation."""
        return self._workflow_manager.finish_scanning(success, error)

    # ========== UI Coordination ==========

    def emit_preview_ready(self, offset: int, image: QImage) -> None:
        """Emit signal that a preview is ready for display.

        Args:
            offset: The ROM offset for this preview
            image: The QImage preview to display
        """
        self.preview_ready.emit(offset, image)

    # ========== SettingsManager Convenience Methods ==========
    # These methods consolidate settings/cache functionality from SettingsManager

    @property
    def app_name(self) -> str:
        """Get the application name."""
        return self._app_name

    def get_default_directory(self) -> str:
        """Get the default directory for file operations."""
        # Try last used directory first
        last_used = str(self.get("paths", "last_used_dir", ""))
        if last_used and Path(last_used).exists():
            return last_used

        # Fall back to default dumps directory (platform-appropriate)
        default_dir = str(
            self.get("paths", "default_dumps_dir", str(Path.home() / "Documents" / "Mesen2" / "Debugger"))
        )
        if default_dir and Path(default_dir).exists():
            return default_dir

        # Final fallback to home directory (not CWD for better portability)
        return str(Path.home())

    def set_last_used_directory(self, directory: str) -> None:
        """Set the last used directory."""
        if directory and Path(directory).exists():
            self.set("paths", "last_used_dir", directory)
            self.save_session()

    def get_mesen_output_dir(self) -> str:
        """Get the Mesen2 output directory.

        Returns:
            Configured Mesen2 output directory, or empty string if using default.
            Empty string means LogWatcher should use the project's mesen2_exchange/ directory.
        """
        return str(self.get("paths", "mesen_output_dir", ""))

    def set_mesen_output_dir(self, directory: str) -> None:
        """Set the Mesen2 output directory.

        Args:
            directory: Path to the Mesen2 exchange directory.
                      Empty string means use the project default (mesen2_exchange/).
        """
        self.set("paths", "mesen_output_dir", directory)
        self.save_session()

    def get_cache_settings(self) -> dict[str, object]:
        """Get all cache settings."""
        return {
            "enabled": self.get("cache", "enabled", True),
            "location": self.get("cache", "location", ""),
            "max_size_mb": self.get("cache", "max_size_mb", 500),
            "expiration_days": self.get("cache", "expiration_days", 30),
            "auto_cleanup": self.get("cache", "auto_cleanup", True),
            "show_indicators": self.get("cache", "show_indicators", True),
        }

    def set_cache_enabled(self, enabled: bool) -> None:
        """Enable or disable caching."""
        self.set("cache", "enabled", enabled)
        self.save_session()

    def get_cache_enabled(self) -> bool:
        """Check if caching is enabled."""
        return bool(self.get("cache", "enabled", True))

    def set_cache_location(self, location: str) -> None:
        """Set custom cache location."""
        self.set("cache", "location", location)
        self.save_session()

    def get_cache_location(self) -> str:
        """Get custom cache location (empty string means default)."""
        return str(self.get("cache", "location", ""))

    def get_cache_max_size_mb(self) -> int:
        """Get maximum cache size in MB."""
        value = self.get("cache", "max_size_mb", 500)
        if isinstance(value, (int, str)):
            return int(value)
        return 500

    def set_cache_max_size_mb(self, size_mb: int) -> None:
        """Set maximum cache size in MB."""
        self.set("cache", "max_size_mb", max(CACHE_SIZE_MIN_MB, min(CACHE_SIZE_MAX_MB, size_mb)))
        self.save_session()

    def get_cache_expiration_days(self) -> int:
        """Get cache expiration in days."""
        value = self.get("cache", "expiration_days", 30)
        if isinstance(value, (int, str)):
            return int(value)
        return 30

    def set_cache_expiration_days(self, days: int) -> None:
        """Set cache expiration in days."""
        self.set("cache", "expiration_days", max(CACHE_EXPIRATION_MIN_DAYS, min(CACHE_EXPIRATION_MAX_DAYS, days)))
        self.save_session()

    def get_debug_logging(self) -> bool:
        """Check if debug logging is enabled."""
        return bool(self.get("ui", "debug_logging", False))

    def set_debug_logging(self, enabled: bool) -> None:
        """Enable or disable debug logging."""
        self.set("ui", "debug_logging", enabled)
        self.save_session()

    def get_disabled_log_categories(self) -> list[str]:
        """Get the list of disabled logging categories."""
        result = self.get("logging", "disabled_categories", [])
        if isinstance(result, list):
            return result
        return []

    def set_disabled_log_categories(self, categories: list[str]) -> None:
        """Set the list of disabled logging categories."""
        self.set("logging", "disabled_categories", categories)
        self.save_session()

    def _ensure_default_settings(self) -> None:
        """Ensure default settings exist in persistent storage."""
        # Check and set default cache settings if not present
        if self.get("cache", "enabled") is None:
            self.set("cache", "enabled", True)
        if self.get("cache", "max_size_mb") is None:
            self.set("cache", "max_size_mb", 500)
        if self.get("cache", "expiration_days") is None:
            self.set("cache", "expiration_days", 30)
        if self.get("cache", "auto_cleanup") is None:
            self.set("cache", "auto_cleanup", True)
        if self.get("cache", "show_indicators") is None:
            self.set("cache", "show_indicators", True)

        # Set default paths if not present
        if self.get("paths", "default_dumps_dir") is None:
            default_dir = str(Path.home() / "Documents" / "Mesen2" / "Debugger")
            self.set("paths", "default_dumps_dir", default_dir)
