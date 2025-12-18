"""
Unit tests for GridPreviewGenerator
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw

from ui.row_arrangement.grid_arrangement_manager import (
    # Systematic pytest markers applied based on test content analysis
    ArrangementType,
    GridArrangementManager,
    TileGroup,
    TilePosition,
)
from ui.row_arrangement.grid_image_processor import GridImageProcessor
from ui.row_arrangement.grid_preview_generator import GridPreviewGenerator
from ui.row_arrangement.palette_colorizer import PaletteColorizer

pytestmark = [
    pytest.mark.headless,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.unit,
    pytest.mark.ci_safe,
    pytest.mark.slow,
    pytest.mark.allows_registry_state,
]
class TestGridPreviewGenerator:
    """Test the GridPreviewGenerator class"""

    def test_init_without_colorizer(self):
        """Test initialization without colorizer"""
        generator = GridPreviewGenerator()

        assert generator.colorizer is None
        assert generator.grid_color == (128, 128, 128, 128)
        assert generator.selection_color == (255, 255, 0, 64)
        assert len(generator.group_colors) == 6
        assert generator.group_colors[0] == (255, 0, 0, 64)  # Red

    def test_init_with_colorizer(self):
        """Test initialization with colorizer"""
        colorizer = Mock(spec=PaletteColorizer)
        generator = GridPreviewGenerator(colorizer)

        assert generator.colorizer == colorizer
        assert generator.grid_color == (128, 128, 128, 128)
        assert generator.selection_color == (255, 255, 0, 64)

    def test_inheritance_from_preview_generator(self):
        """Test that GridPreviewGenerator inherits from PreviewGenerator"""
        from ui.row_arrangement.preview_generator import PreviewGenerator

        generator = GridPreviewGenerator()
        assert isinstance(generator, PreviewGenerator)

    def test_create_grid_arranged_image_empty_arrangement(self):
        """Test creating arranged image with empty arrangement"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock empty arrangement
        manager.get_arrangement_order.return_value = []

        result = generator.create_grid_arranged_image(processor, manager)

        assert result is None

    def test_create_grid_arranged_image_single_tile(self):
        """Test creating arranged image with single tile"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock single tile arrangement
        manager.get_arrangement_order.return_value = [(ArrangementType.TILE, "1,2")]

        # Mock tile image
        tile_image = Image.new("L", (8, 8))
        processor.get_tile.return_value = tile_image
        processor.tile_width = 8
        processor.tile_height = 8
        processor.grid_cols = 4

        # Call real method - don't mock _create_arranged_image_with_spacing
        result = generator.create_grid_arranged_image(processor, manager)

        # Verify actual behavior
        assert result is not None
        assert result.mode == "L"
        # Note: Actual size includes layout spacing, verify reasonable dimensions
        assert result.size[0] >= 8  # At least tile width
        assert result.size[1] >= 8  # At least tile height
        processor.get_tile.assert_called_once_with(TilePosition(1, 2))

    def test_create_grid_arranged_image_row_arrangement(self):
        """Test creating arranged image with row arrangement"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock row arrangement
        manager.get_arrangement_order.return_value = [(ArrangementType.ROW, "1")]

        # Mock row tiles
        tile1 = Image.new("L", (8, 8))
        tile2 = Image.new("L", (8, 8))
        row_tiles = [(TilePosition(1, 0), tile1), (TilePosition(1, 1), tile2)]
        processor.get_row_tiles.return_value = row_tiles
        processor.tile_width = 8
        processor.tile_height = 8
        processor.grid_cols = 4

        # Call real method - don't mock _create_arranged_image_with_spacing
        result = generator.create_grid_arranged_image(processor, manager)

        # Verify actual behavior - 2 tiles arranged
        assert result is not None
        assert result.mode == "L"
        # Note: Actual size includes layout spacing, verify reasonable dimensions
        assert result.size[0] >= 16  # At least 2 tiles wide
        assert result.size[1] >= 8   # At least tile height
        processor.get_row_tiles.assert_called_once_with(1)

    def test_create_grid_arranged_image_column_arrangement(self):
        """Test creating arranged image with column arrangement"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock column arrangement
        manager.get_arrangement_order.return_value = [(ArrangementType.COLUMN, "2")]

        # Mock column tiles
        tile1 = Image.new("L", (8, 8))
        tile2 = Image.new("L", (8, 8))
        col_tiles = [(TilePosition(0, 2), tile1), (TilePosition(1, 2), tile2)]
        processor.get_column.return_value = col_tiles
        processor.tile_width = 8
        processor.tile_height = 8
        processor.grid_cols = 4

        # Call real method - don't mock _create_arranged_image_with_spacing
        result = generator.create_grid_arranged_image(processor, manager)

        # Verify actual behavior - 2 tiles arranged
        assert result is not None
        assert result.mode == "L"
        # Note: Actual size includes layout spacing, verify reasonable dimensions
        assert result.size[0] >= 16  # At least 2 tiles wide
        assert result.size[1] >= 8   # At least tile height
        processor.get_column.assert_called_once_with(2)

    def test_create_grid_arranged_image_group_arrangement(self):
        """Test creating arranged image with group arrangement"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock group arrangement
        manager.get_arrangement_order.return_value = [
            (ArrangementType.GROUP, "test_group")
        ]

        # Mock group
        group = TileGroup("test_group", [TilePosition(0, 0), TilePosition(0, 1)], 2, 1)
        manager.get_groups.return_value = {"test_group": group}

        # Mock group tiles
        tile1 = Image.new("L", (8, 8))
        tile2 = Image.new("L", (8, 8))
        group_tiles = [(TilePosition(0, 0), tile1), (TilePosition(0, 1), tile2)]
        processor.get_tile_group.return_value = group_tiles
        processor.tile_width = 8
        processor.tile_height = 8
        processor.grid_cols = 4

        # Call real method - don't mock _create_arranged_image_with_spacing
        result = generator.create_grid_arranged_image(processor, manager)

        # Verify actual behavior - 2 tiles from group arranged
        assert result is not None
        assert result.mode == "L"
        # Note: Actual size includes layout spacing, verify reasonable dimensions
        assert result.size[0] >= 16  # At least 2 tiles wide
        assert result.size[1] >= 8   # At least tile height
        processor.get_tile_group.assert_called_once_with(group)

    def test_create_grid_arranged_image_mixed_arrangements(self):
        """Test creating arranged image with mixed arrangement types"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock mixed arrangement
        manager.get_arrangement_order.return_value = [
            (ArrangementType.TILE, "0,0"),
            (ArrangementType.ROW, "1"),
            (ArrangementType.COLUMN, "2"),
        ]

        # Mock tile
        tile_image = Image.new("L", (8, 8))
        processor.get_tile.return_value = tile_image

        # Mock row tiles
        row_tiles = [(TilePosition(1, 0), tile_image)]
        processor.get_row_tiles.return_value = row_tiles

        # Mock column tiles
        col_tiles = [(TilePosition(0, 2), tile_image)]
        processor.get_column.return_value = col_tiles

        processor.tile_width = 8
        processor.tile_height = 8
        processor.grid_cols = 4

        # Call real method - don't mock _create_arranged_image_with_spacing
        result = generator.create_grid_arranged_image(processor, manager)

        # Verify actual behavior - 3 tiles total (1 + 1 + 1) arranged
        assert result is not None
        assert result.mode == "L"
        # Note: Actual size includes layout spacing, verify reasonable dimensions
        assert result.size[0] >= 24  # At least 3 tiles wide
        assert result.size[1] >= 8   # At least tile height
        processor.get_tile.assert_called_once_with(TilePosition(0, 0))
        processor.get_row_tiles.assert_called_once_with(1)
        processor.get_column.assert_called_once_with(2)

    def test_create_grid_arranged_image_no_tiles(self):
        """Test creating arranged image when no tiles are found"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock arrangement that returns no tiles
        manager.get_arrangement_order.return_value = [(ArrangementType.TILE, "0,0")]
        processor.get_tile.return_value = None  # No tile found

        result = generator.create_grid_arranged_image(processor, manager)

        assert result is None

    def test_create_grid_preview_with_overlay_basic(self):
        """Test creating grid preview with basic overlay"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock original image
        original_image = Image.new("L", (16, 16))
        processor.original_image = original_image

        # Mock colorizer
        generator.colorizer = Mock(spec=PaletteColorizer)
        generator.colorizer.is_palette_mode.return_value = False

        # Mock arrangement data
        manager.get_arranged_tiles.return_value = [TilePosition(0, 0)]
        manager.get_groups.return_value = {}
        manager.get_tile_group.return_value = None

        processor.tile_width = 8
        processor.tile_height = 8
        processor.grid_cols = 2
        processor.grid_rows = 2

        result = generator.create_grid_preview_with_overlay(processor, manager)

        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == (16, 16)

    def test_create_grid_preview_with_overlay_no_original_image(self):
        """Test creating grid preview when no original image"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock no original image
        processor.original_image = None

        result = generator.create_grid_preview_with_overlay(processor, manager)

        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == (1, 1)

    def test_create_grid_preview_with_overlay_with_colorization(self):
        """Test creating grid preview with colorization"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock original image
        original_image = Image.new("L", (16, 16))
        processor.original_image = original_image

        # Mock colorizer with palette mode
        generator.colorizer = Mock(spec=PaletteColorizer)
        generator.colorizer.is_palette_mode.return_value = True
        colorized_image = Image.new("RGBA", (16, 16))
        generator.apply_palette_to_full_image = Mock(return_value=colorized_image)

        # Mock arrangement data
        manager.get_arranged_tiles.return_value = []
        manager.get_groups.return_value = {}

        processor.tile_width = 8
        processor.tile_height = 8
        processor.grid_cols = 2
        processor.grid_rows = 2

        result = generator.create_grid_preview_with_overlay(processor, manager)

        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == (16, 16)

    def test_create_grid_preview_with_overlay_with_selected_tiles(self):
        """Test creating grid preview with selected tiles"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock original image
        original_image = Image.new("L", (16, 16))
        processor.original_image = original_image

        # Mock colorizer
        generator.colorizer = Mock(spec=PaletteColorizer)
        generator.colorizer.is_palette_mode.return_value = False

        # Mock arrangement data
        manager.get_arranged_tiles.return_value = []
        manager.get_groups.return_value = {}

        processor.tile_width = 8
        processor.tile_height = 8
        processor.grid_cols = 2
        processor.grid_rows = 2

        # Add selected tiles
        selected_tiles = [TilePosition(0, 1), TilePosition(1, 0)]

        result = generator.create_grid_preview_with_overlay(
            processor, manager, selected_tiles=selected_tiles
        )

        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == (16, 16)

    def test_create_arranged_image_with_spacing_empty(self):
        """Test creating arranged image with spacing from empty tiles"""
        generator = GridPreviewGenerator()

        result = generator._create_arranged_image_with_spacing([], 8, 8, 2, 2)

        assert result.size == (1, 1)
        assert result.mode == "L"

    def test_create_arranged_image_with_spacing_no_spacing(self):
        """Test creating arranged image with no spacing"""
        generator = GridPreviewGenerator()

        # Create test tiles
        tile1 = Image.new("L", (8, 8))
        tile2 = Image.new("L", (8, 8))
        tiles = [(TilePosition(0, 0), tile1), (TilePosition(0, 1), tile2)]

        result = generator._create_arranged_image_with_spacing(tiles, 8, 8, 2, 0)

        assert result.size == (16, 8)  # 2 tiles wide, 1 tile high
        assert result.mode == "L"

    def test_create_arranged_image_with_spacing_with_spacing(self):
        """Test creating arranged image with spacing"""
        generator = GridPreviewGenerator()

        # Create test tiles
        tile1 = Image.new("L", (8, 8))
        tile2 = Image.new("L", (8, 8))
        tiles = [(TilePosition(0, 0), tile1), (TilePosition(0, 1), tile2)]

        result = generator._create_arranged_image_with_spacing(tiles, 8, 8, 2, 2)

        # Width: 2 tiles * 8 + 1 spacing * 2 = 18
        # Height: 1 row * 8 + 0 spacing = 8
        assert result.size == (18, 8)
        assert result.mode == "L"

    def test_create_arranged_image_with_spacing_multiple_rows(self):
        """Test creating arranged image with multiple rows"""
        generator = GridPreviewGenerator()

        # Create test tiles
        tiles = []
        for i in range(4):
            tile = Image.new("L", (8, 8))
            tiles.append((TilePosition(i // 2, i % 2), tile))

        result = generator._create_arranged_image_with_spacing(tiles, 8, 8, 2, 1)

        # Width: 2 tiles * 8 + 1 spacing * 1 = 17
        # Height: 2 rows * 8 + 1 spacing * 1 = 17
        assert result.size == (17, 17)
        assert result.mode == "L"

    def test_create_arranged_image_with_spacing_with_colorizer(self):
        """Test creating arranged image with colorizer"""
        colorizer = Mock(spec=PaletteColorizer)
        colorizer.is_palette_mode.return_value = True
        colorizer.get_display_image.return_value = Image.new("RGBA", (8, 8))

        generator = GridPreviewGenerator(colorizer)

        # Create test tiles
        tile1 = Image.new("L", (8, 8))
        tiles = [(TilePosition(0, 0), tile1)]

        result = generator._create_arranged_image_with_spacing(tiles, 8, 8, 1, 0)

        assert result.size == (8, 8)
        assert result.mode == "RGBA"
        colorizer.get_display_image.assert_called_once_with(0, tile1)

    def test_draw_grid(self):
        """Test drawing grid lines"""
        generator = GridPreviewGenerator()

        # Create test image and draw
        test_image = Image.new("RGBA", (16, 16))
        draw = ImageDraw.Draw(test_image)

        generator._draw_grid(draw, 8, 8, 2, 2)

        # The draw operations should complete without error
        # Testing visual output would require pixel-level verification
        # which is complex for this test
        assert True  # Test passes if no exceptions

    def test_highlight_tile(self):
        """Test highlighting a tile"""
        generator = GridPreviewGenerator()

        # Create test image and draw
        test_image = Image.new("RGBA", (16, 16))
        draw = ImageDraw.Draw(test_image)

        generator._highlight_tile(draw, TilePosition(0, 1), 8, 8, (255, 0, 0, 128))

        # The draw operations should complete without error
        assert True  # Test passes if no exceptions

    def test_export_grid_arrangement(self):
        """Test exporting grid arrangement"""
        generator = GridPreviewGenerator()

        # Create test image
        arranged_image = Image.new("L", (16, 16))

        # Mock the save method
        arranged_image.save = Mock()

        result = generator.export_grid_arrangement(
            "/path/to/sprite.png", arranged_image, "test"
        )

        # Function returns just filename (stem + arrangement + suffix), not full path
        assert result == "sprite_test_arranged.png"
        arranged_image.save.assert_called_once_with("sprite_test_arranged.png")

    def test_export_grid_arrangement_default_type(self):
        """Test exporting grid arrangement with default type"""
        generator = GridPreviewGenerator()

        # Create test image
        arranged_image = Image.new("L", (16, 16))

        # Mock the save method
        arranged_image.save = Mock()

        result = generator.export_grid_arrangement(
            "/path/to/sprite.png", arranged_image
        )

        # Function returns just filename (stem + arrangement + suffix), not full path
        assert result == "sprite_grid_arranged.png"
        arranged_image.save.assert_called_once_with("sprite_grid_arranged.png")

    def test_create_arrangement_preview_data(self):
        """Test creating arrangement preview data"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock processor data
        processor.grid_rows = 3
        processor.grid_cols = 4
        processor.tile_width = 8
        processor.tile_height = 8

        # Mock manager data
        manager.get_arrangement_order.return_value = [
            (ArrangementType.TILE, "0,0"),
            (ArrangementType.ROW, "1"),
        ]

        group = TileGroup("test_group", [TilePosition(0, 0)], 1, 1, "Test Group")
        manager.get_groups.return_value = {"test_group": group}
        manager.get_arranged_count.return_value = 5

        result = generator.create_arrangement_preview_data(manager, processor)

        assert result["grid_dimensions"]["rows"] == 3
        assert result["grid_dimensions"]["cols"] == 4
        assert result["grid_dimensions"]["tile_width"] == 8
        assert result["grid_dimensions"]["tile_height"] == 8

        assert len(result["arrangement_order"]) == 2
        assert result["arrangement_order"][0]["type"] == "tile"
        assert result["arrangement_order"][0]["key"] == "0,0"
        assert result["arrangement_order"][1]["type"] == "row"
        assert result["arrangement_order"][1]["key"] == "1"

        assert len(result["groups"]) == 1
        assert result["groups"][0]["id"] == "test_group"
        assert result["groups"][0]["name"] == "Test Group"
        assert result["groups"][0]["width"] == 1
        assert result["groups"][0]["height"] == 1
        assert result["groups"][0]["tiles"] == [{"row": 0, "col": 0}]

        assert result["total_tiles"] == 5

    def test_create_arrangement_preview_data_no_groups(self):
        """Test creating arrangement preview data with no groups"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock processor data
        processor.grid_rows = 2
        processor.grid_cols = 2
        processor.tile_width = 8
        processor.tile_height = 8

        # Mock manager data with no groups
        manager.get_arrangement_order.return_value = []
        manager.get_groups.return_value = {}
        manager.get_arranged_count.return_value = 0

        result = generator.create_arrangement_preview_data(manager, processor)

        assert result["grid_dimensions"]["rows"] == 2
        assert result["grid_dimensions"]["cols"] == 2
        assert len(result["arrangement_order"]) == 0
        assert len(result["groups"]) == 0
        assert result["total_tiles"] == 0

    def test_group_colors_cycling(self):
        """Test that group colors cycle properly"""
        generator = GridPreviewGenerator()

        # Should have 6 colors
        assert len(generator.group_colors) == 6

        # Colors should be unique
        assert len(set(generator.group_colors)) == 6

        # All colors should be RGBA tuples
        for color in generator.group_colors:
            assert len(color) == 4
            assert all(isinstance(c, int) and 0 <= c <= 255 for c in color)

    def test_inheritance_methods_available(self):
        """Test that inherited methods are available"""
        generator = GridPreviewGenerator()

        # Check that methods from parent class are available
        assert hasattr(generator, "apply_palette_to_full_image")
        assert hasattr(generator, "generate_output_filename")

        # Check that the colorizer is properly handled
        assert generator.colorizer is None

        # Test with colorizer
        colorizer = Mock(spec=PaletteColorizer)
        generator_with_colorizer = GridPreviewGenerator(colorizer)
        assert generator_with_colorizer.colorizer == colorizer

    def test_edge_case_large_grid(self):
        """Test handling large grid dimensions"""
        generator = GridPreviewGenerator()
        processor = Mock(spec=GridImageProcessor)
        manager = Mock(spec=GridArrangementManager)

        # Mock large grid
        processor.grid_cols = 100
        processor.tile_width = 8
        processor.tile_height = 8

        # Mock single tile arrangement
        manager.get_arrangement_order.return_value = [(ArrangementType.TILE, "0,0")]
        tile_image = Image.new("L", (8, 8))
        processor.get_tile.return_value = tile_image

        # Call real method - verify it handles large grids properly
        result = generator.create_grid_arranged_image(processor, manager)

        # Should produce a valid image (cap is handled internally)
        assert result is not None
        assert result.mode == "L"
        # Note: Actual size includes layout spacing, verify reasonable dimensions
        assert result.size[0] >= 8  # At least tile width
        assert result.size[1] >= 8  # At least tile height

    def test_edge_case_zero_tile_dimensions(self):
        """Test handling zero tile dimensions"""
        generator = GridPreviewGenerator()

        # Test with zero tile dimensions
        tiles = [(TilePosition(0, 0), Image.new("L", (8, 8)))]

        result = generator._create_arranged_image_with_spacing(tiles, 0, 0, 1, 0)

        # Should create image with zero dimensions
        assert result.size == (0, 0)
        assert result.mode == "L"
