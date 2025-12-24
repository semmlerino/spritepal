#!/usr/bin/env python3
from __future__ import annotations

"""
SpritePal - Modern Sprite Extraction Tool
Simplifies sprite extraction with automatic palette association
"""

import sys
from types import TracebackType

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from core.di_container import inject
from core.managers import (
    cleanup_managers,
    initialize_managers,
    validate_manager_dependencies,
)
from core.managers.application_state_manager import ApplicationStateManager
from core.services.rom_cache import ROMCache
from ui.main_window import MainWindow
from ui.styles.accessibility import initialize_accessibility
from utils.logging_config import get_logger, setup_logging


def handle_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> None:
    """Global exception handler to log unhandled exceptions"""
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow KeyboardInterrupt to work normally
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Get logger (setup_logging should have been called by now)
    logger = get_logger("global_exception_handler")

    # Log the unhandled exception
    logger.critical("Unhandled exception occurred!", exc_info=(exc_type, exc_value, exc_traceback))
    logger.critical(f"Exception type: {exc_type.__name__}")
    logger.critical(f"Exception value: {exc_value}")
    logger.critical("=" * 80)
    logger.critical("CRASH DETECTED - Application will likely terminate")
    logger.critical("=" * 80)

    # Call the default handler to maintain normal behavior
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

def apply_dark_theme(app: QApplication) -> None:
    """Apply a modern dark theme to the application."""
    SpritePalApp._apply_dark_theme(app)  # type: ignore[arg-type]

class SpritePalApp(QApplication):
    """Main application class for SpritePal"""

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)

        # Set application metadata
        self.setApplicationName("SpritePal")
        self.setOrganizationName("KirbySpriteTools")
        self.setApplicationDisplayName("SpritePal - Sprite Extraction Tool")

        # Apply modern dark theme
        self._apply_dark_theme()

        # Initialize accessibility features
        initialize_accessibility()

        # B.6: Create main window with explicit DI dependencies
        # This eliminates deprecation warnings and makes dependencies explicit
        self.main_window = MainWindow(
            settings_manager=inject(ApplicationStateManager),
            rom_cache=inject(ROMCache),
            session_manager=inject(ApplicationStateManager),
        )

    def _apply_dark_theme(self):
        """Apply a modern dark theme to the application"""
        # Create dark palette
        dark_palette = QPalette()

        # Window colors
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48))
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)

        # Base colors (for input widgets)
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(50, 50, 52))

        # Text colors
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)

        # Button colors
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 58))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)

        # Highlight colors
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 122, 204))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)

        # Other colors
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(0, 162, 232))
        dark_palette.setColor(QPalette.ColorRole.LinkVisited, QColor(128, 128, 255))

        # Disabled colors
        dark_palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.WindowText,
            QColor(127, 127, 127),
        )
        dark_palette.setColor(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127)
        )
        dark_palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            QColor(127, 127, 127),
        )

        self.setPalette(dark_palette)

        # Set comprehensive dark theme stylesheet
        self.setStyleSheet(
            """
            /* Main application styling */
            QMainWindow {
                background-color: #2d2d30;
                color: white;
            }

            QWidget {
                background-color: #2d2d30;
                color: white;
            }

            /* Tooltips */
            QToolTip {
                color: white;
                background-color: #2b2b2b;
                border: 1px solid #555;
                padding: 4px;
                border-radius: 4px;
            }

            /* Group Boxes and Panels */
            QGroupBox {
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 12px;
                font-weight: bold;
                background-color: #383838;
                color: white;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: white;
            }

            /* Buttons */
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                border: 1px solid #555;
                min-width: 80px;
                background-color: #55555a;
                color: white;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #484848;
                border-color: #0078d4;
            }

            QPushButton:pressed {
                background-color: #383838;
            }

            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666;
                border-color: #444;
            }

            /* Input Fields */
            QLineEdit {
                padding: 6px;
                border: 1px solid #555;
                border-radius: 4px;
                background-color: #2b2b2b;
                color: white;
                selection-background-color: #0078d4;
            }

            QLineEdit:focus {
                border-color: #0078d4;
                outline: none;
            }

            QLineEdit:disabled {
                background-color: #1e1e1e;
                color: #666;
            }

            /* Combo Boxes */
            QComboBox {
                padding: 6px;
                border: 1px solid #555;
                border-radius: 4px;
                background-color: #2b2b2b;
                color: white;
                min-width: 100px;
            }

            QComboBox:hover {
                border-color: #0078d4;
            }

            QComboBox:disabled {
                background-color: #1e1e1e;
                color: #666;
            }

            QComboBox::drop-down {
                border: none;
                width: 20px;
                background-color: #383838;
            }

            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #ccc;
                margin-right: 5px;
            }

            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                color: white;
                border: 1px solid #555;
                selection-background-color: #0078d4;
            }

            /* Spin Boxes */
            QSpinBox, QDoubleSpinBox {
                padding: 6px;
                border: 1px solid #555;
                border-radius: 4px;
                background-color: #2b2b2b;
                color: white;
            }

            QSpinBox:focus, QDoubleSpinBox:focus {
                border-color: #0078d4;
            }

            /* Progress Bars */
            QProgressBar {
                border: 1px solid #555;
                border-radius: 4px;
                text-align: center;
                background-color: #2b2b2b;
                color: white;
            }

            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }

            /* Tabs */
            QTabWidget::pane {
                border: 1px solid #555;
                background-color: #2d2d30;
            }

            QTabBar::tab {
                background-color: #383838;
                color: white;
                padding: 10px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border: 1px solid #555;
                border-bottom: none;
            }

            QTabBar::tab:selected {
                background-color: #2d2d30;
                border-bottom: 2px solid #0078d4;
            }

            QTabBar::tab:hover {
                background-color: #484848;
            }

            /* Scroll Areas */
            QScrollArea {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
            }

            QScrollBar:vertical {
                background-color: #383838;
                width: 12px;
                border-radius: 6px;
                margin: 0;
            }

            QScrollBar::handle:vertical {
                background-color: #666;
                min-height: 20px;
                border-radius: 6px;
                margin: 2px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #777;
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }

            /* Sliders */
            QSlider::groove:horizontal {
                border: 1px solid #555;
                height: 8px;
                background: #2b2b2b;
                border-radius: 4px;
            }

            QSlider::handle:horizontal {
                background: #0078d4;
                border: 1px solid #0078d4;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }

            QSlider::handle:horizontal:hover {
                background: #106ebe;
                border-color: #106ebe;
            }

            /* Splitters */
            QSplitter::handle {
                background-color: #555;
                border: 1px solid #666;
                width: 8px;
                height: 8px;
            }

            QSplitter::handle:hover {
                background-color: #666;
            }

            /* Labels for previews */
            QLabel[preview="true"] {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
            }

            /* Status Bar */
            QStatusBar {
                background-color: #007acc;
                color: white;
                border-top: 1px solid #555;
            }

            /* Menu Bar */
            QMenuBar {
                background-color: #383838;
                color: white;
                border-bottom: 1px solid #555;
            }

            QMenuBar::item {
                background-color: transparent;
                padding: 6px 12px;
            }

            QMenuBar::item:selected {
                background-color: #484848;
            }

            QMenu {
                background-color: #2b2b2b;
                color: white;
                border: 1px solid #555;
            }

            QMenu::item {
                padding: 6px 20px;
            }

            QMenu::item:selected {
                background-color: #0078d4;
            }
        """
        )

    def show(self):
        """Show the main window"""
        self.main_window.show()

