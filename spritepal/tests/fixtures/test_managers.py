"""
Test fixture managers for UI row arrangement components.

Provides real component instances with test data for integration testing.
For extraction/injection test files, use TestDataFactory directly.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from PIL import Image

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]

from ui.row_arrangement.grid_arrangement_manager import (
    GridArrangementManager,
    TilePosition,
)
from ui.row_arrangement.grid_image_processor import GridImageProcessor
from ui.row_arrangement.grid_preview_generator import GridPreviewGenerator
from ui.row_arrangement.palette_colorizer import PaletteColorizer
from ui.row_arrangement.preview_generator import PreviewGenerator


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

        self.sprite_path = str(Path(self.temp_dir) / "test_grid_sprite.png")
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
        if Path(self.temp_dir).exists():
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

# Convenience functions for creating test fixtures
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
