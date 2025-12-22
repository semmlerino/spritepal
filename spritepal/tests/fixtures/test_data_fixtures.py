"""
Consolidated test data fixtures for SpritePal tests.

This module provides centralized test data generation for:
- ROM files (various sizes and configurations)
- VRAM dump files
- Test byte patterns

Usage:
    # For tests that need a simple ROM file:
    def test_something(test_rom_file):
        rom_path = test_rom_file()  # Default 1MB
        rom_path = test_rom_file(size="small")  # 13KB
        rom_path = test_rom_file(size="large", with_header=True)  # 2MB with SNES header

    # For tests that need raw ROM data:
    def test_something(test_rom_data_factory):
        data = test_rom_data_factory()  # Default 1MB
        data = test_rom_data_factory(size=32 * 1024)  # 32KB

    # For tests that need VRAM:
    def test_something(test_vram_file):
        vram_path = test_vram_file()  # 64KB VRAM dump
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


# ROM size presets
ROM_SIZES = {
    "tiny": 13 * 1024,       # 13KB - minimal for quick tests
    "small": 32 * 1024,      # 32KB
    "medium": 512 * 1024,    # 512KB (LoROM)
    "default": 1024 * 1024,  # 1MB - most common
    "large": 2 * 1024 * 1024, # 2MB
}


def _create_snes_header(data: bytearray, is_lorom: bool = True) -> None:
    """Add a valid SNES internal header to ROM data.

    Args:
        data: Mutable bytearray to modify in-place
        is_lorom: If True, use LoROM header offset (0x7FC0), else HiROM (0xFFC0)
    """
    header_offset = 0x7FC0 if is_lorom else 0xFFC0

    if len(data) <= header_offset + 32:
        return  # ROM too small for header

    # Game title (21 bytes, ASCII padded with spaces)
    title = b"TEST ROM DATA        "[:21]
    data[header_offset:header_offset + 21] = title

    # Map mode (byte 21): 0x20 = LoROM, 0x21 = HiROM
    data[header_offset + 21] = 0x20 if is_lorom else 0x21

    # ROM type (byte 22): 0x00 = ROM only
    data[header_offset + 22] = 0x00

    # ROM size (byte 23): log2(size in KB) - e.g., 0x0A = 1MB
    rom_kb = len(data) // 1024
    size_byte = max(8, min(12, rom_kb.bit_length() - 1))  # Clamp to valid range
    data[header_offset + 23] = size_byte

    # SRAM size (byte 24): 0x00 = no SRAM
    data[header_offset + 24] = 0x00

    # Country code (byte 25): 0x01 = North America
    data[header_offset + 25] = 0x01

    # Developer ID (byte 26): 0x00
    data[header_offset + 26] = 0x00

    # Version (byte 27): 0x00
    data[header_offset + 27] = 0x00

    # Checksum complement and checksum (bytes 28-31)
    # Simple placeholder values
    data[header_offset + 28:header_offset + 32] = b'\xFF\xFF\x00\x00'


def _add_sprite_patterns(data: bytearray, offsets: list[int] | None = None) -> None:
    """Add recognizable tile/sprite patterns at specified offsets.

    Args:
        data: Mutable bytearray to modify in-place
        offsets: List of offsets where to add patterns. Defaults to common locations.
    """
    if offsets is None:
        offsets = [0x10000, 0x20000, 0x30000]

    for offset in offsets:
        if offset + 320 >= len(data):
            continue
        # Add 10 tiles worth of 4bpp data (32 bytes per tile)
        for tile_idx in range(10):
            tile_offset = offset + (tile_idx * 32)
            for byte_idx in range(32):
                data[tile_offset + byte_idx] = (tile_idx + byte_idx) % 256


def _add_incrementing_pattern(data: bytearray, offset: int = 0x1000, length: int = 256) -> None:
    """Add simple incrementing byte pattern for testing.

    Args:
        data: Mutable bytearray to modify in-place
        offset: Starting offset
        length: Number of bytes
    """
    if offset + length > len(data):
        return
    for i in range(length):
        data[offset + i] = i % 256


@pytest.fixture
def test_rom_data_factory() -> Callable[[int], bytearray]:
    """Factory fixture for creating raw ROM data of any size.

    Returns:
        A callable that creates ROM data: (size: int) -> bytearray

    Example:
        def test_something(test_rom_data_factory):
            data = test_rom_data_factory(32 * 1024)  # 32KB
    """
    def _create_rom_data(size: int = ROM_SIZES["default"]) -> bytearray:
        data = bytearray(size)
        # Add some non-zero content for tests that check for actual data
        _add_incrementing_pattern(data)
        return data

    return _create_rom_data


@pytest.fixture
def test_rom_file(tmp_path: Path) -> Callable[..., str]:
    """Factory fixture for creating test ROM files with various configurations.

    Returns:
        A callable that creates a ROM file and returns its path.

    Example:
        def test_something(test_rom_file):
            path = test_rom_file()  # Default 1MB
            path = test_rom_file(size="small")  # 13KB
            path = test_rom_file(size="large", with_header=True, with_sprites=True)
    """
    _counter = [0]  # Mutable counter for unique filenames

    def _create_rom_file(
        size: str | int = "default",
        with_header: bool = False,
        with_sprites: bool = False,
        filename: str | None = None,
    ) -> str:
        """Create a test ROM file.

        Args:
            size: Either a preset name ("tiny", "small", "medium", "default", "large")
                  or an int specifying exact size in bytes
            with_header: If True, add SNES internal header
            with_sprites: If True, add sprite/tile patterns
            filename: Custom filename (default: test_N.sfc)

        Returns:
            Path to the created ROM file as a string
        """
        # Resolve size
        if isinstance(size, str):
            rom_size = ROM_SIZES.get(size, ROM_SIZES["default"])
        else:
            rom_size = size

        # Generate unique filename
        if filename is None:
            _counter[0] += 1
            filename = f"test_{_counter[0]}.sfc"

        rom_path = tmp_path / filename
        rom_data = bytearray(rom_size)

        # Add content based on options
        _add_incrementing_pattern(rom_data)

        if with_header and rom_size >= 0x8000:
            _create_snes_header(rom_data)

        if with_sprites and rom_size >= 0x40000:
            _add_sprite_patterns(rom_data)

        rom_path.write_bytes(rom_data)
        return str(rom_path)

    return _create_rom_file


@pytest.fixture
def test_vram_file(tmp_path: Path) -> Callable[..., str]:
    """Factory fixture for creating VRAM dump files.

    Returns:
        A callable that creates a VRAM file and returns its path.

    Example:
        def test_something(test_vram_file):
            path = test_vram_file()  # Default 64KB
            path = test_vram_file(size=32 * 1024, with_tiles=True)
    """
    _counter = [0]

    def _create_vram_file(
        size: int = 64 * 1024,
        with_tiles: bool = True,
        filename: str | None = None,
    ) -> str:
        """Create a test VRAM dump file.

        Args:
            size: VRAM size in bytes (default 64KB)
            with_tiles: If True, add tile pattern data
            filename: Custom filename (default: test_vram_N.dmp)

        Returns:
            Path to the created VRAM file as a string
        """
        if filename is None:
            _counter[0] += 1
            filename = f"test_vram_{_counter[0]}.dmp"

        vram_path = tmp_path / filename
        vram_data = bytearray(size)

        if with_tiles:
            # Add 4bpp tile patterns (32 bytes per tile)
            for i in range(0, min(len(vram_data), 32 * 100), 32):
                for j in range(32):
                    vram_data[i + j] = (i // 32 + j) % 256

        vram_path.write_bytes(vram_data)
        return str(vram_path)

    return _create_vram_file


# Legacy compatibility fixtures for tests that use the old simple interface
@pytest.fixture
def simple_test_rom_file(tmp_path: Path) -> str:
    """Simple ROM file fixture for backward compatibility.

    Creates a 13KB ROM file with basic test data.
    Prefer test_rom_file factory for new tests.
    """
    rom_file = tmp_path / "test.sfc"
    rom_file.write_bytes(b"TEST_ROM_DATA" * 1000)  # ~13KB
    return str(rom_file)


@pytest.fixture
def simple_test_rom_data() -> bytearray:
    """Simple ROM data fixture for backward compatibility.

    Creates 32KB of test data.
    Prefer test_rom_data_factory for new tests.
    """
    return bytearray(b'\x00\x01\x02\x03' * 256 * 32)  # 32KB


__all__ = [
    "ROM_SIZES",
    "test_rom_data_factory",
    "test_rom_file",
    "test_vram_file",
    "simple_test_rom_file",
    "simple_test_rom_data",
]
