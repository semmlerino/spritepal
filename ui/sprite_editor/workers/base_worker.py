#!/usr/bin/env python3
"""
Base worker class for threaded operations.
Provides common functionality for all worker threads.
"""

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from utils.logging_config import get_logger

logger = get_logger(__name__)


class BaseWorker(QThread):
    """Base class for worker threads with common signals and error handling.

    This class provides:
    - Standard signal interface (progress, error, finished_signal)
    - Cancellation support (via cancel() method)
    - Auto-registration with WorkerManager for cleanup on app shutdown
    """

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
            self._file_path = Path(file_path) if not isinstance(file_path, Path) else file_path

        # Auto-register with WorkerManager for cleanup_all() on app shutdown
        from core.services.worker_lifecycle import WorkerManager

        WorkerManager._register_worker(self)

    def cancel(self) -> None:
        """Request cancellation of the worker thread.

        Uses both internal flag and Qt's requestInterruption() for robust cancellation.
        """
        self._is_cancelled = True
        self.requestInterruption()

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested via any mechanism.

        Returns True if cancel() was called OR if Qt's requestInterruption() was called.
        """
        return self._is_cancelled or self.isInterruptionRequested()

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
        self.emit_finished()
