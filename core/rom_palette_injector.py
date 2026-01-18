"""
ROM palette injection functionality for SpritePal.

Handles injection of modified palette data (32 bytes BGR555) into ROM files.
"""

from __future__ import annotations

from pathlib import Path

from core.rom_validator import ROMValidator
from utils.constants import CGRAM_PALETTE_SIZE, COLORS_PER_PALETTE
from utils.file_validator import atomic_write
from utils.logging_config import get_logger

logger = get_logger(__name__)


class ROMPaletteInjector:
    """Handles palette injection directly into ROM files."""

    def __init__(self) -> None:
        """Initialize ROM palette injector."""
        logger.debug("ROMPaletteInjector initialized")

    @staticmethod
    def rgb888_to_bgr555(r: int, g: int, b: int) -> int:
        """
        Convert 8-bit RGB to 16-bit BGR555.

        This is the inverse of the extraction formula used in ROMPaletteExtractor.
        The 8-bit to 5-bit conversion uses simple bit shifting (>>3), which may
        result in slight color differences due to quantization.

        Args:
            r: Red component (0-255)
            g: Green component (0-255)
            b: Blue component (0-255)

        Returns:
            16-bit BGR555 value (0-32767)
        """
        # Clamp values to valid range
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))

        # Convert 8-bit to 5-bit
        r5 = (r >> 3) & 0x1F
        g5 = (g >> 3) & 0x1F
        b5 = (b >> 3) & 0x1F

        # Combine into BGR555 format
        bgr555 = (b5 << 10) | (g5 << 5) | r5
        return bgr555

    @staticmethod
    def colors_to_bgr555_bytes(colors: list[tuple[int, int, int]]) -> bytes:
        """
        Convert a list of RGB color tuples to BGR555 byte data.

        Args:
            colors: List of 16 RGB color tuples [(r, g, b), ...]

        Returns:
            32 bytes of BGR555 palette data (little-endian)

        Raises:
            ValueError: If colors list doesn't contain exactly 16 colors
        """
        if len(colors) != COLORS_PER_PALETTE:
            raise ValueError(f"Expected {COLORS_PER_PALETTE} colors, got {len(colors)}")

        result = bytearray(CGRAM_PALETTE_SIZE)

        for i, (r, g, b) in enumerate(colors):
            bgr555 = ROMPaletteInjector.rgb888_to_bgr555(r, g, b)
            # Little-endian byte order
            offset = i * 2
            result[offset] = bgr555 & 0xFF
            result[offset + 1] = (bgr555 >> 8) & 0xFF

        return bytes(result)

    def inject_palette_to_rom(
        self,
        rom_path: str,
        output_path: str,
        palette_offset: int,
        colors: list[tuple[int, int, int]],
        *,
        create_backup: bool = True,
        ignore_checksum: bool = False,
    ) -> tuple[bool, str]:
        """
        Inject palette data directly into ROM file.

        Args:
            rom_path: Path to input ROM
            output_path: Path for output ROM
            palette_offset: Offset in ROM where palette data is located
            colors: List of 16 RGB color tuples to inject
            create_backup: Create backup before modification (if output == input)
            ignore_checksum: If True, warn on checksum mismatch instead of failing

        Returns:
            Tuple of (success, message)
        """
        try:
            logger.info(f"Starting palette injection at offset 0x{palette_offset:X}")

            # Validate colors
            if len(colors) != COLORS_PER_PALETTE:
                return False, f"Expected {COLORS_PER_PALETTE} colors, got {len(colors)}"

            # Convert colors to BGR555 bytes
            palette_bytes = self.colors_to_bgr555_bytes(colors)
            logger.debug(f"Converted palette to {len(palette_bytes)} bytes")

            # Validate ROM
            header_info, _ = ROMValidator.validate_rom_for_injection(
                rom_path, palette_offset, lenient_checksum=ignore_checksum
            )

            # Load ROM data
            rom_path_obj = Path(rom_path)
            with rom_path_obj.open("rb") as f:
                rom_data = bytearray(f.read())

            # Adjust for SMC header
            smc_offset = header_info.header_offset
            file_offset = palette_offset + smc_offset
            if smc_offset > 0:
                logger.info(
                    f"Adjusting for {smc_offset}-byte SMC header: "
                    f"ROM offset 0x{palette_offset:X} -> file offset 0x{file_offset:X}"
                )

            # Validate offset bounds
            if file_offset + CGRAM_PALETTE_SIZE > len(rom_data):
                return False, (
                    f"Palette offset 0x{palette_offset:X} would overflow ROM "
                    f"(file offset 0x{file_offset:X} + {CGRAM_PALETTE_SIZE} bytes "
                    f"> ROM size {len(rom_data)})"
                )

            # Read original palette for logging
            original_bytes = rom_data[file_offset : file_offset + CGRAM_PALETTE_SIZE]
            logger.debug(f"Original palette bytes: {original_bytes.hex()}")

            # Create ROM copy if output differs from input
            if output_path != rom_path:
                import shutil

                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(rom_path, output_path)
                logger.info(f"Created ROM copy: {rom_path} -> {output_path}")
            elif create_backup:
                from utils.rom_backup import ROMBackupManager

                try:
                    backup_path = ROMBackupManager.create_backup(rom_path)
                    logger.info(f"Created backup: {backup_path}")
                except Exception as e:
                    logger.error(f"Backup creation failed: {e}")
                    return False, f"Backup creation failed: {e}"

            # Inject palette bytes
            rom_data[file_offset : file_offset + CGRAM_PALETTE_SIZE] = palette_bytes
            logger.info(f"Injected {CGRAM_PALETTE_SIZE} bytes at offset 0x{file_offset:X}")

            # Update checksum
            # header_info.header_offset is SMC offset (0 or 512)
            # header_info.rom_type_offset is SNES header base (0x7FC0 for LoROM)
            header_base = header_info.header_offset + header_info.rom_type_offset
            checksum, complement = ROMValidator.calculate_checksum(rom_data, smc_offset)

            # Write checksum to ROM data
            # SNES header layout: complement at +28, checksum at +30
            checksum_offset = header_base + 28
            rom_data[checksum_offset] = complement & 0xFF
            rom_data[checksum_offset + 1] = (complement >> 8) & 0xFF
            rom_data[checksum_offset + 2] = checksum & 0xFF
            rom_data[checksum_offset + 3] = (checksum >> 8) & 0xFF
            logger.info(f"Updated ROM checksum: 0x{checksum:04X}")

            # Write output atomically
            atomic_write(output_path, bytes(rom_data))
            logger.info(f"Wrote modified ROM to: {output_path}")

            return True, (
                f"Successfully injected palette at 0x{palette_offset:X}\n"
                f"Palette size: {CGRAM_PALETTE_SIZE} bytes\n"
                f"ROM checksum updated: 0x{checksum:04X}"
            )

        except Exception as e:
            logger.exception("Palette injection failed")
            return False, f"Palette injection error: {e!s}"
