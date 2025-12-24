"""
Base manager class providing common functionality for all managers
"""
from __future__ import annotations

import functools
import logging
import threading
from collections.abc import Callable, Mapping
from typing import Any, ParamSpec, TypeVar

# Type variable for generic _ensure_component method
T = TypeVar("T")
# ParamSpec for decorator type preservation
P = ParamSpec("P")

from PySide6.QtCore import QObject, Signal

try:
    from utils.logging_config import get_logger  # type: ignore[import]
except ImportError:
    # Fallback for when the module path is not available
    try:
        from utils.logging_config import get_logger  # type: ignore[import]
    except ImportError:
        # Final fallback to standard logging
        import logging
        def get_logger(name: str) -> logging.Logger:
            return logging.getLogger(name)

from core.exceptions import ValidationError


class BaseManager(QObject):
    """Abstract base class for all manager classes"""

    # Common signals that all managers can emit
    error_occurred = Signal(str)
    """Emitted on error. Args: error_message."""

    warning_occurred = Signal(str)
    """Emitted on warning. Args: warning_message."""

    operation_started = Signal(str)
    """Emitted when operation starts. Args: operation_name."""

    operation_finished = Signal(str)
    """Emitted when operation finishes. Args: operation_name."""

    progress_updated = Signal(str, int, int)
    """Emitted with progress. Args: operation_name, current, total."""

    def __init__(self, name: str | None = None, parent: QObject | None = None) -> None:
        """
        Initialize base manager

        Args:
            name: manager name for logging
            parent: Qt parent object for proper lifecycle management
        """
        super().__init__(parent)

        # Set up logger with module-specific naming
        self._name: str = name or self.__class__.__name__
        self._logger: logging.Logger = get_logger(f"managers.{self._name}")

        # Thread safety
        self._lock: threading.RLock = threading.RLock()
        self._operation_locks: dict[str, threading.Lock] = {}

        # State tracking
        self._is_initialized: bool = False
        self._active_operations: set[str] = set()
        self._initializing: bool = True  # Flag to prevent cross-manager access during init

        # Initialize the manager
        try:
            self._initialize()
        finally:
            self._initializing = False  # Clear flag regardless of success/failure

    def _initialize(self) -> None:
        """Initialize the manager - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement _initialize()")

    def cleanup(self) -> None:
        """Cleanup resources - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement cleanup()")

    def get_name(self) -> str:
        """Get the manager name"""
        return self._name

    def is_initialized(self) -> bool:
        """Check if manager is initialized"""
        return self._is_initialized

    def is_initializing(self) -> bool:
        """Check if manager is currently initializing"""
        return self._initializing

    def is_operation_active(self, operation: str) -> bool:
        """Check if a specific operation is currently active"""
        with self._lock:
            return operation in self._active_operations

    def has_active_operations(self) -> bool:
        """Check if any operations are currently active"""
        with self._lock:
            return len(self._active_operations) > 0

    def _start_operation(self, operation: str) -> bool:
        """
        Mark an operation as started

        Args:
            operation: Operation name

        Returns:
            True if operation started, False if already running
        """
        with self._lock:
            if operation in self._active_operations:
                self._logger.warning(f"Operation '{operation}' is already active")
                return False

            self._active_operations.add(operation)
            self.operation_started.emit(operation)
            self._logger.debug(f"Started operation: {operation}")
            return True

    def _finish_operation(self, operation: str) -> None:
        """
        Mark an operation as finished

        Args:
            operation: Operation name
        """
        with self._lock:
            if operation in self._active_operations:
                self._active_operations.remove(operation)
                self.operation_finished.emit(operation)
                self._logger.debug(f"Finished operation: {operation}")

    def _with_operation_lock(self, operation: str, func: Callable[[], object]) -> object:
        """
        Execute a function with operation-specific locking

        Args:
            operation: Operation name for the lock
            func: Function to execute

        Returns:
            Result from the function
        """
        # Atomic check-and-set under RLock to prevent race condition
        # where two threads could create different Lock objects
        with self._lock:
            if operation not in self._operation_locks:
                self._operation_locks[operation] = threading.Lock()
            op_lock = self._operation_locks[operation]

        with op_lock:
            return func()

    def _handle_error(self, error: Exception, operation: str | None = None) -> None:
        """
        Handle an error with logging and signal emission

        Args:
            error: The exception that occurred
            operation: operation name for context
        """
        error_msg = str(error)
        if operation:
            error_msg = f"{operation}: {error_msg}"

        self._logger.error(error_msg)
        self.error_occurred.emit(error_msg)

        # Finish the operation if it was active
        if operation:
            self._finish_operation(operation)

    def _handle_warning(self, message: str) -> None:
        """
        Handle a warning with logging and signal emission

        Args:
            message: Warning message
        """
        self._logger.warning(message)
        self.warning_occurred.emit(message)

    def _update_progress(self, operation: str, current: int, total: int) -> None:
        """
        Update operation progress

        Args:
            operation: Operation name
            current: Current progress value
            total: Total progress value
        """
        self.progress_updated.emit(operation, current, total)

    def _on_worker_progress_adapter(self, *args: object) -> None:
        """Adapter to handle different worker progress signal signatures.

        Different workers emit different signals:
        - core/workers: Signal(int, str) -> (percent, message)
        - ui/workers: Signal(str) -> (message,)

        This adapter normalizes both to extract the message and calls
        ``_on_worker_progress(message)``. Subclasses must implement
        ``_on_worker_progress`` to handle the normalized message.
        """
        if len(args) == 1:
            # Signal(str) - message only
            message = str(args[0])
        elif len(args) >= 2:
            # Signal(int, str) - (percent, message)
            message = str(args[1])
        else:
            message = ""
        self._on_worker_progress(message)

    def _on_worker_progress(self, message: str) -> None:
        """Handle normalized worker progress message.

        Subclasses should override to emit domain-specific signals.
        Default implementation emits the generic ``progress_updated`` signal.

        Args:
            message: Progress message from worker
        """
        self.progress_updated.emit(message)

    def _handle_worker_completion(
        self, operation: str, success: bool, message: str
    ) -> None:
        """Handle common worker completion logic.

        Finishes the operation tracking and logs the result. Subclasses should
        call this, then emit their domain-specific completion signal.

        Args:
            operation: Operation name (e.g., "injection", "extraction")
            success: Whether the operation succeeded
            message: Completion message
        """
        self._finish_operation(operation)

        if success:
            self._logger.info(f"{operation.title()} completed successfully: {message}")
        else:
            self._logger.error(f"{operation.title()} failed: {message}")

    def _validate_required(self, params: Mapping[str, object], required: list[str]) -> None:
        """
        Validate that required parameters are present.

        Delegates to utils.validation.validate_required_params.
        """
        from utils.validation import validate_required_params

        validate_required_params(params, required)

    def _validate_type(self, value: object, name: str, expected_type: type[object]) -> None:
        """
        Validate parameter type.

        Delegates to utils.validation.validate_type.
        """
        from utils.validation import validate_type

        validate_type(value, name, expected_type)

    def _validate_range(
        self,
        value: int | float,
        name: str,
        min_val: int | float | None = None,
        max_val: int | float | None = None,
    ) -> None:
        """
        Validate that a numeric value is within range.

        Delegates to utils.validation.validate_range.
        """
        from utils.validation import validate_range

        validate_range(value, name, min_val, max_val)

    def _ensure_component(
        self,
        component: T | None,
        name: str,
        error_type: type[Exception] = RuntimeError,
    ) -> T:
        """
        Ensure a component is initialized and return it.

        Delegates to utils.validation.ensure_component.
        """
        from utils.validation import ensure_component

        return ensure_component(component, name, error_type)

    def _handle_categorized_error(
        self,
        error: Exception,
        operation: str,
        category: str,
        context: str = "",
        error_class: type[Exception] | None = None,
    ) -> None:
        """Handle errors with standardized logging and re-raising.

        This is a unified error handler that replaces the separate
        _handle_file_io_error, _handle_data_format_error, and
        _handle_operation_error methods.

        Args:
            error: The original exception
            operation: Operation name for context
            category: Error category for the message (e.g., "File I/O", "Data format")
            context: Additional context for the error message
            error_class: Exception class to raise. If None, uses original error type.

        Raises:
            Exception: Re-raises with enhanced error message
        """
        context_suffix = f" {context}" if context else ""
        enhanced_msg = f"{category} error during {operation}{context_suffix}: {error!s}"

        # Use specified error class or keep original type
        exc_class = error_class if error_class is not None else type(error)
        enhanced_error = exc_class(enhanced_msg)
        enhanced_error.__cause__ = error

        self._handle_error(enhanced_error, operation)
        raise enhanced_error

    # Convenience wrappers for backwards compatibility
    def _handle_file_io_error(
        self, error: Exception, operation: str, context: str = ""
    ) -> None:
        """Handle file I/O errors. Wrapper for _handle_categorized_error."""
        self._handle_categorized_error(error, operation, "File I/O", context)

    def _handle_data_format_error(
        self, error: Exception, operation: str, context: str = ""
    ) -> None:
        """Handle data format errors. Wrapper for _handle_categorized_error."""
        self._handle_categorized_error(error, operation, "Data format", context)

    def _handle_operation_error(
        self,
        error: Exception,
        operation: str,
        error_class: type[Exception],
        context: str = "",
    ) -> None:
        """Handle operation-specific errors. Wrapper for _handle_categorized_error."""
        self._handle_categorized_error(
            error, operation, operation.title(), context, error_class
        )


