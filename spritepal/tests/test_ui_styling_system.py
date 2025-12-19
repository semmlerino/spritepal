"""
Tests for the centralized UI styling system

from ui.styles import get_button_style, get_input_style, get_muted_text_style, get_panel_style

from ui.styles import get_button_style, get_input_style, get_muted_text_style, get_panel_style

from ui.styles import get_button_style, get_input_style, get_muted_text_style, get_panel_style

from ui.styles import get_button_style, get_input_style, get_muted_text_style, get_panel_style
"""
from __future__ import annotations

import pytest

from ui.styles import (
    # Systematic pytest markers applied based on test content analysis
    COLORS,
    DIMENSIONS,
    get_dialog_button_box_style,
    get_scroll_area_style,
    get_splitter_style,
)

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]
class TestStylingSystemFunctions:
    """Test the new styling functions added in Phase 1"""

    def test_get_splitter_style_default(self):
        """Test splitter style with default parameters"""
        css = get_splitter_style()

        # Should contain splitter handle styling
        assert "QSplitter::handle" in css
        assert "QSplitter::handle:hover" in css
        assert "QSplitter::handle:pressed" in css

        # Should use theme colors
        assert COLORS["border"] in css
        assert COLORS["gray"] in css
        assert COLORS["dark_gray"] in css

        # Should use default width of 8px
        assert "width: 8px" in css
        assert "height: 8px" in css

    def test_get_splitter_style_custom_width(self):
        """Test splitter style with custom handle width"""
        css = get_splitter_style(handle_width=12)

        # Should use custom width
        assert "width: 12px" in css
        assert "height: 12px" in css

    def test_get_dialog_button_box_style(self):
        """Test dialog button box styling"""
        css = get_dialog_button_box_style()

        # Should contain button box styling
        assert "QDialogButtonBox" in css
        assert "QDialogButtonBox QPushButton" in css

        # Should use theme dimensions
        assert f"min-height: {DIMENSIONS['button_height']}px" in css
        assert f"padding: {DIMENSIONS['spacing_md']}px 0" in css

        # Should have border radius
        assert f"border-radius: {DIMENSIONS['border_radius']}px" in css

    def test_get_scroll_area_style_default(self):
        """Test scroll area style with default background"""
        css = get_scroll_area_style()

        # Should contain scroll area and scrollbar styling
        assert "QScrollArea" in css
        assert "QScrollBar:vertical" in css
        assert "QScrollBar::handle:vertical" in css
        assert "QScrollBar::handle:vertical:hover" in css

        # Should use default background color
        assert COLORS["background"] in css
        assert COLORS["border"] in css

    def test_get_scroll_area_style_custom_background(self):
        """Test scroll area style with custom background"""
        css = get_scroll_area_style("light_gray")

        # Should use light gray background
        assert COLORS["light_gray"] in css

    def test_get_scroll_area_style_invalid_background(self):
        """Test scroll area style with invalid background falls back to default"""
        css = get_scroll_area_style("invalid_color")

        # Should fall back to default background
        assert COLORS["background"] in css

    def test_styling_functions_return_strings(self):
        """Test that all styling functions return non-empty strings"""
        functions = [
            get_splitter_style,
            get_dialog_button_box_style,
            get_scroll_area_style,
        ]

        for func in functions:
            result = func()
            assert isinstance(result, str)
            assert len(result) > 0
            assert result.strip()  # Should not be just whitespace

    def test_css_output_well_formed(self):
        """Test that CSS output is well-formed with proper braces"""
        css_outputs = [
            get_splitter_style(),
            get_dialog_button_box_style(),
            get_scroll_area_style(),
        ]

        for css in css_outputs:
            # Count braces - should be balanced
            open_braces = css.count("{")
            close_braces = css.count("}")
            assert open_braces == close_braces, f"Unbalanced braces in CSS: {css[:100]}..."

            # Should not have empty selectors
            assert not css.startswith("{")
            assert "{}" not in css

    def test_theme_constants_used_consistently(self):
        """Test that styling functions use theme constants consistently"""
        css_outputs = [
            get_splitter_style(),
            get_dialog_button_box_style(),
            get_scroll_area_style(),
        ]

        # Get all valid theme colors to allow
        valid_colors = set(COLORS.values())

        for css in css_outputs:
            # Should not contain hardcoded colors that aren't in theme
            lines = [line.strip() for line in css.split("\n") if line.strip()]
            for line in lines:
                if not line.startswith("/*") and ":" in line and "#" in line:
                    # Extract color value
                    value_part = line.split(":")[1].strip()
                    # Find hex colors in the value
                    import re
                    hex_colors = re.findall(r"#[0-9a-fA-F]{6}", value_part)
                    for hex_color in hex_colors:
                        assert hex_color in valid_colors, f"Hardcoded color not in theme: {hex_color} in line: {line}"

class TestStylingSystemIntegration:
    """Test styling system integration"""

    def test_new_styling_functions_available_in_main_import(self):
        """Test that new functions are available from main styles import"""
        # Test that we can import all new functions
        from ui.styles import (
            get_dialog_button_box_style,
            get_scroll_area_style,
            get_splitter_style,
        )

        # All should be callable
        assert callable(get_splitter_style)
        assert callable(get_dialog_button_box_style)
        assert callable(get_scroll_area_style)

    def test_styling_system_backwards_compatibility(self):
        """Test that existing styling functions still work"""
        from ui.styles import (
            get_button_style,
            get_input_style,
            get_muted_text_style,
            get_panel_style,
        )

        # All existing functions should still work
        functions = [
            get_button_style,
            get_input_style,
            get_panel_style,
            get_muted_text_style,
        ]

        for func in functions:
            result = func()
            assert isinstance(result, str)
            assert len(result) > 0

class TestRealWorldUsage:
    """Test styling functions in realistic usage scenarios"""

    def test_splitter_style_in_dialog_context(self):
        """Test splitter style works in dialog context"""
        # Simulate usage in RowArrangementDialog
        main_splitter_css = get_splitter_style(8)
        content_splitter_css = get_splitter_style(8)

        # Both should be identical and well-formed
        assert main_splitter_css == content_splitter_css
        assert "QSplitter::handle" in main_splitter_css

    def test_dialog_button_box_realistic_usage(self):
        """Test dialog button box style in realistic scenario"""
        # Simulate usage across multiple dialogs
        error_dialog_css = get_dialog_button_box_style()
        row_dialog_css = get_dialog_button_box_style()
        grid_dialog_css = get_dialog_button_box_style()

        # All should be identical (consistent styling)
        assert error_dialog_css == row_dialog_css == grid_dialog_css

    def test_scroll_area_different_contexts(self):
        """Test scroll area style in different contexts"""
        # Different background contexts
        default_css = get_scroll_area_style()
        light_css = get_scroll_area_style("light_gray")
        panel_css = get_scroll_area_style("panel_background")

        # Should all be valid but different
        assert default_css != light_css != panel_css
        assert "QScrollArea" in default_css
        assert "QScrollArea" in light_css
        assert "QScrollArea" in panel_css
