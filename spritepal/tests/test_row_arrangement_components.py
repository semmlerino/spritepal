"""
Tests for row arrangement refactored components
"""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from PIL import Image

from ui.row_arrangement import (
    # Systematic pytest markers applied based on test content analysis
    ArrangementManager,
    PaletteColorizer,
    PreviewGenerator,
    RowImageProcessor,
)

pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.cache,
    pytest.mark.ci_safe,
    pytest.mark.signals_slots,
]
class TestRowImageProcessor:
    """Test the RowImageProcessor component"""

    def test_init(self):
        """Test processor initialization"""
        processor = RowImageProcessor()
        assert processor.tile_width == 0
        assert processor.tile_height == 0

    def test_calculate_tile_dimensions(self):
        """Test tile dimension calculation"""
        processor = RowImageProcessor()

        # Create a test image
        test_image = Image.new("L", (128, 64))

        # Calculate dimensions for 16 tiles per row
        width, height = processor.calculate_tile_dimensions(test_image, 16)

        assert width == 8  # 128 / 16
        assert height == 8  # Square tiles
        assert processor.tile_width == 8
        assert processor.tile_height == 8

    def test_extract_rows(self):
        """Test row extraction from sprite sheet"""
        processor = RowImageProcessor()

        # Create test image with 2 rows of 8x8 tiles
        test_image = Image.new("L", (128, 16))  # 16 tiles wide, 2 rows

        # Extract rows
        rows = processor.extract_rows(test_image, 16)

        assert len(rows) == 2
        assert rows[0]["index"] == 0
        assert rows[0]["tiles"] == 16
        assert rows[0]["image"].size == (128, 8)
        assert rows[1]["index"] == 1
        assert rows[1]["tiles"] == 16
        assert rows[1]["image"].size == (128, 8)

    def test_load_sprite_palette_mode(self, tmp_path):
        """Test loading sprite in palette mode with real image"""
        processor = RowImageProcessor()

        # Create real palette mode image file
        sprite_file = tmp_path / "test_sprite.png"
        img = Image.new("P", (16, 16))
        # Set a simple palette
        palette = []
        for i in range(256):
            palette.extend([i, i, i])  # Grayscale palette
        img.putpalette(palette)
        img.save(sprite_file)

        result = processor.load_sprite(str(sprite_file))

        # Verify real conversion occurred
        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.mode == "L"  # Should be converted to grayscale

    def test_process_sprite_sheet(self, tmp_path):
        """Test complete sprite processing pipeline with real image"""
        processor = RowImageProcessor()

        # Create real test image (128x16 pixels for 2 rows of 16 tiles each)
        sprite_file = tmp_path / "test_sprite.png"
        img = Image.new("L", (128, 16))
        # Create a pattern to verify processing
        pixels = []
        for y in range(16):
            for x in range(128):
                pixels.append((x + y) % 256)
        img.putdata(pixels)
        img.save(sprite_file)

        image, rows = processor.process_sprite_sheet(str(sprite_file), 16)

        # Verify real processing occurred
        assert image is not None
        assert isinstance(image, Image.Image)
        assert image.size == (128, 16)
        assert len(rows) == 2
        assert processor.tile_width == 8
        assert processor.tile_height == 8

        # Verify row data
        for row in rows:
            assert "image" in row
            assert "tiles" in row
            assert "index" in row
            assert isinstance(row["image"], Image.Image)

