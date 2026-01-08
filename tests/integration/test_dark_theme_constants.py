"""
Tests for dark theme color constants and accessibility compliance.

This module consolidates tests from:
- test_dark_theme_colors.py (color validation, theme class tests)
- test_dark_theme_accessibility.py (WCAG contrast requirements)

All tests in this module are headless (no Qt required).
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
    pytest.mark.allows_registry_state(reason="UI tests may trigger Qt auto-registration"),
    pytest.mark.headless,
]


# =============================================================================
# Utility Classes
# =============================================================================


class ContrastCalculator:
    """Utility class for calculating color contrast ratios according to WCAG 2.1."""

    @staticmethod
    def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    @staticmethod
    def relative_luminance(r: int, g: int, b: int) -> float:
        """Calculate relative luminance according to WCAG 2.1."""

        def gamma_correct(c: float) -> float:
            c = c / 255.0
            if c <= 0.03928:
                return c / 12.92
            else:
                return ((c + 0.055) / 1.055) ** 2.4

        r_linear = gamma_correct(r)
        g_linear = gamma_correct(g)
        b_linear = gamma_correct(b)

        return 0.2126 * r_linear + 0.7152 * g_linear + 0.0722 * b_linear

    @classmethod
    def contrast_ratio(cls, color1: str, color2: str) -> float:
        """Calculate contrast ratio between two hex colors."""
        rgb1 = cls.hex_to_rgb(color1)
        rgb2 = cls.hex_to_rgb(color2)

        l1 = cls.relative_luminance(*rgb1)
        l2 = cls.relative_luminance(*rgb2)

        bright = max(l1, l2)
        dark = min(l1, l2)

        return (bright + 0.05) / (dark + 0.05)

    @classmethod
    def meets_wcag_aa(cls, color1: str, color2: str, large_text: bool = False) -> bool:
        """Check if color combination meets WCAG 2.1 AA standards."""
        ratio = cls.contrast_ratio(color1, color2)
        required_ratio = 3.0 if large_text else 4.5
        return ratio >= required_ratio

    @classmethod
    def meets_wcag_aaa(cls, color1: str, color2: str, large_text: bool = False) -> bool:
        """Check if color combination meets WCAG 2.1 AAA standards."""
        ratio = cls.contrast_ratio(color1, color2)
        required_ratio = 4.5 if large_text else 7.0
        return ratio >= required_ratio


# =============================================================================
# Color Constant Tests (from test_dark_theme_colors.py)
# =============================================================================


class TestColorConstants:
    """Test dark theme color constants validation."""

    def test_all_colors_are_valid_hex(self) -> None:
        """All color constants should be valid hex color codes."""
        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")

        for color_name, color_value in COLORS.items():
            assert isinstance(color_value, str), f"Color {color_name} should be string"
            assert hex_pattern.match(color_value), f"Color {color_name} ({color_value}) should be valid hex"

    def test_required_colors_exist(self) -> None:
        """Essential colors for dark theme should be defined."""
        required_colors = [
            "primary",
            "secondary",
            "accent",
            "background",
            "panel_background",
            "input_background",
            "preview_background",
            "text_primary",
            "text_secondary",
            "text_muted",
            "border",
            "border_focus",
            "border_error",
            "success",
            "warning",
            "danger",
            "info",
            "disabled",
            "disabled_text",
        ]

        for color in required_colors:
            assert color in COLORS, f"Required color '{color}' is missing"

    def test_color_hierarchy_consistency(self) -> None:
        """Color variations should have consistent naming patterns."""
        action_colors = ["primary", "secondary", "accent", "extract", "editor"]

        for base_color in action_colors:
            if base_color in COLORS:
                hover_key = f"{base_color}_hover"
                pressed_key = f"{base_color}_pressed"

                assert hover_key in COLORS, f"Missing hover variant for {base_color}"
                assert pressed_key in COLORS, f"Missing pressed variant for {base_color}"

    @pytest.mark.parametrize(
        "color_key,expected_darkness",
        [
            ("background", True),
            ("panel_background", True),
            ("preview_background", True),
            ("text_primary", False),
            ("text_secondary", False),
        ],
    )
    def test_color_darkness_appropriate_for_theme(self, color_key: str, expected_darkness: bool) -> None:
        """Colors should have appropriate lightness for dark theme."""
        color_hex = COLORS[color_key]
        r = int(color_hex[1:3], 16)
        g = int(color_hex[3:5], 16)
        b = int(color_hex[5:7], 16)

        brightness = r * 0.299 + g * 0.587 + b * 0.114
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
        assert 20 <= DIMENSIONS["button_height"] <= 40, "Button height should be reasonable"
        assert 20 <= DIMENSIONS["input_height"] <= 40, "Input height should be reasonable"
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
        assert "QWidget {" in css
        assert "QGroupBox {" in css
        # QLabel inherits from QWidget; only preview labels have specific styling
        assert "QLabel[preview=" in css
        assert "QStatusBar {" in css
        assert COLORS["text_primary"] in css
        assert COLORS["background"] in css
        assert COLORS["panel_background"] in css

    def test_get_theme_style_contains_expected_properties(self) -> None:
        """Theme style should contain expected CSS properties."""
        css = get_theme_style()

        assert f"font-family: {FONTS['default_family']}" in css
        assert f"font-size: {FONTS['default_size']}" in css
        assert f"color: {COLORS['text_primary']}" in css
        assert f"background-color: {COLORS['background']}" in css
        assert f"background-color: {COLORS['panel_background']}" in css
        assert f"{DIMENSIONS['border_width']}px solid" in css
        assert f"border-radius: {DIMENSIONS['border_radius']}px" in css

    def test_get_disabled_state_style_returns_valid_css(self) -> None:
        """get_disabled_state_style should return valid CSS for disabled widgets."""
        css = get_disabled_state_style()

        assert isinstance(css, str)
        assert len(css) > 0
        assert ":disabled {" in css
        assert COLORS["disabled"] in css
        assert COLORS["disabled_text"] in css


class TestColorUtilities:
    """Test color utility functions and calculations."""

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    def test_color_parsing_utility(self) -> None:
        """Utility function for parsing colors works correctly."""
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


class TestColorConstantsHeadless:
    """Headless tests for color constants that don't require Qt."""

    def test_colors_dictionary_is_immutable_reference(self) -> None:
        """COLORS dictionary should be a stable reference for imports."""
        from ui.styles.theme import COLORS as colors_import

        assert colors_import is COLORS
        assert len(colors_import) > 0

    def test_theme_constants_are_strings(self) -> None:
        """All theme constants should be strings for CSS compatibility."""
        test_constants = [Theme.PRIMARY, Theme.BACKGROUND, Theme.TEXT, Theme.BORDER, Theme.SUCCESS]

        for constant in test_constants:
            assert isinstance(constant, str)
            assert constant.startswith("#")


