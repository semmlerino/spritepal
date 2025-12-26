"""
ROM validation utilities for SpritePal
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from utils.constants import (
    ROM_CHECKSUM_COMPLEMENT_MASK,
    ROM_CHECKSUM_PAL_EUROPE,
    ROM_CHECKSUM_PAL_JAPAN,
    ROM_CHECKSUM_PAL_USA,
    ROM_HEADER_OFFSET_EXHIROM,
    ROM_HEADER_OFFSET_HIROM,
    ROM_HEADER_OFFSET_LOROM,
    ROM_SIZE_1_5MB,
    ROM_SIZE_1MB,
    ROM_SIZE_2_5MB,
    ROM_SIZE_2MB,
    ROM_SIZE_3MB,
    ROM_SIZE_4MB,
    ROM_SIZE_6MB,
    ROM_SIZE_512KB,
    ROM_TYPE_SA1_MAX,
    ROM_TYPE_SA1_MIN,
)
from utils.logging_config import get_logger
from utils.rom_exceptions import (
    InvalidROMError,
    ROMChecksumError,
    ROMHeaderError,
    ROMSizeError,
)

logger = get_logger(__name__)


@dataclass
class ROMHeader:
    """SNES ROM header information."""

    title: str
    rom_type: int
    rom_size: int
    sram_size: int
    checksum: int
    checksum_complement: int
    header_offset: int
    rom_type_offset: int  # 0x7FC0 for LoROM, 0xFFC0 for HiROM
    # Extended fields (captured by validator but not by legacy injector)
    region: int = 0
    developer: int = 0
    version: int = 0


class ROMValidator:
    """Validates SNES ROM files"""

    # Valid ROM sizes (in bytes, without header)
    VALID_ROM_SIZES: ClassVar[list[int]] = [
        ROM_SIZE_512KB,  # 512KB (4 Mbit)
        ROM_SIZE_1MB,  # 1MB (8 Mbit)
        ROM_SIZE_1_5MB,  # 1.5MB (12 Mbit)
        ROM_SIZE_2MB,  # 2MB (16 Mbit)
        ROM_SIZE_2_5MB,  # 2.5MB (20 Mbit)
        ROM_SIZE_3MB,  # 3MB (24 Mbit)
        ROM_SIZE_4MB,  # 4MB (32 Mbit)
        ROM_SIZE_6MB,  # 6MB (48 Mbit)
    ]

    # Known game titles and their checksums
    # NOTE: Only include games with verified checksums from actual ROM dumps.
    # Do not add placeholder/stub values - they can cause ROM misidentification.
    KNOWN_GAMES: ClassVar[dict[str, dict[str, int]]] = {
        "KIRBY SUPER STAR": {
            "USA": ROM_CHECKSUM_PAL_USA,
            "Japan": ROM_CHECKSUM_PAL_JAPAN,
            "Europe": ROM_CHECKSUM_PAL_EUROPE,
        },
        # KIRBY'S DREAM LAND 3 removed - no verified ROM checksum available
    }

    @classmethod
    def validate_rom_file(cls, rom_path: str) -> tuple[bool, str | None]:
        """
        Validate ROM file basic properties.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check file exists
        rom_path_obj = Path(rom_path)
        if not rom_path_obj.exists():
            return False, "ROM file does not exist"

        # Check file size
        file_size = rom_path_obj.stat().st_size
        if file_size == 0:
            return False, "ROM file is empty"

        # Check for SMC header (512 bytes)
        has_header = file_size % 1024 == 512
        rom_size = file_size - (512 if has_header else 0)

        # Validate ROM size
        if rom_size not in cls.VALID_ROM_SIZES:
            return False, f"Invalid ROM size: {rom_size} bytes"

        return True, None

    @classmethod
    def validate_rom_header(cls, rom_path: str) -> tuple[ROMHeader, int]:
        """
        Validate and extract ROM header information.

        Returns:
            Tuple of (ROMHeader, smc_header_offset)
            - ROMHeader contains all parsed header fields
            - smc_header_offset is 512 if SMC header present, else 0

        Raises:
            ROMHeaderError: If header is invalid
        """
        rom_path_obj = Path(rom_path)
        with rom_path_obj.open("rb") as f:
            # Check for SMC header
            file_size = rom_path_obj.stat().st_size
            smc_header_offset = 512 if file_size % 1024 == 512 else 0

            # Validate SMC header content if detected by size
            if smc_header_offset == 512:
                f.seek(0)
                smc_header = f.read(512)
                if not cls._validate_smc_header_content(smc_header, file_size):
                    logger.warning(
                        "SMC header detected by size but content validation failed. "
                        "This may be a non-standard header format or a headerless ROM "
                        "with unusual size. Proceeding with header detection."
                    )

            # Try all possible header locations: LoROM, HiROM, ExHiROM
            # ExHiROM is needed for large (>4MB) games like Tales of Phantasia
            header_offsets = [
                (ROM_HEADER_OFFSET_LOROM, "LoROM"),
                (ROM_HEADER_OFFSET_HIROM, "HiROM"),
            ]

            # Only check ExHiROM if ROM is large enough (>4MB after SMC header)
            if file_size - smc_header_offset > 0x400000:
                header_offsets.append((ROM_HEADER_OFFSET_EXHIROM, "ExHiROM"))

            for base_offset, mapping_type in header_offsets:
                # Skip if offset would exceed file size
                if smc_header_offset + base_offset + 32 > file_size:
                    continue

                f.seek(smc_header_offset + base_offset)
                header_data = f.read(32)

                if len(header_data) < 32:
                    continue

                # Parse header fields
                title = header_data[0:21].decode("ascii", errors="ignore").strip("\x00")
                rom_type = header_data[21]
                rom_size = header_data[23]
                sram_size = header_data[24]
                region = header_data[25]
                developer = header_data[26]
                version = header_data[27]
                checksum_complement = struct.unpack("<H", header_data[28:30])[0]
                checksum = struct.unpack("<H", header_data[30:32])[0]

                # Verify checksum format
                if (checksum ^ checksum_complement) == ROM_CHECKSUM_COMPLEMENT_MASK:
                    # Detect SA-1 chip (used by Kirby Super Star, Super Mario RPG, etc.)
                    has_sa1 = ROM_TYPE_SA1_MIN <= rom_type <= ROM_TYPE_SA1_MAX

                    header = ROMHeader(
                        title=title,
                        rom_type=rom_type,
                        rom_size=rom_size,
                        sram_size=sram_size,
                        checksum=checksum,
                        checksum_complement=checksum_complement,
                        header_offset=smc_header_offset,
                        rom_type_offset=base_offset,
                        region=region,
                        developer=developer,
                        version=version,
                    )

                    chip_info = " [SA-1]" if has_sa1 else ""
                    logger.info(
                        f"Found valid {mapping_type} ROM header: {title}{chip_info} "
                        f"(checksum: 0x{checksum:04X}, type: 0x{rom_type:02X})"
                    )
                    return header, smc_header_offset

        raise ROMHeaderError("Could not find valid SNES ROM header")

    @classmethod
    def _validate_smc_header_content(cls, smc_header: bytes, file_size: int) -> bool:
        """
        Validate SMC header content beyond just size detection.

        SMC headers typically have these characteristics:
        - Bytes 0-1: File size / 8KB (little-endian)
        - Byte 2: Flags (usually 0x00 or specific values)
        - Bytes 3-511: Usually zeros or metadata

        Args:
            smc_header: The 512-byte SMC header
            file_size: Total file size including header

        Returns:
            True if header content looks valid, False otherwise
        """
        if len(smc_header) != 512:
            return False

        # Check if bytes 8-511 are mostly zeros (common in SMC headers)
        # Allow some non-zero bytes for metadata
        non_zero_count = sum(1 for b in smc_header[8:] if b != 0)
        if non_zero_count > 64:  # More than 64 non-zero bytes is suspicious
            logger.debug(
                f"SMC header has {non_zero_count} non-zero bytes after offset 8, "
                "which is unusual for a standard SMC header"
            )
            return False

        # Check if size field is plausible (bytes 0-1 = size / 8KB)
        # This is a heuristic - not all SMC headers follow this exactly
        expected_rom_size = file_size - 512
        size_field = smc_header[0] | (smc_header[1] << 8)
        expected_size_field = expected_rom_size // 8192  # 8KB units

        # Allow some tolerance (size field may not be exact)
        if size_field > 0 and abs(size_field - expected_size_field) > 16:
            logger.debug(
                f"SMC size field ({size_field}) doesn't match expected "
                f"({expected_size_field}) for ROM size {expected_rom_size}"
            )
            # Don't fail on this alone - it's just informational

        return True

    @classmethod
    def calculate_checksum(cls, rom_data: bytes | bytearray, header_offset: int = 0) -> tuple[int, int]:
        """
        Calculate SNES ROM checksum and complement.

        Args:
            rom_data: ROM data bytes (may include SMC header)
            header_offset: SMC header offset to skip (0 or 512)

        Returns:
            Tuple of (checksum, complement)
        """
        data = rom_data[header_offset:]
        checksum = 0
        for i in range(0, len(data), 2):
            if i + 1 < len(data):
                word = (data[i + 1] << 8) | data[i]
            else:
                word = data[i]
            checksum = (checksum + word) & ROM_CHECKSUM_COMPLEMENT_MASK

        complement = checksum ^ ROM_CHECKSUM_COMPLEMENT_MASK
        return checksum, complement

    @classmethod
    def verify_rom_checksum(cls, rom_path: str, header: ROMHeader, lenient: bool = False) -> bool:
        """
        Verify ROM checksum matches header.

        Args:
            rom_path: Path to ROM file
            header: ROMHeader from validate_rom_header()
            lenient: If True, log warning on mismatch instead of raising exception.
                     Useful for patched/modified ROMs with intentionally invalid checksums.

        Returns:
            True if checksum is valid, False if mismatch in lenient mode

        Raises:
            ROMChecksumError: If checksum validation fails (only when lenient=False)
        """
        with Path(rom_path).open("rb") as f:
            rom_data = f.read()

        calculated_checksum, _ = cls.calculate_checksum(rom_data, header.header_offset)

        if calculated_checksum != header.checksum:
            msg = f"ROM checksum mismatch: expected 0x{header.checksum:04X}, got 0x{calculated_checksum:04X}"
            if lenient:
                logger.warning(f"{msg} (continuing in lenient mode)")
                return False
            raise ROMChecksumError(msg)

        logger.info("ROM checksum verified successfully")
        return True

    @classmethod
    def identify_rom_version(cls, header: ROMHeader) -> str | None:
        """
        Identify ROM version/region from header.

        Args:
            header: ROMHeader from validate_rom_header()

        Returns:
            Version string (e.g., "USA", "Japan") or None if unknown
        """
        # Check known games
        for game_title, versions in cls.KNOWN_GAMES.items():
            if game_title in header.title.upper():
                for version, expected_checksum in versions.items():
                    if header.checksum == expected_checksum:
                        logger.info(f"Identified ROM: {game_title} ({version})")
                        return version

        # Try to determine from region code
        region_codes = {
            0: "Japan",
            1: "USA/Canada",
            2: "Europe",
            3: "Sweden/Scandinavia",
            4: "Finland",
            5: "Denmark",
            6: "France",
            7: "Netherlands",
            8: "Spain",
            9: "Germany",
            10: "Italy",
            11: "China",
            12: "Indonesia",
            13: "Korea",
            14: "Common/World",
            15: "Canada",
            16: "Brazil",
            17: "Australia",
        }

        if header.region in region_codes:
            return region_codes[header.region]

        return None

    @classmethod
    def validate_rom_for_injection(
        cls, rom_path: str, sprite_offset: int, lenient_checksum: bool = False
    ) -> tuple[ROMHeader, int]:
        """
        Complete ROM validation for injection.

        Args:
            rom_path: Path to ROM file
            sprite_offset: Offset in ROM where sprite is located
            lenient_checksum: If True, warn on checksum mismatch instead of failing.
                              Useful for patched/modified ROMs.

        Returns:
            Tuple of (ROMHeader, smc_header_offset)

        Raises:
            Various ROM exceptions on validation failure
        """
        # Basic file validation
        is_valid, error_msg = cls.validate_rom_file(rom_path)
        if not is_valid:
            raise InvalidROMError(error_msg)

        # Header validation
        header, smc_header_offset = cls.validate_rom_header(rom_path)

        # Checksum validation
        cls.verify_rom_checksum(rom_path, header, lenient=lenient_checksum)

        # Validate sprite offset
        file_size = Path(rom_path).stat().st_size
        actual_rom_size = file_size - smc_header_offset

        if sprite_offset >= actual_rom_size:
            raise ROMSizeError(f"Sprite offset 0x{sprite_offset:X} is beyond ROM size (0x{actual_rom_size:X} bytes)")

        # Identify version
        version = cls.identify_rom_version(header)
        if version:
            logger.info(f"ROM version identified: {version}")
        else:
            logger.warning("Unknown ROM version - sprite locations may not match")

        return header, smc_header_offset
