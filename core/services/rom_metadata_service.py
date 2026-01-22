"""
ROM metadata loading and parsing services.

Provides pure functions for loading and parsing ROM metadata, extraction info,
and ROM header data. These functions are stateless and receive dependencies
as parameters.

This module follows the pattern established by path_suggestion_service.py.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache

logger = logging.getLogger(__name__)


def load_metadata(
    metadata_path: str,
) -> dict[str, object] | None:
    """
    Load and parse metadata file.

    This is a pure function that parses extraction metadata JSON files.
    No side effects, no signals.

    Args:
        metadata_path: Path to metadata JSON file

    Returns:
        Parsed metadata dict with extraction info, or None if loading fails.
        Structure:
        {
            "metadata": <raw parsed JSON>,
            "source_type": "vram" | "rom",
            "extraction": <extraction dict or None>,
            "extraction_vram_offset": <str or None>,
            "rom_extraction_info": <dict or None>,
            "default_vram_offset": "0xC000" (if applicable)
        }
    """
    if not metadata_path or not Path(metadata_path).exists():
        return None

    parsed_info: dict[str, object] | None = None
    metadata: dict[str, object] | None = None

    try:
        with Path(metadata_path).open() as f:
            metadata = cast(dict[str, object], json.load(f))

        if "extraction" in metadata:
            extraction = metadata["extraction"]
            if not isinstance(extraction, dict):
                return None
            source_type = cast(str, extraction.get("source_type", "vram"))

            parsed_info = {"metadata": metadata, "source_type": source_type, "extraction": extraction}

            if source_type == "rom":
                parsed_info["rom_extraction_info"] = {
                    "rom_source": extraction.get("rom_source", ""),
                    "rom_offset": extraction.get("rom_offset", "0x0"),
                    "sprite_name": extraction.get("sprite_name", ""),
                    "tile_count": extraction.get("tile_count", "Unknown"),
                }
                parsed_info["extraction_vram_offset"] = None
                parsed_info["default_vram_offset"] = "0xC000"
            else:
                vram_offset = extraction.get("vram_offset", "0xC000")
                parsed_info["extraction_vram_offset"] = vram_offset
                parsed_info["rom_extraction_info"] = None

    except (OSError, PermissionError) as e:
        logger.warning(f"File I/O error loading metadata from {metadata_path}: {e}")
        return None
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Invalid metadata format in {metadata_path}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to load metadata from {metadata_path}: {e}")
        return None
    else:
        if metadata and "extraction" in metadata and parsed_info:
            return parsed_info
        return {
            "metadata": metadata,
            "source_type": "vram",
            "extraction": None,
            "extraction_vram_offset": None,
            "rom_extraction_info": None,
            "default_vram_offset": "0xC000",
        }


def read_rom_header_dict(
    rom_path: str,
    rom_extractor: ROMExtractor,
) -> dict[str, object]:
    """
    Read ROM header information as a dictionary.

    Pure wrapper around ROMExtractor.read_rom_header that converts
    the dataclass result to a dict.

    Args:
        rom_path: Path to ROM file
        rom_extractor: ROMExtractor instance for reading header

    Returns:
        Dictionary containing ROM header information

    Raises:
        ExtractionError: If operation fails
        OSError: If file cannot be read
        ValueError: If ROM format is invalid
    """
    header = rom_extractor.read_rom_header(rom_path)
    return asdict(header)


def get_sprite_locations_with_cache(
    rom_path: str,
    rom_extractor: ROMExtractor,
    rom_cache: ROMCache,
) -> tuple[dict[str, object], bool, float]:
    """
    Get known sprite locations for a ROM with caching support.

    This function handles cache lookup and storage, returning both the
    locations and cache metadata. Signal emission is left to the caller.

    Args:
        rom_path: Path to ROM file
        rom_extractor: ROMExtractor instance for scanning
        rom_cache: ROMCache instance for caching

    Returns:
        Tuple of:
        - Dictionary of known sprite locations (values are pointer objects with .offset)
        - Boolean indicating if this was a cache hit
        - Time saved by cache hit (0.0 if cache miss)

    Raises:
        ExtractionError: If operation fails
        OSError: If file cannot be read
    """
    import time

    # Try to load from cache first
    start_time = time.time()
    cached_locations = rom_cache.get_sprite_locations(rom_path)

    if cached_locations:
        time_saved = 2.5  # Estimated time saved by not scanning ROM
        logger.debug(f"Loaded sprite locations from cache: {rom_path}")
        return dict(cached_locations), True, time_saved

    # Cache miss - scan ROM file
    logger.debug(f"Cache miss, scanning ROM for sprite locations: {rom_path}")
    locations = rom_extractor.get_known_sprite_locations(rom_path)
    scan_time = time.time() - start_time

    # Save to cache for future use
    if locations:
        cache_success = rom_cache.save_sprite_locations(rom_path, locations)
        if cache_success:
            logger.debug(f"Cached {len(locations)} sprite locations for future use (scan took {scan_time:.1f}s)")

    return dict(locations), False, 0.0


def load_rom_info_dict(
    rom_path: str,
    rom_extractor: ROMExtractor,
    rom_cache: ROMCache,
    header_getter: object = None,  # Callable[[str], dict[str, object]] for read_rom_header
    locations_getter: object = None,  # Callable[[str], dict[str, object]] for get_known_sprite_locations
) -> dict[str, object]:
    """
    Load ROM information and sprite locations.

    This is a pure function that loads ROM info. Callers can provide custom
    getters for header and locations (useful for maintaining signal emission).

    Args:
        rom_path: Path to ROM file
        rom_extractor: ROMExtractor instance
        rom_cache: ROMCache instance
        header_getter: Optional custom function for reading header (defaults to read_rom_header_dict)
        locations_getter: Optional custom function for getting locations

    Returns:
        Dict containing header, sprite_locations, cached flag, or error info
    """
    from utils.file_validator import FileValidator

    def _create_error_result(message: str, error_type: str) -> dict[str, object]:
        return {"error": message, "error_type": error_type}

    try:
        validation_result = FileValidator.validate_rom_file(rom_path)
        if not validation_result.is_valid:
            error_msg = validation_result.error_message or f"Invalid ROM file: {rom_path}"
            return _create_error_result(error_msg, "ValidationError")

        # Try cache first
        cached_info = rom_cache.get_rom_info(rom_path)

        if cached_info:
            logger.debug(f"Loaded ROM info from cache: {rom_path}")
            result_dict = dict(cached_info)
            result_dict["cached"] = True
            return result_dict

        # Cache miss - load from file
        logger.debug(f"Cache miss, loading ROM info from file: {rom_path}")

        # Use provided getter or default
        if header_getter:
            header = cast(dict[str, object], header_getter(rom_path))  # type: ignore[operator]
        else:
            header = read_rom_header_dict(rom_path, rom_extractor)

        result: dict[str, object] = {
            "header": {"title": header["title"], "rom_type": header["rom_type"], "checksum": header["checksum"]},
            "sprite_locations": {},
            "cached": False,
        }

        # Get sprite locations if this is Kirby Super Star
        title = cast(str, header["title"])
        if "KIRBY" in title.upper():
            try:
                logger.info(f"Scanning ROM for sprite locations: {title}")

                if locations_getter:
                    locations = cast(dict[str, object], locations_getter(rom_path))  # type: ignore[operator]
                else:
                    locations, _cache_hit, _time_saved = get_sprite_locations_with_cache(
                        rom_path, rom_extractor, rom_cache
                    )

                sprite_dict: dict[str, int] = {}
                for name, pointer in locations.items():
                    display_name = name.replace("_", " ").title()
                    # Pointer objects have .offset attribute (from ROM analysis)
                    sprite_dict[display_name] = cast(object, pointer).offset  # type: ignore[attr-defined]
                result["sprite_locations"] = sprite_dict

                logger.info(f"Found {len(sprite_dict)} sprite locations")

                rom_cache.save_rom_info(rom_path, result)
                logger.debug(f"Cached ROM info for future use: {rom_path}")

            except Exception as sprite_error:
                logger.warning(f"Failed to load sprite locations: {sprite_error}")
                result["sprite_locations_error"] = str(sprite_error)
        else:
            rom_cache.save_rom_info(rom_path, result)

    except Exception as e:
        logger.exception("Failed to load ROM info")
        return _create_error_result(str(e), type(e).__name__)
    else:
        return result
