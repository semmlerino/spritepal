"""
Session file controller for managing panel session persistence.

Handles validation and organization of session file paths without
owning any Qt widgets. Panels use this to validate and prepare
session data for save/restore operations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import QObject, Signal

from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SessionFileEntry:
    """A single file entry in session data.

    Attributes:
        key: Session key name (e.g., "vram_path")
        path: File path (may be empty)
        exists: Whether the path points to an existing file
    """

    key: str
    path: str
    exists: bool


@dataclass
class ValidatedSessionData:
    """Session data after validation.

    Attributes:
        files: List of validated file entries
        valid_files: Only entries with existing files
        missing_files: Only entries with missing files
        extras: Non-file session data (mode indices, etc.)
    """

    files: list[SessionFileEntry]
    extras: dict[str, Any]  # pyright: ignore[reportExplicitAny] - Session data can be any type

    @property
    def valid_files(self) -> list[SessionFileEntry]:
        """Get only entries where the file exists."""
        return [f for f in self.files if f.exists]

    @property
    def missing_files(self) -> list[SessionFileEntry]:
        """Get only entries where the file is missing."""
        return [f for f in self.files if not f.exists]

    @property
    def has_any_valid(self) -> bool:
        """Whether any files are valid."""
        return len(self.valid_files) > 0


@dataclass
class SessionFileConfig:
    """Configuration for session file handling.

    Attributes:
        file_keys: List of keys that represent file paths
        extra_keys: List of keys that are non-file data (preserved as-is)
    """

    file_keys: list[str] = field(default_factory=list)
    extra_keys: list[str] = field(default_factory=list)


# Default configurations for common panel types
EXTRACTION_PANEL_CONFIG = SessionFileConfig(
    file_keys=["vram_path", "cgram_path", "oam_path"],
    extra_keys=["extraction_mode"],
)

ROM_PANEL_CONFIG = SessionFileConfig(
    file_keys=["rom_path", "output_path"],
    extra_keys=["sprite_name", "sprite_offset", "manual_mode"],
)


class SessionFileController(QObject):
    """Controller for session file path management.

    Validates file paths, tracks which files exist, and provides
    clean data structures for session save/restore operations.

    Signals:
        validation_complete: Emitted after validating session data
    """

    validation_complete = Signal(object)  # ValidatedSessionData

    def __init__(
        self,
        config: SessionFileConfig | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize session file controller.

        Args:
            config: Configuration defining file and extra keys
            parent: Parent QObject
        """
        super().__init__(parent)
        self._config = config or SessionFileConfig()

    @property
    def config(self) -> SessionFileConfig:
        """Get the current configuration."""
        return self._config

    def set_config(self, config: SessionFileConfig) -> None:
        """Update the configuration.

        Args:
            config: New configuration
        """
        self._config = config

    def validate_session_data(
        self,
        data: Mapping[str, Any],  # pyright: ignore[reportExplicitAny] - Session data can be any type
    ) -> ValidatedSessionData:
        """Validate session data and check file existence.

        Args:
            data: Raw session data dictionary

        Returns:
            ValidatedSessionData with file existence info
        """
        files: list[SessionFileEntry] = []
        extras: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny]

        # Validate file paths
        for key in self._config.file_keys:
            path_value = data.get(key, "")
            path_str = str(path_value) if path_value else ""

            if path_str:
                exists = Path(path_str).exists()
            else:
                exists = False

            files.append(SessionFileEntry(key=key, path=path_str, exists=exists))

        # Collect extra data
        for key in self._config.extra_keys:
            if key in data:
                extras[key] = data[key]

        result = ValidatedSessionData(files=files, extras=extras)
        self.validation_complete.emit(result)

        return result

    def build_session_data(
        self,
        file_paths: dict[str, str],
        extras: dict[str, Any] | None = None,  # pyright: ignore[reportExplicitAny]
    ) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Build session data dictionary from current state.

        Args:
            file_paths: Dictionary of key -> path mappings
            extras: Additional non-file data to include

        Returns:
            Complete session data dictionary
        """
        result: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny]

        # Add file paths
        for key in self._config.file_keys:
            result[key] = file_paths.get(key, "")

        # Add extras
        if extras:
            for key in self._config.extra_keys:
                if key in extras:
                    result[key] = extras[key]

        return result

    def get_valid_paths(
        self,
        data: Mapping[str, Any],  # pyright: ignore[reportExplicitAny]
    ) -> dict[str, str]:
        """Get only file paths that exist.

        Args:
            data: Raw session data

        Returns:
            Dictionary of key -> path for existing files only
        """
        validated = self.validate_session_data(data)
        return {entry.key: entry.path for entry in validated.valid_files}

    @staticmethod
    def check_file_exists(path: str | Path | None) -> bool:
        """Check if a file path exists.

        Args:
            path: Path to check

        Returns:
            True if path points to an existing file
        """
        if not path:
            return False
        return Path(path).exists()

    @staticmethod
    def normalize_path(path: str | Path | None) -> str:
        """Normalize a path to string form.

        Args:
            path: Path to normalize

        Returns:
            String path or empty string if None
        """
        if not path:
            return ""
        return str(path)


def create_extraction_panel_controller(
    parent: QObject | None = None,
) -> SessionFileController:
    """Create a session controller configured for ExtractionPanel.

    Args:
        parent: Parent QObject

    Returns:
        Configured SessionFileController
    """
    return SessionFileController(config=EXTRACTION_PANEL_CONFIG, parent=parent)


def create_rom_panel_controller(
    parent: QObject | None = None,
) -> SessionFileController:
    """Create a session controller configured for ROMExtractionPanel.

    Args:
        parent: Parent QObject

    Returns:
        Configured SessionFileController
    """
    return SessionFileController(config=ROM_PANEL_CONFIG, parent=parent)
