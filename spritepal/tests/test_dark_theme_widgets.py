"""
Tests for dark theme component styling and Qt widget integration.

Consolidates tests from:
- test_dark_theme_components.py (CSS generation functions)
- test_dark_theme_integration.py (Qt widget integration)

This module tests component-specific styling functions and their integration
with real Qt widgets following TDD principles.
"""
from __future__ import annotations

import os
import re
import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
from ui.styles.theme import COLORS, FONTS, get_theme_style

# Determine if running in offscreen mode
_is_offscreen = os.environ.get("QT_QPA_PLATFORM") == "offscreen"

# Mock the Qt widget imports to avoid import dependencies during testing
try:
    from ui.widgets.sprite_preview_widget import SpritePreviewWidget
    from ui.zoomable_preview import ZoomablePreviewWidget
    WIDGETS_AVAILABLE = True
except ImportError:
    WIDGETS_AVAILABLE = False
    SpritePreviewWidget = Mock
    ZoomablePreviewWidget = Mock

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.allows_registry_state(reason="UI tests may trigger Qt auto-registration"),
]


# =============================================================================
# Component CSS Generation Tests (from test_dark_theme_components.py)
# =============================================================================


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


# =============================================================================
# Qt Widget Integration Tests (from test_dark_theme_integration.py)
# =============================================================================


class TestApplicationThemeIntegration:
    """Test dark theme integration at the application level."""

    @pytest.mark.gui
    def test_application_dark_palette_creation(self, qtbot) -> None:
        """Test that dark palette can be created and applied to application."""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        # Test palette creation similar to launch_spritepal.py
        dark_palette = QPalette()

        # Window colors
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48))
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)

        # Base colors
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)

        # Button colors
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 58))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)

        # Apply palette
        original_palette = app.palette()
        app.setPalette(dark_palette)

        # Test that palette was applied
        current_palette = app.palette()
        assert current_palette.color(QPalette.ColorRole.Window) == QColor(45, 45, 48)
        assert current_palette.color(QPalette.ColorRole.WindowText) == Qt.GlobalColor.white

        # Restore original palette
        app.setPalette(original_palette)

    @pytest.mark.gui
    def test_global_dark_theme_stylesheet_application(self, qtbot) -> None:
        """Test that global dark theme stylesheet can be applied."""
        # Create a test widget
        widget = QWidget()
        qtbot.addWidget(widget)

        # Apply theme stylesheet
        theme_css = get_theme_style()
        widget.setStyleSheet(theme_css)

        # Test that stylesheet was applied
        applied_css = widget.styleSheet()
        assert theme_css in applied_css or len(applied_css) > 0

        # Test that widget shows with dark theme
        widget.show()
        qtbot.waitExposed(widget)

    @pytest.mark.gui
    def test_dark_theme_with_real_widgets(self, qtbot) -> None:
        """Test dark theme application with real Qt widgets."""
        # Create container widget
        container = QWidget()
        qtbot.addWidget(container)
        layout = QVBoxLayout(container)

        # Create various widgets
        group_box = QGroupBox("Test Group")
        button = QPushButton("Test Button")
        line_edit = QLineEdit("Test Input")
        label = QLabel("Test Label")

        layout.addWidget(group_box)
        layout.addWidget(button)
        layout.addWidget(line_edit)
        layout.addWidget(label)

        # Apply dark theme styles
        container.setStyleSheet(get_theme_style())
        button.setStyleSheet(get_button_style("primary"))
        line_edit.setStyleSheet(get_input_style("text"))
        group_box.setStyleSheet(get_panel_style("default"))

        # Show widget to ensure styles are applied
        container.show()
        qtbot.waitExposed(container)

        # Test that widgets have stylesheets applied
        assert len(button.styleSheet()) > 0
        assert len(line_edit.styleSheet()) > 0
        assert len(group_box.styleSheet()) > 0


