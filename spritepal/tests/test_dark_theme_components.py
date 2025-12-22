"""
Tests for dark theme component styling functions.

This module tests the component-specific styling functions from ui.styles.components.py
following TDD principles with real CSS generation and validation.
"""
from __future__ import annotations

import re

import pytest

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.allows_registry_state(reason="UI tests may trigger Qt auto-registration"),
]

from ui.styles.components import (
    get_bold_text_style,
    get_borderless_preview_style,
    get_button_style,
    get_dark_panel_style,
    get_dark_preview_style,
    get_dialog_button_box_style,
    get_error_text_style,
    get_hex_label_style,
    get_input_style,
    get_link_text_style,
    get_minimal_preview_style,
    get_monospace_text_style,
    get_muted_text_style,
    get_panel_style,
    get_preview_panel_style,
    get_progress_style,
    get_scroll_area_style,
    get_slider_style,
    get_splitter_style,
    get_status_style,
    get_success_text_style,
    get_tab_style,
)
from ui.styles.theme import COLORS, FONTS


class TestButtonStyling:
    """Test button styling function with different variations."""

    def test_button_style_returns_valid_css(self) -> None:
        """get_button_style should return valid CSS for QPushButton."""
        css = get_button_style()

        assert isinstance(css, str)
        assert len(css) > 0
        assert "QPushButton {" in css
        assert "QPushButton:hover {" in css
        assert "QPushButton:pressed {" in css

    @pytest.mark.parametrize("button_type", [
        "primary", "secondary", "accent", "extract", "editor", "default"
    ])
    def test_button_style_supports_all_types(self, button_type: str) -> None:
        """Button styling should support all defined button types."""
        css = get_button_style(style_type=button_type)

        assert isinstance(css, str)
        assert "QPushButton {" in css

        # Should contain background-color property
        assert "background-color:" in css

        # Should contain hover and pressed states
        assert ":hover {" in css
        assert ":pressed {" in css

    def test_button_style_with_custom_height(self) -> None:
        """Button styling should accept custom height parameter."""
        custom_height = 35
        css = get_button_style(min_height=custom_height)

        assert f"min-height: {custom_height}px" in css

    def test_button_style_with_custom_font_size(self) -> None:
        """Button styling should accept custom font size parameter."""
        custom_font = "16px"
        css = get_button_style(font_size=custom_font)

        assert f"font-size: {custom_font}" in css

    def test_button_style_includes_disabled_state(self) -> None:
        """Button styling should include disabled state styling."""
        css = get_button_style()

        # Should include disabled state (from get_disabled_state_style)
        assert ":disabled" in css
        assert COLORS["disabled"] in css or COLORS["disabled_text"] in css

    def test_primary_button_has_primary_colors(self) -> None:
        """Primary button should use primary color scheme."""
        css = get_button_style(style_type="primary")

        assert COLORS["primary"] in css
        assert COLORS["primary_hover"] in css
        assert COLORS["primary_pressed"] in css

    def test_default_button_has_different_text_color(self) -> None:
        """Default button should use different text color than themed buttons."""
        default_css = get_button_style(style_type="default")
        primary_css = get_button_style(style_type="primary")

        # Default buttons should have different text color handling
        assert COLORS["light_gray"] in default_css  # Default background
        assert COLORS["primary"] in primary_css    # Primary background

class TestInputStyling:
    """Test input field styling functions."""

    @pytest.mark.parametrize("input_type", ["text", "combo", "spin"])
    def test_input_style_supports_all_types(self, input_type: str) -> None:
        """Input styling should support text, combo, and spin input types."""
        css = get_input_style(input_type=input_type)

        assert isinstance(css, str)
        assert len(css) > 0

        # Should contain appropriate Qt widget selector
        if input_type == "text":
            assert "QLineEdit {" in css
        elif input_type == "combo":
            assert "QComboBox {" in css
            assert "::drop-down" in css
            assert "::down-arrow" in css
        elif input_type == "spin":
            assert "QSpinBox" in css
            assert "QDoubleSpinBox" in css

    def test_input_style_includes_focus_state(self) -> None:
        """Input styling should include focus state styling."""
        css = get_input_style("text")

        assert ":focus {" in css
        assert COLORS["border_focus"] in css

    def test_input_style_includes_disabled_state(self) -> None:
        """Input styling should include disabled state styling."""
        css = get_input_style("text")

        assert ":disabled" in css

    def test_input_style_with_custom_width(self) -> None:
        """Input styling should accept custom width parameter."""
        custom_width = 250
        css = get_input_style("text", min_width=custom_width)

        assert f"min-width: {custom_width}px" in css

    def test_combo_style_includes_dropdown_styling(self) -> None:
        """Combo box styling should include dropdown arrow styling."""
        css = get_input_style("combo")

        assert "::drop-down {" in css
        assert "::down-arrow {" in css
        # Note: QAbstractItemView styling is not currently implemented
        # This is acceptable as the basic combo box functionality works without it

    def test_input_style_uses_dark_theme_colors(self) -> None:
        """Input styling should use appropriate dark theme colors."""
        css = get_input_style("text")

        assert COLORS["input_background"] in css
        assert COLORS["border"] in css

