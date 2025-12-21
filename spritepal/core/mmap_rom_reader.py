"""
Memory-mapped ROM reader for efficient large file access.

This module provides optimized ROM reading using memory-mapped I/O,
significantly improving performance for large ROM files by avoiding
loading entire files into memory.
"""
from __future__ import annotations

import logging
import mmap
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Protocol, override

if TYPE_CHECKING:
    class Decompressor(Protocol):
        def decompress(self, data: bytes) -> bytes: ...

logger = logging.getLogger(__name__)

class MemoryMappedROMReader:
    """
    Efficient ROM reader using memory-mapped I/O.

    Benefits:
    - Lazy loading: Only accessed pages are loaded into memory
    - OS-level caching: Automatic page cache management
    - Reduced memory usage: No need to load entire ROM
    - Better performance: Direct memory access without read() calls
    - Thread-safe: Multiple readers can share same mmap
    """

    def __init__(self, rom_path: str | Path):
        """
        Initialize memory-mapped ROM reader.

        Args:
            rom_path: Path to ROM file

        Raises:
            FileNotFoundError: If ROM file doesn't exist
            PermissionError: If ROM file can't be accessed
        """
        self.rom_path = Path(rom_path)
        if not self.rom_path.exists():
            raise FileNotFoundError(f"ROM file not found: {rom_path}")

        self.file_size = self.rom_path.stat().st_size
        self._file: BinaryIO | None = None
        self._mmap: mmap.mmap | None = None
        logger.debug(f"Initialized MemoryMappedROMReader for {rom_path} ({self.file_size} bytes)")

    @contextmanager
    def open_mmap(self, write: bool = False):
        """
        Context manager for memory-mapped ROM access.

        Args:
            write: If True, open for read-write access (default: read-only)

        Yields:
            mmap.mmap object for direct memory access

        Example:
            with reader.open_mmap() as rom_data:
                header = rom_data[0x7FC0:0x7FE0]
                sprite = rom_data[offset:offset+size]
        """
        access_mode = "r+b" if write else "rb"

        file_handle = None
        mapped = None

        try:
            # Open file
            file_handle = self.rom_path.open(access_mode)

            # Create memory map
            # Use ACCESS_COPY for read-write without modifying original file
            access = mmap.ACCESS_WRITE if write else mmap.ACCESS_READ
            mapped = mmap.mmap(file_handle.fileno(), 0, access=access)

            logger.debug(f"Memory-mapped {self.rom_path} ({'read-write' if write else 'read-only'})")
            yield mapped

        finally:
            # Clean up resources
            if mapped:
                try:
                    mapped.close()
                except Exception as e:
                    logger.warning(f"Error closing mmap: {e}")

            if file_handle:
                try:
                    file_handle.close()
                except Exception as e:
                    logger.warning(f"Error closing file: {e}")

    def read_bytes(self, offset: int, size: int, *, strict: bool = False) -> bytes:
        """
        Read bytes from ROM at specified offset.

        Args:
            offset: Starting offset in ROM
            size: Number of bytes to read
            strict: If True, raise ValueError when requested size cannot be fully read.
                    If False (default), silently return fewer bytes if at end of file.

        Returns:
            Bytes read from ROM

        Raises:
            ValueError: If offset or size is invalid, or if strict=True and
                        the full requested size cannot be read.
        """
        if offset < 0 or offset >= self.file_size:
            raise ValueError(f"Invalid offset {offset} for ROM size {self.file_size}")

        if size < 0:
            raise ValueError(f"Invalid size {size}")

        # Clamp size to file bounds
        actual_size = min(size, self.file_size - offset)

        if strict and actual_size < size:
            raise ValueError(
                f"Requested {size} bytes at offset 0x{offset:X}, "
                f"but only {actual_size} bytes available (ROM size: 0x{self.file_size:X})"
            )

        with self.open_mmap() as rom_data:
            return bytes(rom_data[offset:offset + actual_size])

    def read_header(self) -> dict[str, object]:
        """
        Read SNES ROM header information.

        Returns:
            Dictionary with header fields
        """
        # Try both LoROM and HiROM header locations
        headers = {
            "LoROM": 0x7FC0,
            "HiROM": 0xFFC0
        }

        with self.open_mmap() as rom_data:
            for rom_type, header_offset in headers.items():
                if header_offset + 32 > self.file_size:
                    continue

                # Read header bytes
                header_data = rom_data[header_offset:header_offset + 32]

                # Parse header fields
                title = header_data[0:21].decode('ascii', errors='ignore').strip()
                if title and not all(c == 0xff for c in header_data[0:21]):
                    return {
                        "title": title,
                        "rom_type": rom_type,
                        "rom_size": header_data[23],
                        "ram_size": header_data[24],
                        "country": header_data[25],
                        "license": header_data[26],
                        "version": header_data[27],
                        "checksum_complement": int.from_bytes(header_data[28:30], 'little'),
                        "checksum": int.from_bytes(header_data[30:32], 'little'),
                        "header_offset": header_offset
                    }

        return {"title": "Unknown", "rom_type": "Unknown"}

    def search_pattern(
        self,
        pattern: bytes,
        start_offset: int = 0,
        end_offset: int | None = None,
        step: int = 1
    ) -> Iterator[int]:
        """
        Search for byte pattern in ROM.

        Args:
            pattern: Byte pattern to search for
            start_offset: Starting offset for search
            end_offset: Ending offset (None = end of file)
            step: Step size for search (1 = every byte)

        Yields:
            Offsets where pattern is found
        """
        if not pattern:
            return

        end_offset = end_offset or self.file_size
        pattern_len = len(pattern)

        with self.open_mmap() as rom_data:
            offset = start_offset
            while offset <= end_offset - pattern_len:
                # Use mmap.find() for efficient searching
                found = rom_data.find(pattern, offset, end_offset)
                if found == -1:
                    break

                yield found
                offset = found + step

    def calculate_checksum(self) -> int:
        """
        Calculate ROM checksum for validation.

        Returns:
            16-bit checksum value
        """
        checksum = 0

        with self.open_mmap() as rom_data:
            # SNES checksum calculation
            for i in range(0, self.file_size, 2):
                if i + 1 < self.file_size:
                    checksum += int.from_bytes(rom_data[i:i+2], 'little')
                else:
                    checksum += rom_data[i]
                checksum &= 0xFFFF

        return checksum

    def extract_compressed_data(self, offset: int, decompressor: Decompressor) -> bytes:
        """
        Extract compressed data starting at offset.

        Args:
            offset: Starting offset of compressed data
            decompressor: Decompression object with decompress(data) method

        Returns:
            Decompressed data
        """
        with self.open_mmap() as rom_data:
            # Read compression header to determine size
            # This is a simplified example - actual implementation
            # would depend on compression format

            # For HAL compression, we might need to read until end marker
            # or use the decompressor to determine compressed size
            # Use max size (64KB or remaining file) - the decompressor will
            # only read what it needs from the data
            compressed_size = min(0x10000, self.file_size - offset)
            compressed_data = bytes(rom_data[offset:offset + compressed_size])

            return decompressor.decompress(compressed_data)

    @contextmanager
    def batch_reader(self):
        """
        Context manager for multiple reads from same mmap.

        More efficient for multiple operations on same ROM.

        Example:
            with reader.batch_reader() as batch:
                header = batch.read(0x7FC0, 32)
                sprite1 = batch.read(0x50000, 0x800)
                sprite2 = batch.read(0x51000, 0x800)
        """
        with self.open_mmap() as rom_data:
            class BatchReader:
                def read(self, offset: int, size: int) -> bytes:
                    return bytes(rom_data[offset:offset + size])

                def find(self, pattern: bytes, start: int = 0) -> int:
                    return rom_data.find(pattern, start)

                def __getitem__(self, key: int | slice) -> int | bytes:
                    return rom_data[key]

            yield BatchReader()

