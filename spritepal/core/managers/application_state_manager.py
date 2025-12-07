"""
Consolidated Application State Manager for SpritePal.

This manager combines session, settings, state, and history management
into a single cohesive unit while maintaining backward compatibility.
"""

from __future__ import annotations

import json
import pickle
import sys
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from PySide6.QtCore import QObject, Signal
from typing_extensions import override

from .base_manager import BaseManager
from .exceptions import SessionError
from .session_manager import SessionManager

T = TypeVar("T")

class ApplicationStateManager(BaseManager):
    """
    Consolidated manager for all application state:
    - Session management (persistent settings)
    - Settings management (configuration)
    - State management (temporary runtime state)
    - History management (sprite history tracking)

    This manager provides a unified interface for all state-related operations
    while maintaining backward compatibility through embedded adapters.
    """

    # Unified signals
    state_changed = Signal(str, dict)  # State type, data

    # Session-specific signals (for backward compatibility)
    session_changed = Signal()
    files_updated = Signal(dict)
    settings_saved = Signal()
    session_restored = Signal(dict)

    # History-specific signals
    history_updated = Signal(list)  # List of sprite offsets
    sprite_added = Signal(int, float)  # Offset, quality

    def __init__(self, app_name: str = "SpritePal", settings_path: Path | None = None,
                 parent: QObject | None = None) -> None:
        """
        Initialize application state manager.

        Args:
            app_name: Application name for settings file
            settings_path: Optional custom path for settings file
            parent: Qt parent object
        """
        # Initialize state components
        self._app_name = app_name
        self._settings_file = settings_path or Path.cwd() / f".{app_name.lower()}_settings.json"

        # Persistent settings (saved to disk)
        self._settings: dict[str, Any] = {}
        self._session_dirty = False

        # Runtime state (temporary, not saved)
        self._runtime_state: dict[str, dict[str, Any]] = {}
        self._state_snapshots: dict[str, StateSnapshot] = OrderedDict()
        self._max_snapshots = 10

        # Sprite history
        self._sprite_history: list[dict[str, Any]] = []
        self._max_history = 50

        # Thread safety
        self._state_lock = threading.RLock()

        # Create backward compatibility adapters
        self._session_adapter: SessionAdapter | None = None
        self._settings_adapter: SettingsAdapter | None = None
        self._state_adapter: StateAdapter | None = None
        self._history_adapter: HistoryAdapter | None = None

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

            # Create adapters for backward compatibility
            self._session_adapter = SessionAdapter(self)
            self._settings_adapter = SettingsAdapter(self)
            self._state_adapter = StateAdapter(self)
            self._history_adapter = HistoryAdapter(self)

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
        and history but don't want the overhead of full manager re-initialization.

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

        self._logger.debug("ApplicationStateManager state reset (full_reset=%s)", full_reset)

    # ========== Settings Management (Persistent) ==========

    def get_setting(self, category: str, key: str, default: Any = None) -> Any:
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

    def set_setting(self, category: str, key: str, value: Any) -> None:
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

    def _load_settings(self) -> dict[str, Any]:
        """Load settings from file."""
        if self._settings_file.exists():
            try:
                with self._settings_file.open() as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._logger.info("Settings loaded successfully")
                        return self._merge_with_defaults(data)
            except (OSError, json.JSONDecodeError) as e:
                self._logger.warning(f"Could not load settings: {e}")

        return self._get_default_settings()

    def _get_default_settings(self) -> dict[str, Any]:
        """Get default settings structure."""
        return {
            "session": {
                "last_rom_path": "",
                "last_vram_path": "",
                "last_output_dir": "",
                "recent_files": []
            },
            "ui": {
                "window_width": 1200,
                "window_height": 800,
                "window_x": None,
                "window_y": None,
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
                "last_export_dir": "",
                "last_import_dir": ""
            }
        }

    def _merge_with_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        """Merge loaded settings with defaults."""
        defaults = self._get_default_settings()

        for category, values in defaults.items():
            if category not in data:
                data[category] = values
            elif isinstance(values, dict):
                for key, default_value in values.items():
                    if key not in data[category]:
                        data[category][key] = default_value

        return data

    # ========== State Management (Runtime/Temporary) ==========

    def get_state(self, namespace: str, key: str, default: Any = None) -> Any:
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

    def set_state(self, namespace: str, key: str, value: Any,
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
                             metadata: dict[str, Any] | None = None) -> bool:
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

            # Create sprite info
            sprite_info = {
                "offset": offset,
                "quality": quality,
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "metadata": metadata or {}
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

    def get_sprite_history(self) -> list[dict[str, Any]]:
        """Get full sprite history."""
        with self._lock:
            return self._sprite_history.copy()

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
        return recent[:max_files]

    def add_recent_file(self, file_path: str) -> None:
        """Add file to recent files list."""
        recent = self.get_setting("session", "recent_files", [])

        # Remove if already in list
        if file_path in recent:
            recent.remove(file_path)

        # Add to beginning
        recent.insert(0, file_path)

        # Limit size
        recent = recent[:20]

        self.set_setting("session", "recent_files", recent)

    # ========== Backward Compatibility Adapters ==========

    def get_session_adapter(self) -> SessionManager:
        """Get session manager adapter for backward compatibility."""
        if not self._session_adapter:
            raise SessionError("Session adapter not initialized")
        return self._session_adapter

    def get_settings_adapter(self) -> Any:
        """Get settings manager adapter for backward compatibility."""
        return self._settings_adapter

    def get_state_adapter(self) -> Any:
        """Get state manager adapter for backward compatibility."""
        return self._state_adapter

    def get_history_adapter(self) -> Any:
        """Get history manager adapter for backward compatibility."""
        return self._history_adapter

class StateEntry:
    """Wrapper for runtime state values with metadata."""

    def __init__(self, value: Any, ttl_seconds: float | None = None):
        self.value = value
        self.created_at = time.time()
        self.accessed_at = time.time()
        self.ttl_seconds = ttl_seconds
        self.access_count = 0

        # Track size for memory management
        try:
            self.size_bytes = len(pickle.dumps(value))
        except (TypeError, pickle.PicklingError):
            self.size_bytes = sys.getsizeof(value)

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    def touch(self) -> None:
        """Update access time."""
        self.accessed_at = time.time()
        self.access_count += 1

class StateSnapshot:
    """Immutable snapshot of state at a point in time."""

    def __init__(self, states: dict[str, Any], namespace: str | None = None):
        import uuid
        self.id = str(uuid.uuid4())
        self.timestamp = time.time()
        self.namespace = namespace

        # Deep copy the states
        try:
            self.states = pickle.loads(pickle.dumps(states))
        except (TypeError, pickle.PicklingError):
            self.states = states.copy()

class SessionAdapter(SessionManager):
    """Adapter providing SessionManager interface."""

    def __init__(self, state_manager: ApplicationStateManager):
        """Initialize adapter."""
        self._state_mgr = state_manager
        QObject.__init__(self, state_manager)
        self._is_initialized = True
        self._name = "SessionAdapter"
        self._logger = state_manager._logger

        # Set up required attributes that parent methods expect
        self._settings = state_manager._settings

        # Forward signals
        state_manager.session_changed.connect(self.session_changed.emit)
        state_manager.files_updated.connect(self.files_updated.emit)
        state_manager.settings_saved.connect(self.settings_saved.emit)
        state_manager.session_restored.connect(self.session_restored.emit)

    @override
    def _initialize(self) -> None:
        pass

    @override
    def cleanup(self) -> None:
        pass

    @override
    def get(self, category: str, key: str, default: Any = None) -> Any:
        return self._state_mgr.get_setting(category, key, default)

    @override
    def set(self, category: str, key: str, value: Any) -> None:
        self._state_mgr.set_setting(category, key, value)

    def save_session(self) -> bool:  # type: ignore[override]  # Base returns None, override returns bool for success
        return self._state_mgr.save_settings()

    @override
    def get_session_data(self) -> dict[str, Any]:
        return self._state_mgr.get_setting("session", "data", {})

    @override
    def update_session_data(self, data: dict[str, Any]) -> None:
        self._state_mgr.set_setting("session", "data", data)

    def update_file_path(self, file_type: str, path: str) -> None:
        self._state_mgr.update_session_file(file_type, path)

class SettingsAdapter:
    """Adapter providing SettingsManager interface."""

    def __init__(self, state_manager: ApplicationStateManager):
        self._state_mgr = state_manager
        self.app_name = state_manager._app_name

    def get(self, category: str, key: str, default: Any = None) -> Any:
        return self._state_mgr.get_setting(category, key, default)

    def set(self, category: str, key: str, value: Any) -> None:
        self._state_mgr.set_setting(category, key, value)

    def save_settings(self) -> None:
        self._state_mgr.save_settings()

    def save(self) -> None:
        self.save_settings()

    def get_value(self, category: str, key: str, default: Any = None) -> Any:
        return self.get(category, key, default)

    def set_value(self, category: str, key: str, value: Any) -> None:
        self.set(category, key, value)

class StateAdapter:
    """Adapter providing StateManager interface."""

    def __init__(self, state_manager: ApplicationStateManager):
        self._state_mgr = state_manager

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        return self._state_mgr.get_state(namespace, key, default)

    def set(self, namespace: str, key: str, value: Any,
            ttl_seconds: float | None = None) -> None:
        self._state_mgr.set_state(namespace, key, value, ttl_seconds)

    def clear(self, namespace: str | None = None) -> None:
        self._state_mgr.clear_state(namespace)

    def create_snapshot(self, namespace: str | None = None) -> str:
        return self._state_mgr.create_snapshot(namespace)

    def restore_snapshot(self, snapshot_id: str) -> bool:
        return self._state_mgr.restore_snapshot(snapshot_id)

class HistoryAdapter:
    """Adapter providing SpriteHistoryManager interface."""

    def __init__(self, state_manager: ApplicationStateManager):
        self._state_mgr = state_manager
        self.MAX_HISTORY = 50

    def add_sprite(self, offset: int, quality: float = 1.0) -> bool:
        return self._state_mgr.add_sprite_to_history(offset, quality)

    def has_sprite(self, offset: int) -> bool:
        history = self._state_mgr.get_sprite_history()
        return any(s["offset"] == offset for s in history)

    def clear_history(self) -> None:
        self._state_mgr.clear_sprite_history()

    def get_sprites(self) -> list[tuple[int, float]]:
        history = self._state_mgr.get_sprite_history()
        return [(s["offset"], s.get("quality", 1.0)) for s in history]

    def get_sprite_info(self, offset: int) -> dict[str, Any] | None:
        history = self._state_mgr.get_sprite_history()
        for sprite in history:
            if sprite["offset"] == offset:
                return sprite.copy()
        return None
