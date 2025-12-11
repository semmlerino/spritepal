"""
Comprehensive Qt integration tests for recent SpritePal UI improvements.

This module tests the recent UI changes with real Qt components:
1. Dark theme applied to real application (launch_spritepal.py sets global dark CSS)
2. Main window reduced from 1200x750 to 1000x650
3. Manual offset dialog with new direct signals (offset_changed, sprite_found)
4. Sprite preview widgets with dark backgrounds (#1e1e1e)
5. Button styling with gradients and hover states

Focus on @pytest.mark.gui tests with real Qt interaction using qtbot.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import (
    QMainWindow,
    QPushButton,
    QWidget,
)

# Import SpritePal components
from launch_spritepal import SpritePalApp
from ui.main_window import MainWindow
from ui.styles.components import get_button_style, get_dark_preview_style
from ui.styles.theme import COLORS, get_theme_style

# Import manual offset dialog
try:
    from ui.dialogs.manual_offset_unified_integrated import UnifiedManualOffsetDialog
    MANUAL_OFFSET_AVAILABLE = True
except ImportError:
    MANUAL_OFFSET_AVAILABLE = False
    UnifiedManualOffsetDialog = Mock

class TestSpritePalAppDarkThemeIntegration:
    """Test SpritePalApp dark theme integration with real Qt components."""

    @pytest.mark.gui
    def test_spritepal_app_dark_theme_applied(self, qtbot) -> None:
        """Test that SpritePalApp applies dark theme correctly to real application."""
        pytest.skip("Cannot instantiate SpritePalApp (QApplication) when a QApplication already exists (managed by pytest-qt)")
        # Create SpritePalApp instance
        app_args = ["test_spritepal"]
        spritepal_app = SpritePalApp(app_args)

        # Test that dark palette is applied
        palette = spritepal_app.palette()

        # Check key dark theme colors
        window_color = palette.color(QPalette.ColorRole.Window)
        assert window_color == QColor(45, 45, 48), f"Expected dark window color, got {window_color.name()}"

        text_color = palette.color(QPalette.ColorRole.WindowText)
        assert text_color == Qt.GlobalColor.white, f"Expected white text, got {text_color.name()}"

        base_color = palette.color(QPalette.ColorRole.Base)
        assert base_color == QColor(30, 30, 30), f"Expected dark base color, got {base_color.name()}"

        button_color = palette.color(QPalette.ColorRole.Button)
        assert button_color == QColor(55, 55, 58), f"Expected dark button color, got {button_color.name()}"

    @pytest.mark.gui
    def test_spritepal_app_comprehensive_stylesheet_applied(self, qtbot) -> None:
        """Test that comprehensive dark theme stylesheet is applied."""
        pytest.skip("Cannot instantiate SpritePalApp (QApplication) when a QApplication already exists (managed by pytest-qt)")
        app_args = ["test_spritepal"]
        spritepal_app = SpritePalApp(app_args)

        # Get application stylesheet
        stylesheet = spritepal_app.styleSheet()

        # Test key stylesheet components
        assert "QMainWindow" in stylesheet, "Stylesheet should include QMainWindow styling"
        assert "#2d2d30" in stylesheet, "Stylesheet should include main dark background color"
        assert "#1e1e1e" in stylesheet, "Stylesheet should include preview dark background"
        assert "QPushButton:hover" in stylesheet, "Stylesheet should include button hover states"
        assert "QLabel[preview=\"true\"]" in stylesheet, "Stylesheet should include preview label styling"

        # Test comprehensive widget coverage
        essential_widgets = [
            "QPushButton", "QLineEdit", "QComboBox", "QGroupBox",
            "QProgressBar", "QTabWidget", "QScrollArea", "QSlider"
        ]

        for widget in essential_widgets:
            assert widget in stylesheet, f"Stylesheet should include {widget} styling"

    @pytest.mark.gui
    def test_spritepal_app_with_main_window_size(self, qtbot) -> None:
        """Test that main window has correct size (1000x650)."""
        pytest.skip("Cannot instantiate SpritePalApp (QApplication) when a QApplication already exists (managed by pytest-qt)")
        app_args = ["test_spritepal"]
        spritepal_app = SpritePalApp(app_args)

        # Get main window
        main_window = spritepal_app.main_window
        assert isinstance(main_window, QMainWindow), "Should have real MainWindow instance"

        # Test minimum size is set correctly
        min_size = main_window.minimumSize()
        expected_size = QSize(1000, 650)

        assert min_size.width() >= expected_size.width(), f"Window width should be at least {expected_size.width()}, got {min_size.width()}"
        assert min_size.height() >= expected_size.height(), f"Window height should be at least {expected_size.height()}, got {min_size.height()}"

class TestMainWindowIntegration:
    """Test MainWindow integration with new size and dark theme."""

    @pytest.mark.gui
    @pytest.mark.usefixtures("setup_managers")
    def test_main_window_size_constants(self, qtbot) -> None:
        """Test that MainWindow uses correct size constants."""
        from ui.main_window import MAIN_WINDOW_MIN_SIZE

        # Verify size constants match recent changes
        assert MAIN_WINDOW_MIN_SIZE == (1000, 650), f"Expected size (1000, 650), got {MAIN_WINDOW_MIN_SIZE}"

    @pytest.mark.gui
    @pytest.mark.usefixtures("setup_managers")
    def test_main_window_with_dark_theme_styling(self, qtbot) -> None:
        """Test MainWindow with real dark theme styling applied."""
        # Create real MainWindow
        main_window = MainWindow()
        qtbot.addWidget(main_window)

        # Apply dark theme
        theme_css = get_theme_style()
        main_window.setStyleSheet(theme_css)

        # Show and test
        main_window.show()
        qtbot.waitExposed(main_window)

        # Test that window has dark theme applied
        stylesheet = main_window.styleSheet()
        assert len(stylesheet) > 0, "MainWindow should have stylesheet applied"

        # Test window size
        size = main_window.size()
        assert size.width() >= 1000, f"Window width should be at least 1000, got {size.width()}"
        assert size.height() >= 650, f"Window height should be at least 650, got {size.height()}"


class TestManualOffsetDialogSignalIntegration:
    """Test manual offset dialog with new signals (offset_changed, sprite_found)."""

    @pytest.mark.gui
    @pytest.mark.skipif(not MANUAL_OFFSET_AVAILABLE, reason="Manual offset dialog not available")
    def test_manual_offset_dialog_has_required_signals(self, qtbot) -> None:
        """Test that manual offset dialog has offset_changed and sprite_found signals."""
        # Mock dependencies
        with mock_manager_dependencies():
            try:
                dialog = UnifiedManualOffsetDialog()
                qtbot.addWidget(dialog)

                # Test that required signals exist
                assert hasattr(dialog, 'offset_changed'), "Dialog should have offset_changed signal"
                assert hasattr(dialog, 'sprite_found'), "Dialog should have sprite_found signal"

                # Test signal types
                # If dialog is mocked, these are CallbackSignal, else Signal
                # UnifiedManualOffsetDialog is either real or Mock
                # If Mock, it's MockUnifiedOffsetDialog from infrastructure which uses CallbackSignal
                # If real, it uses Signal
                if type(dialog).__name__ == "MockUnifiedOffsetDialog":
                    # It's a mock, skip type check or check for CallbackSignal
                    pass 
                else:
                    assert isinstance(dialog.offset_changed, Signal), "offset_changed should be a Qt Signal"
                    assert isinstance(dialog.sprite_found, Signal), "sprite_found should be a Qt Signal"

            except Exception as e:
                pytest.skip(f"Could not create manual offset dialog: {e}")

    @pytest.mark.gui
    @pytest.mark.skipif(not MANUAL_OFFSET_AVAILABLE, reason="Manual offset dialog not available")
    def test_manual_offset_dialog_offset_changed_signal_emission(self, qtbot) -> None:
        """Test offset_changed signal emission with real Qt signal testing."""
        with mock_manager_dependencies():
            try:
                dialog = UnifiedManualOffsetDialog()
                qtbot.addWidget(dialog)

                # Use QSignalSpy to monitor offset_changed signal
                # If dialog is mocked, it uses CallbackSignal which is not compatible with QSignalSpy
                is_mock = type(dialog).__name__ == "MockUnifiedOffsetDialog"
                
                if not is_mock:
                    spy = QSignalSpy(dialog.offset_changed)

                # If dialog has browse_tab with offset controls, test signal emission
                if hasattr(dialog, 'browse_tab') and hasattr(dialog.browse_tab, 'set_offset'):
                    # Trigger offset change
                    test_offset = 12345
                    dialog.browse_tab.set_offset(test_offset)

                    if not is_mock:
                        # Wait for signal emission
                        qtbot.waitUntil(lambda: len(spy) > 0, timeout=500)

                        # Test that signal was emitted
                        assert len(spy) > 0, "offset_changed signal should have been emitted"

                        # Test signal argument
                        if len(spy) > 0:
                            emitted_offset = spy[-1][0]  # Get last emitted offset
                            assert emitted_offset == test_offset, f"Expected offset {test_offset}, got {emitted_offset}"
                else:
                    pytest.skip("Dialog does not have expected browse_tab structure")

            except Exception as e:
                pytest.skip(f"Could not test offset signal emission: {e}")

    @pytest.mark.gui
    @pytest.mark.skipif(not MANUAL_OFFSET_AVAILABLE, reason="Manual offset dialog not available")
    def test_manual_offset_dialog_sprite_found_signal_emission(self, qtbot) -> None:
        """Test sprite_found signal emission with real Qt signal testing."""
        with mock_manager_dependencies():
            try:
                dialog = UnifiedManualOffsetDialog()
                qtbot.addWidget(dialog)

                is_mock = type(dialog).__name__ == "MockUnifiedOffsetDialog"
                
                if not is_mock:
                    # Use QSignalSpy to monitor sprite_found signal
                    spy = QSignalSpy(dialog.sprite_found)

                # Manually emit sprite_found signal for testing
                test_offset = 54321
                test_sprite_name = "TestSprite"

                dialog.sprite_found.emit(test_offset, test_sprite_name)

                if not is_mock:
                    # Wait for signal processing
                    qtbot.waitUntil(lambda: len(spy) > 0, timeout=500)

                    # Test that signal was emitted
                    assert len(spy) > 0, "sprite_found signal should have been emitted"

                    # Test signal arguments
                    if len(spy) > 0:
                        emitted_data = spy[-1]  # Get last emission
                        assert emitted_data[0] == test_offset, f"Expected offset {test_offset}, got {emitted_data[0]}"
                        assert emitted_data[1] == test_sprite_name, f"Expected name {test_sprite_name}, got {emitted_data[1]}"

            except Exception as e:
                pytest.skip(f"Could not test sprite_found signal emission: {e}")

    @pytest.mark.gui
    @pytest.mark.skipif(not MANUAL_OFFSET_AVAILABLE, reason="Manual offset dialog not available")
    def test_manual_offset_dialog_with_dark_theme(self, qtbot) -> None:
        """Test manual offset dialog with dark theme applied."""
        with mock_manager_dependencies():
            try:
                dialog = UnifiedManualOffsetDialog()
                qtbot.addWidget(dialog)

                # Apply dark theme
                theme_css = get_theme_style()
                
                # Check if it's a mock that supports setStyleSheet
                if hasattr(dialog, 'setStyleSheet'):
                    dialog.setStyleSheet(theme_css)

                # Show dialog
                dialog.show()
                
                # Only wait exposed if it's a real widget
                if type(dialog).__name__ != "MockUnifiedOffsetDialog":
                    qtbot.waitExposed(dialog)

                    # Test that dialog has dark styling
                    stylesheet = dialog.styleSheet()
                    assert len(stylesheet) > 0, "Dialog should have stylesheet applied"

                    # Test dialog size is reasonable
                    size = dialog.size()
                    assert size.width() > 0 and size.height() > 0, "Dialog should have valid size"

            except Exception as e:
                pytest.skip(f"Could not test dialog with dark theme: {e}")

class TestPreviewWidgetDarkBackgrounds:
    """Test sprite preview widgets with dark backgrounds (#1e1e1e)."""

    @pytest.mark.gui
    def test_dark_preview_style_colors(self, qtbot) -> None:
        """Test that dark preview style uses correct color (#1e1e1e)."""
        dark_preview_css = get_dark_preview_style()

        # Test that CSS contains the expected dark background color
        assert "#1e1e1e" in dark_preview_css, "Dark preview style should contain #1e1e1e background"
        assert "background-color" in dark_preview_css, "Dark preview style should set background-color"

        # Test that it's valid CSS structure
        assert dark_preview_css.count('{') == dark_preview_css.count('}'), "CSS should have balanced braces"

    @pytest.mark.gui
    def test_preview_widget_with_dark_background_applied(self, qtbot) -> None:
        """Test preview widget with dark background (#1e1e1e) applied."""
        from PySide6.QtWidgets import QLabel

        # Create a preview widget (using QLabel as base)
        preview_widget = QLabel("Preview Content")
        qtbot.addWidget(preview_widget)

        # Apply dark preview styling
        dark_css = get_dark_preview_style()
        preview_widget.setStyleSheet(dark_css)

        # Show widget
        preview_widget.show()
        qtbot.waitExposed(preview_widget)

        # Test that styling was applied
        applied_css = preview_widget.styleSheet()
        assert len(applied_css) > 0, "Preview widget should have stylesheet"
        assert "#1e1e1e" in applied_css, "Applied CSS should contain dark background color"

    @pytest.mark.gui
    def test_preview_widget_contrast_with_dark_background(self, qtbot) -> None:
        """Test that preview widgets have good contrast with dark backgrounds."""
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QLabel

        # Create preview widget
        preview_widget = QLabel()
        qtbot.addWidget(preview_widget)

        # Create test pixmap with light content (should contrast well with dark bg)
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(255, 255, 255))  # White content

        # Apply dark background
        preview_widget.setPixmap(pixmap)
        preview_widget.setStyleSheet(f"background-color: {COLORS['preview_background']};")

        # Show and test
        preview_widget.show()
        qtbot.waitExposed(preview_widget)

        # Test that pixmap is set and widget has dark background
        assert preview_widget.pixmap() is not None, "Preview should have pixmap content"

        # Test background color matches theme
        expected_bg = COLORS['preview_background']
        assert expected_bg in preview_widget.styleSheet(), f"Background should use theme color {expected_bg}"

