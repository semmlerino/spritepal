"""
ROM validation utilities for SpritePal
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, ClassVar

from utils.constants import (
    ROM_CHECKSUM_COMPLEMENT_MASK,
    ROM_CHECKSUM_PAL_EUROPE,
    ROM_CHECKSUM_PAL_JAPAN,
    ROM_CHECKSUM_PAL_USA,
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
)
from utils.logging_config import get_logger
from utils.rom_exceptions import (
    InvalidROMError,
    ROMChecksumError,
    ROMHeaderError,
    ROMSizeError,
)

logger = get_logger(__name__)

class ROMValidator:
    """Validates SNES ROM files"""

    # Valid ROM sizes (in bytes, without header)
    VALID_ROM_SIZES: ClassVar[list[int]] = [
        ROM_SIZE_512KB,   # 512KB (4 Mbit)
        ROM_SIZE_1MB,     # 1MB (8 Mbit)
        ROM_SIZE_1_5MB,   # 1.5MB (12 Mbit)
        ROM_SIZE_2MB,     # 2MB (16 Mbit)
        ROM_SIZE_2_5MB,   # 2.5MB (20 Mbit)
        ROM_SIZE_3MB,     # 3MB (24 Mbit)
        ROM_SIZE_4MB,     # 4MB (32 Mbit)
        ROM_SIZE_6MB,     # 6MB (48 Mbit)
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
    def validate_rom_header(cls, rom_path: str) -> tuple[dict[str, Any], int]:
        """
        Validate and extract ROM header information.

        Returns:
            Tuple of (header_info, header_offset)

        Raises:
            ROMHeaderError: If header is invalid
        """
        rom_path_obj = Path(rom_path)
        with rom_path_obj.open("rb") as f:
            # Check for SMC header
            file_size = rom_path_obj.stat().st_size
            header_offset = 512 if file_size % 1024 == 512 else 0

            # Try both possible header locations
            for base_offset in [ROM_HEADER_OFFSET_LOROM, ROM_HEADER_OFFSET_HIROM]:
                f.seek(header_offset + base_offset)
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
                    header_info = {
                        "title": title,
                        "rom_type": rom_type,
                        "rom_size": rom_size,
                        "sram_size": sram_size,
                        "region": region,
                        "developer": developer,
                        "version": version,
                        "checksum": checksum,
                        "checksum_complement": checksum_complement,
                        "header_location": base_offset,
                    }

                    logger.info(
                        f"Found valid ROM header: {title} (checksum: 0x{checksum:04X})"
                    )
                    return header_info, header_offset

        raise ROMHeaderError("Could not find valid SNES ROM header")

    @classmethod
    def verify_rom_checksum(
        cls, rom_path: str, header_info: dict[str, Any], header_offset: int
    ) -> bool:
        """
        Verify ROM checksum matches header.

        Returns:
            True if checksum is valid

        Raises:
            ROMChecksumError: If checksum validation fails
        """
        with Path(rom_path).open("rb") as f:
            # Read ROM data (skip SMC header if present)
            f.seek(header_offset)
            rom_data = f.read()

        # Calculate actual checksum
        checksum = 0
        for i in range(0, len(rom_data), 2):
            if i + 1 < len(rom_data):
                word = (rom_data[i + 1] << 8) | rom_data[i]
            else:
                word = rom_data[i]
            checksum = (checksum + word) & ROM_CHECKSUM_COMPLEMENT_MASK

        # Compare with header checksum
        if checksum != header_info["checksum"]:
            raise ROMChecksumError(
                f"ROM checksum mismatch: expected 0x{header_info['checksum']:04X}, "
                f"got 0x{checksum:04X}"
            )

        logger.info("ROM checksum verified successfully")
        return True

    @classmethod
    def identify_rom_version(cls, header_info: dict[str, Any]) -> str | None:
        """
        Identify ROM version/region from header.

        Returns:
            Version string (e.g., "USA", "Japan") or None if unknown
        """
        title = header_info["title"]
        checksum = header_info["checksum"]

        # Check known games
        for game_title, versions in cls.KNOWN_GAMES.items():
            if game_title in title.upper():
                for version, expected_checksum in versions.items():
                    if checksum == expected_checksum:
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

        region = header_info.get("region", 0)
        if region in region_codes:
            return region_codes[region]

        return None

    @classmethod
    def validate_rom_for_injection(
        cls, rom_path: str, sprite_offset: int
    ) -> tuple[dict[str, Any], int]:
        """
        Complete ROM validation for injection.

        Returns:
            Tuple of (header_info, header_offset)

        Raises:
            Various ROM exceptions on validation failure
        """
        # Basic file validation
        is_valid, error_msg = cls.validate_rom_file(rom_path)
        if not is_valid:
            raise InvalidROMError(error_msg)

        # Header validation
        header_info, header_offset = cls.validate_rom_header(rom_path)

        # Checksum validation
        cls.verify_rom_checksum(rom_path, header_info, header_offset)

        # Validate sprite offset
        file_size = Path(rom_path).stat().st_size
        actual_rom_size = file_size - header_offset

        if sprite_offset >= actual_rom_size:
            raise ROMSizeError(
                f"Sprite offset 0x{sprite_offset:X} is beyond ROM size "
                f"(0x{actual_rom_size:X} bytes)"
            )

        # Identify version
        version = cls.identify_rom_version(header_info)
        if version:
            logger.info(f"ROM version identified: {version}")
        else:
            logger.warning("Unknown ROM version - sprite locations may not match")

        return header_info, header_offset
