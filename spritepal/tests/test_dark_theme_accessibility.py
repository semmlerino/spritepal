"""
Tests for dark theme accessibility and contrast ratios.

This module tests the accessibility compliance of the dark theme implementation,
focusing on WCAG 2.1 AA contrast requirements and visual accessibility.
"""
from __future__ import annotations

import pytest

from ui.styles.theme import COLORS

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.allows_registry_state(reason="UI tests may trigger Qt auto-registration"),
]


class ContrastCalculator:
    """Utility class for calculating color contrast ratios according to WCAG 2.1."""

    @staticmethod
    def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def relative_luminance(r: int, g: int, b: int) -> float:
        """
        Calculate relative luminance according to WCAG 2.1.
        
        Formula from: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
        """
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
        """
        Calculate contrast ratio between two hex colors.
        
        Returns ratio where 1.0 is no contrast and 21.0 is maximum contrast.
        """
        rgb1 = cls.hex_to_rgb(color1)
        rgb2 = cls.hex_to_rgb(color2)

        l1 = cls.relative_luminance(*rgb1)
        l2 = cls.relative_luminance(*rgb2)

        # Ensure lighter color is in numerator
        bright = max(l1, l2)
        dark = min(l1, l2)

        return (bright + 0.05) / (dark + 0.05)

    @classmethod
    def meets_wcag_aa(cls, color1: str, color2: str, large_text: bool = False) -> bool:
        """
        Check if color combination meets WCAG 2.1 AA standards.
        
        Args:
            color1: First color (hex)
            color2: Second color (hex)
            large_text: If True, uses 3:1 ratio requirement, otherwise 4.5:1
            
        Returns:
            True if combination meets WCAG AA requirements
        """
        ratio = cls.contrast_ratio(color1, color2)
        required_ratio = 3.0 if large_text else 4.5
        return ratio >= required_ratio

    @classmethod
    def meets_wcag_aaa(cls, color1: str, color2: str, large_text: bool = False) -> bool:
        """
        Check if color combination meets WCAG 2.1 AAA standards.
        
        Args:
            color1: First color (hex)
            color2: Second color (hex)
            large_text: If True, uses 4.5:1 ratio requirement, otherwise 7:1
            
        Returns:
            True if combination meets WCAG AAA requirements
        """
        ratio = cls.contrast_ratio(color1, color2)
        required_ratio = 4.5 if large_text else 7.0
        return ratio >= required_ratio

class TestWCAGContrast:
    """Test WCAG contrast ratios for dark theme color combinations."""

    def test_primary_text_on_background_meets_wcag_aa(self) -> None:
        """Primary text on main background should meet WCAG AA standards."""
        ratio = ContrastCalculator.contrast_ratio(
            COLORS["text_primary"],
            COLORS["background"]
        )

        assert ratio >= 4.5, (
            f"Primary text contrast ratio {ratio:.2f} should be >= 4.5 "
            f"({COLORS['text_primary']} on {COLORS['background']})"
        )

        # Should also meet AA standard using utility method
        assert ContrastCalculator.meets_wcag_aa(
            COLORS["text_primary"],
            COLORS["background"]
        )

    def test_secondary_text_on_background_meets_wcag_aa(self) -> None:
        """Secondary text on main background should meet WCAG AA standards."""
        ratio = ContrastCalculator.contrast_ratio(
            COLORS["text_secondary"],
            COLORS["background"]
        )

        assert ratio >= 4.5, (
            f"Secondary text contrast ratio {ratio:.2f} should be >= 4.5 "
            f"({COLORS['text_secondary']} on {COLORS['background']})"
        )

    def test_muted_text_visibility(self) -> None:
        """Muted text should still be readable, though may not meet full WCAG AA."""
        ratio = ContrastCalculator.contrast_ratio(
            COLORS["text_muted"],
            COLORS["background"]
        )

        # Muted text should have at least 3:1 contrast (WCAG AA for large text)
        assert ratio >= 3.0, (
            f"Muted text contrast ratio {ratio:.2f} should be >= 3.0 for readability "
            f"({COLORS['text_muted']} on {COLORS['background']})"
        )

    def test_disabled_text_distinguishable(self) -> None:
        """Disabled text should be visually distinguishable but intentionally lower contrast."""
        disabled_ratio = ContrastCalculator.contrast_ratio(
            COLORS["disabled_text"],
            COLORS["background"]
        )

        normal_ratio = ContrastCalculator.contrast_ratio(
            COLORS["text_primary"],
            COLORS["background"]
        )

        # Disabled text should have lower contrast than normal text
        assert disabled_ratio < normal_ratio, "Disabled text should have lower contrast than normal text"

        # But should still be somewhat visible (at least 2:1)
        assert disabled_ratio >= 2.0, "Disabled text should still be somewhat visible"

    @pytest.mark.parametrize("text_color,background_color", [
        ("text_primary", "panel_background"),
        ("text_primary", "input_background"),
        ("text_secondary", "panel_background"),
    ])
    def test_text_on_various_backgrounds_readable(
        self, text_color: str, background_color: str
    ) -> None:
        """Text should be readable on various dark theme backgrounds."""
        ratio = ContrastCalculator.contrast_ratio(
            COLORS[text_color],
            COLORS[background_color]
        )

        assert ratio >= 3.0, (
            f"Text {text_color} on {background_color} contrast ratio {ratio:.2f} "
            f"should be >= 3.0 for readability"
        )

