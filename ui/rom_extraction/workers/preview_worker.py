"""Worker thread for loading sprite previews"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.rom_extractor import ROMExtractor

from PySide6.QtCore import Signal

from core.workers.base import BaseWorker, handle_worker_errors
from utils.logging_config import get_logger
from utils.rom_utils import detect_smc_offset

logger = get_logger(__name__)


class SpritePreviewWorker(BaseWorker):
    """Worker thread for loading sprite previews"""

    # Custom signals (BaseWorker provides progress, error, warning, operation_finished)
    preview_ready = Signal(bytes, int, int, str, int)
    """Emitted when preview is ready. Args: tile_data (bytes), width (pixels), height (pixels), sprite_name, compressed_size."""

    preview_error = Signal(str)
    """Emitted on preview error. Args: error_message."""

    def __init__(
        self,
        rom_path: str,
        offset: int,
        sprite_name: str,
        extractor: ROMExtractor,
        sprite_config: object = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.rom_path = rom_path
        self.offset = offset
        self.sprite_name = sprite_name
        self.extractor = extractor
        self.sprite_config = sprite_config
        self._operation_name = f"SpritePreviewWorker-{sprite_name}"  # For logging

    @handle_worker_errors("sprite preview loading", handle_interruption=True)
    def run(self):
        """Load sprite preview in background"""

        logger.info(
            f"[PREVIEW_WORKER] Starting preview for sprite_name='{self.sprite_name}' at offset=0x{self.offset:06X}"
        )
        logger.debug(f"[PREVIEW_WORKER] ROM path: {self.rom_path}")

        def _validate_rom_path(rom_path: str) -> None:
            """Validate ROM file path exists"""
            if not rom_path or not Path(rom_path).exists():
                raise FileNotFoundError(f"ROM file not found: {rom_path}")

        def _validate_offset(offset: int) -> None:
            """Validate offset is not negative"""
            if offset < 0:
                raise ValueError(f"Invalid offset: 0x{offset:X} (negative)")

        def _validate_rom_file_access(rom_path: str, e: Exception) -> None:
            """Validate ROM file access and re-raise with context"""
            if isinstance(e, PermissionError):
                raise PermissionError(f"Cannot read ROM file: {rom_path}") from e
            if isinstance(e, OSError):
                raise OSError(f"Error reading ROM file: {e}") from e

        def _validate_rom_size(rom_size: int) -> None:
            """Validate ROM file size"""
            if rom_size < 0x8000:  # Minimum reasonable SNES ROM size
                raise ValueError(f"ROM file too small: {rom_size} bytes")

        def _validate_offset_bounds(offset: int, rom_size: int) -> None:
            """Validate offset is within ROM bounds"""
            if offset >= rom_size:
                raise ValueError(f"Offset 0x{offset:X} is beyond ROM size (0x{rom_size:X})")

        def _validate_sprite_data(tile_data: bytes, offset: int) -> None:
            """Validate extracted sprite data"""
            if not tile_data:
                raise ValueError(f"No sprite data found at offset 0x{offset:X}")

        def _validate_sprite_integrity(tile_data: bytes, offset: int, bytes_per_tile: int) -> None:
            """Validate sprite data integrity"""
            extra_bytes = len(tile_data) % bytes_per_tile
            if extra_bytes > bytes_per_tile // 2:
                raise ValueError(
                    f"Invalid sprite data detected at 0x{offset:X}. "
                    f"Expected multiple of {bytes_per_tile} bytes, got {len(tile_data)} bytes."
                )

        def _validate_tile_count(num_tiles: int, tile_data_length: int) -> None:
            """Validate that we have complete tiles"""
            if num_tiles == 0:
                raise ValueError(f"No complete tiles found in sprite data ({tile_data_length} bytes)")

        def _handle_decompression_error(error: Exception, offset: int) -> None:
            """Handle decompression errors with appropriate messages"""
            if "decompression" in str(error).lower():
                raise ValueError(
                    f"Failed to decompress sprite at 0x{offset:X}: Invalid compressed data format"
                ) from error
            raise ValueError(f"Error extracting sprite at 0x{offset:X}: {error}") from error

        try:
            # Validate inputs
            _validate_rom_path(self.rom_path)
            _validate_offset(self.offset)

            # Initialize variables to prevent unbound errors
            rom_data: bytes = b""
            tile_data: bytes = b""
            expected_size: int | None = None

            # Read ROM data with file size validation
            try:
                with Path(self.rom_path).open("rb") as f:
                    rom_data = f.read()
            except (PermissionError, OSError) as e:
                _validate_rom_file_access(self.rom_path, e)

            # Strip SMC header if present
            smc_offset = detect_smc_offset(rom_data)
            if smc_offset > 0:
                logger.debug(f"Stripping {smc_offset}-byte SMC header from ROM data")
                rom_data = rom_data[smc_offset:]

            # Validate ROM size
            rom_size = len(rom_data)
            _validate_rom_size(rom_size)

            # Validate offset is within ROM bounds
            _validate_offset_bounds(self.offset, rom_size)

            # Try HAL decompression first for all sprites (including manual offset browsing)
            # This allows Lua-captured offsets to work correctly
            compressed_size = 0

            # First attempt: Try HAL decompression
            decompression_start = time.time()
            try:
                logger.debug(f"[PREVIEW_WORKER] Attempting HAL decompression at 0x{self.offset:06X}")

                # Check if we have offset variants and expected size from sprite config
                offset_variants = []
                expected_size = None
                if hasattr(self, "sprite_config") and self.sprite_config:
                    offset_variants = getattr(self.sprite_config, "offset_variants", [])
                    expected_size = getattr(self.sprite_config, "estimated_size", None)
                    if expected_size:
                        logger.debug(f"[PREVIEW_WORKER] Using expected size from config: {expected_size} bytes")

                # Don't use hardcoded fallback sizes - let decompression return full data
                # The rom_injector has a 64KB safety limit and will return actual decompressed size
                # Using the actual decompressed size prevents truncation of valid sprites
                if not expected_size:
                    # Pass None - rom_injector will use 64KB max and return actual size
                    logger.debug("[PREVIEW_WORKER] No config size - using full decompression")

                # Try to decompress
                rom_injector = self.extractor.rom_injector
                if offset_variants:
                    compressed_size, tile_data, successful_offset = rom_injector.find_compressed_sprite_with_fallback(
                        rom_data, self.offset, offset_variants, expected_size
                    )
                    if successful_offset != self.offset:
                        logger.info(f"Used alternate offset 0x{successful_offset:X} for {self.sprite_name}")
                else:
                    compressed_size, tile_data = rom_injector.find_compressed_sprite(
                        rom_data, self.offset, expected_size
                    )

                decompression_time = (time.time() - decompression_start) * 1000
                logger.info(
                    f"[PREVIEW_WORKER] Successfully decompressed {len(tile_data)} bytes from offset 0x{self.offset:06X} in {decompression_time:.1f}ms"
                )
                logger.debug(
                    f"[PREVIEW_WORKER] Compressed size: {compressed_size} bytes, Compression ratio: {len(tile_data) / compressed_size:.2f}x"
                    if compressed_size > 0
                    else "[PREVIEW_WORKER] No compression size info"
                )

            except Exception as decomp_error:
                # Decompression failed - fall back to raw tile extraction for manual browsing
                decompression_time = (time.time() - decompression_start) * 1000
                logger.warning(
                    f"[PREVIEW_WORKER] HAL decompression failed at 0x{self.offset:06X} after {decompression_time:.1f}ms: {decomp_error.__class__.__name__}: {decomp_error}"
                )

                if self.sprite_name.startswith("manual_"):
                    # Manual offset browsing - extract raw 4bpp tile data as fallback
                    logger.info(
                        f"[PREVIEW_WORKER] Falling back to raw tile extraction for manual offset 0x{self.offset:06X}"
                    )
                    expected_size = 4096  # 4KB for fast preview

                    if self.offset + expected_size <= len(rom_data):
                        tile_data = rom_data[self.offset : self.offset + expected_size]
                    else:
                        tile_data = rom_data[self.offset :]

                    compressed_size = 0
                    logger.info(
                        f"[PREVIEW_WORKER] Extracted {len(tile_data)} bytes of raw tile data from 0x{self.offset:06X}"
                    )
                else:
                    # For non-manual sprites, decompression failure is an error
                    _handle_decompression_error(decomp_error, self.offset)

            # Validate extracted data
            _validate_sprite_data(tile_data, self.offset)

            # Check for data alignment issues
            bytes_per_tile = 32
            extra_bytes = len(tile_data) % bytes_per_tile
            if extra_bytes != 0:
                logger.warning(
                    f"Sprite data size ({len(tile_data)} bytes) is not a multiple of {bytes_per_tile} "
                    f"(tile size). Extra bytes: {extra_bytes}. Data may be corrupted."
                )

                # If significant misalignment, likely wrong offset
                _validate_sprite_integrity(tile_data, self.offset, bytes_per_tile)

            # Validate size against expected size if available
            if expected_size and expected_size > 0:
                size_ratio = len(tile_data) / expected_size
                if size_ratio < 0.5:
                    logger.warning(
                        f"Decompressed size ({len(tile_data)} bytes) is significantly smaller "
                        f"than expected ({expected_size} bytes). Sprite may be incomplete."
                    )
                elif size_ratio > 2.0:
                    logger.warning(
                        f"Decompressed size ({len(tile_data)} bytes) is significantly larger "
                        f"than expected ({expected_size} bytes). May contain extra data."
                    )
                else:
                    logger.debug(
                        f"Decompressed size ({len(tile_data)} bytes) is within acceptable range "
                        f"of expected size ({expected_size} bytes)"
                    )

            # Calculate dimensions (assume standard preview size)
            num_tiles = len(tile_data) // 32  # 32 bytes per tile
            _validate_tile_count(num_tiles, len(tile_data))

            tiles_per_row = 16
            tile_rows = (num_tiles + tiles_per_row - 1) // tiles_per_row

            width = min(tiles_per_row * 8, 128)
            height = min(tile_rows * 8, 128)

            self.preview_ready.emit(tile_data, width, height, self.sprite_name, compressed_size)
            self.operation_finished.emit(True, f"Preview loaded for {self.sprite_name}")

        except Exception as e:
            error_msg = f"Failed to load preview for {self.sprite_name}: {e}"
            logger.error(error_msg, exc_info=True)
            self.preview_error.emit(error_msg)
            self.operation_finished.emit(False, error_msg)

    # emit_error is inherited from BaseWorker
