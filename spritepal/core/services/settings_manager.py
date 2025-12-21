from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from utils.constants import (
    CACHE_EXPIRATION_MAX_DAYS,
    CACHE_EXPIRATION_MIN_DAYS,
    CACHE_SIZE_MAX_MB,
    CACHE_SIZE_MIN_MB,
)

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ApplicationStateManagerProtocol


class SettingsManager:
    """Manages application settings and session persistence"""

    def __init__(self, app_name: str, session_manager: ApplicationStateManagerProtocol) -> None:
        """Initialize SettingsManager with required dependencies.

        Args:
            app_name: Application name for settings identification.
            session_manager: Required session manager for settings persistence.
        """
        self.app_name: str = app_name
        self._session_manager = session_manager
        # Initialize default settings if not present
        self._ensure_default_settings()


    def _ensure_default_settings(self) -> None:
        """Ensure default settings exist in SessionManager"""
        # Check and set default cache settings if not present
        if self._session_manager.get("cache", "enabled") is None:
            self._session_manager.set("cache", "enabled", True)
        if self._session_manager.get("cache", "max_size_mb") is None:
            self._session_manager.set("cache", "max_size_mb", 500)
        if self._session_manager.get("cache", "expiration_days") is None:
            self._session_manager.set("cache", "expiration_days", 30)
        if self._session_manager.get("cache", "auto_cleanup") is None:
            self._session_manager.set("cache", "auto_cleanup", True)
        if self._session_manager.get("cache", "show_indicators") is None:
            self._session_manager.set("cache", "show_indicators", True)

        # Set default paths if not present
        if self._session_manager.get("paths", "default_dumps_dir") is None:
            default_dir = str(Path.home() / "Documents" / "Mesen2" / "Debugger")
            self._session_manager.set("paths", "default_dumps_dir", default_dir)

    def save_settings(self) -> None:
        """Save settings to file"""
        self._session_manager.save_session()

    def save(self) -> None:
        """Save settings to file (alias for save_settings)"""
        self.save_settings()

    def get(self, category: str, key: str, default: object = None) -> object:
        """Get a setting value"""
        return self._session_manager.get(category, key, default)

    def get_value(self, category: str, key: str, default: object = None) -> object:
        """Get a setting value (alias for get method)"""
        return self.get(category, key, default)

    def set(self, category: str, key: str, value: object) -> None:
        """Set a setting value"""
        self._session_manager.set(category, key, value)

    def set_value(self, category: str, key: str, value: object) -> None:
        """Set a setting value (alias for set method)"""
        self.set(category, key, value)

    def get_session_data(self) -> dict[str, object]:
        """Get all session data"""
        # Protocol returns Mapping, need to convert to dict
        return dict(self._session_manager.get_session_data())

    def save_session_data(self, session_data: dict[str, object]) -> None:
        """Save session data"""
        self._session_manager.update_session_data(session_data)

    def get_ui_data(self) -> dict[str, object]:
        """Get UI settings"""
        # Get all UI settings from SessionManager
        ui_data: dict[str, object] = {}
        for key in ["window_width", "window_height", "window_x", "window_y", "restore_position", "theme"]:
            value = self._session_manager.get("ui", key)
            if value is not None:
                ui_data[key] = value
        return ui_data

    def save_ui_data(self, ui_data: dict[str, object]) -> None:
        """Save UI settings"""
        for key, value in ui_data.items():
            self._session_manager.set("ui", key, value)
        self.save_settings()

    def validate_file_paths(self) -> dict[str, str]:
        """Validate and return existing file paths from session"""
        session = self.get_session_data()
        validated_paths = {}

        for key in ["vram_path", "cgram_path", "oam_path"]:
            path = str(session.get(key, ""))  # Cast object to str
            if path and Path(path).exists():
                validated_paths[key] = path
            else:
                validated_paths[key] = ""

        return validated_paths

    def has_valid_session(self) -> bool:
        """Check if there's a valid session to restore"""
        validated = self.validate_file_paths()
        return bool(validated.get("vram_path") or validated.get("cgram_path"))

    def clear_session(self) -> None:
        """Clear session data"""
        self._session_manager.clear_session()

    def get_default_directory(self) -> str:
        """Get the default directory for file operations"""
        # Try last used directory first
        last_used = str(self.get("paths", "last_used_dir", ""))
        if last_used and Path(last_used).exists():
            return last_used

        # Fall back to default dumps directory (platform-appropriate)
        default_dir = str(
            self.get(
                "paths",
                "default_dumps_dir",
                str(Path.home() / "Documents" / "Mesen2" / "Debugger")
            )
        )
        if default_dir and Path(default_dir).exists():
            return default_dir

        # Final fallback to home directory (not CWD for better portability)
        return str(Path.home())

    def set_last_used_directory(self, directory: str) -> None:
        """Set the last used directory"""
        if directory and Path(directory).exists():
            self.set("paths", "last_used_dir", directory)
            self.save_settings()

    def get_cache_settings(self) -> dict[str, object]:
        """Get all cache settings"""
        return {
            "enabled": self.get("cache", "enabled", True),
            "location": self.get("cache", "location", ""),
            "max_size_mb": self.get("cache", "max_size_mb", 500),
            "expiration_days": self.get("cache", "expiration_days", 30),
            "auto_cleanup": self.get("cache", "auto_cleanup", True),
            "show_indicators": self.get("cache", "show_indicators", True),
        }

    def set_cache_enabled(self, enabled: bool) -> None:
        """Enable or disable caching"""
        self.set("cache", "enabled", enabled)
        self.save_settings()

    def get_cache_enabled(self) -> bool:
        """Check if caching is enabled"""
        return bool(self.get("cache", "enabled", True))

    def set_cache_location(self, location: str) -> None:
        """Set custom cache location"""
        self.set("cache", "location", location)
        self.save_settings()

    def get_cache_location(self) -> str:
        """Get custom cache location (empty string means default)"""
        return str(self.get("cache", "location", ""))

    def get_cache_max_size_mb(self) -> int:
        """Get maximum cache size in MB"""
        value = self.get("cache", "max_size_mb", 500)
        return int(value) if value is not None else 500  # pyright: ignore[reportArgumentType] - runtime ensures int/str

    def set_cache_max_size_mb(self, size_mb: int) -> None:
        """Set maximum cache size in MB"""
        self.set("cache", "max_size_mb", max(CACHE_SIZE_MIN_MB, min(CACHE_SIZE_MAX_MB, size_mb)))
        self.save_settings()

    def get_cache_expiration_days(self) -> int:
        """Get cache expiration in days"""
        value = self.get("cache", "expiration_days", 30)
        return int(value) if value is not None else 30  # pyright: ignore[reportArgumentType] - runtime ensures int/str

    def set_cache_expiration_days(self, days: int) -> None:
        """Set cache expiration in days"""
        self.set("cache", "expiration_days", max(CACHE_EXPIRATION_MIN_DAYS, min(CACHE_EXPIRATION_MAX_DAYS, days)))
        self.save_settings()