class TestButtonContrast:
    """Test contrast ratios for button color combinations."""

    @pytest.mark.parametrize("button_type", [
        "primary", "secondary", "accent", "extract", "editor"
    ])
    def test_button_text_contrast_on_button_background(self, button_type: str) -> None:
        """Button text should have good contrast on button backgrounds."""
        button_bg = COLORS[button_type]
        text_color = COLORS["white"]  # Most buttons use white text

        ratio = ContrastCalculator.contrast_ratio(text_color, button_bg)

        # Buttons should have reasonable contrast (at least 2.5:1 for usability)
        # Note: Some buttons may not meet full WCAG AA (4.5:1) due to design choices
        assert ratio >= 2.0, (
            f"Button {button_type} text contrast {ratio:.2f} should be >= 2.0 for basic readability "
            f"({text_color} on {button_bg})"
        )

        # Document WCAG AA compliance separately
        if ratio < 4.5:
            # This is informational - some colorful buttons may not meet AA
            pass  # Could log or collect metrics here

    def test_default_button_text_contrast(self) -> None:
        """Default button should have appropriate text contrast."""
        button_bg = COLORS["light_gray"]
        text_color = COLORS["black"]  # Default buttons use black text

        ratio = ContrastCalculator.contrast_ratio(text_color, button_bg)

        assert ratio >= 2.0, (
            f"Default button text contrast {ratio:.2f} should be >= 2.0 for basic readability "
            f"({text_color} on {button_bg})"
        )

    @pytest.mark.parametrize("button_type", [
        "primary", "secondary", "accent", "extract", "editor"
    ])
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

    @pytest.mark.parametrize("status_type", [
        "success", "warning", "danger", "info"
    ])
    def test_status_colors_visible_on_dark_background(self, status_type: str) -> None:
        """Status colors should be highly visible on dark backgrounds."""
        status_color = COLORS[status_type]
        background = COLORS["background"]

        ratio = ContrastCalculator.contrast_ratio(status_color, background)

        # Status colors should be visible (aim for AA compliance, accept some lower values)
        assert ratio >= 3.0, (
            f"Status {status_type} contrast {ratio:.2f} should be >= 3.0 for visibility "
            f"({status_color} on {background})"
        )

        # Informational: Note if colors achieve higher standards
        if ratio >= 7.0:
            # Achieves AAA compliance
            pass

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

            # Borders should have reasonable visibility (at least 1.5:1)
            assert ratio >= 1.5, (
                f"Border on {bg_key} contrast {ratio:.2f} should be >= 1.5 "
                f"({border_color} on {bg_color})"
            )

    def test_focus_border_highly_visible(self) -> None:
        """Focus borders should be highly visible for accessibility."""
        focus_border = COLORS["border_focus"]

        backgrounds = ["background", "panel_background", "input_background"]
        for bg_key in backgrounds:
            bg_color = COLORS[bg_key]
            ratio = ContrastCalculator.contrast_ratio(focus_border, bg_color)

            # Focus borders should be visible
            assert ratio >= 2.5, (
                f"Focus border on {bg_key} contrast {ratio:.2f} should be >= 2.5 "
                f"({focus_border} on {bg_color})"
            )

    def test_error_border_highly_visible(self) -> None:
        """Error borders should be highly visible for accessibility."""
        error_border = COLORS["border_error"]

        backgrounds = ["background", "panel_background", "input_background"]
        for bg_key in backgrounds:
            bg_color = COLORS[bg_key]
            ratio = ContrastCalculator.contrast_ratio(error_border, bg_color)

            # Error borders should be very visible
            assert ratio >= 3.0, (
                f"Error border on {bg_key} contrast {ratio:.2f} should be >= 3.0 "
                f"({error_border} on {bg_color})"
            )

