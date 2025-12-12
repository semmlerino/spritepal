"""
Unified error handling service for SpritePal.

DEPRECATED: This module is deprecated in favor of the simpler error handling pattern:
- Use `core.protocols.error_handler_protocol.ErrorHandlerProtocol` for the interface
- Use `core.console_error_handler.ConsoleErrorHandler` for console/file logging
- Use `ui.common.error_handler.ErrorHandler` for Qt UI-based error display

This module remains for backward compatibility but will be removed in a future version.
New code should use ErrorHandlerProtocol and ConsoleErrorHandler instead.

Original description:
This module provides a comprehensive error handling system that standardizes
error processing, categorization, and recovery across the entire application.
It builds upon the existing error_handler.py and integrates with all error patterns.
"""

from __future__ import annotations

import logging
import threading
import traceback
import weakref
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget as _QWidget

# Import core exceptions - these should always be available
from core.exceptions import (
    CacheError,
    ExtractionError,
    FileOperationError,
    InjectionError,
    PreviewError,
    SessionError,
    ValidationError,
)

# Import Qt modules with fallbacks for headless environments
try:
    from PySide6.QtCore import QObject as QtQObject, Signal as QtPyqtSignal
    from PySide6.QtWidgets import QMessageBox as QtQMessageBox, QWidget as QtQWidget
    QT_AVAILABLE = True

    # Use Qt classes directly
    QObject = QtQObject  # type: ignore[misc]
    Signal = QtPyqtSignal  # type: ignore[misc]
    QMessageBox = QtQMessageBox  # type: ignore[misc]
    QWidget = QtQWidget
except ImportError:
    # Fallback for environments without Qt
    QT_AVAILABLE = False
    import sys

    # Create functional fallback classes for non-Qt environments
    class QObject:
        """Functional QObject fallback for non-Qt environments."""
        def __init__(self, parent: Any = None):
            self.parent = parent
            self._signals = {}

    class _FallbackSignal:
        """Functional signal implementation with weak reference support for non-Qt environments."""

        def __init__(self, *args: Any):
            self._callbacks: list[Any] = []
            self._arg_types = args

        def _create_reference(self, callback: Callable[..., Any]) -> Any:
            """Create appropriate reference for the callback."""
            if hasattr(callback, '__self__') and hasattr(callback, '__func__'):
                # Bound method (instance method) - use WeakMethod
                return weakref.WeakMethod(callback)
            if hasattr(callback, '__self__'):
                # Callable object with __self__ - use weakref.ref
                return weakref.ref(callback)
            # Regular function, lambda, static method, etc. - store directly
            return callback

        def _get_callback_from_ref(self, ref: Any) -> Callable[..., Any] | None:
            """Get actual callback from reference, handling weak refs."""
            if isinstance(ref, (weakref.ref, weakref.WeakMethod)):
                callback = ref()
                return callback  # None if dead reference
            return ref  # Direct reference

        def _is_same_callback(self, ref: Any, target_callback: Callable[..., Any]) -> bool:
            """Check if reference points to the same callback."""
            current_callback = self._get_callback_from_ref(ref)
            return current_callback is not None and current_callback == target_callback

        def emit(self, *args: Any, **kwargs: Any) -> None:
            """Emit signal to all connected callbacks."""
            dead_refs = []

            # Call all live callbacks and collect dead references
            for i, ref in enumerate(self._callbacks):
                callback = self._get_callback_from_ref(ref)

                if callback is None:
                    # Weak reference is dead - mark for cleanup
                    dead_refs.append(i)
                    continue

                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    # Log but don't raise - match Qt behavior
                    print(f"Error in signal callback: {e}", file=sys.stderr)

            # Clean up dead references (in reverse order to maintain indices)
            for i in reversed(dead_refs):
                del self._callbacks[i]

        def connect(self, callback: Callable[..., Any]) -> None:
            """Connect a callback to this signal."""
            if self._is_already_connected(callback):
                return

            ref = self._create_reference(callback)
            self._callbacks.append(ref)

        def _is_already_connected(self, callback: Callable[..., Any]) -> bool:
            """Check if callback is already connected."""
            return any(self._is_same_callback(ref, callback) for ref in self._callbacks)

        def disconnect(self, callback: Callable[..., Any] | None = None) -> None:
            """Disconnect callback(s) from this signal."""
            if callback is None:
                self._callbacks.clear()
            else:
                # Remove all matching callbacks
                self._callbacks = [
                    ref for ref in self._callbacks
                    if not self._is_same_callback(ref, callback)
                ]

    def Signal(*args: Any, **kwargs: Any) -> _FallbackSignal:
        """Create a functional signal for non-Qt environments."""
        return _FallbackSignal(*args)

    class QMessageBox:
        """Console-based message box fallback for non-Qt environments."""
        @staticmethod
        def information(parent: Any, title: str, message: str) -> None:
            """Display information message to console."""
            print(f"\n[INFO] {title}: {message}\n", file=sys.stderr)

        @staticmethod
        def warning(parent: Any, title: str, message: str) -> None:
            """Display warning message to console."""
            print(f"\n[WARNING] {title}: {message}\n", file=sys.stderr)

        @staticmethod
        def critical(parent: Any, title: str, message: str) -> None:
            """Display critical error message to console."""
            print(f"\n[CRITICAL ERROR] {title}: {message}\n", file=sys.stderr)

