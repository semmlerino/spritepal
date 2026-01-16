"""
Test constants validation and usage.

Validates that constants are properly defined and used consistently.
Note: Address translation tests are in test_address_translation.py.
"""

from __future__ import annotations

import pytest

from ui.common import spacing_constants
from utils import constants

pytestmark = [pytest.mark.headless, pytest.mark.no_manager_setup]


class TestConstantsValidation:
    """Test constants definition and validation."""

    def test_sprite_format_constants_consistency(self):
        """Test sprite format constants are mathematically consistent."""
        assert constants.BYTES_PER_TILE == 32
        assert constants.TILE_WIDTH == 8
        assert constants.TILE_HEIGHT == 8
        assert constants.DEFAULT_TILES_PER_ROW == 16

        # Tile format math validation
        pixels_per_tile = constants.TILE_WIDTH * constants.TILE_HEIGHT  # 64 pixels
        bits_per_pixel = 4  # 4bpp format
        bytes_per_tile_calculated = (pixels_per_tile * bits_per_pixel) // 8
        assert bytes_per_tile_calculated == constants.BYTES_PER_TILE

    def test_palette_info_completeness(self):
        """Test that palette info covers all sprite palettes."""
        palette_info = constants.PALETTE_INFO

        for palette_idx in range(constants.SPRITE_PALETTE_START, constants.SPRITE_PALETTE_END):
            assert palette_idx in palette_info, f"Missing palette info for index {palette_idx}"
            name, description = palette_info[palette_idx]
            assert isinstance(name, str) and len(name) > 0
            assert isinstance(description, str) and len(description) > 0

    def test_sprite_analysis_constants_ranges(self):
        """Test sprite analysis constants have valid ranges."""
        assert constants.MIN_SPRITE_TILES < constants.TYPICAL_SPRITE_MIN
        assert constants.TYPICAL_SPRITE_MIN < constants.TYPICAL_SPRITE_MAX
        assert constants.TYPICAL_SPRITE_MAX < constants.LARGE_SPRITE_MAX

        assert 0.0 <= constants.SPRITE_QUALITY_THRESHOLD <= 1.0
        assert 0.0 <= constants.SPRITE_QUALITY_BONUS <= 1.0
        assert constants.SPRITE_QUALITY_THRESHOLD + constants.SPRITE_QUALITY_BONUS <= 1.0

    def test_progress_reporting_constants_reasonable(self):
        """Test that progress reporting intervals are reasonable."""
        assert constants.PROGRESS_LOG_INTERVAL > 0
        assert constants.PROGRESS_SAVE_INTERVAL > 0
        assert constants.PROGRESS_DISPLAY_INTERVAL > 0
        assert constants.PROGRESS_SAVE_INTERVAL <= constants.PROGRESS_DISPLAY_INTERVAL

    def test_hal_compression_limits(self):
        """Test HAL compression limits are consistent."""
        assert constants.DATA_SIZE == 65536  # 64KB
        assert constants.DATA_SIZE == constants.BUFFER_SIZE_64KB
        assert constants.BUFFER_SIZE_64KB > constants.VRAM_SPRITE_SIZE


class TestSpacingConstantsValidation:
    """Test UI spacing constants validation."""

    def test_base_unit_grid_system(self):
        """Test that spacing follows 8px grid system."""
        assert spacing_constants.BASE_UNIT == 8

        spacing_values = [
            spacing_constants.SPACING_TINY,
            spacing_constants.SPACING_SMALL,
            spacing_constants.SPACING_MEDIUM,
            spacing_constants.SPACING_LARGE,
            spacing_constants.SPACING_XLARGE,
        ]

        for spacing in spacing_values:
            assert spacing % spacing_constants.BASE_UNIT == 0 or spacing == spacing_constants.BASE_UNIT // 2

    def test_widget_size_consistency(self):
        """Test widget size constants are consistent and reasonable."""
        assert 20 <= spacing_constants.BUTTON_HEIGHT <= 60
        assert 20 <= spacing_constants.COMPACT_BUTTON_HEIGHT <= 50
        assert 20 <= spacing_constants.INPUT_HEIGHT <= 50
        assert spacing_constants.COMPACT_BUTTON_HEIGHT <= spacing_constants.BUTTON_HEIGHT

        assert spacing_constants.COMPACT_WIDTH < spacing_constants.MEDIUM_WIDTH
        assert spacing_constants.MEDIUM_WIDTH < spacing_constants.WIDE_WIDTH

    def test_animation_constants_reasonable_values(self):
        """Test animation timing constants are reasonable."""
        assert 50 <= spacing_constants.COLLAPSIBLE_ANIMATION_DURATION <= 500
        assert spacing_constants.COLLAPSIBLE_EASING in ["ease", "ease-in", "ease-out", "ease-in-out", "linear"]

    def test_preview_widget_constants(self):
        """Test preview widget constants are reasonable."""
        assert 16 <= spacing_constants.PALETTE_PREVIEW_SIZE <= 64
        assert 128 <= spacing_constants.PREVIEW_MIN_SIZE <= 512
        assert 5.0 <= spacing_constants.MAX_ZOOM <= 50.0

        max_magnified_size = spacing_constants.PREVIEW_MIN_SIZE * spacing_constants.MAX_ZOOM
        assert max_magnified_size >= 2560


class TestConstantUsageValidation:
    """Test that constants are being used correctly in the codebase."""

    def test_palette_constants_usage(self):
        """Test palette-related constants are properly defined for usage."""
        assert hasattr(constants, "SPRITE_PALETTE_START")
        assert hasattr(constants, "SPRITE_PALETTE_END")
        assert hasattr(constants, "COLORS_PER_PALETTE")

        palette_range = list(range(constants.SPRITE_PALETTE_START, constants.SPRITE_PALETTE_END))
        assert len(palette_range) == 8  # Palettes 8-15
        assert all(0 <= p <= 15 for p in palette_range)

    def test_buffer_size_constants_usage(self):
        """Test buffer size constants are suitable for memory operations."""
        assert constants.BUFFER_SIZE_64KB >= constants.DATA_SIZE
        assert constants.BUFFER_SIZE_16KB >= constants.VRAM_SPRITE_SIZE

        chunk_count = constants.BUFFER_SIZE_64KB // constants.BUFFER_SIZE_1KB
        assert chunk_count == 64

    def test_settings_key_constants_usage(self):
        """Test settings key constants are properly formatted for QSettings."""
        settings_keys = [
            constants.SETTINGS_KEY_VRAM_PATH,
            constants.SETTINGS_KEY_CGRAM_PATH,
            constants.SETTINGS_KEY_OAM_PATH,
            constants.SETTINGS_KEY_OUTPUT_BASE,
            constants.SETTINGS_KEY_GEOMETRY,
            constants.SETTINGS_KEY_STATE,
        ]

        for key in settings_keys:
            assert isinstance(key, str)
            assert len(key) > 0
            assert key.replace("_", "").isalnum()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
