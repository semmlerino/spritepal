"""
Validation mixins for manager classes.

Provides shared validation logic used by both consolidated managers
(CoreOperationsManager) and deprecated managers (ExtractionManager,
InjectionManager) to avoid code duplication.
"""

from __future__ import annotations

from typing import Any

from utils.file_validator import FileValidator

from .exceptions import ValidationError


class ExtractionValidationMixin:
    """Mixin providing extraction parameter validation.

    Requires the class to inherit from BaseManager (for _validate_* helpers).
    """

    # Type stubs for mixin - assumes BaseManager methods are available via MRO
    _validate_required: Any
    _validate_type: Any
    _validate_range: Any
    _validate_rom_file_exists: Any

    def validate_extraction_params(self, params: dict[str, Any]) -> bool:
        """
        Validate extraction parameters.

        Args:
            params: Parameters to validate

        Returns:
            True if validation passes

        Raises:
            ValidationError: If validation fails
        """
        # Determine extraction type
        if "vram_path" in params:
            # VRAM extraction - check for missing VRAM file specifically
            if not params.get("vram_path"):
                raise ValidationError("VRAM file is required for extraction")
            self._validate_required(params, ["output_base"])
        elif "rom_path" in params:
            # ROM extraction
            self._validate_required(params, ["rom_path", "offset", "output_base"])
            self._validate_rom_file_exists(params["rom_path"])
            self._validate_type(params["offset"], "offset", int)
            self._validate_range(params["offset"], "offset", min_val=0)
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
        output_base = params.get("output_base", "")
        if not output_base or not output_base.strip():
            raise ValidationError("Output name is required for extraction")

        return True


class InjectionValidationMixin:
    """Mixin providing injection parameter validation.

    Requires the class to inherit from BaseManager (for _validate_* helpers).
    """

    # Type stubs for mixin - assumes BaseManager methods are available via MRO
    _validate_required: Any
    _validate_type: Any
    _validate_range: Any

    def validate_injection_params(self, params: dict[str, Any]) -> None:
        """
        Validate injection parameters.

        Args:
            params: Parameters to validate

        Raises:
            ValidationError: If parameters are invalid
        """
        # Check required common parameters
        required = ["mode", "sprite_path", "offset"]
        self._validate_required(params, required)

        self._validate_type(params["mode"], "mode", str)
        self._validate_type(params["sprite_path"], "sprite_path", str)
        self._validate_type(params["offset"], "offset", int)

        # Use FileValidator for sprite file validation
        sprite_result = FileValidator.validate_image_file(params["sprite_path"])
        if not sprite_result.is_valid:
            raise ValidationError(
                f"Sprite file validation failed: {sprite_result.error_message}"
            )

        self._validate_range(params["offset"], "offset", min_val=0)

        # Check mode-specific parameters
        if params["mode"] == "vram":
            vram_required = ["input_vram", "output_vram"]
            self._validate_required(params, vram_required)

            vram_result = FileValidator.validate_vram_file(params["input_vram"])
            if not vram_result.is_valid:
                raise ValidationError(
                    f"Input VRAM file validation failed: {vram_result.error_message}"
                )

        elif params["mode"] == "rom":
            rom_required = ["input_rom", "output_rom"]
            self._validate_required(params, rom_required)

            rom_result = FileValidator.validate_rom_file(params["input_rom"])
            if not rom_result.is_valid:
                raise ValidationError(
                    f"Input ROM file validation failed: {rom_result.error_message}"
                )

            # Validate optional fast_compression parameter
            if "fast_compression" in params:
                self._validate_type(
                    params["fast_compression"], "fast_compression", bool
                )
        else:
            raise ValidationError(f"Invalid injection mode: {params['mode']}")

        # Validate optional metadata_path
        if params.get("metadata_path"):
            metadata_result = FileValidator.validate_json_file(params["metadata_path"])
            if not metadata_result.is_valid:
                raise ValidationError(
                    f"Metadata file validation failed: {metadata_result.error_message}"
                )
