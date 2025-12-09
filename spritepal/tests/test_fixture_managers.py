"""
Test the test fixture managers

from ui.row_arrangement.grid_arrangement_manager import TilePosition

from ui.row_arrangement.grid_arrangement_manager import TilePosition

from ui.row_arrangement.grid_arrangement_manager import TilePosition

from ui.row_arrangement.grid_arrangement_manager import TilePosition

Verify that the test fixture managers work correctly and provide
real implementations instead of mocks.
"""

import pytest

from tests.fixtures.test_managers import (
    # Systematic pytest markers applied based on test content analysis
    create_colorizer_fixture,
    create_grid_arrangement_fixture,
    create_grid_processor_fixture,
    create_preview_generator_fixture,
)

pytestmark = [
    pytest.mark.headless,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.unit,
    pytest.mark.ci_safe,
    pytest.mark.integration,
]
class TestFixtureManagers:
    """Test the test fixture managers functionality"""

    def test_grid_arrangement_fixture(self):
        """Test that GridArrangementManagerFixture works correctly"""
        fixture = create_grid_arrangement_fixture(rows=4, cols=4)
        manager = fixture.get_manager()

        # Verify the manager is real and has test data
        assert manager.total_rows == 4
        assert manager.total_cols == 4
        assert manager.get_arranged_count() > 0  # Should have test arrangements

        # Verify it has actual arrangements (not mocked)
        arrangements = manager.get_arrangement_order()
        assert len(arrangements) > 0

        # Test that we can add more arrangements
        from ui.row_arrangement.grid_arrangement_manager import TilePosition
        initial_count = manager.get_arranged_count()
        manager.add_tile(TilePosition(3, 3))
        assert manager.get_arranged_count() > initial_count

    def test_grid_processor_fixture(self):
        """Test that GridImageProcessorFixture works correctly"""
        fixture = create_grid_processor_fixture()
        processor = fixture.get_processor()

        # Verify the processor is real and has processed data
        assert processor.grid_rows > 0
        assert processor.grid_cols > 0
        assert processor.tile_width > 0
        assert processor.tile_height > 0

        # Verify it has actual tiles data
        original_image, tiles = fixture.get_test_data()
        assert original_image is not None
        assert len(tiles) > 0

        # Cleanup
        fixture.cleanup()

    def test_colorizer_fixture(self):
        """Test that PaletteColorizerFixture works correctly"""
        fixture = create_colorizer_fixture()
        colorizer = fixture.get_colorizer()

        # Verify the colorizer has real palettes
        palettes = fixture.get_test_palettes()
        assert len(palettes) > 0

        # Verify palettes are in expected range (8-15)
        for pal_idx in palettes:
            assert 8 <= pal_idx <= 15

        # Verify each palette has 16 colors
        for palette in palettes.values():
            assert len(palette) == 16
            # Verify colors are RGB tuples
            for color in palette:
                assert len(color) == 3
                assert all(0 <= c <= 255 for c in color)

        # Test colorizer functionality
        assert colorizer.is_palette_mode() is False  # Should start in grayscale mode
        enabled = colorizer.toggle_palette_mode()
        assert enabled is True
        assert colorizer.is_palette_mode() is True

    def test_preview_generator_fixture(self):
        """Test that PreviewGeneratorFixture works correctly"""
        fixture = create_preview_generator_fixture()

        # Verify we get real generators
        preview_gen = fixture.get_preview_generator()
        grid_preview_gen = fixture.get_grid_preview_generator()
        colorizer = fixture.get_colorizer()

        assert preview_gen is not None
        assert grid_preview_gen is not None
        assert colorizer is not None

        # Verify the generators have colorizers
        assert preview_gen.colorizer == colorizer
        assert grid_preview_gen.colorizer == colorizer

        # Verify colorizer has test palettes
        palettes = colorizer.get_palettes()
        assert len(palettes) > 0

    def test_fixture_integration(self):
        """Test that fixtures work together correctly"""
        # Create multiple fixtures
        grid_fixture = create_grid_arrangement_fixture()
        processor_fixture = create_grid_processor_fixture()
        colorizer_fixture = create_colorizer_fixture()

        # Get the real objects
        manager = grid_fixture.get_manager()
        processor = processor_fixture.get_processor()
        colorizer_fixture.get_colorizer()

        # Verify they can work together (basic compatibility)
        assert manager.total_rows > 0
        assert processor.grid_rows > 0

        # They don't have to match exactly, but should be reasonable
        assert manager.total_rows <= 16  # Reasonable limit
        assert processor.grid_rows <= 16  # Reasonable limit

        # Cleanup
        processor_fixture.cleanup()

    def test_fixtures_are_independent(self):
        """Test that fixtures are independent and don't share state"""
        # Create two separate fixtures
        fixture1 = create_grid_arrangement_fixture(rows=4, cols=4)
        fixture2 = create_grid_arrangement_fixture(rows=6, cols=6)

        manager1 = fixture1.get_manager()
        manager2 = fixture2.get_manager()

        # Verify they have different configurations
        assert manager1.total_rows == 4
        assert manager2.total_rows == 6

        # Modify one and verify the other is unaffected
        from ui.row_arrangement.grid_arrangement_manager import TilePosition
        initial_count1 = manager1.get_arranged_count()
        initial_count2 = manager2.get_arranged_count()

        manager1.add_tile(TilePosition(3, 3))  # Use corner tile that's likely not arranged

        assert manager1.get_arranged_count() > initial_count1
        assert manager2.get_arranged_count() == initial_count2  # Unchanged