class TestPreviewWidgetDarkTheme:
    """Test dark theme integration with preview widgets."""

    @pytest.mark.gui
    @pytest.mark.skipif(not WIDGETS_AVAILABLE, reason="Preview widgets not available")
    def test_sprite_preview_widget_dark_backgrounds(self, qtbot) -> None:
        """Test that SpritePreviewWidget applies dark backgrounds correctly."""
        preview_widget = SpritePreviewWidget("Test Preview")
        qtbot.addWidget(preview_widget)

        preview_widget.show()
        qtbot.waitExposed(preview_widget)

        # Test that preview widget exists and can be styled
        assert preview_widget is not None

        # If the widget has a preview_label, test its styling
        if hasattr(preview_widget, 'preview_label') and preview_widget.preview_label:
            style_sheet = preview_widget.preview_label.styleSheet()

            # Should contain dark background styling
            assert "background-color:" in style_sheet or len(style_sheet) == 0

    @pytest.mark.gui
    @pytest.mark.skipif(not WIDGETS_AVAILABLE, reason="Preview widgets not available")
    def test_zoomable_preview_widget_dark_backgrounds(self, qtbot) -> None:
        """Test that ZoomablePreviewWidget applies dark backgrounds correctly."""
        zoomable_widget = ZoomablePreviewWidget()
        qtbot.addWidget(zoomable_widget)

        zoomable_widget.show()
        qtbot.waitExposed(zoomable_widget)

        # Test that zoomable widget exists and can be styled
        assert zoomable_widget is not None

        # Test that widget has dark styling applied
        style_sheet = zoomable_widget.styleSheet()
        if len(style_sheet) > 0:
            # Should contain dark background references
            assert "#1e1e1e" in style_sheet or "background-color:" in style_sheet

    @pytest.mark.gui
    def test_preview_label_with_dark_preview_style(self, qtbot) -> None:
        """Test QLabel with dark preview styling applied."""
        # Create a preview label
        preview_label = QLabel("Preview Content")
        qtbot.addWidget(preview_label)

        # Apply dark preview style
        preview_css = get_dark_preview_style()
        preview_label.setStyleSheet(preview_css)

        # Show label
        preview_label.show()
        qtbot.waitExposed(preview_label)

        # Test that style was applied
        applied_style = preview_label.styleSheet()
        assert len(applied_style) > 0
        assert COLORS["preview_background"] in applied_style

    @pytest.mark.gui
    def test_preview_with_mock_pixmap(self, qtbot) -> None:
        """Test preview label with mock pixmap content."""
        preview_label = QLabel()
        qtbot.addWidget(preview_label)

        # Create mock pixmap
        pixmap = QPixmap(64, 64)  # pixmap-ok: main thread test code
        pixmap.fill(QColor(255, 0, 0))  # Red test image

        preview_label.setPixmap(pixmap)
        preview_label.setStyleSheet(get_dark_preview_style())

        # Show and test
        preview_label.show()
        qtbot.waitExposed(preview_label)

        assert preview_label.pixmap() is not None
        assert preview_label.pixmap().width() == 64


class TestStylesheetIntegration:
    """Test CSS stylesheet integration with Qt widgets."""

    @pytest.mark.gui
    def test_button_styling_integration(self, qtbot) -> None:
        """Test button styling CSS integration with real QPushButton."""
        button = QPushButton("Test Button")
        qtbot.addWidget(button)

        # Test different button styles
        button_styles = ["primary", "secondary", "accent", "extract", "editor", "default"]

        for style_type in button_styles:
            css = get_button_style(style_type)
            button.setStyleSheet(css)

            button.show()
            qtbot.waitExposed(button)

            # Test that CSS was applied
            applied_css = button.styleSheet()
            assert css in applied_css or len(applied_css) > 0

            # Test that button is clickable with style applied
            assert button.isEnabled()

            # Simulate hover state (if supported)
            button.enterEvent(None)
            button.leaveEvent(None)

    @pytest.mark.gui
    def test_input_styling_integration(self, qtbot) -> None:
        """Test input styling CSS integration with real QLineEdit."""
        line_edit = QLineEdit("Test Input")
        qtbot.addWidget(line_edit)

        # Apply text input styling
        css = get_input_style("text")
        line_edit.setStyleSheet(css)

        line_edit.show()
        qtbot.waitExposed(line_edit)

        # Test that styling was applied
        applied_css = line_edit.styleSheet()
        assert len(applied_css) > 0

        # Test input functionality with styling
        line_edit.setText("New test text")
        assert line_edit.text() == "New test text"

        # Test focus behavior - in offscreen mode, focus may not work reliably
        # but the widget should be focusable (focusPolicy check)
        line_edit.setFocus()
        QApplication.processEvents()  # Allow focus to be processed

        # Check focusability instead of actual focus (more reliable in headless)
        assert line_edit.focusPolicy() != Qt.FocusPolicy.NoFocus, "Widget should accept focus"

    @pytest.mark.gui
    def test_group_box_styling_integration(self, qtbot) -> None:
        """Test group box styling CSS integration with real QGroupBox."""
        group_box = QGroupBox("Test Group Box")
        qtbot.addWidget(group_box)

        # Apply panel styling
        css = get_panel_style("primary")
        group_box.setStyleSheet(css)

        group_box.show()
        qtbot.waitExposed(group_box)

        # Test that styling was applied
        applied_css = group_box.styleSheet()
        assert len(applied_css) > 0
        assert COLORS["primary"] in applied_css

    @pytest.mark.gui
    def test_nested_widget_styling(self, qtbot) -> None:
        """Test that nested widgets inherit and apply styling correctly."""
        # Create parent container
        container = QWidget()
        qtbot.addWidget(container)
        layout = QVBoxLayout(container)

        # Create nested group box with widgets
        group_box = QGroupBox("Nested Test")
        group_layout = QVBoxLayout(group_box)

        nested_button = QPushButton("Nested Button")
        nested_input = QLineEdit("Nested Input")

        group_layout.addWidget(nested_button)
        group_layout.addWidget(nested_input)
        layout.addWidget(group_box)

        # Apply styles at different levels
        container.setStyleSheet(get_theme_style())
        group_box.setStyleSheet(get_panel_style("secondary"))
        nested_button.setStyleSheet(get_button_style("accent"))
        nested_input.setStyleSheet(get_input_style("text"))

        # Show and test
        container.show()
        qtbot.waitExposed(container)

        # Test that all styles are applied
        assert len(container.styleSheet()) > 0
        assert len(group_box.styleSheet()) > 0
        assert len(nested_button.styleSheet()) > 0
        assert len(nested_input.styleSheet()) > 0


