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
from core.rom_validator import ROMValidator
from core.sprite_config_loader import SpriteConfigLoader
from utils.constants import (
    ROM_CHECKSUM_COMPLEMENT_MASK,
    ROM_HEADER_OFFSET_HIROM,
    ROM_HEADER_OFFSET_LOROM,
    SMC_HEADER_SIZE,
)
from utils.file_validator import atomic_write
from utils.logging_config import get_logger
from utils.rom_backup import ROMBackupManager

logger = get_logger(__name__)

@dataclass
class ROMHeader:
    """SNES ROM header information"""

    title: str
    rom_type: int
    rom_size: int
    sram_size: int
    checksum: int
    checksum_complement: int
    header_offset: int
    rom_type_offset: int  # 0x7FC0 for LoROM, 0xFFC0 for HiROM

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
        """Read and parse SNES ROM header"""
        logger.info(f"Reading ROM header from: {rom_path}")
        with Path(rom_path).open("rb") as f:
            # Try to detect header offset (SMC header is 512 bytes)
            f.seek(0)
            f.read(SMC_HEADER_SIZE)

            # Check for SMC header
            header_offset = 0
            rom_size = Path(rom_path).stat().st_size
            if rom_size % 1024 == SMC_HEADER_SIZE:
                header_offset = SMC_HEADER_SIZE
                logger.debug(f"SMC header detected ({SMC_HEADER_SIZE} bytes), ROM size: {rom_size} bytes")
            else:
                logger.debug(f"No SMC header detected, ROM size: {rom_size} bytes")

            # Read header at expected location
            # SNES header is typically at 0x7FC0 or 0xFFC0 depending on ROM type
            for offset in [ROM_HEADER_OFFSET_LOROM, ROM_HEADER_OFFSET_HIROM]:
                f.seek(header_offset + offset)
                header_data = f.read(32)

                # Parse header
                title = header_data[0:21].decode("ascii", errors="ignore").strip()
                rom_type = header_data[21]
                rom_size = header_data[23]
                sram_size = header_data[24]
                checksum_complement = struct.unpack("<H", header_data[28:30])[0]
                checksum = struct.unpack("<H", header_data[30:32])[0]

                # Verify checksum to ensure valid header
                if (checksum ^ checksum_complement) == ROM_CHECKSUM_COMPLEMENT_MASK:
                    self.header = ROMHeader(
                        title=title,
                        rom_type=rom_type,
                        rom_size=rom_size,
                        sram_size=sram_size,
                        checksum=checksum,
                        checksum_complement=checksum_complement,
                        header_offset=header_offset,
                        rom_type_offset=offset,  # Store which offset was validated
                    )
                    logger.info(f"Found valid ROM header at offset 0x{header_offset + offset:X}")
                    logger.debug(f"ROM Title: {title}")
                    logger.debug(f"ROM Type: 0x{rom_type:02X}")
                    logger.debug(f"Checksum: 0x{checksum:04X}, Complement: 0x{checksum_complement:04X}")
                    return self.header
                logger.debug(f"Invalid checksum at offset 0x{header_offset + offset:X}")

        raise ValueError("Could not find valid SNES ROM header")

    def calculate_checksum(self, rom_data: bytes | bytearray) -> tuple[int, int]:
        """Calculate SNES ROM checksum and complement"""
        logger.debug("Calculating ROM checksum")
        # Skip SMC header if present
        offset = self.header.header_offset if self.header else 0
        data = rom_data[offset:]

        # Calculate checksum
        checksum = 0
        for i in range(0, len(data), 2):
            word = data[i + 1] << 8 | data[i] if i + 1 < len(data) else data[i]
            checksum = (checksum + word) & ROM_CHECKSUM_COMPLEMENT_MASK

        # Calculate complement
        complement = checksum ^ ROM_CHECKSUM_COMPLEMENT_MASK

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
        default_max_sprite_size = 32768  # 32KB - reasonable max for SNES sprites

        if expected_size:
            logger.debug(f"Expected decompressed size: {expected_size} bytes")
        else:
            # Apply default size limit to prevent the 42KB issue
            expected_size = default_max_sprite_size
            logger.warning(
                f"No expected size provided, using default max limit: {expected_size} bytes"
            )

        # Create temp file for decompression with only the relevant portion
        # Extract a window from offset to offset + 128KB (or end of ROM)
        # This reduces memory/disk usage from 4MB to ~128KB per operation
        window_size = 0x20000  # 128KB window - sufficient for any SNES sprite
        window_end = min(len(rom_data), offset + window_size)
        rom_window = rom_data[offset:window_end]
        adjusted_offset = 0  # Offset within the window

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(rom_window)
            tmp_rom = tmp.name

        try:
            # Decompress sprite data from the window
            decompressed = self.hal_compressor.decompress_from_rom(tmp_rom, adjusted_offset)

            # Validate decompressed data
            if len(decompressed) == 0:
                raise ValueError("Decompression produced no data")

            original_size = len(decompressed)

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

                    # Try to find valid sprite data within the full decompressed data
                    # Need to use the original full data, not truncated
                    full_data = self.hal_compressor.decompress_from_rom(tmp_rom, adjusted_offset)
                    sprite_offset = self._find_sprite_in_data(full_data, expected_size)
                    if sprite_offset >= 0:
                        logger.info(
                            f"Found valid sprite data at offset {sprite_offset} within decompressed block"
                        )
                        decompressed = full_data[sprite_offset:sprite_offset + expected_size]
                    else:
                        logger.warning(
                            "Could not find valid sprite data. Consider using sprite scanner."
                        )
            elif expected_size and len(decompressed) < expected_size:
                logger.warning(
                    f"Decompressed data ({original_size} bytes) is smaller than expected "
                    f"({expected_size} bytes). This may indicate a problem."
                )

            # Check if data size is valid for sprite tiles (should be multiple of 32)
            bytes_per_tile = 32
            extra_bytes = len(decompressed) % bytes_per_tile
            if extra_bytes != 0:
                logger.warning(
                    f"Decompressed data size ({len(decompressed)} bytes) is not a multiple of {bytes_per_tile}. "
                    f"Extra bytes: {extra_bytes}. This may indicate incorrect offset or corrupted data."
                )

                # If more than half a tile of extra data, likely wrong offset
                if extra_bytes > bytes_per_tile // 2:
                    logger.error(
                        f"Significant data misalignment detected ({extra_bytes} extra bytes). "
                        f"The sprite offset 0x{offset:X} is likely incorrect for this ROM version."
                    )

            # Estimate compressed size by searching for next compressed data
            # This is a heuristic - in practice we'd need better tracking
            compressed_size = self._estimate_compressed_size(bytes(rom_data), offset)

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

        Args:
            data: Decompressed data to validate

        Returns:
            True if data appears to be valid sprite data
        """
        if len(data) == 0:
            return False

        bytes_per_tile = 32

        # Check if data is tile-aligned
        if len(data) % bytes_per_tile != 0:
            return False

        num_tiles = len(data) // bytes_per_tile

        # Sample several tiles to check for sprite characteristics
        tiles_to_check = min(10, num_tiles)
        valid_tiles = 0

        for i in range(tiles_to_check):
            tile_offset = i * bytes_per_tile
            tile_data = data[tile_offset:tile_offset + bytes_per_tile]

            # Check for 4bpp characteristics
            if self._has_4bpp_tile_characteristics(tile_data):
                valid_tiles += 1

        # Require at least 60% of sampled tiles to be valid
        validity_ratio = valid_tiles / tiles_to_check
        logger.debug(f"Sprite data validation: {valid_tiles}/{tiles_to_check} tiles valid ({validity_ratio:.1%})")

        return validity_ratio >= 0.6

    def _has_4bpp_tile_characteristics(self, tile_data: bytes) -> bool:
        """
        Check if a single tile has characteristics of 4bpp sprite data.

        Args:
            tile_data: 32 bytes of tile data

        Returns:
            True if tile appears to be valid 4bpp data
        """
        if len(tile_data) != 32:
            return False

        # Check for variety in bitplanes (not all 0 or all FF)
        # 4bpp has 4 bitplanes organized in specific pattern
        bitplane_stats = {
            "zeros": 0,
            "ones": 0,
            "varied": 0
        }

        # Check all 4 bitplanes
        for plane_start in [0, 1, 16, 17]:  # Bitplane starting positions
            plane_bytes = [tile_data[plane_start + i*2] for i in range(8)]

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
        bytes_per_tile = 32

        # Only search at tile boundaries
        max_offset = len(data) - expected_size
        if max_offset < 0:
            return -1

        # Try common alignment points first
        common_offsets = [0, 0x100, 0x200, 0x400, 0x800, 0x1000]

        for test_offset in common_offsets:
            if test_offset > max_offset:
                break

            test_data = data[test_offset:test_offset + expected_size]
            if self._validate_sprite_data(test_data):
                return test_offset

        # If common offsets fail, scan tile by tile (slower)
        logger.debug("Common offsets failed, scanning tile boundaries...")
        for test_offset in range(0, min(max_offset, 0x2000), bytes_per_tile):
            test_data = data[test_offset:test_offset + expected_size]
            if self._validate_sprite_data(test_data):
                return test_offset

        return -1

    def _estimate_compressed_size(self, rom_data: bytes, offset: int) -> int:
        """Estimate size of compressed data (heuristic)"""
        logger.debug(f"Estimating compressed size at offset 0x{offset:X}")
        # This is a simplified approach - real implementation would need
        # to parse the compression format or use known sizes
        # For now, scan for typical compression end patterns
        max_size = min(0x10000, len(rom_data) - offset)  # Max 64KB

        # Look for common patterns that indicate end of compressed data
        for i in range(32, max_size, 2):
            # Check for alignment padding (series of 0xFF or 0x00)
            if rom_data[offset + i : offset + i + 16] == b"\xff" * 16:
                return i
            if rom_data[offset + i : offset + i + 16] == b"\x00" * 16:
                return i

        # Default estimate
        logger.debug("Using default compressed size estimate: 4KB")
        return 0x1000  # 4KB default

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
            logger.info(
                f"Starting ROM injection: {Path(sprite_path).name} -> offset 0x{sprite_offset:X}"
            )

            # Validate ROM before modification
            _header_info, _header_offset = ROMValidator.validate_rom_for_injection(
                rom_path, sprite_offset
            )

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

            # Convert PNG to 4bpp
            logger.info("Converting PNG to 4bpp tile data")
            tile_data = self.convert_png_to_4bpp(sprite_path)
            logger.debug(f"Converted to {len(tile_data)} bytes of 4bpp data")

            # Find and decompress original sprite for size comparison
            logger.info("Analyzing original sprite data in ROM")
            original_size, original_data = self.find_compressed_sprite(
                self.rom_data, sprite_offset
            )
            logger.debug(f"Original sprite: {original_size} bytes compressed, {len(original_data)} bytes decompressed")

            # Compress new sprite data
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
                Path(compressed_path).unlink(missing_ok=True)
                return False, "Cannot compress empty sprite data"
            compression_ratio = (
                (uncompressed_size - compressed_size) / uncompressed_size * 100
            )
            space_saved = original_size - compressed_size
            compression_mode = "fast" if fast_compression else "standard"

            logger.info(f"Compression statistics ({compression_mode} mode):")
            logger.info(f"  - Uncompressed size: {uncompressed_size} bytes")
            logger.info(f"  - Compressed size: {compressed_size} bytes")
            logger.info(f"  - Compression ratio: {compression_ratio:.1f}%")
            logger.info(f"  - Space saved vs original: {space_saved} bytes")

            # Check if compressed data fits
            if compressed_size > original_size:
                Path(compressed_path).unlink(missing_ok=True)
                suggestion = (
                    "standard compression"
                    if fast_compression
                    else "a smaller sprite or split it into parts"
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
            Path(compressed_path).unlink(missing_ok=True)

            # Inject compressed data into ROM
            # Bounds validation to prevent ROM corruption
            if sprite_offset + compressed_size > len(self.rom_data):
                raise ValueError(
                    f"Sprite data would overflow ROM: offset 0x{sprite_offset:X} + "
                    f"{compressed_size} bytes exceeds ROM size {len(self.rom_data)}"
                )
            logger.info(f"Injecting {compressed_size} bytes of compressed data at offset 0x{sprite_offset:X}")
            self.rom_data[sprite_offset : sprite_offset + compressed_size] = (
                compressed_data
            )

            # Pad remaining space if needed
            if compressed_size < original_size:
                padding = b"\xff" * (original_size - compressed_size)
                self.rom_data[
                    sprite_offset + compressed_size : sprite_offset + original_size
                ] = padding
                logger.info(f"Padded {original_size - compressed_size} bytes with 0xFF")

            # Update checksum
            self.update_rom_checksum(self.rom_data)

            # Write output ROM atomically (prevents corruption on crash/power loss)
            logger.info(f"Writing modified ROM to: {output_path}")
            atomic_write(output_path, bytes(self.rom_data))
            logger.debug(f"Successfully wrote {len(self.rom_data)} bytes to output ROM")

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
            sprite_configs = self.sprite_config_loader.get_game_sprites(
                header.title, header.checksum
            )

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
                    logger.debug(f"  {name}: offset=0x{pointer.offset:X}, bank=0x{pointer.bank:02X}, size={pointer.compressed_size}")

        except Exception:
            logger.exception("Failed to find sprite locations")

        return pointers

    def find_compressed_sprite_with_fallback(
        self, rom_data: bytes, primary_offset: int, fallback_offsets: list[int] | None = None,
        expected_size: int | None = None
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
            logger.debug(f"Trying offset {i+1}/{len(offsets_to_try)}: 0x{offset:X}")
            try:
                compressed_size, decompressed = self.find_compressed_sprite(
                    rom_data, offset, expected_size
                )

                # Check if data is valid (multiple of tile size)
                bytes_per_tile = 32
                extra_bytes = len(decompressed) % bytes_per_tile

                if extra_bytes == 0:
                    logger.info(f"Successfully decompressed sprite at offset 0x{offset:X} (perfectly aligned)")
                    return compressed_size, decompressed, offset
                if extra_bytes <= bytes_per_tile // 4:  # Allow up to 8 extra bytes
                    logger.info(f"Successfully decompressed sprite at offset 0x{offset:X} (minor misalignment: {extra_bytes} extra bytes)")
                    return compressed_size, decompressed, offset
                logger.warning(f"Offset 0x{offset:X} produced misaligned data ({extra_bytes} extra bytes), trying next offset")
                continue

            except Exception as e:
                last_error = e
                logger.debug(f"Offset 0x{offset:X} failed: {e}")
                continue

        # All offsets failed
        if last_error:
            raise last_error
        raise ValueError("No valid sprite data found at any of the provided offsets")
