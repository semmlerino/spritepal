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

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.palette_manager import PaletteManager
    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache

from core.exceptions import ExtractionError, ValidationError
from core.palette_manager import PaletteManager
from core.services.extraction_results import ExtractionResult, PreviewResult
from utils.constants import (
    BYTES_PER_TILE,
    DEFAULT_PREVIEW_HEIGHT,
    DEFAULT_PREVIEW_WIDTH,
)
from utils.file_validator import FileValidator
from utils.logging_config import get_logger

logger = get_logger(__name__)


class CacheResult:
    """Result from cache operations."""

    def __init__(
        self,
        data: dict[str, object] | None = None,
        *,
        hit: bool = False,
        time_saved: float = 0.0,
        items_saved: int = 0,
    ):
        self.data = data
        self.hit = hit
        self.time_saved = time_saved
        self.items_saved = items_saved


class ROMService:
    """
    Service for ROM-based sprite extraction operations.

    Provides:
    - ROM sprite extraction with palette support
    - ROM preview generation
    - Sprite location discovery with caching
    - ROM header reading
    """

    # Instance attributes (set in __init__, never None after initialization)
    _rom_extractor: ROMExtractor
    _palette_manager: PaletteManager
    _rom_cache: ROMCache

    def __init__(
        self,
        rom_extractor: ROMExtractor | None = None,
        palette_manager: PaletteManager | None = None,
        *,
        rom_cache: ROMCache | None = None,
    ) -> None:
        """
        Initialize the ROM service.

        Args:
            rom_extractor: Optional ROMExtractor instance (uses DI if not provided)
            palette_manager: Optional PaletteManager instance (created if not provided)
            rom_cache: Optional ROMCache instance (uses DI if not provided)
        """
        self._logger = get_logger(f"services.{self.__class__.__name__}")
        if rom_extractor is None:
            from core.di_container import inject
            from core.rom_extractor import ROMExtractor

            rom_extractor = inject(ROMExtractor)
        if rom_cache is None:
            from core.di_container import inject
            from core.services.rom_cache import ROMCache as ROMCacheClass

            rom_cache = inject(ROMCacheClass)
        self._rom_extractor = rom_extractor
        self._rom_cache = rom_cache
        self._palette_manager = palette_manager or PaletteManager()
        self._logger.info("ROMService initialized")

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
        progress_callback: Callable[[str], None] | None = None,
    ) -> ExtractionResult:
        """
        Extract sprites from ROM at specific offset.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM to extract from
            output_base: Base name for output files
            sprite_name: Name of the sprite being extracted
            cgram_path: CGRAM dump for palette extraction
            progress_callback: Optional callback for progress messages

        Returns:
            ExtractionResult with files, preview, palettes, and any warnings

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

        def _progress(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        extracted_files: list[str] = []
        warning: str | None = None
        preview_image: Image.Image | None = None
        tile_count = 0
        palettes: dict[int, list[list[int]]] = {}
        active_palette_indices: list[int] = []

        # Extract from ROM
        _progress(f"Extracting {sprite_name} from ROM...")

        # Pass output_base (without .png) and sprite_name to extractor
        # Extractor appends .png internally and returns the actual output path
        output_path, _extraction_info = self._rom_extractor.extract_sprite_from_rom(
            rom_path, offset, output_base, sprite_name
        )

        if output_path:
            # Create PIL image for preview using context manager to prevent resource leak
            with Image.open(output_path) as img:
                tile_count = (img.width * img.height) // (8 * 8)
                # Copy image data before context exits (caller needs valid data)
                preview_image = img.copy()

            extracted_files.append(output_path)

            # Extract palettes if CGRAM provided - catch errors for partial success
            if cgram_path:
                try:
                    from core.services.palette_utils import (
                        extract_palettes_and_create_files,
                    )

                    palette_result = extract_palettes_and_create_files(
                        palette_manager=self._palette_manager,
                        cgram_path=cgram_path,
                        output_base=output_base,
                        png_file=output_path,
                        oam_path=None,
                        source_path=rom_path,
                        source_offset=offset,
                        num_tiles=tile_count,
                        create_grayscale=True,
                        create_metadata=True,
                        progress_callback=progress_callback,
                    )
                    extracted_files.extend(palette_result.files)
                    palettes = palette_result.palettes
                    active_palette_indices = palette_result.active_palette_indices
                except Exception as e:
                    # Log and track palette failure but don't fail sprite extraction
                    warning = f"Sprite extracted but palette extraction failed: {e}"
                    self._logger.warning(f"Palette extraction failed: {e}")
        else:
            raise ExtractionError("Failed to extract sprite from ROM")

        # Log completion
        if warning:
            _progress("ROM extraction complete (palettes failed)")
        else:
            _progress("ROM extraction complete!")

        return ExtractionResult(
            files=extracted_files,
            preview_image=preview_image,
            tile_count=tile_count,
            palettes=palettes,
            active_palette_indices=active_palette_indices,
            warning=warning,
        )

    def get_sprite_preview(
        self,
        rom_path: str,
        offset: int,
        sprite_name: str | None = None,
    ) -> PreviewResult:
        """
        Get a preview of sprite data from ROM without saving files.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM
            sprite_name: Sprite name for logging

        Returns:
            PreviewResult with tile_data, width, height

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

        return PreviewResult(tile_data=tile_data, width=width, height=height)

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
            result = self.extract_from_rom(
                rom_path=rom_path,
                offset=sprite_offset,
                output_base=output_base,
                sprite_name=sprite_name,
                cgram_path=cgram_path,
            )

            # Return True if any files were created
            return len(result.files) > 0

        except (ExtractionError, ValidationError):
            # Return False for interface compatibility; exceptions propagate to manager
            return False

    def get_known_sprite_locations(
        self,
        rom_path: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[dict[str, object], CacheResult]:
        """
        Get known sprite locations for a ROM with caching.

        Args:
            rom_path: Path to ROM file
            progress_callback: Optional callback for progress messages

        Returns:
            Tuple of (locations dict, CacheResult with hit/miss info)

        Raises:
            ExtractionError: If operation fails
        """
        # Validate ROM file exists
        FileValidator.validate_rom_file_exists_or_raise(rom_path)

        # Try to load from cache first
        start_time = time.time()

        cached_locations = self._rom_cache.get_sprite_locations(rom_path)

        if cached_locations:
            time_saved = 2.5  # Estimated time saved by not scanning ROM
            self._logger.debug(f"Loaded sprite locations from cache: {rom_path}")
            return dict(cached_locations), CacheResult(hit=True, time_saved=time_saved)

        # Cache miss - scan ROM file
        self._logger.debug(f"Cache miss, scanning ROM for sprite locations: {rom_path}")
        locations = self._rom_extractor.get_known_sprite_locations(rom_path)
        scan_time = time.time() - start_time

        cache_result = CacheResult(hit=False)

        # Save to cache for future use
        if locations:
            cache_success = self._rom_cache.save_sprite_locations(rom_path, locations)
            if cache_success:
                self._logger.debug(
                    f"Cached {len(locations)} sprite locations for future use "
                    f"(scan took {scan_time:.1f}s)"
                )
                cache_result.items_saved = len(locations)

        return dict(locations), cache_result

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