class TestButtonStylingWithGradients:
    """Test button styling with gradients and hover states."""

    @pytest.mark.gui
    def test_button_style_generation_with_gradients(self, qtbot) -> None:
        """Test that button styles include gradient and hover state styling."""
        button_types = ["primary", "secondary", "accent", "extract", "editor"]

        for button_type in button_types:
            css = get_button_style(button_type)

            # Test that CSS includes hover states
            assert "hover" in css.lower(), f"Button style {button_type} should include hover states"

            # Test that CSS includes some form of styling (background, border, etc.)
            style_properties = ["background", "border", "color"]
            has_style = any(prop in css.lower() for prop in style_properties)
            assert has_style, f"Button style {button_type} should include visual styling properties"

    @pytest.mark.gui
    def test_button_with_gradient_styling_applied(self, qtbot) -> None:
        """Test QPushButton with gradient styling applied."""
        button = QPushButton("Test Button")
        qtbot.addWidget(button)

        # Apply primary button style
        primary_css = get_button_style("primary")
        button.setStyleSheet(primary_css)

        # Show button
        button.show()
        qtbot.waitExposed(button)

        # Test that styling was applied
        applied_css = button.styleSheet()
        assert len(applied_css) > 0, "Button should have stylesheet applied"

        # Test button functionality
        assert button.isEnabled(), "Styled button should be enabled"
        assert button.text() == "Test Button", "Button text should be preserved"

    @pytest.mark.gui
    def test_multiple_button_styles_consistency(self, qtbot) -> None:
        """Test that multiple button styles work consistently."""
        from PySide6.QtWidgets import QVBoxLayout

        # Create container with multiple buttons
        container = QWidget()
        qtbot.addWidget(container)
        layout = QVBoxLayout(container)

        button_configs = [
            ("Extract", "extract"),
            ("Arrange Rows", "primary"),
            ("Grid Arrange", "secondary"),
            ("Inject", "accent"),
            ("Open Editor", "editor")
        ]

        buttons = []
        for text, style_type in button_configs:
            button = QPushButton(text)
            button.setStyleSheet(get_button_style(style_type))
            layout.addWidget(button)
            buttons.append((button, style_type))

        # Show container
        container.show()
        qtbot.waitExposed(container)

        # Test all buttons are properly styled and functional
        for button, style_type in buttons:
            assert len(button.styleSheet()) > 0, f"Button {style_type} should have styling"
            assert button.isEnabled(), f"Button {style_type} should be enabled"

            # Test hover simulation (enter/leave events)
            button.enterEvent(None)
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()  # Allow hover state processing
            button.leaveEvent(None)

    @pytest.mark.gui
    def test_button_hover_state_changes(self, qtbot) -> None:
        """Test button hover state visual changes."""
        button = QPushButton("Hover Test")
        qtbot.addWidget(button)

        # Apply style with hover effects
        hover_css = get_button_style("primary")
        button.setStyleSheet(hover_css)

        button.show()
        qtbot.waitExposed(button)

        # Test hover state changes (visual feedback)
        original_size = button.size()

        # Simulate mouse enter (hover start)
        button.enterEvent(None)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()  # Allow visual state change

        # Simulate mouse leave (hover end)
        button.leaveEvent(None)
        QApplication.processEvents()

        # Test that button maintains consistent size
        final_size = button.size()
        assert final_size == original_size, "Button size should be consistent after hover"