if TYPE_CHECKING:
    from collections.abc import Generator
    try:
        from PySide6.QtWidgets import QWidget  # type: ignore[import-not-found]
    except ImportError:
        QWidget = None

class IErrorDisplay(Protocol):
    """Protocol for error display handlers to break circular dependency"""
    def handle_critical_error(self, title: str, message: str) -> None: ...
    def handle_warning(self, title: str, message: str) -> None: ...
    def handle_info(self, title: str, message: str) -> None: ...

# Create a simple console-based error display as default
class ConsoleErrorDisplay:
    """Simple console-based error display"""
    def handle_critical_error(self, title: str, message: str) -> None:
        print(f"CRITICAL: {title} - {message}")

    def handle_warning(self, title: str, message: str) -> None:
        print(f"WARNING: {title} - {message}")

    def handle_info(self, title: str, message: str) -> None:
        print(f"INFO: {title} - {message}")

# Get logger directly without circular import
logger = logging.getLogger(f"spritepal.{__name__}")

class ErrorSeverity(Enum):
    """Error severity levels for categorization"""
    CRITICAL = "critical"      # App-breaking errors
    HIGH = "high"              # Major functionality issues
    MEDIUM = "medium"          # Minor functionality issues
    LOW = "low"                # Warnings and notices
    INFO = "info"              # Informational messages

class ErrorCategory(Enum):
    """Error categories for specialized handling"""
    FILE_IO = "file_io"                # File operations
    VALIDATION = "validation"          # Input validation
    WORKER_THREAD = "worker_thread"    # Worker thread operations
    QT_GUI = "qt_gui"                  # Qt GUI operations
    EXTRACTION = "extraction"          # Sprite/ROM extraction
    INJECTION = "injection"            # Sprite/ROM injection
    CACHE = "cache"                    # Cache operations
    SESSION = "session"                # Session/settings
    PREVIEW = "preview"                # Preview generation
    NETWORK = "network"                # Network operations
    SYSTEM = "system"                  # System-level errors
    UNKNOWN = "unknown"                # Uncategorized

@dataclass
class ErrorContext:
    """Context information for error handling"""
    operation: str                     # What operation was being performed
    file_path: str | None = None    # File being operated on
    user_input: str | None = None   # User input that caused error
    component: str | None = None    # UI component or module name
    recovery_possible: bool = True     # Whether recovery is possible
    additional_info: dict[str, Any] | None = None  # Extra context data

