"""
Test constants validation and usage in Phase 2 improvements.

Validates that constants are properly defined, used consistently,
and that the replacement of magic numbers is effective.
"""

from __future__ import annotations

import pytest

from ui.common import spacing_constants
from ui.styles.theme import COLORS
from utils import constants

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.no_manager_setup,
]


class TestConstantsValidation:
    """Test constants definition and validation"""

    def test_sprite_format_constants_consistency(self):
        """Test sprite format constants are mathematically consistent"""
        # Tile format
        assert constants.BYTES_PER_TILE == 32
        assert constants.TILE_WIDTH == 8
        assert constants.TILE_HEIGHT == 8
        assert constants.DEFAULT_TILES_PER_ROW == 16

        # Tile format math validation
        pixels_per_tile = constants.TILE_WIDTH * constants.TILE_HEIGHT  # 64 pixels
        bits_per_pixel = 4  # 4bpp format
        bytes_per_tile_calculated = (pixels_per_tile * bits_per_pixel) // 8
        assert bytes_per_tile_calculated == constants.BYTES_PER_TILE

    def test_buffer_size_constants_powers_of_two(self):
        """Test that buffer sizes are proper powers of two"""
        buffer_sizes = [
            constants.BUFFER_SIZE_64KB,
            constants.BUFFER_SIZE_16KB,
            constants.BUFFER_SIZE_8KB,
            constants.BUFFER_SIZE_4KB,
            constants.BUFFER_SIZE_2KB,
            constants.BUFFER_SIZE_1KB,
            constants.BUFFER_SIZE_512B,
            constants.BUFFER_SIZE_256B,
        ]

        for size in buffer_sizes:
            # Check if it's a power of 2
            assert size > 0 and (size & (size - 1)) == 0, f"Buffer size {size} is not a power of 2"

        # Check descending order
        for i in range(len(buffer_sizes) - 1):
            assert buffer_sizes[i] > buffer_sizes[i + 1], (
                f"Buffer sizes not in descending order: {buffer_sizes[i]} <= {buffer_sizes[i + 1]}"
            )

    def test_palette_info_completeness(self):
        """Test that palette info covers all sprite palettes"""
        palette_info = constants.PALETTE_INFO

        # Should cover all sprite palette indices
        for palette_idx in range(constants.SPRITE_PALETTE_START, constants.SPRITE_PALETTE_END):
            assert palette_idx in palette_info, f"Missing palette info for index {palette_idx}"

            name, description = palette_info[palette_idx]
            assert isinstance(name, str) and len(name) > 0, f"Invalid name for palette {palette_idx}"
            assert isinstance(description, str) and len(description) > 0, (
                f"Invalid description for palette {palette_idx}"
            )

    def test_file_pattern_constants_validity(self):
        """Test that file pattern constants are valid glob patterns"""
        patterns = {
            "VRAM": constants.VRAM_PATTERNS,
            "CGRAM": constants.CGRAM_PATTERNS,
            "OAM": constants.OAM_PATTERNS,
        }

        for pattern_type, pattern_list in patterns.items():
            assert isinstance(pattern_list, list), f"{pattern_type} patterns should be a list"
            assert len(pattern_list) > 0, f"{pattern_type} patterns should not be empty"

            for pattern in pattern_list:
                assert isinstance(pattern, str), f"Pattern {pattern} should be string"
                assert "*" in pattern, f"Pattern {pattern} should contain wildcards"
                assert pattern.endswith(".dmp"), f"Pattern {pattern} should end with .dmp"

    def test_sprite_analysis_constants_ranges(self):
        """Test sprite analysis constants have valid ranges"""
        # Sprite size constants should be in ascending order
        assert constants.MIN_SPRITE_TILES < constants.TYPICAL_SPRITE_MIN
        assert constants.TYPICAL_SPRITE_MIN < constants.TYPICAL_SPRITE_MAX
        assert constants.TYPICAL_SPRITE_MAX < constants.LARGE_SPRITE_MAX

        # Quality thresholds should be in valid range
        assert 0.0 <= constants.SPRITE_QUALITY_THRESHOLD <= 1.0
        assert 0.0 <= constants.SPRITE_QUALITY_BONUS <= 1.0
        assert constants.SPRITE_QUALITY_THRESHOLD + constants.SPRITE_QUALITY_BONUS <= 1.0

    def test_progress_reporting_constants_reasonable(self):
        """Test that progress reporting intervals are reasonable"""
        # Progress intervals should be positive
        assert constants.PROGRESS_LOG_INTERVAL > 0
        assert constants.PROGRESS_SAVE_INTERVAL > 0
        assert constants.PROGRESS_DISPLAY_INTERVAL > 0

        # Save interval should be more frequent than display (for responsiveness)
        assert constants.PROGRESS_SAVE_INTERVAL <= constants.PROGRESS_DISPLAY_INTERVAL

    def test_hal_compression_limits(self):
        """Test HAL compression limits are consistent"""
        assert constants.DATA_SIZE == 65536  # 64KB
        assert constants.DATA_SIZE == constants.BUFFER_SIZE_64KB
        assert constants.BUFFER_SIZE_64KB > constants.VRAM_SPRITE_SIZE

    def test_settings_namespace_constants(self):
        """Test settings namespace constants are properly defined"""
        namespaces = [
            constants.SETTINGS_NS_SESSION,
            constants.SETTINGS_NS_WINDOW,
            constants.SETTINGS_NS_DIRECTORIES,
            constants.SETTINGS_NS_ROM_INJECTION,
        ]

        for namespace in namespaces:
            assert isinstance(namespace, str), f"Namespace {namespace} should be string"
            assert len(namespace) > 0, f"Namespace {namespace} should not be empty"
            assert namespace.isalnum() or "_" in namespace, f"Namespace {namespace} has invalid characters"