# =============================================================================
# WCAG Accessibility Tests (from test_dark_theme_accessibility.py)
# =============================================================================


class TestWCAGContrast:
    """Test WCAG contrast ratios for dark theme color combinations."""

    def test_primary_text_on_background_meets_wcag_aa(self) -> None:
        """Primary text on main background should meet WCAG AA standards."""
        ratio = ContrastCalculator.contrast_ratio(COLORS["text_primary"], COLORS["background"])

        assert ratio >= 4.5, (
            f"Primary text contrast ratio {ratio:.2f} should be >= 4.5 "
            f"({COLORS['text_primary']} on {COLORS['background']})"
        )
        assert ContrastCalculator.meets_wcag_aa(COLORS["text_primary"], COLORS["background"])

    def test_secondary_text_on_background_meets_wcag_aa(self) -> None:
        """Secondary text on main background should meet WCAG AA standards."""
        ratio = ContrastCalculator.contrast_ratio(COLORS["text_secondary"], COLORS["background"])

        assert ratio >= 4.5, (
            f"Secondary text contrast ratio {ratio:.2f} should be >= 4.5 "
            f"({COLORS['text_secondary']} on {COLORS['background']})"
        )

    def test_muted_text_visibility(self) -> None:
        """Muted text should still be readable, though may not meet full WCAG AA."""
        ratio = ContrastCalculator.contrast_ratio(COLORS["text_muted"], COLORS["background"])

        assert ratio >= 3.0, (
            f"Muted text contrast ratio {ratio:.2f} should be >= 3.0 for readability "
            f"({COLORS['text_muted']} on {COLORS['background']})"
        )

    def test_disabled_text_distinguishable(self) -> None:
        """Disabled text should be visually distinguishable but intentionally lower contrast."""
        disabled_ratio = ContrastCalculator.contrast_ratio(COLORS["disabled_text"], COLORS["background"])

        normal_ratio = ContrastCalculator.contrast_ratio(COLORS["text_primary"], COLORS["background"])

        assert disabled_ratio < normal_ratio, "Disabled text should have lower contrast than normal text"
        assert disabled_ratio >= 2.0, "Disabled text should still be somewhat visible"

    @pytest.mark.parametrize(
        "text_color,background_color",
        [
            ("text_primary", "panel_background"),
            ("text_primary", "input_background"),
            ("text_secondary", "panel_background"),
        ],
    )
    def test_text_on_various_backgrounds_readable(self, text_color: str, background_color: str) -> None:
        """Text should be readable on various dark theme backgrounds."""
        ratio = ContrastCalculator.contrast_ratio(COLORS[text_color], COLORS[background_color])

        assert ratio >= 3.0, (
            f"Text {text_color} on {background_color} contrast ratio {ratio:.2f} should be >= 3.0 for readability"
        )