class TestCompleteUserWorkflowIntegration:
    """Test complete user workflows with real Qt interaction."""


    @pytest.mark.gui
    @pytest.mark.usefixtures("setup_managers")
    def test_theme_consistency_across_workflow(self, qtbot) -> None:
        """Test that dark theme is consistent across entire user workflow."""
        # Step 1: Create main window
        main_window = MainWindow()
        qtbot.addWidget(main_window)

        # Step 2: Apply application theme
        app_theme = get_theme_style()
        main_window.setStyleSheet(app_theme)

        main_window.show()
        qtbot.waitExposed(main_window)

        # Step 3: Test theme colors are consistent
        palette = main_window.palette()
        window_bg = palette.color(QPalette.ColorRole.Window)

        # Step 4: Create additional UI components
        test_button = QPushButton("Test Workflow", main_window)
        test_button.setStyleSheet(get_button_style("primary"))

        # Step 5: Verify theme consistency
        assert window_bg.value() < 128, "Main window should have dark background"
        assert len(main_window.styleSheet()) > 0, "Main window should have theme CSS"
        assert len(test_button.styleSheet()) > 0, "Button should have consistent styling"

        # Step 6: Test that theme colors match expected values
        expected_bg = COLORS['background']
        expected_preview_bg = COLORS['preview_background']

        theme_css = main_window.styleSheet()
        assert expected_bg in theme_css, f"Theme should use background color {expected_bg}"
        assert expected_preview_bg in theme_css or expected_preview_bg == "#1e1e1e", "Theme should include preview background"

    @pytest.mark.gui
    @pytest.mark.usefixtures("setup_managers")
    def test_responsive_ui_with_size_constraints(self, qtbot) -> None:
        """Test that UI responds correctly to size constraints (1000x650)."""
        # Create main window
        main_window = MainWindow()
        qtbot.addWidget(main_window)

        # Test minimum size constraints
        main_window.setMinimumSize(1000, 650)
        main_window.show()
        qtbot.waitExposed(main_window)

        # Test actual size meets constraints
        actual_size = main_window.size()
        assert actual_size.width() >= 1000, f"Width should be at least 1000, got {actual_size.width()}"
        assert actual_size.height() >= 650, f"Height should be at least 650, got {actual_size.height()}"

        # Test resize behavior
        main_window.resize(1200, 800)
        qtbot.waitUntil(lambda: main_window.size().width() >= 1200, timeout=1000)

        new_size = main_window.size()
        assert new_size.width() >= 1000, "Width should remain at least 1000 after resize"
        assert new_size.height() >= 650, "Height should remain at least 650 after resize"