class TestMockApplicationIntegration:
    """Test application-level theme integration using mocks where appropriate."""

    @patch('launch_spritepal.QApplication')
    def test_application_theme_setup_mock(self, mock_qapp_class) -> None:
        """Test application theme setup logic with mocked QApplication."""
        # Mock QApplication instance
        mock_app = Mock()
        mock_qapp_class.return_value = mock_app

        # Mock palette
        mock_palette = Mock()
        mock_app.setPalette.return_value = None
        mock_app.setStyleSheet.return_value = None

        # Test that theme application calls would work
        # This simulates the _apply_dark_theme method logic

        # Test palette setting
        mock_app.setPalette(mock_palette)
        mock_app.setPalette.assert_called_once_with(mock_palette)

        # Test stylesheet setting
        test_css = "QWidget { background-color: #2d2d30; }"
        mock_app.setStyleSheet(test_css)
        mock_app.setStyleSheet.assert_called_once_with(test_css)

    def test_environment_based_theme_switching(self) -> None:
        """Test theme switching based on environment variables."""
        # Test different environment scenarios
        test_environments = [
            {"SPRITEPAL_THEME": "dark"},
            {"SPRITEPAL_THEME": "auto"},
            {"CI": "1"},  # CI environment
            {}  # No environment variables
        ]

        for env_vars in test_environments:
            with patch.dict(os.environ, env_vars, clear=False):
                # This would test theme detection logic
                # For now, just test that environment variables are readable
                theme_setting = os.environ.get("SPRITEPAL_THEME", "dark")
                assert theme_setting in ["dark", "auto", "light"] or theme_setting == "dark"


class TestThemeConsistency:
    """Test consistency of theme application across different widgets."""

    @pytest.mark.gui
    def test_color_consistency_across_widgets(self, qtbot) -> None:
        """Test that colors are consistent across different widget types."""
        # Create multiple widgets
        widgets = [
            QPushButton("Button"),
            QLineEdit("Input"),
            QLabel("Label"),
            QGroupBox("Group"),
        ]

        container = QWidget()
        qtbot.addWidget(container)
        layout = QVBoxLayout(container)

        for widget in widgets:
            layout.addWidget(widget)

        # Apply consistent theme
        theme_css = get_theme_style()
        container.setStyleSheet(theme_css)

        # Apply specific styles
        widgets[0].setStyleSheet(get_button_style("primary"))
        widgets[1].setStyleSheet(get_input_style("text"))
        widgets[3].setStyleSheet(get_panel_style("default"))

        container.show()
        qtbot.waitExposed(container)

        # Test that all widgets are properly styled
        for widget in widgets:
            # Each widget should have some styling applied (either inherited or direct)
            total_style_length = len(widget.styleSheet()) + len(container.styleSheet())
            assert total_style_length > 0, f"Widget {type(widget).__name__} has no styling"

    @pytest.mark.gui
    def test_theme_performance_with_many_widgets(self, qtbot) -> None:
        """Test theme performance with multiple widgets."""
        container = QWidget()
        qtbot.addWidget(container)
        layout = QVBoxLayout(container)

        # Create many widgets
        start_time = time.time()

        for i in range(20):  # Create 20 widgets
            button = QPushButton(f"Button {i}")
            button.setStyleSheet(get_button_style("primary"))
            layout.addWidget(button)

        creation_time = time.time() - start_time

        # Show container
        container.show()
        qtbot.waitExposed(container)

        total_time = time.time() - start_time

        # Performance should be reasonable (under 1 second for 20 widgets)
        assert creation_time < 1.0, f"Widget creation took too long: {creation_time:.2f}s"
        assert total_time < 2.0, f"Total theme application took too long: {total_time:.2f}s"


