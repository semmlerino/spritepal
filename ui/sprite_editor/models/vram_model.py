#!/usr/bin/env python3
"""
VRAM/CGRAM/OAM data model for the sprite editor.
Handles memory dump file operations for SNES sprite data.
"""

from dataclasses import dataclass, field
from pathlib import Path

from ..constants import (
    BYTES_PER_PALETTE,
    BYTES_PER_TILE_4BPP,
    CGRAM_SIZE,
    MAX_CGRAM_FILE_SIZE,
    MAX_OAM_FILE_SIZE,
    MAX_VRAM_FILE_SIZE,
    OAM_SIZE,
)


@dataclass
class VRAMInfo:
    """Information about a VRAM dump file."""

    file_path: str
    file_size: int
    total_tiles: int
    is_valid: bool
    error_message: str | None = None


@dataclass
class CGRAMInfo:
    """Information about a CGRAM (color palette) dump file."""

    file_path: str
    file_size: int
    palette_count: int
    is_valid: bool
    error_message: str | None = None


@dataclass
class OAMInfo:
    """Information about an OAM (sprite attributes) dump file."""

    file_path: str
    file_size: int
    sprite_count: int
    is_valid: bool
    error_message: str | None = None


@dataclass
class VRAMModel:
    """
    Model for managing VRAM, CGRAM, and OAM dump files.
    Provides validation and basic file operations.
    """

    vram_file: str | None = None
    cgram_file: str | None = None
    oam_file: str | None = None

    # Cached file info
    _vram_info: VRAMInfo | None = field(default=None, repr=False)

    def set_vram_file(self, file_path: str) -> VRAMInfo:
        """
        Set and validate VRAM file.
        Returns info about the file.
        """
        info = self._validate_vram_file(file_path)
        if info.is_valid:
            self.vram_file = file_path
            self._vram_info = info
        return info

    def set_cgram_file(self, file_path: str) -> CGRAMInfo:
        """
        Set and validate CGRAM file.
        Returns info about the file including validation results.
        """
        info = self._validate_cgram_file(file_path)
        if info.is_valid:
            self.cgram_file = file_path
        return info

    def set_oam_file(self, file_path: str) -> OAMInfo:
        """
        Set and validate OAM file.
        Returns info about the file including validation results.
        """
        info = self._validate_oam_file(file_path)
        if info.is_valid:
            self.oam_file = file_path
        return info

    def _validate_vram_file(self, file_path: str) -> VRAMInfo:
        """Validate a VRAM dump file."""
        path = Path(file_path) if file_path else None
        if not path or not path.exists():
            return VRAMInfo(
                file_path=file_path or "",
                file_size=0,
                total_tiles=0,
                is_valid=False,
                error_message="File does not exist",
            )

        file_size = path.stat().st_size

        if file_size > MAX_VRAM_FILE_SIZE:
            return VRAMInfo(
                file_path=file_path,
                file_size=file_size,
                total_tiles=0,
                is_valid=False,
                error_message=f"File too large ({file_size} bytes, max {MAX_VRAM_FILE_SIZE})",
            )

        if file_size < BYTES_PER_TILE_4BPP:
            return VRAMInfo(
                file_path=file_path,
                file_size=file_size,
                total_tiles=0,
                is_valid=False,
                error_message="File too small to contain tile data",
            )

        total_tiles = file_size // BYTES_PER_TILE_4BPP

        return VRAMInfo(
            file_path=file_path,
            file_size=file_size,
            total_tiles=total_tiles,
            is_valid=True,
        )

    def _validate_cgram_file(self, file_path: str) -> CGRAMInfo:
        """Validate a CGRAM dump file."""
        path = Path(file_path) if file_path else None
        if not path or not path.exists():
            return CGRAMInfo(
                file_path=file_path or "",
                file_size=0,
                palette_count=0,
                is_valid=False,
                error_message="File does not exist",
            )

        file_size = path.stat().st_size

        if file_size < CGRAM_SIZE:
            return CGRAMInfo(
                file_path=file_path,
                file_size=file_size,
                palette_count=0,
                is_valid=False,
                error_message=f"File too small ({file_size} bytes, need {CGRAM_SIZE})",
            )

        if file_size > MAX_CGRAM_FILE_SIZE:
            return CGRAMInfo(
                file_path=file_path,
                file_size=file_size,
                palette_count=0,
                is_valid=False,
                error_message=f"File too large ({file_size} bytes, max {MAX_CGRAM_FILE_SIZE})",
            )

        palette_count = file_size // BYTES_PER_PALETTE

        return CGRAMInfo(
            file_path=file_path,
            file_size=file_size,
            palette_count=palette_count,
            is_valid=True,
        )

    def _validate_oam_file(self, file_path: str) -> OAMInfo:
        """Validate an OAM dump file."""
        path = Path(file_path) if file_path else None
        if not path or not path.exists():
            return OAMInfo(
                file_path=file_path or "",
                file_size=0,
                sprite_count=0,
                is_valid=False,
                error_message="File does not exist",
            )

        file_size = path.stat().st_size

        if file_size < OAM_SIZE:
            return OAMInfo(
                file_path=file_path,
                file_size=file_size,
                sprite_count=0,
                is_valid=False,
                error_message=f"File too small ({file_size} bytes, need {OAM_SIZE})",
            )

        if file_size > MAX_OAM_FILE_SIZE:
            return OAMInfo(
                file_path=file_path,
                file_size=file_size,
                sprite_count=0,
                is_valid=False,
                error_message=f"File too large ({file_size} bytes, max {MAX_OAM_FILE_SIZE})",
            )

        # OAM has 128 sprite entries (4 bytes each) + 32 bytes for high bits
        sprite_count = 128 if file_size >= OAM_SIZE else file_size // 4

        return OAMInfo(
            file_path=file_path,
            file_size=file_size,
            sprite_count=sprite_count,
            is_valid=True,
        )

    def read_vram_data(self, offset: int, size: int) -> bytes:
        """
        Read data from VRAM file at specified offset and size.

        Raises:
            ValueError: If no VRAM file is set
            RuntimeError: If file read fails or returns incomplete data
        """
        if not self.vram_file:
            raise ValueError("No VRAM file set")

        try:
            with Path(self.vram_file).open("rb") as f:
                f.seek(offset)
                data = f.read(size)
            if len(data) < size:
                raise RuntimeError(
                    f"Incomplete read: got {len(data)} bytes, expected {size}"
                )
            return data
        except OSError as e:
            raise RuntimeError(f"Failed to read VRAM: {e}") from e

    def write_vram_data(
        self, data: bytes, offset: int, output_file: str | None = None
    ) -> str:
        """
        Write data to VRAM file at specified offset.
        If output_file is None, modifies original file.

        Returns:
            Output file path on success

        Raises:
            ValueError: If no VRAM file set or offset/data exceeds bounds
            RuntimeError: If file operations fail
        """
        if not self.vram_file:
            raise ValueError("No VRAM file set")

        target_file = output_file or self.vram_file

        try:
            # If writing to different file, copy original first
            if output_file and output_file != self.vram_file:
                with Path(self.vram_file).open("rb") as src:
                    vram_data = bytearray(src.read())
            else:
                with Path(self.vram_file).open("rb") as f:
                    vram_data = bytearray(f.read())

            # Validate bounds
            if offset + len(data) > len(vram_data):
                raise ValueError(
                    f"Data ({len(data)} bytes) at offset {offset} exceeds "
                    f"VRAM size ({len(vram_data)} bytes)"
                )

            # Write data at offset
            vram_data[offset : offset + len(data)] = data

            # Save to target file
            with Path(target_file).open("wb") as f:
                f.write(vram_data)

            return target_file

        except OSError as e:
            raise RuntimeError(f"Failed to write VRAM: {e}") from e

    def get_vram_info(self) -> VRAMInfo | None:
        """Get cached VRAM info."""
        return self._vram_info

    def clear(self) -> None:
        """Clear all file references."""
        self.vram_file = None
        self.cgram_file = None
        self.oam_file = None
        self._vram_info = None