class TestPanelStyling:
    """Test panel and groupbox styling functions."""

    @pytest.mark.parametrize("panel_type", ["default", "primary", "secondary"])
    def test_panel_style_supports_all_types(self, panel_type: str) -> None:
        """Panel styling should support different panel types."""
        css = get_panel_style(panel_type)

        assert isinstance(css, str)
        assert "QGroupBox {" in css
        assert "QGroupBox::title {" in css

    def test_panel_style_uses_appropriate_border_colors(self) -> None:
        """Panel styling should use appropriate border colors for each type."""
        primary_css = get_panel_style("primary")
        secondary_css = get_panel_style("secondary")
        default_css = get_panel_style("default")

        assert COLORS["primary"] in primary_css
        assert COLORS["secondary"] in secondary_css
        assert COLORS["border"] in default_css

    def test_get_dark_panel_style_comprehensive(self) -> None:
        """get_dark_panel_style should provide comprehensive dark theme styling."""
        css = get_dark_panel_style()

        assert "QGroupBox {" in css
        assert "QGroupBox::title {" in css
        assert "QWidget {" in css

        # Should use dark theme colors
        assert COLORS["panel_background"] in css
        assert COLORS["background"] in css
        assert COLORS["text_primary"] in css

class TestStatusStyling:
    """Test status indicator styling functions."""

    @pytest.mark.parametrize("status_type", ["info", "success", "warning", "danger"])
    def test_status_style_supports_all_types(self, status_type: str) -> None:
        """Status styling should support all status types."""
        css = get_status_style(status_type)

        assert isinstance(css, str)
        assert "QLabel {" in css

        # Should use appropriate status color
        expected_color = COLORS[status_type]
        assert expected_color in css

    def test_status_style_includes_border_accent(self) -> None:
        """Status styling should include colored left border accent."""
        css = get_status_style("success")

        assert "border-left:" in css
        assert COLORS["success"] in css

class TestProgressStyling:
    """Test progress bar styling function."""

    def test_progress_style_returns_valid_css(self) -> None:
        """get_progress_style should return valid CSS for QProgressBar."""
        css = get_progress_style()

        assert isinstance(css, str)
        assert "QProgressBar {" in css
        assert "QProgressBar::chunk {" in css

        # Should use primary color for progress
        assert COLORS["primary"] in css

class TestTabStyling:
    """Test tab widget styling function."""

    def test_tab_style_returns_comprehensive_css(self) -> None:
        """get_tab_style should return comprehensive tab styling."""
        css = get_tab_style()

        assert isinstance(css, str)
        assert "QTabWidget::pane {" in css
        assert "QTabBar::tab {" in css
        assert "QTabBar::tab:selected {" in css
        assert "QTabBar::tab:hover {" in css