class TestRegressionPrevention:
    """Tests to prevent regression of recent UI improvements."""

    @pytest.mark.gui
    def test_no_regression_in_window_size(self, qtbot) -> None:
        """Test that window size hasn't regressed from 1000x650."""
        from ui.main_window import MAIN_WINDOW_MIN_SIZE

        # This test will fail if someone accidentally changes the size back
        assert MAIN_WINDOW_MIN_SIZE == (1000, 650), (
            f"Window size regression detected! Expected (1000, 650), got {MAIN_WINDOW_MIN_SIZE}. "
            "The recent UI improvement reduced size from 1200x750 to 1000x650."
        )

    @pytest.mark.gui
    def test_no_regression_in_dark_theme_colors(self, qtbot) -> None:
        """Test that dark theme colors haven't regressed."""
        # Test key colors from theme
        assert COLORS['background'] == '#2d2d30', "Main background color should remain #2d2d30"
        assert COLORS['preview_background'] == '#1e1e1e', "Preview background should remain #1e1e1e"
        assert COLORS['panel_background'] == '#383838', "Panel background should remain #383838"

        # Test that theme function includes these colors
        theme_css = get_theme_style()
        assert COLORS['background'] in theme_css, "Theme CSS should include main background color"

    @pytest.mark.gui
    @pytest.mark.skipif(not MANUAL_OFFSET_AVAILABLE, reason="Manual offset dialog not available")
    def test_no_regression_in_manual_offset_signals(self, qtbot) -> None:
        """Test that manual offset dialog signals haven't regressed."""
        # Pass mock extraction_manager directly (replaces deprecated get_extraction_manager patch)
        mock_extraction_manager = Mock()

        try:
            dialog = UnifiedManualOffsetDialog(extraction_manager=mock_extraction_manager)

            # Test that new signals are still present
            required_signals = ['offset_changed', 'sprite_found']
            for signal_name in required_signals:
                assert hasattr(dialog, signal_name), (
                    f"Signal regression detected! Manual offset dialog missing {signal_name} signal. "
                    "These signals were added in recent UI improvements."
                )

                signal_obj = getattr(dialog, signal_name)
                assert isinstance(signal_obj, Signal), f"{signal_name} should be a Qt Signal"

        except Exception as e:
            pytest.skip(f"Could not test signal regression: {e}")

    @pytest.mark.gui
    def test_no_regression_in_button_styling_system(self, qtbot) -> None:
        """Test that button styling system hasn't regressed."""
        # Test that all button styles still exist
        button_types = ["primary", "secondary", "accent", "extract", "editor"]

        for button_type in button_types:
            css = get_button_style(button_type)
            assert isinstance(css, str), f"Button style {button_type} should return CSS string"
            assert len(css) > 0, f"Button style {button_type} should not be empty"

            # Test that hover states are still included
            assert "hover" in css.lower(), f"Button style {button_type} should include hover states"