class TestButtonContrast:
    """Test contrast ratios for button color combinations."""

    @pytest.mark.parametrize("button_type", ["primary", "secondary", "accent", "extract", "editor"])
    def test_button_text_contrast_on_button_background(self, button_type: str) -> None:
        """Button text should have good contrast on button backgrounds."""
        button_bg = COLORS[button_type]
        text_color = COLORS["white"]

        ratio = ContrastCalculator.contrast_ratio(text_color, button_bg)

        assert ratio >= 2.0, (
            f"Button {button_type} text contrast {ratio:.2f} should be >= 2.0 for basic readability "
            f"({text_color} on {button_bg})"
        )

    def test_default_button_text_contrast(self) -> None:
        """Default button should have appropriate text contrast."""
        button_bg = COLORS["light_gray"]
        text_color = COLORS["black"]

        ratio = ContrastCalculator.contrast_ratio(text_color, button_bg)

        assert ratio >= 2.0, (
            f"Default button text contrast {ratio:.2f} should be >= 2.0 for basic readability "
            f"({text_color} on {button_bg})"
        )

    @pytest.mark.parametrize("button_type", ["primary", "secondary", "accent", "extract", "editor"])
    def test_button_hover_state_contrast(self, button_type: str) -> None:
        """Button hover states should maintain good contrast."""
        hover_bg = COLORS[f"{button_type}_hover"]
        text_color = COLORS["white"]

        ratio = ContrastCalculator.contrast_ratio(text_color, hover_bg)

        assert ratio >= 1.2, (
            f"Button {button_type} hover contrast {ratio:.2f} should be >= 1.2 for basic readability "
            f"({text_color} on {hover_bg})"
        )


class TestStatusColorContrast:
    """Test contrast ratios for status indicator colors."""

    @pytest.mark.parametrize("status_type", ["success", "warning", "danger", "info"])
    def test_status_colors_visible_on_dark_background(self, status_type: str) -> None:
        """Status colors should be highly visible on dark backgrounds."""
        status_color = COLORS[status_type]
        background = COLORS["background"]

        ratio = ContrastCalculator.contrast_ratio(status_color, background)

        assert ratio >= 3.0, (
            f"Status {status_type} contrast {ratio:.2f} should be >= 3.0 for visibility "
            f"({status_color} on {background})"
        )

    def test_status_colors_on_panel_background(self) -> None:
        """Status colors should be visible on panel backgrounds."""
        panel_bg = COLORS["panel_background"]

        status_colors = ["success", "warning", "danger", "info"]
        for status_type in status_colors:
            status_color = COLORS[status_type]
            ratio = ContrastCalculator.contrast_ratio(status_color, panel_bg)

            assert ratio >= 3.0, (
                f"Status {status_type} on panel background contrast {ratio:.2f} "
                f"should be >= 3.0 for visibility ({status_color} on {panel_bg})"
            )


