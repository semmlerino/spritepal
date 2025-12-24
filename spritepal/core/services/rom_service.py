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
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QObject, Signal, SignalInstance

if TYPE_CHECKING:
    from collections.abc import Mapping

    from core.palette_manager import PaletteManager
    from core.rom_extractor import ROMExtractor

from core.exceptions import ExtractionError, ValidationError
from core.palette_manager import PaletteManager
from utils.constants import (
    BYTES_PER_TILE,
    DEFAULT_PREVIEW_HEIGHT,
    DEFAULT_PREVIEW_WIDTH,
)
from utils.file_validator import FileValidator
from utils.logging_config import get_logger

# ROMCache accessed via DI: inject(ROMCache)

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
    palettes_extracted = Signal(object)  # Palette data - use object to avoid PySide6 copy warning
    active_palettes_found = Signal(list)  # Active palette indices
    files_created = Signal(list)  # List of created files
    cache_operation_started = Signal(str, str)  # Operation type, cache type
    cache_hit = Signal(str, float)  # Cache type, time saved in seconds
    cache_miss = Signal(str)  # Cache type
    cache_saved = Signal(str, int)  # Cache type, number of items saved
    error_occurred = Signal(str)  # Error message

    # Instance attributes (set in __init__, never None after initialization)
    _rom_extractor: ROMExtractor
    _palette_manager: PaletteManager
    _parent_signals: Mapping[str, SignalInstance] | None

    def __init__(
        self,
        rom_extractor: ROMExtractor | None = None,
        palette_manager: PaletteManager | None = None,
        parent_signals: Mapping[str, SignalInstance] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the ROM service.

        Args:
            rom_extractor: Optional ROMExtractor instance (uses DI if not provided)
            palette_manager: Optional PaletteManager instance (created if not provided)
            parent_signals: Optional mapping of signal names to parent signal instances.
                           When provided, signals are emitted to parent instead of own signals.
            parent: Qt parent object
        """
        super().__init__(parent)
        self._logger = get_logger(f"services.{self.__class__.__name__}")
        if rom_extractor is None:
            from core.di_container import inject
            from core.rom_extractor import ROMExtractor
            rom_extractor = inject(ROMExtractor)
        self._rom_extractor = rom_extractor
        self._palette_manager = palette_manager or PaletteManager()
        self._parent_signals = parent_signals
        self._logger.info("ROMService initialized")

    def _emit(self, signal_name: str, *args: object) -> None:
        """Emit to parent signal if available, otherwise emit to own signal.

        Args:
            signal_name: Name of the signal to emit
            *args: Arguments to pass to the signal
        """
        if self._parent_signals and signal_name in self._parent_signals:
            self._parent_signals[signal_name].emit(*args)
        else:
            getattr(self, signal_name).emit(*args)

    def cleanup(self) -> None:
        """Cleanup service resources.

        Note: Currently no persistent resources to cleanup.
        ROM file handles are managed via context managers in MemoryMappedROMReader.
        """
        pass

    def get_rom_extractor(self) -> ROMExtractor:
        """
        Get the ROM extractor instance for advanced operations.

        Returns:
            ROMExtractor instance

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
        FileValidator.validate_rom_file_or_raise(rom_path)
        if offset < 0:
            raise ValidationError(f"offset must be >= 0, got {offset}")
        if cgram_path:
            FileValidator.validate_cgram_file_or_raise(cgram_path)

        extracted_files: list[str] = []
        palette_extraction_failed = False
        palette_error_msg = ""

        # Extract from ROM
        self._emit("extraction_progress", f"Extracting {sprite_name} from ROM...")

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
            self._emit("preview_generated", img_copy, tile_count)

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
            self._emit(
                "extraction_warning",
                f"Sprite extracted but palette extraction failed: {palette_error_msg}",
            )
            self._emit("extraction_progress", "ROM extraction complete (palettes failed)")
        else:
            self._emit("extraction_progress", "ROM extraction complete!")

        self._emit("files_created", extracted_files)
        return extracted_files

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
        FileValidator.validate_rom_file_exists_or_raise(rom_path)
        if offset < 0:
            raise ValidationError(f"offset must be >= 0, got {offset}")

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

        except (ExtractionError, ValidationError):
            # Return False for interface compatibility; exceptions propagate to manager
            return False

    def get_known_sprite_locations(self, rom_path: str) -> dict[str, object]:
        """
        Get known sprite locations for a ROM with caching.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of known sprite locations

        Raises:
            ExtractionError: If operation fails
        """
        # Validate ROM file exists
        FileValidator.validate_rom_file_exists_or_raise(rom_path)

        # Try to load from cache first
        start_time = time.time()
        from core.di_container import inject
        from core.services.rom_cache import ROMCache
        rom_cache = inject(ROMCache)

        # Signal that cache loading operation is starting
        self._emit("cache_operation_started", "Loading", "sprite_locations")
        cached_locations = rom_cache.get_sprite_locations(rom_path)

        if cached_locations:
            time_saved = 2.5  # Estimated time saved by not scanning ROM
            self._logger.debug(f"Loaded sprite locations from cache: {rom_path}")
            self._emit("cache_hit", "sprite_locations", time_saved)
            return dict(cached_locations)  # Convert Mapping to dict

        # Cache miss - scan ROM file
        self._logger.debug(f"Cache miss, scanning ROM for sprite locations: {rom_path}")
        self._emit("cache_miss", "sprite_locations")
        locations = self._rom_extractor.get_known_sprite_locations(rom_path)
        scan_time = time.time() - start_time

        # Save to cache for future use
        if locations:
            # Signal that cache saving operation is starting
            self._emit("cache_operation_started", "Saving", "sprite_locations")
            cache_success = rom_cache.save_sprite_locations(rom_path, locations)
            if cache_success:
                self._logger.debug(
                    f"Cached {len(locations)} sprite locations for future use "
                    f"(scan took {scan_time:.1f}s)"
                )
                self._emit("cache_saved", "sprite_locations", len(locations))

        return dict(locations)  # Convert Mapping to dict

    def read_rom_header(self, rom_path: str) -> dict[str, object]:
        """
        Read ROM header information.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary containing ROM header information

        Raises:
            ExtractionError: If operation fails
        """
        # Validate ROM file exists
        FileValidator.validate_rom_file_exists_or_raise(rom_path)

        # ROMExtractor has rom_injector with read_rom_header method
        header = self._rom_extractor.rom_injector.read_rom_header(rom_path)
        return asdict(header)

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

        Delegates to shared palette_utils.extract_palettes_and_create_files.

        Returns:
            List of created file paths
        """
        from core.services.palette_utils import extract_palettes_and_create_files

        return extract_palettes_and_create_files(
            palette_manager=self._palette_manager,
            cgram_path=cgram_path,
            output_base=output_base,
            png_file=png_file,
            oam_path=oam_path,
            source_path=source_path,
            source_offset=source_offset,
            num_tiles=num_tiles,
            create_grayscale=create_grayscale,
            create_metadata=create_metadata,
            emit=self._emit,
        )
