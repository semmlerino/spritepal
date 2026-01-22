#!/usr/bin/env python3
"""
VRAM file operations service.
Handles reading, writing, and injecting data into VRAM dump files.
"""

from pathlib import Path

from utils.constants import (
    TILE_DATA_MAX_SIZE,
    VRAM_SIZE_ABSOLUTE_MAX,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)


class VRAMService:
    """Service for VRAM file operations."""

    def read(self, vram_file: str, offset: int, size: int) -> bytes:
        """
        Read data from VRAM dump file.

        Args:
            vram_file: Path to VRAM dump file
            offset: Byte offset to start reading from
            size: Number of bytes to read

        Returns:
            Raw bytes read from file

        Raises:
            ValueError: If offset or size is negative/invalid
            RuntimeError: If file operations fail or incomplete read
        """
        try:
            if offset < 0:
                raise ValueError(f"Invalid negative offset: {offset}")
            if size < 0:
                raise ValueError(f"Invalid negative size: {size}")

            with Path(vram_file).open("rb") as f:
                f.seek(offset)
                data = f.read(size)

            if len(data) < size:
                raise RuntimeError(f"Incomplete read at offset {hex(offset)}: requested {size} bytes, got {len(data)}")

            return data

        except ValueError:
            raise
        except OSError as e:
            raise RuntimeError(f"Error reading VRAM: {e}") from e

    def inject(
        self,
        tile_data: bytes,
        vram_file: str,
        offset: int,
        output_file: str | None = None,
    ) -> str | bytes:
        """
        Inject tile data into VRAM dump at specified offset.

        Args:
            tile_data: Tile data bytes to inject
            vram_file: Path to source VRAM dump file
            offset: Byte offset for injection
            output_file: Optional output file path. If None, returns modified bytes.

        Returns:
            Output file path if output_file provided, otherwise modified VRAM bytes

        Raises:
            ValueError: If offset, size, or data is invalid
            RuntimeError: If file operations fail
        """
        try:
            if offset < 0:
                raise ValueError(f"Invalid negative offset: {offset}")

            with Path(vram_file).open("rb") as f:
                vram_data = bytearray(f.read())

            if len(vram_data) > VRAM_SIZE_ABSOLUTE_MAX:
                raise ValueError(f"VRAM file too large: {len(vram_data)} bytes")

            if offset >= len(vram_data):
                raise ValueError(f"Offset {hex(offset)} is at or beyond VRAM size ({len(vram_data)} bytes)")

            if len(tile_data) > TILE_DATA_MAX_SIZE:
                raise ValueError(f"Tile data too large: {len(tile_data)} bytes")

            if offset + len(tile_data) > len(vram_data):
                raise ValueError(f"Tile data ({len(tile_data)} bytes) would exceed VRAM size at offset {hex(offset)}")

            vram_data[offset : offset + len(tile_data)] = tile_data

            if output_file:
                with Path(output_file).open("wb") as f:
                    f.write(vram_data)
                return output_file
            return bytes(vram_data)

        except ValueError:
            raise
        except OSError as e:
            raise RuntimeError(f"Error injecting into VRAM: {e}") from e
