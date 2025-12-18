"""
ROM Service for SpritePal

Handles all ROM-based sprite extraction operations:
- ROM sprite extraction
- ROM preview generation
- Sprite location discovery
- ROM header reading
- Cache coordination for ROM operations

This service was extracted from ExtractionManager to provide
better separation of concerns between ROM and VRAM operations.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image
from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from core.palette_manager import PaletteManager
    from core.protocols.manager_protocols import ROMExtractorProtocol

from core.exceptions import ExtractionError, ValidationError
from core.palette_manager import PaletteManager
from utils.constants import (
    BYTES_PER_TILE,
    DEFAULT_PREVIEW_HEIGHT,
    DEFAULT_PREVIEW_WIDTH,
    SPRITE_PALETTE_END,
    SPRITE_PALETTE_START,
)
from utils.file_validator import FileValidator
from utils.logging_config import get_logger

# ROMCache accessed via DI: inject(ROMCacheProtocol)

logger = get_logger(__name__)


class ROMService(QObject):
    """
    Service for ROM-based sprite extraction operations.

    Provides:
    - ROM sprite extraction with palette support
    - ROM preview generation
    - Sprite location discovery with caching
    - ROM header reading
    """

    # Signals for ROM operations
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
    error_occurred = Signal(str)  # Error message

    # Instance attributes (set in __init__, never None after initialization)
    _rom_extractor: ROMExtractorProtocol
    _palette_manager: PaletteManager

    def __init__(
        self,
        rom_extractor: ROMExtractorProtocol | None = None,
        palette_manager: PaletteManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the ROM service.

        Args:
            rom_extractor: Optional ROMExtractor instance (uses DI if not provided)
            palette_manager: Optional PaletteManager instance (created if not provided)
            parent: Qt parent object
        """
        super().__init__(parent)
        self._logger = get_logger(f"services.{self.__class__.__name__}")
        if rom_extractor is None:
            from core.di_container import inject
            from core.protocols.manager_protocols import ROMExtractorProtocol
            rom_extractor = inject(ROMExtractorProtocol)
        self._rom_extractor = rom_extractor
        self._palette_manager = palette_manager or PaletteManager()
        self._logger.info("ROMService initialized")

    def cleanup(self) -> None:
        """Cleanup service resources.

        Note: Currently no persistent resources to cleanup.
        ROM file handles are managed via context managers in MemoryMappedROMReader.
        """
        pass

    def get_rom_extractor(self) -> ROMExtractorProtocol:
        """
        Get the ROM extractor instance for advanced operations.

        Returns:
            ROMExtractorProtocol instance

        Note:
            This method provides access to the underlying ROM extractor
            for UI components that need direct access to ROM operations.
            Consider using the service methods when possible.
        """
        # Always valid since __init__ guarantees _rom_extractor is set
        assert self._rom_extractor is not None
        return self._rom_extractor

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
            ValidationError: If parameters are invalid
        """
        # Validate parameters
        self._validate_rom_file(rom_path)
        self._validate_offset(offset)
        if cgram_path:
            self._validate_cgram_file(cgram_path)

        try:
            extracted_files = []
            palette_extraction_failed = False
            palette_error_msg = ""

            # Extract from ROM
            self.extraction_progress.emit(f"Extracting {sprite_name} from ROM...")

            # Pass output_base (without .png) and sprite_name to extractor
            # Extractor appends .png internally and returns the actual output path
            output_path, _extraction_info = self._rom_extractor.extract_sprite_from_rom(
                rom_path, offset, output_base, sprite_name
            )

            if output_path:
                # Create PIL image for preview using context manager to prevent resource leak
                with Image.open(output_path) as img:
                    tile_count = (img.width * img.height) // (8 * 8)
                    # Copy image data before context exits (signal receiver needs valid data)
                    img_copy = img.copy()

                extracted_files.append(output_path)
                self.preview_generated.emit(img_copy, tile_count)

                # Extract palettes if CGRAM provided - catch errors for partial success
                if cgram_path:
                    try:
                        extracted_files.extend(
                            self._extract_palettes(
                                cgram_path,
                                output_base,
                                output_path,
                                None,
                                rom_path,
                                offset,
                                tile_count,
                                True,
                                True,
                            )
                        )
                    except Exception as e:
                        # Log and track palette failure but don't fail sprite extraction
                        palette_extraction_failed = True
                        palette_error_msg = str(e)
                        self._logger.warning(f"Palette extraction failed: {e}")
            else:
                raise ExtractionError("Failed to extract sprite from ROM")

            # Emit appropriate completion message
            if palette_extraction_failed:
                self.extraction_warning.emit(
                    f"Sprite extracted but palette extraction failed: {palette_error_msg}"
                )
                self.extraction_progress.emit("ROM extraction complete (palettes failed)")
            else:
                self.extraction_progress.emit("ROM extraction complete!")

            self.files_created.emit(extracted_files)
            return extracted_files

        except (OSError, PermissionError) as e:
            error_msg = f"File I/O error during ROM extraction: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise
        except (ValueError, TypeError) as e:
            error_msg = f"Data format error during ROM extraction: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise
        except Exception as e:
            if not isinstance(e, ExtractionError):
                error_msg = f"ROM extraction failed: {e}"
                self._logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                raise ExtractionError(error_msg) from e
            raise

    def get_sprite_preview(
        self,
        rom_path: str,
        offset: int,
        sprite_name: str | None = None,
    ) -> tuple[bytes, int, int]:
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
        # Validate parameters
        self._validate_rom_file_exists(rom_path)
        self._validate_offset(offset)

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
                raise ValueError(f"Offset 0x{offset:X} exceeds ROM size 0x{rom_size:X}")

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

            return tile_data, width, height

        except (OSError, PermissionError) as e:
            error_msg = f"File I/O error during preview generation: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise
        except (ValueError, TypeError) as e:
            error_msg = f"Data format error during preview generation: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise
        except Exception as e:
            error_msg = f"Preview generation failed: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise ExtractionError(error_msg) from e

    def extract_sprite_to_png(
        self,
        rom_path: str,
        sprite_offset: int,
        output_path: str,
        cgram_path: str | None = None,
    ) -> bool:
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
                cgram_path=cgram_path,
            )

            # Return True if any files were created
            return len(created_files) > 0

        except (ExtractionError, ValidationError) as e:
            self.error_occurred.emit(f"Sprite extraction failed: {e}")
            return False

    def get_known_sprite_locations(self, rom_path: str) -> dict[str, Any]:
        """
        Get known sprite locations for a ROM with caching.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of known sprite locations

        Raises:
            ExtractionError: If operation fails
        """
        try:
            # Validate ROM file exists
            self._validate_rom_file_exists(rom_path)

            # Try to load from cache first
            start_time = time.time()
            from core.di_container import inject
            from core.protocols.manager_protocols import ROMCacheProtocol
            rom_cache = inject(ROMCacheProtocol)

            # Signal that cache loading operation is starting
            self.cache_operation_started.emit("Loading", "sprite_locations")
            cached_locations = rom_cache.get_sprite_locations(rom_path)

            if cached_locations:
                time_saved = 2.5  # Estimated time saved by not scanning ROM
                self._logger.debug(f"Loaded sprite locations from cache: {rom_path}")
                self.cache_hit.emit("sprite_locations", time_saved)
                return cached_locations

            # Cache miss - scan ROM file
            self._logger.debug(f"Cache miss, scanning ROM for sprite locations: {rom_path}")
            self.cache_miss.emit("sprite_locations")
            locations = self._rom_extractor.get_known_sprite_locations(rom_path)
            scan_time = time.time() - start_time

            # Save to cache for future use
            if locations:
                # Signal that cache saving operation is starting
                self.cache_operation_started.emit("Saving", "sprite_locations")
                cache_success = rom_cache.save_sprite_locations(rom_path, locations)
                if cache_success:
                    self._logger.debug(
                        f"Cached {len(locations)} sprite locations for future use "
                        f"(scan took {scan_time:.1f}s)"
                    )
                    self.cache_saved.emit("sprite_locations", len(locations))

            return locations

        except (OSError, PermissionError) as e:
            error_msg = f"File I/O error getting sprite locations: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise
        except (ImportError, AttributeError) as e:
            error_msg = f"ROM analysis not available: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise ExtractionError(error_msg) from e
        except Exception as e:
            error_msg = f"Getting sprite locations failed: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise ExtractionError(error_msg) from e

    def read_rom_header(self, rom_path: str) -> dict[str, Any]:
        """
        Read ROM header information.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary containing ROM header information

        Raises:
            ExtractionError: If operation fails
        """
        try:
            # Validate ROM file exists
            self._validate_rom_file_exists(rom_path)

            header = self._rom_extractor.rom_injector.read_rom_header(rom_path)
            return asdict(header)
        except (OSError, PermissionError) as e:
            error_msg = f"File I/O error reading ROM header: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise
        except (ValueError, TypeError) as e:
            error_msg = f"Data format error reading ROM header: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise
        except Exception as e:
            error_msg = f"Reading ROM header failed: {e}"
            self._logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise ExtractionError(error_msg) from e

    # Private helper methods

    def _extract_palettes(
        self,
        cgram_path: str,
        output_base: str,
        png_file: str,
        oam_path: str | None,
        source_path: str,
        source_offset: int | None,
        num_tiles: int,
        create_grayscale: bool,
        create_metadata: bool,
    ) -> list[str]:
        """
        Extract palettes and create palette/metadata files.

        Returns:
            List of created file paths
        """
        created_files = []

        self.extraction_progress.emit("Extracting palettes...")
        self._palette_manager.load_cgram(cgram_path)

        # Get sprite palettes
        sprite_palettes = self._palette_manager.get_sprite_palettes()
        self.palettes_extracted.emit(sprite_palettes)

        # Create palette files
        if create_grayscale:
            self.extraction_progress.emit("Creating palette files...")

            # Create main palette file (default to palette 8)
            main_pal_file = f"{output_base}.pal.json"
            self._palette_manager.create_palette_json(8, main_pal_file, png_file)
            created_files.append(main_pal_file)

            # Create individual palette files
            palette_files = {}
            for pal_idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
                pal_file = f"{output_base}_pal{pal_idx}.pal.json"
                self._palette_manager.create_palette_json(pal_idx, pal_file, png_file)
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

                metadata_file = self._palette_manager.create_metadata_json(
                    output_base, palette_files, extraction_params
                )
                created_files.append(metadata_file)

        # Analyze OAM if available
        if oam_path:
            self.extraction_progress.emit("Analyzing sprite palette usage...")
            active_palettes = self._palette_manager.analyze_oam_palettes(oam_path)
            self.active_palettes_found.emit(active_palettes)

        return created_files

    def _validate_rom_file(self, rom_path: str) -> None:
        """Validate ROM file exists and has correct extension."""
        result = FileValidator.validate_rom_file(rom_path)
        if not result.is_valid:
            raise ValidationError(result.error_message or f"Invalid ROM file: {rom_path}")

    def _validate_rom_file_exists(self, rom_path: str) -> None:
        """Validate ROM file exists."""
        if not Path(rom_path).exists():
            raise ValidationError(f"ROM file does not exist: {rom_path}")

    def _validate_cgram_file(self, cgram_path: str) -> None:
        """Validate CGRAM file exists and is valid."""
        result = FileValidator.validate_cgram_file(cgram_path)
        if not result.is_valid:
            raise ValidationError(result.error_message or f"Invalid CGRAM file: {cgram_path}")

    def _validate_offset(self, offset: int) -> None:
        """Validate offset is a non-negative integer."""
        # Type checking enforces int type; only validate non-negative
        if offset < 0:
            raise ValidationError(f"offset must be >= 0, got {offset}")
