"""
Unit tests for GridImageProcessor
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from PIL import Image

from ui.row_arrangement.grid_arrangement_manager import (
    # Systematic pytest markers applied based on test content analysis
    TileGroup,
    TilePosition,
)
from ui.row_arrangement.grid_image_processor import GridImageProcessor

pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.slow,
    pytest.mark.allows_registry_state,
]
class TestGridImageProcessor:
    """Test the GridImageProcessor class"""

    def test_init(self):
        """Test processor initialization"""
        processor = GridImageProcessor()

        # Check inherited attributes
        assert processor.tile_width == 0
        assert processor.tile_height == 0

        # Check new attributes
        assert processor.tiles == {}
        assert processor.grid_rows == 0
        assert processor.grid_cols == 0
        assert processor.original_image is None

    def test_extract_tiles_as_grid_valid(self):
        """Test extracting tiles as grid with valid input"""
        processor = GridImageProcessor()

        # Create a test image (16x16 pixels, 2x2 tiles of 8x8 each)
        test_image = Image.new("L", (16, 16))

        # Mock the calculate_tile_dimensions method
        processor.calculate_tile_dimensions = Mock(return_value=(8, 8))
        processor.tile_width = 8
        processor.tile_height = 8

        result = processor.extract_tiles_as_grid(test_image, 2)

        # Should return 4 tiles (2x2 grid)
        assert len(result) == 4
        assert processor.grid_rows == 2
        assert processor.grid_cols == 2

        # Check that all expected positions are present
        expected_positions = [
            TilePosition(0, 0),
            TilePosition(0, 1),
            TilePosition(1, 0),
            TilePosition(1, 1),
        ]

        for pos in expected_positions:
            assert pos in result
            assert isinstance(result[pos], Image.Image)
            assert result[pos].size == (8, 8)

    def test_extract_tiles_as_grid_invalid_tiles_per_row(self):
        """Test extracting tiles with invalid tiles_per_row"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Test zero tiles per row
        with pytest.raises(ValueError, match="tiles_per_row must be positive"):
            processor.extract_tiles_as_grid(test_image, 0)

        # Test negative tiles per row
        with pytest.raises(ValueError, match="tiles_per_row must be positive"):
            processor.extract_tiles_as_grid(test_image, -1)

    def test_extract_tiles_as_grid_invalid_image(self):
        """Test extracting tiles with invalid image"""
        processor = GridImageProcessor()

        # Test None image
        with pytest.raises(ValueError, match="Invalid image dimensions"):
            processor.extract_tiles_as_grid(None, 2)

        # Test zero-width image
        invalid_image = Image.new("L", (0, 16))
        with pytest.raises(ValueError, match="Invalid image dimensions"):
            processor.extract_tiles_as_grid(invalid_image, 2)

        # Test zero-height image
        invalid_image = Image.new("L", (16, 0))
        with pytest.raises(ValueError, match="Invalid image dimensions"):
            processor.extract_tiles_as_grid(invalid_image, 2)

    def test_extract_tiles_as_grid_invalid_tile_dimensions(self):
        """Test extracting tiles when tile dimensions are invalid"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Mock calculate_tile_dimensions to return invalid dimensions
        processor.calculate_tile_dimensions = Mock(return_value=(0, 8))
        processor.tile_width = 0
        processor.tile_height = 8

        with pytest.raises(ValueError, match="Invalid tile dimensions"):
            processor.extract_tiles_as_grid(test_image, 2)

        # Test negative tile dimensions
        processor.tile_width = -1
        processor.tile_height = 8

        with pytest.raises(ValueError, match="Invalid tile dimensions"):
            processor.extract_tiles_as_grid(test_image, 2)

    def test_get_tile_valid(self):
        """Test getting a specific tile"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 2)

        # Get valid tile
        tile = processor.get_tile(TilePosition(0, 0))
        assert tile is not None
        assert isinstance(tile, Image.Image)
        assert tile.size == (8, 8)

    def test_get_tile_invalid(self):
        """Test getting a non-existent tile"""
        processor = GridImageProcessor()

        # Get tile that doesn't exist
        tile = processor.get_tile(TilePosition(10, 10))
        assert tile is None

    def test_get_column_valid(self):
        """Test getting all tiles in a column"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 2)

        # Get column 0
        column_tiles = processor.get_column(0)
        assert len(column_tiles) == 2  # 2 rows

        # Check positions
        positions = [pos for pos, _ in column_tiles]
        assert TilePosition(0, 0) in positions
        assert TilePosition(1, 0) in positions

        # Check images
        for _pos, img in column_tiles:
            assert isinstance(img, Image.Image)
            assert img.size == (8, 8)

    def test_get_column_empty(self):
        """Test getting column when no tiles extracted"""
        processor = GridImageProcessor()
        processor.grid_rows = 2
        processor.grid_cols = 2

        # Get column from empty processor
        column_tiles = processor.get_column(0)
        assert len(column_tiles) == 0

    def test_get_row_tiles_valid(self):
        """Test getting all tiles in a row"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 2)

        # Get row 0
        row_tiles = processor.get_row_tiles(0)
        assert len(row_tiles) == 2  # 2 columns

        # Check positions
        positions = [pos for pos, _ in row_tiles]
        assert TilePosition(0, 0) in positions
        assert TilePosition(0, 1) in positions

        # Check images
        for _pos, img in row_tiles:
            assert isinstance(img, Image.Image)
            assert img.size == (8, 8)

    def test_get_row_tiles_empty(self):
        """Test getting row when no tiles extracted"""
        processor = GridImageProcessor()
        processor.grid_rows = 2
        processor.grid_cols = 2

        # Get row from empty processor
        row_tiles = processor.get_row_tiles(0)
        assert len(row_tiles) == 0

    def test_get_tile_group_valid(self):
        """Test getting tiles for a group"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 2)

        # Create a group
        group_tiles = [TilePosition(0, 0), TilePosition(0, 1)]
        group = TileGroup("test_group", group_tiles, 2, 1)

        # Get group tiles
        result = processor.get_tile_group(group)
        assert len(result) == 2

        # Check positions
        positions = [pos for pos, _ in result]
        assert TilePosition(0, 0) in positions
        assert TilePosition(0, 1) in positions

    def test_get_tile_group_partial(self):
        """Test getting tiles for a group where some tiles don't exist"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 2)

        # Create a group with some non-existent tiles
        group_tiles = [TilePosition(0, 0), TilePosition(5, 5)]  # (5,5) doesn't exist
        group = TileGroup("test_group", group_tiles, 2, 1)

        # Get group tiles
        result = processor.get_tile_group(group)
        assert len(result) == 1  # Only one tile exists

        # Check that only the valid tile is returned
        positions = [pos for pos, _ in result]
        assert TilePosition(0, 0) in positions
        assert TilePosition(5, 5) not in positions

    def test_create_image_from_tiles_valid(self):
        """Test creating image from tiles"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 2)

        # Create image from some tiles
        tiles = [
            (TilePosition(0, 0), processor.get_tile(TilePosition(0, 0))),
            (TilePosition(0, 1), processor.get_tile(TilePosition(0, 1))),
        ]

        result = processor.create_image_from_tiles(tiles)

        # Should create a 16x8 image (2 tiles wide, 1 tile high)
        assert result.size == (16, 8)
        assert result.mode == "L"

    def test_create_image_from_tiles_empty(self):
        """Test creating image from empty tiles list"""
        processor = GridImageProcessor()

        result = processor.create_image_from_tiles([])

        # Should return a 1x1 image
        assert result.size == (1, 1)
        assert result.mode == "L"

    def test_create_image_from_tiles_with_width(self):
        """Test creating image from tiles with specific width"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 2)

        # Create image from tiles with specific width
        tiles = [
            (TilePosition(0, 0), processor.get_tile(TilePosition(0, 0))),
            (TilePosition(0, 1), processor.get_tile(TilePosition(0, 1))),
            (TilePosition(1, 0), processor.get_tile(TilePosition(1, 0))),
            (TilePosition(1, 1), processor.get_tile(TilePosition(1, 1))),
        ]

        result = processor.create_image_from_tiles(tiles, arrangement_width=2)

        # Should create a 16x16 image (2 tiles wide, 2 tiles high)
        assert result.size == (16, 16)
        assert result.mode == "L"

    def test_create_column_strip_valid(self):
        """Test creating column strip"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 2)

        # Create column strip
        strip = processor.create_column_strip(0)

        assert strip is not None
        assert strip.size == (8, 16)  # 1 tile wide, 2 tiles high
        assert strip.mode == "L"

    def test_create_column_strip_empty(self):
        """Test creating column strip for empty column"""
        processor = GridImageProcessor()
        processor.grid_rows = 2
        processor.grid_cols = 2

        # Create strip for empty column
        strip = processor.create_column_strip(0)

        assert strip is None

    def test_create_row_strip_valid(self):
        """Test creating row strip"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (16, 16))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 2)

        # Create row strip
        strip = processor.create_row_strip(0)

        assert strip is not None
        assert strip.size == (16, 8)  # 2 tiles wide, 1 tile high
        assert strip.mode == "L"

    def test_create_row_strip_empty(self):
        """Test creating row strip for empty row"""
        processor = GridImageProcessor()
        processor.grid_rows = 2
        processor.grid_cols = 2

        # Create strip for empty row
        strip = processor.create_row_strip(0)

        assert strip is None

    def test_create_group_image_preserve_layout(self):
        """Test creating group image with preserved layout"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (24, 24))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 3)

        # Create a group
        group_tiles = [TilePosition(0, 0), TilePosition(0, 2), TilePosition(2, 0)]
        group = TileGroup("test_group", group_tiles, 3, 3)

        # Create group image with preserved layout
        result = processor.create_group_image(group, preserve_layout=True)

        assert result is not None
        assert result.size == (24, 24)  # 3x3 tiles to preserve layout
        assert result.mode == "L"

    def test_create_group_image_packed(self):
        """Test creating group image with packed layout"""
        processor = GridImageProcessor()
        test_image = Image.new("L", (24, 24))

        # Set up processor
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 3)

        # Create a group
        group_tiles = [TilePosition(0, 0), TilePosition(0, 2), TilePosition(2, 0)]
        group = TileGroup("test_group", group_tiles, 3, 3)

        # Create group image with packed layout
        result = processor.create_group_image(group, preserve_layout=False)

        assert result is not None
        assert result.size == (24, 8)  # 3 tiles wide, 1 tile high (packed)
        assert result.mode == "L"

    def test_create_group_image_empty(self):
        """Test creating group image for empty group"""
        processor = GridImageProcessor()

        # Create empty group
        group = TileGroup("empty_group", [], 0, 0)

        # Create group image
        result = processor.create_group_image(group)

        assert result is None

    def test_process_sprite_sheet_as_grid_valid(self, tmp_path):
        """Test complete sprite processing pipeline with real files"""
        # Create real test sprite file
        sprite_file = tmp_path / "test_sprite.png"
        test_image = Image.new("L", (16, 16))
        # Create a simple pattern for testing
        pixels = []
        for y in range(16):
            for x in range(16):
                pixels.append((x + y * 16) % 256)
        test_image.putdata(pixels)
        test_image.save(sprite_file)

        processor = GridImageProcessor()

        # Process sprite sheet using real file
        result_image, result_tiles = processor.process_sprite_sheet_as_grid(
            str(sprite_file), 2
        )

        # Check results - test actual behavior, not mocked behavior
        assert result_image is not None
        assert isinstance(result_image, Image.Image)
        assert result_image.size == (16, 16)
        assert result_tiles is not None
        assert isinstance(result_tiles, dict)
        assert processor.original_image is not None

        # Verify real tile extraction occurred
        assert len(result_tiles) > 0
        for pos, tile in result_tiles.items():
            assert isinstance(pos, TilePosition)
            assert isinstance(tile, Image.Image)

    def test_process_sprite_sheet_as_grid_file_not_found(self, tmp_path):
        """Test processing when sprite file doesn't exist"""
        processor = GridImageProcessor()

        # Use a path that definitely doesn't exist
        nonexistent_file = tmp_path / "nonexistent.png"

        with pytest.raises(FileNotFoundError, match="Sprite file not found"):
            processor.process_sprite_sheet_as_grid(str(nonexistent_file), 2)

    def test_process_sprite_sheet_as_grid_processing_error(self, tmp_path):
        """Test processing when an error occurs during processing"""
        # Create a file that exists but isn't a valid image
        invalid_file = tmp_path / "invalid.png"
        invalid_file.write_text("This is not a valid PNG file")

        processor = GridImageProcessor()

        with pytest.raises(Exception, match="Error processing sprite sheet"):
            processor.process_sprite_sheet_as_grid(str(invalid_file), 2)

        # Check cleanup
        assert processor.original_image is None
        assert processor.tiles == {}

    def test_grid_dimensions_calculation(self):
        """Test that grid dimensions are calculated correctly"""
        processor = GridImageProcessor()

        # Test with 24x16 image and 8x8 tiles
        test_image = Image.new("L", (24, 16))
        processor.tile_width = 8
        processor.tile_height = 8

        processor.extract_tiles_as_grid(test_image, 3)

        # Should have 3 columns and 2 rows
        assert processor.grid_cols == 3
        assert processor.grid_rows == 2
        assert len(processor.tiles) == 6  # 3 * 2 tiles

    def test_tile_extraction_coordinates(self):
        """Test that tiles are extracted at correct coordinates"""
        processor = GridImageProcessor()

        # Create test image with distinct patterns
        test_image = Image.new("L", (16, 16))
        pixels = test_image.load()

        # Fill different quadrants with different values
        for y in range(8):
            for x in range(8):
                pixels[x, y] = 100  # Top-left
                pixels[x + 8, y] = 150  # Top-right
                pixels[x, y + 8] = 200  # Bottom-left
                pixels[x + 8, y + 8] = 250  # Bottom-right

        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image, 2)

        # Check that each tile has the expected pixel values
        tile_00 = processor.get_tile(TilePosition(0, 0))
        tile_01 = processor.get_tile(TilePosition(0, 1))
        tile_10 = processor.get_tile(TilePosition(1, 0))
        tile_11 = processor.get_tile(TilePosition(1, 1))

        # Check pixel values in center of each tile
        assert tile_00.getpixel((4, 4)) == 100
        assert tile_01.getpixel((4, 4)) == 150
        assert tile_10.getpixel((4, 4)) == 200
        assert tile_11.getpixel((4, 4)) == 250

    def test_inheritance_from_row_image_processor(self):
        """Test that GridImageProcessor properly inherits from RowImageProcessor"""
        from ui.row_arrangement.image_processor import RowImageProcessor

        processor = GridImageProcessor()
        assert isinstance(processor, RowImageProcessor)

        # Check that inherited methods are available
        assert hasattr(processor, "load_sprite")
        assert hasattr(processor, "calculate_tile_dimensions")
        assert hasattr(processor, "extract_rows")
        assert hasattr(processor, "process_sprite_sheet")

    def test_clearing_tiles_on_new_extraction(self):
        """Test that tiles are cleared when extracting new grid"""
        processor = GridImageProcessor()

        # First extraction
        test_image1 = Image.new("L", (16, 16))
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image1, 2)

        initial_tile_count = len(processor.tiles)
        assert initial_tile_count == 4

        # Second extraction with different image
        test_image2 = Image.new("L", (8, 8))
        processor.tile_width = 8
        processor.tile_height = 8
        processor.extract_tiles_as_grid(test_image2, 1)

        # Should have different tiles now
        assert len(processor.tiles) == 1
        assert TilePosition(0, 0) in processor.tiles

    def test_edge_case_single_tile(self):
        """Test processing single tile image"""
        processor = GridImageProcessor()

        # Create single tile image
        test_image = Image.new("L", (8, 8))
        processor.tile_width = 8
        processor.tile_height = 8

        result = processor.extract_tiles_as_grid(test_image, 1)

        assert len(result) == 1
        assert TilePosition(0, 0) in result
        assert processor.grid_rows == 1
        assert processor.grid_cols == 1

    def test_edge_case_non_square_tiles(self):
        """Test processing with non-square tiles"""
        processor = GridImageProcessor()

        # Create image with rectangular tiles
        test_image = Image.new("L", (16, 8))
        processor.tile_width = 8
        processor.tile_height = 4

        result = processor.extract_tiles_as_grid(test_image, 2)

        assert len(result) == 4  # 2 columns, 2 rows
        assert processor.grid_rows == 2
        assert processor.grid_cols == 2

        # Check tile sizes
        for tile in result.values():
            assert tile.size == (8, 4)
