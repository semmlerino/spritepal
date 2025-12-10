"""
Manager for session state and application settings
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from PySide6.QtCore import Signal
from typing_extensions import override

from utils.file_validator import atomic_write

from .base_manager import BaseManager
from .exceptions import SessionError, ValidationError

T = TypeVar("T")

class SessionManager(BaseManager):
    """Manages session state and application settings"""

    # Signals for session events
    session_changed: Signal = Signal()  # Emitted when session state changes
    files_updated: Signal = Signal(dict)  # Emitted when file paths change
    settings_saved: Signal = Signal()  # Emitted when settings are saved
    session_restored: Signal = Signal(dict)  # Emitted when session is restored

    def __init__(self, app_name: str = "SpritePal", settings_path: Path | None = None) -> None:
        """
        Initialize session manager

        Args:
            app_name: Application name for settings file
            settings_path: Optional custom path for settings file (for testing)
        """
        # Initialize attributes needed by _initialize() before calling super()
        self._app_name: str
        self._settings_file: Path
        self._settings: dict[str, Any] = {}
        self._session_dirty: bool = False

        self._app_name = app_name
        if settings_path:
            self._settings_file = settings_path
        else:
            self._settings_file = Path.cwd() / f".{app_name.lower()}_settings.json"
        self._settings = {}
        self._session_dirty = False

        # Now call super() which will call _initialize()
        super().__init__("SessionManager")

    @override
    def _initialize(self) -> None:
        """Initialize session management"""
        self._settings = self._load_settings()
        self._is_initialized = True
        self._logger.info(f"SessionManager initialized with settings file: {self._settings_file}")

    @override
    def cleanup(self) -> None:
        """Save settings on cleanup"""
        if self._session_dirty:
            self.save_session()

    def reset_state(self) -> None:
        """Reset internal state for test isolation.

        This method clears any mutable state that could leak between tests
        when the manager is used in class-scoped fixtures. It reloads settings
        from file and clears the dirty flag.
        """
        self._settings = self._load_settings()
        self._session_dirty = False

    def _load_settings(self) -> dict[str, Any]:
        """Load settings from file"""
        if self._settings_file.exists():
            try:
                with self._settings_file.open() as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._logger.info("Settings loaded successfully")
                        # Check if this is old format (flat structure without categories)
                        if not any(key in data for key in ["session", "ui", "cache", "paths"]):
                            self._logger.info("Detected old settings format, migrating...")
                            return self._migrate_old_settings(data)
                        # Merge with defaults to ensure all keys exist
                        return self._merge_with_defaults(data)
                    self._logger.warning("Invalid settings file format, using defaults")
            except (OSError, json.JSONDecodeError) as e:
                self._logger.warning(f"Could not load settings: {e}")

        # Return default settings
        return self._get_default_settings()

    def _merge_with_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        """Merge loaded settings with defaults to ensure all keys exist"""
        defaults = self._get_default_settings()

        # Deep merge - ensure all default categories and keys exist
        for category, values in defaults.items():
            if category not in data:
                data[category] = values
            elif isinstance(values, dict):
                for key, default_value in values.items():
                    if key not in data[category]:
                        data[category][key] = default_value

        return data

    def _migrate_old_settings(self, old_data: dict[str, Any]) -> dict[str, Any]:
        """Migrate old flat settings format to new categorized format"""
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

    def _get_default_settings(self) -> dict[str, Any]:
        """Get default settings structure"""
        return {
            "session": {
                "vram_path": "",
                "cgram_path": "",
                "oam_path": "",
                "output_name": "",
                "create_grayscale": True,
                "create_metadata": True,
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
            },
            "paths": {
                "default_dumps_dir": str(Path.home() / "Documents" / "Mesen2" / "Debugger"),
                "last_used_dir": "",
            },
            "recent_files": {
                "vram": [],
                "cgram": [],
                "oam": [],
                "rom": [],
                "max_recent": 10,
            }
        }

    def save_session(self) -> None:
        """Save current session to file"""
        operation = "save_session"

        if not self._start_operation(operation):
            return

        try:
            # Use atomic write to prevent corruption on crash/power loss
            data = json.dumps(self._settings, indent=2).encode("utf-8")
            atomic_write(self._settings_file, data)

            self._session_dirty = False
            self.settings_saved.emit()
            self._logger.info("Session saved successfully")

        except OSError as e:
            error = SessionError(f"Could not save settings: {e}")
            self._handle_error(error, operation)
        finally:
            self._finish_operation(operation)

    def restore_session(self) -> dict[str, Any]:
        """
        Restore session from file

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

        except Exception as e:
            error = SessionError(f"Could not restore session: {e}")
            self._handle_error(error, operation)
            return {}
        else:
            return session_data
        finally:
            self._finish_operation(operation)

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """
        Get a setting value

        Args:
            category: Setting category
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value or default
        """
        return self._settings.get(category, {}).get(key, default)

    def set(self, category: str, key: str, value: Any) -> None:
        """
        Set a setting value

        Args:
            category: Setting category
            key: Setting key
            value: Value to set
        """
        if category not in self._settings:
            self._settings[category] = {}

        old_value = self._settings[category].get(key)
        if old_value != value:
            self._settings[category][key] = value
            self._session_dirty = True
            self.session_changed.emit()

            # Emit specific signals for file updates
            if category == "session" and key in ["vram_path", "cgram_path", "oam_path"]:
                self.files_updated.emit({key: value})

    def get_session_data(self) -> dict[str, Any]:
        """Get all session data"""
        session = self._settings.get("session", {})
        return session if isinstance(session, dict) else {}

    def update_session_data(self, data: dict[str, Any]) -> None:
        """
        Update multiple session values at once

        Args:
            data: Dictionary of session data to update
        """
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
        Update file paths in session

        Args:
            vram: VRAM file path
            cgram: CGRAM file path
            oam: OAM file path
        """
        updates = {}
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

    def update_window_state(self, geometry: dict[str, int | float]) -> None:
        """
        Update window geometry in settings

        Args:
            geometry: Dictionary with width, height, x, y
        """
        if "ui" not in self._settings:
            self._settings["ui"] = {}

        changed = False
        for key in ["width", "height", "x", "y"]:
            if key in geometry:
                setting_key = f"window_{key}"
                if self._settings["ui"].get(setting_key) != geometry[key]:
                    self._settings["ui"][setting_key] = geometry[key]
                    changed = True

        if changed:
            self._session_dirty = True

    def get_window_geometry(self) -> dict[str, int]:
        """Get saved window geometry"""
        ui_settings = self._settings.get("ui", {})
        # Use 'or' to handle both missing keys and None values
        return {
            "width": ui_settings.get("window_width") or 900,
            "height": ui_settings.get("window_height") or 600,
            "x": ui_settings.get("window_x") if ui_settings.get("window_x") is not None else -1,
            "y": ui_settings.get("window_y") if ui_settings.get("window_y") is not None else -1,
        }

    def get_recent_files(self, file_type: str) -> list[str]:
        """
        Get recent files of a specific type

        Args:
            file_type: Type of files (vram, cgram, oam, rom)

        Returns:
            List of recent file paths
        """
        recent = self._settings.get("recent_files", {})
        files = recent.get(file_type, [])

        # Filter out non-existent files
        existing_files = [f for f in files if Path(f).exists()]

        # Update if we removed any
        if len(existing_files) != len(files):
            if "recent_files" not in self._settings:
                self._settings["recent_files"] = {}
            self._settings["recent_files"][file_type] = existing_files
            self._session_dirty = True

        return existing_files

    def _add_recent_file(self, file_type: str, file_path: str) -> None:
        """Add a file to recent files list"""
        if not file_path or not Path(file_path).exists():
            return

        if "recent_files" not in self._settings:
            self._settings["recent_files"] = {}

        recent = self._settings["recent_files"]
        if file_type not in recent:
            recent[file_type] = []

        # Remove if already in list
        if file_path in recent[file_type]:
            recent[file_type].remove(file_path)

        # Add to front
        recent[file_type].insert(0, file_path)

        # Limit size
        max_recent = recent.get("max_recent", 10)
        recent[file_type] = recent[file_type][:max_recent]

        self._session_dirty = True

    def clear_session(self) -> None:
        """Clear current session data"""
        if "session" in self._settings:
            self._settings["session"] = self._get_default_settings()["session"]
            self._session_dirty = True
            self.session_changed.emit()
            self._logger.info("Session cleared")

    def clear_recent_files(self, file_type: str | None = None) -> None:
        """
        Clear recent files

        Args:
            file_type: Specific type to clear, or None for all
        """
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
        Export settings to a file

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
        Import settings from a file

        Args:
            file_path: Path to import from

        Raises:
            SessionError: If import fails
            ValidationError: If settings are invalid
        """
        try:
            self._validate_file_exists(file_path, "Settings file")

            with Path(file_path).open() as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValidationError("Invalid settings file format")

            # Validate basic structure
            if "session" not in data and "ui" not in data and "paths" not in data:
                raise ValidationError("Settings file missing required sections")

            # Merge with defaults to ensure all keys exist
            defaults = self._get_default_settings()
            for category in defaults:
                if category not in data:
                    data[category] = defaults[category]
                elif isinstance(defaults[category], dict):
                    for key in defaults[category]:
                        if key not in data[category]:
                            data[category][key] = defaults[category][key]

            self._settings = data
            self._session_dirty = True
            self.session_changed.emit()
            self._logger.info(f"Settings imported from {file_path}")

        except (OSError, json.JSONDecodeError) as e:
            raise SessionError(f"Could not import settings: {e}") from e