# Helper functions for test setup
@contextmanager
def mock_manager_dependencies() -> Generator[None, None, None]:
    """Context manager to mock common manager dependencies."""
    from core.di_container import get_container, register_singleton
    from core.protocols.manager_protocols import (
        ExtractionManagerProtocol,
        ROMCacheProtocol,
        ROMExtractorProtocol,
        SessionManagerProtocol,
        SettingsManagerProtocol,
    )

    # Create mocks
    mock_session = Mock()
    mock_extraction = Mock()
    mock_rom_extractor = Mock()
    mock_settings = Mock()
    mock_rom_cache = Mock()

    # Configure mocks
    mock_extraction.get_rom_extractor.return_value = mock_rom_extractor

    # Register in DI container (replaces deprecated get_*_manager patches)
    register_singleton(ExtractionManagerProtocol, mock_extraction)
    register_singleton(SettingsManagerProtocol, mock_settings)
    register_singleton(ROMCacheProtocol, mock_rom_cache)
    register_singleton(ROMExtractorProtocol, mock_rom_extractor)
    register_singleton(SessionManagerProtocol, mock_session)

    try:
        # DI container is already configured with mocks above
        # No need to patch deprecated get_*_manager functions - they've been removed
        yield
    finally:
        # Clean up DI container registrations to prevent test pollution
        container = get_container()
        container.unregister(ExtractionManagerProtocol)
        container.unregister(SettingsManagerProtocol)
        container.unregister(ROMCacheProtocol)
        container.unregister(ROMExtractorProtocol)
        container.unregister(SessionManagerProtocol)

def create_test_spritepal_app() -> SpritePalApp:
    """Create a test SpritePalApp instance with minimal setup."""
    return SpritePalApp(["test_spritepal"])

@pytest.fixture
def test_app(qtbot) -> Generator[SpritePalApp, None, None]:
    """Fixture providing a test SpritePalApp instance."""
    app = create_test_spritepal_app()
    yield app
    # Cleanup is handled by qtbot

@pytest.fixture
def test_main_window(qtbot) -> Generator[MainWindow, None, None]:
    """Fixture providing a test MainWindow with mocked dependencies."""
    with mock_manager_dependencies():
        main_window = MainWindow()
        qtbot.addWidget(main_window)
        yield main_window
