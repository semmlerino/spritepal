#!/usr/bin/env python3
"""
Base worker class for threaded operations.
Provides common functionality for all worker threads.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


class BaseWorker(QThread):
    """Base class for worker threads with common signals and error handling."""

    progress = Signal(int, str)  # Progress percentage (0-100), message
    error = Signal(str)  # Error message
    finished_signal = Signal()  # Operation completed

    def __init__(
        self,
        file_path: str | Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the base worker.

        Args:
            file_path: Optional file path (string or Path object)
            parent: Parent QObject for proper cleanup
        """
        super().__init__(parent)
        self._is_cancelled = False
        self._file_path: Path | None = None

        if file_path is not None:
            self._file_path = (
                Path(file_path) if not isinstance(file_path, Path) else file_path
            )

    def cancel(self) -> None:
        """Request cancellation of the worker thread."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._is_cancelled

    @property
    def file_path(self) -> Path | None:
        """Get the file path as a Path object (read-only)."""
        return self._file_path

    def validate_file_path(self, must_exist: bool = True) -> bool:
        """Validate the file path.

        Args:
            must_exist: If True, check that the file exists

        Returns:
            True if valid, False otherwise
        """
        if self._file_path is None:
            self.emit_error("No file path provided")
            return False

        if must_exist and not self._file_path.exists():
            self.emit_error(f"File not found: {self._file_path}")
            return False

        return True

    def emit_progress(self, value: int, message: str = "") -> None:
        """Emit progress signal if not cancelled.

        Args:
            value: Progress percentage (0-100)
            message: Optional progress message
        """
        if not self._is_cancelled:
            self.progress.emit(value, message)

    def emit_error(self, message: str) -> None:
        """Emit error signal with formatted message."""
        if not self._is_cancelled:
            logger.error(f"Worker error: {message}")
            self.error.emit(message)

    def emit_finished(self) -> None:
        """Emit finished signal if not cancelled."""
        if not self._is_cancelled:
            self.finished_signal.emit()

    def handle_exception(self, exception: Exception) -> None:
        """Handle an exception by emitting it as an error."""
        self.emit_error(str(exception))
