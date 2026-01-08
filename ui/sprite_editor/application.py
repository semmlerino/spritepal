#!/usr/bin/env python3
"""
Application entry point for the unified sprite editor.
"""

import sys
from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import QApplication

from .controllers import (
    EditingController,
    ExtractionController,
    InjectionController,
)
from .controllers.rom_workflow_controller import ROMWorkflowController
from .views import SpriteEditorMainWindow

if TYPE_CHECKING:
    from ui.managers.status_bar_manager import StatusBarManager


class MainWindowMessageAdapter:
    """Adapts SpriteEditorMainWindow.set_status to message service interface."""

    def __init__(self, window: "SpriteEditorMainWindow") -> None:
        self._window = window

    def show_message(self, message: str, timeout: int = 0) -> None:
        """Display a message in the window's status bar."""
        self._window.set_status(message)

    def clear_message(self) -> None:
        """Clear the status bar message."""
        self._window.set_status("")


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

        # Create message adapter
        message_adapter = MainWindowMessageAdapter(self.main_window)

        # Create sub-controllers directly with explicit dependencies
        self.extraction_controller = ExtractionController(
            None,
            rom_cache=context.rom_cache,
            rom_extractor=context.rom_extractor,
        )
        self.editing_controller = EditingController(None)
        self.injection_controller = InjectionController(None)
        self.rom_workflow_controller = ROMWorkflowController(
            None,
            self.editing_controller,
            message_service=cast("StatusBarManager", message_adapter),
            rom_cache=context.rom_cache,
            rom_extractor=context.rom_extractor,
            log_watcher=context.log_watcher,
            sprite_library=context.sprite_library,
        )

        # Wire controllers to window
        self.main_window.wire_controllers(
            self.extraction_controller,
            self.editing_controller,
            self.injection_controller,
            self.rom_workflow_controller,
        )

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
