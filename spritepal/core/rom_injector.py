"""
ROM injection functionality for SpritePal.
Handles injection of edited sprites directly into ROM files.
"""

from __future__ import annotations

import struct
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# Only import Qt for type checking and the worker class
from core.hal_compression import HALCompressionError, HALCompressor
from core.injector import SpriteInjector
from core.rom_validator import ROMHeader, ROMValidator
from core.sprite_config_loader import SpriteConfigLoader
from utils.constants import (
    BYTES_PER_TILE,
    DECOMPRESSION_WINDOW_SIZE,
    SPRITE_VALIDATION_THRESHOLD,
)
from utils.file_validator import atomic_write
from utils.logging_config import get_logger
from utils.rom_backup import ROMBackupManager

logger = get_logger(__name__)


@dataclass
class SpritePointer:
    """Sprite data pointer in ROM"""

    offset: int
    bank: int
    address: int
    compressed_size: int | None = None
    offset_variants: list[int] | None = None


class ROMInjector(SpriteInjector):
    """Handles sprite injection directly into ROM files"""

    def __init__(self) -> None:
        super().__init__()
        self.hal_compressor: HALCompressor = HALCompressor()
        self.rom_data: bytearray | None = None
        self.header: ROMHeader | None = None
        self.sprite_config_loader: SpriteConfigLoader = SpriteConfigLoader()
        logger.debug("ROMInjector initialized with HAL compression support")

    def read_rom_header(self, rom_path: str) -> ROMHeader:
        """Read and parse SNES ROM header (delegates to ROMValidator)."""
        logger.info(f"Reading ROM header from: {rom_path}")
        header, _ = ROMValidator.validate_rom_header(rom_path)
        self.header = header
        logger.debug(f"ROM Title: {header.title}")
        logger.debug(f"ROM Type: 0x{header.rom_type:02X}")
        logger.debug(f"Checksum: 0x{header.checksum:04X}, Complement: 0x{header.checksum_complement:04X}")
        return self.header

    def calculate_checksum(self, rom_data: bytes | bytearray) -> tuple[int, int]:
        """Calculate SNES ROM checksum and complement (delegates to ROMValidator)."""
        logger.debug("Calculating ROM checksum")
        offset = self.header.header_offset if self.header else 0
        checksum, complement = ROMValidator.calculate_checksum(rom_data, offset)
        logger.debug(f"Calculated checksum: 0x{checksum:04X}, complement: 0x{complement:04X}")
        return checksum, complement

    def update_rom_checksum(self, rom_data: bytearray) -> None:
        """Update ROM checksum after modification"""
        if not self.header:
            raise ValueError("ROM header not loaded")

        logger.info("Updating ROM checksum after modification")
        # Calculate new checksum
        checksum, complement = self.calculate_checksum(rom_data)

        # Use the validated header offset stored during read_rom_header()
        header_base = self.header.header_offset + self.header.rom_type_offset

        # Update checksum in ROM
        struct.pack_into("<H", rom_data, header_base + 28, complement)
        struct.pack_into("<H", rom_data, header_base + 30, checksum)

        # Verify write was successful
        written_complement = struct.unpack_from("<H", rom_data, header_base + 28)[0]
        written_checksum = struct.unpack_from("<H", rom_data, header_base + 30)[0]
        if written_complement != complement or written_checksum != checksum:
            raise ValueError(
                f"Checksum write verification failed: expected {complement:04X}/{checksum:04X}, "
                f"got {written_complement:04X}/{written_checksum:04X}"
            )

        # Update header
        old_checksum = self.header.checksum
        self.header.checksum = checksum
        self.header.checksum_complement = complement
        logger.info(f"ROM checksum updated: 0x{old_checksum:04X} -> 0x{checksum:04X}")

    def find_compressed_sprite(
        self, rom_data: bytes | bytearray, offset: int, expected_size: int | None = None
    ) -> tuple[int, bytes]:
        """
        Find and decompress sprite data at given offset.

        Args:
            rom_data: ROM data
            offset: Offset in ROM where compressed sprite starts
            expected_size: Expected decompressed size (will truncate if larger)

        Returns:
            Tuple of (compressed_size, decompressed_data)
        """
        logger.debug(f"Finding and decompressing sprite at offset 0x{offset:X}")

        # Validate offset before any operations
        if offset < 0:
            raise ValueError(f"Invalid negative offset: {offset}")
        if offset >= len(rom_data):
            raise ValueError(f"Offset 0x{offset:X} exceeds ROM data size 0x{len(rom_data):X}")

        # Default size limit to prevent oversized decompression
        default_max_sprite_size = 65536  # 64KB - HAL compression limit

        if expected_size:
            logger.debug(f"Expected decompressed size: {expected_size} bytes")
        else:
            # Apply default size limit to prevent the 42KB issue
            expected_size = default_max_sprite_size
            logger.warning(f"No expected size provided, using default max limit: {expected_size} bytes")

        # Create temp file for decompression with only the relevant portion
        # Extract a window from offset to offset + 128KB (or end of ROM)
        # This reduces memory/disk usage from 4MB to ~128KB per operation
        window_size = DECOMPRESSION_WINDOW_SIZE  # 128KB - sufficient for any SNES sprite
        window_end = min(len(rom_data), offset + window_size)
        rom_window = rom_data[offset:window_end]
        adjusted_offset = 0  # Offset within the window

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(rom_window)
            tmp_rom = tmp.name

        try:
            # Decompress sprite data from the window - cache full result
            full_decompressed = self.hal_compressor.decompress_from_rom(tmp_rom, adjusted_offset)

            # Validate decompressed data
            if len(full_decompressed) == 0:
                raise ValueError("Decompression produced no data")

            original_size = len(full_decompressed)

            # Safety validation: Check if original decompressed size is reasonable
            max_reasonable_sprite_size = 65536  # 64KB absolute max for SNES sprites
            if original_size > max_reasonable_sprite_size:
                logger.error(
                    f"Decompressed sprite size ({original_size} bytes) exceeds reasonable limit "
                    f"({max_reasonable_sprite_size} bytes). This indicates a decompression error."
                )
                raise ValueError(
                    f"Sprite data too large: {original_size} bytes. "
                    f"Maximum reasonable size is {max_reasonable_sprite_size} bytes."
                )

            # Work with full data, truncate only when returning
            decompressed = full_decompressed

            # Truncate to expected size if specified
            if expected_size and len(decompressed) > expected_size:
                logger.warning(
                    f"Decompressed data ({original_size} bytes) exceeds expected size "
                    f"({expected_size} bytes). Truncating to expected size."
                )
                decompressed = decompressed[:expected_size]

                # Validate truncated data
                if not self._validate_sprite_data(decompressed):
                    logger.warning(
                        "Truncated data failed sprite validation. May contain non-sprite data. "
                        "Searching for sprite data within decompressed block..."
                    )

                    # Use cached full_decompressed instead of re-decompressing
                    sprite_offset = self._find_sprite_in_data(full_decompressed, expected_size)
                    if sprite_offset >= 0:
                        logger.info(f"Found valid sprite data at offset {sprite_offset} within decompressed block")
                        decompressed = full_decompressed[sprite_offset : sprite_offset + expected_size]
                    else:
                        logger.warning("Could not find valid sprite data. Consider using sprite scanner.")
            elif expected_size and len(decompressed) < expected_size:
                logger.warning(
                    f"Decompressed data ({original_size} bytes) is smaller than expected "
                    f"({expected_size} bytes). This may indicate a problem."
                )

            # Check if data size is valid for sprite tiles (should be multiple of tile size)
            extra_bytes = len(decompressed) % BYTES_PER_TILE
            if extra_bytes != 0:
                logger.warning(
                    f"Decompressed data size ({len(decompressed)} bytes) is not a multiple of {BYTES_PER_TILE}. "
                    f"Extra bytes: {extra_bytes}. This may indicate incorrect offset or corrupted data."
                )

                # If more than half a tile of extra data, likely wrong offset
                if extra_bytes > BYTES_PER_TILE // 2:
                    logger.error(
                        f"Significant data misalignment detected ({extra_bytes} extra bytes). "
                        f"The sprite offset 0x{offset:X} is likely incorrect for this ROM version."
                    )

            # Parse HAL format to find actual compressed block size
            # Falls back to conservative heuristic if parsing fails
            compressed_size = self._parse_hal_compressed_size(bytes(rom_data), offset)

            # Validate compression ratio is reasonable (HAL typically achieves 30-70%)
            # This helps detect parser errors like incorrect terminator detection
            if original_size > 0:
                compression_ratio = compressed_size / original_size
                if compression_ratio < 0.05:
                    logger.warning(
                        f"Unusually low compression ratio ({compression_ratio:.2%}): "
                        f"compressed={compressed_size}, decompressed={original_size}. "
                        f"Parser may have found terminator too early."
                    )
                elif compression_ratio > 2.0:
                    logger.warning(
                        f"Compression ratio > 200% ({compression_ratio:.2%}): "
                        f"compressed={compressed_size}, decompressed={original_size}. "
                        f"Parser may have overestimated compressed size."
                    )

            logger.debug(
                f"Decompressed {original_size} bytes (truncated to {len(decompressed)} bytes), "
                f"estimated compressed size: {compressed_size} bytes"
            )
            return compressed_size, decompressed

        finally:
            Path(tmp_rom).unlink(missing_ok=True)

    def _validate_sprite_data(self, data: bytes) -> bool:
        """
        Validate if data appears to be valid sprite data.

        Samples tiles throughout the data (not just the first few) to catch
        cases where the beginning is valid but the rest is garbage.

        Args:
            data: Decompressed data to validate

        Returns:
            True if data appears to be valid sprite data
        """
        if len(data) == 0:
            return False

        # Check if data is tile-aligned
        if len(data) % BYTES_PER_TILE != 0:
            return False

        num_tiles = len(data) // BYTES_PER_TILE

        # Sample tiles throughout the data, not just the beginning
        # For small sprite: check all tiles (up to 10)
        # For large sprite: sample evenly distributed tiles
        max_samples = 10
        if num_tiles <= max_samples:
            # Check all tiles for small sprites
            tile_indices = list(range(num_tiles))
        else:
            # Sample evenly throughout the data
            step = num_tiles // max_samples
            tile_indices = [i * step for i in range(max_samples)]
            # Always include the last tile to catch truncation issues
            if tile_indices[-1] != num_tiles - 1:
                tile_indices[-1] = num_tiles - 1

        valid_tiles = 0
        tiles_to_check = len(tile_indices)

        for tile_idx in tile_indices:
            tile_offset = tile_idx * BYTES_PER_TILE
            tile_data = data[tile_offset : tile_offset + BYTES_PER_TILE]

            # Check for 4bpp characteristics
            if self._has_4bpp_tile_characteristics(tile_data):
                valid_tiles += 1

        # Threshold defined in utils/constants.py - see SPRITE_VALIDATION_THRESHOLD docs
        validity_ratio = valid_tiles / tiles_to_check
        logger.debug(f"Sprite data validation: {valid_tiles}/{tiles_to_check} tiles valid ({validity_ratio:.1%})")

        return validity_ratio >= SPRITE_VALIDATION_THRESHOLD

    def _has_4bpp_tile_characteristics(self, tile_data: bytes) -> bool:
        """
        Check if a single tile has characteristics of 4bpp sprite data.

        Args:
            tile_data: BYTES_PER_TILE bytes of tile data (32 for 4bpp)

        Returns:
            True if tile appears to be valid 4bpp data
        """
        if len(tile_data) != BYTES_PER_TILE:
            return False

        # Check for variety in bitplanes (not all 0 or all FF)
        # 4bpp has 4 bitplanes organized in specific pattern
        bitplane_stats = {"zeros": 0, "ones": 0, "varied": 0}

        # Check all 4 bitplanes
        for plane_start in [0, 1, 16, 17]:  # Bitplane starting positions
            plane_bytes = [tile_data[plane_start + i * 2] for i in range(8)]

            if all(b == 0 for b in plane_bytes):
                bitplane_stats["zeros"] += 1
            elif all(b == 0xFF for b in plane_bytes):
                bitplane_stats["ones"] += 1
            else:
                bitplane_stats["varied"] += 1

        # Good sprite data should have variety, not all blank/full bitplanes
        # Allow some blank planes but require at least 2 varied planes
        return bitplane_stats["varied"] >= 2

    def _find_sprite_in_data(self, data: bytes, expected_size: int) -> int:
        """
        Search for valid sprite data within a larger data block.

        Args:
            data: Large data block to search within
            expected_size: Expected size of sprite data

        Returns:
            Offset where valid sprite data starts, or -1 if not found
        """
        # Only search at tile boundaries
        max_offset = len(data) - expected_size
        if max_offset < 0:
            return -1

        # Try common alignment points first
        common_offsets = [0, 0x100, 0x200, 0x400, 0x800, 0x1000]

        for test_offset in common_offsets:
            if test_offset > max_offset:
                break

            test_data = data[test_offset : test_offset + expected_size]
            if self._validate_sprite_data(test_data):
                return test_offset

        # If common offsets fail, scan tile by tile (slower)
        logger.debug("Common offsets failed, scanning tile boundaries...")
        for test_offset in range(0, min(max_offset, 0x2000), BYTES_PER_TILE):
            test_data = data[test_offset : test_offset + expected_size]
            if self._validate_sprite_data(test_data):
                return test_offset

        return -1

    def _parse_hal_compressed_size(self, rom_data: bytes, offset: int) -> int:
        """
        Parse HAL compression stream to find actual compressed block size.

        HAL compression format (verified from exhal compress.c):
        - No header - starts directly with command bytes
        - Command byte determines type and length:
          - If (cmd & 0xE0) == 0xE0: Long command
            - command = (cmd >> 2) & 0x07
            - length = (((cmd & 0x03) << 8) | next_byte) + 1
          - Else: Short command
            - command = cmd >> 5
            - length = (cmd & 0x1F) + 1
        - Commands:
          - 0: Raw bytes (length bytes follow in stream)
          - 1: 8-bit RLE (1 byte follows)
          - 2: 16-bit RLE (2 bytes follow)
          - 3: Sequence RLE (1 byte follows)
          - 4,7: Forward backref (2 bytes offset follow)
          - 5: Rotated backref (2 bytes offset follow)
          - 6: Backward backref (2 bytes offset follow)
        - 0xFF terminates the stream

        Returns:
            Actual compressed block size in bytes
        """
        logger.debug(f"Parsing HAL compressed size at offset 0x{offset:X}")

        max_pos = min(offset + 0x10000, len(rom_data))  # Cap at 64KB
        pos = offset

        try:
            while pos < max_pos:
                if pos >= len(rom_data):
                    break

                cmd = rom_data[pos]
                pos += 1

                # 0xFF terminates the stream
                if cmd == 0xFF:
                    compressed_size = pos - offset
                    logger.debug(f"HAL parsing complete: compressed={compressed_size} bytes")
                    return compressed_size

                # Decode command and length
                if (cmd & 0xE0) == 0xE0:
                    # Long command
                    if pos >= len(rom_data):
                        logger.warning(f"Truncated long command at 0x{pos:X}")
                        return pos - offset
                    command = (cmd >> 2) & 0x07
                    length = (((cmd & 0x03) << 8) | rom_data[pos]) + 1
                    pos += 1
                else:
                    # Short command
                    command = cmd >> 5
                    length = (cmd & 0x1F) + 1

                # Consume data bytes based on command type
                if command == 0:
                    # Raw: length bytes follow
                    pos += length
                elif command == 1:
                    # 8-bit RLE: 1 byte follows
                    pos += 1
                elif command == 2:
                    # 16-bit RLE: 2 bytes follow
                    pos += 2
                elif command == 3:
                    # Sequence RLE: 1 byte follows
                    pos += 1
                elif command in (4, 5, 6, 7):
                    # Backreferences: 2 bytes offset follow
                    pos += 2
                else:
                    # Unknown command - treat as end
                    logger.warning(f"Unknown HAL command {command} at 0x{pos:X}")
                    break

            # No terminator found within limit
            compressed_size = pos - offset
            logger.debug(f"HAL parsing reached limit without terminator: size={compressed_size} bytes")
            return compressed_size

        except Exception as e:
            logger.warning(f"HAL parsing failed at 0x{pos:X}: {e}, falling back to heuristic")
            return self._estimate_compressed_size_conservative(rom_data, offset)

    def _estimate_compressed_size_conservative(self, rom_data: bytes, offset: int) -> int:
        """
        Conservative fallback: require longer padding runs to reduce false positives.

        Uses 64-byte runs of 0x00/0xFF to reduce the chance that legitimate
        compressed data containing white sprite regions (0xFF) or empty areas (0x00)
        triggers early termination.

        This is a fallback when HAL parsing fails - results should be treated
        as approximate and validated against actual decompression output.
        """
        logger.warning(
            f"Using conservative size estimation at offset 0x{offset:X} - HAL parsing failed, result may be inaccurate"
        )
        max_size = min(0x10000, len(rom_data) - offset)  # Max 64KB

        # Require 64 consecutive bytes of padding to avoid truncating
        # valid sprite data that contains white regions (0xFF) or empty areas
        padding_threshold = 64
        for i in range(64, max_size, 2):
            if rom_data[offset + i : offset + i + padding_threshold] == b"\xff" * padding_threshold:
                logger.debug(f"Found 0xFF padding at offset+{i}")
                return i
            if rom_data[offset + i : offset + i + padding_threshold] == b"\x00" * padding_threshold:
                logger.debug(f"Found 0x00 padding at offset+{i}")
                return i

        # Default estimate - use 8KB instead of 4KB to be more conservative
        logger.debug("Using default compressed size estimate: 8KB")
        return 0x2000  # 8KB default (was 4KB)

    def inject_sprite_to_rom(
        self,
        sprite_path: str,
        rom_path: str,
        output_path: str,
        sprite_offset: int,
        fast_compression: bool = False,
        create_backup: bool = True,
    ) -> tuple[bool, str]:
        """
        Inject sprite directly into ROM file with validation and backup.

        Args:
            sprite_path: Path to edited sprite PNG
            rom_path: Path to input ROM
            output_path: Path for output ROM
            sprite_offset: Offset in ROM where sprite data is located
            fast_compression: Use fast compression mode
            create_backup: Create backup before modification

        Returns:
            Tuple of (success, message)
        """
        try:
            start_time = time.time()
            logger.info(f"Starting ROM injection: {Path(sprite_path).name} -> offset 0x{sprite_offset:X}")

            # Validate ROM before modification
            _header_info, _header_offset = ROMValidator.validate_rom_for_injection(rom_path, sprite_offset)

            # Create backup if requested - ABORT if backup fails
            backup_path = None
            if create_backup:
                try:
                    backup_path = ROMBackupManager.create_backup(rom_path)
                    logger.info(f"Created backup: {backup_path}")
                except Exception as e:
                    logger.error(f"Backup creation failed: {e}")
                    return False, (
                        f"Cannot proceed: backup creation failed ({e}). "
                        "Refusing to modify ROM without a backup. "
                        "Free up disk space or fix permissions and retry."
                    )

            # Read ROM header (using improved method)
            self.header = self.read_rom_header(rom_path)

            # Load ROM data
            with Path(rom_path).open("rb") as f:
                self.rom_data = bytearray(f.read())

            # Adjust sprite offset for SMC header (ROM offset -> file offset)
            smc_offset = self.header.header_offset
            file_offset = sprite_offset + smc_offset
            if smc_offset > 0:
                logger.info(
                    f"Adjusting for {smc_offset}-byte SMC header: "
                    f"ROM offset 0x{sprite_offset:X} -> file offset 0x{file_offset:X}"
                )

            # Convert PNG to 4bpp
            logger.info("Converting PNG to 4bpp tile data")
            tile_data = self.convert_png_to_4bpp(sprite_path)
            logger.debug(f"Converted to {len(tile_data)} bytes of 4bpp data")

            # Find and decompress original sprite for size comparison
            logger.info("Analyzing original sprite data in ROM")
            original_size, original_data = self.find_compressed_sprite(self.rom_data, file_offset)
            logger.debug(f"Original sprite: {original_size} bytes compressed, {len(original_data)} bytes decompressed")

            # Compress new sprite data
            # FIX #1: Use try-finally to guarantee temp file cleanup on any error
            compressed_path: str | None = None
            try:
                compression_start = time.time()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
                    compressed_path = tmp.name

                compressed_size = self.hal_compressor.compress_to_file(
                    tile_data, compressed_path, fast=fast_compression
                )
                compression_time = time.time() - compression_start
                logger.debug(f"Compression took {compression_time:.2f} seconds")

                # Calculate compression statistics
                uncompressed_size = len(tile_data)
                if uncompressed_size == 0:
                    return False, "Cannot compress empty sprite data"
                compression_ratio = (uncompressed_size - compressed_size) / uncompressed_size * 100
                space_saved = original_size - compressed_size
                compression_mode = "fast" if fast_compression else "standard"

                logger.info(f"Compression statistics ({compression_mode} mode):")
                logger.info(f"  - Uncompressed size: {uncompressed_size} bytes")
                logger.info(f"  - Compressed size: {compressed_size} bytes")
                logger.info(f"  - Compression ratio: {compression_ratio:.1f}%")
                logger.info(f"  - Space saved vs original: {space_saved} bytes")

                # Check if compressed data fits
                if compressed_size > original_size:
                    suggestion = (
                        "standard compression" if fast_compression else "a smaller sprite or split it into parts"
                    )
                    return False, (
                        f"Compressed sprite too large: {compressed_size} bytes "
                        f"(original: {original_size} bytes).\n"
                        f"Compression ratio: {compression_ratio:.1f}%\n"
                        f"Try using {suggestion}."
                    )

                # Read compressed data
                with Path(compressed_path).open("rb") as f:
                    compressed_data = f.read()
            finally:
                # FIX #1: Always clean up temp file, even on exception or early return
                if compressed_path is not None:
                    Path(compressed_path).unlink(missing_ok=True)

            # FIX #4: Work on a copy of ROM data to prevent state corruption on write failure
            # Only update self.rom_data after successful write
            modified_rom = bytearray(self.rom_data)

            # Inject compressed data into ROM copy
            # Bounds validation to prevent ROM corruption
            if file_offset + compressed_size > len(modified_rom):
                raise ValueError(
                    f"Sprite data would overflow ROM: file offset 0x{file_offset:X} + "
                    f"{compressed_size} bytes exceeds ROM size {len(modified_rom)}"
                )
            logger.info(f"Injecting {compressed_size} bytes of compressed data at ROM offset 0x{sprite_offset:X}")
            modified_rom[file_offset : file_offset + compressed_size] = compressed_data

            # Pad remaining space if needed
            if compressed_size < original_size:
                padding = b"\xff" * (original_size - compressed_size)
                modified_rom[file_offset + compressed_size : file_offset + original_size] = padding
                logger.info(f"Padded {original_size - compressed_size} bytes with 0xFF")

            # Update checksum on the copy
            self.update_rom_checksum(modified_rom)

            # Write output ROM atomically (prevents corruption on crash/power loss)
            logger.info(f"Writing modified ROM to: {output_path}")
            atomic_write(output_path, bytes(modified_rom))
            logger.debug(f"Successfully wrote {len(modified_rom)} bytes to output ROM")

            # FIX #4: Only commit changes after successful write
            self.rom_data = modified_rom

            total_time = time.time() - start_time
            logger.info(f"ROM injection completed in {total_time:.2f} seconds")

        except HALCompressionError as e:
            return False, f"Compression error: {e!s}"
        except Exception as e:
            return False, f"ROM injection error: {e!s}"
        else:
            return True, (
                f"Successfully injected sprite at 0x{sprite_offset:X}\n"
                f"Original size: {original_size} bytes\n"
                f"New size: {compressed_size} bytes ({compression_ratio:.1f}% compression)\n"
                f"Space saved: {space_saved} bytes\n"
                f"Compression mode: {compression_mode}\n"
                f"Checksum updated: 0x{self.header.checksum:04X}\n"
                f"Total time: {total_time:.2f} seconds"
            )

    def find_sprite_locations(self, rom_path: str) -> dict[str, SpritePointer]:
        """
        Find sprite locations for the given ROM using configuration data.
        """
        logger.info(f"Finding sprite locations for ROM: {rom_path}")
        pointers = {}

        # Read ROM header to get title and checksum
        try:
            header = self.read_rom_header(rom_path)

            # Get sprite configurations for this ROM
            sprite_configs = self.sprite_config_loader.get_game_sprites(header.title, header.checksum)

            # Convert configs to SpritePointer objects
            for name, config in sprite_configs.items():
                bank = (config.offset >> 16) & 0xFF
                address = config.offset & 0xFFFF
                pointer = SpritePointer(
                    offset=config.offset,
                    bank=bank,
                    address=address,
                    compressed_size=config.estimated_size,
                )
                # Store offset variants if available
                if hasattr(config, "offset_variants") and config.offset_variants:
                    pointer.offset_variants = config.offset_variants
                pointers[name] = pointer

            if not pointers:
                logger.warning(f"No sprite locations found for ROM: {header.title}")
            else:
                logger.info(f"Found {len(pointers)} sprite locations for ROM: {header.title}")
                for name, pointer in pointers.items():
                    logger.debug(
                        f"  {name}: offset=0x{pointer.offset:X}, bank=0x{pointer.bank:02X}, size={pointer.compressed_size}"
                    )

        except Exception:
            logger.exception("Failed to find sprite locations")

        return pointers

    def find_compressed_sprite_with_fallback(
        self,
        rom_data: bytes,
        primary_offset: int,
        fallback_offsets: list[int] | None = None,
        expected_size: int | None = None,
    ) -> tuple[int, bytes, int]:
        """
        Try to find and decompress sprite data with fallback offsets.

        Args:
            rom_data: ROM data
            primary_offset: Primary offset to try
            fallback_offsets: Alternative offsets to try if primary fails
            expected_size: Expected decompressed size (will truncate if larger)

        Returns:
            Tuple of (compressed_size, decompressed_data, successful_offset)
        """
        offsets_to_try = [primary_offset]
        if fallback_offsets:
            offsets_to_try.extend(fallback_offsets)

        logger.info(f"Attempting sprite decompression with {len(offsets_to_try)} offset(s)")

        last_error = None
        for i, offset in enumerate(offsets_to_try):
            logger.debug(f"Trying offset {i + 1}/{len(offsets_to_try)}: 0x{offset:X}")
            try:
                compressed_size, decompressed = self.find_compressed_sprite(rom_data, offset, expected_size)

                # Check if data is valid (multiple of tile size)
                extra_bytes = len(decompressed) % BYTES_PER_TILE

                if extra_bytes == 0:
                    logger.info(f"Successfully decompressed sprite at offset 0x{offset:X} (perfectly aligned)")
                    return compressed_size, decompressed, offset
                if extra_bytes <= BYTES_PER_TILE // 4:  # Allow up to 8 extra bytes
                    logger.info(
                        f"Successfully decompressed sprite at offset 0x{offset:X} (minor misalignment: {extra_bytes} extra bytes)"
                    )
                    return compressed_size, decompressed, offset
                logger.warning(
                    f"Offset 0x{offset:X} produced misaligned data ({extra_bytes} extra bytes), trying next offset"
                )
                continue

            except Exception as e:
                last_error = e
                logger.debug(f"Offset 0x{offset:X} failed: {e}")
                continue

        # All offsets failed
        if last_error:
            raise last_error
        raise ValueError("No valid sprite data found at any of the provided offsets")
