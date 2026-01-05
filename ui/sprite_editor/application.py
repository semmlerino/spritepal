#!/usr/bin/env python3
"""
Application entry point for the unified sprite editor.
"""

import sys

from PySide6.QtWidgets import QApplication

from .controllers import MainController
from .views import SpriteEditorMainWindow


class SpriteEditorApplication:
    """Main application class for the unified sprite editor."""

    def __init__(self, argv: list[str] | None = None) -> None:
        """Initialize the application.

        Args:
            argv: Command line arguments (uses sys.argv if not provided)
        """
        if argv is None:
            argv = sys.argv

        # Create Qt application (reuse existing or create new)
        existing = QApplication.instance()
        if existing is not None and isinstance(existing, QApplication):
            self.app = existing
        else:
            self.app = QApplication(argv)

        # Initialize AppContext for settings/state management
        from core.app_context import create_app_context, get_app_context, is_context_initialized

        if not is_context_initialized():
            create_app_context("SpritePalEditor")
        context = get_app_context()

        # Create main window with settings manager
        self.main_window = SpriteEditorMainWindow(settings_manager=context.application_state_manager)

        # Create main controller
        self.controller = MainController()
        self.controller.set_main_window(self.main_window)

        # Connect status messages
        self.controller.status_message.connect(self.main_window.set_status)

    def run(self) -> int:
        """Run the application.

        Returns:
            Exit code from the application
        """
        self.main_window.show()
        return self.app.exec()


def main() -> int:
    """Main entry point."""
    app = SpriteEditorApplication()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