def main():
    """Main entry point"""
    # Create ConfigurationService FIRST - single source of truth for paths
    from core.configuration_service import ConfigurationService

    config_service = ConfigurationService()

    # Ensure required directories exist
    config_service.ensure_directories_exist()

    # Initialize logging with path from ConfigurationService
    logger = setup_logging(log_dir=config_service.log_directory)
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Platform: {sys.platform}")
    logger.info(f"App root: {config_service.app_root}")
    logger.info(f"Settings file: {config_service.settings_file}")

    # Install global exception handler to catch unhandled crashes
    sys.excepthook = handle_exception
    logger.info("Global exception handler installed")

    # Initialize managers with enhanced error handling
    logger.info("Initializing managers...")
    try:
        initialize_managers(
            "SpritePal",
            settings_path=config_service.settings_file,
            configuration_service=config_service,
        )
        logger.info("Managers initialized successfully")

        # Register UI factories with DI container
        # This must happen AFTER initialize_managers() but BEFORE using dialogs
        try:
            from ui import register_ui_factories
            register_ui_factories()
            logger.info("UI factories registered")
        except Exception as e:
            raise RuntimeError(f"Failed to register UI factories: {e}") from e

        # Validate manager dependencies
        if validate_manager_dependencies():
            logger.info("Manager dependencies validated successfully")
        else:
            logger.warning("Manager dependency validation failed - some features may not work correctly")

    except Exception as e:
        logger.critical(f"Failed to initialize managers: {e}")
        logger.critical("Application cannot start without properly initialized managers")
        sys.exit(1)

    try:
        # Create application
        app = SpritePalApp(sys.argv)

        # Show main window
        app.show()

        # Run event loop
        result = app.exec()
    finally:
        # Cleanup managers on exit
        logger.info("Cleaning up managers...")
        cleanup_managers()
        logger.info("Managers cleaned up")

    sys.exit(result)

if __name__ == "__main__":
    main()