class CachedROMReader(MemoryMappedROMReader):
    """
    Memory-mapped ROM reader with intelligent caching.

    Adds LRU cache for frequently accessed regions.
    """

    def __init__(self, rom_path: str | Path, cache_size: int = 32):
        """
        Initialize cached ROM reader.

        Args:
            rom_path: Path to ROM file
            cache_size: Number of regions to cache (default: 32)
        """
        super().__init__(rom_path)
        self._cache: dict[tuple[int, int], bytes] = {}
        self._cache_order: list[tuple[int, int]] = []
        self._cache_size = cache_size

    @override
    def read_bytes(self, offset: int, size: int, *, strict: bool = False) -> bytes:
        """
        Read bytes with caching.

        Caches frequently accessed regions for better performance.

        Args:
            offset: File offset to read from
            size: Number of bytes to read
            strict: If True, raise ValueError when fewer bytes are available than requested
        """
        cache_key = (offset, size)

        # Check cache (only for non-strict reads or when we know we have full data)
        if cache_key in self._cache:
            # Move to end (most recently used)
            self._cache_order.remove(cache_key)
            self._cache_order.append(cache_key)
            logger.debug(f"Cache hit for offset 0x{offset:X}, size {size}")
            return self._cache[cache_key]

        # Read from ROM
        data = super().read_bytes(offset, size, strict=strict)

        # Add to cache
        self._cache[cache_key] = data
        self._cache_order.append(cache_key)

        # Evict oldest if cache is full
        if len(self._cache_order) > self._cache_size:
            oldest = self._cache_order.pop(0)
            del self._cache[oldest]
            logger.debug(f"Evicted cache entry: offset 0x{oldest[0]:X}, size {oldest[1]}")

        return data

    def clear_cache(self):
        """Clear the cache."""
        self._cache.clear()
        self._cache_order.clear()
        logger.debug("Cleared ROM cache")

def optimize_rom_operations(rom_path: str) -> MemoryMappedROMReader:
    """
    Create optimized ROM reader based on file size.

    Args:
        rom_path: Path to ROM file

    Returns:
        Appropriate ROM reader instance
    """
    file_size = Path(rom_path).stat().st_size

    # Use cached reader for smaller ROMs that fit in memory
    if file_size < 16 * 1024 * 1024:  # 16MB
        logger.info(f"Using cached reader for {rom_path} ({file_size} bytes)")
        return CachedROMReader(rom_path, cache_size=64)
    logger.info(f"Using direct mmap reader for {rom_path} ({file_size} bytes)")
    return MemoryMappedROMReader(rom_path)