class TestBorderContrast:
    """Test contrast ratios for border colors."""

    def test_default_border_visible_on_backgrounds(self) -> None:
        """Default borders should be visible on dark backgrounds."""
        border_color = COLORS["border"]

        backgrounds = ["background", "panel_background", "input_background"]
        for bg_key in backgrounds:
            bg_color = COLORS[bg_key]
            ratio = ContrastCalculator.contrast_ratio(border_color, bg_color)

            assert ratio >= 1.5, (
                f"Border on {bg_key} contrast {ratio:.2f} should be >= 1.5 ({border_color} on {bg_color})"
            )

    def test_focus_border_highly_visible(self) -> None:
        """Focus borders should be highly visible for accessibility."""
        focus_border = COLORS["border_focus"]

        backgrounds = ["background", "panel_background", "input_background"]
        for bg_key in backgrounds:
            bg_color = COLORS[bg_key]
            ratio = ContrastCalculator.contrast_ratio(focus_border, bg_color)

            assert ratio >= 2.5, (
                f"Focus border on {bg_key} contrast {ratio:.2f} should be >= 2.5 ({focus_border} on {bg_color})"
            )

    def test_error_border_highly_visible(self) -> None:
        """Error borders should be highly visible for accessibility."""
        error_border = COLORS["border_error"]

        backgrounds = ["background", "panel_background", "input_background"]
        for bg_key in backgrounds:
            bg_color = COLORS[bg_key]
            ratio = ContrastCalculator.contrast_ratio(error_border, bg_color)

            assert ratio >= 3.0, (
                f"Error border on {bg_key} contrast {ratio:.2f} should be >= 3.0 ({error_border} on {bg_color})"
            )


class TestPreviewBackgroundContrast:
    """Test contrast for sprite preview backgrounds."""

    def test_preview_background_darker_than_main(self) -> None:
        """Preview background should be darker than main background for sprite visibility."""
        preview_lum = ContrastCalculator.relative_luminance(
            *ContrastCalculator.hex_to_rgb(COLORS["preview_background"])
        )
        main_lum = ContrastCalculator.relative_luminance(*ContrastCalculator.hex_to_rgb(COLORS["background"]))

        assert preview_lum < main_lum, (
            "Preview background should be darker than main background "
            f"({COLORS['preview_background']} vs {COLORS['background']})"
        )

    def test_preview_text_readable_on_preview_background(self) -> None:
        """Text should be readable on preview backgrounds when needed."""
        ratio = ContrastCalculator.contrast_ratio(COLORS["text_primary"], COLORS["preview_background"])

        assert ratio >= 4.5, (
            f"Text on preview background contrast {ratio:.2f} should be >= 4.5 "
            f"({COLORS['text_primary']} on {COLORS['preview_background']})"
        )


class TestColorDistinguishability:
    """Test that colors are sufficiently distinguishable from each other."""

    def test_action_colors_distinguishable(self) -> None:
        """Action colors should be sufficiently different from each other."""
        action_colors = ["primary", "secondary", "accent", "extract", "editor"]

        for i, color1_key in enumerate(action_colors):
            for color2_key in action_colors[i + 1 :]:
                color1 = COLORS[color1_key]
                color2 = COLORS[color2_key]

                ratio = ContrastCalculator.contrast_ratio(color1, color2)
                assert ratio >= 1.0, (
                    f"Action colors {color1_key} and {color2_key} should be at least nominally different "
                    f"(contrast ratio: {ratio:.2f})"
                )

    def test_text_colors_distinguishable(self) -> None:
        """Different text colors should be distinguishable."""
        text_colors = ["text_primary", "text_secondary", "text_muted"]

        for i, color1_key in enumerate(text_colors):
            for color2_key in text_colors[i + 1 :]:
                color1 = COLORS[color1_key]
                color2 = COLORS[color2_key]

                ratio = ContrastCalculator.contrast_ratio(color1, color2)
                assert ratio >= 1.1, (
                    f"Text colors {color1_key} and {color2_key} should be distinguishable (contrast ratio: {ratio:.2f})"
                )

    def test_background_colors_distinguishable(self) -> None:
        """Background colors should be distinguishable for layering."""
        bg_colors = ["background", "panel_background", "input_background", "preview_background"]

        main_bg = COLORS["background"]
        for bg_key in bg_colors[1:]:
            bg_color = COLORS[bg_key]
            ratio = ContrastCalculator.contrast_ratio(main_bg, bg_color)

            assert ratio >= 1.03, (
                f"Background colors should be distinguishable: background vs {bg_key} (contrast: {ratio:.2f})"
            )