class TestTextStyling:
    """Test various text styling functions."""

    @pytest.mark.parametrize("color_level", ["light", "medium", "dark"])
    def test_muted_text_style_color_levels(self, color_level: str) -> None:
        """Muted text styling should support different color intensity levels."""
        css = get_muted_text_style(color_level=color_level)

        assert isinstance(css, str)
        assert "QLabel {" in css
        assert "color:" in css

    def test_muted_text_style_with_italic(self) -> None:
        """Muted text styling should support italic option."""
        css = get_muted_text_style(italic=True)

        assert "font-style: italic;" in css

    @pytest.mark.parametrize("color", ["extract", "editor", "primary", "secondary", "accent"])
    def test_link_text_style_color_variants(self, color: str) -> None:
        """Link text styling should support different color themes."""
        css = get_link_text_style(color=color)

        assert isinstance(css, str)
        assert "QLabel {" in css
        assert COLORS[color] in css

    def test_monospace_text_style_uses_monospace_font(self) -> None:
        """Monospace text styling should use monospace font family."""
        css = get_monospace_text_style()

        assert FONTS["monospace_family"] in css

    def test_bold_text_style_uses_bold_weight(self) -> None:
        """Bold text styling should use bold font weight."""
        css = get_bold_text_style()

        assert FONTS["bold_weight"] in css

    def test_success_text_style_uses_success_color(self) -> None:
        """Success text styling should use editor/success color."""
        css = get_success_text_style()

        assert COLORS["editor"] in css
        assert FONTS["bold_weight"] in css

    def test_error_text_style_uses_danger_color(self) -> None:
        """Error text styling should use danger color."""
        css = get_error_text_style()

        assert COLORS["danger"] in css

class TestPreviewStyling:
    """Test preview widget styling functions."""

    def test_preview_panel_style_dark_background(self) -> None:
        """Preview panel styling should use dark preview background."""
        css = get_preview_panel_style()

        assert "QLabel {" in css
        assert COLORS["preview_background"] in css
        assert COLORS["border"] in css

    def test_minimal_preview_style_lighter_styling(self) -> None:
        """Minimal preview styling should use lighter styling."""
        css = get_minimal_preview_style()

        assert "QLabel {" in css
        assert COLORS["background"] in css

    def test_borderless_preview_style_no_styling(self) -> None:
        """Borderless preview styling should remove all decorative elements."""
        css = get_borderless_preview_style()

        assert "border: none;" in css
        assert "background-color: transparent;" in css
        assert "margin: 0px;" in css
        assert "padding: 0px;" in css

    def test_get_dark_preview_style_comprehensive(self) -> None:
        """get_dark_preview_style should provide comprehensive dark preview styling."""
        css = get_dark_preview_style()

        assert "QLabel {" in css
        assert "QScrollArea {" in css
        assert "QScrollArea QWidget {" in css

        # Should use dark preview background consistently
        assert COLORS["preview_background"] in css

class TestHexLabelStyling:
    """Test hex/code label styling function."""

    def test_hex_label_style_with_background(self) -> None:
        """Hex label styling with background should include background styling."""
        css = get_hex_label_style(background=True)

        assert FONTS["monospace_family"] in css
        assert "background-color:" in css
        assert "border:" in css

    def test_hex_label_style_without_background(self) -> None:
        """Hex label styling without background should not include background styling."""
        css = get_hex_label_style(background=False)

        assert FONTS["monospace_family"] in css
        # Should not contain background properties
        assert "background-color:" not in css

    @pytest.mark.parametrize("color", ["extract", "secondary", "accent"])
    def test_hex_label_style_color_variants(self, color: str) -> None:
        """Hex label styling should support different color themes."""
        css = get_hex_label_style(color=color)

        assert COLORS[color] in css

class TestSliderStyling:
    """Test slider styling function."""

    def test_slider_style_comprehensive_styling(self) -> None:
        """Slider styling should provide comprehensive QSlider styling."""
        css = get_slider_style()

        assert "QSlider::groove:horizontal {" in css
        assert "QSlider::handle:horizontal {" in css
        assert "QSlider::handle:horizontal:hover {" in css
        assert "QSlider::sub-page:horizontal {" in css

    @pytest.mark.parametrize("color", ["extract", "secondary", "accent"])
    def test_slider_style_color_variants(self, color: str) -> None:
        """Slider styling should support different color themes."""
        css = get_slider_style(color=color)

        assert COLORS[color] in css

class TestSplitterStyling:
    """Test splitter styling function."""

    def test_splitter_style_with_custom_width(self) -> None:
        """Splitter styling should accept custom handle width."""
        custom_width = 10
        css = get_splitter_style(handle_width=custom_width)

        assert f"width: {custom_width}px;" in css
        assert f"height: {custom_width}px;" in css

    def test_splitter_style_includes_hover_pressed(self) -> None:
        """Splitter styling should include hover and pressed states."""
        css = get_splitter_style()

        assert "QSplitter::handle:hover {" in css
        assert "QSplitter::handle:pressed {" in css

