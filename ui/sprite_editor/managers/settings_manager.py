#!/usr/bin/env python3
"""
Settings manager for the sprite editor.
Handles user preferences and persistent settings.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EditorSettings:
    """Editor settings data class."""

    # Extraction defaults
    default_offset: int = 0xC000
    default_size: int = 0x4000
    default_tiles_per_row: int = 16
    default_palette_index: int = 8

    # UI preferences
    zoom_level: int = 4
    show_grid: bool = True
    grid_color: str = "#808080"

    # Tool settings
    brush_size: int = 1
    last_tool: str = "pencil"

    # Recent files
    recent_vram_files: list[str] = field(default_factory=list)
    recent_cgram_files: list[str] = field(default_factory=list)
    recent_image_files: list[str] = field(default_factory=list)

    # Max recent files
    max_recent_files: int = 10


class SettingsManager:
    """Manages editor settings and persistence."""

    def __init__(self, settings_file: str | Path | None = None) -> None:
        """Initialize settings manager with optional settings file path."""
        if settings_file:
            self.settings_file = Path(settings_file)
        else:
            self.settings_file = Path.home() / ".spritepal" / "editor_settings.json"

        self.settings = EditorSettings()
        self._load_settings()

    def _load_settings(self) -> None:
        """Load settings from file."""
        if not self.settings_file.exists():
            return

        try:
            with self.settings_file.open() as f:
                data = json.load(f)

            # Update settings from loaded data
            for key, value in data.items():
                if hasattr(self.settings, key):
                    setattr(self.settings, key, value)

        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load settings: {e}")

    def save_settings(self) -> bool:
        """Save settings to file. Returns True on success."""
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)

            with self.settings_file.open("w") as f:
                json.dump(asdict(self.settings), f, indent=2)

            return True

        except OSError as e:
            logger.error(f"Could not save settings: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        return getattr(self.settings, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a setting value."""
        if hasattr(self.settings, key):
            setattr(self.settings, key, value)

    def add_recent_file(self, file_path: str, file_type: str) -> None:
        """Add a file to recent files list."""
        attr_name = f"recent_{file_type}_files"
        if not hasattr(self.settings, attr_name):
            return

        recent_list: list[str] = getattr(self.settings, attr_name)

        # Remove if already in list
        if file_path in recent_list:
            recent_list.remove(file_path)

        # Add to front
        recent_list.insert(0, file_path)

        # Trim to max size
        while len(recent_list) > self.settings.max_recent_files:
            recent_list.pop()

    def get_recent_files(self, file_type: str) -> list[str]:
        """Get recent files list for a file type."""
        attr_name = f"recent_{file_type}_files"
        if hasattr(self.settings, attr_name):
            return getattr(self.settings, attr_name)
        return []
