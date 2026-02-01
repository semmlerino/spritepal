"""Auto-save manager for Frame Mapping projects.

Provides debounced auto-save functionality to avoid saving on every small change.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import override

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from utils.logging_config import get_logger

logger = get_logger(__name__)


class _SaveWorkerSignals(QObject):
    """Signals for the background save worker."""

    finished = Signal(bool, str)  # success, error_message


class _SaveWorker(QRunnable):
    """Background worker for saving projects without blocking UI."""

    def __init__(self, save_project: Callable[[Path], bool], project_path: Path) -> None:
        super().__init__()
        self.signals = _SaveWorkerSignals()
        self._save_project = save_project
        self._project_path = project_path

    @override
    def run(self) -> None:
        """Run the save operation in background thread."""
        try:
            self._save_project(self._project_path)
            self.signals.finished.emit(True, "")
        except Exception as e:
            self.signals.finished.emit(False, str(e))


class AutoSaveManager(QObject):
    """Debounced auto-save for Frame Mapping projects.

    Timer is owned by the workspace; this class manages the save logic.
    Uses a debounce pattern: multiple rapid changes only trigger one save
    after activity stops.

    Inherits from QObject to ensure signal handlers run on the main thread
    when receiving signals from background workers.

    Attributes:
        _timer: QTimer for debouncing (owned externally, connected to perform_save)
        _get_project_path: Callable returning current project path or None
        _save_project: Callable to save project to a path (returns bool)
        _show_message: Optional callable to show status messages
        _parent_widget: Optional parent widget for error dialogs
        _save_lock: Threading lock to prevent concurrent saves (auto vs manual)
    """

    def __init__(
        self,
        timer: QTimer,
        get_project_path: Callable[[], Path | None],
        save_project: Callable[[Path], bool],
        show_message: Callable[[str, int], None] | None = None,
        parent_widget: QWidget | None = None,
        on_save_success: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the auto-save manager.

        Args:
            timer: QTimer configured for debouncing (should be single-shot)
            get_project_path: Callable that returns the current project path
            save_project: Callable that saves the project to a given path
            show_message: Optional callable for status messages (message, duration_ms)
            parent_widget: Optional parent widget for error dialogs
            on_save_success: Optional callback invoked after successful save
        """
        super().__init__(parent_widget)
        self._timer = timer
        self._get_project_path = get_project_path
        self._save_project = save_project
        self._show_message = show_message
        self._parent_widget = parent_widget
        self._on_save_success = on_save_success
        self._save_in_progress = False
        # Keep reference to current worker to prevent GC during signal emission
        self._current_worker: _SaveWorker | None = None
        # Lock to prevent concurrent saves from auto-save and manual save
        self._save_lock = threading.Lock()

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

    def set_on_save_success(self, callback: Callable[[], None] | None) -> None:
        """Set the on_save_success callback for deferred injection.

        Args:
            callback: Callback to invoke after successful save, or None to disable
        """
        self._on_save_success = callback

    def try_acquire_save_lock(self) -> bool:
        """Try to acquire the save lock without blocking.

        Returns:
            True if lock was acquired, False if save already in progress
        """
        return self._save_lock.acquire(blocking=False)

    def release_save_lock(self) -> None:
        """Release the save lock.

        Should only be called if try_acquire_save_lock returned True.
        """
        self._save_lock.release()

    @property
    def is_save_in_progress(self) -> bool:
        """Check if a save operation is currently in progress.

        Returns:
            True if save in progress (lock held), False otherwise
        """
        return self._save_in_progress

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

        Saves the project in a background thread to avoid blocking UI.
        Shows a message on success or an error dialog on failure.
        """
        project_path = self._get_project_path()
        if not project_path:
            return

        # Try to acquire lock - if already held (by manual save), skip
        if not self.try_acquire_save_lock():
            logger.debug("Save lock held, skipping auto-save")
            return

        self._save_in_progress = True

        # Create and run worker in background thread
        # Keep reference to prevent GC during signal emission
        self._current_worker = _SaveWorker(self._save_project, project_path)
        # Use QueuedConnection to ensure handler runs on main thread (required for QMessageBox)
        self._current_worker.signals.finished.connect(self._on_save_finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(self._current_worker)

    def _on_save_finished(self, success: bool, error_message: str) -> None:
        """Handle completion of background save operation.

        Args:
            success: Whether the save succeeded
            error_message: Error message if save failed
        """
        self._save_in_progress = False
        self._current_worker = None  # Release reference
        self.release_save_lock()  # Release lock after save completes

        if success:
            if self._on_save_success:
                self._on_save_success()
            if self._show_message:
                self._show_message("Project auto-saved", 2000)
            logger.info("Auto-saved project to %s", self._get_project_path())
        else:
            logger.exception("Failed to auto-save project: %s", error_message)
            if self._parent_widget:
                QMessageBox.warning(
                    self._parent_widget,
                    "Auto-Save Failed",
                    f"Failed to save project: {error_message}\n\nPlease save manually.",
                )
