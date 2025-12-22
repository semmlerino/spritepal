"""
Sprite preset manager for user-managed sprite offset presets.

This module provides CRUD operations for sprite presets, ROM matching,
and import/export functionality for community sharing.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from core.types import SpritePreset

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ConfigurationServiceProtocol

logger = logging.getLogger(__name__)


class SpritePresetManager(QObject):
    """Manages user-defined sprite presets with persistence and ROM matching.

    Presets are stored in a user-specific JSON file separate from built-in
    configurations, allowing community sharing via import/export.
    """

    # Signals for UI updates
    preset_added = Signal(str)  # Preset name
    preset_removed = Signal(str)  # Preset name
    preset_updated = Signal(str)  # Preset name
    presets_loaded = Signal()
    presets_imported = Signal(int)  # Number imported

    PRESETS_FILENAME = "user_sprite_presets.json"
    EXPORT_EXTENSION = ".spritepal-presets.json"

    def __init__(
        self,
        config_service: ConfigurationServiceProtocol | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the preset manager.

        Args:
            config_service: Optional configuration service for paths
            parent: Optional Qt parent object
        """
        super().__init__(parent)

        self._presets: dict[str, SpritePreset] = {}
        self._config_service = config_service
        self._presets_file: Path | None = None

        # Determine presets file path
        if config_service is not None:
            self._presets_file = config_service.config_directory / self.PRESETS_FILENAME
        else:
            # Fallback to home directory
            self._presets_file = Path.home() / ".spritepal" / self.PRESETS_FILENAME

        # Load existing presets
        self._load_presets()

    def _load_presets(self) -> None:
        """Load presets from the user presets file."""
        if self._presets_file is None or not self._presets_file.exists():
            logger.debug("No user presets file found, starting with empty presets")
            return

        try:
            with open(self._presets_file, encoding="utf-8") as f:
                data = json.load(f)

            version = data.get("version", "1.0")
            presets_data = data.get("presets", [])

            for preset_data in presets_data:
                try:
                    preset = SpritePreset.from_dict(preset_data)
                    self._presets[preset.name] = preset
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"Skipping invalid preset: {e}")

            logger.info(
                f"Loaded {len(self._presets)} user presets (version {version})"
            )
            self.presets_loaded.emit()

        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load user presets: {e}")

    def _save_presets(self) -> bool:
        """Save presets to the user presets file.

        Returns:
            True if save succeeded, False otherwise
        """
        if self._presets_file is None:
            logger.warning("No presets file path configured")
            return False

        try:
            # Ensure directory exists
            self._presets_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "version": "1.0",
                "presets": [preset.to_dict() for preset in self._presets.values()],
            }

            # Atomic write using temp file
            temp_file = self._presets_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self._presets_file)

            logger.debug(f"Saved {len(self._presets)} presets to {self._presets_file}")
            return True

        except OSError as e:
            logger.error(f"Failed to save user presets: {e}")
            return False

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    def add_preset(self, preset: SpritePreset) -> bool:
        """Add a new preset.

        Args:
            preset: The preset to add

        Returns:
            True if added, False if preset with that name already exists
        """
        if preset.name in self._presets:
            logger.warning(f"Preset '{preset.name}' already exists")
            return False

        self._presets[preset.name] = preset
        self._save_presets()
        self.preset_added.emit(preset.name)
        logger.info(f"Added preset '{preset.name}' for {preset.game_title}")
        return True

    def update_preset(self, preset: SpritePreset) -> bool:
        """Update an existing preset.

        Args:
            preset: The preset with updated values (matched by name)

        Returns:
            True if updated, False if preset doesn't exist
        """
        if preset.name not in self._presets:
            logger.warning(f"Preset '{preset.name}' not found for update")
            return False

        self._presets[preset.name] = preset
        self._save_presets()
        self.preset_updated.emit(preset.name)
        logger.info(f"Updated preset '{preset.name}'")
        return True

    def remove_preset(self, name: str) -> bool:
        """Remove a preset by name.

        Args:
            name: Name of the preset to remove

        Returns:
            True if removed, False if not found
        """
        if name not in self._presets:
            logger.warning(f"Preset '{name}' not found for removal")
            return False

        del self._presets[name]
        self._save_presets()
        self.preset_removed.emit(name)
        logger.info(f"Removed preset '{name}'")
        return True

    def get_preset(self, name: str) -> SpritePreset | None:
        """Get a preset by name.

        Args:
            name: Name of the preset

        Returns:
            The preset, or None if not found
        """
        return self._presets.get(name)

    def get_all_presets(self) -> list[SpritePreset]:
        """Get all user presets.

        Returns:
            List of all presets
        """
        return list(self._presets.values())

    def get_presets_for_game(self, game_title: str) -> list[SpritePreset]:
        """Get all presets for a specific game.

        Args:
            game_title: The game title to match

        Returns:
            List of matching presets
        """
        return [
            p for p in self._presets.values()
            if p.game_title.upper() == game_title.upper()
        ]

    def get_presets_for_checksum(self, checksum: int) -> list[SpritePreset]:
        """Get all presets that match a ROM checksum.

        Args:
            checksum: The ROM checksum to match

        Returns:
            List of matching presets
        """
        return [
            p for p in self._presets.values()
            if checksum in p.game_checksums
        ]

    def get_presets_by_tag(self, tag: str) -> list[SpritePreset]:
        """Get all presets with a specific tag.

        Args:
            tag: The tag to match (case-insensitive)

        Returns:
            List of matching presets
        """
        tag_lower = tag.lower()
        return [
            p for p in self._presets.values()
            if any(t.lower() == tag_lower for t in p.tags)
        ]

    # =========================================================================
    # Import/Export
    # =========================================================================

    def export_presets(
        self,
        path: Path,
        preset_names: list[str] | None = None,
    ) -> int:
        """Export presets to a file for sharing.

        Args:
            path: Path to export file
            preset_names: Optional list of preset names to export
                         (exports all if None)

        Returns:
            Number of presets exported
        """
        if preset_names is None:
            presets_to_export = list(self._presets.values())
        else:
            presets_to_export = [
                self._presets[name]
                for name in preset_names
                if name in self._presets
            ]

        if not presets_to_export:
            logger.warning("No presets to export")
            return 0

        try:
            # Mark exported presets
            export_data = {
                "version": "1.0",
                "format": "spritepal-presets",
                "presets": [
                    {**preset.to_dict(), "source": "imported"}
                    for preset in presets_to_export
                ],
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)

            logger.info(f"Exported {len(presets_to_export)} presets to {path}")
            return len(presets_to_export)

        except OSError as e:
            logger.error(f"Failed to export presets: {e}")
            return 0

    def import_presets(
        self,
        path: Path,
        overwrite_existing: bool = False,
    ) -> int:
        """Import presets from a file.

        Args:
            path: Path to import file
            overwrite_existing: If True, overwrite presets with same name

        Returns:
            Number of presets imported
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            # Validate format
            if data.get("format") != "spritepal-presets":
                logger.warning(f"Invalid preset file format: {path}")
                return 0

            presets_data = data.get("presets", [])
            imported_count = 0

            for preset_data in presets_data:
                try:
                    # Force source to "imported"
                    preset_data["source"] = "imported"
                    preset = SpritePreset.from_dict(preset_data)

                    if preset.name in self._presets:
                        if overwrite_existing:
                            self._presets[preset.name] = preset
                            imported_count += 1
                        else:
                            logger.debug(
                                f"Skipping existing preset '{preset.name}'"
                            )
                    else:
                        self._presets[preset.name] = preset
                        imported_count += 1

                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"Skipping invalid preset during import: {e}")

            if imported_count > 0:
                self._save_presets()
                self.presets_imported.emit(imported_count)

            logger.info(f"Imported {imported_count} presets from {path}")
            return imported_count

        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to import presets: {e}")
            return 0

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def has_preset(self, name: str) -> bool:
        """Check if a preset with the given name exists.

        Args:
            name: Preset name to check

        Returns:
            True if preset exists
        """
        return name in self._presets

    def get_preset_count(self) -> int:
        """Get the total number of presets.

        Returns:
            Number of presets
        """
        return len(self._presets)

    def get_all_game_titles(self) -> list[str]:
        """Get list of unique game titles in presets.

        Returns:
            Sorted list of unique game titles
        """
        return sorted({p.game_title for p in self._presets.values()})

    def get_all_tags(self) -> list[str]:
        """Get list of all unique tags.

        Returns:
            Sorted list of unique tags
        """
        all_tags: set[str] = set()
        for preset in self._presets.values():
            all_tags.update(preset.tags)
        return sorted(all_tags)

    def clear_all(self) -> None:
        """Remove all presets."""
        self._presets.clear()
        self._save_presets()
        self.presets_loaded.emit()
        logger.info("Cleared all user presets")

    def reload(self) -> None:
        """Reload presets from disk."""
        self._presets.clear()
        self._load_presets()
