"""
Path suggestion service for VRAM and ROM files.

Provides smart path suggestions for injection workflows by using multiple
strategies: metadata, session data, basename patterns, and saved settings.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from utils.constants import (
    SETTINGS_KEY_LAST_INPUT_VRAM,
    SETTINGS_NS_ROM_INJECTION,
    SETTINGS_NS_SESSION,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from core.protocols.manager_protocols import ApplicationStateManagerProtocol


logger = logging.getLogger(__name__)


class PathSuggestionService:
    """
    Service for suggesting file paths in injection workflows.

    Uses multiple strategies in priority order to find the best path
    suggestions for VRAM and ROM files.
    """

    # VRAM filename patterns to check (in order of specificity)
    VRAM_PATTERNS = [
        "{base}.dmp",
        "{base}_VRAM.dmp",
        "{base}.VRAM.dmp",
        "{base}.vram",
        "{base}.SnesVideoRam.dmp",
        "{base}.VideoRam.dmp",
        "VRAM.dmp",
        "vram.dmp",
    ]

    # Editor suffixes to strip when matching
    EDITOR_SUFFIXES = ["_sprites_editor", "_sprites", "_editor", "Edited"]

    def __init__(
        self,
        session_manager_getter: Callable[[], ApplicationStateManagerProtocol | None] | None = None,
    ) -> None:
        """
        Initialize the path suggestion service.

        Args:
            session_manager_getter: Optional callable that returns the session manager.
                                   If not provided, session-based strategies are skipped.
                                   Using a callable allows lazy evaluation to support
                                   mocking scenarios in tests.
        """
        self._session_manager_getter = session_manager_getter
        self._logger = logging.getLogger(__name__)

    def set_session_manager_getter(
        self, getter: Callable[[], ApplicationStateManagerProtocol | None]
    ) -> None:
        """Set the session manager getter for session-based strategies."""
        self._session_manager_getter = getter

    def _get_session_manager(self) -> ApplicationStateManagerProtocol | None:
        """Get the session manager lazily via the getter."""
        if self._session_manager_getter:
            return self._session_manager_getter()
        return None

    def validate_path(self, path: str | None) -> str:
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
        self,
        sprite_path: str,
        metadata_path: str = "",
        metadata: Mapping[str, object] | None = None,
        pre_suggested: str = "",
        strip_editor_suffixes: bool = False,
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

        Returns:
            Suggested VRAM path or empty string if none found
        """
        # Strategy 1: Pre-suggested path
        if result := self.validate_path(pre_suggested):
            return result

        # Get session manager lazily
        session_manager = self._get_session_manager()

        # Strategy 2: Session manager vram_path
        if session_manager:
            try:
                session_vram = cast(
                    str, session_manager.get(SETTINGS_NS_SESSION, "vram_path", "")
                )
                if result := self.validate_path(session_vram):
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
            if result := self.validate_path(
                cast(str, loaded_metadata.get("source_vram", ""))
            ):
                return result
            # Check extraction.vram_source (relative path)
            extraction = loaded_metadata.get("extraction")
            if isinstance(extraction, dict):
                vram_source = cast(str, extraction.get("vram_source", ""))
                if vram_source and sprite_path:
                    sprite_dir = Path(sprite_path).parent
                    if result := self.validate_path(str(sprite_dir / vram_source)):
                        return result

        # Strategy 4: Basename pattern matching
        if sprite_path:
            sprite_path_obj = Path(sprite_path)
            sprite_dir = sprite_path_obj.parent
            base_name = sprite_path_obj.stem

            if strip_editor_suffixes:
                for suffix in self.EDITOR_SUFFIXES:
                    if base_name.endswith(suffix):
                        base_name = base_name[: -len(suffix)]
                        break

            for pattern in self.VRAM_PATTERNS:
                filename = pattern.format(base=base_name)
                if result := self.validate_path(str(sprite_dir / filename)):
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
                if result := self.validate_path(last_vram):
                    return result
            except (OSError, ValueError, TypeError):
                pass

        self._logger.debug("No VRAM suggestion found")
        return ""

    def get_smart_vram_suggestion(
        self, sprite_path: str, metadata_path: str = ""
    ) -> str:
        """
        Get smart suggestion for input VRAM path using multiple strategies.

        Tries multiple sources in priority order: extraction panel, metadata,
        basename patterns, session data, and last injection settings.

        Args:
            sprite_path: Path to sprite file
            metadata_path: Optional metadata file path

        Returns:
            Suggested VRAM path or empty string if none found
        """
        return self.find_vram_path(
            sprite_path=sprite_path,
            metadata_path=metadata_path,
            strip_editor_suffixes=False,
        )

    def find_suggested_input_vram(
        self,
        sprite_path: str,
        metadata: Mapping[str, object] | None = None,
        suggested_vram: str = "",
    ) -> str:
        """
        Find the best suggestion for input VRAM path.

        Args:
            sprite_path: Path to sprite file
            metadata: Loaded metadata dict (from load_metadata)
            suggested_vram: Pre-suggested VRAM path

        Returns:
            Suggested VRAM path or empty string if none found
        """
        return self.find_vram_path(
            sprite_path=sprite_path,
            metadata=metadata,
            pre_suggested=suggested_vram,
            strip_editor_suffixes=True,
        )

    def suggest_output_path(
        self,
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

    def suggest_output_vram_path(self, input_vram_path: str) -> str:
        """
        Suggest output VRAM path based on input path with smart numbering.

        Args:
            input_vram_path: Input VRAM file path

        Returns:
            Suggested output path
        """
        return self.suggest_output_path(input_vram_path, "_injected", ".dmp")

    def suggest_output_rom_path(self, input_rom_path: str) -> str:
        """
        Suggest output ROM path based on input path with smart numbering.

        Args:
            input_rom_path: Input ROM file path

        Returns:
            Suggested output path (in same directory as input)
        """
        return self.suggest_output_path(
            input_rom_path, "_modified", None, preserve_parent=True
        )
