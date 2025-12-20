"""
Test fixture managers for real extraction/injection logic

Provides real manager instances with test data instead of mocks,
improving test reliability and reducing mocking overhead.

NOTE: This file directly instantiates managers for testing purposes.
The deprecation warning is suppressed since these are test fixtures.
"""
from __future__ import annotations

import os
import sys
import tempfile
import warnings

import pytest

# Suppress deprecation warning for direct manager instantiation in test fixtures
warnings.filterwarnings(
    "ignore",
    message=r"Direct SessionManager instantiation is deprecated",
    category=DeprecationWarning,
)
from PIL import Image

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]

from core.managers import SessionManager
from core.managers.core_operations_manager import CoreOperationsManager
from ui.row_arrangement.grid_arrangement_manager import (
    GridArrangementManager,
    TilePosition,
)
from ui.row_arrangement.grid_image_processor import GridImageProcessor
from ui.row_arrangement.grid_preview_generator import GridPreviewGenerator
from ui.row_arrangement.palette_colorizer import PaletteColorizer
from ui.row_arrangement.preview_generator import PreviewGenerator


class ExtractionManagerFixture:
    """Test fixture providing real extraction manager with test data.

    Uses CoreOperationsManager which implements ExtractionManagerProtocol.
    """

    def __init__(self, temp_dir: str | None = None):
        from pathlib import Path

        from tests.fixtures.test_data_factory import TestDataFactory

        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.manager = CoreOperationsManager()

        # Use TestDataFactory for file creation (DRY consolidation)
        paths = TestDataFactory.create_test_files(Path(self.temp_dir))
        self.vram_path = str(paths.vram_path)
        self.cgram_path = str(paths.cgram_path)
        self.oam_path = str(paths.oam_path)
        self.rom_path = str(paths.rom_path)
        self.output_dir = str(paths.output_dir)

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
    """Test fixture providing real injection manager with test data.

    Uses CoreOperationsManager which implements InjectionManagerProtocol.
    """

    def __init__(self, temp_dir: str | None = None):
        from pathlib import Path

        from tests.fixtures.test_data_factory import TestDataFactory

        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.manager = CoreOperationsManager()

        # Use TestDataFactory for injection test files (DRY consolidation)
        paths = TestDataFactory.create_injection_test_files(Path(self.temp_dir))
        self.sprite_path = str(paths.sprite_path)
        self.vram_input_path = str(paths.vram_path)
        self.vram_output_path = os.path.join(self.temp_dir, "output.vram")
        self.rom_input_path = str(paths.rom_path)
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