class TestSpacingConstantsValidation:
    """Test UI spacing constants validation"""

    def test_base_unit_grid_system(self):
        """Test that spacing follows 8px grid system"""
        assert spacing_constants.BASE_UNIT == 8

        # All spacing values should be multiples of base unit
        spacing_values = [
            spacing_constants.SPACING_TINY,
            spacing_constants.SPACING_SMALL,
            spacing_constants.SPACING_MEDIUM,
            spacing_constants.SPACING_LARGE,
            spacing_constants.SPACING_XLARGE,
        ]

        for spacing in spacing_values:
            assert spacing % spacing_constants.BASE_UNIT == 0 or spacing == spacing_constants.BASE_UNIT // 2, (
                f"Spacing {spacing} doesn't follow 8px grid system"
            )

    def test_widget_size_consistency(self):
        """Test widget size constants are consistent and reasonable"""
        # Heights should be reasonable for UI elements
        assert 20 <= spacing_constants.BUTTON_HEIGHT <= 60
        assert 20 <= spacing_constants.COMPACT_BUTTON_HEIGHT <= 50
        assert 20 <= spacing_constants.INPUT_HEIGHT <= 50
        assert spacing_constants.COMPACT_BUTTON_HEIGHT <= spacing_constants.BUTTON_HEIGHT

        # Widths should be in ascending order
        assert spacing_constants.COMPACT_WIDTH < spacing_constants.MEDIUM_WIDTH
        assert spacing_constants.MEDIUM_WIDTH < spacing_constants.WIDE_WIDTH

    def test_color_constants_valid_hex(self):
        """Test that color constants in theme.py are valid hex colors"""
        # Now using COLORS from ui/styles/theme.py (single source of truth)
        colors = [
            COLORS["primary"],
            COLORS["success"],
            COLORS["warning"],
            COLORS["danger"],  # Renamed from ERROR
            COLORS["text_muted"],
            COLORS["background"],
            COLORS["preview_background"],  # Renamed from SURFACE
            COLORS["border"],
        ]

        for color in colors:
            assert isinstance(color, str), f"Color {color} should be string"
            assert color.startswith("#"), f"Color {color} should start with #"
            assert len(color) == 7, f"Color {color} should be 7 characters long"
            # Test that it's valid hex
            int(color[1:], 16)  # Should not raise ValueError

    def test_font_size_constants_valid_css(self):
        """Test that font size constants are valid CSS values"""
        font_sizes = [
            spacing_constants.FONT_SIZE_SMALL,
            spacing_constants.FONT_SIZE_NORMAL,
            spacing_constants.FONT_SIZE_MEDIUM,
            spacing_constants.FONT_SIZE_LARGE,
            spacing_constants.FONT_SIZE_XLARGE,
        ]

        for font_size in font_sizes:
            assert isinstance(font_size, str), f"Font size {font_size} should be string"
            assert font_size.endswith("px"), f"Font size {font_size} should end with px"
            # Extract numeric part and validate
            numeric_part = font_size[:-2]
            assert numeric_part.isdigit(), f"Font size {font_size} has invalid numeric part"
            assert 8 <= int(numeric_part) <= 24, f"Font size {font_size} is out of reasonable range"

    def test_animation_constants_reasonable_values(self):
        """Test animation timing constants are reasonable"""
        # Animation duration should be reasonable for UI
        assert 50 <= spacing_constants.COLLAPSIBLE_ANIMATION_DURATION <= 500

        # Easing should be valid CSS easing function
        assert spacing_constants.COLLAPSIBLE_EASING in ["ease", "ease-in", "ease-out", "ease-in-out", "linear"], (
            f"Invalid easing function: {spacing_constants.COLLAPSIBLE_EASING}"
        )

    def test_preview_widget_constants(self):
        """Test preview widget constants are reasonable"""
        # Preview sizes should be reasonable
        assert 16 <= spacing_constants.PALETTE_PREVIEW_SIZE <= 64
        assert 128 <= spacing_constants.PREVIEW_MIN_SIZE <= 512
        assert 5.0 <= spacing_constants.MAX_ZOOM <= 50.0

        # Zoom should allow reasonable magnification
        max_magnified_size = spacing_constants.PREVIEW_MIN_SIZE * spacing_constants.MAX_ZOOM
        assert max_magnified_size >= 2560, "Maximum zoom should allow reasonable magnification"