def with_operation_handling(
    operation: str,
    context: str,
    *,
    with_progress: bool = True,
    exclusive: bool = True,
    target_error: type[Exception] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for operations with standardized error handling.

    Handles:
    - Operation lifecycle (start/finish)
    - Progress updates (optional)
    - Categorized exception handling for File I/O, data format, and general errors

    Args:
        operation: Operation identifier for tracking
        context: Human-readable context for error messages
        with_progress: If True, emit progress at 0% and 100%
        exclusive: If True, raise if operation already in progress
        target_error: Exception type for wrapping unexpected errors (default: Exception)

    Usage:
        @with_operation_handling("extraction", "file extraction", with_progress=True)
        def extract(self, path: str) -> list[str]:
            return self._service.extract(path)
    """
    final_target_error = target_error if target_error is not None else Exception

    def decorator(method: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(method)
        def wrapper(
            self: BaseManager, *args: Any, **kwargs: Any  # pyright: ignore[reportExplicitAny] - generic decorator
        ) -> T:
            started = self._start_operation(operation)
            if exclusive and not started:
                raise final_target_error(f"{operation} already in progress")

            try:
                if with_progress:
                    self._update_progress(operation, 0, 100)
                result = method(self, *args, **kwargs)
                if with_progress:
                    self._update_progress(operation, 100, 100)
                return result
            except (OSError, PermissionError) as e:
                self._handle_file_io_error(e, operation, context)
                raise  # Handler already raises, but kept for safety/clarity
            except (ValueError, TypeError) as e:
                self._handle_data_format_error(e, operation, context)
                raise
            except ValidationError:
                raise
            except Exception as e:
                if not isinstance(e, final_target_error):
                    self._handle_operation_error(e, operation, final_target_error, context)
                raise
            finally:
                if started:
                    self._finish_operation(operation)

        return wrapper

    return decorator