@dataclass
class ErrorResult:
    """Result of error handling operation"""
    handled: bool                      # Whether error was handled
    severity: ErrorSeverity           # Determined severity
    category: ErrorCategory           # Determined category
    message: str                      # User-friendly message
    technical_details: str            # Technical error details
    recovery_suggestions: list[str]   # Suggested recovery actions
    should_retry: bool = False        # Whether operation should be retried
    should_abort: bool = False        # Whether operation should be aborted

class UnifiedErrorHandler(QObject):
    """
    Unified error handling service that standardizes error processing.

    This class provides:
    - Context-aware error categorization
    - Standardized error message formatting
    - Recovery suggestion generation
    - Integration with existing error handling patterns
    - Support for error chaining and nested contexts
    """

    # Signals for different error types (extends existing ErrorHandler)
    error_processed = Signal(ErrorResult)
    recovery_suggested = Signal(str, list)  # operation, suggestions

    def __init__(self, parent: _QWidget | None = None, error_display: IErrorDisplay | None = None):
        """Initialize the unified error handler

        Args:
            parent: Parent widget for Qt integration
            error_display: Error display handler (injected to break circular dependency)
        """
        super().__init__(parent)
        self._error_display = error_display or ConsoleErrorDisplay()
        self._context_stack: list[ErrorContext] = []
        self._error_count = 0
        self._error_history: list[tuple[Exception, ErrorContext]] = []
        self._max_history = 50

        # Error category mappings
        self._exception_category_map = {
            FileOperationError: ErrorCategory.FILE_IO,
            InterruptedError: ErrorCategory.WORKER_THREAD,  # Check before OSError
            OSError: ErrorCategory.FILE_IO,
            IOError: ErrorCategory.FILE_IO,
            PermissionError: ErrorCategory.FILE_IO,
            ValidationError: ErrorCategory.VALIDATION,
            ValueError: ErrorCategory.VALIDATION,
            TypeError: ErrorCategory.VALIDATION,
            ExtractionError: ErrorCategory.EXTRACTION,
            InjectionError: ErrorCategory.INJECTION,
            CacheError: ErrorCategory.CACHE,
            SessionError: ErrorCategory.SESSION,
            PreviewError: ErrorCategory.PREVIEW,
            RuntimeError: ErrorCategory.SYSTEM,
        }

        # Recovery suggestion templates
        self._recovery_suggestions = {
            ErrorCategory.FILE_IO: [
                "Verify the file path exists and is accessible",
                "Check file permissions",
                "Ensure sufficient disk space",
                "Try selecting a different file",
            ],
            ErrorCategory.VALIDATION: [
                "Check input parameters are valid",
                "Verify data format matches requirements",
                "Review input constraints in documentation",
            ],
            ErrorCategory.WORKER_THREAD: [
                "Try the operation again",
                "Check if required resources are available",
                "Restart the application if the issue persists",
            ],
            ErrorCategory.EXTRACTION: [
                "Verify ROM file is valid and not corrupted",
                "Check if ROM format is supported",
                "Try different extraction parameters",
            ],
            ErrorCategory.INJECTION: [
                "Verify target file is writable",
                "Check if injection data is valid",
                "Ensure target format compatibility",
            ],
            ErrorCategory.CACHE: [
                "Clear application cache",
                "Check available disk space",
                "Restart the application",
            ],
        }

    @contextmanager
    def error_context(
        self,
        operation: str,
        **context_kwargs: Any
    ) -> Generator[ErrorContext, None, None]:
        """
        Context manager for error handling operations.

        Usage:
            with error_handler.error_context("extracting sprites", file_path="rom.smc"):
                # Operation that might fail
                result = risky_operation()
        """
        context = ErrorContext(operation=operation, **context_kwargs)
        self._context_stack.append(context)

        try:
            yield context
        except Exception as e:
            # Automatically handle any exception that occurs in the context
            self.handle_exception(e, context)
            raise
        finally:
            if self._context_stack and self._context_stack[-1] == context:
                self._context_stack.pop()

    def handle_file_error(
        self,
        error: OSError,
        file_path: str,
        operation: str,
        **context_kwargs: Any
    ) -> ErrorResult:
        """Handle file-related errors with specific context"""
        context = ErrorContext(
            operation=operation,
            file_path=file_path,
            **context_kwargs
        )
        return self._process_error(error, context, ErrorCategory.FILE_IO)

    def handle_validation_error(
        self,
        error: ValidationError | ValueError | TypeError | Exception,
        context_info: str,
        user_input: str | None = None,
        **context_kwargs: Any
    ) -> ErrorResult:
        """Handle validation errors with input context"""
        # Convert non-ValidationError exceptions to ValidationError for consistency
        if not isinstance(error, ValidationError):
            if isinstance(error, (ValueError, TypeError)):
                # Convert common validation-related exceptions
                validation_error = ValidationError(str(error))
                validation_error.__cause__ = error  # Preserve original exception
            else:
                # For other exception types, wrap them
                validation_error = ValidationError(f"Validation failed: {error!s}")
                validation_error.__cause__ = error
            error = validation_error

        context = ErrorContext(
            operation=context_info,
            user_input=user_input,
            **context_kwargs
        )
        return self._process_error(error, context, ErrorCategory.VALIDATION)

    def handle_worker_error(
        self,
        error: Exception,
        worker_name: str,
        operation: str,
        **context_kwargs: Any
    ) -> ErrorResult:
        """Handle worker thread errors"""
        context = ErrorContext(
            operation=operation,
            component=worker_name,
            **context_kwargs
        )
        
        # Determine category from exception
        category = self._categorize_exception(error)
        
        # If it's unknown, fall back to worker thread category
        if category == ErrorCategory.UNKNOWN:
            category = ErrorCategory.WORKER_THREAD
            
        return self._process_error(error, context, category)

    def handle_qt_error(
        self,
        error: Exception,
        component: str,
        operation: str,
        **context_kwargs: Any
    ) -> ErrorResult:
        """Handle Qt GUI-related errors"""
        context = ErrorContext(
            operation=operation,
            component=component,
            **context_kwargs
        )
        return self._process_error(error, context, ErrorCategory.QT_GUI)

    def handle_exception(
        self,
        error: Exception,
        context: ErrorContext | None = None,
        category: ErrorCategory | None = None
    ) -> ErrorResult:
        """
        General exception handler with automatic categorization.

        This is the main entry point for handling any exception.
        """
        # Use current context if none provided
        if context is None and self._context_stack:
            context = self._context_stack[-1]
        elif context is None:
            context = ErrorContext(operation="unknown operation")

        # Auto-determine category if not provided
        if category is None:
            category = self._categorize_exception(error)

        return self._process_error(error, context, category)

    def _process_error(
        self,
        error: Exception,
        context: ErrorContext,
        category: ErrorCategory
    ) -> ErrorResult:
        """Core error processing logic"""
        self._error_count += 1

        # Add to history
        self._add_to_history(error, context)

        # Determine severity
        severity = self._determine_severity(error, category, context)

        # Generate user-friendly message
        user_message = self._format_user_message(error, context, category)

        # Get technical details
        technical_details = self._format_technical_details(error, context)

        # Generate recovery suggestions
        recovery_suggestions = self._generate_recovery_suggestions(
            error, category, context
        )

        # Determine action recommendations
        should_retry = self._should_suggest_retry(error, category)
        should_abort = self._should_suggest_abort(error, severity)

        # Create result
        result = ErrorResult(
            handled=True,
            severity=severity,
            category=category,
            message=user_message,
            technical_details=technical_details,
            recovery_suggestions=recovery_suggestions,
            should_retry=should_retry,
            should_abort=should_abort
        )

        # Log the error
        self._log_error(error, context, result)

        # Emit signals
        self.error_processed.emit(result)
        if recovery_suggestions:
            self.recovery_suggested.emit(context.operation, recovery_suggestions)

        # Integrate with existing error handler for UI display
        self._integrate_with_existing_handler(result)

        return result

    def _categorize_exception(self, error: Exception) -> ErrorCategory:
        """Automatically categorize an exception"""
        for exc_type, category in self._exception_category_map.items():
            if isinstance(error, exc_type):
                return category
        return ErrorCategory.UNKNOWN

    def _determine_severity(
        self,
        error: Exception,
        category: ErrorCategory,
        context: ErrorContext
    ) -> ErrorSeverity:
        """Determine error severity based on exception and context"""
        # Critical errors
        if isinstance(error, (MemoryError, SystemError)):
            return ErrorSeverity.CRITICAL

        # High severity for core functionality
        if category in (ErrorCategory.EXTRACTION, ErrorCategory.INJECTION):
            return ErrorSeverity.HIGH

        # Medium severity for file operations
        if category == ErrorCategory.FILE_IO:
            if isinstance(error, PermissionError):
                return ErrorSeverity.HIGH
            return ErrorSeverity.MEDIUM

        # Low severity for validation
        if category == ErrorCategory.VALIDATION:
            return ErrorSeverity.LOW

        # Default to medium
        return ErrorSeverity.MEDIUM

    def _format_user_message(
        self,
        error: Exception,
        context: ErrorContext,
        category: ErrorCategory
    ) -> str:
        """Format a user-friendly error message"""
        operation = context.operation

        # Define message templates for each category
        category_templates = {
            ErrorCategory.FILE_IO: self._format_file_io_message,
            ErrorCategory.VALIDATION: self._format_validation_message,
        }

        # Simple category messages
        simple_messages = {
            ErrorCategory.WORKER_THREAD: f"Background operation '{operation}' failed: {error!s}",
            ErrorCategory.EXTRACTION: f"Sprite extraction failed during {operation}: {error!s}",
            ErrorCategory.INJECTION: f"Sprite injection failed during {operation}: {error!s}",
            ErrorCategory.CACHE: f"Cache operation failed during {operation}: {error!s}",
        }

        # Use specific formatter if available
        if category in category_templates:
            return category_templates[category](operation, error, context)

        # Use simple message if available
        if category in simple_messages:
            return simple_messages[category]

        # Default message
        return f"Error during {operation}: {error!s}"

    def _format_file_io_message(self, operation: str, error: Exception, context: ErrorContext) -> str:
        """Format file I/O specific error message"""
        if context.file_path:
            return f"Failed to {operation} file '{context.file_path}': {error!s}"
        return f"File operation failed during {operation}: {error!s}"

    def _format_validation_message(self, operation: str, error: Exception, context: ErrorContext) -> str:
        """Format validation specific error message"""
        if context.user_input:
            return f"Invalid input for {operation}: {error!s}"
        return f"Validation failed during {operation}: {error!s}"

    def _format_technical_details(
        self,
        error: Exception,
        context: ErrorContext
    ) -> str:
        """Format technical error details for logging/debugging"""
        details = [
            f"Exception: {type(error).__name__}: {error!s}",
            f"Operation: {context.operation}",
        ]

        # Add exception chain information if available
        if hasattr(error, "__cause__") and error.__cause__ is not None:
            details.append(f"Caused by: {type(error.__cause__).__name__}: {error.__cause__!s}")

        if context.file_path:
            details.append(f"File: {context.file_path}")

        if context.component:
            details.append(f"Component: {context.component}")

        if context.user_input:
            details.append(f"User Input: {context.user_input}")

        if context.additional_info:
            for key, value in context.additional_info.items():
                details.append(f"{key}: {value}")

        # Add detailed exception chain
        details.append("\nException Chain:")
        current_error = error
        chain_level = 0
        while current_error is not None:
            indent = "  " * chain_level
            details.append(f"{indent}{type(current_error).__name__}: {current_error!s}")
            current_error = getattr(current_error, "__cause__", None)
            chain_level += 1
            if chain_level > 10:  # Prevent infinite loops
                break

        # Add stack trace for debugging
        details.append("\nStack trace:")
        details.append(traceback.format_exc())

        return "\n".join(details)

    def _generate_recovery_suggestions(
        self,
        error: Exception,
        category: ErrorCategory,
        context: ErrorContext
    ) -> list[str]:
        """Generate context-aware recovery suggestions"""
        suggestions = []

        # Get base suggestions for category
        base_suggestions = self._recovery_suggestions.get(category, [])
        suggestions.extend(base_suggestions)

        # Add specific suggestions based on error type
        if isinstance(error, FileNotFoundError):
            suggestions.insert(0, f"Verify that the file '{context.file_path}' exists")

        elif isinstance(error, PermissionError):
            suggestions.insert(0, "Check that you have permission to access the file")
            suggestions.append("Try running the application as administrator")

        elif isinstance(error, ValidationError):
            suggestions.insert(0, "Review the input requirements and try again")

        elif isinstance(error, InterruptedError):
            suggestions = ["The operation was cancelled", "You can try again"]

        # Add context-specific suggestions
        if context.recovery_possible:
            suggestions.append("Try the operation again with different parameters")
        else:
            suggestions.append("This error may require restarting the application")

        return list(dict.fromkeys(suggestions))  # Remove duplicates while preserving order

    def _should_suggest_retry(self, error: Exception, category: ErrorCategory) -> bool:
        """Determine if a retry should be suggested"""
        # Don't retry validation errors
        if category == ErrorCategory.VALIDATION:
            return False

        # Don't retry permission errors
        if isinstance(error, PermissionError):
            return False

        # Retry transient errors
        if category in (ErrorCategory.WORKER_THREAD, ErrorCategory.CACHE):
            return True

        return True

    def _should_suggest_abort(self, error: Exception, severity: ErrorSeverity) -> bool:
        """Determine if operation should be aborted"""
        return severity == ErrorSeverity.CRITICAL

    def _log_error(
        self,
        error: Exception,
        context: ErrorContext,
        result: ErrorResult
    ) -> None:
        """Log the error with appropriate level"""
        log_message = f"[{result.category.value}] {context.operation}: {error!s}"

        if result.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message, exc_info=error)
        elif result.severity == ErrorSeverity.HIGH:
            logger.error(log_message, exc_info=error)
        elif result.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.info(log_message)

    def _integrate_with_existing_handler(self, result: ErrorResult) -> None:
        """Integrate with error display handler for UI display"""
        if result.severity == ErrorSeverity.CRITICAL:
            self._error_display.handle_critical_error(
                "Critical Error", result.message
            )
        elif result.severity in (ErrorSeverity.HIGH, ErrorSeverity.MEDIUM):
            self._error_display.handle_warning(
                "Error", result.message
            )
        else:
            self._error_display.handle_info(
                "Notice", result.message
            )

    def set_error_display(self, error_display: IErrorDisplay) -> None:
        """Set the error display handler (for dependency injection)"""
        self._error_display = error_display

    def _add_to_history(self, error: Exception, context: ErrorContext) -> None:
        """Add error to history for analysis"""
        self._error_history.append((error, context))

        # Keep history size manageable
        if len(self._error_history) > self._max_history:
            self._error_history = self._error_history[-self._max_history:]

    # Convenience decorators and utilities

    def create_error_decorator(
        self,
        operation: str,
        category: ErrorCategory | None = None,
        **context_kwargs: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Create a decorator for handling errors in a specific operation"""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    context = ErrorContext(
                        operation=operation,
                        component=func.__name__,
                        **context_kwargs
                    )
                    result = self.handle_exception(e, context, category)

                    # Re-raise if not handled or critical
                    if not result.handled or result.should_abort:
                        raise

                    return None
            return wrapper
        return decorator

    def get_error_statistics(self) -> dict[str, Any]:
        """Get error statistics for monitoring"""
        categories = {}
        severities = {}

        for error, context in self._error_history:
            category = self._categorize_exception(error)
            severity = self._determine_severity(error, category, context)

            categories[category.value] = categories.get(category.value, 0) + 1
            severities[severity.value] = severities.get(severity.value, 0) + 1

        return {
            "total_errors": self._error_count,
            "categories": categories,
            "severities": severities,
            "recent_errors": len(self._error_history),
        }

class _UnifiedErrorHandlerSingleton:
    """Thread-safe singleton holder for UnifiedErrorHandler."""
    _instance: UnifiedErrorHandler | None = None
    _lock = threading.Lock()
    _error_display: IErrorDisplay | None = None

    @classmethod
    def get(cls, parent: _QWidget | None = None, error_display: IErrorDisplay | None = None) -> UnifiedErrorHandler:
        """Get or create the global unified error handler (thread-safe)

        Args:
            parent: Parent widget for Qt integration
            error_display: Error display handler (injected to break circular dependency)
        """
        # Fast path - check without lock
        if cls._instance is not None:
            # Update error display if provided
            if error_display is not None and cls._instance._error_display != error_display:
                cls._instance.set_error_display(error_display)
            return cls._instance

        # Slow path - create with lock
        with cls._lock:
            # Double-check pattern
            if cls._instance is None:
                # Use provided error display or stored one
                display = error_display or cls._error_display or ConsoleErrorDisplay()
                cls._instance = UnifiedErrorHandler(parent, display)
                cls._error_display = display
            return cls._instance

    @classmethod
    def set_error_display(cls, error_display: IErrorDisplay) -> None:
        """Set the error display handler for future instances"""
        with cls._lock:
            cls._error_display = error_display
            if cls._instance is not None:
                cls._instance.set_error_display(error_display)

    @classmethod
    def reset(cls) -> None:
        """Reset the global unified error handler (useful for testing)"""
        with cls._lock:
            cls._instance = None

def get_unified_error_handler(parent: _QWidget | None = None, error_display: IErrorDisplay | None = None) -> UnifiedErrorHandler:
    """Get or create the global unified error handler (thread-safe)

    Args:
        parent: Parent widget for Qt integration
        error_display: Error display handler (injected to break circular dependency)
    """
    return _UnifiedErrorHandlerSingleton.get(parent, error_display)

def set_global_error_display(error_display: IErrorDisplay) -> None:
    """Set the global error display handler

    This should be called during application initialization to inject
    the UI error handler and break the circular dependency.
    """
    _UnifiedErrorHandlerSingleton.set_error_display(error_display)

def reset_unified_error_handler() -> None:
    """Reset the global unified error handler (useful for testing)"""
    _UnifiedErrorHandlerSingleton.reset()

# Convenience functions for common error patterns

def handle_file_operation_error(
    operation: str,
    file_path: str,
    error_handler: UnifiedErrorHandler | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for file operations"""
    if error_handler is None:
        error_handler = get_unified_error_handler()

    return error_handler.create_error_decorator(
        operation=operation,
        category=ErrorCategory.FILE_IO,
        file_path=file_path
    )

def handle_validation_error(
    operation: str,
    error_handler: UnifiedErrorHandler | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for validation operations"""
    if error_handler is None:
        error_handler = get_unified_error_handler()

    return error_handler.create_error_decorator(
        operation=operation,
        category=ErrorCategory.VALIDATION
    )

def handle_worker_operation_error(
    operation: str,
    worker_name: str,
    error_handler: UnifiedErrorHandler | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for worker operations"""
    if error_handler is None:
        error_handler = get_unified_error_handler()

    return error_handler.create_error_decorator(
        operation=operation,
        category=ErrorCategory.WORKER_THREAD,
        component=worker_name
    )
