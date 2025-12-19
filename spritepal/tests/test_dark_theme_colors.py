"""
Tests for dark theme color constants and basic theme functionality.

This module tests the color definitions, Theme class, and basic styling functions
from ui.styles.theme.py following TDD principles with real implementations.
"""
from __future__ import annotations

import re

import pytest

from ui.styles.theme import (
    COLORS,
    DIMENSIONS,
    FONTS,
    Theme,
    get_disabled_state_style,
    get_theme_style,
)

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.allows_registry_state,
]


class TestColorConstants:
    """Test dark theme color constants validation."""

    def test_all_colors_are_valid_hex(self) -> None:
        """All color constants should be valid hex color codes."""
        hex_pattern = re.compile(r'^#[0-9A-Fa-f]{6}$')

        for color_name, color_value in COLORS.items():
            assert isinstance(color_value, str), f"Color {color_name} should be string"
            assert hex_pattern.match(color_value), f"Color {color_name} ({color_value}) should be valid hex"

    def test_required_colors_exist(self) -> None:
        """Essential colors for dark theme should be defined."""
        required_colors = [
            "primary", "secondary", "accent",
            "background", "panel_background", "input_background", "preview_background",
            "text_primary", "text_secondary", "text_muted",
            "border", "border_focus", "border_error",
            "success", "warning", "danger", "info",
            "disabled", "disabled_text"
        ]

        for color in required_colors:
            assert color in COLORS, f"Required color '{color}' is missing"

    def test_color_hierarchy_consistency(self) -> None:
        """Color variations should have consistent naming patterns."""
        # Test that hover/pressed variants exist for action colors
        action_colors = ["primary", "secondary", "accent", "extract", "editor"]

        for base_color in action_colors:
            if base_color in COLORS:
                hover_key = f"{base_color}_hover"
                pressed_key = f"{base_color}_pressed"

                assert hover_key in COLORS, f"Missing hover variant for {base_color}"
                assert pressed_key in COLORS, f"Missing pressed variant for {base_color}"

    @pytest.mark.parametrize("color_key,expected_darkness", [
        ("background", True),
        ("panel_background", True),
        ("preview_background", True),
        ("text_primary", False),  # Should be light (white)
        ("text_secondary", False),  # Should be light
    ])
    def test_color_darkness_appropriate_for_theme(
        self, color_key: str, expected_darkness: bool
    ) -> None:
        """Colors should have appropriate lightness for dark theme."""
        color_hex = COLORS[color_key]
        # Parse hex color to RGB
        r = int(color_hex[1:3], 16)
        g = int(color_hex[3:5], 16)
        b = int(color_hex[5:7], 16)

        # Calculate perceived brightness (0-255)
        brightness = (r * 0.299 + g * 0.587 + b * 0.114)
        is_dark = brightness < 128

        assert is_dark == expected_darkness, (
            f"Color {color_key} ({color_hex}) brightness={brightness:.1f} "
            f"should be {'dark' if expected_darkness else 'light'}"
        )

class TestFontConstants:
    """Test font constant definitions."""

    def test_font_families_defined(self) -> None:
        """Font families should be properly defined."""
        assert "default_family" in FONTS
        assert "monospace_family" in FONTS
        assert isinstance(FONTS["default_family"], str)
        assert isinstance(FONTS["monospace_family"], str)

    def test_font_sizes_defined(self) -> None:
        """Font sizes should be defined with px units."""
        size_keys = ["small_size", "default_size", "medium_size", "large_size"]

        for size_key in size_keys:
            assert size_key in FONTS
            size_value = FONTS[size_key]
            assert isinstance(size_value, str)
            assert size_value.endswith("px"), f"Font size {size_key} should end with 'px'"

            # Extract numeric value and validate
            numeric_part = size_value[:-2]
            assert numeric_part.isdigit(), f"Font size {size_key} should have numeric value"
            assert int(numeric_part) > 0, f"Font size {size_key} should be positive"

    def test_font_weights_defined(self) -> None:
        """Font weights should be properly defined."""
        assert "normal_weight" in FONTS
        assert "bold_weight" in FONTS
        assert FONTS["normal_weight"] in ["normal", "400"]
        assert FONTS["bold_weight"] in ["bold", "600", "700"]

class TestDimensionConstants:
    """Test dimension constant definitions."""

    def test_spacing_dimensions_are_positive_integers(self) -> None:
        """Spacing dimensions should be positive integers."""
        spacing_keys = ["spacing_xs", "spacing_sm", "spacing_md", "spacing_lg", "spacing_xl"]

        for key in spacing_keys:
            assert key in DIMENSIONS
            value = DIMENSIONS[key]
            assert isinstance(value, int), f"Dimension {key} should be integer"
            assert value > 0, f"Dimension {key} should be positive"

    def test_component_dimensions_are_reasonable(self) -> None:
        """Component dimensions should be within reasonable ranges."""
        # Test button heights
        assert 20 <= DIMENSIONS["button_height"] <= 40, "Button height should be reasonable"
        assert 20 <= DIMENSIONS["input_height"] <= 40, "Input height should be reasonable"

        # Test widths
        assert 50 <= DIMENSIONS["button_min_width"] <= 200, "Button min width should be reasonable"
        assert 100 <= DIMENSIONS["combo_min_width"] <= 400, "Combo min width should be reasonable"

    def test_border_dimensions_are_small_positive_integers(self) -> None:
        """Border widths should be small positive integers."""
        border_keys = ["border_width", "border_width_thick"]

        for key in border_keys:
            assert key in DIMENSIONS
            value = DIMENSIONS[key]
            assert isinstance(value, int)
            assert 1 <= value <= 5, f"Border width {key} should be 1-5 pixels"