class TestArrangementManager:
    """Test the ArrangementManager component"""

    def test_init(self):
        """Test manager initialization"""
        manager = ArrangementManager()
        assert manager.get_arranged_indices() == []
        assert manager.get_arranged_count() == 0

    def test_add_row(self):
        """Test adding rows to arrangement"""
        manager = ArrangementManager()

        # Test signal emission
        manager.arrangement_changed = Mock()
        manager.row_added = Mock()

        # Add new row
        assert manager.add_row(5) is True
        assert manager.get_arranged_indices() == [5]
        manager.row_added.emit.assert_called_once_with(5)
        manager.arrangement_changed.emit.assert_called_once()

        # Try to add duplicate
        manager.arrangement_changed.reset_mock()
        manager.row_added.reset_mock()
        assert manager.add_row(5) is False
        manager.row_added.emit.assert_not_called()
        manager.arrangement_changed.emit.assert_not_called()

    def test_remove_row(self):
        """Test removing rows from arrangement"""
        manager = ArrangementManager()
        manager.add_row(3)
        manager.add_row(7)

        # Test signal emission
        manager.arrangement_changed = Mock()
        manager.row_removed = Mock()

        # Remove existing row
        assert manager.remove_row(3) is True
        assert manager.get_arranged_indices() == [7]
        manager.row_removed.emit.assert_called_once_with(3)
        manager.arrangement_changed.emit.assert_called_once()

        # Try to remove non-existent row
        manager.arrangement_changed.reset_mock()
        manager.row_removed.reset_mock()
        assert manager.remove_row(3) is False
        manager.row_removed.emit.assert_not_called()
        manager.arrangement_changed.emit.assert_not_called()

    def test_add_multiple_rows(self):
        """Test adding multiple rows at once"""
        manager = ArrangementManager()
        manager.arrangement_changed = Mock()

        count = manager.add_multiple_rows([1, 2, 3, 2, 4])  # Note duplicate

        assert count == 4  # Only 4 unique rows added
        assert sorted(manager.get_arranged_indices()) == [1, 2, 3, 4]
        manager.arrangement_changed.emit.assert_called_once()

    def test_reorder_rows(self):
        """Test reordering rows"""
        manager = ArrangementManager()
        manager.add_multiple_rows([1, 2, 3])

        manager.arrangement_changed = Mock()
        manager.reorder_rows([3, 1, 2])

        assert manager.get_arranged_indices() == [3, 1, 2]
        manager.arrangement_changed.emit.assert_called_once()

    def test_clear(self):
        """Test clearing arrangement"""
        manager = ArrangementManager()
        manager.add_multiple_rows([1, 2, 3])

        manager.arrangement_cleared = Mock()
        manager.arrangement_changed = Mock()

        manager.clear()

        assert manager.get_arranged_indices() == []
        manager.arrangement_cleared.emit.assert_called_once()
        manager.arrangement_changed.emit.assert_called_once()

class TestPaletteColorizer:
    """Test the PaletteColorizer component"""

    def test_init(self):
        """Test colorizer initialization"""
        colorizer = PaletteColorizer()
        assert colorizer.is_palette_mode() is False
        assert colorizer.get_selected_palette_index() == 8
        assert colorizer.has_palettes() is False

    def test_set_palettes(self):
        """Test setting palettes"""
        colorizer = PaletteColorizer()

        test_palettes = {
            8: [(255, 0, 0), (0, 255, 0), (0, 0, 255)],
            9: [(255, 255, 0), (255, 0, 255), (0, 255, 255)],
        }

        colorizer.set_palettes(test_palettes)
        assert colorizer.has_palettes() is True

    def test_toggle_palette_mode(self):
        """Test toggling palette mode"""
        colorizer = PaletteColorizer()
        colorizer.palette_mode_changed = Mock()

        # Toggle on
        assert colorizer.toggle_palette_mode() is True
        assert colorizer.is_palette_mode() is True
        colorizer.palette_mode_changed.emit.assert_called_with(True)

        # Toggle off
        assert colorizer.toggle_palette_mode() is False
        assert colorizer.is_palette_mode() is False
        colorizer.palette_mode_changed.emit.assert_called_with(False)

    def test_cycle_palette(self):
        """Test cycling through palettes"""
        colorizer = PaletteColorizer()
        colorizer.palette_index_changed = Mock()

        # Set palettes
        colorizer.set_palettes({8: [], 10: [], 12: []})

        # Start at 8, cycle to 10
        assert colorizer.cycle_palette() == 10
        colorizer.palette_index_changed.emit.assert_called_with(10)

        # Cycle to 12
        assert colorizer.cycle_palette() == 12

        # Cycle back to 8
        assert colorizer.cycle_palette() == 8

    def test_apply_palette_to_image(self):
        """Test applying palette to grayscale image"""
        colorizer = PaletteColorizer()

        # Create test grayscale image
        grayscale = Image.new("L", (2, 2))
        pixels = grayscale.load()
        pixels[0, 0] = 0  # Transparent
        pixels[1, 0] = 16  # Color index 1
        pixels[0, 1] = 32  # Color index 2
        pixels[1, 1] = 240  # Color index 15

        # Test palette
        palette = [(0, 0, 0)] + [(i * 16, i * 16, i * 16) for i in range(1, 16)]

        result = colorizer.apply_palette_to_image(grayscale, palette)

        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == (2, 2)

        # Check transparency
        assert result.getpixel((0, 0))[3] == 0  # Alpha = 0

        # Check colors
        assert result.getpixel((1, 0))[:3] == (16, 16, 16)  # RGB from palette[1]
        assert result.getpixel((0, 1))[:3] == (32, 32, 32)  # RGB from palette[2]

    def test_get_display_image_caching(self):
        """Test that display images are cached"""
        colorizer = PaletteColorizer()
        colorizer.set_palettes({8: [(255, 0, 0)] * 16})
        colorizer.toggle_palette_mode()

        # Create test image
        test_image = Image.new("L", (8, 8))

        # First call should create and cache
        result1 = colorizer.get_display_image(0, test_image)
        assert result1 is not None

        # Second call should return cached version
        with patch.object(colorizer, "apply_palette_to_image") as mock_apply:
            result2 = colorizer.get_display_image(0, test_image)
            mock_apply.assert_not_called()  # Should use cache
            assert result2 is result1  # Same object

