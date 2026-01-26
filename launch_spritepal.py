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
    _apply_dark_theme_to_app(app)


def _apply_dark_theme_to_app(app: QApplication) -> None:
    """Apply a modern dark theme to the given QApplication."""
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

    app.setPalette(dark_palette)

    # Set comprehensive dark theme stylesheet from theme service
    app.setStyleSheet(get_theme_style())


class SpritePalApp:
    """Main application class for SpritePal - configures an existing QApplication"""

    def __init__(self, app: QApplication, context: AppContext) -> None:
        self._app = app
        self._context = context

        # Set application metadata
        app.setApplicationName("SpritePal")
        app.setOrganizationName("KirbySpriteTools")
        app.setApplicationDisplayName("SpritePal - Sprite Extraction Tool")

        # Apply modern dark theme
        _apply_dark_theme_to_app(app)

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
            rom_extractor=context.rom_extractor,
            sprite_library=context.sprite_library,
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

    # Create QApplication FIRST so managers can have Qt parent
    # Note: We create a basic QApplication here, then configure it in SpritePalApp.__init__
    app = QApplication(sys.argv)

    # Create app context with explicit wiring (now QApplication exists)
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
        # Apply stored logging settings
        from utils.logging_config import set_console_debug_mode, set_disabled_categories

        debug_logging_enabled = context.application_state_manager.get_debug_logging()
        set_console_debug_mode(debug_logging_enabled)
        logger.info(f"Console debug logging: {'enabled' if debug_logging_enabled else 'disabled'}")

        # Apply disabled log categories
        disabled_categories = context.application_state_manager.get_disabled_log_categories()
        if disabled_categories:
            set_disabled_categories(set(disabled_categories))
            logger.info(f"Disabled log categories: {disabled_categories}")

        # Configure application with context
        spritepal = SpritePalApp(app, context=context)

        # Show main window
        spritepal.show()

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
