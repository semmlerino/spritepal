"""
Path suggestion functions for VRAM and ROM files.

Provides smart path suggestions for injection workflows by using multiple
strategies: metadata, session data, basename patterns, and saved settings.

This module uses pure functions instead of a stateless service class.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

from utils.constants import (
    SETTINGS_KEY_LAST_INPUT_VRAM,
    SETTINGS_NS_ROM_INJECTION,
    SETTINGS_NS_SESSION,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from core.managers.application_state_manager import ApplicationStateManager


logger = logging.getLogger(__name__)


# VRAM filename patterns to check (common conventions only)
VRAM_PATTERNS = [
    "{base}.dmp",
    "{base}_VRAM.dmp",
]

# Editor suffixes to strip when matching
EDITOR_SUFFIXES = ["_sprites_editor", "_sprites", "_editor", "Edited"]


def validate_path(path: str | None) -> str:
    """
    Validate and return path if it exists, empty string otherwise.

    Args:
        path: Path to validate

    Returns:
        The path if it exists, empty string otherwise
    """
    if path and Path(path).exists():
        return str(path)
    return ""


def find_vram_path(
    sprite_path: str,
    metadata_path: str = "",
    metadata: Mapping[str, object] | None = None,
    pre_suggested: str = "",
    strip_editor_suffixes: bool = False,
    session_manager: ApplicationStateManager | None = None,
) -> str:
    """
    Find VRAM path using multiple strategies in priority order.

    Strategies (in order):
    1. Pre-suggested path
    2. Session manager vram_path
    3. Metadata file (source_vram or extraction.vram_source)
    4. Basename pattern matching
    5. Last injection settings

    Args:
        sprite_path: Path to sprite file
        metadata_path: Optional metadata file path (loads and parses)
        metadata: Pre-loaded metadata dict (from load_metadata)
        pre_suggested: Pre-suggested VRAM path to check first
        strip_editor_suffixes: Strip editor suffixes from sprite name
        session_manager: Optional session manager for session-based strategies

    Returns:
        Suggested VRAM path or empty string if none found
    """
    # Strategy 1: Pre-suggested path
    if result := validate_path(pre_suggested):
        return result

    # Strategy 2: Session manager vram_path
    if session_manager:
        try:
            session_vram = cast(
                str, session_manager.get(SETTINGS_NS_SESSION, "vram_path", "")
            )
            if result := validate_path(session_vram):
                return result
        except (OSError, ValueError, TypeError):
            pass

    # Strategy 3: Metadata file
    loaded_metadata = dict(metadata) if metadata else None
    if not loaded_metadata and metadata_path and Path(metadata_path).exists():
        try:
            with Path(metadata_path).open() as f:
                loaded_metadata = cast(dict[str, object], json.load(f))
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    if loaded_metadata:
        # Check top-level source_vram (absolute path)
        if result := validate_path(
            cast(str, loaded_metadata.get("source_vram", ""))
        ):
            return result
        # Check extraction.vram_source (relative path)
        extraction = loaded_metadata.get("extraction")
        if isinstance(extraction, dict):
            vram_source = cast(str, extraction.get("vram_source", ""))
            if vram_source and sprite_path:
                sprite_dir = Path(sprite_path).parent
                if result := validate_path(str(sprite_dir / vram_source)):
                    return result

    # Strategy 4: Basename pattern matching
    if sprite_path:
        sprite_path_obj = Path(sprite_path)
        sprite_dir = sprite_path_obj.parent
        base_name = sprite_path_obj.stem

        if strip_editor_suffixes:
            for suffix in EDITOR_SUFFIXES:
                if base_name.endswith(suffix):
                    base_name = base_name[: -len(suffix)]
                    break

        for pattern in VRAM_PATTERNS:
            filename = pattern.format(base=base_name)
            if result := validate_path(str(sprite_dir / filename)):
                return result

    # Strategy 5: Last injection settings
    if session_manager:
        try:
            last_vram = cast(
                str,
                session_manager.get(
                    SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_VRAM, ""
                ),
            )
            if result := validate_path(last_vram):
                return result
        except (OSError, ValueError, TypeError):
            pass

    logger.debug("No VRAM suggestion found")
    return ""


def get_smart_vram_suggestion(
    sprite_path: str,
    metadata_path: str = "",
    session_manager: ApplicationStateManager | None = None,
) -> str:
    """
    Get smart suggestion for input VRAM path using multiple strategies.

    Tries multiple sources in priority order: extraction panel, metadata,
    basename patterns, session data, and last injection settings.

    Args:
        sprite_path: Path to sprite file
        metadata_path: Optional metadata file path
        session_manager: Optional session manager for session-based strategies

    Returns:
        Suggested VRAM path or empty string if none found
    """
    return find_vram_path(
        sprite_path=sprite_path,
        metadata_path=metadata_path,
        strip_editor_suffixes=False,
        session_manager=session_manager,
    )


def find_suggested_input_vram(
    sprite_path: str,
    metadata: Mapping[str, object] | None = None,
    suggested_vram: str = "",
    session_manager: ApplicationStateManager | None = None,
) -> str:
    """
    Find the best suggestion for input VRAM path.

    Args:
        sprite_path: Path to sprite file
        metadata: Loaded metadata dict (from load_metadata)
        suggested_vram: Pre-suggested VRAM path
        session_manager: Optional session manager for session-based strategies

    Returns:
        Suggested VRAM path or empty string if none found
    """
    return find_vram_path(
        sprite_path=sprite_path,
        metadata=metadata,
        pre_suggested=suggested_vram,
        strip_editor_suffixes=True,
        session_manager=session_manager,
    )


def suggest_output_path(
    input_path: str,
    suffix: str,
    extension: str | None = None,
    preserve_parent: bool = False,
) -> str:
    """
    Generic output path suggestion with smart numbering.

    Args:
        input_path: Input file path
        suffix: Suffix to add (e.g., "_injected", "_modified")
        extension: Override extension (e.g., ".dmp") or None to preserve original
        preserve_parent: Whether to keep file in same directory as input

    Returns:
        Suggested non-existent output path
    """
    path = Path(input_path)
    base = path.stem.removesuffix(suffix)
    ext = extension if extension else path.suffix
    parent = path.parent if preserve_parent else Path()

    # Try base name with suffix
    suggested = parent / f"{base}{suffix}{ext}"
    if not suggested.exists():
        return str(suggested)

    # Try numbered variations
    for counter in range(2, 11):
        suggested = parent / f"{base}{suffix}{counter}{ext}"
        if not suggested.exists():
            return str(suggested)

    # Fall back to timestamp
    timestamp = int(time.time())
    return str(parent / f"{base}{suffix}_{timestamp}{ext}")


def suggest_output_vram_path(input_vram_path: str) -> str:
    """
    Suggest output VRAM path based on input path with smart numbering.

    Args:
        input_vram_path: Input VRAM file path

    Returns:
        Suggested output path
    """
    return suggest_output_path(input_vram_path, "_injected", ".dmp")


def suggest_output_rom_path(input_rom_path: str) -> str:
    """
    Suggest output ROM path based on input path with smart numbering.

    Args:
        input_rom_path: Input ROM file path

    Returns:
        Suggested output path (in same directory as input)
    """
    return suggest_output_path(input_rom_path, "_modified", None, preserve_parent=True)


# Type alias for session manager getter callable
SessionManagerGetter = "Callable[[], ApplicationStateManager | None] | None"


# DEPRECATED: Backward compatibility alias
# Remove after all callers migrate to direct function imports
class PathSuggestionService:
    """
    DEPRECATED: Use module-level functions instead.

    This class is kept for backward compatibility only.
    All methods delegate to the module-level functions.
    """

    def __init__(
        self,
        session_manager_getter: Callable[[], ApplicationStateManager | None] | None = None,
    ) -> None:
        self._session_manager: ApplicationStateManager | None = None
        # If getter is provided, call it once to get the session manager
        if session_manager_getter is not None:
            self._session_manager = session_manager_getter()

    def set_session_manager_getter(
        self, getter: Callable[[], ApplicationStateManager | None]
    ) -> None:
        """DEPRECATED: Set session manager directly instead."""
        self._session_manager = getter()

    def validate_path(self, path: str | None) -> str:
        return validate_path(path)

    def find_vram_path(
        self,
        sprite_path: str,
        metadata_path: str = "",
        metadata: Mapping[str, object] | None = None,
        pre_suggested: str = "",
        strip_editor_suffixes: bool = False,
    ) -> str:
        return find_vram_path(
            sprite_path=sprite_path,
            metadata_path=metadata_path,
            metadata=metadata,
            pre_suggested=pre_suggested,
            strip_editor_suffixes=strip_editor_suffixes,
            session_manager=self._session_manager,
        )

    def get_smart_vram_suggestion(
        self, sprite_path: str, metadata_path: str = ""
    ) -> str:
        return get_smart_vram_suggestion(
            sprite_path=sprite_path,
            metadata_path=metadata_path,
            session_manager=self._session_manager,
        )

    def find_suggested_input_vram(
        self,
        sprite_path: str,
        metadata: Mapping[str, object] | None = None,
        suggested_vram: str = "",
    ) -> str:
        return find_suggested_input_vram(
            sprite_path=sprite_path,
            metadata=metadata,
            suggested_vram=suggested_vram,
            session_manager=self._session_manager,
        )

    def suggest_output_path(
        self,
        input_path: str,
        suffix: str,
        extension: str | None = None,
        preserve_parent: bool = False,
    ) -> str:
        return suggest_output_path(
            input_path=input_path,
            suffix=suffix,
            extension=extension,
            preserve_parent=preserve_parent,
        )

    def suggest_output_vram_path(self, input_vram_path: str) -> str:
        return suggest_output_vram_path(input_vram_path)

    def suggest_output_rom_path(self, input_rom_path: str) -> str:
        return suggest_output_rom_path(input_rom_path)
