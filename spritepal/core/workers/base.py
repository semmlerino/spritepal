"""
Base worker classes for standardized async operations.

This module provides the foundation for all worker threads in SpritePal,
ensuring consistent interfaces, proper error handling, and type safety.
"""
from __future__ import annotations

import weakref
from abc import abstractmethod
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

from PySide6.QtCore import QMetaObject, QThread, Signal
from typing_extensions import override

if TYPE_CHECKING:
    from PySide6.QtCore import QObject
else:
    from PySide6.QtCore import QObject

if TYPE_CHECKING:
    from core.managers.factory import ManagerFactory

from core.managers.base_manager import BaseManager
from utils.constants import SLEEP_WORKER
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Type variables for proper type preservation in decorators
P = ParamSpec("P")
R = TypeVar("R")

def handle_worker_errors(
    operation_context: str = "operation",
    handle_interruption: bool = False,
    include_runtime_error: bool = False
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator for standardized worker exception handling.

    Handles the common exception patterns found across worker classes:
    - Re-raises InterruptedError for proper cancellation handling (or handles it if handle_interruption=True)
    - Catches file I/O errors: (OSError, IOError, PermissionError) - logs and emits signals
    - Catches data format errors: (ValueError, TypeError) - logs and emits signals
    - Optionally catches RuntimeError (for base class compatibility) - logs and emits signals
    - Catches general exceptions as fallback - logs and emits signals

    All handled exceptions emit both error and operation_finished signals for consistent error handling.

    Args:
        operation_context: Context string for error messages (e.g., "VRAM extraction")
        handle_interruption: If True, handles InterruptedError instead of re-raising
        include_runtime_error: If True, adds RuntimeError to the handled exceptions

    Returns:
        Decorated function that handles exceptions consistently

    Usage:
        @handle_worker_errors("VRAM extraction")
        def perform_operation(self) -> None:
            # Your operation code here
            pass
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Extract self from args for proper BaseWorker access
            self: BaseWorker = args[0]  # type: ignore[assignment]
            try:
                return func(*args, **kwargs)

            except InterruptedError:
                if handle_interruption:
                    logger.info(f"{self._operation_name}: Operation cancelled")
                    self.operation_finished.emit(False, "Operation cancelled")
                    return None  # type: ignore[return-value]  # Signal emission is the real result
                else:
                    # Re-raise cancellation to be handled by caller or base class
                    raise

            except (OSError, PermissionError) as e:
                error_msg = f"File I/O error during {operation_context}: {e!s}"
                logger.exception(f"{self._operation_name}: {error_msg}", exc_info=e)
                # Emit signals for error handling
                self.emit_error(error_msg, e)
                self.operation_finished.emit(False, error_msg)
                return None  # type: ignore[return-value]  # Signal emission is the real result

            except (ValueError, TypeError) as e:
                error_msg = f"Data format error during {operation_context}: {e!s}"
                logger.exception(f"{self._operation_name}: {error_msg}", exc_info=e)
                # Emit signals for error handling
                self.emit_error(error_msg, e)
                self.operation_finished.emit(False, error_msg)
                return None  # type: ignore[return-value]  # Signal emission is the real result

            except RuntimeError as e:
                if include_runtime_error:
                    error_msg = f"Runtime error during {operation_context}: {e!s}"
                    logger.exception(f"{self._operation_name}: {error_msg}", exc_info=e)
                    # Emit signals for error handling
                    self.emit_error(error_msg, e)
                    self.operation_finished.emit(False, error_msg)
                    return None  # type: ignore[return-value]  # Signal emission is the real result
                else:
                    # If not handling RuntimeError, let it propagate
                    raise

            except Exception as e:
                error_msg = f"{operation_context} failed: {e!s}"
                logger.exception(f"{self._operation_name}: {error_msg}", exc_info=e)
                # General exception catch: log AND emit signals
                self.emit_error(error_msg, e)
                self.operation_finished.emit(False, error_msg)
                return None  # type: ignore[return-value]  # Signal emission is the real result

        return wrapper
    return decorator

class WorkerMeta(type(QThread)):
    """Metaclass that properly combines QThread and ABC functionality."""

    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any) -> type:
        # First create the class with QThread metaclass
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Add ABC functionality manually for abstract methods
        if any(hasattr(base, '__abstractmethods__') for base in bases):
            # Collect abstract methods from all bases
            abstracts = set()
            for base in bases:
                if hasattr(base, '__abstractmethods__'):
                    abstracts.update(base.__abstractmethods__)

            # Add abstract methods from current class
            for name, value in namespace.items():
                if getattr(value, '__isabstractmethod__', False):
                    abstracts.add(name)

            # Remove implemented methods
            for method in list(abstracts):
                if method in namespace and not getattr(namespace[method], '__isabstractmethod__', False):
                    abstracts.discard(method)

            cls.__abstractmethods__ = frozenset(abstracts)  # type: ignore[attr-defined]  # Metaclass magic for ABCs

        return cls

