"""ROM utility functions - shared ROM loading and SMC header detection.

This module consolidates common ROM operations used across multiple workers to follow DRY principle.
"""

from __future__ import annotations

import logging
import mmap

logger = logging.getLogger(__name__)


class BytesMMAPWrapper:
    """Wrapper for bytes to provide mmap-compatible interface for fallback loading.

    Used when memory mapping fails (e.g., on some filesystems or with very small files).
    Provides the same interface as mmap for transparent use by callers.
    """

    def __init__(self, data: bytes) -> None:
        self._data = data

    def __getitem__(self, key: int | slice) -> bytes | int:
        return self._data[key]

    def __len__(self) -> int:
        return len(self._data)

    def close(self) -> None:
        pass  # No-op for bytes wrapper


def detect_smc_offset(rom_data: bytes | mmap.mmap | BytesMMAPWrapper) -> int:
    """Detect SMC header offset from ROM data.

    SNES ROM files may have a 512-byte SMC/SWC header prepended.
    This header is present when file_size % 1024 == 512.

    Args:
        rom_data: ROM data as bytes, mmap, or BytesMMAPWrapper.

    Returns:
        512 if SMC header is present, 0 otherwise.
    """
    file_size = len(rom_data)
    return 512 if file_size % 1024 == 512 else 0


def detect_smc_offset_from_size(file_size: int) -> int:
    """Detect SMC header offset from file size.

    Args:
        file_size: Size of the ROM file in bytes.

    Returns:
        512 if SMC header is present, 0 otherwise.
    """
    return 512 if file_size % 1024 == 512 else 0


def load_rom_data_stripped(rom_path: str) -> bytes:
    """Load ROM file and strip SMC header if present.

    This consolidates the common pattern of reading a ROM file and removing
    the optional 512-byte SMC/SWC header so offsets are ROM addresses.

    Args:
        rom_path: Path to the ROM file.

    Returns:
        ROM data with SMC header stripped (if present).
    """
    from pathlib import Path

    with Path(rom_path).open("rb") as rom_file:
        rom_data = rom_file.read()

    smc_offset = detect_smc_offset(rom_data)
    if smc_offset > 0:
        logger.info(f"Stripping {smc_offset}-byte SMC header from ROM data")
        rom_data = rom_data[smc_offset:]

    logger.debug(f"ROM size: {len(rom_data)} bytes (after SMC strip)")
    return rom_data