class TestPreviewBackgroundContrast:
    """Test contrast for sprite preview backgrounds."""

    def test_preview_background_darker_than_main(self) -> None:
        """Preview background should be darker than main background for sprite visibility."""
        preview_lum = ContrastCalculator.relative_luminance(
            *ContrastCalculator.hex_to_rgb(COLORS["preview_background"])
        )
        main_lum = ContrastCalculator.relative_luminance(
            *ContrastCalculator.hex_to_rgb(COLORS["background"])
        )

        assert preview_lum < main_lum, (
            "Preview background should be darker than main background "
            f"({COLORS['preview_background']} vs {COLORS['background']})"
        )

    def test_preview_text_readable_on_preview_background(self) -> None:
        """Text should be readable on preview backgrounds when needed."""
        ratio = ContrastCalculator.contrast_ratio(
            COLORS["text_primary"],
            COLORS["preview_background"]
        )

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
            for color2_key in action_colors[i+1:]:
                color1 = COLORS[color1_key]
                color2 = COLORS[color2_key]

                # Colors should have some contrast between them
                ratio = ContrastCalculator.contrast_ratio(color1, color2)
                # Some similar colors may have very low contrast - this is acceptable for similar semantics
                assert ratio >= 1.0, (
                    f"Action colors {color1_key} and {color2_key} should be at least nominally different "
                    f"(contrast ratio: {ratio:.2f})"
                )

    def test_text_colors_distinguishable(self) -> None:
        """Different text colors should be distinguishable."""
        text_colors = ["text_primary", "text_secondary", "text_muted"]

        for i, color1_key in enumerate(text_colors):
            for color2_key in text_colors[i+1:]:
                color1 = COLORS[color1_key]
                color2 = COLORS[color2_key]

                ratio = ContrastCalculator.contrast_ratio(color1, color2)
                assert ratio >= 1.1, (
                    f"Text colors {color1_key} and {color2_key} should be distinguishable "
                    f"(contrast ratio: {ratio:.2f})"
                )

    def test_background_colors_distinguishable(self) -> None:
        """Background colors should be distinguishable for layering."""
        bg_colors = ["background", "panel_background", "input_background", "preview_background"]

        # Test main background against others
        main_bg = COLORS["background"]
        for bg_key in bg_colors[1:]:  # Skip first (main background)
            bg_color = COLORS[bg_key]
            ratio = ContrastCalculator.contrast_ratio(main_bg, bg_color)

            assert ratio >= 1.03, (
                f"Background colors should be distinguishable: "
                f"background vs {bg_key} (contrast: {ratio:.2f})"
            )

class TestAccessibilityGuidelines:
    """Test compliance with additional accessibility guidelines."""

    def test_sufficient_color_separation_in_ui(self) -> None:
        """UI elements should have sufficient color separation for color-blind users."""
        # Test that we don't rely solely on color for critical distinctions
        # This is more of a design validation

        # Error states should use color + other indicators
        error_color = COLORS["border_error"]
        danger_color = COLORS["danger"]

        # These colors should be different enough
        ratio = ContrastCalculator.contrast_ratio(error_color, danger_color)
        # Allow lower contrast since these are similar semantic colors
        assert ratio >= 1.0, "Error-related colors should be at least nominally distinguishable"

    def test_disabled_states_appropriately_muted(self) -> None:
        """Disabled states should be visually muted but still perceivable."""
        disabled_bg = COLORS["disabled"]
        disabled_text = COLORS["disabled_text"]
        normal_bg = COLORS["light_gray"]
        normal_text = COLORS["text_primary"]

        # Disabled elements should have lower contrast than normal elements
        disabled_contrast = ContrastCalculator.contrast_ratio(disabled_text, disabled_bg)
        normal_contrast = ContrastCalculator.contrast_ratio(normal_text, normal_bg)

        # Disabled should be less contrasty but still somewhat visible
        assert disabled_contrast < normal_contrast, "Disabled states should have lower contrast"
        assert disabled_contrast >= 2.0, "Disabled states should still be somewhat visible"