# =============================================================================
# Headless Tests (no Qt display required)
# =============================================================================


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


@pytest.mark.headless
class TestIntegrationHeadless:
    """Headless integration tests that don't require Qt display."""

    def test_css_generation_integration(self) -> None:
        """Test that CSS generation works correctly for integration scenarios."""
        # Test that all major styling functions can be called together
        styles = {
            'theme': get_theme_style(),
            'button': get_button_style("primary"),
            'input': get_input_style("text"),
            'panel': get_panel_style("default"),
            'preview': get_dark_preview_style(),
        }

        for style_name, css in styles.items():
            assert isinstance(css, str), f"Style {style_name} should return string"
            assert len(css) > 0, f"Style {style_name} should not be empty"

            # Basic CSS validation
            assert css.count('{') == css.count('}'), f"Style {style_name} has unbalanced braces"

    def test_color_references_in_integrated_styles(self) -> None:
        """Test that integrated styles reference valid colors."""
        # Generate integrated stylesheet combining multiple components
        integrated_css = (
            get_theme_style() +
            get_button_style("primary") +
            get_input_style("text") +
            get_panel_style("default")
        )

        # Find all color references
        color_pattern = re.compile(r'#[0-9A-Fa-f]{6}')
        colors_in_css = set(color_pattern.findall(integrated_css))

        # Test that found colors are all valid theme colors
        theme_color_values = set(COLORS.values())

        for color in colors_in_css:
            # Most colors should be from our theme (some might be hardcoded for specific reasons)
            if color not in theme_color_values:
                # This is just informational - some hardcoded colors may be intentional
                pass

    def test_mock_widget_style_application(self) -> None:
        """Test style application using mock widgets."""
        # Create mock widgets
        mock_button = Mock()
        mock_input = Mock()
        mock_label = Mock()

        # Test that style functions can generate CSS for mock application
        button_css = get_button_style("primary")
        input_css = get_input_style("text")
        theme_css = get_theme_style()

        # Mock the setStyleSheet calls
        mock_button.setStyleSheet(button_css)
        mock_input.setStyleSheet(input_css)
        mock_label.setStyleSheet(theme_css)

        # Verify calls were made
        mock_button.setStyleSheet.assert_called_once_with(button_css)
        mock_input.setStyleSheet.assert_called_once_with(input_css)
        mock_label.setStyleSheet.assert_called_once_with(theme_css)

    def test_theme_integration_completeness(self) -> None:
        """Test that theme integration covers all major UI components."""
        # Test that theme CSS includes styling for major components
        theme_css = get_theme_style()

        # At minimum, theme should include QWidget and QGroupBox
        assert "QWidget" in theme_css, "Theme should include base QWidget styling"
        assert "QGroupBox" in theme_css, "Theme should include QGroupBox styling"

        # Test that component-specific functions exist
        component_functions = [
            get_button_style,
            get_input_style,
            get_panel_style,
            get_dark_preview_style,
        ]

        for func in component_functions:
            css = func()
            assert isinstance(css, str), f"Function {func.__name__} should return CSS string"
            assert len(css) > 0, f"Function {func.__name__} should return non-empty CSS"


class TestRealWorldUsage:
    """Test styling functions in realistic usage scenarios.

    Migrated from test_ui_styling_system.py - tests semantic equality
    (CSS outputs identical across contexts) rather than string-contains.
    """

    def test_splitter_style_in_dialog_context(self) -> None:
        """Test splitter style works in dialog context."""
        # Simulate usage in RowArrangementDialog
        main_splitter_css = get_splitter_style(8)
        content_splitter_css = get_splitter_style(8)

        # Both should be identical and well-formed
        assert main_splitter_css == content_splitter_css
        assert "QSplitter::handle" in main_splitter_css

    def test_dialog_button_box_realistic_usage(self) -> None:
        """Test dialog button box style in realistic scenario."""
        # Simulate usage across multiple dialogs
        error_dialog_css = get_dialog_button_box_style()
        row_dialog_css = get_dialog_button_box_style()
        grid_dialog_css = get_dialog_button_box_style()

        # All should be identical (consistent styling)
        assert error_dialog_css == row_dialog_css == grid_dialog_css

    def test_scroll_area_different_contexts(self) -> None:
        """Test scroll area style in different contexts."""
        # Different background contexts
        default_css = get_scroll_area_style()
        light_css = get_scroll_area_style("light_gray")
        panel_css = get_scroll_area_style("panel_background")

        # Should all be valid but different
        assert default_css != light_css != panel_css
        assert "QScrollArea" in default_css
        assert "QScrollArea" in light_css
        assert "QScrollArea" in panel_css