class BaseWorker(QThread, metaclass=WorkerMeta):
    """
    Base class for all worker threads with standard signals and behavior.

    Provides:
    - Standard signal interface
    - Cancellation and pause support
    - Consistent error handling
    - Progress reporting utilities
    """

    # Standard signals all workers must have
    progress = Signal(int, str)  # percent (0-100), message
    error = Signal(str, Exception)  # message, exception
    warning = Signal(str)  # warning message

    # Standard finished signal - use this instead of QThread.finished
    operation_finished = Signal(bool, str)  # success, message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._is_cancelled = False
        self._is_paused = False
        self._operation_name = self.__class__.__name__
        self._signal_connections: list[QMetaObject.Connection] = []

        # Register cleanup to prevent signal leaks
        self.finished.connect(self._cleanup_connections)

    def _cleanup_connections(self) -> None:
        """Clean up signal connections to prevent memory leaks"""
        connection_count = len(self._signal_connections)
        for connection in self._signal_connections:
            try:
                QObject.disconnect(connection)
            except Exception as e:
                logger.debug(f"Error disconnecting signal: {e}")
        self._signal_connections.clear()
        logger.debug(f"{self._operation_name}: Cleaned up {connection_count} signal connections")

    def connect_signal_with_tracking(self, signal: Signal, slot: Callable[..., Any]) -> QMetaObject.Connection:
        """Connect a signal and track the connection for cleanup"""
        connection = signal.connect(slot)  # type: ignore[attr-defined]  # Signal.connect exists at runtime
        self._signal_connections.append(connection)
        return connection

    def cancel(self) -> None:
        """Request cancellation of the operation."""
        logger.debug(f"{self._operation_name}: Cancellation requested")
        self._is_cancelled = True

    def pause(self) -> None:
        """Request pause of the operation."""
        logger.debug(f"{self._operation_name}: Pause requested")
        self._is_paused = True

    def resume(self) -> None:
        """Resume paused operation."""
        logger.debug(f"{self._operation_name}: Resume requested")
        self._is_paused = False

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._is_cancelled

    @property
    def is_paused(self) -> bool:
        """Check if operation is paused."""
        return self._is_paused

    def emit_progress(self, percent: int, message: str = "") -> None:
        """
        Emit progress in a standard format.

        Args:
            percent: Progress percentage (0-100)
            message: Optional progress message
        """
        # Clamp percent to valid range
        percent = max(0, min(100, percent))
        self.progress.emit(percent, message)

        if message:
            logger.debug(f"{self._operation_name}: {percent}% - {message}")

    def emit_error(self, message: str, exception: Exception | None = None) -> None:
        """
        Emit error in a standard format.

        Args:
            message: Error message
            exception: Optional exception object
        """
        exc = exception or Exception(message)
        logger.error(f"{self._operation_name}: {message}", exc_info=exc)
        self.error.emit(message, exc)

    def emit_warning(self, message: str) -> None:
        """
        Emit warning message.

        Args:
            message: Warning message
        """
        logger.warning(f"{self._operation_name}: {message}")
        self.warning.emit(message)

    def check_cancellation(self) -> None:
        """
        Check if operation was cancelled and exit if so.

        This method checks both the internal cancellation flag and Qt's
        built-in interruption mechanism for maximum compatibility.

        Call this periodically in long-running operations.

        Raises:
            InterruptedError: If operation was cancelled via any mechanism
        """
        # Check internal cancellation flag (BaseWorker pattern)
        if self._is_cancelled:
            raise InterruptedError("Operation was cancelled")

        # Check Qt's built-in interruption mechanism
        if self.isInterruptionRequested():
            logger.debug(f"{self._operation_name}: Qt interruption detected")
            self._is_cancelled = True  # Update internal state for consistency
            raise InterruptedError("Operation was interrupted via Qt mechanism")

    def wait_if_paused(self) -> None:
        """
        Wait while operation is paused.

        Also respects Qt's interruption mechanism and cancellation flags.
        Call this periodically in long-running operations.
        """
        while self._is_paused and not self._is_cancelled and not self.isInterruptionRequested():
            self.msleep(int(SLEEP_WORKER * 1000))  # Sleep 100ms

        # If we exited due to Qt interruption, update internal state
        if self.isInterruptionRequested() and not self._is_cancelled:
            logger.debug(f"{self._operation_name}: Qt interruption detected during pause")
            self._is_cancelled = True

    @override
    @abstractmethod
    def run(self) -> None:
        """
        Subclasses must implement the actual work.

        Should emit operation_finished signal when complete.
        """