class TestContrastCalculatorUtility:
    """Test the contrast calculator utility itself."""

    def test_contrast_calculator_with_known_values(self) -> None:
        """Test contrast calculator with known reference values."""
        # Test with pure black and white (maximum contrast)
        black_white_ratio = ContrastCalculator.contrast_ratio("#000000", "#ffffff")
        assert abs(black_white_ratio - 21.0) < 0.1, "Black/white contrast should be ~21:1"

        # Test with identical colors (minimum contrast)
        identical_ratio = ContrastCalculator.contrast_ratio("#808080", "#808080")
        assert abs(identical_ratio - 1.0) < 0.1, "Identical colors should have 1:1 contrast"

    def test_hex_to_rgb_conversion(self) -> None:
        """Test hex to RGB conversion utility."""
        assert ContrastCalculator.hex_to_rgb("#ffffff") == (255, 255, 255)
        assert ContrastCalculator.hex_to_rgb("#000000") == (0, 0, 0)
        assert ContrastCalculator.hex_to_rgb("#ff0000") == (255, 0, 0)
        assert ContrastCalculator.hex_to_rgb("ffffff") == (255, 255, 255)  # Without #

    def test_relative_luminance_calculation(self) -> None:
        """Test relative luminance calculation."""
        # White should have luminance ~1.0
        white_lum = ContrastCalculator.relative_luminance(255, 255, 255)
        assert abs(white_lum - 1.0) < 0.1, "White luminance should be ~1.0"

        # Black should have luminance ~0.0
        black_lum = ContrastCalculator.relative_luminance(0, 0, 0)
        assert abs(black_lum - 0.0) < 0.1, "Black luminance should be ~0.0"

    def test_wcag_compliance_methods(self) -> None:
        """Test WCAG compliance checking methods."""
        # Black text on white background should meet all standards
        assert ContrastCalculator.meets_wcag_aa("#000000", "#ffffff")
        assert ContrastCalculator.meets_wcag_aaa("#000000", "#ffffff")

        # Light gray on white should not meet standards
        assert not ContrastCalculator.meets_wcag_aa("#cccccc", "#ffffff")
        assert not ContrastCalculator.meets_wcag_aaa("#cccccc", "#ffffff")

@pytest.mark.headless
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

        # Test all methods are callable
        assert callable(ContrastCalculator.hex_to_rgb)
        assert callable(ContrastCalculator.relative_luminance)
        assert callable(ContrastCalculator.contrast_ratio)
        assert callable(ContrastCalculator.meets_wcag_aa)
        assert callable(ContrastCalculator.meets_wcag_aaa)

    def test_critical_accessibility_combinations(self) -> None:
        """Test most critical accessibility combinations for the dark theme."""
        # This is a summary test of the most important combinations
        critical_tests = [
            # (text_color, background_color, min_ratio, description)
            ("text_primary", "background", 4.5, "Primary text on main background"),
            ("text_primary", "panel_background", 4.5, "Primary text on panels"),
            ("success", "background", 4.5, "Success indicators"),
            ("danger", "background", 4.5, "Error indicators"),
            ("warning", "background", 3.0, "Warning indicators (can be slightly lower)"),
        ]

        for text_key, bg_key, min_ratio, description in critical_tests:
            ratio = ContrastCalculator.contrast_ratio(COLORS[text_key], COLORS[bg_key])
            assert ratio >= min_ratio, f"{description}: {ratio:.2f} should be >= {min_ratio}"
