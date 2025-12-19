
from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]
"""
Test data generator for creating test ROMs with known content.
"""

import struct
from pathlib import Path
from typing import Any


class TestROMGenerator:
    """Generate test ROM files with known sprite data."""

    @staticmethod
    def create_4bpp_tile_data(tile_count: int, pattern: str = "gradient") -> bytes:
        """
        Create 4bpp tile data with known patterns.
        
        Args:
            tile_count: Number of 8x8 tiles to generate
            pattern: Pattern type ("gradient", "checkerboard", "solid", "random")
        
        Returns:
            Bytes of 4bpp tile data (32 bytes per tile)
        """
        tile_data = bytearray()

        for tile_idx in range(tile_count):
            if pattern == "gradient":
                # Create gradient pattern
                for row in range(8):
                    for plane in range(4):
                        # Each plane contributes to the color index
                        byte_val = (tile_idx + row * 8 + plane * 2) % 256
                        tile_data.append(byte_val)

            elif pattern == "checkerboard":
                # Create checkerboard pattern
                for row in range(8):
                    for plane in range(4):
                        if plane < 2:
                            # Low planes: alternating pattern
                            byte_val = 0xAA if (row % 2) == 0 else 0x55
                        else:
                            # High planes: inverse pattern
                            byte_val = 0x55 if (row % 2) == 0 else 0xAA
                        tile_data.append(byte_val)

            elif pattern == "solid":
                # Solid color tiles
                color_index = (tile_idx % 16)
                for row in range(8):
                    for plane in range(4):
                        # Set bits based on color index
                        bit_set = (color_index >> plane) & 1
                        byte_val = 0xFF if bit_set else 0x00
                        tile_data.append(byte_val)

            else:  # random
                # Random pattern
                for _ in range(32):
                    tile_data.append((tile_idx * 37 + _) % 256)

        return bytes(tile_data)

    @staticmethod
    def create_test_rom(size: int = 1024 * 1024) -> bytes:
        """
        Create a test ROM with various data patterns.
        
        Args:
            size: ROM size in bytes (default 1MB)
        
        Returns:
            ROM data bytes
        """
        rom_data = bytearray(size)

        # Fill with recognizable pattern
        for i in range(size):
            rom_data[i] = (i // 256) % 256

        # Add header-like data at beginning
        rom_data[0:4] = b'TEST'

        # Add version number
        rom_data[4:8] = struct.pack('<I', 0x01000000)  # Version 1.0.0.0

        return bytes(rom_data)

    @staticmethod
    def insert_sprite_at_offset(rom_data: bytearray, offset: int, sprite_data: bytes,
                              compress: bool = False) -> dict[str, Any]:
        """
        Insert sprite data at a specific offset in ROM.
        
        Args:
            rom_data: Mutable ROM data
            offset: Offset to insert at
            sprite_data: Sprite tile data
            compress: Whether to HAL-compress the data
        
        Returns:
            Dictionary with sprite info
        """
        sprite_info = {
            'offset': offset,
            'decompressed_size': len(sprite_data),
            'tile_count': len(sprite_data) // 32,
            'compressed': compress
        }

        if compress:
            # Note: HAL compression requires file I/O, so we'll skip actual compression in test data
            # For real testing, use actual ROM files with known compressed sprites
            data_to_insert = sprite_data
            sprite_info['compressed'] = False
            sprite_info['compressed_size'] = len(sprite_data)
        else:
            # Insert raw data
            data_to_insert = sprite_data
            sprite_info['compressed_size'] = len(sprite_data)

        # Check bounds
        if offset + len(data_to_insert) <= len(rom_data):
            rom_data[offset:offset + len(data_to_insert)] = data_to_insert
        else:
            raise ValueError(f"Sprite data at offset {offset} exceeds ROM size")

        return sprite_info

    @staticmethod
    def create_rom_with_sprites(sprites: list[dict[str, Any]], rom_size: int = 4 * 1024 * 1024) -> tuple[bytes, list[dict[str, Any]]]:
        """
        Create a ROM with multiple sprites at specified locations.
        
        Args:
            sprites: List of sprite definitions with 'offset', 'tile_count', 'pattern', 'compress'
            rom_size: Total ROM size
        
        Returns:
            Tuple of (ROM data, sprite info list)
        """
        # Create base ROM
        rom_data = bytearray(TestROMGenerator.create_test_rom(rom_size))
        sprite_infos = []

        for sprite_def in sprites:
            offset = sprite_def['offset']
            tile_count = sprite_def.get('tile_count', 64)
            pattern = sprite_def.get('pattern', 'gradient')
            compress = sprite_def.get('compress', True)

            # Generate sprite data
            sprite_data = TestROMGenerator.create_4bpp_tile_data(tile_count, pattern)

            # Insert into ROM
            sprite_info = TestROMGenerator.insert_sprite_at_offset(
                rom_data, offset, sprite_data, compress
            )
            sprite_infos.append(sprite_info)

        return bytes(rom_data), sprite_infos

    @staticmethod
    def create_kirby_like_rom() -> tuple[bytes, list[dict[str, Any]]]:
        """
        Create a ROM with Kirby-like sprite layout.
        
        Returns:
            Tuple of (ROM data, sprite info list)
        """
        sprites = [
            # Main character sprites
            {'offset': 0x200000, 'tile_count': 256, 'pattern': 'gradient', 'compress': True},
            {'offset': 0x206000, 'tile_count': 64, 'pattern': 'checkerboard', 'compress': True},
            {'offset': 0x208000, 'tile_count': 128, 'pattern': 'solid', 'compress': True},

            # Enemy sprites
            {'offset': 0x210000, 'tile_count': 96, 'pattern': 'random', 'compress': True},
            {'offset': 0x212000, 'tile_count': 48, 'pattern': 'gradient', 'compress': True},

            # Raw tile data (uncompressed)
            {'offset': 0x100000, 'tile_count': 32, 'pattern': 'checkerboard', 'compress': False},
        ]

        return TestROMGenerator.create_rom_with_sprites(sprites)

    @staticmethod
    def save_test_rom(path: Path, rom_data: bytes, sprite_infos: list[dict[str, Any]] | None = None):
        """
        Save test ROM to file with optional metadata.
        
        Args:
            path: Path to save ROM
            rom_data: ROM data bytes
            sprite_infos: Optional sprite information
        """
        # Save ROM
        path.write_bytes(rom_data)

        # Save metadata if provided
        if sprite_infos:
            import json
            metadata_path = path.with_suffix('.json')
            metadata = {
                'rom_file': path.name,
                'size': len(rom_data),
                'sprites': sprite_infos
            }
            metadata_path.write_text(json.dumps(metadata, indent=2))

# Utility functions for tests
def generate_test_sprite(tile_count: int = 64, pattern: str = "gradient") -> bytes:
    """Generate test sprite data quickly."""
    return TestROMGenerator.create_4bpp_tile_data(tile_count, pattern)

def generate_compressed_sprite(tile_count: int = 64) -> bytes:
    """Generate sprite data (compression requires file I/O)."""
    # Note: Actual HAL compression requires file operations
    # For testing, use real ROM files or pre-compressed data
    return generate_test_sprite(tile_count)
