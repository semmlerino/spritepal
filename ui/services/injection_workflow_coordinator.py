"""Injection workflow coordination service.

Extracted from MainWindow to manage injection orchestration including:
- Injection workflow (VRAM and ROM modes)
- Signal connection management
- Progress and completion handling
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QMetaObject, QObject, Signal

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from core.app_context import AppContext

logger = get_logger(__name__)


class InjectionWorkflowCoordinator(QObject):
    """Coordinates injection workflows (VRAM/ROM).

    This service handles injection orchestration that was previously
    in MainWindow, providing a cleaner separation of concerns.

    Signals:
        injection_started(): Emitted when injection begins
        injection_progress(str): Emitted during injection (message)
        injection_finished(bool, str): Emitted when injection completes (success, message)

    Usage:
        coordinator = InjectionWorkflowCoordinator(app_context)
        coordinator.injection_finished.connect(my_handler)
        coordinator.start_injection(params)
    """

    injection_started = Signal()
    injection_progress = Signal(str)  # message
    injection_finished = Signal(bool, str)  # success, message

    def __init__(self, app_context: AppContext) -> None:
        """Initialize the injection workflow coordinator.

        Args:
            app_context: Application context with managers and services
        """
        super().__init__()
        self._app_context = app_context
        self._progress_connection: QMetaObject.Connection | None = None
        self._finished_connection: QMetaObject.Connection | None = None

    @property
    def core_operations_manager(self):
        """Access to core operations manager for signal connections."""
        return self._app_context.core_operations_manager

    def start_injection(self, params: Mapping[str, object]) -> bool:
        """Start injection workflow.

        Connects to manager signals, starts the injection, and handles
        forwarding progress/completion signals. Connection cleanup is
        automatic when injection completes.

        Args:
            params: Injection parameters dict containing:
                - mode: "vram" or "rom"
                - sprite_path: Path to sprite PNG file
                - For VRAM: input_vram, output_vram, offset
                - For ROM: input_rom, output_rom, offset, fast_compression
                - Optional: metadata_path

        Returns:
            True if injection started successfully, False otherwise
        """
        logger.debug("Starting injection workflow")

        try:
            manager = self.core_operations_manager

            # Connect to manager signals before starting
            self._progress_connection = manager.injection_progress.connect(self._on_progress)
            self._finished_connection = manager.injection_finished.connect(self._on_finished)

            # Emit started signal
            self.injection_started.emit()

            # Start injection via manager
            success = manager.start_injection(params)

            if not success:
                logger.warning("Injection failed to start")
                self._cleanup_connections()

            return success

        except Exception as e:
            logger.exception("Error starting injection")
            self._cleanup_connections()
            self.injection_finished.emit(False, f"Injection error: {e}")
            return False

    def _on_progress(self, message: str) -> None:
        """Handle injection progress updates.

        Args:
            message: Progress message from manager
        """
        logger.debug(f"Injection progress: {message}")
        self.injection_progress.emit(message)

    def _on_finished(self, success: bool, message: str) -> None:
        """Handle injection completion.

        Args:
            success: Whether injection completed successfully
            message: Completion message from manager
        """
        if success:
            logger.debug(f"Injection completed: {message}")
        else:
            logger.error(f"Injection failed: {message}")

        self._cleanup_connections()
        self.injection_finished.emit(success, message)

    def _cleanup_connections(self) -> None:
        """Cleanup manager signal connections."""
        from PySide6.QtCore import QObject

        if self._progress_connection is not None:
            try:
                QObject.disconnect(self._progress_connection)
            except (RuntimeError, TypeError):
                pass
            self._progress_connection = None

        if self._finished_connection is not None:
            try:
                QObject.disconnect(self._finished_connection)
            except (RuntimeError, TypeError):
                pass
            self._finished_connection = None