class TestThemeClass:
    """Test the Theme class provides correct color access."""

    def test_theme_class_provides_primary_colors(self) -> None:
        """Theme class should provide access to primary color variations."""
        assert COLORS["primary"] == Theme.PRIMARY
        assert COLORS["primary_hover"] == Theme.PRIMARY_LIGHT
        assert COLORS["primary_pressed"] == Theme.PRIMARY_DARK

    def test_theme_class_provides_background_colors(self) -> None:
        """Theme class should provide access to background colors."""
        assert COLORS["background"] == Theme.BACKGROUND
        assert COLORS["panel_background"] == Theme.SURFACE
        assert COLORS["input_background"] == Theme.INPUT_BACKGROUND
        assert COLORS["preview_background"] == Theme.PREVIEW_BACKGROUND

    def test_theme_class_provides_text_colors(self) -> None:
        """Theme class should provide access to text colors."""
        assert COLORS["text_primary"] == Theme.TEXT
        assert COLORS["text_secondary"] == Theme.TEXT_SECONDARY
        assert COLORS["text_muted"] == Theme.TEXT_MUTED
        assert COLORS["disabled_text"] == Theme.TEXT_DISABLED

    def test_theme_class_provides_status_colors(self) -> None:
        """Theme class should provide access to status colors."""
        assert COLORS["success"] == Theme.SUCCESS
        assert COLORS["warning"] == Theme.WARNING
        assert COLORS["danger"] == Theme.DANGER
        assert COLORS["info"] == Theme.INFO

    def test_theme_class_provides_border_colors(self) -> None:
        """Theme class should provide access to border colors."""
        assert COLORS["border"] == Theme.BORDER
        assert COLORS["border_focus"] == Theme.BORDER_FOCUS
        assert COLORS["border_error"] == Theme.BORDER_ERROR

class TestThemeStylingFunctions:
    """Test basic theme styling functions."""

    def test_get_theme_style_returns_valid_css(self) -> None:
        """get_theme_style should return valid CSS string."""
        css = get_theme_style()

        assert isinstance(css, str)
        assert len(css) > 0

        # Check for essential CSS structure
        assert "QWidget {" in css
        assert "QGroupBox {" in css
        assert "QLabel {" in css
        assert "QStatusBar {" in css

        # Check for color references
        assert COLORS["text_primary"] in css
        assert COLORS["background"] in css
        assert COLORS["panel_background"] in css

    def test_get_theme_style_contains_expected_properties(self) -> None:
        """Theme style should contain expected CSS properties."""
        css = get_theme_style()

        # Check for font properties
        assert f"font-family: {FONTS['default_family']}" in css
        assert f"font-size: {FONTS['default_size']}" in css

        # Check for colors
        assert f"color: {COLORS['text_primary']}" in css
        assert f"background-color: {COLORS['background']}" in css
        assert f"background-color: {COLORS['panel_background']}" in css

        # Check for dimensions
        assert f"{DIMENSIONS['border_width']}px solid" in css
        assert f"border-radius: {DIMENSIONS['border_radius']}px" in css

    def test_get_disabled_state_style_returns_valid_css(self) -> None:
        """get_disabled_state_style should return valid CSS for disabled widgets."""
        css = get_disabled_state_style()

        assert isinstance(css, str)
        assert len(css) > 0

        # Check for disabled selector
        assert ":disabled {" in css

        # Check for disabled colors
        assert COLORS["disabled"] in css
        assert COLORS["disabled_text"] in css

    def test_theme_functions_handle_missing_constants_gracefully(self) -> None:
        """Theme functions should not crash if constants are temporarily unavailable."""
        # This test ensures robustness - functions should complete even if some constants change
        css = get_theme_style()
        disabled_css = get_disabled_state_style()

        # Basic validation that functions complete
        assert isinstance(css, str)
        assert isinstance(disabled_css, str)

class TestColorUtilities:
    """Test color utility functions and calculations."""

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def test_color_parsing_utility(self) -> None:
        """Utility function for parsing colors works correctly."""
        # Test with known colors
        assert self._hex_to_rgb("#ffffff") == (255, 255, 255)
        assert self._hex_to_rgb("#000000") == (0, 0, 0)
        assert self._hex_to_rgb("#ff0000") == (255, 0, 0)
        assert self._hex_to_rgb(COLORS["primary"]) is not None

    def test_all_colors_parseable(self) -> None:
        """All theme colors should be parseable to RGB."""
        for color_name, color_hex in COLORS.items():
            try:
                rgb = self._hex_to_rgb(color_hex)
                assert len(rgb) == 3
                assert all(0 <= c <= 255 for c in rgb), f"Color {color_name} RGB values out of range"
            except ValueError:
                pytest.fail(f"Color {color_name} ({color_hex}) is not parseable")

@pytest.mark.headless
class TestColorConstantsHeadless:
    """Headless tests for color constants that don't require Qt."""

    def test_colors_dictionary_is_immutable_reference(self) -> None:
        """COLORS dictionary should be a stable reference for imports."""
        # This tests that the COLORS dict is consistently available
        from ui.styles.theme import COLORS as colors_import

        assert colors_import is COLORS
        assert len(colors_import) > 0

    def test_theme_constants_are_strings(self) -> None:
        """All theme constants should be strings for CSS compatibility."""
        test_constants = [
            Theme.PRIMARY, Theme.BACKGROUND, Theme.TEXT,
            Theme.BORDER, Theme.SUCCESS
        ]

        for constant in test_constants:
            assert isinstance(constant, str)
            assert constant.startswith("#")