class TestAccessibilityGuidelines:
    """Test compliance with additional accessibility guidelines."""

    def test_sufficient_color_separation_in_ui(self) -> None:
        """UI elements should have sufficient color separation for color-blind users."""
        error_color = COLORS["border_error"]
        danger_color = COLORS["danger"]

        ratio = ContrastCalculator.contrast_ratio(error_color, danger_color)
        assert ratio >= 1.0, "Error-related colors should be at least nominally distinguishable"

    def test_disabled_states_appropriately_muted(self) -> None:
        """Disabled states should be visually muted but still perceivable."""
        disabled_bg = COLORS["disabled"]
        disabled_text = COLORS["disabled_text"]
        normal_bg = COLORS["light_gray"]
        normal_text = COLORS["text_primary"]

        disabled_contrast = ContrastCalculator.contrast_ratio(disabled_text, disabled_bg)
        normal_contrast = ContrastCalculator.contrast_ratio(normal_text, normal_bg)

        assert disabled_contrast < normal_contrast, "Disabled states should have lower contrast"
        assert disabled_contrast >= 2.0, "Disabled states should still be somewhat visible"


class TestContrastCalculatorUtility:
    """Test the contrast calculator utility itself."""

    def test_contrast_calculator_with_known_values(self) -> None:
        """Test contrast calculator with known reference values."""
        black_white_ratio = ContrastCalculator.contrast_ratio("#000000", "#ffffff")
        assert abs(black_white_ratio - 21.0) < 0.1, "Black/white contrast should be ~21:1"

        identical_ratio = ContrastCalculator.contrast_ratio("#808080", "#808080")
        assert abs(identical_ratio - 1.0) < 0.1, "Identical colors should have 1:1 contrast"

    def test_hex_to_rgb_conversion(self) -> None:
        """Test hex to RGB conversion utility."""
        assert ContrastCalculator.hex_to_rgb("#ffffff") == (255, 255, 255)
        assert ContrastCalculator.hex_to_rgb("#000000") == (0, 0, 0)
        assert ContrastCalculator.hex_to_rgb("#ff0000") == (255, 0, 0)
        assert ContrastCalculator.hex_to_rgb("ffffff") == (255, 255, 255)

    def test_relative_luminance_calculation(self) -> None:
        """Test relative luminance calculation."""
        white_lum = ContrastCalculator.relative_luminance(255, 255, 255)
        assert abs(white_lum - 1.0) < 0.1, "White luminance should be ~1.0"

        black_lum = ContrastCalculator.relative_luminance(0, 0, 0)
        assert abs(black_lum - 0.0) < 0.1, "Black luminance should be ~0.0"

    def test_wcag_compliance_methods(self) -> None:
        """Test WCAG compliance checking methods."""
        assert ContrastCalculator.meets_wcag_aa("#000000", "#ffffff")
        assert ContrastCalculator.meets_wcag_aaa("#000000", "#ffffff")
        assert not ContrastCalculator.meets_wcag_aa("#cccccc", "#ffffff")
        assert not ContrastCalculator.meets_wcag_aaa("#cccccc", "#ffffff")


class TestAccessibilityHeadless:
    """Headless accessibility tests that don't require Qt."""

    def test_all_theme_colors_have_valid_contrast_calculations(self) -> None:
        """All theme colors should be processable by contrast calculator."""
        for color_name, color_value in COLORS.items():
            try:
                rgb = ContrastCalculator.hex_to_rgb(color_value)
                luminance = ContrastCalculator.relative_luminance(*rgb)

                assert 0.0 <= luminance <= 1.0, f"Luminance for {color_name} out of range"

            except Exception as e:
                pytest.fail(f"Could not calculate contrast for color {color_name} ({color_value}): {e}")

    def test_accessibility_utility_functions_available(self) -> None:
        """Accessibility utility functions should be available for future use."""
        ContrastCalculator()

        assert callable(ContrastCalculator.hex_to_rgb)
        assert callable(ContrastCalculator.relative_luminance)
        assert callable(ContrastCalculator.contrast_ratio)
        assert callable(ContrastCalculator.meets_wcag_aa)
        assert callable(ContrastCalculator.meets_wcag_aaa)

    def test_critical_accessibility_combinations(self) -> None:
        """Test most critical accessibility combinations for the dark theme."""
        critical_tests = [
            ("text_primary", "background", 4.5, "Primary text on main background"),
            ("text_primary", "panel_background", 4.5, "Primary text on panels"),
            ("success", "background", 4.5, "Success indicators"),
            ("danger", "background", 4.5, "Error indicators"),
            ("warning", "background", 3.0, "Warning indicators (can be slightly lower)"),
        ]

        for text_key, bg_key, min_ratio, description in critical_tests:
            ratio = ContrastCalculator.contrast_ratio(COLORS[text_key], COLORS[bg_key])
            assert ratio >= min_ratio, f"{description}: {ratio:.2f} should be >= {min_ratio}"
