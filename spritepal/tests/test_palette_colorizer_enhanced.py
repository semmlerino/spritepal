"""
Enhanced tests for PaletteColorizer
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from PIL import Image

from ui.row_arrangement.palette_colorizer import PaletteColorizer

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.performance,
    pytest.mark.slow,
]

class TestPaletteColorizerEnhanced:
    """Enhanced tests for PaletteColorizer functionality"""

    def test_initialization(self):
        """Test colorizer initialization"""
        colorizer = PaletteColorizer()

        assert colorizer.get_palettes() == {}
        assert colorizer.is_palette_mode() is False
        assert colorizer.get_selected_palette_index() == 8
        assert colorizer.has_palettes() is False

    def test_palette_management(self):
        """Test palette setting and getting"""
        colorizer = PaletteColorizer()

        # Create test palettes
        test_palettes = {
            8: [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)],
            9: [(0, 0, 0), (255, 255, 0), (255, 0, 255), (0, 255, 255)],
            10: [(0, 0, 0), (128, 128, 128), (192, 192, 192), (255, 255, 255)],
        }

        # Set palettes
        colorizer.set_palettes(test_palettes)

        # Verify palettes were set
        assert colorizer.has_palettes() is True
        palettes = colorizer.get_palettes()
        assert len(palettes) == 3
        assert 8 in palettes
        assert 9 in palettes
        assert 10 in palettes

        # Verify palette data
        assert palettes[8] == [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]
        assert palettes[9] == [(0, 0, 0), (255, 255, 0), (255, 0, 255), (0, 255, 255)]
        assert palettes[10] == [
            (0, 0, 0),
            (128, 128, 128),
            (192, 192, 192),
            (255, 255, 255),
        ]

    def test_palette_mode_toggle(self):
        """Test palette mode toggling"""
        colorizer = PaletteColorizer()

        # Mock signal emission
        colorizer.palette_mode_changed = Mock()

        # Initially disabled
        assert colorizer.is_palette_mode() is False

        # Toggle on
        result = colorizer.toggle_palette_mode()
        assert result is True
        assert colorizer.is_palette_mode() is True
        colorizer.palette_mode_changed.emit.assert_called_once_with(True)

        # Toggle off
        result = colorizer.toggle_palette_mode()
        assert result is False
        assert colorizer.is_palette_mode() is False
        colorizer.palette_mode_changed.emit.assert_called_with(False)

    def test_palette_selection(self):
        """Test palette selection"""
        colorizer = PaletteColorizer()

        # Mock signal emission
        colorizer.palette_index_changed = Mock()

        # Test setting palette index
        colorizer.set_selected_palette(10)
        assert colorizer.get_selected_palette_index() == 10
        colorizer.palette_index_changed.emit.assert_called_once_with(10)

        # Test setting same palette index (should not emit signal)
        colorizer.palette_index_changed.reset_mock()
        colorizer.set_selected_palette(10)
        colorizer.palette_index_changed.emit.assert_not_called()

        # Test setting different palette index
        colorizer.set_selected_palette(12)
        assert colorizer.get_selected_palette_index() == 12
        colorizer.palette_index_changed.emit.assert_called_once_with(12)

    def test_palette_cycling(self):
        """Test palette cycling functionality"""
        colorizer = PaletteColorizer()

        # Mock signal emission
        colorizer.palette_index_changed = Mock()

        # Test cycling with no palettes
        initial_index = colorizer.get_selected_palette_index()
        result = colorizer.cycle_palette()
        assert result == initial_index

        # Set up palettes
        test_palettes = {
            8: [(0, 0, 0), (255, 0, 0)],
            10: [(0, 0, 0), (0, 255, 0)],
            12: [(0, 0, 0), (0, 0, 255)],
        }
        colorizer.set_palettes(test_palettes)

        # Start at palette 8
        colorizer.set_selected_palette(8)
        colorizer.palette_index_changed.reset_mock()

        # Cycle to next palette
        result = colorizer.cycle_palette()
        assert result == 10
        assert colorizer.get_selected_palette_index() == 10
        colorizer.palette_index_changed.emit.assert_called_once_with(10)

        # Cycle to next palette
        result = colorizer.cycle_palette()
        assert result == 12
        assert colorizer.get_selected_palette_index() == 12

        # Cycle back to first palette
        result = colorizer.cycle_palette()
        assert result == 8
        assert colorizer.get_selected_palette_index() == 8

    def test_palette_cycling_with_invalid_current(self):
        """Test palette cycling when current palette is not available"""
        colorizer = PaletteColorizer()

        # Set up palettes
        test_palettes = {9: [(0, 0, 0), (255, 0, 0)], 11: [(0, 0, 0), (0, 255, 0)]}
        colorizer.set_palettes(test_palettes)

        # Set current palette to unavailable index
        colorizer.set_selected_palette(15)

        # Cycle should select first available palette
        result = colorizer.cycle_palette()
        assert result == 9
        assert colorizer.get_selected_palette_index() == 9

    def test_apply_palette_to_grayscale_image(self):
        """Test applying palette to grayscale image"""
        colorizer = PaletteColorizer()

        # Create test grayscale image
        test_image = Image.new("L", (4, 4))
        pixels = test_image.load()

        # Set pixel values to map to different palette indices
        pixels[0, 0] = 0  # Index 0 - should be transparent
        pixels[1, 0] = 16  # Index 1
        pixels[2, 0] = 32  # Index 2
        pixels[3, 0] = 48  # Index 3

        # Create test palette
        test_palette = [
            (0, 0, 0),  # Index 0 - transparent
            (255, 0, 0),  # Index 1 - red
            (0, 255, 0),  # Index 2 - green
            (0, 0, 255),  # Index 3 - blue
        ]

        # Apply palette
        result = colorizer.apply_palette_to_image(test_image, test_palette)

        # Verify result
        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == (4, 4)

        # Check pixel colors
        assert result.getpixel((0, 0)) == (0, 0, 0, 0)  # Transparent
        assert result.getpixel((1, 0)) == (255, 0, 0, 255)  # Red
        assert result.getpixel((2, 0)) == (0, 255, 0, 255)  # Green
        assert result.getpixel((3, 0)) == (0, 0, 255, 255)  # Blue

    def test_apply_palette_to_palette_mode_image(self):
        """Test applying palette to palette mode image"""
        colorizer = PaletteColorizer()

        # Create test palette mode image
        test_image = Image.new("P", (4, 4))
        pixels = test_image.load()

        # Set pixel values directly as palette indices
        pixels[0, 0] = 0  # Index 0 - transparent
        pixels[1, 0] = 1  # Index 1
        pixels[2, 0] = 2  # Index 2
        pixels[3, 0] = 3  # Index 3

        # Create test palette
        test_palette = [
            (0, 0, 0),  # Index 0 - transparent
            (255, 128, 0),  # Index 1 - orange
            (128, 0, 255),  # Index 2 - purple
            (0, 255, 255),  # Index 3 - cyan
        ]

        # Apply palette
        result = colorizer.apply_palette_to_image(test_image, test_palette)

        # Verify result
        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == (4, 4)

        # Check pixel colors
        assert result.getpixel((0, 0)) == (0, 0, 0, 0)  # Transparent
        assert result.getpixel((1, 0)) == (255, 128, 0, 255)  # Orange
        assert result.getpixel((2, 0)) == (128, 0, 255, 255)  # Purple
        assert result.getpixel((3, 0)) == (0, 255, 255, 255)  # Cyan

    def test_apply_palette_error_handling(self):
        """Test error handling in palette application"""
        colorizer = PaletteColorizer()

        # Test with None image
        result = colorizer.apply_palette_to_image(None, [(255, 0, 0)])
        assert result is None

        # Test with empty palette
        test_image = Image.new("L", (2, 2))
        result = colorizer.apply_palette_to_image(test_image, [])
        assert result is None

        # Test with None palette
        result = colorizer.apply_palette_to_image(test_image, None)
        assert result is None

    def test_apply_palette_out_of_range_indices(self):
        """Test applying palette with out of range indices"""
        colorizer = PaletteColorizer()

        # Create test image with high pixel values
        test_image = Image.new("L", (2, 2))
        pixels = test_image.load()
        pixels[0, 0] = 255  # High value - should map to index 15
        pixels[1, 0] = 200  # Should map to index 12

        # Create small palette
        test_palette = [
            (0, 0, 0),  # Index 0
            (255, 0, 0),  # Index 1
            (0, 255, 0),  # Index 2
        ]

        # Apply palette
        result = colorizer.apply_palette_to_image(test_image, test_palette)

        # Verify result
        assert result is not None

        # Out of range indices should be black
        assert result.getpixel((0, 0)) == (0, 0, 0, 255)  # Index 15 -> black
        assert result.getpixel((1, 0)) == (0, 0, 0, 255)  # Index 12 -> black

    def test_get_display_image_grayscale_mode(self):
        """Test getting display image in grayscale mode"""
        colorizer = PaletteColorizer()

        # Create test image
        test_image = Image.new("L", (4, 4))

        # Set up palettes
        test_palettes = {8: [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]}
        colorizer.set_palettes(test_palettes)

        # Ensure palette mode is off
        assert colorizer.is_palette_mode() is False

        # Get display image
        result = colorizer.get_display_image(0, test_image)

        # Should return original grayscale image
        assert result is test_image

    def test_get_display_image_palette_mode(self):
        """Test getting display image in palette mode"""
        colorizer = PaletteColorizer()

        # Create test image
        test_image = Image.new("L", (4, 4))
        pixels = test_image.load()
        pixels[0, 0] = 16  # Index 1

        # Set up palettes
        test_palettes = {8: [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]}
        colorizer.set_palettes(test_palettes)

        # Enable palette mode
        colorizer.toggle_palette_mode()
        colorizer.set_selected_palette(8)

        # Get display image
        result = colorizer.get_display_image(0, test_image)

        # Should return colorized image
        assert result is not test_image
        assert result.mode == "RGBA"
        assert result.getpixel((0, 0)) == (255, 0, 0, 255)  # Red

    def test_get_display_image_caching(self):
        """Test display image caching functionality"""
        colorizer = PaletteColorizer()

        # Create test image
        test_image = Image.new("L", (4, 4))
        pixels = test_image.load()
        pixels[0, 0] = 16  # Index 1

        # Set up palettes
        test_palettes = {8: [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]}
        colorizer.set_palettes(test_palettes)

        # Enable palette mode
        colorizer.toggle_palette_mode()
        colorizer.set_selected_palette(8)

        # Get display image first time
        result1 = colorizer.get_display_image(0, test_image)

        # Get display image second time (should be cached)
        result2 = colorizer.get_display_image(0, test_image)

        # Should return the same cached image
        assert result1 is result2

    def test_get_display_image_cache_invalidation(self):
        """Test cache invalidation when palette changes"""
        colorizer = PaletteColorizer()

        # Create test image
        test_image = Image.new("L", (4, 4))
        pixels = test_image.load()
        pixels[0, 0] = 16  # Index 1

        # Set up palettes
        test_palettes = {
            8: [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)],
            9: [(0, 0, 0), (0, 255, 0), (255, 0, 0), (0, 0, 255)],
        }
        colorizer.set_palettes(test_palettes)

        # Enable palette mode
        colorizer.toggle_palette_mode()
        colorizer.set_selected_palette(8)

        # Get display image with palette 8
        result1 = colorizer.get_display_image(0, test_image)
        assert result1.getpixel((0, 0)) == (255, 0, 0, 255)  # Red

        # Change palette
        colorizer.set_selected_palette(9)

        # Get display image with palette 9
        result2 = colorizer.get_display_image(0, test_image)
        assert result2.getpixel((0, 0)) == (0, 255, 0, 255)  # Green

        # Should be different images
        assert result1 is not result2

    def test_get_display_image_fallback(self):
        """Test fallback to grayscale when palette application fails"""
        colorizer = PaletteColorizer()

        # Create test image
        test_image = Image.new("L", (4, 4))

        # Set up palettes
        test_palettes = {8: [(0, 0, 0), (255, 0, 0)]}
        colorizer.set_palettes(test_palettes)

        # Enable palette mode with non-existent palette
        colorizer.toggle_palette_mode()
        colorizer.set_selected_palette(15)  # Not in palettes

        # Get display image
        result = colorizer.get_display_image(0, test_image)

        # Should fall back to grayscale
        assert result is test_image

    def test_cache_management(self):
        """Test cache management functionality"""
        colorizer = PaletteColorizer()

        # Test cache clearing
        colorizer.clear_cache()
        assert len(colorizer._colorized_cache) == 0

        # Create test setup
        test_image = Image.new("L", (4, 4))
        test_palettes = {8: [(0, 0, 0), (255, 0, 0)]}
        colorizer.set_palettes(test_palettes)
        colorizer.toggle_palette_mode()

        # Cache some images
        colorizer.get_display_image(0, test_image)
        colorizer.get_display_image(1, test_image)
        assert len(colorizer._colorized_cache) == 2

        # Clear cache
        colorizer.clear_cache()
        assert len(colorizer._colorized_cache) == 0

    def test_cache_limit_enforcement(self):
        """Test cache limit enforcement"""
        colorizer = PaletteColorizer()

        # Set a small cache limit for testing
        colorizer._max_cache_size = 3

        # Create test setup
        test_image = Image.new("L", (4, 4))
        test_palettes = {8: [(0, 0, 0), (255, 0, 0)]}
        colorizer.set_palettes(test_palettes)
        colorizer.toggle_palette_mode()

        # Cache more images than the limit
        for i in range(5):
            colorizer.get_display_image(i, test_image)

        # Cache should be limited
        assert len(colorizer._colorized_cache) <= 3

    def test_cache_invalidation_on_palette_change(self):
        """Test cache invalidation when palettes change"""
        colorizer = PaletteColorizer()

        # Create test setup
        test_image = Image.new("L", (4, 4))
        test_palettes = {8: [(0, 0, 0), (255, 0, 0)]}
        colorizer.set_palettes(test_palettes)
        colorizer.toggle_palette_mode()

        # Cache some images
        colorizer.get_display_image(0, test_image)
        colorizer.get_display_image(1, test_image)
        assert len(colorizer._colorized_cache) == 2

        # Change palettes
        new_palettes = {9: [(0, 0, 0), (0, 255, 0)]}
        colorizer.set_palettes(new_palettes)

        # Cache should be cleared
        assert len(colorizer._colorized_cache) == 0

    def test_cache_invalidation_on_mode_toggle(self):
        """Test cache invalidation when mode toggles"""
        colorizer = PaletteColorizer()

        # Create test setup
        test_image = Image.new("L", (4, 4))
        test_palettes = {8: [(0, 0, 0), (255, 0, 0)]}
        colorizer.set_palettes(test_palettes)
        colorizer.toggle_palette_mode()

        # Cache some images
        colorizer.get_display_image(0, test_image)
        assert len(colorizer._colorized_cache) == 1

        # Toggle mode
        colorizer.toggle_palette_mode()

        # Cache should be cleared
        assert len(colorizer._colorized_cache) == 0

    def test_signal_emissions(self):
        """Test that signals are emitted correctly"""
        colorizer = PaletteColorizer()

        # Mock signals
        colorizer.palette_mode_changed = Mock()
        colorizer.palette_index_changed = Mock()

        # Test palette mode change signal
        colorizer.toggle_palette_mode()
        colorizer.palette_mode_changed.emit.assert_called_once_with(True)

        # Test palette index change signal
        colorizer.set_selected_palette(10)
        colorizer.palette_index_changed.emit.assert_called_once_with(10)

        # Test cycling signal
        test_palettes = {8: [(0, 0, 0), (255, 0, 0)], 9: [(0, 0, 0), (0, 255, 0)]}
        colorizer.set_palettes(test_palettes)
        colorizer.set_selected_palette(8)
        colorizer.palette_index_changed.reset_mock()

        colorizer.cycle_palette()
        colorizer.palette_index_changed.emit.assert_called_once_with(9)

    def test_comprehensive_workflow(self):
        """Test comprehensive colorizer workflow"""
        colorizer = PaletteColorizer()

        # Create test image with pattern
        test_image = Image.new("L", (8, 8))
        pixels = test_image.load()
        for y in range(8):
            for x in range(8):
                # Create a pattern that maps to different palette indices
                pixels[x, y] = (x + y) * 8

        # Set up multiple palettes
        test_palettes = {
            8: [
                (0, 0, 0),
                (255, 0, 0),
                (0, 255, 0),
                (0, 0, 255),
                (255, 255, 0),
                (255, 0, 255),
                (0, 255, 255),
                (255, 255, 255),
            ],
            9: [
                (0, 0, 0),
                (128, 0, 0),
                (0, 128, 0),
                (0, 0, 128),
                (128, 128, 0),
                (128, 0, 128),
                (0, 128, 128),
                (128, 128, 128),
            ],
            10: [
                (0, 0, 0),
                (64, 64, 64),
                (128, 128, 128),
                (192, 192, 192),
                (255, 255, 255),
                (255, 128, 128),
                (128, 255, 128),
                (128, 128, 255),
            ],
        }
        colorizer.set_palettes(test_palettes)

        # Test initial state
        assert colorizer.has_palettes() is True
        assert colorizer.is_palette_mode() is False
        assert colorizer.get_selected_palette_index() == 8

        # Enable palette mode
        colorizer.toggle_palette_mode()
        assert colorizer.is_palette_mode() is True

        # Test with different palettes
        for palette_idx in [8, 9, 10]:
            colorizer.set_selected_palette(palette_idx)

            # Get colorized image
            colorized = colorizer.get_display_image(0, test_image)

            # Verify colorization
            assert colorized is not test_image
            assert colorized.mode == "RGBA"
            assert colorized.size == test_image.size

            # Verify caching
            cached = colorizer.get_display_image(0, test_image)
            assert cached is colorized

        # Test cycling through palettes
        colorizer.set_selected_palette(8)
        assert colorizer.cycle_palette() == 9
        assert colorizer.cycle_palette() == 10
        assert colorizer.cycle_palette() == 8  # Back to start

        # Test cache clearing
        colorizer.clear_cache()
        new_colorized = colorizer.get_display_image(0, test_image)
        assert new_colorized is not colorized  # Should be new image

        # Disable palette mode
        colorizer.toggle_palette_mode()
        grayscale = colorizer.get_display_image(0, test_image)
        assert grayscale is test_image

    def test_edge_cases(self):
        """Test edge cases and boundary conditions"""
        colorizer = PaletteColorizer()

        # Test with empty image
        empty_image = Image.new("L", (0, 0))
        test_palette = [(0, 0, 0), (255, 255, 255)]
        result = colorizer.apply_palette_to_image(empty_image, test_palette)
        assert result is not None
        assert result.size == (0, 0)

        # Test with single pixel image
        single_pixel = Image.new("L", (1, 1))
        single_pixel.putpixel((0, 0), 16)  # Index 1
        result = colorizer.apply_palette_to_image(single_pixel, test_palette)
        assert result is not None
        assert result.size == (1, 1)
        assert result.getpixel((0, 0)) == (255, 255, 255, 255)

        # Test with large image
        large_image = Image.new("L", (100, 100))
        result = colorizer.apply_palette_to_image(large_image, test_palette)
        assert result is not None
        assert result.size == (100, 100)

        # Test with single color palette
        single_color_palette = [(255, 0, 0)]
        result = colorizer.apply_palette_to_image(single_pixel, single_color_palette)
        assert result is not None

    def test_performance_characteristics(self):
        """Test performance characteristics"""
        colorizer = PaletteColorizer()

        # Create moderately sized image
        test_image = Image.new("L", (64, 64))
        test_palette = [(i * 16, i * 16, i * 16) for i in range(16)]

        import time

        # Test palette application performance
        start_time = time.time()
        result = colorizer.apply_palette_to_image(test_image, test_palette)
        end_time = time.time()

        # Should complete reasonably quickly
        assert end_time - start_time < 1.0
        assert result is not None

        # Test caching performance
        colorizer.set_palettes({8: test_palette})
        colorizer.toggle_palette_mode()

        # First call (should cache)
        start_time = time.time()
        result1 = colorizer.get_display_image(0, test_image)
        first_call_time = time.time() - start_time

        # Second call (should use cache)
        start_time = time.time()
        result2 = colorizer.get_display_image(0, test_image)
        second_call_time = time.time() - start_time

        # Cache should be faster
        assert second_call_time < first_call_time
        assert result1 is result2
