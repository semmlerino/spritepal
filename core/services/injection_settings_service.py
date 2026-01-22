"""
Injection settings management services.

Provides pure functions for saving, loading, and restoring ROM injection
settings from session storage. These functions are stateless and receive
dependencies as parameters.

This module follows the pattern established by path_suggestion_service.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from core.services.path_suggestion_service import suggest_output_rom_path
from utils.constants import (
    SETTINGS_KEY_FAST_COMPRESSION,
    SETTINGS_KEY_LAST_CUSTOM_OFFSET,
    SETTINGS_KEY_LAST_INPUT_ROM,
    SETTINGS_KEY_LAST_SPRITE_LOCATION,
    SETTINGS_NS_ROM_INJECTION,
    VRAM_TO_ROM_MAPPING,
)

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager

logger = logging.getLogger(__name__)


def convert_vram_to_rom_offset(vram_offset_str: str | int) -> int | None:
    """
    Convert VRAM offset to ROM offset based on known mappings.

    The SNES PPU loads sprite tiles from VRAM, but the actual graphics data
    lives in ROM at different addresses. This mapping is game-specific.
    See VRAM_TO_ROM_MAPPING in utils/constants.py for known mappings.

    Args:
        vram_offset_str: VRAM offset as string (e.g., "0xC000") or int

    Returns:
        ROM offset as integer, or None if no mapping found
    """
    try:
        if isinstance(vram_offset_str, str):
            vram_offset = int(vram_offset_str, 16)
        else:
            vram_offset = vram_offset_str

        # Use the documented VRAM->ROM mapping from constants
        return VRAM_TO_ROM_MAPPING.get(vram_offset)

    except (ValueError, TypeError):
        return None


def save_rom_injection_settings(
    session_manager: ApplicationStateManager,
    input_rom: str,
    sprite_location_text: str,
    custom_offset: str,
    fast_compression: bool,
) -> bool:
    """
    Save ROM injection parameters to settings for future use.

    This is a pure function that persists settings. Returns success status
    instead of raising exceptions.

    Args:
        session_manager: Session manager for settings persistence
        input_rom: Input ROM path
        sprite_location_text: Selected sprite location text from combo box
        custom_offset: Custom offset text if used
        fast_compression: Fast compression checkbox state

    Returns:
        True if settings were saved successfully, False otherwise
    """
    try:
        if input_rom:
            session_manager.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, input_rom)

        if sprite_location_text and sprite_location_text != "Select sprite location...":
            session_manager.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_SPRITE_LOCATION, sprite_location_text)

        if custom_offset:
            session_manager.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_CUSTOM_OFFSET, custom_offset)

        session_manager.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION, fast_compression)

        session_manager.save_session()
        return True

    except Exception as e:
        logger.exception(f"Failed to save ROM injection parameters: {e}")
        return False


def load_rom_injection_defaults(
    session_manager: ApplicationStateManager,
    sprite_path: str,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """
    Load ROM injection defaults from metadata or saved settings.

    This is a pure function that loads settings and metadata.

    Args:
        session_manager: Session manager for settings lookup
        sprite_path: Path to sprite file
        metadata: Loaded metadata dict (from load_metadata)

    Returns:
        Dict containing:
        - input_rom: Path to input ROM or empty string
        - output_rom: Suggested output ROM path or empty string
        - rom_offset: ROM offset as int or None
        - sprite_location_index: Index in sprite list or None
        - custom_offset: Custom offset string
        - fast_compression: Boolean
        - offset_parse_error: String if offset parsing failed (optional)
    """
    result: dict[str, object] = {
        "input_rom": "",
        "output_rom": "",
        "rom_offset": None,
        "sprite_location_index": None,
        "custom_offset": "",
        "fast_compression": False,
    }

    # Try to load from metadata first (has priority)
    if metadata and metadata.get("rom_extraction_info"):
        rom_info = metadata["rom_extraction_info"]
        if isinstance(rom_info, dict):
            rom_source = cast(str, rom_info.get("rom_source", ""))
            rom_offset_str = cast(str, rom_info.get("rom_offset", "0x0"))

            if rom_source and sprite_path:
                sprite_dir = Path(sprite_path).parent
                possible_rom_path = Path(sprite_dir) / rom_source
                if possible_rom_path.exists():
                    result["input_rom"] = str(possible_rom_path)
                    result["output_rom"] = suggest_output_rom_path(str(possible_rom_path))

                    try:
                        if rom_offset_str.startswith(("0x", "0X")):
                            result["rom_offset"] = int(rom_offset_str, 16)
                        else:
                            result["rom_offset"] = int(rom_offset_str, 16)
                        result["custom_offset"] = rom_offset_str
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse ROM offset '{rom_offset_str}': {e}")
                        result["offset_parse_error"] = str(e)

                    return result

    # Fall back to saved settings
    last_input_rom = cast(str, session_manager.get(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, ""))
    if last_input_rom and Path(last_input_rom).exists():
        result["input_rom"] = last_input_rom
        result["output_rom"] = suggest_output_rom_path(last_input_rom)

    result["custom_offset"] = session_manager.get(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_CUSTOM_OFFSET, "")

    result["fast_compression"] = session_manager.get(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION, False)

    return result


def restore_saved_sprite_location(
    session_manager: ApplicationStateManager,
    extraction_vram_offset: str | None,
    sprite_locations: dict[str, int],
) -> dict[str, object]:
    """
    Restore saved sprite location selection.

    This is a pure function that determines which sprite location should be
    selected based on extraction metadata or saved settings.

    Args:
        session_manager: Session manager for settings lookup
        extraction_vram_offset: VRAM offset from extraction metadata
        sprite_locations: Dict of sprite name -> offset from loaded ROM

    Returns:
        Dict containing:
        - sprite_location_name: Name of sprite location or None
        - sprite_location_index: 1-based index in sprite list or None
        - custom_offset: Custom offset string if no match found
    """
    result: dict[str, object] = {"sprite_location_name": None, "sprite_location_index": None, "custom_offset": ""}

    # Try to match extraction VRAM offset to a known sprite location
    if extraction_vram_offset:
        rom_offset = convert_vram_to_rom_offset(extraction_vram_offset)
        if rom_offset is not None:
            for i, (name, offset) in enumerate(sprite_locations.items(), 1):
                if offset == rom_offset:
                    result["sprite_location_name"] = name
                    result["sprite_location_index"] = i
                    return result
            # No match found - use as custom offset
            result["custom_offset"] = f"0x{rom_offset:X}"
            return result

    # Fall back to last saved sprite location
    last_sprite_location = cast(
        str, session_manager.get(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_SPRITE_LOCATION, "")
    )
    if last_sprite_location:
        # Strip offset suffix if present (e.g., "Waddle Dee (0x12345)" -> "Waddle Dee")
        saved_display_name = (
            last_sprite_location.split(" (0x")[0] if " (0x" in last_sprite_location else last_sprite_location
        )

        for i, name in enumerate(sprite_locations.keys(), 1):
            if name == saved_display_name:
                result["sprite_location_name"] = name
                result["sprite_location_index"] = i
                break

    return result