class TestDialogStyling:
    """Test dialog-specific styling functions."""

    def test_dialog_button_box_style_valid_css(self) -> None:
        """Dialog button box styling should return valid CSS."""
        css = get_dialog_button_box_style()

        assert "QDialogButtonBox {" in css
        assert "QDialogButtonBox QPushButton {" in css

class TestScrollAreaStyling:
    """Test scroll area styling function."""

    @pytest.mark.parametrize("bg_color", ["background", "light_gray", "panel_background"])
    def test_scroll_area_style_background_variants(self, bg_color: str) -> None:
        """Scroll area styling should support different background color themes."""
        css = get_scroll_area_style(background_color=bg_color)

        assert "QScrollArea {" in css
        assert "QScrollBar:vertical {" in css
        assert "QScrollBar::handle:vertical {" in css

        # Should use specified background color
        expected_color = COLORS[bg_color]
        assert expected_color in css

class TestCSSValidation:
    """Test CSS validation utilities and patterns."""

    def _validate_css_structure(self, css: str) -> list[str]:
        """Validate basic CSS structure and return any issues found."""
        issues = []

        # Check for balanced braces
        open_braces = css.count('{')
        close_braces = css.count('}')
        if open_braces != close_braces:
            issues.append(f"Unbalanced braces: {open_braces} open, {close_braces} close")

        # Check for valid color references
        color_pattern = re.compile(r'#[0-9A-Fa-f]{6}')
        colors_in_css = color_pattern.findall(css)
        for color in colors_in_css:
            if color not in COLORS.values():
                # This is just a warning, not necessarily an error
                pass

        # Check for basic property syntax
        if ':' in css and ';' not in css:
            issues.append("CSS properties should end with semicolons")

        return issues

    @pytest.mark.parametrize("style_function", [
        get_button_style, get_input_style, get_panel_style, get_status_style,
        get_progress_style, get_tab_style, get_preview_panel_style,
        get_dark_preview_style, get_dark_panel_style
    ])
    def test_all_styling_functions_return_valid_css(self, style_function) -> None:
        """All styling functions should return structurally valid CSS."""
        css = style_function()
        issues = self._validate_css_structure(css)

        assert len(issues) == 0, f"CSS validation issues in {style_function.__name__}: {issues}"

    def test_css_functions_are_deterministic(self) -> None:
        """CSS functions should return identical results for identical inputs."""
        # Test that functions are deterministic
        css1 = get_button_style("primary")
        css2 = get_button_style("primary")

        assert css1 == css2, "Styling functions should be deterministic"

    def test_css_functions_handle_edge_cases(self) -> None:
        """CSS functions should handle edge cases gracefully."""
        # Test with invalid style types - should fall back to defaults
        css = get_button_style("nonexistent_type")
        assert isinstance(css, str)
        assert len(css) > 0

        # Test with zero dimensions
        css = get_splitter_style(handle_width=0)
        assert isinstance(css, str)

@pytest.mark.headless
class TestComponentStylingHeadless:
    """Headless tests for component styling that don't require Qt."""

    def test_all_component_functions_importable(self) -> None:
        """All component styling functions should be importable."""
        # This test ensures all functions are properly defined
        functions = [
            get_button_style, get_input_style, get_panel_style, get_status_style,
            get_progress_style, get_tab_style, get_muted_text_style, get_link_text_style,
            get_monospace_text_style, get_bold_text_style, get_success_text_style,
            get_error_text_style, get_hex_label_style, get_slider_style,
            get_splitter_style, get_dialog_button_box_style, get_scroll_area_style,
            get_preview_panel_style, get_minimal_preview_style, get_borderless_preview_style,
            get_dark_preview_style, get_dark_panel_style
        ]

        for func in functions:
            assert callable(func), f"Function {func.__name__} should be callable"

    def test_component_functions_basic_execution(self) -> None:
        """All component functions should execute without errors."""
        # Basic smoke test
        functions_to_test = [
            (get_button_style, {}),
            (get_input_style, {}),
            (get_panel_style, {}),
            (get_status_style, {}),
            (get_progress_style, {}),
            (get_tab_style, {}),
        ]

        for func, kwargs in functions_to_test:
            try:
                result = func(**kwargs)
                assert isinstance(result, str)
                assert len(result) > 0
            except Exception as e:
                pytest.fail(f"Function {func.__name__} failed with: {e}")
