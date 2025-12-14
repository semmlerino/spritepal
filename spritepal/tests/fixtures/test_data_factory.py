"""
Consolidated test data factory for creating test files.

This module consolidates the various _create_test_files() implementations
that were duplicated across multiple test helper files.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image


@dataclass
class TestDataPaths:
    """Paths to test data files created by TestDataFactory."""

    base_dir: Path
    vram_path: Path
    cgram_path: Path
    oam_path: Path
    rom_path: Path
    sprite_path: Path
    palette_path: Path
    metadata_path: Path
    output_dir: Path


class TestDataFactory:
    """
    Factory for creating standardized test data files.

    Consolidates test file creation from:
    - test_dialog_helper.py
    - test_main_window_helper.py
    - test_main_window_helper_simple.py
    - test_managers.py (ExtractionManagerFixture, InjectionManagerFixture)
    - test_worker_helper.py

    Usage:
        paths = TestDataFactory.create_test_files(temp_dir)
        # Use paths.vram_path, paths.rom_path, etc.
    """

    # Standard file sizes
    VRAM_SIZE = 0x10000  # 64KB
    CGRAM_SIZE = 512  # 512 bytes (256 colors * 2 bytes)
    OAM_SIZE = 544  # 544 bytes
    ROM_SIZE = 0x400000  # 4MB

    # Sprite data offset in VRAM
    SPRITE_OFFSET = 0xC000
    SPRITE_DATA_SIZE = 0x1000  # 4KB of sprite data

    @classmethod
    def create_test_files(
        cls,
        base_dir: Path,
        *,
        create_sprite_png: bool = True,
        create_palette_json: bool = True,
        create_metadata: bool = True,
        minimal: bool = False,
    ) -> TestDataPaths:
        """
        Create all standard test data files in the given directory.

        Args:
            base_dir: Directory to create files in
            create_sprite_png: Whether to create a sprite PNG file
            create_palette_json: Whether to create a palette JSON file
            create_metadata: Whether to create a metadata JSON file
            minimal: If True, create minimal files (smaller sizes, less data)

        Returns:
            TestDataPaths with paths to all created files
        """
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)

        # Create output directory
        output_dir = base_dir / "output"
        output_dir.mkdir(exist_ok=True)

        # Create data files
        vram_path = cls.create_vram_file(base_dir / "test_VRAM.dmp", minimal=minimal)
        cgram_path = cls.create_cgram_file(base_dir / "test_CGRAM.dmp")
        oam_path = cls.create_oam_file(base_dir / "test_OAM.dmp")
        rom_path = cls.create_rom_file(base_dir / "test_ROM.sfc", minimal=minimal)

        # Create optional files
        sprite_path = base_dir / "test_sprite.png"
        if create_sprite_png:
            cls.create_sprite_png(sprite_path, minimal=minimal)

        palette_path = base_dir / "test_sprite.pal.json"
        if create_palette_json:
            cls.create_palette_json(palette_path)

        metadata_path = base_dir / "test_sprite.metadata.json"
        if create_metadata:
            cls.create_metadata_json(metadata_path, palette_path)

        return TestDataPaths(
            base_dir=base_dir,
            vram_path=vram_path,
            cgram_path=cgram_path,
            oam_path=oam_path,
            rom_path=rom_path,
            sprite_path=sprite_path,
            palette_path=palette_path,
            metadata_path=metadata_path,
            output_dir=output_dir,
        )

    @classmethod
    def create_vram_file(cls, path: Path, *, minimal: bool = False) -> Path:
        """
        Create a test VRAM file with sprite-like data pattern.

        Args:
            path: Path to create the file at
            minimal: If True, create a smaller file (32KB instead of 64KB)

        Returns:
            Path to the created file
        """
        size = 0x8000 if minimal else cls.VRAM_SIZE
        vram_data = bytearray(size)

        # Add sprite-like pattern at sprite offset
        sprite_offset = min(cls.SPRITE_OFFSET, size - cls.SPRITE_DATA_SIZE)
        if sprite_offset > 0:
            for i in range(min(cls.SPRITE_DATA_SIZE, size - sprite_offset)):
                vram_data[sprite_offset + i] = i % 256

        path.write_bytes(vram_data)
        return path

    @classmethod
    def create_cgram_file(cls, path: Path) -> Path:
        """
        Create a test CGRAM file with realistic palette data.

        The file contains BGR555 format color data.

        Returns:
            Path to the created file
        """
        cgram_data = bytearray(cls.CGRAM_SIZE)

        # Add basic palette colors (BGR555 format)
        palette_colors = [
            0x0000,  # Black
            0x001F,  # Red
            0x03E0,  # Green
            0x7C00,  # Blue
            0x7FFF,  # White
        ]

        for i, color in enumerate(palette_colors):
            if i * 2 + 1 < len(cgram_data):
                cgram_data[i * 2] = color & 0xFF
                cgram_data[i * 2 + 1] = (color >> 8) & 0xFF

        # Fill remaining with gradient pattern
        for i in range(len(palette_colors), 256):
            if i * 2 + 1 < len(cgram_data):
                cgram_data[i * 2] = i % 32
                cgram_data[i * 2 + 1] = (i // 32) % 32

        path.write_bytes(cgram_data)
        return path

    @classmethod
    def create_oam_file(cls, path: Path) -> Path:
        """
        Create a test OAM file with sprite entries.

        Returns:
            Path to the created file
        """
        oam_data = bytearray(cls.OAM_SIZE)

        # Add test sprite entries
        oam_data[0] = 0x50  # X position
        oam_data[1] = 0x50  # Y position
        oam_data[2] = 0x00  # Tile number
        oam_data[3] = 0x00  # Attributes

        path.write_bytes(oam_data)
        return path

    @classmethod
    def create_rom_file(cls, path: Path, *, minimal: bool = False) -> Path:
        """
        Create a test ROM file with header and sprite data.

        Args:
            path: Path to create the file at
            minimal: If True, create a smaller file (32KB instead of 4MB)

        Returns:
            Path to the created file
        """
        size = 0x8000 if minimal else cls.ROM_SIZE
        rom_data = bytearray(size)

        # Add ROM header pattern (if file is large enough)
        header_offset = 0x7FC0
        header_text = b"TEST ROM FOR TESTING"
        if header_offset + len(header_text) < size:
            rom_data[header_offset : header_offset + len(header_text)] = header_text

        # Add sprite data at common offsets
        if not minimal:
            test_sprite_offsets = [0x8000, 0x200000, 0x300000, 0x380000]
            for offset in test_sprite_offsets:
                if offset + 0x800 < size:
                    for i in range(0x800):  # 2KB of sprite data
                        rom_data[offset + i] = ((i * 7) % 256)
        else:
            # Add data at beginning for minimal file
            for i in range(min(0x1000, size)):
                rom_data[i] = i % 256

        path.write_bytes(rom_data)
        return path

    @classmethod
    def create_sprite_png(cls, path: Path, *, minimal: bool = False) -> Path:
        """
        Create a test sprite PNG file.

        Args:
            path: Path to create the file at
            minimal: If True, create a 1x1 pixel image; otherwise 64x64

        Returns:
            Path to the created file
        """
        if minimal:
            # Minimal 1x1 pixel PNG data
            png_data = (
                b"\x89PNG\r\n\x1a\n"  # PNG signature
                b"\x00\x00\x00\rIHDR"  # IHDR chunk
                b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"  # 1x1 RGB
                b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xdd\x8d\xb4\x1c"  # Minimal data
                b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND
            )
            path.write_bytes(png_data)
        else:
            # Try to use PIL for a proper image, fall back to minimal PNG if not available
            try:
                from PIL import Image as PILImage

                # Create 64x64 grayscale image with pattern
                img = PILImage.new("L", (64, 64), 0)
                pixels = []
                for y in range(64):
                    for x in range(64):
                        value = ((x + y) * 4) % 256
                        pixels.append(value)
                img.putdata(pixels)
                img.save(str(path))
            except ImportError:
                # Fall back to minimal 16x16 PNG
                png_data = (
                    b"\x89PNG\r\n\x1a\n"
                    b"\x00\x00\x00\rIHDR"
                    b"\x00\x00\x00\x10\x00\x00\x00\x10\x08\x02\x00\x00\x00\x90\x91h6"
                    b"\x00\x00\x00\x19tEXtSoftware\x00Adobe ImageReadyq\xc9e<"
                    b"\x00\x00\x00\x0eIDATx\xdab\x00\x02\x00\x00\x05\x00\x01\r\n-\xdb"
                    b"\x00\x00\x00\x00IEND\xaeB`\x82"
                )
                path.write_bytes(png_data)

        return path

    @classmethod
    def create_palette_json(cls, path: Path) -> Path:
        """
        Create a test palette JSON file.

        Returns:
            Path to the created file
        """
        palette_data = {
            "8": [[255, 0, 255], [0, 0, 0], [255, 255, 255], [128, 128, 128]],
            "9": [[255, 255, 0], [0, 255, 0], [0, 0, 255], [255, 128, 0]],
        }
        path.write_text(json.dumps(palette_data, indent=2))
        return path

    @classmethod
    def create_metadata_json(cls, path: Path, palette_path: Path) -> Path:
        """
        Create a test metadata JSON file.

        Args:
            path: Path to create the file at
            palette_path: Path to the associated palette file

        Returns:
            Path to the created file
        """
        metadata = {
            "palette_files": [str(palette_path)],
            "active_palettes": [8, 9],
            "default_palette": 8,
        }
        path.write_text(json.dumps(metadata, indent=2))
        return path

    @classmethod
    def create_injection_test_files(cls, base_dir: Path) -> TestDataPaths:
        """
        Create test files specifically for injection testing.

        This creates empty/zeroed VRAM and ROM files suitable for injection targets.

        Returns:
            TestDataPaths with paths to all created files
        """
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)

        output_dir = base_dir / "output"
        output_dir.mkdir(exist_ok=True)

        # Create zeroed VRAM for injection target
        vram_path = base_dir / "input.vram"
        vram_path.write_bytes(b"\x00" * cls.VRAM_SIZE)

        # Create zeroed ROM for injection target
        rom_path = base_dir / "input.sfc"
        rom_path.write_bytes(b"\x00" * cls.ROM_SIZE)

        # Create sprite image
        sprite_path = base_dir / "test_sprite.png"
        cls.create_sprite_png(sprite_path)

        # Create placeholder paths for other files
        cgram_path = base_dir / "test_CGRAM.dmp"
        oam_path = base_dir / "test_OAM.dmp"
        palette_path = base_dir / "test_sprite.pal.json"
        metadata_path = base_dir / "test_sprite.metadata.json"

        return TestDataPaths(
            base_dir=base_dir,
            vram_path=vram_path,
            cgram_path=cgram_path,
            oam_path=oam_path,
            rom_path=rom_path,
            sprite_path=sprite_path,
            palette_path=palette_path,
            metadata_path=metadata_path,
            output_dir=output_dir,
        )


# Convenience functions for backwards compatibility
def create_test_vram(path: Path | str, *, minimal: bool = False) -> Path:
    """Create a test VRAM file. Wrapper for TestDataFactory.create_vram_file."""
    return TestDataFactory.create_vram_file(Path(path), minimal=minimal)


def create_test_cgram(path: Path | str) -> Path:
    """Create a test CGRAM file. Wrapper for TestDataFactory.create_cgram_file."""
    return TestDataFactory.create_cgram_file(Path(path))


def create_test_rom(path: Path | str, *, minimal: bool = False) -> Path:
    """Create a test ROM file. Wrapper for TestDataFactory.create_rom_file."""
    return TestDataFactory.create_rom_file(Path(path), minimal=minimal)


def create_test_sprite_png(path: Path | str, *, minimal: bool = False) -> Path:
    """Create a test sprite PNG. Wrapper for TestDataFactory.create_sprite_png."""
    return TestDataFactory.create_sprite_png(Path(path), minimal=minimal)
