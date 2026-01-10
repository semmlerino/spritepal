"""
ROM sprite extraction functionality for SpritePal
Extracts sprites directly from ROM files using HAL decompression
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import logging

    from core.services.rom_cache import ROMCache

from PIL import Image

from core.default_palette_loader import DefaultPaletteLoader
from core.hal_compression import HALCompressionError, HALCompressor
from core.rom_injector import ROMInjector, SpritePointer
from core.rom_palette_extractor import ROMPaletteExtractor
from core.rom_validator import ROMHeader
from core.sprite_config_loader import SpriteConfigLoader
from core.types import ExtractionMetadata, SpriteInfo
from utils.constants import (
    BUFFER_SIZE_1KB,
    BUFFER_SIZE_2KB,
    BUFFER_SIZE_4KB,
    BUFFER_SIZE_8KB,
    BUFFER_SIZE_16KB,
    BUFFER_SIZE_64KB,
    BUFFER_SIZE_512B,
    BYTE_FREQUENCY_SAMPLE_SIZE,
    BYTES_PER_TILE,
    DEFAULT_TILES_PER_ROW,
    ENTROPY_ANALYSIS_SAMPLE,
    LARGE_SPRITE_MAX,
    MAX_ALIGNMENT_ERROR,
    MAX_BYTE_VALUE,
    MIN_SPRITE_TILES,
    PIXEL_SCALE_FACTOR,
    PROGRESS_LOG_INTERVAL,
    PROGRESS_SAVE_INTERVAL,
    ROM_SCAN_STEP_DEFAULT,
    SPRITE_ENTROPY_MAX,
    SPRITE_ENTROPY_MIN,
    SPRITE_QUALITY_BONUS,
    SPRITE_QUALITY_THRESHOLD,
    TILE_ANALYSIS_SAMPLE,
    TILE_HEIGHT,
    TILE_PLANE_SIZE,
    TILE_WIDTH,
    TYPICAL_SPRITE_MAX,
    TYPICAL_SPRITE_MIN,
)
from utils.logging_config import get_logger
from utils.math_utils import calculate_entropy
from utils.rom_exceptions import ROMCompressionError
from utils.rom_utils import load_rom_data_stripped

logger: logging.Logger = get_logger(__name__)


class ROMExtractor:
    """Handles sprite extraction directly from ROM files"""

    def __init__(self, rom_cache: ROMCache) -> None:
        """Initialize ROM extractor with required components.

        Args:
            rom_cache: Required ROM cache for caching scan results and sprite data.
        """
        logger.debug("Initializing ROMExtractor")
        self.hal_compressor: HALCompressor = HALCompressor()
        self.rom_injector: ROMInjector = ROMInjector()
        self.default_palette_loader: DefaultPaletteLoader = DefaultPaletteLoader()
        self.rom_palette_extractor: ROMPaletteExtractor = ROMPaletteExtractor()
        self.sprite_config_loader: SpriteConfigLoader = SpriteConfigLoader()
        self.rom_cache = rom_cache
        logger.info("ROMExtractor initialized with HAL compression and palette extraction support")

    # -------------------------------------------------------------------------
    # Facade methods - delegate to rom_injector to avoid reach-through access
    # -------------------------------------------------------------------------

    def find_compressed_sprite(
        self, rom_data: bytes | bytearray, offset: int, expected_size: int | None = None
    ) -> tuple[int, bytes, int]:
        """Find and decompress sprite data at given offset.

        Delegates to rom_injector.find_compressed_sprite().

        Args:
            rom_data: ROM data
            offset: Offset in ROM where compressed sprite starts
            expected_size: Expected decompressed size (will truncate if larger)

        Returns:
            Tuple of (compressed_size, decompressed_data, slack_size)
        """
        return self.rom_injector.find_compressed_sprite(rom_data, offset, expected_size)

    def read_rom_header(self, rom_path: str) -> ROMHeader:
        """Read ROM header information.

        Delegates to rom_injector.read_rom_header().

        Args:
            rom_path: Path to ROM file

        Returns:
            ROMHeader with title, rom_type, checksum, etc.
        """
        return self.rom_injector.read_rom_header(rom_path)

    def inject_sprite_to_rom(
        self,
        sprite_path: str,
        rom_path: str,
        output_path: str,
        sprite_offset: int,
        fast_compression: bool = False,
        create_backup: bool = True,
        ignore_checksum: bool = False,
        force: bool = False,
    ) -> tuple[bool, str]:
        """Inject sprite directly into ROM file with validation and backup.

        Delegates to rom_injector.inject_sprite_to_rom().

        Args:
            sprite_path: Path to edited sprite PNG
            rom_path: Path to input ROM
            output_path: Path for output ROM
            sprite_offset: Offset in ROM where sprite data is located
            fast_compression: Use fast compression mode
            create_backup: Create backup before modification
            ignore_checksum: If True, warn on checksum mismatch instead of failing
            force: If True, inject even if compressed size exceeds limit

        Returns:
            Tuple of (success, message)
        """
        return self.rom_injector.inject_sprite_to_rom(
            sprite_path,
            rom_path,
            output_path,
            sprite_offset,
            fast_compression,
            create_backup,
            ignore_checksum,
            force,
        )

    # -------------------------------------------------------------------------
    # Core extraction methods
    # -------------------------------------------------------------------------

    def extract_sprite_data(self, rom_path: str, sprite_offset: int) -> bytes:
        """
        Extract raw sprite data from ROM at specified offset.

        Args:
            rom_path: Path to ROM file
            sprite_offset: Offset in ROM where sprite data is located (logical offset)

        Returns:
            Raw sprite data as bytes

        Raises:
            ValueError: If offset is invalid (negative or exceeds ROM size)
            HALCompressionError: If decompression fails
        """
        logger.debug(f"Extracting sprite data from ROM: offset=0x{sprite_offset:X}")

        try:
            # Check for SMC header to adjust offset if needed
            header = self.rom_injector.read_rom_header(rom_path)
            smc_offset = header.header_offset

            # Adjust offset: ROM offset -> file offset
            file_offset = sprite_offset + smc_offset
            if smc_offset > 0:
                logger.info(f"Adjusting for {smc_offset}-byte SMC header: 0x{sprite_offset:X} -> 0x{file_offset:X}")

            # Try to decompress the data at the adjusted offset
            decompressed_data = self.hal_compressor.decompress_from_rom(rom_path, file_offset)

            return decompressed_data

        except Exception as e:
            logger.error(f"Failed to extract sprite data at offset 0x{sprite_offset:X}: {e}")
            raise HALCompressionError(f"Sprite extraction failed: {e}") from e

    def extract_sprite_from_rom(
        self, rom_path: str, sprite_offset: int, output_base: str, sprite_name: str = ""
    ) -> tuple[str, ExtractionMetadata]:
        """
        Extract sprite from ROM at specified offset.

        Args:
            rom_path: Path to ROM file
            sprite_offset: Offset in ROM where sprite data is located
            output_base: Base name for output files (without extension)
            sprite_name: Name of the sprite (e.g., "kirby_normal")

        Returns:
            Tuple of (output_png_path, extraction_info)
        """
        logger.info("=" * 60)
        logger.info(f"Starting ROM sprite extraction: offset=0x{sprite_offset:X}, sprite={sprite_name or 'unnamed'}")
        logger.debug(f"ROM path: {rom_path}")
        logger.debug(f"Output base: {output_base}")

        try:
            # Stage 1: Validate ROM and read data
            header, rom_data = self._validate_and_read_rom(rom_path)

            # Stage 2: Load sprite configuration if available
            expected_size = self._load_sprite_configuration(sprite_name, header)

            # Stage 3: Decompress sprite data
            compressed_size, sprite_data, _slack_size = self._decompress_sprite_data(
                rom_data, sprite_offset, expected_size
            )

            # Stage 4: Convert to PNG
            output_path = f"{output_base}.png"
            logger.info(f"Converting decompressed data to PNG: {output_path}")
            tile_count = self._convert_4bpp_to_png(sprite_data, output_path)

            # Stage 5: Extract palettes (ROM or default)
            palette_files, rom_palettes_used = self._extract_rom_palettes(rom_path, sprite_name, header, output_base)

            # Stage 6: Fall back to default palettes if needed
            if not palette_files and sprite_name:
                palette_files = self._load_default_palettes(sprite_name, output_base, header.title)

            if not palette_files:
                logger.info("No palettes available - sprite will be grayscale in editor")

            # Stage 7: Create extraction metadata
            extraction_info = self._create_extraction_metadata(
                rom_path,
                sprite_offset,
                sprite_name,
                compressed_size,
                tile_count,
                sprite_data,
                header,
                rom_palettes_used,
                palette_files,
            )

        except HALCompressionError as e:
            logger.exception("HAL decompression failed")
            raise ROMCompressionError(f"Failed to decompress sprite: {e}") from e
        except (OSError, PermissionError) as e:
            logger.exception(f"File I/O error during ROM extraction: {e}")
            raise
        except (ValueError, TypeError) as e:
            logger.exception(f"Data format error during ROM extraction: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error during ROM extraction: {e}")
            raise
        else:
            logger.info("ROM extraction completed successfully")
            logger.info(f"Output: {output_path} ({tile_count} tiles)")
            logger.info(f"Palettes: {len(palette_files)} files")
            logger.info("=" * 60)

            return output_path, extraction_info

    def _validate_and_read_rom(self, rom_path: str) -> tuple[ROMHeader, bytes]:
        """
        Validate ROM header and read ROM data.

        Args:
            rom_path: Path to ROM file

        Returns:
            Tuple of (header, rom_data) where rom_data has SMC header stripped
        """
        # Read ROM header for validation
        header = self.rom_injector.read_rom_header(rom_path)
        logger.info(f"ROM identified: {header.title} (checksum: 0x{header.checksum:04X})")

        # Read ROM data, stripping SMC header if present
        logger.info(f"Reading ROM data from: {rom_path}")
        with Path(rom_path).open("rb") as rom_file:
            rom_data = rom_file.read()

        # Strip SMC header so offsets are ROM addresses (not file offsets)
        smc_offset = header.header_offset
        if smc_offset > 0:
            logger.info(f"Stripping {smc_offset}-byte SMC header from ROM data")
            rom_data = rom_data[smc_offset:]

        logger.debug(f"ROM size: {len(rom_data)} bytes (after SMC strip)")

        return header, rom_data

    def _load_sprite_configuration(self, sprite_name: str, header: ROMHeader) -> int | None:
        """
        Load sprite configuration to get expected size.

        Args:
            sprite_name: Name of the sprite
            header: ROM header information

        Returns:
            Expected size in bytes, or None if not found
        """
        if not sprite_name:
            return None

        # Get sprite configurations for this ROM
        sprite_configs = self.sprite_config_loader.get_game_sprites(header.title, header.checksum)

        if sprite_name in sprite_configs:
            expected_size = sprite_configs[sprite_name].estimated_size
            logger.debug(f"Using expected size from config: {expected_size} bytes")
            return expected_size
        logger.debug(f"No sprite config found for '{sprite_name}', decompressing without size limit")
        return None

    def _decompress_sprite_data(
        self, rom_data: bytes, sprite_offset: int, expected_size: int | None
    ) -> tuple[int, bytes, int]:
        """
        Decompress sprite data from ROM.

        Args:
            rom_data: ROM data bytes
            sprite_offset: Offset to start decompression
            expected_size: Expected decompressed size (optional)

        Returns:
            Tuple of (compressed_size, decompressed_data, slack_size)
        """
        logger.info(f"Decompressing sprite data at offset 0x{sprite_offset:X}")
        compressed_size, sprite_data, slack_size = self.rom_injector.find_compressed_sprite(
            rom_data, sprite_offset, expected_size
        )

        logger.info(
            f"Decompressed sprite from 0x{sprite_offset:X}: "
            f"{compressed_size} bytes compressed, "
            f"{len(sprite_data)} bytes decompressed, "
            f"{slack_size} bytes slack space"
        )

        return compressed_size, sprite_data, slack_size

    def _extract_rom_palettes(
        self, rom_path: str, sprite_name: str, header: ROMHeader, output_base: str
    ) -> tuple[list[str], bool]:
        """
        Extract palettes from ROM for the sprite.

        Args:
            rom_path: Path to ROM file
            sprite_name: Name of the sprite
            header: ROM header information
            output_base: Base path for output files

        Returns:
            Tuple of (palette_files, rom_palettes_used)
        """
        palette_files = []
        rom_palettes_used = False

        if not sprite_name:
            return palette_files, rom_palettes_used

        logger.debug(f"Looking for palette configuration for sprite: {sprite_name}")

        # Get game configuration
        game_config = self._find_game_configuration(header)
        if not game_config:
            return palette_files, rom_palettes_used

        # Get palette configuration
        logger.debug(f"Getting palette configuration for {sprite_name}")
        palette_offset, palette_indices = self.rom_palette_extractor.get_palette_config_from_sprite_config(
            cast(dict[str, object], game_config),
            sprite_name,
        )

        if palette_offset and palette_indices:
            # Extract palettes from ROM
            logger.info(f"Extracting palettes from ROM at offset 0x{palette_offset:X}")
            logger.debug(f"Palette indices: {palette_indices}")
            palette_files = self.rom_palette_extractor.extract_palettes_from_rom(
                rom_path, palette_offset, palette_indices, output_base
            )

            if palette_files:
                rom_palettes_used = True
                logger.info(f"Successfully extracted {len(palette_files)} palettes from ROM")
                for pf in palette_files:
                    logger.debug(f"  - {Path(pf).name}")
            else:
                logger.warning("Failed to extract palettes from ROM")
        else:
            logger.debug("No palette configuration found for this sprite")

        return palette_files, rom_palettes_used

    def _find_game_configuration(self, header: ROMHeader) -> Mapping[str, object] | None:
        """
        Find game configuration matching the ROM header.

        Uses the unified game matching logic from SpriteConfigLoader which
        prioritizes checksum matching (most reliable) and falls back to
        flexible title matching with regional variant support.

        Args:
            header: ROM header information

        Returns:
            Game configuration dict or None if not found
        """
        # Use unified game matching (checksum + flexible title) from sprite_config_loader
        game_name, config = self.sprite_config_loader.find_game_config(header.title, header.checksum)
        if game_name:
            logger.debug(f"Found game configuration: {game_name}")
        return config

    def _load_default_palettes(self, sprite_name: str, output_base: str, rom_title: str = "") -> list[str]:
        """
        Load default palettes as fallback.

        Args:
            sprite_name: Name of the sprite
            output_base: Base path for output files
            rom_title: ROM title for fallback lookup when sprite name doesn't match

        Returns:
            List of palette file paths
        """
        # Try sprite name first
        if self.default_palette_loader.has_default_palettes(sprite_name):
            logger.info(f"Falling back to default palettes for {sprite_name}")
            palette_files = self.default_palette_loader.create_palette_files(sprite_name, output_base)
            logger.info(f"Created {len(palette_files)} default palette files for {sprite_name}")
            for pf in palette_files:
                logger.debug(f"  - {Path(pf).name}")
            return palette_files

        # Fall back to ROM title lookup (for generic sprite names like "High_Quality_Sprite_1")
        if rom_title and self.default_palette_loader.has_palettes_for_rom_title(rom_title):
            palette_key = self.default_palette_loader.get_palette_key_for_rom_title(rom_title)
            if palette_key:
                logger.info(f"Falling back to default palettes for ROM title: {rom_title} -> {palette_key}")
                palette_files = self.default_palette_loader.create_palette_files(palette_key, output_base)
                logger.info(f"Created {len(palette_files)} default palette files via ROM title")
                for pf in palette_files:
                    logger.debug(f"  - {Path(pf).name}")
                return palette_files

        return []

    def _create_extraction_metadata(
        self,
        rom_path: str,
        sprite_offset: int,
        sprite_name: str,
        compressed_size: int,
        tile_count: int,
        sprite_data: bytes,
        header: ROMHeader,
        rom_palettes_used: bool,
        palette_files: list[str],
    ) -> ExtractionMetadata:
        """
        Create extraction metadata dictionary.

        Args:
            rom_path: Path to ROM file
            sprite_offset: Offset where sprite was found
            sprite_name: Name of the sprite
            compressed_size: Size of compressed data
            tile_count: Number of tiles extracted
            sprite_data: Decompressed sprite data
            header: ROM header information
            rom_palettes_used: Whether ROM palettes were used
            palette_files: List of palette files

        Returns:
            Extraction info dictionary
        """
        return {
            "source_type": "rom",
            "rom_source": Path(rom_path).name,
            "rom_offset": f"0x{sprite_offset:X}",
            "sprite_name": sprite_name,
            "compressed_size": compressed_size,
            "tile_count": tile_count,
            "extraction_size": len(sprite_data),
            "rom_title": header.title,
            "rom_checksum": f"0x{header.checksum:04X}",
            "rom_palettes_used": rom_palettes_used,
            "default_palettes_used": len(palette_files) > 0 and not rom_palettes_used,
            "palette_count": len(palette_files),
        }

    def _convert_4bpp_to_png(self, tile_data: bytes, output_path: str) -> int:
        """
        Convert 4bpp tile data to grayscale PNG.

        Args:
            tile_data: Raw 4bpp tile data
            output_path: Path to save PNG

        Returns:
            Number of tiles extracted
        """
        # Calculate dimensions
        num_tiles = len(tile_data) // BYTES_PER_TILE
        tiles_per_row = DEFAULT_TILES_PER_ROW  # Standard width for sprite sheets

        # Handle empty data gracefully
        if num_tiles == 0:
            logger.info("No tile data to convert (0 bytes)")
            return 0

        # Check if we have partial tile data
        if len(tile_data) % BYTES_PER_TILE != 0:
            logger.warning(
                f"Tile data not aligned: {len(tile_data)} bytes ({len(tile_data) % BYTES_PER_TILE} extra bytes)"
            )

        # Calculate image dimensions
        img_width = tiles_per_row * TILE_WIDTH
        img_height = ((num_tiles + tiles_per_row - 1) // tiles_per_row) * TILE_HEIGHT

        logger.info(f"Converting 4bpp data: {len(tile_data)} bytes -> {num_tiles} tiles")
        logger.debug(f"Tiles per row: {tiles_per_row}")
        logger.debug(f"Image dimensions: {img_width}x{img_height} pixels")

        # Create indexed image directly
        img = Image.new("P", (img_width, img_height), 0)

        # Create grayscale palette (16 colors)
        # Map indices 0-15 to grayscale values 0-255 (multiples of 17)
        palette = []
        for i in range(256):
            if i < 16:
                val = i * PIXEL_SCALE_FACTOR
                palette.extend((val, val, val))
            else:
                palette.extend((0, 0, 0))
        img.putpalette(palette)

        # Process each tile
        log_interval = PROGRESS_LOG_INTERVAL  # Log progress every 100 tiles

        for tile_idx in range(num_tiles):
            # Calculate tile position
            tile_x = (tile_idx % tiles_per_row) * TILE_WIDTH
            tile_y = (tile_idx // tiles_per_row) * TILE_HEIGHT

            if (tile_idx + 1) % log_interval == 0:
                logger.debug(f"Processing tile {tile_idx + 1}/{num_tiles}")

            # Extract tile data
            tile_offset = tile_idx * BYTES_PER_TILE
            tile_bytes = tile_data[tile_offset : tile_offset + BYTES_PER_TILE]

            # Convert 4bpp planar to pixels
            for y in range(TILE_HEIGHT):
                for x in range(TILE_WIDTH):
                    # Get pixel value from 4bpp planar format (0-15)
                    pixel = self._get_4bpp_pixel(tile_bytes, x, y)
                    # Set pixel index directly
                    img.putpixel((tile_x + x, tile_y + y), pixel)

        # Save as indexed PNG
        img.save(output_path, "PNG")

        logger.info(f"Saved PNG: {output_path} ({img.width}x{img.height} pixels, {num_tiles} tiles)")
        return num_tiles

    def _get_4bpp_pixel(self, tile_data: bytes, x: int, y: int) -> int:
        """
        Get pixel value from 4bpp planar tile data.

        SNES 4bpp format stores 2 bitplanes together:
        - Planes 0,1 are interleaved in first {TILE_PLANE_SIZE} bytes
        - Planes 2,3 are interleaved in next {TILE_PLANE_SIZE} bytes
        """
        # Calculate byte positions
        row = y
        bit = 7 - (x % 8)

        # Get bits from each plane
        plane0 = (tile_data[row * 2] >> bit) & 1
        plane1 = (tile_data[row * 2 + 1] >> bit) & 1
        plane2 = (tile_data[TILE_PLANE_SIZE + row * 2] >> bit) & 1
        plane3 = (tile_data[TILE_PLANE_SIZE + row * 2 + 1] >> bit) & 1

        # Combine bits to get 4-bit value
        return (plane3 << 3) | (plane2 << 2) | (plane1 << 1) | plane0

    def get_known_sprite_locations(self, rom_path: str) -> dict[str, SpritePointer]:
        """
        Get known sprite locations for the given ROM.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of sprite name to SpritePointer
        """
        logger.info(f"Getting known sprite locations for ROM: {rom_path}")
        try:
            # Read ROM header to identify the game
            header = self.rom_injector.read_rom_header(rom_path)

            # Check if this is Kirby Super Star
            if "KIRBY" in header.title.upper():
                logger.debug(f"Detected Kirby ROM: {header.title}")
                locations = self.rom_injector.find_sprite_locations(rom_path)
                logger.info(f"Found {len(locations)} sprite locations")
                return locations

        except (OSError, PermissionError):
            logger.exception("File I/O error getting sprite locations")
            return {}
        except (ImportError, AttributeError) as e:
            logger.warning(f"ROM header parsing not available: {e}")
            return {}
        except Exception:
            logger.exception("Unexpected error getting sprite locations")
            return {}
        else:
            logger.warning(f"Unknown ROM: {header.title} - no sprite locations available")
            return {}

    def scan_for_sprites(
        self, rom_path: str, start_offset: int, end_offset: int, step: int = ROM_SCAN_STEP_DEFAULT
    ) -> list[SpriteInfo]:
        """
        Scan ROM for valid sprite data within a range of offsets with resumable caching.

        Args:
            rom_path: Path to ROM file
            start_offset: Starting offset to scan from
            end_offset: Ending offset to scan to
            step: Step size between scan attempts (default: {BUFFER_SIZE_256B} bytes)

        Returns:
            List of dictionaries containing valid sprite locations found
        """
        logger.info(f"Scanning ROM for sprites: 0x{start_offset:X} to 0x{end_offset:X} (step: 0x{step:X})")

        # Initialize scan context
        scan_params = self._create_scan_params(start_offset, end_offset, step)
        rom_cache = self.rom_cache

        # Check for cached results
        cached_result = self._load_cached_scan(rom_cache, rom_path, scan_params)
        if cached_result is not None:
            return cached_result

        # Get resume state from cache
        found_sprites, resume_offset = self._get_resume_state(rom_cache, rom_path, scan_params, start_offset)

        try:
            # Load and validate ROM data
            rom_data = self._load_rom_data(rom_path)
            end_offset = self._validate_scan_range(rom_data, end_offset)

            # Perform the scan
            found_sprites = self._perform_scan(
                rom_data, resume_offset, end_offset, step, found_sprites, rom_cache, rom_path, scan_params
            )

            # Sort by quality and save results
            found_sprites.sort(key=lambda x: x["quality"], reverse=True)
            rom_cache.save_partial_scan_results(
                rom_path,
                cast(dict[str, int], scan_params),
                cast(list[Mapping[str, object]], found_sprites),
                end_offset,
                completed=True,
            )

            return found_sprites

        except (OSError, PermissionError, MemoryError, Exception) as e:
            self._handle_scan_error(e, found_sprites, rom_cache, rom_path, scan_params, resume_offset)
            # Return partial results instead of discarding all progress
            if found_sprites:
                found_sprites.sort(key=lambda x: x["quality"], reverse=True)
                logger.info(f"Returning {len(found_sprites)} sprites found before error")
            return found_sprites

    def _create_scan_params(self, start_offset: int, end_offset: int, step: int) -> dict[str, object]:
        """Create scan parameters dictionary for caching.

        Args:
            start_offset: Starting offset
            end_offset: Ending offset
            step: Step size

        Returns:
            Scan parameters dictionary
        """
        return {"start_offset": start_offset, "end_offset": end_offset, "step": step, "scan_type": "sprite_scan"}

    def _load_cached_scan(
        self, rom_cache: ROMCache, rom_path: str, scan_params: Mapping[str, object]
    ) -> list[SpriteInfo] | None:
        """Load completed scan from cache if available.

        Args:
            rom_cache: ROM cache instance
            rom_path: Path to ROM file
            scan_params: Scan parameters

        Returns:
            Cached sprites list or None if not complete
        """
        cached_progress = rom_cache.get_partial_scan_results(rom_path, cast(dict[str, int], scan_params))
        if cached_progress and cached_progress.get("completed", False):
            logger.info("Found completed scan in cache, returning cached results")
            return cast(list[SpriteInfo], cached_progress.get("found_sprites", []))
        return None

    def _get_resume_state(
        self, rom_cache: ROMCache, rom_path: str, scan_params: Mapping[str, object], start_offset: int
    ) -> tuple[list[SpriteInfo], int]:
        """Get resume state from cached progress.

        Args:
            rom_cache: ROM cache instance
            rom_path: Path to ROM file
            scan_params: Scan parameters
            start_offset: Default start offset

        Returns:
            Tuple of (found_sprites list, resume_offset)
        """
        cached_progress = rom_cache.get_partial_scan_results(rom_path, cast(dict[str, int], scan_params))

        if cached_progress and not cached_progress.get("completed", False):
            found_sprites = cast(list[SpriteInfo], cached_progress.get("found_sprites", []))
            resume_offset = cast(int, cached_progress.get("current_offset", start_offset))
            logger.info(
                f"Resuming scan from cached progress: {len(found_sprites)} sprites found, "
                f"resuming from offset 0x{resume_offset:X}"
            )
            return found_sprites, resume_offset

        return [], start_offset

    def _load_rom_data(self, rom_path: str) -> bytes:
        """Load ROM data from file, stripping SMC header if present.

        Args:
            rom_path: Path to ROM file

        Returns:
            ROM data as bytes (with SMC header stripped so offsets are ROM addresses)
        """
        return load_rom_data_stripped(rom_path)

    def _validate_scan_range(self, rom_data: bytes, end_offset: int) -> int:
        """Validate and adjust scan range if needed.

        Args:
            rom_data: ROM data
            end_offset: Requested end offset

        Returns:
            Adjusted end offset
        """
        rom_size = len(rom_data)
        if end_offset > rom_size:
            logger.warning(f"End offset 0x{end_offset:X} exceeds ROM size, adjusting to 0x{rom_size:X}")
            return rom_size
        return end_offset

    def _perform_scan(
        self,
        rom_data: bytes,
        resume_offset: int,
        end_offset: int,
        step: int,
        found_sprites: list[SpriteInfo],
        rom_cache: ROMCache,
        rom_path: str,
        scan_params: Mapping[str, object],
    ) -> list[SpriteInfo]:
        """Perform the actual sprite scanning.

        Args:
            rom_data: ROM data to scan
            resume_offset: Offset to resume from
            end_offset: End offset
            step: Step size
            found_sprites: List of already found sprites
            rom_cache: ROM cache instance
            rom_path: Path to ROM file
            scan_params: Scan parameters

        Returns:
            List of found sprites
        """
        scan_count = 0
        save_progress_interval = PROGRESS_SAVE_INTERVAL

        # Use while loop to ensure we scan up to and including the last valid offset
        # Minimum bytes needed for compressed data header
        min_compressed_header = 4
        offset = resume_offset
        while offset < end_offset:
            # Bounds check: ensure enough room for compressed header
            if offset + min_compressed_header > len(rom_data):
                logger.debug(f"Stopping scan at 0x{offset:X}: insufficient data for compressed header")
                break

            scan_count += 1

            # Log progress periodically
            if scan_count % PROGRESS_LOG_INTERVAL == 0:
                logger.debug(f"Scanned {scan_count} offsets... (currently at 0x{offset:X})")

            # Save progress periodically
            if scan_count % save_progress_interval == 0:
                rom_cache.save_partial_scan_results(
                    rom_path,
                    cast(dict[str, int], scan_params),
                    cast(list[Mapping[str, object]], found_sprites),
                    offset,
                    completed=False,
                )

            # Try to find sprite at this offset
            sprite_info = self._try_extract_sprite_at_offset(rom_data, offset)
            if sprite_info:
                found_sprites.append(sprite_info)
                logger.info(
                    f"Found valid sprite at 0x{offset:X}: "
                    f"{sprite_info['tile_count']} tiles, {sprite_info['compressed_size']} bytes compressed, "
                    f"alignment: {sprite_info['alignment']}"
                )

            offset += step

        # Check the final offset if it's exactly at the end boundary and has room for data
        if offset == end_offset and offset + min_compressed_header <= len(rom_data):
            scan_count += 1
            sprite_info = self._try_extract_sprite_at_offset(rom_data, offset)
            if sprite_info:
                found_sprites.append(sprite_info)
                logger.info(f"Found valid sprite at end offset 0x{offset:X}")

        logger.info(f"Scan complete: checked {scan_count} offsets, found {len(found_sprites)} valid sprites")
        return found_sprites

    def _try_extract_sprite_at_offset(self, rom_data: bytes, offset: int) -> SpriteInfo | None:
        """Try to extract and validate sprite at given offset.

        Args:
            rom_data: ROM data
            offset: Offset to check

        Returns:
            Sprite info dictionary or None if invalid
        """
        try:
            # Try to decompress sprite at this offset
            compressed_size, sprite_data, _ = self.rom_injector.find_compressed_sprite(rom_data, offset)

            if len(sprite_data) == 0:
                return None

            # Validate sprite data
            sprite_info = self._validate_sprite_data(sprite_data, offset, compressed_size)
            return sprite_info

        except HALCompressionError:
            # Decompression failed, not a valid sprite location
            return None
        except (OSError, MemoryError) as e:
            logger.debug(f"I/O or memory error at offset 0x{offset:X}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Unexpected error at offset 0x{offset:X}: {e}")
            return None

    def _validate_sprite_data(self, sprite_data: bytes, offset: int, compressed_size: int) -> SpriteInfo | None:
        """Validate sprite data and create info dictionary.

        Args:
            sprite_data: Decompressed sprite data
            offset: ROM offset
            compressed_size: Compressed size in bytes

        Returns:
            Sprite info dictionary or None if invalid
        """
        bytes_per_tile = BYTES_PER_TILE
        extra_bytes = len(sprite_data) % bytes_per_tile
        num_tiles = len(sprite_data) // bytes_per_tile

        # Only accept perfectly aligned data or minor misalignment
        if extra_bytes > bytes_per_tile // 4 or num_tiles < MIN_SPRITE_TILES:
            return None

        alignment_status = "perfect" if extra_bytes == 0 else f"{extra_bytes} extra bytes"

        return {
            "offset": offset,
            "offset_hex": f"0x{offset:X}",
            "compressed_size": compressed_size,
            "decompressed_size": len(sprite_data),
            "tile_count": num_tiles,
            "alignment": alignment_status,
            "quality": self._assess_sprite_quality(sprite_data),
        }

    def _handle_scan_error(
        self,
        error: Exception,
        found_sprites: list[SpriteInfo],
        rom_cache: ROMCache,
        rom_path: str,
        scan_params: Mapping[str, object],
        resume_offset: int,
    ) -> None:
        """Handle errors during scanning and save partial results.

        Args:
            error: The exception that occurred
            found_sprites: List of sprites found so far
            rom_cache: ROM cache instance
            rom_path: Path to ROM file
            scan_params: Scan parameters
            resume_offset: Last offset scanned
        """
        error_type = type(error).__name__
        logger.exception(f"{error_type} during sprite scan")

        # Try to save partial results
        if found_sprites:
            try:
                rom_cache.save_partial_scan_results(
                    rom_path,
                    cast(dict[str, int], scan_params),
                    cast(list[Mapping[str, object]], found_sprites),
                    resume_offset,
                    completed=False,
                )
            except Exception as cache_error:
                logger.warning(f"Failed to save partial results on scan failure: {cache_error}")

    def _assess_sprite_quality(self, sprite_data: bytes, check_embedded: bool = True) -> float:
        """
        Assess the quality of sprite data based on various heuristics.

        Args:
            sprite_data: Decompressed sprite data
            check_embedded: Whether to check for embedded sprites

        Returns:
            Quality score (0.0 to 1.0)
        """
        data_size = len(sprite_data)

        # Early validation
        if data_size == 0 or data_size > BUFFER_SIZE_64KB:
            return 0.0

        # Calculate component scores
        score = 0.0

        # Size and alignment scoring
        alignment_score = self._score_data_alignment(data_size)
        if alignment_score < 0:  # Fatal alignment error
            return 0.0
        score += alignment_score

        # Tile count scoring
        tile_score = self._score_tile_count(data_size)
        if tile_score < 0:  # Fatal tile count error
            return 0.0
        score += tile_score

        # Entropy scoring
        entropy_score = self._score_entropy(sprite_data, data_size)
        score = self._apply_entropy_penalty(score, entropy_score)

        # Tile structure validation
        tile_validity_score = self._score_tile_validity(sprite_data, data_size)
        score = self._apply_tile_validity_adjustment(score, tile_validity_score)

        # Pattern analysis
        if self._has_graphics_patterns(sprite_data):
            score += 0.1

        # Check for embedded sprites if needed
        if check_embedded:
            embedded_score = self._check_embedded_sprites(sprite_data, data_size, score)
            if embedded_score > score:
                return embedded_score

        return min(score, 1.0)

    def _score_data_alignment(self, data_size: int) -> float:
        """Score data based on byte alignment.

        Args:
            data_size: Size of the data in bytes

        Returns:
            Alignment score (0.0-0.2) or -1.0 for fatal error
        """
        extra_bytes = data_size % BYTES_PER_TILE

        if extra_bytes == 0:
            return 0.2  # Perfect alignment
        if extra_bytes > MAX_ALIGNMENT_ERROR:
            return -1.0  # Fatal: badly misaligned
        if extra_bytes <= 8:
            return 0.1  # Minor misalignment acceptable
        return 0.0

    def _score_tile_count(self, data_size: int) -> float:
        """Score data based on tile count.

        Args:
            data_size: Size of the data in bytes

        Returns:
            Tile count score (0.0-0.2) or -1.0 for fatal error
        """
        num_tiles = data_size // BYTES_PER_TILE

        if num_tiles > LARGE_SPRITE_MAX:
            return -1.0  # Fatal: too large
        if TYPICAL_SPRITE_MIN <= num_tiles <= TYPICAL_SPRITE_MAX:
            return 0.2  # Typical sprite size
        if MIN_SPRITE_TILES <= num_tiles < TYPICAL_SPRITE_MIN:
            return 0.1  # Small but acceptable
        if TYPICAL_SPRITE_MAX < num_tiles <= LARGE_SPRITE_MAX:
            return 0.1  # Large but acceptable
        if num_tiles < MIN_SPRITE_TILES:
            return 0.05  # Too small, but not fatal
        return 0.0

    def _score_entropy(self, sprite_data: bytes, data_size: int) -> float:
        """Calculate entropy score for sprite data.

        Args:
            sprite_data: The sprite data
            data_size: Size of the data

        Returns:
            Entropy score (0.0-0.2)
        """
        sample_size = min(ENTROPY_ANALYSIS_SAMPLE, data_size)
        entropy = self._calculate_entropy(sprite_data[:sample_size])

        if SPRITE_ENTROPY_MIN <= entropy <= SPRITE_ENTROPY_MAX:
            return 0.2  # Graphics data typically has moderate entropy
        return 0.0  # Too uniform or too random

    def _apply_entropy_penalty(self, current_score: float, entropy_score: float) -> float:
        """Apply entropy-based penalty to the current score.

        Args:
            current_score: Current quality score
            entropy_score: Entropy score component

        Returns:
            Adjusted score
        """
        if entropy_score > 0:
            return current_score + entropy_score
        # Penalize bad entropy
        return current_score * 0.5

    def _score_tile_validity(self, sprite_data: bytes, data_size: int) -> float:
        """Score tile structure validity.

        Args:
            sprite_data: The sprite data
            data_size: Size of the data

        Returns:
            Tile validity ratio (0.0-1.0)
        """
        num_tiles = data_size // BYTES_PER_TILE
        tiles_checked = min(TILE_ANALYSIS_SAMPLE, num_tiles)

        if tiles_checked == 0:
            return 0.0

        valid_tile_count = 0
        for i in range(tiles_checked):
            tile_offset = i * BYTES_PER_TILE
            tile_data = sprite_data[tile_offset : tile_offset + BYTES_PER_TILE]
            if len(tile_data) == BYTES_PER_TILE and self._validate_4bpp_tile(tile_data):
                valid_tile_count += 1

        return valid_tile_count / tiles_checked

    def _apply_tile_validity_adjustment(self, current_score: float, validity_ratio: float) -> float:
        """Apply tile validity adjustment to score.

        Args:
            current_score: Current quality score
            validity_ratio: Ratio of valid tiles (0.0-1.0)

        Returns:
            Adjusted score
        """
        if validity_ratio >= 0.8:
            return current_score + 0.3
        if validity_ratio >= 0.5:
            return current_score + SPRITE_QUALITY_BONUS
        if validity_ratio < 0.3:
            return current_score * 0.5  # Penalize low validity
        return current_score

    def _check_embedded_sprites(self, sprite_data: bytes, data_size: int, current_score: float) -> float:
        """Check for embedded sprites within the data.

        Args:
            sprite_data: The sprite data
            data_size: Size of the data
            current_score: Current quality score

        Returns:
            Best score found (current or embedded)
        """
        # Only check if score is low and data is large enough
        if current_score >= SPRITE_QUALITY_THRESHOLD or data_size <= BUFFER_SIZE_16KB:
            return current_score

        best_score = current_score
        test_offsets = [BUFFER_SIZE_512B, BUFFER_SIZE_1KB, BUFFER_SIZE_2KB, BUFFER_SIZE_4KB]

        for test_offset in test_offsets:
            if test_offset + BUFFER_SIZE_8KB > data_size:
                continue

            embedded_data = sprite_data[test_offset : test_offset + BUFFER_SIZE_8KB]
            # Recursive call but without embedded check to avoid infinite recursion
            embedded_score = self._assess_sprite_quality(embedded_data, check_embedded=False)

            if embedded_score > best_score:
                logger.debug(f"Found better quality sprite embedded at offset +{test_offset}")
                best_score = embedded_score

        return best_score

    def _has_4bpp_characteristics(self, data: bytes) -> bool:
        """
        Check if data has characteristics of 4bpp sprite data.

        Args:
            data: Sprite data to check

        Returns:
            True if data appears to be 4bpp sprite data
        """
        if len(data) < BYTES_PER_TILE:
            return False

        # Check first tile for 4bpp structure
        tile_data = data[:BYTES_PER_TILE]

        # In 4bpp format, bitplanes are organized in a specific way
        # Check for reasonable bit patterns (not all 0 or all 1)
        bitplane_variety = 0

        for i in range(0, TILE_PLANE_SIZE, 2):  # First two bitplanes
            byte1 = tile_data[i]
            byte2 = tile_data[i + 1]
            if 0 < byte1 < MAX_BYTE_VALUE or 0 < byte2 < MAX_BYTE_VALUE:
                bitplane_variety += 1

        for i in range(TILE_PLANE_SIZE, BYTES_PER_TILE, 2):  # Second two bitplanes
            byte1 = tile_data[i]
            byte2 = tile_data[i + 1]
            if 0 < byte1 < MAX_BYTE_VALUE or 0 < byte2 < MAX_BYTE_VALUE:
                bitplane_variety += 1

        # Expect some variety in the bitplanes
        return bitplane_variety >= 4

    def _calculate_entropy(self, data: bytes) -> float:
        """Calculate Shannon entropy of data.

        Args:
            data: Data to analyze

        Returns:
            Entropy value (0-8 for byte data)
        """
        return calculate_entropy(data)

    def _validate_4bpp_tile(self, tile_data: bytes) -> bool:
        """
        Validate if a single tile has valid 4bpp sprite characteristics.

        Args:
            tile_data: {BYTES_PER_TILE} bytes of tile data

        Returns:
            True if tile appears valid
        """
        if len(tile_data) != BYTES_PER_TILE:
            return False

        # Check for completely empty or full tile (common in non-sprite data)
        if tile_data in (b"\x00" * BYTES_PER_TILE, b"\xff" * BYTES_PER_TILE):
            return False

        # Check bitplane structure
        plane_validity = 0

        # Check first two bitplanes (bytes 0-15)
        plane01_zeros = sum(1 for b in tile_data[0:TILE_PLANE_SIZE] if b == 0)
        plane01_ones = sum(1 for b in tile_data[0:TILE_PLANE_SIZE] if b == 0xFF)
        if plane01_zeros < (TILE_PLANE_SIZE - 1) and plane01_ones < (TILE_PLANE_SIZE - 1):  # Not all blank/full
            plane_validity += 1

        # Check second two bitplanes (bytes 16-31)
        plane23_zeros = sum(1 for b in tile_data[16:32] if b == 0)
        plane23_ones = sum(1 for b in tile_data[16:32] if b == 0xFF)
        if plane23_zeros < 15 and plane23_ones < 15:  # Not all blank/full
            plane_validity += 1

        # Check for bitplane patterns that indicate graphics
        # In sprites, bitplanes often have correlated patterns
        correlation = 0
        for i in range(8):  # Check each row
            # Get bytes from each bitplane pair
            p0 = tile_data[i * 2]
            p1 = tile_data[i * 2 + 1]
            p2 = tile_data[16 + i * 2]
            p3 = tile_data[16 + i * 2 + 1]

            # Check if there's some correlation between planes
            if (p0 & p2) != 0 or (p1 & p3) != 0:
                correlation += 1

        return plane_validity >= 1 and correlation >= 2

    def _has_graphics_patterns(self, data: bytes) -> bool:
        """
        Check for patterns typical of graphics data.

        Args:
            data: Sprite data to analyze

        Returns:
            True if data shows graphics patterns
        """
        if len(data) < 64:
            return False

        # Check for repeating patterns at tile boundaries
        # Graphics often have similar tiles or tile patterns
        pattern_matches = 0
        bytes_per_tile = BYTES_PER_TILE

        for i in range(0, min(len(data) - bytes_per_tile * 2, BYTE_FREQUENCY_SAMPLE_SIZE), bytes_per_tile):
            tile1 = data[i : i + bytes_per_tile]
            tile2 = data[i + bytes_per_tile : i + bytes_per_tile * 2]

            # Count similar bytes between adjacent tiles
            similar_bytes = sum(1 for j in range(bytes_per_tile) if tile1[j] == tile2[j])

            # Adjacent tiles often share some similarity in sprites
            if 4 <= similar_bytes <= 28:  # Some similarity but not identical
                pattern_matches += 1

        # Expect some pattern matches in real sprite data
        return pattern_matches >= 2
