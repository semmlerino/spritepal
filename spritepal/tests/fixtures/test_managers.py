"""
Test fixture managers for real extraction/injection logic

Provides real manager instances with test data instead of mocks,
improving test reliability and reducing mocking overhead.
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest
from PIL import Image

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
]

from core.managers import ExtractionManager, InjectionManager, SessionManager
from ui.row_arrangement.grid_arrangement_manager import (
    GridArrangementManager,
    TilePosition,
)
from ui.row_arrangement.grid_image_processor import GridImageProcessor
from ui.row_arrangement.grid_preview_generator import GridPreviewGenerator
from ui.row_arrangement.palette_colorizer import PaletteColorizer
from ui.row_arrangement.preview_generator import PreviewGenerator


class ExtractionManagerFixture:
    """Test fixture providing real ExtractionManager with test data"""

    def __init__(self, temp_dir: str | None = None):
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.manager = ExtractionManager()
        self._create_test_files()

    def _create_test_files(self):
        """Create realistic test files for extraction"""
        # Create test VRAM file with sprite-like data pattern
        vram_data = bytearray(0x10000)  # 64KB
        # Add some sprite-like pattern at sprite offset
        sprite_offset = 0xC000
        for i in range(0x1000):  # 4KB of sprite data
            vram_data[sprite_offset + i] = (i % 256)  # Pattern data

        self.vram_path = os.path.join(self.temp_dir, "test.vram")
        with open(self.vram_path, "wb") as f:
            f.write(vram_data)

        # Create test CGRAM file with realistic palette data
        cgram_data = bytearray(512)  # 512 bytes
        # Add some basic palette colors (BGR555 format)
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

        self.cgram_path = os.path.join(self.temp_dir, "test.cgram")
        with open(self.cgram_path, "wb") as f:
            f.write(cgram_data)

        # Create test OAM file
        oam_data = b"\x00" * 544  # 544 bytes of OAM data
        self.oam_path = os.path.join(self.temp_dir, "test.oam")
        with open(self.oam_path, "wb") as f:
            f.write(oam_data)

        # Create test ROM file with header and sprite data
        rom_data = bytearray(0x400000)  # 4MB ROM
        # Add ROM header pattern
        rom_data[0x7FC0:0x7FE0] = b"TEST ROM FOR TESTING"
        # Add some sprite data at common offsets
        test_sprite_offsets = [0x200000, 0x300000, 0x380000]
        for offset in test_sprite_offsets:
            if offset + 0x800 < len(rom_data):
                for i in range(0x800):  # 2KB of sprite data
                    rom_data[offset + i] = ((i * 7) % 256)  # Pattern

        self.rom_path = os.path.join(self.temp_dir, "test.sfc")
        with open(self.rom_path, "wb") as f:
            f.write(rom_data)

        self.output_dir = os.path.join(self.temp_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)

    def get_vram_extraction_params(self):
        """Get realistic VRAM extraction parameters"""
        return {
            "vram_path": self.vram_path,
            "cgram_path": self.cgram_path,
            "oam_path": self.oam_path,
            "output_base": os.path.join(self.output_dir, "sprite"),
            "vram_offset": 0xC000,
            "sprite_size": (8, 8),
            "create_metadata": True,
            "create_grayscale": True
        }

    def get_rom_extraction_params(self):
        """Get realistic ROM extraction parameters"""
        return {
            "rom_path": self.rom_path,
            "offset": 0x200000,
            "output_base": os.path.join(self.output_dir, "rom_sprite"),
            "sprite_size": (16, 16),
            "create_metadata": True
        }

    def cleanup(self):
        """Clean up test files"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

