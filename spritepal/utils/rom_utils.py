"""ROM utility functions - shared ROM loading and SMC header detection.

This module consolidates common ROM operations used across multiple workers to follow DRY principle.
"""

from __future__ import annotations

import logging
import mmap
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    pass

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


@dataclass
class ROMData:
    """Container for loaded ROM data with SMC header information.

    Attributes:
        data: The ROM data (mmap or BytesMMAPWrapper).
        smc_offset: SMC header offset (512 if present, 0 otherwise).
        raw_size: Original file size before any header stripping.
    """

    data: mmap.mmap | BytesMMAPWrapper
    smc_offset: int
    raw_size: int

    @property
    def rom_size(self) -> int:
        """Size of ROM data without SMC header."""
        return len(self.data) - self.smc_offset

    def read_chunk(self, offset: int, size: int) -> bytes | None:
        """Read a chunk from ROM at the given ROM offset (adjusted for SMC header).

        Args:
            offset: ROM offset (without SMC header adjustment).
            size: Number of bytes to read.

        Returns:
            Bytes read, or None if offset is out of bounds.
        """
        # Adjust offset for SMC header (ROM offset -> file offset)
        file_offset = offset + self.smc_offset

        # Bounds checking
        if file_offset < 0 or file_offset >= len(self.data):
            return None

        end_offset = min(file_offset + size, len(self.data))
        chunk = self.data[file_offset:end_offset]
        # Slicing always returns bytes, not int
        return bytes(chunk) if isinstance(chunk, int) else chunk


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


def strip_smc_header(rom_data: bytes) -> tuple[bytes, int]:
    """Strip SMC header from ROM data if present.

    Args:
        rom_data: Raw ROM file data.

    Returns:
        Tuple of (stripped_data, smc_offset).
        If no header present, returns original data and 0.
    """
    smc_offset = detect_smc_offset(rom_data)
    if smc_offset > 0:
        logger.debug(f"Stripping {smc_offset}-byte SMC header from ROM data")
        return rom_data[smc_offset:], smc_offset
    return rom_data, 0


@contextmanager
def rom_context(rom_path: str | Path) -> Iterator[ROMData]:
    """Context manager for safe ROM file and memory map handling.

    Attempts to memory-map the ROM file for efficient access. Falls back to
    reading the entire file into memory if memory mapping fails.

    Args:
        rom_path: Path to the ROM file.

    Yields:
        ROMData containing the mapped/loaded data and SMC offset.

    Raises:
        OSError: If the file cannot be opened.
        FileNotFoundError: If the file doesn't exist.
    """
    rom_file = None
    rom_mmap = None
    path = Path(rom_path)

    try:
        rom_file = path.open("rb")
        raw_size = path.stat().st_size

        try:
            # Try memory mapping first
            rom_mmap = mmap.mmap(rom_file.fileno(), 0, access=mmap.ACCESS_READ)
            smc_offset = detect_smc_offset(rom_mmap)
            if smc_offset > 0:
                logger.debug(f"Detected {smc_offset}-byte SMC header in ROM")
            yield ROMData(rom_mmap, smc_offset, raw_size)

        except Exception as mmap_error:
            logger.warning(f"Failed to memory-map ROM, using fallback: {mmap_error}")
            # Fallback to reading entire file
            rom_file.seek(0)
            rom_data = rom_file.read()
            smc_offset = detect_smc_offset(rom_data)
            if smc_offset > 0:
                logger.debug(f"Detected {smc_offset}-byte SMC header in ROM")

            # Use BytesMMAPWrapper for mmap-compatible interface
            yield ROMData(BytesMMAPWrapper(rom_data), smc_offset, raw_size)

    finally:
        # Ensure proper cleanup in all cases
        with suppress(Exception):
            if rom_mmap is not None:
                rom_mmap.close()
        with suppress(Exception):
            if rom_file is not None:
                rom_file.close()


def load_rom_stripped(rom_path: str | Path) -> tuple[bytes, int]:
    """Load ROM data with SMC header stripped.

    Convenience function for workers that need stripped ROM data in memory.

    Args:
        rom_path: Path to the ROM file.

    Returns:
        Tuple of (stripped_rom_data, smc_offset).
    """
    with Path(rom_path).open("rb") as f:
        rom_data = f.read()
    return strip_smc_header(rom_data)
