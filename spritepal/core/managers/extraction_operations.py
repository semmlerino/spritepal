"""
Extraction Operations Manager.

Handles ROM and VRAM extraction operations, preview generation,
and extraction validation. This is a focused sub-manager delegated
from CoreOperationsManager.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from PIL import Image
from PySide6.QtCore import QObject, Signal

from core.exceptions import ExtractionError, ValidationError
from utils.file_validator import FileValidator, ValidationResult
from utils.validation import validate_range, validate_required_params, validate_type

if TYPE_CHECKING:
    from core.palette_manager import PaletteManager
    from core.rom_extractor import ROMExtractor
    from core.services import ROMService, VRAMService
    from core.services.rom_cache import ROMCache


class ExtractionOperationsManager(QObject):
    """
    Manages extraction operations for ROM and VRAM data.

    Responsibilities:
    - ROM extraction (extract_from_rom)
    - VRAM extraction (extract_from_vram)
    - Preview generation
    - Extraction parameter validation
    - Known sprite location queries

    Thread-safe: Operations emit signals for async UI updates.
    """

    # Extraction signals
    extraction_progress = Signal(str)  # progress message
    extraction_warning = Signal(str)  # warning message (partial success)
    preview_generated = Signal(object, int)  # pixmap, offset
    palettes_extracted = Signal(object)  # palette data
    active_palettes_found = Signal(list)  # list of active palette indices
    files_created = Signal(list)  # list of created file paths

    # Cache signals (emitted when loading sprite locations)
    cache_operation_started = Signal(str, str)  # operation, key
    cache_hit = Signal(str, float)  # key, load_time
    cache_miss = Signal(str)  # key
    cache_saved = Signal(str, int)  # key, size_bytes

    def __init__(
        self,
        *,
        rom_extractor: ROMExtractor | None = None,
        palette_manager: PaletteManager | None = None,
        rom_cache: ROMCache | None = None,
        rom_service: ROMService | None = None,
        vram_service: VRAMService | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize extraction operations manager.

        Args:
            rom_extractor: ROM extractor for sprite data
            palette_manager: Palette management component
            rom_cache: Cache for ROM data
            rom_service: Service for ROM extraction operations
            vram_service: Service for VRAM extraction operations
            parent: Qt parent object
        """
        super().__init__(parent)
        self._logger = logging.getLogger(__name__)

        # Store dependencies
        self._rom_extractor = rom_extractor
        self._palette_manager = palette_manager
        self._rom_cache = rom_cache
        self._rom_service = rom_service
        self._vram_service = vram_service

    # ========== Service Accessors ==========

    def _ensure_rom_service(self) -> ROMService:
        """Ensure ROM service is available."""
        if self._rom_service is None:
            raise ExtractionError("ROM service not initialized")
        return self._rom_service

    def _ensure_vram_service(self) -> VRAMService:
        """Ensure VRAM service is available."""
        if self._vram_service is None:
            raise ExtractionError("VRAM service not initialized")
        return self._vram_service

    # ========== Extraction Operations ==========

    def extract_from_vram(
        self,
        vram_path: str,
        output_base: str,
        cgram_path: str | None = None,
        oam_path: str | None = None,
        vram_offset: int | None = None,
        create_grayscale: bool = True,
        create_metadata: bool = True,
        grayscale_mode: bool = False,
    ) -> list[str]:
        """
        Extract sprites from VRAM dump.

        Args:
            vram_path: Path to VRAM dump file
            output_base: Base name for output files (without extension)
            cgram_path: Path to CGRAM dump for palette extraction
            oam_path: Path to OAM dump for palette analysis
            vram_offset: Offset in VRAM (default: 0xC000)
            create_grayscale: Create grayscale palette files
            create_metadata: Create metadata JSON file
            grayscale_mode: Skip palette extraction entirely

        Returns:
            List of created file paths

        Raises:
            ExtractionError: If extraction fails
        """
        vram_service = self._ensure_vram_service()

        result = vram_service.extract_from_vram(
            vram_path=vram_path,
            output_base=output_base,
            cgram_path=cgram_path,
            oam_path=oam_path,
            vram_offset=vram_offset,
            create_grayscale=create_grayscale,
            create_metadata=create_metadata,
            grayscale_mode=grayscale_mode,
            progress_callback=self.extraction_progress.emit,
        )

        # Emit signals from result
        if result.preview_image:
            self.preview_generated.emit(result.preview_image, result.tile_count)
        if result.palettes:
            self.palettes_extracted.emit(result.palettes)
        if result.active_palette_indices:
            self.active_palettes_found.emit(result.active_palette_indices)
        if result.warning:
            self.extraction_warning.emit(result.warning)
        self.files_created.emit(result.files)

        return result.files

    def extract_from_rom(
        self,
        rom_path: str,
        offset: int,
        output_base: str,
        sprite_name: str,
        cgram_path: str | None = None,
    ) -> list[str]:
        """
        Extract sprites from ROM at specific offset.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM to extract from
            output_base: Base name for output files
            sprite_name: Name of the sprite being extracted
            cgram_path: CGRAM dump for palette extraction

        Returns:
            List of created file paths

        Raises:
            ExtractionError: If extraction fails
        """
        rom_service = self._ensure_rom_service()

        result = rom_service.extract_from_rom(
            rom_path=rom_path,
            offset=offset,
            output_base=output_base,
            sprite_name=sprite_name,
            cgram_path=cgram_path,
            progress_callback=self.extraction_progress.emit,
        )

        # Emit signals from result
        if result.preview_image:
            self.preview_generated.emit(result.preview_image, result.tile_count)
        if result.palettes:
            self.palettes_extracted.emit(result.palettes)
        if result.active_palette_indices:
            self.active_palettes_found.emit(result.active_palette_indices)
        if result.warning:
            self.extraction_warning.emit(result.warning)
        self.files_created.emit(result.files)

        return result.files

    def get_sprite_preview(self, rom_path: str, offset: int, sprite_name: str | None = None) -> tuple[bytes, int, int]:
        """
        Get a preview of sprite data from ROM without saving files.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM
            sprite_name: Sprite name for logging

        Returns:
            Tuple of (tile_data, width, height)

        Raises:
            ExtractionError: If preview generation fails
        """
        rom_service = self._ensure_rom_service()
        result = rom_service.get_sprite_preview(rom_path, offset, sprite_name)
        return result.tile_data, result.width, result.height

    # ========== Validation ==========

    def validate_extraction_params(self, params: Mapping[str, object]) -> bool:
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
            validate_required_params(params, ["output_base"])
        elif "rom_path" in params:
            # ROM extraction
            validate_required_params(params, ["rom_path", "offset", "output_base"])
            rom_path = cast(str, params["rom_path"])
            FileValidator.validate_rom_file_exists_or_raise(rom_path)
            validate_type(params["offset"], "offset", int)
            offset = cast(int, params["offset"])
            validate_range(offset, "offset", min_val=0)
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

    # ========== Preview Generation ==========

    def generate_preview(self, vram_path: str, offset: int) -> tuple[Image.Image, int]:
        """Generate a preview image from VRAM at the specified offset.

        Args:
            vram_path: Path to VRAM dump file
            offset: Offset in VRAM to start extracting from

        Returns:
            Tuple of (PIL image, tile count)

        Raises:
            ExtractionError: If preview generation fails
        """
        vram_service = self._ensure_vram_service()
        return vram_service.generate_preview(vram_path, offset)

    # ========== ROM Information ==========

    def get_rom_extractor(self) -> ROMExtractor:
        """Get the ROM extractor instance for advanced operations."""
        rom_service = self._ensure_rom_service()
        return rom_service.get_rom_extractor()

    def get_known_sprite_locations(self, rom_path: str) -> dict[str, object]:  # Pointer objects with .offset attribute
        """
        Get known sprite locations for a ROM with caching.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of known sprite locations (values are pointer objects with .offset)

        Raises:
            ExtractionError: If operation fails
        """
        rom_service = self._ensure_rom_service()
        locations, cache_result = rom_service.get_known_sprite_locations(rom_path)

        # Emit cache signals based on result
        self.cache_operation_started.emit("Loading", "sprite_locations")
        if cache_result.hit:
            self.cache_hit.emit("sprite_locations", cache_result.time_saved)
        else:
            self.cache_miss.emit("sprite_locations")
            if cache_result.items_saved > 0:
                self.cache_operation_started.emit("Saving", "sprite_locations")
                self.cache_saved.emit("sprite_locations", cache_result.items_saved)

        return locations

    def read_rom_header(self, rom_path: str) -> dict[str, object]:  # ROM header with title, rom_type, checksum, etc.
        """
        Read ROM header information.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary containing ROM header information

        Raises:
            ExtractionError: If operation fails
        """
        rom_service = self._ensure_rom_service()
        return rom_service.read_rom_header(rom_path)

    # ========== Validation Helpers ==========

    def validate_rom_file(self, rom_path: str) -> ValidationResult:
        """Validate ROM file exists, is readable, and has reasonable size.

        Uses FileValidator for comprehensive validation.

        Returns:
            ValidationResult with is_valid, error_message, warnings, and file_info
        """
        return FileValidator.validate_rom_file(rom_path)

    def validate_extraction_rom_file(self, rom_path: str) -> None:
        """Validate ROM file, raising ValidationError if invalid."""
        result = self.validate_rom_file(rom_path)
        if not result.is_valid:
            raise ValidationError(result.error_message or f"Invalid ROM file: {rom_path}")

    # ========== State Management ==========

    def reset_state(self) -> None:
        """Reset internal state for test isolation."""
        # No mutable state to reset in current implementation
        pass