class TestConstantUsageValidation:
    """Test that constants are being used correctly in the codebase"""

    def test_palette_constants_usage(self):
        """Test palette-related constants are properly defined for usage"""
        # These constants should be available for palette validation logic
        assert hasattr(constants, "SPRITE_PALETTE_START")
        assert hasattr(constants, "SPRITE_PALETTE_END")
        assert hasattr(constants, "COLORS_PER_PALETTE")

        # Should be able to generate valid palette range
        palette_range = list(range(constants.SPRITE_PALETTE_START, constants.SPRITE_PALETTE_END))
        assert len(palette_range) == 8  # Palettes 8-15
        assert all(0 <= p <= 15 for p in palette_range)

    def test_buffer_size_constants_usage(self):
        """Test buffer size constants are suitable for memory operations"""
        # Common buffer operations should work with these constants
        assert constants.BUFFER_SIZE_64KB >= constants.DATA_SIZE
        assert constants.BUFFER_SIZE_16KB >= constants.VRAM_SPRITE_SIZE

        # Should be able to calculate chunk sizes
        chunk_count = constants.BUFFER_SIZE_64KB // constants.BUFFER_SIZE_1KB
        assert chunk_count == 64

    def test_file_extension_constants_usage(self):
        """Test file extension constants are properly formatted"""
        extensions = [
            constants.PALETTE_EXTENSION,
            constants.METADATA_EXTENSION,
            constants.SPRITE_EXTENSION,
        ]

        for ext in extensions:
            assert ext.startswith("."), f"Extension {ext} should start with dot"
            assert len(ext) > 1, f"Extension {ext} should have content after dot"
            assert ext.islower() or ext == ext.upper(), f"Extension {ext} should be consistent case"

    def test_settings_key_constants_usage(self):
        """Test settings key constants are properly formatted for QSettings"""
        settings_keys = [
            constants.SETTINGS_KEY_VRAM_PATH,
            constants.SETTINGS_KEY_CGRAM_PATH,
            constants.SETTINGS_KEY_OAM_PATH,
            constants.SETTINGS_KEY_OUTPUT_BASE,
            constants.SETTINGS_KEY_GEOMETRY,
            constants.SETTINGS_KEY_STATE,
        ]

        for key in settings_keys:
            assert isinstance(key, str), f"Settings key {key} should be string"
            assert len(key) > 0, f"Settings key {key} should not be empty"
            assert key.replace("_", "").isalnum(), f"Settings key {key} has invalid characters"


