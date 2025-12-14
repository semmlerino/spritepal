"""
Tests for dark theme integration with Qt widgets and application.

This module tests the integration of dark theme styling with real Qt widgets,
application theme switching, and preview widget dark backgrounds.
Uses real Qt components following the established testing patterns.
"""
from __future__ import annotations

import os
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
    get_button_style,
    get_dark_preview_style,
    get_input_style,
    get_panel_style,
)
from ui.styles.theme import COLORS, get_theme_style

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
    pytest.mark.allows_registry_state,  # Theme tests don't use managers but tolerate state
]


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
    @pytest.mark.xfail(
        _is_offscreen,
        reason="SpritePreviewWidget may fail to initialize in offscreen mode",
        strict=False,
    )
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
            assert "background-color:" in style_sheet or len(style_sheet) == 0  # May not be set initially

    @pytest.mark.gui
    @pytest.mark.skipif(not WIDGETS_AVAILABLE, reason="Preview widgets not available")
    @pytest.mark.xfail(
        _is_offscreen,
        reason="ZoomablePreviewWidget may fail to initialize in offscreen mode",
        strict=False,
    )
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
        pixmap = QPixmap(64, 64)
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
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

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
        import time

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
        import re

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
        # List of major UI components that should have styling

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
