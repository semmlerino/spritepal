"""
Unit tests for dark theme constants, CSS generation, and accessibility.

Headless validation tests that don't require Qt widgets.
Split from tests/integration/test_ui_styling.py - Qt widget tests remain there.
"""

from __future__ import annotations

import re

import pytest

from ui.styles.components import (
    get_button_style,
    get_input_style,
    get_panel_style,
    get_progress_style,
    get_scroll_area_style,
    get_splitter_style,
    get_status_style,
    get_tab_style,
)
from ui.styles.theme import (
    COLORS,
    DIMENSIONS,
    FONTS,
    Theme,
    get_disabled_state_style,
    get_theme_style,
)

pytestmark = [
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


# =============================================================================
# Theme Constants & Accessibility
# =============================================================================


class TestThemeConstants:
    """Test dark theme constants and basic accessibility requirements."""

    def test_colors_are_valid_and_present(self) -> None:
        """All color constants should be valid hex codes and essential keys must exist."""
        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        required_colors = ["primary", "background", "text_primary", "border", "success", "danger"]

        for color in required_colors:
            assert color in COLORS, f"Required color '{color}' is missing"
            assert hex_pattern.match(COLORS[color]), f"Color {color} is invalid hex"

    def test_theme_class_mapping(self) -> None:
        """Theme class should provide correct mapping to COLORS dictionary."""
        assert COLORS["primary"] == Theme.PRIMARY
        assert COLORS["background"] == Theme.BACKGROUND
        assert COLORS["text_primary"] == Theme.TEXT
        assert COLORS["border"] == Theme.BORDER

    def test_font_and_dimension_validity(self) -> None:
        """Font and dimension constants should have reasonable values."""
        assert "default_size" in FONTS
        assert FONTS["default_size"].endswith("px")
        assert DIMENSIONS["spacing_md"] > 0
        assert 20 <= DIMENSIONS["button_height"] <= 50

    def test_critical_accessibility_contrast(self) -> None:
        """Critical UI combinations must meet minimum contrast requirements."""
        # text_primary on background should meet WCAG AA (4.5:1)
        ratio = ContrastCalculator.contrast_ratio(COLORS["text_primary"], COLORS["background"])
        assert ratio >= 4.5

        # status colors should be visible on background (3.0:1)
        for status in ["success", "danger", "warning"]:
            ratio = ContrastCalculator.contrast_ratio(COLORS[status], COLORS["background"])
            assert ratio >= 3.0


# =============================================================================
# CSS Generation
# =============================================================================


class TestCSSGeneration:
    """Test CSS generation functions for various UI components."""

    @pytest.mark.parametrize(
        "style_func,selector",
        [
            (get_theme_style, "QWidget"),
            (get_button_style, "QPushButton"),
            (get_input_style, "QLineEdit"),
            (get_panel_style, "QGroupBox"),
            (get_status_style, "QLabel"),
            (get_tab_style, "QTabWidget"),
            (get_progress_style, "QProgressBar"),
            (get_scroll_area_style, "QScrollArea"),
            (get_splitter_style, "QSplitter"),
        ],
    )
    def test_style_functions_return_valid_css(self, style_func, selector) -> None:
        """Styling functions should return non-empty strings containing expected selectors."""
        css = style_func()
        assert isinstance(css, str)
        assert len(css) > 0
        assert selector in css
        assert css.count("{") == css.count("}")

    def test_button_style_variants(self) -> None:
        """Button style should support variants and custom dimensions."""
        primary_css = get_button_style("primary")
        assert COLORS["primary"] in primary_css

        custom_css = get_button_style(min_height=42)
        assert "min-height: 42px" in custom_css

    def test_disabled_state_style(self) -> None:
        """Disabled state styling should be available and valid."""
        css = get_disabled_state_style()
        assert ":disabled" in css
        assert COLORS["disabled_text"] in css

    def test_css_functions_are_deterministic(self) -> None:
        """CSS generation should be consistent across identical calls."""
        assert get_theme_style() == get_theme_style()
        assert get_button_style("primary") == get_button_style("primary")


# =============================================================================
# Headless Validation
# =============================================================================


@pytest.mark.headless
def test_theme_completeness_headless() -> None:
    """Ensure all major theme components are reachable in headless mode."""
    assert len(COLORS) > 10
    assert len(FONTS) > 5
    assert len(get_theme_style()) > 1000
    assert "QWidget" in get_theme_style()