class TestPreviewGenerator:
    """Test the PreviewGenerator component"""

    def test_init_without_colorizer(self):
        """Test generator initialization without colorizer"""
        generator = PreviewGenerator()
        assert generator.colorizer is None

    def test_init_with_colorizer(self):
        """Test generator initialization with colorizer"""
        colorizer = Mock()
        generator = PreviewGenerator(colorizer)
        assert generator.colorizer is colorizer

    def test_create_arranged_image_empty(self):
        """Test creating arranged image with no rows"""
        generator = PreviewGenerator()

        original = Image.new("L", (128, 64))
        tile_rows = []
        arranged_indices = []

        result = generator.create_arranged_image(
            original, tile_rows, arranged_indices, 8
        )

        assert result is None

    def test_create_arranged_image_single_row(self):
        """Test creating arranged image with single row"""
        generator = PreviewGenerator()

        original = Image.new("L", (128, 64))
        row_image = Image.new("L", (128, 8))
        tile_rows = [{"index": 0, "image": row_image, "tiles": 16}]
        arranged_indices = [0]

        result = generator.create_arranged_image(
            original, tile_rows, arranged_indices, 8
        )

        assert result is not None
        assert result.size == (128, 8)  # Single row height

    def test_create_arranged_image_multiple_rows(self):
        """Test creating arranged image with multiple rows"""
        generator = PreviewGenerator()

        original = Image.new("L", (128, 64))
        tile_rows = [
            {"index": i, "image": Image.new("L", (128, 8)), "tiles": 16}
            for i in range(4)
        ]
        arranged_indices = [0, 2, 1]  # Different order

        result = generator.create_arranged_image(
            original, tile_rows, arranged_indices, 8, row_spacing_ratio=0.75
        )

        assert result is not None
        # Height = 2 * spacing + last row = 2 * 6 + 8 = 20
        assert result.size == (128, 20)

    def test_create_arranged_image_with_colorizer(self):
        """Test creating arranged image with palette applied"""
        colorizer = Mock()
        colorizer.is_palette_mode.return_value = True
        colorizer.get_display_image.return_value = Image.new("RGBA", (128, 8))

        generator = PreviewGenerator(colorizer)

        original = Image.new("L", (128, 64))
        tile_rows = [{"index": 0, "image": Image.new("L", (128, 8)), "tiles": 16}]
        arranged_indices = [0]

        result = generator.create_arranged_image(
            original, tile_rows, arranged_indices, 8
        )

        assert result is not None
        assert result.mode == "RGBA"  # Colorized output
        colorizer.get_display_image.assert_called_once()

    def test_export_arranged_image(self):
        """Test exporting arranged image"""
        generator = PreviewGenerator()

        test_image = Image.new("L", (128, 16))

        with patch.object(test_image, "save") as mock_save:
            output_path = generator.export_arranged_image(
                "/path/to/sprite.png", test_image, 2
            )

            assert output_path == "sprite_arranged.png"
            mock_save.assert_called_once_with("sprite_arranged.png")

    def test_generate_output_filename(self):
        """Test output filename generation"""
        generator = PreviewGenerator()

        assert (
            generator.generate_output_filename("/path/to/sprite.png")
            == "sprite_arranged.png"
        )

        assert (
            generator.generate_output_filename("sprite.png", "_modified")
            == "sprite_modified.png"
        )