class TestSNESAddressParsing:
    """Test SNES address parsing and normalization functions"""

    def test_parse_snes_banked_with_dollar_prefix(self):
        """Test parsing Mesen-style SNES address with $ prefix"""
        val, fmt = constants.parse_address_string("$98:8000")
        assert val == 0x988000
        assert fmt == "snes_banked"

    def test_parse_snes_banked_without_prefix(self):
        """Test parsing SNES bank:offset without $ prefix"""
        val, fmt = constants.parse_address_string("98:8000")
        assert val == 0x988000
        assert fmt == "snes_banked"

    def test_parse_snes_banked_lowercase(self):
        """Test parsing lowercase SNES address"""
        val, fmt = constants.parse_address_string("$98:b000")
        assert val == 0x98B000
        assert fmt == "snes_banked"

    def test_parse_snes_combined_with_dollar(self):
        """Test parsing combined SNES address with $ prefix"""
        val, fmt = constants.parse_address_string("$988000")
        assert val == 0x988000
        assert fmt == "snes"

    def test_parse_hex_with_0x_prefix(self):
        """Test parsing standard hex with 0x prefix"""
        val, fmt = constants.parse_address_string("0x0C3000")
        assert val == 0x0C3000
        assert fmt == "hex"

    def test_parse_hex_without_prefix_with_hex_chars(self):
        """Test parsing hex without prefix when it contains a-f"""
        val, fmt = constants.parse_address_string("C3000")
        assert val == 0xC3000
        assert fmt == "hex"

    def test_parse_decimal(self):
        """Test parsing pure decimal number"""
        val, fmt = constants.parse_address_string("123456")
        assert val == 123456
        assert fmt == "decimal"

    def test_parse_empty_raises_error(self):
        """Test that empty string raises ValueError"""
        with pytest.raises(ValueError, match="Empty"):
            constants.parse_address_string("")

    def test_parse_whitespace_only_raises_error(self):
        """Test that whitespace-only string raises ValueError"""
        with pytest.raises(ValueError, match="Empty"):
            constants.parse_address_string("   ")

    def test_parse_invalid_bank_raises_error(self):
        """Test that bank > 0xFF raises ValueError"""
        with pytest.raises(ValueError, match="exceeds"):
            constants.parse_address_string("$1FF:8000")

    def test_parse_invalid_address_raises_error(self):
        """Test that address > 0xFFFF raises ValueError"""
        with pytest.raises(ValueError, match="exceeds"):
            constants.parse_address_string("$98:1FFFF")

    def test_parse_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped"""
        val, fmt = constants.parse_address_string("  0x8000  ")
        assert val == 0x8000
        assert fmt == "hex"

    def test_is_snes_address_high_address(self):
        """Test is_snes_address detects addresses > 0x7FFFFF"""
        assert constants.is_snes_address(0x808000) is True
        assert constants.is_snes_address(0x988000) is True

    def test_is_snes_address_lorom_pattern(self):
        """Test is_snes_address detects LoROM pattern"""
        # Bank 0x01, address 0x8000 - looks like SNES
        assert constants.is_snes_address(0x018000) is True
        # Just 0x8000 with no bank - file offset
        assert constants.is_snes_address(0x8000) is False

    def test_is_snes_address_file_offset(self):
        """Test is_snes_address returns False for file offsets"""
        assert constants.is_snes_address(0x0C3000) is False
        assert constants.is_snes_address(0x200000) is False

    def test_snes_to_file_offset_basic(self):
        """Test LoROM address conversion"""
        # $80:8000 -> bank 0 (mirrored), addr 0x8000 -> file 0x0000
        assert constants.snes_to_file_offset(0x808000) == 0x0000

    def test_snes_to_file_offset_bank_mirror(self):
        """Test bank mirroring (0x80-0xFF -> 0x00-0x7F)"""
        # $98:8000 -> bank 0x18, addr 0x8000 -> file 0xC0000
        offset = constants.snes_to_file_offset(0x988000)
        assert offset == 0xC0000

    def test_snes_to_file_offset_with_smc_header(self):
        """Test conversion with SMC header adjustment"""
        offset = constants.snes_to_file_offset(0x808000, has_smc_header=True)
        assert offset == 512  # 0x0000 + 512

    def test_normalize_address_snes(self):
        """Test normalize_address with SNES address"""
        # 2MB ROM without SMC header
        offset = constants.normalize_address(0x988000, 0x200000)
        assert offset == 0xC0000

    def test_normalize_address_file_offset(self):
        """Test normalize_address with file offset (passthrough)"""
        offset = constants.normalize_address(0x50000, 0x200000)
        assert offset == 0x50000

    def test_normalize_address_with_smc_header(self):
        """Test normalize_address detects SMC header from size"""
        # ROM size 0x200200 = 2MB + 512 bytes (has SMC header)
        # File offset should add 512
        offset = constants.normalize_address(0x50000, 0x200200)
        assert offset == 0x50200  # 0x50000 + 512
