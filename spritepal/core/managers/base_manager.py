"""
Base manager class providing common functionality for all managers
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

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

from .exceptions import ValidationError


class BaseManager(QObject):
    """Abstract base class for all manager classes"""

    # Dependency declaration for initialization ordering.
    # Subclasses should override this to declare which manager types they depend on.
    # The registry uses topological sort to determine safe initialization order.
    # Example: DEPENDS_ON: ClassVar[list[type[BaseManager]]] = [ApplicationStateManager]
    DEPENDS_ON: list[type[BaseManager]] = []

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

    def _with_operation_lock(self, operation: str, func: Callable[[], Any]) -> Any:
        """
        Execute a function with operation-specific locking

        Args:
            operation: Operation name for the lock
            func: Function to execute

        Returns:
            Result from the function
        """
        if operation not in self._operation_locks:
            self._operation_locks[operation] = threading.Lock()

        with self._operation_locks[operation]:
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

    def _validate_required(self, params: dict[str, Any], required: list[str]) -> None:
        """
        Validate that required parameters are present

        Args:
            params: Parameters to validate
            required: List of required parameter names

        Raises:
            ValidationError: If required parameters are missing
        """
        missing = [key for key in required if key not in params or params[key] is None]
        if missing:
            raise ValidationError(f"Missing required parameters: {', '.join(missing)}")

    def _validate_type(self, value: Any, name: str, expected_type: type[Any]) -> None:
        """
        Validate parameter type

        Args:
            value: Value to validate
            name: Parameter name for error messages
            expected_type: Expected type

        Raises:
            ValidationError: If type doesn't match
        """
        if not isinstance(value, expected_type):
            raise ValidationError(
                f"Invalid type for '{name}': expected {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )

    def _validate_file_exists(self, path: str, name: str) -> None:
        """
        Validate that a file exists

        Args:
            path: File path to check
            name: Parameter name for error messages

        Raises:
            ValidationError: If file doesn't exist
        """
        if not Path(path).exists():
            raise ValidationError(f"{name} does not exist: {path}")

    def _validate_range(self, value: int | float, name: str,
                       min_val: int | float | None = None,
                       max_val: int | float | None = None) -> None:
        """
        Validate that a numeric value is within range

        Args:
            value: Value to validate
            name: Parameter name for error messages
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)

        Raises:
            ValidationError: If value is out of range
        """
        if min_val is not None and value < min_val:
            raise ValidationError(f"{name} must be >= {min_val}, got {value}")
        if max_val is not None and value > max_val:
            raise ValidationError(f"{name} must be <= {max_val}, got {value}")

    def _handle_file_io_error(self, error: Exception, operation: str,
                             context: str = "") -> None:
        """
        Handle file I/O related errors with standardized logging and re-raising

        Args:
            error: The original exception (OSError, IOError, PermissionError)
            operation: Operation name for context
            context: Additional context for the error message

        Raises:
            Exception: Re-raises the exception with enhanced error message
        """
        context_suffix = f" {context}" if context else ""
        enhanced_msg = f"File I/O error during {operation}{context_suffix}: {error!s}"

        # Create exception of the same type with enhanced message
        enhanced_error = type(error)(enhanced_msg)
        enhanced_error.__cause__ = error

        self._handle_error(enhanced_error, operation)
        raise enhanced_error

    def _handle_data_format_error(self, error: Exception, operation: str,
                                 context: str = "") -> None:
        """
        Handle data format related errors with standardized logging and re-raising

        Args:
            error: The original exception (ValueError, TypeError, json.JSONDecodeError)
            operation: Operation name for context
            context: Additional context for the error message

        Raises:
            Exception: Re-raises the exception with enhanced error message
        """
        context_suffix = f" {context}" if context else ""
        enhanced_msg = f"Data format error during {operation}{context_suffix}: {error!s}"

        # Create exception of the same type with enhanced message
        enhanced_error = type(error)(enhanced_msg)
        enhanced_error.__cause__ = error

        self._handle_error(enhanced_error, operation)
        raise enhanced_error

    def _handle_operation_error(self, error: Exception, operation: str,
                               error_class: type[Exception],
                               context: str = "") -> None:
        """
        Handle operation-specific errors with standardized logging and re-raising

        Args:
            error: The original exception
            operation: Operation name for context
            error_class: Exception class to raise (e.g., ExtractionError, InjectionError)
            context: Additional context for the error message

        Raises:
            error_class: Re-raises as the specified exception type
        """
        context_suffix = f" {context}" if context else ""
        enhanced_msg = f"{operation.title()} failed{context_suffix}: {error!s}"

        # Create new exception of specified type
        enhanced_error = error_class(enhanced_msg)
        enhanced_error.__cause__ = error

        self._handle_error(enhanced_error, operation)
        raise enhanced_error