class InjectionManagerFixture:
    """Test fixture providing real InjectionManager with test data"""

    def __init__(self, temp_dir: str | None = None):
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.manager = InjectionManager()
        self._create_test_files()

    def _create_test_files(self):
        """Create realistic test files for injection"""
        # Create test sprite image
        sprite_image = Image.new("L", (64, 64), 0)  # 64x64 grayscale
        # Add some pattern to the sprite
        pixels = []
        for y in range(64):
            for x in range(64):
                # Create a simple pattern
                value = ((x + y) * 4) % 256
                pixels.append(value)
        sprite_image.putdata(pixels)

        self.sprite_path = os.path.join(self.temp_dir, "test_sprite.png")
        sprite_image.save(self.sprite_path)

        # Create test VRAM file for injection target
        vram_data = b"\x00" * 0x10000  # 64KB
        self.vram_input_path = os.path.join(self.temp_dir, "input.vram")
        with open(self.vram_input_path, "wb") as f:
            f.write(vram_data)

        self.vram_output_path = os.path.join(self.temp_dir, "output.vram")

        # Create test ROM file for injection target
        rom_data = b"\x00" * 0x400000  # 4MB
        self.rom_input_path = os.path.join(self.temp_dir, "input.sfc")
        with open(self.rom_input_path, "wb") as f:
            f.write(rom_data)

        self.rom_output_path = os.path.join(self.temp_dir, "output.sfc")

    def get_vram_injection_params(self):
        """Get realistic VRAM injection parameters"""
        return {
            "sprite_path": self.sprite_path,
            "input_vram_path": self.vram_input_path,
            "output_vram_path": self.vram_output_path,
            "vram_offset": 0xC000
        }

    def get_rom_injection_params(self):
        """Get realistic ROM injection parameters"""
        return {
            "sprite_path": self.sprite_path,
            "input_rom_path": self.rom_input_path,
            "output_rom_path": self.rom_output_path,
            "rom_offset": 0x200000
        }

    def cleanup(self):
        """Clean up test files"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

class GridArrangementManagerFixture:
    """Test fixture providing real GridArrangementManager with test data"""

    def __init__(self, rows: int = 4, cols: int = 4):
        self.rows = rows
        self.cols = cols
        self.manager = GridArrangementManager(rows, cols)
        self._add_test_arrangements()

    def _add_test_arrangements(self):
        """Add some test arrangements"""
        # Add individual tiles
        self.manager.add_tile(TilePosition(0, 0))
        self.manager.add_tile(TilePosition(0, 1))

        # Add a row
        self.manager.add_row(1)

        # Add a column
        self.manager.add_column(2)

        # Create a group
        group_tiles = [TilePosition(3, 0), TilePosition(3, 1), TilePosition(3, 2)]
        self.manager.create_group_from_selection(group_tiles, "test_group", "Test Group")

    def get_manager(self) -> GridArrangementManager:
        """Get the configured manager"""
        return self.manager

    def get_test_tile_positions(self):
        """Get list of test tile positions"""
        return [
            TilePosition(0, 0), TilePosition(0, 1), TilePosition(0, 2), TilePosition(0, 3),
            TilePosition(1, 0), TilePosition(1, 1), TilePosition(1, 2), TilePosition(1, 3),
            TilePosition(2, 0), TilePosition(2, 1), TilePosition(2, 2), TilePosition(2, 3),
            TilePosition(3, 0), TilePosition(3, 1), TilePosition(3, 2), TilePosition(3, 3),
        ]

class GridImageProcessorFixture:
    """Test fixture providing real GridImageProcessor with test data"""

    def __init__(self, temp_dir: str | None = None):
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.processor = GridImageProcessor()
        self._create_test_sprite()

    def _create_test_sprite(self):
        """Create a test sprite image"""
        # Create 128x128 sprite (8x8 tiles, 16 tiles per row)
        sprite_image = Image.new("L", (128, 128), 0)

        # Create a pattern with distinct tiles
        pixels = []
        for y in range(128):
            for x in range(128):
                # Create tile-based pattern
                tile_x = x // 8
                tile_y = y // 8
                local_x = x % 8
                local_y = y % 8

                # Each tile has a unique pattern based on its position
                tile_id = tile_y * 16 + tile_x
                value = ((tile_id * 16) + (local_x + local_y * 2)) % 256
                pixels.append(value)

        sprite_image.putdata(pixels)

        self.sprite_path = os.path.join(self.temp_dir, "test_grid_sprite.png")
        sprite_image.save(self.sprite_path)

        # Process the sprite
        self.original_image, self.tiles = self.processor.process_sprite_sheet_as_grid(
            self.sprite_path, tiles_per_row=16
        )

    def get_processor(self) -> GridImageProcessor:
        """Get the processor with test data"""
        return self.processor

    def get_test_data(self):
        """Get test image and tiles data"""
        return self.original_image, self.tiles

    def cleanup(self):
        """Clean up test files"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

