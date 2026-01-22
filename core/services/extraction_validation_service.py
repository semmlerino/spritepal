"""
Extraction and injection parameter validation services.

Provides pure validation functions for extraction and injection parameters.
These functions are stateless and raise ValidationError on invalid input.

This module follows the pattern established by path_suggestion_service.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from core.exceptions import ValidationError
from utils.file_validator import FileValidator
from utils.validation import validate_range, validate_required_params, validate_type


def validate_extraction_params(params: Mapping[str, object]) -> bool:
    """
    Validate extraction parameters.

    This is a pure validation function. No side effects, no signals.

    Args:
        params: Parameters to validate. Expected keys depend on extraction type:
            - For VRAM extraction: vram_path, output_base, cgram_path (optional),
              grayscale_mode (optional)
            - For ROM extraction: rom_path, offset (or sprite_offset), output_base

    Returns:
        True if validation passes

    Raises:
        ValidationError: If validation fails with descriptive message
    """
    # Determine extraction type
    if "vram_path" in params:
        # VRAM extraction - check for missing VRAM file specifically
        if not params.get("vram_path"):
            raise ValidationError("VRAM file is required for extraction")
        validate_required_params(params, ["output_base"])
    elif "rom_path" in params:
        # ROM extraction
        if "offset" in params:
            validate_required_params(params, ["rom_path", "offset", "output_base"])
            validate_type(params["offset"], "offset", int)
            offset = cast(int, params["offset"])
            validate_range(offset, "offset", min_val=0)
        elif "sprite_offset" in params:
            validate_required_params(params, ["rom_path", "sprite_offset", "output_base"])
            validate_type(params["sprite_offset"], "sprite_offset", int)
            offset = cast(int, params["sprite_offset"])
            validate_range(offset, "sprite_offset", min_val=0)
        else:
            raise ValidationError("Missing required parameters: offset (or sprite_offset) is required")

        rom_path = cast(str, params["rom_path"])
        FileValidator.validate_rom_file_exists_or_raise(rom_path)

        # Check if offset is within ROM bounds
        from utils.rom_utils import detect_smc_offset_from_size

        rom_size = Path(rom_path).stat().st_size
        header_offset = detect_smc_offset_from_size(rom_size)
        effective_offset = offset + header_offset
        if effective_offset >= rom_size:
            raise ValidationError(
                f"Offset 0x{offset:X} (file offset 0x{effective_offset:X}) exceeds ROM size 0x{rom_size:X}"
            )
    else:
        raise ValidationError("Must provide either vram_path or rom_path")

    # Validate CGRAM requirements for VRAM extraction
    if "vram_path" in params:
        grayscale_mode = params.get("grayscale_mode", False)
        cgram_path = params.get("cgram_path")

        # CGRAM is required for full color mode
        if not grayscale_mode and not cgram_path:
            raise ValidationError(
                "CGRAM file is required for Full Color mode.\n"
                "Please provide a CGRAM file or switch to Grayscale Only mode."
            )

    # Validate output_base is provided and not empty
    output_base = cast(str, params.get("output_base", ""))
    if not output_base or not output_base.strip():
        raise ValidationError("Output name is required for extraction")

    return True


def validate_injection_params(params: Mapping[str, object]) -> None:
    """
    Validate injection parameters.

    This is a pure validation function. No side effects, no signals.

    Args:
        params: Parameters to validate. Expected keys:
            - mode: "vram" or "rom"
            - sprite_path: Path to sprite PNG file
            - offset: Target offset (int >= 0)
            - For VRAM mode: input_vram, output_vram
            - For ROM mode: input_rom, output_rom, fast_compression (optional)
            - Optional: metadata_path

    Raises:
        ValidationError: If parameters are invalid with descriptive message
    """
    # Check required common parameters
    required = ["mode", "sprite_path", "offset"]
    validate_required_params(params, required)

    validate_type(params["mode"], "mode", str)
    validate_type(params["sprite_path"], "sprite_path", str)
    validate_type(params["offset"], "offset", int)

    # Use FileValidator for sprite file validation
    sprite_path = cast(str, params["sprite_path"])
    sprite_result = FileValidator.validate_image_file(sprite_path)
    if not sprite_result.is_valid:
        raise ValidationError(f"Sprite file validation failed: {sprite_result.error_message}")

    # Validate sprite dimensions early (must be multiples of 8)
    from core.injector import SpriteInjector

    injector = SpriteInjector()
    is_valid, error_msg = injector.validate_sprite(sprite_path)
    if not is_valid:
        raise ValidationError(f"Invalid sprite image: {error_msg}")

    offset = cast(int, params["offset"])
    validate_range(offset, "offset", min_val=0)

    # Check mode-specific parameters
    mode = cast(str, params["mode"])
    if mode == "vram":
        vram_required = ["input_vram", "output_vram"]
        validate_required_params(params, vram_required)

        input_vram = cast(str, params["input_vram"])
        vram_result = FileValidator.validate_vram_file(input_vram)
        if not vram_result.is_valid:
            raise ValidationError(f"Input VRAM file validation failed: {vram_result.error_message}")

    elif mode == "rom":
        rom_required = ["input_rom", "output_rom"]
        validate_required_params(params, rom_required)

        input_rom = cast(str, params["input_rom"])
        rom_result = FileValidator.validate_rom_file(input_rom)
        if not rom_result.is_valid:
            raise ValidationError(f"Input ROM file validation failed: {rom_result.error_message}")

        # Validate optional fast_compression parameter
        if "fast_compression" in params:
            validate_type(params["fast_compression"], "fast_compression", bool)
    else:
        raise ValidationError(f"Invalid injection mode: {mode}")

    # Validate optional metadata_path
    metadata_path_val = params.get("metadata_path")
    if metadata_path_val:
        metadata_path = cast(str, metadata_path_val)
        metadata_result = FileValidator.validate_json_file(metadata_path)
        if not metadata_result.is_valid:
            raise ValidationError(f"Metadata file validation failed: {metadata_result.error_message}")
