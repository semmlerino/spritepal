"""
Consolidated Application State Manager for SpritePal.

This manager combines session, settings, state, history, and workflow management
into a single cohesive unit while maintaining backward compatibility.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

# Enum import no longer needed - ExtractionState imported from workflow_manager
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, TypedDict, TypeVar, cast, override

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from core.exceptions import SessionError, ValidationError

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ConfigurationServiceProtocol
from utils.file_validator import atomic_write
from utils.state_manager import StateEntry, StateSnapshot

from .base_manager import BaseManager

T = TypeVar("T")


# ========== Type Definitions ==========


class SpriteInfoDict(TypedDict):
    """Type definition for sprite history entries."""

    offset: int
    quality: float
    timestamp: str
    metadata: dict[str, object]


# ========== Workflow State Machine ==========
# ExtractionState is now defined in workflow_manager.py
# Re-exported here for backward compatibility
from core.managers.workflow_manager import ExtractionState

# Re-export at module level for backward compatibility
__all__ = ["ApplicationStateManager", "ExtractionState"]


class ApplicationStateManager(BaseManager):
    """
    Consolidated manager for all application state:
    - Session management (persistent settings)
    - Settings management (configuration)
    - State management (temporary runtime state)
    - History management (sprite history tracking)
    - Workflow management (extraction state machine)

    This manager provides a unified interface for all state-related operations
    while maintaining backward compatibility through embedded adapters.
    """

    # ========== Workflow State Machine Configuration ==========

    # Valid state transitions for the workflow state machine
    VALID_TRANSITIONS: ClassVar[dict[ExtractionState, set[ExtractionState]]] = {
        ExtractionState.IDLE: {
            ExtractionState.LOADING_ROM,
            ExtractionState.SCANNING_SPRITES,
            ExtractionState.PREVIEWING_SPRITE,
            ExtractionState.SEARCHING_SPRITE,
            ExtractionState.EXTRACTING,
        },
        ExtractionState.LOADING_ROM: {
            ExtractionState.IDLE,
            ExtractionState.ERROR,
        },
        ExtractionState.SCANNING_SPRITES: {
            ExtractionState.IDLE,
            ExtractionState.ERROR,
        },
        ExtractionState.PREVIEWING_SPRITE: {
            ExtractionState.IDLE,
            ExtractionState.ERROR,
            ExtractionState.SEARCHING_SPRITE,  # Can search while preview loads
        },
        ExtractionState.SEARCHING_SPRITE: {
            ExtractionState.IDLE,
            ExtractionState.ERROR,
            ExtractionState.PREVIEWING_SPRITE,  # Preview after finding
        },
        ExtractionState.EXTRACTING: {
            ExtractionState.IDLE,
            ExtractionState.ERROR,
        },
        ExtractionState.ERROR: {
            ExtractionState.IDLE,  # Reset to idle from error
        },
    }

    # States that block new operations
    BLOCKING_STATES: ClassVar[set[ExtractionState]] = {
        ExtractionState.LOADING_ROM,
        ExtractionState.SCANNING_SPRITES,
        ExtractionState.EXTRACTING,
    }

    # ========== Signal Architecture ==========
    #
    # CANONICAL SIGNALS (use in new code):
    #   state_changed - Unified state change with category and data
    #   workflow_state_changed - Workflow state machine transitions
    #   application_state_snapshot - Full state snapshot for debugging
    #
    # DOMAIN-SPECIFIC SIGNALS (simplified for specific use cases):
    #   session_changed, settings_saved - Persistence events
    #   history_updated, sprite_added - History tracking
    #   preview_ready, current_offset_changed - UI updates
    #
    # Signal Registry: Use utils.signal_registry.SignalRegistry for debugging
    # =========================================

    # Unified signals (canonical)
    state_changed = Signal(str, dict)  # category, data
    workflow_state_changed = Signal(object, object)  # old_state, new_state
    application_state_snapshot = Signal(dict)  # full state for debugging

    # Session signals (persistence)
    session_changed = Signal()  # session data modified
    files_updated = Signal(dict)  # file paths changed
    settings_saved = Signal()  # settings persisted to disk
    session_restored = Signal(dict)  # session loaded from disk

    # History signals (sprite tracking)
    history_updated = Signal(list)  # list of sprite offsets
    sprite_added = Signal(int, float)  # offset, quality_score

    # Cache signals (monitoring)
    cache_stats_updated = Signal(dict)  # updated cache metrics

    # UI coordination signals
    current_offset_changed = Signal(int)  # ROM offset changed
    preview_ready = Signal(int, QImage)  # offset, preview_image

    def __init__(self, app_name: str = "SpritePal", settings_path: Path | None = None,
                 parent: QObject | None = None,
                 configuration_service: ConfigurationServiceProtocol | None = None) -> None:
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
                # Try DI injection first (preferred method)
                try:
                    from core.di_container import get_container
                    from core.protocols.manager_protocols import ConfigurationServiceProtocol
                    config = get_container().get_optional(ConfigurationServiceProtocol)
                except (ImportError, ValueError):
                    config = None

                # Fall back to singleton only if DI not available
                if config is None:
                    from core.configuration_service import get_configuration_service
                    config = get_configuration_service()

            # At this point config is guaranteed to be set (fallback always provides one)
            assert config is not None, "ConfigurationService should always be available"
            self._settings_file = config.settings_file

        # Persistent settings (saved to disk) - JSON-serializable values
        self._settings: dict[str, dict[str, object]] = {}
        self._session_dirty = False

        # Runtime state (temporary, not saved) - dynamic namespaces with varied shapes
        self._runtime_state: dict[str, dict[str, object]] = {}
        self._state_snapshots: dict[str, StateSnapshot] = OrderedDict()
        self._max_snapshots = 10

        # Sprite history - structured entries with known fields
        self._sprite_history: list[SpriteInfoDict] = []
        self._max_history = 50

        # Workflow state machine
        self._workflow_state = ExtractionState.IDLE
        self._workflow_error: str | None = None

        # Cache session statistics (per-session tracking, not persisted)
        self._cache_session_stats: dict[str, int] = {"hits": 0, "misses": 0, "total_requests": 0}
        self._preloaded_offsets: set[int] = set()  # Track preloaded offsets

        # Thread safety - Lock hierarchy documentation
        # LOCK ORDERING (always acquire in this order to prevent deadlock):
        #   1. _state_lock     - protects general state (_settings, _runtime_state, etc.)
        #   2. _workflow_lock  - protects workflow transitions (_workflow_state)
        #   3. _cache_stats_lock - protects cache statistics (_cache_session_stats)
        # RULE: Never acquire a lower-numbered lock while holding a higher-numbered lock.
        self._state_lock = threading.RLock()
        self._workflow_lock = threading.RLock()
        self._cache_stats_lock = threading.RLock()

        super().__init__("ApplicationStateManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize application state management."""
        try:
            # Load persistent settings
            self._settings = self._load_settings()

            # Initialize runtime state with default namespaces
            self._runtime_state = {
                "ui": {},
                "dialog": {},
                "widget": {},
                "temp": {}
            }

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

        # Clear runtime state
        with self._state_lock:
            self._runtime_state.clear()
            self._state_snapshots.clear()
            self._sprite_history.clear()

        self._logger.info("ApplicationStateManager cleaned up")

    def reset_state(self, full_reset: bool = False) -> None:
        """Reset internal state for test isolation.

        This method resets mutable state without fully re-initializing the manager.
        Use this for test isolation when you need to clear runtime state, snapshots,
        history, and workflow state but don't want the overhead of full manager
        re-initialization.

        Args:
            full_reset: If True, also reset settings to defaults and clear the
                       session dirty flag. Does NOT reset initialization state
                       since this manager requires settings to function.
        """
        with self._state_lock:
            # Clear runtime state (always reset)
            self._runtime_state.clear()
            self._state_snapshots.clear()
            self._sprite_history.clear()
            self._session_dirty = False

            if full_reset:
                # Reset settings to defaults
                self._settings = self._get_default_settings()

        # Reset workflow state (use workflow lock for consistency)
        with self._workflow_lock:
            self._workflow_state = ExtractionState.IDLE
            self._workflow_error = None

        # Reset cache session stats
        with self._cache_stats_lock:
            self._cache_session_stats = {"hits": 0, "misses": 0, "total_requests": 0}
            self._preloaded_offsets.clear()

        self._logger.debug("ApplicationStateManager state reset (full_reset=%s)", full_reset)

    # ========== Settings Management (Persistent) ==========

    def get_setting(self, category: str, key: str, default: object = None) -> object:
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

    def set_setting(self, category: str, key: str, value: object) -> None:
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
                        # Check if this is old flat format (has old keys, missing categories)
                        if self._is_old_format(data):
                            self._logger.info("Detected old settings format, migrating...")
                            return self._migrate_old_settings(data)
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
                "theme": "default"
            },
            "cache": {
                "enabled": True,
                "max_size_mb": 500,
                "expiration_days": 30,
                "auto_cleanup": True,
                "show_indicators": True
            },
            "paths": {
                "default_dumps_dir": str(Path.home() / "Documents" / "Mesen2" / "Debugger"),
                "last_used_dir": "",
                "last_export_dir": "",
                "last_import_dir": ""
            },
            "recent_files": {
                "vram": [],
                "cgram": [],
                "oam": [],
                "rom": [],
                "max_recent": 10,
            }
        }

    def _merge_with_defaults(
        self, data: dict[str, dict[str, object]]
    ) -> dict[str, dict[str, object]]:
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

    def _is_old_format(self, data: dict[str, object]) -> bool:
        """Check if settings data is in old flat format.

        Old format has flat keys like 'vram_path', 'window_width'.
        New format has categories like 'session', 'ui', 'paths'.
        """
        old_keys = {"vram_path", "cgram_path", "oam_path", "output_name",
                    "window_width", "window_height", "window_x", "window_y",
                    "theme", "last_export_dir"}

        # If any old-style flat keys exist at top level, it's old format
        if old_keys & data.keys():
            return True

        # If no categories exist, it might be old format or empty
        new_categories = {"session", "ui", "paths"}
        if not (new_categories & data.keys()):
            # Only consider it old if it has any keys at all
            return bool(data)

        return False

    def _migrate_old_settings(
        self, old_data: dict[str, object]
    ) -> dict[str, dict[str, object]]:
        """Migrate old flat settings format to new categorized format."""
        # Start with defaults
        new_settings = self._get_default_settings()

        # Map old keys to new structure
        if "vram_path" in old_data:
            new_settings["session"]["vram_path"] = old_data["vram_path"]
        if "cgram_path" in old_data:
            new_settings["session"]["cgram_path"] = old_data["cgram_path"]
        if "oam_path" in old_data:
            new_settings["session"]["oam_path"] = old_data["oam_path"]
        if "output_name" in old_data:
            new_settings["session"]["output_name"] = old_data["output_name"]

        if "window_width" in old_data:
            new_settings["ui"]["window_width"] = old_data["window_width"]
        if "window_height" in old_data:
            new_settings["ui"]["window_height"] = old_data["window_height"]
        if "window_x" in old_data:
            new_settings["ui"]["window_x"] = old_data["window_x"]
        if "window_y" in old_data:
            new_settings["ui"]["window_y"] = old_data["window_y"]
        if "theme" in old_data:
            new_settings["ui"]["theme"] = old_data["theme"]

        if "last_export_dir" in old_data:
            new_settings["paths"]["last_used_dir"] = old_data["last_export_dir"]

        self._logger.info("Settings migration completed")
        return new_settings

    # ========== SessionManagerProtocol Methods ==========

    def get(
        self, category: str, key: str, default: object = None
    ) -> object:
        """
        Get a setting value (alias for get_setting for SessionManagerProtocol).

        Args:
            category: Setting category
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value or default
        """
        return self.get_setting(category, key, default)

    def set(self, category: str, key: str, value: object) -> None:
        """
        Set a setting value (alias for set_setting for SessionManagerProtocol).

        Args:
            category: Setting category
            key: Setting key
            value: Value to set
        """
        self.set_setting(category, key, value)

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

    def update_file_paths(self, vram: str | None = None,
                         cgram: str | None = None,
                         oam: str | None = None) -> None:
        """
        Update file paths in session.

        Args:
            vram: VRAM file path
            cgram: CGRAM file path
            oam: OAM file path
        """
        updates: dict[str, str] = {}
        if vram is not None:
            updates["vram_path"] = vram
            self._add_recent_file("vram", vram)
        if cgram is not None:
            updates["cgram_path"] = cgram
            self._add_recent_file("cgram", cgram)
        if oam is not None:
            updates["oam_path"] = oam
            self._add_recent_file("oam", oam)

        if updates:
            self.update_session_data(updates)

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

    def _add_recent_file(self, file_type: str, file_path: str) -> None:
        """Add a file to recent files list."""
        if not file_path or not Path(file_path).exists():
            return

        with self._lock:
            if "recent_files" not in self._settings:
                self._settings["recent_files"] = {}

            recent = self._settings["recent_files"]
            if file_type not in recent:
                recent[file_type] = []

            # Get the list for this file type and validate it's a list
            file_list_obj = recent[file_type]
            if not isinstance(file_list_obj, list):
                file_list_obj = []
                recent[file_type] = file_list_obj

            # Remove if already in list
            if file_path in file_list_obj:
                file_list_obj.remove(file_path)

            # Add to front
            file_list_obj.insert(0, file_path)

            # Limit size
            max_recent_obj = recent.get("max_recent", 10)
            max_recent = max_recent_obj if isinstance(max_recent_obj, int) else 10
            recent[file_type] = file_list_obj[:max_recent]

            self._session_dirty = True

    # ========== State Management (Runtime/Temporary) ==========

    def get_state(self, namespace: str, key: str, default: object = None) -> object:
        """
        Get runtime state value (not persisted).

        Args:
            namespace: State namespace (e.g., "dialog", "widget")
            key: State key
            default: Default value if not found

        Returns:
            State value or default
        """
        with self._state_lock:
            if namespace in self._runtime_state and key in self._runtime_state[namespace]:
                entry = self._runtime_state[namespace][key]
                if isinstance(entry, StateEntry):
                    if not entry.is_expired():
                        entry.touch()
                        return entry.value
                    # Remove expired entry
                    del self._runtime_state[namespace][key]
                else:
                    return entry
            return default

    def set_state(self, namespace: str, key: str, value: object,
                  ttl_seconds: float | None = None) -> None:
        """
        Set runtime state value.

        Args:
            namespace: State namespace
            key: State key
            value: State value
            ttl_seconds: Optional time-to-live in seconds
        """
        with self._state_lock:
            if namespace not in self._runtime_state:
                self._runtime_state[namespace] = {}

            if ttl_seconds is not None:
                self._runtime_state[namespace][key] = StateEntry(value, ttl_seconds)
            else:
                self._runtime_state[namespace][key] = value

            self.state_changed.emit("runtime", {namespace: {key: value}})

    def clear_state(self, namespace: str | None = None) -> None:
        """
        Clear runtime state.

        Args:
            namespace: Specific namespace to clear, or None for all
        """
        with self._state_lock:
            if namespace:
                if namespace in self._runtime_state:
                    self._runtime_state[namespace].clear()
            else:
                self._runtime_state.clear()

    def create_snapshot(self, namespace: str | None = None) -> str:
        """
        Create a snapshot of current state.

        Args:
            namespace: Specific namespace to snapshot, or None for all

        Returns:
            Snapshot ID
        """
        with self._state_lock:
            if namespace:
                states = self._runtime_state.get(namespace, {}).copy()
            else:
                states = {ns: data.copy() for ns, data in self._runtime_state.items()}

            snapshot = StateSnapshot(states, namespace)

            # Limit number of snapshots
            if len(self._state_snapshots) >= self._max_snapshots:
                # Remove oldest snapshot
                self._state_snapshots.popitem(last=False)  # type: ignore[call-arg]  # Python 3.7+ dict is ordered

            self._state_snapshots[snapshot.id] = snapshot
            return snapshot.id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """
        Restore state from snapshot.

        Args:
            snapshot_id: ID of snapshot to restore

        Returns:
            True if restored successfully
        """
        with self._state_lock:
            if snapshot_id not in self._state_snapshots:
                return False

            snapshot = self._state_snapshots[snapshot_id]

            if snapshot.namespace:
                # Restore specific namespace
                self._runtime_state[snapshot.namespace] = snapshot.states.copy()
            else:
                # Restore all namespaces
                self._runtime_state = snapshot.states.copy()

            self.state_changed.emit("restored", {"snapshot_id": snapshot_id})
            return True

    # ========== History Management ==========

    def add_sprite_to_history(self, offset: int, quality: float = 1.0,
                             metadata: dict[str, object] | None = None) -> bool:
        """
        Add sprite to history.

        Args:
            offset: ROM offset of sprite
            quality: Quality score (0.0 to 1.0)
            metadata: Optional additional metadata

        Returns:
            True if added (not duplicate), False if duplicate
        """
        with self._lock:
            # Check for duplicate
            if any(s["offset"] == offset for s in self._sprite_history):
                return False

            # Create sprite info (explicit TypedDict construction)
            sprite_info: SpriteInfoDict = {
                "offset": offset,
                "quality": quality,
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "metadata": metadata or {},
            }

            # Add to history
            self._sprite_history.append(sprite_info)

            # Enforce limit
            if len(self._sprite_history) > self._max_history:
                self._sprite_history = self._sprite_history[-self._max_history:]

            # Emit signals
            self.sprite_added.emit(offset, quality)
            self.history_updated.emit([s["offset"] for s in self._sprite_history])

            return True

    def get_sprite_history(self) -> Sequence[SpriteInfoDict]:
        """Get full sprite history (read-only snapshot)."""
        with self._lock:
            return list(self._sprite_history)

    def clear_sprite_history(self) -> None:
        """Clear sprite history."""
        with self._lock:
            self._sprite_history.clear()
            self.history_updated.emit([])

    # ========== Session Management ==========

    def update_session_file(self, file_type: str, file_path: str) -> None:
        """
        Update session with file path.

        Args:
            file_type: Type of file (e.g., "rom", "vram", "output")
            file_path: File path to store
        """
        file_map = {
            "rom": ("session", "last_rom_path"),
            "vram": ("session", "last_vram_path"),
            "output": ("session", "last_output_dir")
        }

        if file_type in file_map:
            category, key = file_map[file_type]
            self.set_setting(category, key, file_path)
            self.files_updated.emit({file_type: file_path})

    def get_recent_files(self, max_files: int = 10) -> list[str]:
        """Get list of recent files."""
        recent = self.get_setting("session", "recent_files", [])
        if isinstance(recent, list):
            return recent[:max_files]
        return []

    def add_recent_file(self, file_path: str) -> None:
        """Add file to recent files list."""
        recent_obj = self.get_setting("session", "recent_files", [])

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

        self.set_setting("session", "recent_files", recent)

    # ========== Workflow State Machine ==========

    @property
    def workflow_state(self) -> ExtractionState:
        """Get current workflow state."""
        return self._workflow_state

    @property
    def is_workflow_busy(self) -> bool:
        """Check if a blocking operation is in progress."""
        return self._workflow_state in self.BLOCKING_STATES

    @property
    def can_extract(self) -> bool:
        """Check if extraction can be started."""
        return self._workflow_state == ExtractionState.IDLE

    @property
    def can_preview(self) -> bool:
        """Check if preview can be started."""
        return self._workflow_state in {ExtractionState.IDLE, ExtractionState.SEARCHING_SPRITE}

    @property
    def can_search(self) -> bool:
        """Check if search can be started."""
        return self._workflow_state in {ExtractionState.IDLE, ExtractionState.PREVIEWING_SPRITE}

    @property
    def can_scan(self) -> bool:
        """Check if sprite scanning can be started."""
        return self._workflow_state == ExtractionState.IDLE

    @property
    def workflow_error_message(self) -> str | None:
        """Get error message if in error state."""
        return self._workflow_error if self._workflow_state == ExtractionState.ERROR else None

    def transition_workflow(
        self, new_state: ExtractionState, error_message: str | None = None
    ) -> bool:
        """
        Attempt to transition to a new workflow state.

        Args:
            new_state: Target state
            error_message: Error message if transitioning to ERROR state

        Returns:
            True if transition was successful, False otherwise
        """
        with self._workflow_lock:
            # Check if transition is valid
            valid_targets = self.VALID_TRANSITIONS.get(self._workflow_state, set())
            if new_state not in valid_targets:
                self._logger.warning(
                    f"Invalid workflow transition: {self._workflow_state.name} -> {new_state.name}"
                )
                return False

            old_state = self._workflow_state
            self._workflow_state = new_state

            # Handle error state
            if new_state == ExtractionState.ERROR:
                self._workflow_error = error_message
            else:
                self._workflow_error = None

            # Emit state change signal
            self.workflow_state_changed.emit(old_state, new_state)
            self.state_changed.emit("workflow", {"old": old_state.name, "new": new_state.name})

            self._logger.debug(f"Workflow transition: {old_state.name} -> {new_state.name}")
            return True

    def reset_workflow(self) -> None:
        """Reset workflow to idle state."""
        self.transition_workflow(ExtractionState.IDLE)

    # Convenience methods for workflow transitions
    def start_loading_rom(self) -> bool:
        """Start loading ROM operation."""
        return self.transition_workflow(ExtractionState.LOADING_ROM)

    def finish_loading_rom(self, success: bool = True, error: str | None = None) -> bool:
        """Finish loading ROM operation."""
        if success:
            return self.transition_workflow(ExtractionState.IDLE)
        return self.transition_workflow(ExtractionState.ERROR, error)

    def start_scanning(self) -> bool:
        """Start sprite scanning operation."""
        return self.transition_workflow(ExtractionState.SCANNING_SPRITES)

    def finish_scanning(self, success: bool = True, error: str | None = None) -> bool:
        """Finish sprite scanning operation."""
        if success:
            return self.transition_workflow(ExtractionState.IDLE)
        return self.transition_workflow(ExtractionState.ERROR, error)

    def start_preview(self) -> bool:
        """Start sprite preview operation."""
        return self.transition_workflow(ExtractionState.PREVIEWING_SPRITE)

    def finish_preview(self, success: bool = True, error: str | None = None) -> bool:
        """Finish sprite preview operation."""
        if success:
            return self.transition_workflow(ExtractionState.IDLE)
        return self.transition_workflow(ExtractionState.ERROR, error)

    def start_search(self) -> bool:
        """Start sprite search operation."""
        return self.transition_workflow(ExtractionState.SEARCHING_SPRITE)

    def finish_search(self, success: bool = True, error: str | None = None) -> bool:
        """Finish sprite search operation."""
        if success:
            return self.transition_workflow(ExtractionState.IDLE)
        return self.transition_workflow(ExtractionState.ERROR, error)

    def start_extraction(self) -> bool:
        """Start extraction operation."""
        return self.transition_workflow(ExtractionState.EXTRACTING)

    def finish_extraction(self, success: bool = True, error: str | None = None) -> bool:
        """Finish extraction operation."""
        if success:
            return self.transition_workflow(ExtractionState.IDLE)
        return self.transition_workflow(ExtractionState.ERROR, error)

    # ========== Cache Session Statistics ==========

    def record_cache_hit(self) -> None:
        """Record a cache hit in session statistics."""
        with self._cache_stats_lock:
            self._cache_session_stats["hits"] += 1
            self._cache_session_stats["total_requests"] += 1
            stats_copy = self._cache_session_stats.copy()
        self.cache_stats_updated.emit(stats_copy)

    def record_cache_miss(self) -> None:
        """Record a cache miss in session statistics."""
        with self._cache_stats_lock:
            self._cache_session_stats["misses"] += 1
            self._cache_session_stats["total_requests"] += 1
            stats_copy = self._cache_session_stats.copy()
        self.cache_stats_updated.emit(stats_copy)

    def get_cache_session_stats(self) -> Mapping[str, int]:
        """Get current cache session statistics (read-only view).

        Returns:
            Read-only dict with 'hits', 'misses', and 'total_requests' counts
        """
        with self._cache_stats_lock:
            return MappingProxyType(self._cache_session_stats.copy())

    def reset_cache_session_stats(self) -> None:
        """Reset cache session statistics to zero."""
        with self._cache_stats_lock:
            self._cache_session_stats = {"hits": 0, "misses": 0, "total_requests": 0}
            stats_copy = self._cache_session_stats.copy()
        self.cache_stats_updated.emit(stats_copy)

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate as a percentage.

        Returns:
            Hit rate as percentage (0.0 to 100.0), or 0.0 if no requests
        """
        with self._cache_stats_lock:
            total = self._cache_session_stats["total_requests"]
            if total == 0:
                return 0.0
            return (self._cache_session_stats["hits"] / total) * 100.0

    # ========== Preloaded Offsets Tracking ==========

    def add_preloaded_offset(self, offset: int) -> None:
        """Track an offset that has been preloaded.

        Args:
            offset: ROM offset that was preloaded into cache
        """
        with self._cache_stats_lock:
            self._preloaded_offsets.add(offset)

    def is_offset_preloaded(self, offset: int) -> bool:
        """Check if an offset has been preloaded.

        Args:
            offset: ROM offset to check

        Returns:
            True if offset was preloaded
        """
        with self._cache_stats_lock:
            return offset in self._preloaded_offsets

    def get_preloaded_offsets(self) -> frozenset[int]:
        """Get set of all preloaded offsets (immutable snapshot).

        Returns:
            Immutable frozenset of preloaded offsets
        """
        with self._cache_stats_lock:
            return frozenset(self._preloaded_offsets)

    def clear_preloaded_offsets(self) -> None:
        """Clear the preloaded offsets tracking."""
        with self._cache_stats_lock:
            self._preloaded_offsets.clear()

    # ========== Unified State Snapshot ==========

    def get_full_state_snapshot(self) -> dict[str, object]:
        """Get a complete snapshot of all application state.

        This provides a unified view of the application state for debugging,
        logging, or state synchronization purposes.

        Returns:
            Dictionary containing:
            - workflow: Current workflow state and error
            - settings: All persistent settings
            - runtime: All runtime state by namespace
            - history: Sprite history summary
            - cache_stats: Cache session statistics
        """
        with self._state_lock:
            with self._workflow_lock:
                with self._cache_stats_lock:
                    snapshot: dict[str, object] = {
                        "workflow": {
                            "state": self._workflow_state.name,
                            "error": self._workflow_error,
                            "is_busy": self.is_workflow_busy,
                            "can_extract": self.can_extract,
                            "can_preview": self.can_preview,
                            "can_search": self.can_search,
                            "can_scan": self.can_scan,
                        },
                        "settings": self._settings.copy(),
                        "runtime": {
                            ns: {
                                k: (v.value if isinstance(v, StateEntry) else v)
                                for k, v in data.items()
                            }
                            for ns, data in self._runtime_state.items()
                        },
                        "history": {
                            "count": len(self._sprite_history),
                            "offsets": [s["offset"] for s in self._sprite_history],
                        },
                        "cache_stats": self._cache_session_stats.copy(),
                        "preloaded_offsets_count": len(self._preloaded_offsets),
                        "timestamp": datetime.now(tz=UTC).isoformat(),
                    }
                    return snapshot

    def emit_state_snapshot(self) -> dict[str, object]:
        """Emit a state snapshot signal and return the snapshot.

        This method is useful for triggering state synchronization across
        components that listen to the application_state_snapshot signal.

        Returns:
            The emitted state snapshot dictionary
        """
        snapshot = self.get_full_state_snapshot()
        self.application_state_snapshot.emit(snapshot)
        return snapshot

    def set_current_offset(self, offset: int) -> None:
        """Set the current ROM offset and emit signal.

        Args:
            offset: The new current ROM offset
        """
        self.set_state("ui", "current_offset", offset)
        self.current_offset_changed.emit(offset)

    def get_current_offset(self) -> int | None:
        """Get the current ROM offset.

        Returns:
            Current offset or None if not set
        """
        offset = self.get_state("ui", "current_offset")
        if isinstance(offset, int):
            return offset
        return None

    def emit_preview_ready(self, offset: int, image: QImage) -> None:
        """Emit signal that a preview is ready for display.

        Args:
            offset: The ROM offset for this preview
            image: The QImage preview to display
        """
        self.preview_ready.emit(offset, image)