class PaletteColorizerFixture:
    """Test fixture providing real PaletteColorizer with test data"""

    def __init__(self):
        self.colorizer = PaletteColorizer()
        self._setup_test_palettes()

    def _setup_test_palettes(self):
        """Set up test palettes"""
        test_palettes = {}

        # Create test palettes for indices 8-15 (sprite palettes)
        for pal_idx in range(8, 16):
            # Create a distinct palette for each index
            palette = []
            for color_idx in range(16):
                # Generate distinct colors based on palette and color index
                red = (pal_idx * 32 + color_idx * 8) % 256
                green = (pal_idx * 16 + color_idx * 12) % 256
                blue = (pal_idx * 8 + color_idx * 16) % 256
                palette.append((red, green, blue))

            test_palettes[pal_idx] = palette

        self.colorizer.set_palettes(test_palettes)

    def get_colorizer(self) -> PaletteColorizer:
        """Get the configured colorizer"""
        return self.colorizer

    def get_test_palettes(self):
        """Get the test palettes dictionary"""
        return self.colorizer.get_palettes()

class PreviewGeneratorFixture:
    """Test fixture providing real PreviewGenerator with test data"""

    def __init__(self):
        self.colorizer_fixture = PaletteColorizerFixture()
        self.colorizer = self.colorizer_fixture.get_colorizer()
        self.preview_generator = PreviewGenerator(self.colorizer)
        self.grid_preview_generator = GridPreviewGenerator(self.colorizer)

    def get_preview_generator(self) -> PreviewGenerator:
        """Get the preview generator"""
        return self.preview_generator

    def get_grid_preview_generator(self) -> GridPreviewGenerator:
        """Get the grid preview generator"""
        return self.grid_preview_generator

    def get_colorizer(self) -> PaletteColorizer:
        """Get the colorizer"""
        return self.colorizer

class SessionManagerFixture:
    """Test fixture providing real SessionManager for testing"""

    def __init__(self, temp_dir: str | None = None):
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        # Create session manager with test-specific settings path
        self.settings_path = os.path.join(self.temp_dir, "test_settings.json")
        self.manager = SessionManager(settings_path=self.settings_path)

    def get_manager(self) -> SessionManager:
        """Get the session manager"""
        return self.manager

    def cleanup(self):
        """Clean up test files"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

# Convenience functions for creating test fixtures
def create_extraction_manager_fixture(temp_dir: str | None = None) -> ExtractionManagerFixture:
    """Create a test extraction manager fixture"""
    return ExtractionManagerFixture(temp_dir)

def create_injection_manager_fixture(temp_dir: str | None = None) -> InjectionManagerFixture:
    """Create a test injection manager fixture"""
    return InjectionManagerFixture(temp_dir)

def create_grid_arrangement_fixture(rows: int = 4, cols: int = 4) -> GridArrangementManagerFixture:
    """Create a test grid arrangement manager fixture"""
    return GridArrangementManagerFixture(rows, cols)

def create_grid_processor_fixture(temp_dir: str | None = None) -> GridImageProcessorFixture:
    """Create a test grid image processor fixture"""
    return GridImageProcessorFixture(temp_dir)

def create_colorizer_fixture() -> PaletteColorizerFixture:
    """Create a test palette colorizer fixture"""
    return PaletteColorizerFixture()

def create_preview_generator_fixture() -> PreviewGeneratorFixture:
    """Create a test preview generator fixture"""
    return PreviewGeneratorFixture()

def create_session_manager_fixture(temp_dir: str | None = None) -> SessionManagerFixture:
    """Create a test session manager fixture"""
    return SessionManagerFixture(temp_dir)