class ManagedWorker(BaseWorker):
    """
    Worker that delegates to a manager for business logic.

    This pattern ensures that business logic stays in managers
    while workers only handle Qt threading concerns.

    Supports both direct manager injection (legacy) and factory-based
    manager creation (recommended for new code).
    """

    # Additional signals for specialized worker operations
    preview_ready = Signal(object, int)  # PIL Image, tile_count
    preview_image_ready = Signal(object)  # PIL Image
    injection_finished = Signal(bool)  # success
    progress_percent = Signal(int)  # percentage (0-100)
    compression_info = Signal(str)  # compression info string
    palettes_ready = Signal(object)  # Palette data
    active_palettes_ready = Signal(object)  # Active palette indices

    def __init__(
        self,
        manager: BaseManager | None = None,
        manager_factory: ManagerFactory | None = None,
        parent: QObject | None = None
    ) -> None:
        super().__init__(parent)

        # Validate parameters
        if manager is not None and manager_factory is not None:
            raise ValueError("Cannot specify both manager and manager_factory")

        # Allow both to be None for delayed manager creation pattern
        # (subclass will create manager after super().__init__ completes)

        # Store for subclass use
        self.manager = manager
        self._manager_factory = manager_factory
        self._connections: list[QMetaObject.Connection] = []
        self._weak_manager_ref: weakref.ReferenceType[Any] | None = None

        # Store weak reference to manager to avoid circular references
        if manager is not None:
            self._weak_manager_ref = weakref.ref(manager)

        # If using factory pattern, manager will be created by subclass
        if manager_factory is not None:
            logger.debug(f"{self._operation_name}: Using factory-based manager creation")
        else:
            logger.debug(f"{self._operation_name}: Using direct manager injection")

    def connect_manager_signals(self) -> None:
        """
        Connect manager signals to worker signals.

        Subclasses should implement this to wire manager signals
        to the appropriate worker signals.
        """

    def disconnect_manager_signals(self) -> None:
        """Disconnect all manager signals for cleanup."""
        connection_count = len(self._connections)
        for connection in self._connections:
            try:
                QObject.disconnect(connection)
            except Exception as e:
                logger.debug(f"Error disconnecting signal: {e}")
        self._connections.clear()
        logger.debug(f"{self._operation_name}: Disconnected {connection_count} manager signals")

    @handle_worker_errors("managed operation", handle_interruption=True, include_runtime_error=True)
    def _execute_managed_operation(self) -> None:
        """Execute the core managed operation logic with decorator error handling."""
        logger.debug(f"{self._operation_name}: Starting managed operation")
        self.connect_manager_signals()
        self.perform_operation()

    @override
    def run(self) -> None:
        """
        Template method for managed operations.

        Handles the standard lifecycle:
        1. Connect manager signals
        2. Perform operation via manager
        3. Handle errors and cleanup
        4. Emit completion signal
        """
        try:
            self._execute_managed_operation()
        finally:
            self.disconnect_manager_signals()
            # Clear manager reference to prevent retention
            self._weak_manager_ref = None
            self.manager = None

    @abstractmethod
    def perform_operation(self) -> None:
        """
        Subclasses implement the manager delegation.

        Should call manager methods and emit operation_finished
        when complete.
        """
