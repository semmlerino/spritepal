"""
Manager for handling all extraction operations
"""
from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typing_extensions import override

if TYPE_CHECKING:
    from core.extractor import SpriteExtractor
    from core.palette_manager import PaletteManager
    from core.rom_extractor import ROMExtractor

from PIL import Image
from PySide6.QtCore import QObject, Signal

from core.extractor import SpriteExtractor
from core.palette_manager import PaletteManager
from core.rom_extractor import ROMExtractor
from utils.constants import (
    BYTES_PER_TILE,
    DEFAULT_PREVIEW_HEIGHT,
    DEFAULT_PREVIEW_WIDTH,
    SPRITE_PALETTE_END,
    SPRITE_PALETTE_START,
)
from utils.file_validator import FileValidator
from utils.rom_cache import get_rom_cache

from .base_manager import BaseManager
from .exceptions import ExtractionError, ValidationError


class ExtractionManager(BaseManager):
    """Manages all extraction workflows (VRAM and ROM)"""

    # Additional signals specific to extraction
    extraction_progress = Signal(str)  # Progress message
    extraction_warning = Signal(str)  # Warning message (partial success)
    preview_generated = Signal(object, int)  # PIL Image, tile count
    palettes_extracted = Signal(dict)  # Palette data
    active_palettes_found = Signal(list)  # Active palette indices
    files_created = Signal(list)  # List of created files
    cache_operation_started = Signal(str, str)  # Operation type, cache type
    cache_hit = Signal(str, float)  # Cache type, time saved in seconds
    cache_miss = Signal(str)  # Cache type
    cache_saved = Signal(str, int)  # Cache type, number of items saved

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the extraction manager"""
        # Declare instance variables with type hints
        self._sprite_extractor: SpriteExtractor | None = None
        self._rom_extractor: ROMExtractor | None = None
        self._palette_manager: PaletteManager | None = None

        super().__init__("ExtractionManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize extraction components"""
        self._sprite_extractor = SpriteExtractor()
        self._rom_extractor = ROMExtractor()
        self._palette_manager = PaletteManager()
        self._is_initialized = True
        self._logger.info("ExtractionManager initialized")

    @override
    def cleanup(self) -> None:
        """Cleanup extraction resources"""
        # Clear any active operations to prevent "already active" warnings
        with self._lock:
            self._active_operations.clear()
        # Currently no other resources to cleanup

    def reset_state(self, full_reset: bool = False) -> None:
        """Reset internal state for test isolation.

        This method clears any mutable state that could leak between tests
        when the manager is used in class-scoped fixtures.

        Args:
            full_reset: If True, also clears long-lived components (sprite_extractor,
                       rom_extractor, palette_manager). They will be recreated on
                       next use. Use for tests requiring complete isolation.
                       Default is False for performance (these are stateless).
        """
        with self._lock:
            self._active_operations.clear()
            if full_reset:
                # Clear long-lived components - they'll be recreated via _initialize()
                self._sprite_extractor = None
                self._rom_extractor = None
                self._palette_manager = None
                self._is_initialized = False
                self._logger.debug("ExtractionManager full reset: cleared all components")

    def _ensure_sprite_extractor(self) -> SpriteExtractor:
        """Ensure sprite extractor is initialized and return it."""
        if self._sprite_extractor is None:
            raise ExtractionError("ExtractionManager not properly initialized - sprite extractor is None")
        return self._sprite_extractor

    def _ensure_rom_extractor(self) -> ROMExtractor:
        """Ensure ROM extractor is initialized and return it."""
        if self._rom_extractor is None:
            raise ExtractionError("ExtractionManager not properly initialized - ROM extractor is None")
        return self._rom_extractor

    def _ensure_palette_manager(self) -> PaletteManager:
        """Ensure palette manager is initialized and return it."""
        if self._palette_manager is None:
            raise ExtractionError("ExtractionManager not properly initialized - palette manager is None")
        return self._palette_manager

    def extract_from_vram(self, vram_path: str, output_base: str,
                         cgram_path: str | None = None,
                         oam_path: str | None = None,
                         vram_offset: int | None = None,
                         create_grayscale: bool = True,
                         create_metadata: bool = True,
                         grayscale_mode: bool = False) -> list[str]:
        """
        Extract sprites from VRAM dump

        Args:
            vram_path: Path to VRAM dump file
            output_base: Base name for output files (without extension)
            cgram_path: path to CGRAM dump for palette extraction
            oam_path: path to OAM dump for palette analysis
            vram_offset: offset in VRAM (default: 0xC000)
            create_grayscale: Create grayscale palette files
            create_metadata: Create metadata JSON file
            grayscale_mode: Skip palette extraction entirely

        Returns:
            List of created file paths

        Raises:
            ExtractionError: If extraction fails
            ValidationError: If parameters are invalid
        """
        operation = "vram_extraction"

        # Validate parameters
        try:
            self._validate_required({"vram_path": vram_path, "output_base": output_base},
                                   ["vram_path", "output_base"])

            # Use FileValidator for comprehensive file validation
            self._validate_vram_file(vram_path)

            if cgram_path:
                self._validate_cgram_file(cgram_path)

            if oam_path:
                self._validate_oam_file(oam_path)
        except ValidationError as e:
            self._handle_error(e, operation)
            raise

        if not self._start_operation(operation):
            raise ExtractionError("VRAM extraction already in progress")

        try:
            extracted_files = []
            palette_extraction_failed = False
            palette_error_msg = ""

            # Extract sprites
            self._update_progress(operation, 0, 100)
            self.extraction_progress.emit("Extracting sprites from VRAM...")

            output_file = f"{output_base}.png"
            img, num_tiles = self._ensure_sprite_extractor().extract_sprites_grayscale(
                vram_path, output_file, offset=vram_offset
            )
            extracted_files.append(output_file)

            # Generate preview
            self._update_progress(operation, 25, 100)
            self.extraction_progress.emit("Creating preview...")
            self.preview_generated.emit(img, num_tiles)

            # Extract palettes if requested - catch errors for partial success
            if not grayscale_mode and cgram_path:
                self._update_progress(operation, 50, 100)
                try:
                    extracted_files.extend(
                        self._extract_palettes(
                            cgram_path, output_base, output_file,
                            oam_path, vram_path, vram_offset,
                            num_tiles, create_grayscale, create_metadata
                        )
                    )
                except Exception as e:
                    # Log and track palette failure but don't fail sprite extraction
                    palette_extraction_failed = True
                    palette_error_msg = str(e)
                    self._logger.warning(f"Palette extraction failed: {e}")

            self._update_progress(operation, 100, 100)

            # Emit appropriate completion message
            if palette_extraction_failed:
                self.extraction_warning.emit(
                    f"Sprites extracted but palette extraction failed: {palette_error_msg}"
                )
                self.extraction_progress.emit("Extraction complete (palettes failed)")
            else:
                self.extraction_progress.emit("Extraction complete!")

            self.files_created.emit(extracted_files)

        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, operation, "VRAM extraction")
            raise
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, operation, "VRAM extraction")
            raise
        except Exception as e:
            self._handle_operation_error(e, operation, ExtractionError, "VRAM extraction")
            raise
        else:
            return extracted_files
        finally:
            self._finish_operation(operation)

    def extract_from_rom(self, rom_path: str, offset: int,
                        output_base: str, sprite_name: str,
                        cgram_path: str | None = None) -> list[str]:
        """
        Extract sprites from ROM at specific offset

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
            ValidationError: If parameters are invalid
        """
        operation = "rom_extraction"

        # Validate parameters
        try:
            params = {
                "rom_path": rom_path,
                "offset": offset,
                "output_base": output_base,
                "sprite_name": sprite_name
            }
            self._validate_required(params, list(params.keys()))

            # Use FileValidator for comprehensive ROM file validation
            self._validate_rom_file(rom_path)

            self._validate_type(offset, "offset", int)
            self._validate_range(offset, "offset", min_val=0)

            if cgram_path:
                self._validate_cgram_file(cgram_path)
        except ValidationError as e:
            self._handle_error(e, operation)
            raise

        if not self._start_operation(operation):
            raise ExtractionError("ROM extraction already in progress")

        try:
            extracted_files = []
            palette_extraction_failed = False
            palette_error_msg = ""

            # Extract from ROM
            self._update_progress(operation, 0, 100)
            self.extraction_progress.emit(f"Extracting {sprite_name} from ROM...")

            output_file = f"{output_base}.png"
            result = self._ensure_rom_extractor().extract_sprite_from_rom(
                rom_path, offset, output_file
            )

            if result:
                # Create PIL image for preview using context manager to prevent resource leak
                with Image.open(output_file) as img:
                    tile_count = (img.width * img.height) // (8 * 8)
                    # Copy image data before context exits (signal receiver needs valid data)
                    img_copy = img.copy()

                extracted_files.append(output_file)
                self.preview_generated.emit(img_copy, tile_count)

                # Extract palettes if CGRAM provided - catch errors for partial success
                if cgram_path:
                    self._update_progress(operation, 50, 100)
                    try:
                        extracted_files.extend(
                            self._extract_palettes(
                                cgram_path, output_base, output_file,
                                None, rom_path, offset,
                                tile_count, True, True
                            )
                        )
                    except Exception as e:
                        # Log and track palette failure but don't fail sprite extraction
                        palette_extraction_failed = True
                        palette_error_msg = str(e)
                        self._logger.warning(f"Palette extraction failed: {e}")
            else:
                self._raise_extraction_failed("Failed to extract sprite from ROM")

            # Only emit success signals if extraction actually succeeded
            self._update_progress(operation, 100, 100)

            # Emit appropriate completion message
            if palette_extraction_failed:
                self.extraction_warning.emit(
                    f"Sprite extracted but palette extraction failed: {palette_error_msg}"
                )
                self.extraction_progress.emit("ROM extraction complete (palettes failed)")
            else:
                self.extraction_progress.emit("ROM extraction complete!")

            self.files_created.emit(extracted_files)

        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, operation, "ROM extraction")
            raise
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, operation, "ROM extraction")
            raise
        except Exception as e:
            if not isinstance(e, ExtractionError):
                self._handle_operation_error(e, operation, ExtractionError, "ROM extraction")
            else:
                self._handle_error(e, operation)
            raise
        else:
            return extracted_files
        finally:
            self._finish_operation(operation)

    def get_sprite_preview(self, rom_path: str, offset: int,
                          sprite_name: str | None = None) -> tuple[bytes, int, int]:
        """
        Get a preview of sprite data from ROM without saving files

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM
            sprite_name: sprite name for logging

        Returns:
            Tuple of (tile_data, width, height)

        Raises:
            ExtractionError: If preview generation fails
        """
        operation = "sprite_preview"

        try:
            # Use FileValidator for ROM file validation
            self._validate_rom_file_exists(rom_path)

            self._validate_type(offset, "offset", int)
            self._validate_range(offset, "offset", min_val=0)
        except ValidationError as e:
            self._handle_error(e, operation)
            raise

        started = self._start_operation(operation)
        if not started:
            # Allow multiple preview operations
            self._logger.debug("Preview operation already running, allowing concurrent preview")

        try:
            name = sprite_name or f"offset_0x{offset:X}"
            self._logger.debug(f"Generating preview for {name} at offset 0x{offset:X}")

            # Calculate preview dimensions and expected data size
            width = DEFAULT_PREVIEW_WIDTH
            height = DEFAULT_PREVIEW_HEIGHT
            tile_count = (width * height) // (8 * 8)
            expected_bytes = tile_count * BYTES_PER_TILE

            # Validate offset against ROM size BEFORE reading
            rom_size = Path(rom_path).stat().st_size
            if offset >= rom_size:
                raise ValueError(
                    f"Offset 0x{offset:X} exceeds ROM size 0x{rom_size:X}"
                )

            available_bytes = rom_size - offset
            if expected_bytes > available_bytes:
                raise ValueError(
                    f"Insufficient data at offset 0x{offset:X}: "
                    f"need {expected_bytes} bytes, only {available_bytes} available"
                )

            # Read raw data from ROM with validation
            with Path(rom_path).open("rb") as f:
                f.seek(offset)
                # 4bpp = 32 bytes per tile
                tile_data = f.read(expected_bytes)

                # Verify we got the expected amount of data
                if len(tile_data) != expected_bytes:
                    raise OSError(
                        f"Incomplete read at offset 0x{offset:X}: "
                        f"got {len(tile_data)}/{expected_bytes} bytes"
                    )

        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, operation, "preview generation")
            raise
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, operation, "preview generation")
            raise
        except Exception as e:
            self._handle_operation_error(e, operation, ExtractionError, "preview generation")
            raise
        else:
            return tile_data, width, height
        finally:
            if started:
                self._finish_operation(operation)

    def validate_extraction_params(self, params: dict[str, Any]) -> bool:
        """
        Validate extraction parameters

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

            # Use FileValidator for ROM file validation
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

            # Note: File existence validation is now handled by controller
            # to provide better fail-fast behavior and avoid blocking I/O

        # Validate output_base is provided and not empty
        output_base = params.get("output_base", "")
        if not output_base or not output_base.strip():
            raise ValidationError("Output name is required for extraction")

        # Note: Optional file existence validation is now handled by controller

        # Return True if all validation passes
        return True

    def _extract_palettes(self, cgram_path: str, output_base: str,
                         png_file: str, oam_path: str | None,
                         source_path: str, source_offset: int | None,
                         num_tiles: int, create_grayscale: bool,
                         create_metadata: bool) -> list[str]:
        """
        Extract palettes and create palette/metadata files

        Returns:
            List of created file paths
        """
        created_files = []

        self.extraction_progress.emit("Extracting palettes...")
        palette_manager = self._ensure_palette_manager()
        palette_manager.load_cgram(cgram_path)

        # Get sprite palettes
        sprite_palettes = palette_manager.get_sprite_palettes()
        self.palettes_extracted.emit(sprite_palettes)

        # Create palette files
        if create_grayscale:
            self.extraction_progress.emit("Creating palette files...")

            # Create main palette file (default to palette 8)
            main_pal_file = f"{output_base}.pal.json"
            palette_manager.create_palette_json(8, main_pal_file, png_file)
            created_files.append(main_pal_file)

            # Create individual palette files
            palette_files = {}
            for pal_idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
                pal_file = f"{output_base}_pal{pal_idx}.pal.json"
                palette_manager.create_palette_json(pal_idx, pal_file, png_file)
                created_files.append(pal_file)
                palette_files[pal_idx] = pal_file

            # Create metadata file
            if create_metadata:
                self.extraction_progress.emit("Creating metadata file...")

                # Prepare extraction parameters
                extraction_params = {
                    "source": Path(source_path).name,
                    "offset": source_offset if source_offset is not None else 0xC000,
                    "tile_count": num_tiles,
                    "extraction_size": num_tiles * BYTES_PER_TILE,
                }

                metadata_file = palette_manager.create_metadata_json(
                    output_base, palette_files, extraction_params
                )
                created_files.append(metadata_file)

        # Analyze OAM if available
        if oam_path:
            self.extraction_progress.emit("Analyzing sprite palette usage...")
            active_palettes = palette_manager.analyze_oam_palettes(oam_path)
            self.active_palettes_found.emit(active_palettes)

        return created_files

    def generate_preview(self, vram_path: str, offset: int) -> tuple[Image.Image, int]:
        """Generate a preview image from VRAM at the specified offset

        Args:
            vram_path: Path to VRAM dump file
            offset: Offset in VRAM to start extracting from

        Returns:
            Tuple of (PIL image, tile count)

        Raises:
            ExtractionError: If preview generation fails
        """
        if self._sprite_extractor is None:
            raise ExtractionError("ExtractionManager not initialized")

        try:
            # Load VRAM
            sprite_extractor = self._ensure_sprite_extractor()
            sprite_extractor.load_vram(vram_path)

            # Extract tiles with new offset
            tiles, num_tiles = sprite_extractor.extract_tiles(offset=offset)

            # Create grayscale image
            img = sprite_extractor.create_grayscale_image(tiles)
            return img, num_tiles
        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, "preview_generation", "generating preview")
            raise  # Unreachable but satisfies type checker
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, "preview_generation", "generating preview")
            raise  # Unreachable but satisfies type checker
        except Exception as e:
            self._handle_operation_error(e, "preview_generation", ExtractionError, "generating preview")
            raise  # Unreachable but satisfies type checker

    def get_rom_extractor(self) -> ROMExtractor:
        """
        Get the ROM extractor instance for advanced operations

        Returns:
            ROMExtractor instance

        Note:
            This method provides access to the underlying ROM extractor
            for UI components that need direct access to ROM operations.
            Consider using the manager methods when possible.
        """
        if not self._is_initialized or self._rom_extractor is None:
            raise ExtractionError("ExtractionManager not initialized")
        return self._rom_extractor

    def extract_sprite_to_png(self, rom_path: str, sprite_offset: int,
                             output_path: str, cgram_path: str | None = None) -> bool:
        """
        Extract a single sprite to PNG file.

        Args:
            rom_path: Path to ROM file
            sprite_offset: Offset of sprite in ROM
            output_path: Full path where PNG should be saved
            cgram_path: Optional CGRAM file for palette data

        Returns:
            True if extraction successful, False otherwise
        """
        try:
            # Extract the sprite name from the output path
            sprite_name = Path(output_path).stem
            output_base = str(Path(output_path).parent / sprite_name)

            # Use the existing extract_from_rom method
            created_files = self.extract_from_rom(
                rom_path=rom_path,
                offset=sprite_offset,
                output_base=output_base,
                sprite_name=sprite_name,
                cgram_path=cgram_path
            )

            # Return True if any files were created
            return len(created_files) > 0

        except (ExtractionError, ValidationError) as e:
            self.error_occurred.emit(f"Sprite extraction failed: {e}")
            return False

    def get_known_sprite_locations(self, rom_path: str) -> dict[str, Any]:
        """
        Get known sprite locations for a ROM with caching

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of known sprite locations

        Raises:
            ExtractionError: If operation fails
        """
        try:
            # Use FileValidator for ROM file validation
            self._validate_rom_file_exists(rom_path)

            # Try to load from cache first
            start_time = time.time()
            rom_cache = get_rom_cache()

            # Signal that cache loading operation is starting
            self.cache_operation_started.emit("Loading", "sprite_locations")
            cached_locations = rom_cache.get_sprite_locations(rom_path)

            if cached_locations:
                time_saved = 2.5  # Estimated time saved by not scanning ROM
                self._logger.debug(f"Loaded sprite locations from cache: {rom_path}")
                self.cache_hit.emit("sprite_locations", time_saved)
                # Convert cached dict back to SpritePointer-like objects if needed
                # For now, return the cached dict directly since the callers expect a dict
                return cached_locations

            # Cache miss - scan ROM file
            self._logger.debug(f"Cache miss, scanning ROM for sprite locations: {rom_path}")
            self.cache_miss.emit("sprite_locations")
            locations = self._ensure_rom_extractor().get_known_sprite_locations(rom_path)
            scan_time = time.time() - start_time

            # Save to cache for future use
            if locations:
                # Signal that cache saving operation is starting
                self.cache_operation_started.emit("Saving", "sprite_locations")
                cache_success = rom_cache.save_sprite_locations(rom_path, locations)
                if cache_success:
                    self._logger.debug(f"Cached {len(locations)} sprite locations for future use (scan took {scan_time:.1f}s)")
                    self.cache_saved.emit("sprite_locations", len(locations))

        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, "get_known_sprite_locations", "getting sprite locations")
            raise
        except (ImportError, AttributeError) as e:
            self._handle_operation_error(e, "get_known_sprite_locations", ExtractionError, "ROM analysis not available")
            raise
        except Exception as e:
            self._handle_operation_error(e, "get_known_sprite_locations", ExtractionError, "getting sprite locations")
            raise
        else:
            return locations

    def read_rom_header(self, rom_path: str) -> dict[str, Any]:
        """
        Read ROM header information

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary containing ROM header information

        Raises:
            ExtractionError: If operation fails
        """
        try:
            # Use FileValidator for ROM file validation
            self._validate_rom_file_exists(rom_path)

            header = self._ensure_rom_extractor().rom_injector.read_rom_header(rom_path)
            return asdict(header)
        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, "read_rom_header", "reading ROM header")
            raise
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, "read_rom_header", "reading ROM header")
            raise
        except Exception as e:
            self._handle_operation_error(e, "read_rom_header", ExtractionError, "reading ROM header")
            raise

    def _raise_extraction_failed(self, message: str) -> None:
        """Helper method to raise ExtractionError (for TRY301 compliance)"""
        raise ExtractionError(message)

    def _validate_vram_file(self, vram_path: str) -> None:
        """Validate VRAM file and raise if invalid"""
        vram_result = FileValidator.validate_vram_file(vram_path)
        if not vram_result.is_valid:
            raise ValidationError(f"VRAM file validation failed: {vram_result.error_message}")

    def _validate_cgram_file(self, cgram_path: str) -> None:
        """Validate CGRAM file and raise if invalid"""
        cgram_result = FileValidator.validate_cgram_file(cgram_path)
        if not cgram_result.is_valid:
            raise ValidationError(f"CGRAM file validation failed: {cgram_result.error_message}")

    def _validate_oam_file(self, oam_path: str) -> None:
        """Validate OAM file and raise if invalid"""
        oam_result = FileValidator.validate_oam_file(oam_path)
        if not oam_result.is_valid:
            raise ValidationError(f"OAM file validation failed: {oam_result.error_message}")

    def _validate_rom_file(self, rom_path: str) -> None:
        """Validate ROM file and raise if invalid"""
        rom_result = FileValidator.validate_rom_file(rom_path)
        if not rom_result.is_valid:
            raise ValidationError(f"ROM file validation failed: {rom_result.error_message}")

    def _validate_rom_file_exists(self, rom_path: str) -> None:
        """Validate ROM file existence and raise if not found"""
        rom_result = FileValidator.validate_file_existence(rom_path, "ROM file")
        if not rom_result.is_valid:
            raise ValidationError(f"ROM file validation failed: {rom_result.error_message}")
