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

from core.app_context import AppContext, create_app_context, reset_app_context
from core.managers import validate_manager_dependencies
from ui.main_window import MainWindow
from ui.styles import get_theme_style
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

    def __init__(self, argv: list[str], context: AppContext) -> None:
        super().__init__(argv)

        # Store context reference
        self._context = context

        # Set application metadata
        self.setApplicationName("SpritePal")
        self.setOrganizationName("KirbySpriteTools")
        self.setApplicationDisplayName("SpritePal - Sprite Extraction Tool")

        # Apply modern dark theme
        self._apply_dark_theme()

        # Initialize accessibility features
        initialize_accessibility()

        # Create main window with explicit dependencies from context
        self.main_window = MainWindow(
            settings_manager=context.application_state_manager,
            rom_cache=context.rom_cache,
            session_manager=context.application_state_manager,
            core_operations_manager=context.core_operations_manager,
            log_watcher=context.log_watcher,
            preview_generator=context.preview_generator,
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
        dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
        dark_palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            QColor(127, 127, 127),
        )

        self.setPalette(dark_palette)

        # Set comprehensive dark theme stylesheet from theme service
        self.setStyleSheet(get_theme_style())

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

    # Create app context with explicit wiring
    logger.info("Creating app context...")
    try:
        context = create_app_context(
            "SpritePal",
            settings_path=config_service.settings_file,
            configuration_service=config_service,
        )
        logger.info("App context created successfully")

        # Validate manager dependencies
        if validate_manager_dependencies():
            logger.info("Manager dependencies validated successfully")
        else:
            logger.warning("Manager dependency validation failed - some features may not work correctly")

    except Exception as e:
        logger.critical(f"Failed to create app context: {e}")
        logger.critical("Application cannot start without properly initialized managers")
        sys.exit(1)

    try:
        # Create application with context
        app = SpritePalApp(sys.argv, context=context)

        # Show main window
        app.show()

        # Run event loop
        result = app.exec()
    finally:
        # Cleanup context on exit
        logger.info("Cleaning up app context...")
        reset_app_context()
        logger.info("App context cleaned up")

    sys.exit(result)


if __name__ == "__main__":
    main()
