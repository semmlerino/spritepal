"""Auto-save manager for Frame Mapping projects.

Provides debounced auto-save functionality to avoid saving on every small change.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QWidget

from utils.logging_config import get_logger

logger = get_logger(__name__)


class AutoSaveManager:
    """Debounced auto-save for Frame Mapping projects.

    Timer is owned by the workspace; this class manages the save logic.
    Uses a debounce pattern: multiple rapid changes only trigger one save
    after activity stops.

    Attributes:
        _timer: QTimer for debouncing (owned externally, connected to perform_save)
        _get_project_path: Callable returning current project path or None
        _save_project: Callable to save project to a path (returns bool)
        _show_message: Optional callable to show status messages
        _parent_widget: Optional parent widget for error dialogs
    """

    def __init__(
        self,
        timer: QTimer,
        get_project_path: Callable[[], Path | None],
        save_project: Callable[[Path], bool],
        show_message: Callable[[str, int], None] | None = None,
        parent_widget: QWidget | None = None,
    ) -> None:
        """Initialize the auto-save manager.

        Args:
            timer: QTimer configured for debouncing (should be single-shot)
            get_project_path: Callable that returns the current project path
            save_project: Callable that saves the project to a given path
            show_message: Optional callable for status messages (message, duration_ms)
            parent_widget: Optional parent widget for error dialogs
        """
        self._timer = timer
        self._get_project_path = get_project_path
        self._save_project = save_project
        self._show_message = show_message
        self._parent_widget = parent_widget

    def set_message_service(self, show_message: Callable[[str, int], None] | None) -> None:
        """Set the message service for status updates.

        Args:
            show_message: Callable for status messages, or None to disable
        """
        self._show_message = show_message

    def set_parent_widget(self, widget: QWidget | None) -> None:
        """Set the parent widget for error dialogs.

        Args:
            widget: Parent widget or None
        """
        self._parent_widget = widget

    def schedule_save(self) -> None:
        """Schedule an auto-save with debouncing.

        Uses the timer to debounce multiple rapid changes. Each call
        restarts the timer, so the actual save only happens after
        activity stops for the debounce interval.
        """
        project_path = self._get_project_path()
        if not project_path:
            logger.warning("Cannot auto-save: no project path set")
            return

        # (Re)start the debounce timer - will save after the interval
        self._timer.start()

    def perform_save(self) -> None:
        """Actually perform the auto-save after debounce timer fires.

        Saves the project to the correct project file path.
        Shows a message on success or an error dialog on failure.
        """
        project_path = self._get_project_path()
        if not project_path:
            return

        try:
            self._save_project(project_path)
            if self._show_message:
                self._show_message("Project auto-saved", 2000)
            logger.info("Auto-saved project to %s", project_path)
        except Exception as e:
            logger.exception("Failed to auto-save project after injection")
            if self._parent_widget:
                QMessageBox.warning(
                    self._parent_widget,
                    "Auto-Save Failed",
                    f"Failed to save project: {e}\n\nPlease save manually.",
                )
